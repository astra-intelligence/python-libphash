"""The public API as a type checker sees it.

Checked by mypy and basedpyright (``assert_type`` fails the check when an inferred type
differs) and run by pytest, so every call is also exercised at run time.
"""

import io
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import libphash as ph

pytest.importorskip("numpy")
pytest.importorskip("PIL")
import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from typing_extensions import assert_type
else:

    def assert_type(value: object, _typ: object) -> object:
        return value


def test_hash_overloads(photo: Path) -> None:
    assert_type(ph.hash(photo), int)
    assert_type(ph.hash(photo, "dhash"), int)
    assert_type(ph.hash(photo, ph.Algorithm.WHASH), int)
    assert_type(ph.hash(photo, "radial"), ph.Digest)
    assert_type(ph.hash(photo, ph.Algorithm.COLOR_MOMENTS), ph.Digest)
    name = str(ph.Algorithm.BMH)  # a name known only at run time
    assert_type(ph.hash(photo, name), "int | ph.Digest")
    assert_type(ph.hamming_distance(ph.hash(photo), ph.hash(photo)), int)
    assert_type(ph.hash(photo, "mhash").similarity(ph.hash(photo, "mhash")), float)


def test_context_overloads(photo: Path) -> None:
    with ph.ImageContext() as ctx:
        ctx.load(photo)
        assert_type(ctx.hash(), int)
        assert_type(ctx.hash("ahash"), int)
        assert_type(ctx.hash("color_hash"), ph.Digest)
        assert_type(ctx.phash(), int)
        assert_type(ctx.radial(), ph.Digest)
        assert_type(ctx.hashes("phash", "bmh"), "dict[ph.Algorithm, int | ph.Digest]")


def test_load_accepts_every_source(photo: Path, photo_bytes: bytes) -> None:
    pixels = np.asarray(Image.open(photo).convert("RGB"))
    image = Image.open(photo)
    sources: list[ph.Source] = [
        photo,
        str(photo),
        photo_bytes,
        bytearray(photo_bytes),
        memoryview(photo_bytes),
        io.BytesIO(photo_bytes),
        pixels,
        image,
    ]
    expected = ph.hash(pixels)
    with ph.ImageContext() as ctx:
        for source in sources:
            ctx.load(source)
            assert isinstance(ctx.phash(), int)
        with open(photo, "rb") as f:
            ctx.load(f)
            ctx.load_fileobj(io.BytesIO(photo_bytes))
        ctx.load_pixels(pixels)
        assert ctx.phash() == expected
        ctx.load_pixels(np.zeros((8, 8), dtype=np.uint8))
        ctx.load_pil(image)
        ctx.load_file(str(photo).encode())


def test_batch_result_source_types(photo: Path, photo_bytes: bytes) -> None:
    files = ph.hash_files([photo], ["phash", "ahash"])
    assert_type(files, "list[ph.BatchResult[Path]]")
    assert_type(files[0].source, Path)
    assert_type(files[0].hashes, "dict[ph.Algorithm, int] | None")
    assert_type(files[0].error, "ph.PhashError | None")
    assert files[0].source == photo
    names = ph.hash_files([str(photo)], "dhash")
    assert_type(names[0].source, str)
    buffers = ph.hash_buffers([photo_bytes])
    assert_type(buffers, "list[ph.BatchResult[int]]")
    assert buffers[0].source == 0


def test_config_literals() -> None:
    whash: ph.WHashMode = "full"
    alpha: ph.AlphaMode = "white"
    scale: ph.DecodeScale = 4
    cfg = ph.Config(whash_mode=whash, alpha_mode=alpha, decode_scale=scale)
    assert_type(cfg.whash_mode, ph.WHashMode)
    assert_type(cfg.decode_scale, ph.DecodeScale)
    assert_type(cfg.replace(gamma=2.2), ph.Config)
    assert_type(ph.digest_info("bmh", cfg), "tuple[int, ph.DigestKind]")
