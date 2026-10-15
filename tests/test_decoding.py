"""Decoding: every format variant of libphash's fixtures, broken files and limits."""

from __future__ import annotations

import mmap
import os
import struct
import sys
import threading
import zlib
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import pytest
from conftest import DATA, data, libjpeg_turbo

import libphash as ph

if TYPE_CHECKING:
    from collections.abc import Callable

_T = TypeVar("_T")

JPEG_VARIANTS = sorted(p.name for p in (DATA / "jpeg").glob("*.jpg"))
PNG_VARIANTS = [
    *("gray1.png", "gray4.png", "gray8.png", "palette.png", "palette_trns.png"),
    *("rgb16.png", "rgb8.png", "rgb8_interlaced.png", "rgba8.png"),
    *("rgba8_interlaced.png", "rgb8.webp", "rgba8.webp"),
]
VARIANTS = [f"jpeg/{n}" for n in JPEG_VARIANTS] + [f"png/{n}" for n in PNG_VARIANTS]
BROKEN = [
    *("broken_header.png", "broken_truncated.png", "broken_crc.png"),
    *("broken_crc_ihdr.png", "broken_bitstream.webp", "broken_truncated.webp"),
]


def needs_decoder(name: str) -> None:
    if name.endswith(".webp") and not ph.can_decode("webp"):
        pytest.skip("no WebP decoder in this build")


@pytest.mark.parametrize("grayscale", [False, True])
@pytest.mark.parametrize("name", VARIANTS)
def test_every_variant_decodes(name: str, grayscale: bool) -> None:
    needs_decoder(name)
    with ph.ImageContext(ph.Config(grayscale=grayscale)) as ctx:
        if name == "jpeg/arithmetic.jpg" and not libjpeg_turbo():
            # stb_image has no arithmetic decoding.
            with pytest.raises(ph.CorruptDataError):
                ctx.load_file(data(name))
            return
        ctx.load_file(data(name))
        size = (61, 45) if name.startswith("jpeg/") else (8, 8)
        assert (ctx.width, ctx.height) == size
        # Gray sources are widened to RGB in color mode; grayscale mode folds every
        # source, WebP included, to one channel.
        assert ctx.channels == (1 if grayscale else 3)
        hashes = ctx.hashes(ph.Algorithm.AHASH, ph.Algorithm.PHASH, ph.Algorithm.MHASH)
        assert len(hashes) == 3


def test_a_bad_crc_on_an_ancillary_chunk_is_accepted() -> None:
    assert ph.hash(data("png/ancillary_bad_crc.png"), "ahash") == ph.hash(
        data("png/rgb8.png"), "ahash"
    )


@pytest.mark.parametrize("name", BROKEN)
def test_broken_files_are_corrupt_data(name: str) -> None:
    needs_decoder(name)
    with ph.ImageContext() as ctx:
        ctx.load_file(data("photo.png"))
        with pytest.raises(ph.CorruptDataError) as exc:
            ctx.load_file(data(f"png/{name}"))
        assert exc.value.detail
        assert not ctx.is_loaded


@pytest.mark.parametrize("keep", [0.5, 0.9])
def test_truncated_jpeg_is_corrupt_data(photo_bytes: bytes, keep: float) -> None:
    # The detail is the decoder's own message.
    message = "Premature end" if libjpeg_turbo() else "truncated"
    with pytest.raises(ph.CorruptDataError, match=message):
        ph.hash(photo_bytes[: int(len(photo_bytes) * keep)])


@pytest.mark.parametrize("name", ["photo.jpeg", "photo.png", "photo.webp"])
def test_data_after_the_end_is_ignored(name: str) -> None:
    needs_decoder(name)
    encoded = data(name).read_bytes()
    expected = ph.hash(encoded, "dhash")
    assert ph.hash(encoded + b"\0" * 100, "dhash") == expected
    assert ph.hash(encoded + b"trailing junk", "dhash") == expected


@pytest.mark.parametrize("scale", [1, 2, 4, 8])
def test_decode_scale_reduces_jpeg_only(scale: ph.DecodeScale) -> None:
    config = ph.Config(decode_scale=scale)
    with ph.ImageContext(config) as ctx:
        ctx.load_file(data("photo.jpeg"))
        side = 400 // scale if libjpeg_turbo() else 400
        assert (ctx.width, ctx.height) == (side, side)
        first = ctx.hashes(*ph.Algorithm)
        ctx.load_file(data("photo.jpeg"))
        assert ctx.hashes(*ph.Algorithm) == first
    for name in ("photo.png", "photo.webp"):
        if name.endswith(".webp") and not ph.can_decode("webp"):
            continue
        assert ph.hash(data(name), config=config) == ph.hash(data(name))


def png_header(width: int, height: int) -> bytes:
    """Return a PNG signature and an 8-bit RGB IHDR with its CRC, and no image data."""
    ihdr = b"IHDR" + struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + ihdr
        + struct.pack(">I", zlib.crc32(ihdr))
    )


