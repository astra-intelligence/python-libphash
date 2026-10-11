from typing import TYPE_CHECKING, cast

import pytest
from conftest import data, exactly

import libphash as ph
from libphash._native import ffi
from libphash._sources import pixels_from_array

np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


def pil(name: str) -> "PILImage":
    return cast("PILImage", Image.open(data(name)))


@pytest.mark.parametrize("name", ["png/rgb8.png", "png/rgba8.png", "png/gray8.png"])
def test_pillow_pixels_hash_like_the_file(name: str) -> None:
    # Lossless PNG: Pillow and libpng decode the same pixels.
    for algo in ("phash", "mhash"):
        assert ph.hash(pil(name), algo) == ph.hash(data(name), algo)


def test_numpy_matches_pillow() -> None:
    img = pil("png/rgb8.png")
    arr = np.asarray(img)
    assert ph.hash(arr) == ph.hash(img)
    assert ph.hash(np.ascontiguousarray(arr[:, :, :1])) == ph.hash(arr[:, :, 0].copy())


COLOR = (ph.Algorithm.COLOR_HASH, ph.Algorithm.COLOR_MOMENTS)


def all_hashes(source: ph.Source) -> list[int | ph.Digest]:
    """Every hash that a gray image has too."""
    return [ph.hash(source, a) for a in ph.Algorithm if a not in COLOR]


@pytest.mark.parametrize("mode", ["PA", "LA", "La", "RGBa"])
def test_pillow_modes_with_alpha_become_rgba(mode: str) -> None:
    # Pillow converts premultiplied La only from and to LA.
    rgba8 = pil("png/rgba8.png")
    img = rgba8.convert("LA").convert("La") if mode == "La" else rgba8.convert(mode)
    straight = img.convert("LA") if mode == "La" else img
    rgba = straight.convert("RGBA")
    assert all_hashes(img) == all_hashes(rgba)
    assert all_hashes(rgba) != all_hashes(straight.convert("RGB"))  # the alpha counts


def test_pillow_palette_becomes_rgba() -> None:
    img = pil("png/rgb8.png").convert("P")
    assert all_hashes(img) == all_hashes(img.convert("RGB"))
    img.info["transparency"] = img.getpixel((0, 0))
    rgba = img.convert("RGBA")
    assert all_hashes(img) == all_hashes(rgba)
    assert all_hashes(rgba) != all_hashes(img.convert("RGB"))


def test_pillow_bilevel_becomes_gray() -> None:
    img = pil("png/rgb8.png").convert("1")
    assert all_hashes(img) == all_hashes(img.convert("L"))
    with pytest.raises(ph.RequiresColorError):
        ph.hash(img, "color_hash")


@pytest.mark.parametrize("mode", ["CMYK", "YCbCr", "HSV", "LAB"])
def test_pillow_other_modes_become_rgb(mode: str) -> None:
    img = pil("png/rgb8.png").convert(mode)
    assert all_hashes(img) == all_hashes(img.convert("RGB"))


def test_pillow_16_bit_is_refused() -> None:
    message = (
        "Pillow mode 'I' is not 8-bit; convert it (img.convert('L') or 'RGB') first"
    )
    with pytest.raises(TypeError, match=exactly(message)):
        ph.hash(pil("png/rgb8.png").convert("I"))


class _LooksLikePillow:
    """Has Pillow's attributes but is not a Pillow image."""

    mode = "RGB"

    def tobytes(self) -> bytes:
        return b"\0" * 3


def test_only_pillow_images_are_read_as_pillow() -> None:
    with pytest.raises(TypeError, match="got _LooksLikePillow"):
        ph.hash(cast("ph.Source", _LooksLikePillow()))


def test_row_strided_crop_without_copy_matches_a_copy() -> None:
    arr = np.asarray(pil("photo.png").convert("RGB"))
    crop = arr[20:-30, 10:-40]
    assert not crop.flags.c_contiguous
    assert ph.hash(crop, "radial") == ph.hash(np.ascontiguousarray(crop), "radial")


def test_layouts_that_need_a_copy() -> None:
    arr = np.asarray(pil("photo.png").convert("RGB"))
    # Rows that overlap: the C stride must cover a whole row.
    overlapping = np.lib.stride_tricks.as_strided(
        arr, shape=(10, 20, 3), strides=(30, 3, 1)
    )
    views = (
        arr[:, ::2],
        arr[::-1],
        arr[::2, ::3],
        arr[:, :, ::-1],
        np.asfortranarray(arr),
        overlapping,
    )
    for view in views:
        assert ph.hash(view) == ph.hash(np.ascontiguousarray(view))


def address(pointer: object) -> int:
    return int(ffi.cast("uintptr_t", pointer))


