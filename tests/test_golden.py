"""Every hash of every libphash golden fixture, byte for byte the C library's.

libphash commits the expected hashes of its fixtures in
``tests/data/golden_hashes.<jpeg decoder>.txt`` and its own test compares them exactly:
the library computes the same on every platform, so there is no tolerance. The binding
reaches the same values through each way it loads an image. A wrong signature or struct
layout in the cdef, a digest copied short, a kind or algorithm mapped to the wrong C
value, or an ``int`` built from the wrong byte order all show up here as a mismatch.
"""

from __future__ import annotations

import itertools
import re
from typing import TYPE_CHECKING, NamedTuple

import pytest
from conftest import DATA, data

import libphash as ph
import libphash._batch
import libphash._context

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# The C test's names for the algorithms.
C_NAMES = {
    "aHash": ph.Algorithm.AHASH,
    "dHash": ph.Algorithm.DHASH,
    "pHash": ph.Algorithm.PHASH,
    "wHash": ph.Algorithm.WHASH,
    "BMH": ph.Algorithm.BMH,
    "ColorMoments": ph.Algorithm.COLOR_MOMENTS,
    "Radial": ph.Algorithm.RADIAL,
    "mHash": ph.Algorithm.MHASH,
    "ColorHash": ph.Algorithm.COLOR_HASH,
}
UINT64 = (
    ph.Algorithm.AHASH,
    ph.Algorithm.DHASH,
    ph.Algorithm.PHASH,
    ph.Algorithm.WHASH,
)

# build_info()'s jpeg= value -> the golden file's name. The two JPEG decoders round
# their IDCT differently; nothing else in a build changes a value.
GOLDEN_FILES = {"libjpeg-turbo": "libjpegturbo", "stb": "stbjpeg"}


class Entry(NamedTuple):
    """One line of a golden file."""

    fixture: str
    algorithm: ph.Algorithm
    hex: str


def golden_file() -> Path:
    match = re.search(r"\bjpeg=(\S+)", ph.build_info())
    assert match, ph.build_info()
    return data(f"golden_hashes.{GOLDEN_FILES[match.group(1)]}.txt")


def golden() -> list[Entry]:
    if not (DATA / "golden_hashes.libjpegturbo.txt").exists():
        return []
    entries: list[Entry] = []
    for line in golden_file().read_text().splitlines():
        fixture, name, hex_value = line.split()
        entries.append(Entry(fixture, C_NAMES[name], hex_value))
    return entries


ENTRIES = golden()
FIXTURES = sorted({e.fixture for e in ENTRIES})


def decodable(fixture: str) -> bool:
    return not fixture.endswith(".webp") or ph.can_decode("webp")


def check(entry: Entry, value: int | ph.Digest) -> None:
    where = f"{entry.fixture} {entry.algorithm}"
    if entry.algorithm in UINT64:
        assert isinstance(value, int), where
        assert ph.hash_to_hex(value) == entry.hex, where
        assert value == int(entry.hex, 16), where
    else:
        assert isinstance(value, ph.Digest), where
        assert value.data.hex() == entry.hex, where
        assert (len(value), value.kind) == ph.digest_info(entry.algorithm), where


def test_the_golden_file_covers_every_fixture_and_algorithm() -> None:
    if not ENTRIES:
        pytest.skip("golden files are missing (native/libphash not checked out?)")
    pairs = [(e.fixture, e.algorithm) for e in ENTRIES]
    assert len(pairs) == len(set(pairs))
    assert set(pairs) == set(itertools.product(FIXTURES, ph.Algorithm))


def load_with_c(ctx: ph.ImageContext, path: Path) -> None:
    ctx.load_file(path)


def load_bytes(ctx: ph.ImageContext, path: Path) -> None:
    ctx.load_bytes(path.read_bytes())


def load_fileobj(ctx: ph.ImageContext, path: Path) -> None:
    with path.open("rb") as f:
        ctx.load_fileobj(f)


LOADERS: dict[str, Callable[[ph.ImageContext, Path], None]] = {
    "file": load_with_c,
    "bytes": load_bytes,
    "fileobj": load_fileobj,
}


@pytest.mark.parametrize("loader", LOADERS)
@pytest.mark.parametrize("fixture", FIXTURES)
def test_every_load_path_gives_the_golden_hashes(fixture: str, loader: str) -> None:
    if not decodable(fixture):
        pytest.skip("no WebP decoder in this build")
    entries = [e for e in ENTRIES if e.fixture == fixture]
    with ph.ImageContext() as ctx:
        LOADERS[loader](ctx, data(fixture))
        values = ctx.hashes(*(e.algorithm for e in entries))
        for entry in entries:
            check(entry, values[entry.algorithm])
            check(entry, getattr(ctx, str(entry.algorithm))())


@pytest.mark.parametrize("fixture", FIXTURES)
def test_files_read_in_python_give_the_golden_hashes(
    fixture: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not decodable(fixture):
        pytest.skip("no WebP decoder in this build")
    # The Windows path: the binding reads the file and hands libphash the bytes.
    monkeypatch.setattr(libphash._context, "READ_FILES_IN_PYTHON", True)
    for entry in (e for e in ENTRIES if e.fixture == fixture):
        check(entry, ph.hash(data(fixture), entry.algorithm))


@pytest.mark.parametrize("read_in_python", [False, True])
def test_batches_give_the_golden_hashes(
    read_in_python: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(libphash._batch, "READ_FILES_IN_PYTHON", read_in_python)
    fixtures = [f for f in FIXTURES if decodable(f)]
    if not fixtures:
        pytest.skip("golden files are missing (native/libphash not checked out?)")
    paths = [data(f) for f in fixtures]
    by_file = ph.hash_files(paths, UINT64, threads=2)
    by_buffer = ph.hash_buffers([p.read_bytes() for p in paths], UINT64, threads=2)
    for fixture, from_file, from_buffer in zip(
        fixtures, by_file, by_buffer, strict=True
    ):
        assert from_file.hashes is not None, from_file.error
        assert from_buffer.hashes is not None, from_buffer.error
        for entry in (
            e for e in ENTRIES if e.fixture == fixture and e.algorithm in UINT64
        ):
            check(entry, from_file.hashes[entry.algorithm])
            check(entry, from_buffer.hashes[entry.algorithm])


def test_hex_forms_parse_back_to_the_golden_values() -> None:
    for entry in ENTRIES:
        if entry.algorithm in UINT64:
            assert ph.hash_to_hex(ph.hash_from_hex(entry.hex)) == entry.hex
            continue
        size, kind = ph.digest_info(entry.algorithm)
        digest = ph.Digest.from_hex(f"{kind.name.lower()}:{entry.hex}")
        assert (digest.kind, len(digest), digest.data.hex()) == (kind, size, entry.hex)
