from typing import TYPE_CHECKING, cast

import pytest

import libphash as ph
from conftest import data

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


@pytest.mark.parametrize("mode", ["1", "P", "LA", "CMYK", "YCbCr"])
def test_pillow_modes_are_converted(mode: str) -> None:
    img = pil("png/rgb8.png").convert(mode)
    assert isinstance(ph.hash(img), int)


def test_pillow_16_bit_is_refused() -> None:
    with pytest.raises(TypeError, match="not 8-bit"):
        ph.hash(pil("png/rgb8.png").convert("I"))


def test_row_strided_crop_without_copy_matches_a_copy() -> None:
    arr = np.asarray(pil("photo.png").convert("RGB"))
    crop = arr[20:-30, 10:-40]
    assert not crop.flags.c_contiguous
    assert ph.hash(crop, "radial") == ph.hash(np.ascontiguousarray(crop), "radial")


def test_layouts_that_need_a_copy() -> None:
    arr = np.asarray(pil("photo.png").convert("RGB"))
    for view in (arr[:, ::2], arr[::-1], arr[::2, ::3], np.asfortranarray(arr)):
        assert ph.hash(view) == ph.hash(np.ascontiguousarray(view))


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