def test_arrays_without_a_copy() -> None:
    # The pointer handed to C is the array's own memory, its row step the stride.
    rgb = np.asarray(pil("photo.png").convert("RGB"))
    gray = np.ascontiguousarray(rgb[:, :, 0])
    for arr in (rgb, rgb[20:-30, 10:-40], gray, gray[5:-5, 5:-5]):
        px = pixels_from_array(arr, "rgb")
        assert address(px.pointer) == arr.__array_interface__["data"][0]
        assert (px.height, px.width) == arr.shape[:2]
        assert px.stride == arr.strides[0]
    view = memoryview(rgb)
    px = pixels_from_array(view, "rgb")
    assert address(px.pointer) == address(ffi.from_buffer(view))
    assert (px.height, px.width, px.channels, px.stride) == (*rgb.shape, 0)


def test_bgr_order() -> None:
    rgb = np.asarray(pil("png/rgb8.png"))
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    assert ph.hash(bgr) != ph.hash(rgb)
    with ph.ImageContext() as ctx:
        ctx.load_pixels(bgr, channel_order="bgr")
        assert ctx.phash() == ph.hash(rgb)
    with pytest.raises(ValueError, match="3 or 4"):
        ph.ImageContext().load_pixels(rgb[:, :, 0], channel_order="bgr")


def test_memoryview_with_shape() -> None:
    rgb = np.asarray(pil("png/rgb8.png"))
    view = memoryview(rgb.tobytes()).cast("B", rgb.shape)
    assert ph.hash(view) == ph.hash(rgb)


def test_array_interface_checks_the_type() -> None:
    message = "pixels must be uint8, got typestr ''; convert the array to uint8 first"
    with pytest.raises(TypeError, match=exactly(message)):
        ph.hash(cast("ph.PixelArray", _Interface({"version": 3, "shape": (8, 8)})))


def test_wrong_dtype_and_shape() -> None:
    with pytest.raises(TypeError, match="uint8"):
        ph.hash(np.zeros((8, 8), dtype=np.uint16))
    with pytest.raises(TypeError, match="uint8"):
        ph.hash(np.zeros((8, 8), dtype=np.float32))
    with pytest.raises(ValueError, match="shape"):
        ph.hash(np.zeros((8, 8, 2), dtype=np.uint8))


def test_pixels_ignore_auto_orient() -> None:
    arr = np.asarray(pil("photo.png").convert("RGB"))
    assert ph.hash(arr, config=ph.Config(auto_orient=False)) == ph.hash(arr)


def test_channel_order_is_checked() -> None:
    rgb = np.asarray(pil("png/rgb8.png"))
    message = "channel_order must be 'rgb' or 'bgr', got 'RGB'"
    with pytest.raises(ValueError, match=exactly(message)):
        ph.ImageContext().load_pixels(rgb, channel_order=cast("ph.ChannelOrder", "RGB"))
    message = "channel_order='bgr' needs 3 or 4 channels"
    with pytest.raises(ValueError, match=exactly(message)):
        ph.ImageContext().load_pixels(rgb[:, :, 0], channel_order="bgr")


def test_not_an_array() -> None:
    message = "expected an array of pixels (numpy, memoryview with a shape), got object"
    with pytest.raises(TypeError, match=exactly(message)):
        ph.ImageContext().load_pixels(cast("ph.PixelArray", object()))
    # A buffer without a shape is one row of bytes.
    with pytest.raises(ValueError, match="shape"):
        ph.ImageContext().load_pixels(cast("ph.PixelArray", b"\0" * 12))


def test_memoryview_layouts() -> None:
    rgb = np.asarray(pil("png/rgb8.png"))
    for dtype, fmt in ((np.uint16, "H"), (np.int8, "b")):
        message = (
            f"pixels must be 8-bit unsigned (format 'B'), got format '{fmt}'; "
            "convert the array to uint8 first"
        )
        with pytest.raises(TypeError, match=exactly(message)):
            ph.hash(memoryview(np.zeros((8, 8), dtype=dtype)))
    # Format 'c' is a byte too.
    chars = memoryview(rgb.tobytes()).cast("c", rgb.shape)
    assert ph.hash(chars) == ph.hash(rgb)
    # A gapped view and BGR order are copied once.
    gapped = memoryview(rgb[:, ::2])
    assert ph.hash(gapped) == ph.hash(np.ascontiguousarray(rgb[:, ::2]))
    with ph.ImageContext() as ctx:
        ctx.load_pixels(memoryview(np.ascontiguousarray(rgb[:, :, ::-1])), "bgr")
        assert ctx.phash() == ph.hash(rgb)


class _Interface:
    """An array interface whose data is not an address and has no buffer."""

    def __init__(self, interface: dict[str, object]) -> None:
        self.__array_interface__ = interface


def test_array_interface_without_data() -> None:
    message = "the array does not expose its data through the buffer protocol"
    interface = {"version": 3, "typestr": "|u1", "shape": (8, 8, 3)}
    with pytest.raises(TypeError, match=exactly(message)):
        ph.hash(cast("ph.PixelArray", _Interface(interface)))
