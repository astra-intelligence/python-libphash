"""Decoded pixels against Pillow's: format variants, EXIF orientation, alpha."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, cast, get_args

import pytest
from conftest import data
from test_decoding import VARIANTS, needs_decoder

import libphash as ph

pytest.importorskip("numpy")
pytest.importorskip("PIL")
import numpy as np
from PIL import Image, ImageOps

if TYPE_CHECKING:
    from numpy.typing import NDArray
    from PIL.Image import Image as PILImage

ALPHA_MODES: tuple[ph.AlphaMode, ...] = get_args(ph.AlphaMode)
ORIENTATION = 0x0112


def open_image(source: bytes) -> PILImage:
    return cast("PILImage", Image.open(io.BytesIO(source)))


@pytest.mark.parametrize("alpha_mode", ALPHA_MODES)
@pytest.mark.parametrize("name", [v for v in VARIANTS if "ancillary" not in v])
def test_variants_hash_like_their_pillow_pixels(
    name: str, alpha_mode: ph.AlphaMode
) -> None:
    needs_decoder(name)
    image = cast("PILImage", Image.open(data(name)))
    if image.mode not in ("RGB", "RGBA", "P", "LA", "PA"):
        # One channel is a grayscale image by contract; the file is widened to RGB.
        image = image.convert("RGB")
    config = ph.Config(alpha_mode=alpha_mode)
    with ph.ImageContext(config) as from_file, ph.ImageContext(config) as from_pixels:
        from_file.load_file(data(name))
        from_pixels.load_pil(image)
        assert from_file.hashes(*ph.Algorithm) == from_pixels.hashes(*ph.Algorithm)


def with_orientation(fmt: str, orientation: int) -> bytes:
    """photo.jpeg cropped to a landscape, stored with an EXIF orientation."""
    image = cast("PILImage", Image.open(data("photo.jpeg"))).crop((0, 0, 400, 240))
    exif = Image.Exif()
    exif[ORIENTATION] = orientation
    out = io.BytesIO()
    image.save(out, fmt, exif=exif.tobytes())
    return out.getvalue()


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
@pytest.mark.parametrize("orientation", range(1, 9))
def test_exif_orientation(fmt: str, orientation: int) -> None:
    encoded = with_orientation(fmt, orientation)
    stored = open_image(encoded)
    upright = ImageOps.exif_transpose(open_image(encoded))
    assert stored.getexif()[ORIENTATION] == orientation
    with ph.ImageContext() as ctx, ph.ImageContext() as expected:
        ctx.load_bytes(encoded)
        expected.load_pil(upright)
        assert (ctx.width, ctx.height) == upright.size
        assert ctx.hashes(*ph.Algorithm) == expected.hashes(*ph.Algorithm)
    with ph.ImageContext(ph.Config(auto_orient=False)) as ctx, ph.ImageContext() as raw:
        ctx.load_bytes(encoded)
        raw.load_pil(stored)
        assert (ctx.width, ctx.height) == (400, 240)
        assert ctx.hashes(*ph.Algorithm) == raw.hashes(*ph.Algorithm)


def test_rotated_fixture_is_rotated_pixels_not_exif() -> None:
    # photo_rotated_90.jpeg says orientation 1: auto_orient has nothing to undo.
    path = data("photo_rotated_90.jpeg")
    assert ph.hash(path, config=ph.Config(auto_orient=False)) == ph.hash(path)
    assert ph.hash(path) != ph.hash(data("photo.jpeg"))


def rgba_with_hidden(color: int) -> NDArray[np.uint8]:
    """Return the photo with a transparent checkerboard hiding ``color``."""
    image = Image.open(data("photo.jpeg")).convert("RGB")
    width, height = image.size
    rgba = np.empty((height, width, 4), dtype=np.uint8)
    rgba[..., :3] = np.asarray(image)
    rgba[..., 3] = 255
    rows = np.arange(height, dtype=np.intp) // 50
    cols = np.arange(width, dtype=np.intp) // 50
    hidden = (rows[:, None] + cols[None, :]) % 2 == 0
    rgba[hidden, :3] = color
    rgba[hidden, 3] = 0
    return rgba


def as_png(pixels: NDArray[np.uint8]) -> bytes:
    out = io.BytesIO()
    Image.fromarray(pixels, "RGBA").save(out, "PNG")
    return out.getvalue()


@pytest.mark.parametrize("alpha_mode", ALPHA_MODES)
def test_color_under_alpha_zero(alpha_mode: ph.AlphaMode) -> None:
    black, white = rgba_with_hidden(0), rgba_with_hidden(255)
    config = ph.Config(alpha_mode=alpha_mode)
    hashes = {}
    for name, pixels in (("black", black), ("white", white)):
        with (
            ph.ImageContext(config) as from_file,
            ph.ImageContext(config) as from_array,
        ):
            from_file.load_bytes(as_png(pixels))
            from_array.load_pixels(pixels)
            assert from_file.channels == from_array.channels == 3
            hashes[name] = from_file.hashes(*ph.Algorithm)
            assert from_array.hashes(*ph.Algorithm) == hashes[name]
    if alpha_mode == "ignore":
        # The color channels are hashed as they are, hidden color included.
        a = ph.hash(black, "ahash", config=config)
        assert ph.hamming_distance(a, ph.hash(white, "ahash", config=config)) > 10
    else:
        assert hashes["black"] == hashes["white"]


def test_alpha_modes_differ() -> None:
    pixels = rgba_with_hidden(200)  # not a background color: "ignore" differs too
    values = {
        mode: ph.hash(pixels, "ahash", config=ph.Config(alpha_mode=mode))
        for mode in ALPHA_MODES
    }
    assert len(set(values.values())) == len(ALPHA_MODES)