def test_a_side_over_a_million_is_too_large_whatever_max_pixels() -> None:
    for config in (ph.Config(), ph.Config(max_pixels=0)):
        with pytest.raises(ph.ImageTooLargeError):
            ph.hash(png_header(1_000_001, 1), config=config)
    # Just inside the limit, the header passes and the missing data is the complaint.
    with pytest.raises(ph.CorruptDataError):
        ph.hash(png_header(1_000_000, 1))


@pytest.mark.parametrize("name", ["photo.jpeg", "photo.png", "photo.webp"])
def test_max_pixels_is_inclusive(name: str) -> None:
    needs_decoder(name)
    encoded = data(name).read_bytes()
    with ph.ImageContext() as ctx:
        ctx.load_bytes(encoded)
        pixels = ctx.width * ctx.height
    assert ph.hash(encoded, config=ph.Config(max_pixels=pixels)) == ph.hash(encoded)
    with pytest.raises(ph.ImageTooLargeError):
        ph.hash(encoded, config=ph.Config(max_pixels=pixels - 1))


def test_pixels_are_held_to_the_pixel_count_only() -> None:
    # A row longer than a file may have is fine as pixels: only max_pixels applies.
    row = memoryview(bytes(1_000_001)).cast("B", (1, 1_000_001))
    with ph.ImageContext() as ctx:
        ctx.load_pixels(row)
        assert (ctx.width, ctx.height, ctx.channels) == (1_000_001, 1, 1)
    small = ph.Config(max_pixels=1_000_000)
    with ph.ImageContext(small) as ctx, pytest.raises(ph.ImageTooLargeError):
        ctx.load_pixels(row)


INT_MAX = 2**31 - 1


@pytest.mark.parametrize(
    ("size", "too_large"),
    [(INT_MAX - 16, False), (INT_MAX + 4096, True), (2**32 + 4096, True)],
)
def test_buffers_over_int_max_are_refused(size: int, too_large: bool) -> None:
    # An anonymous mapping is zero pages until written: only the header page is real.
    png = data("png/rgb8.png").read_bytes()
    try:
        buffer = mmap.mmap(-1, size)
    except (OverflowError, OSError, MemoryError):
        pytest.skip("no address space for a 2 GiB mapping")
    with buffer:
        buffer[: len(png)] = png
        view = memoryview(buffer)
        try:
            if too_large:
                with pytest.raises(ph.ImageTooLargeError, match="2 GiB"):
                    ph.hash(view, "ahash")
            else:
                assert ph.hash(view, "ahash") == ph.hash(png, "ahash")
        finally:
            view.release()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX device files")
def test_a_device_is_not_a_regular_file() -> None:
    with pytest.raises(ph.ImageIOError, match="not a regular file"):
        ph.hash(Path(os.devnull))


def _returns_at_once(fifo: Path, call: Callable[[], _T]) -> _T:
    """Return what ``call`` returns, failing if it waits for a writer of ``fifo``."""
    result: list[_T] = []
    caller = threading.Thread(target=lambda: result.append(call()))
    caller.start()
    caller.join(timeout=5)
    if caller.is_alive():  # the call waits in open(): a writer releases it
        os.close(os.open(fifo, os.O_WRONLY))
        caller.join()
        pytest.fail("a load of a FIFO with no writer did not return")
    return result[0]


def _hash_error(path: Path) -> ph.PhashError | None:
    try:
        ph.hash(path)
    except ph.PhashError as e:
        return e
    return None


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFOs")
def test_a_fifo_with_no_writer_is_not_a_regular_file(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe.jpg"
    os.mkfifo(fifo)
    error = _returns_at_once(fifo, lambda: _hash_error(fifo))
    assert isinstance(error, ph.ImageIOError)
    assert "not a regular file" in str(error)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFOs")
def test_a_fifo_in_a_batch_fails_alone(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe.jpg"
    os.mkfifo(fifo)
    paths = [data("photo.jpeg"), fifo, data("photo.jpeg")]
    results = _returns_at_once(fifo, lambda: ph.hash_files(paths, "ahash", threads=1))
    assert [r.ok for r in results] == [True, False, True]
    assert isinstance(results[1].error, ph.ImageIOError)


#: A 2x2 uncompressed 24-bit TGA: an 18-byte header, then the pixels in one block.
TGA_2X2 = bytes.fromhex("0000020000000000000000000200020018000000ff00ff00ff0000ffffff")
#: A 2x2 flat (narrower than 8) Radiance HDR: a 45-byte header, then RGBE pixels.
HDR_2X2 = b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 2 +X 2\n" + bytes.fromhex(
    "80000080008000800000808080808080"
)


@pytest.mark.parametrize(
    ("image", "header"), [(TGA_2X2, 18), (HDR_2X2, 45)], ids=["tga", "hdr"]
)
def test_truncated_pixel_data_is_corrupt(image: bytes, header: int) -> None:
    ph.hash(image, "ahash")
    # A decoder that hands back an image whose pixels stop early hands back pixels
    # nobody wrote, and the same bytes would hash differently from load to load.
    for size in range(header, len(image)):
        with pytest.raises(ph.CorruptDataError):
            ph.hash(image[:size], "ahash")
