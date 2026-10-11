"""The binding computes what libphash computes, compared with libphash called from C.

The golden files pin the values of a handful of photos; these tests run every fixture
of libphash, every setting at the ends of its range, raw pixels of every layout, and
the errors through both the binding and the C reference (``c_reference.py``), so a
setting passed to the wrong setter, a value narrowed differently from C, a load path
that decodes differently or an error code mapped wrongly shows up as a difference.
"""

from __future__ import annotations

import dataclasses
import random
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal

import pytest
from c_reference import DATA, Job, Reference, check

import libphash as ph

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path


# --- Fixtures -----------------------------------------------------------------------


def fixtures() -> list[Path]:
    return sorted(p for p in DATA.rglob("*") if p.is_file() and p.suffix != ".txt")


def require_fixtures() -> list[Path]:
    paths = fixtures()
    if not paths:
        pytest.skip("fixtures are missing (native/libphash not checked out?)")
    return paths


@pytest.mark.parametrize("source", ["file", "memory"])
def test_every_fixture(reference: Reference, source: Literal["file", "memory"]) -> None:
    # Broken files included: the error code is part of the result.
    check(reference, [Job(source, p) for p in require_fixtures()])


@pytest.mark.parametrize("source", ["file", "memory"])
def test_jpeg_fixtures_at_every_decode_scale(
    reference: Reference, source: Literal["file", "memory"]
) -> None:
    jpegs = [p for p in require_fixtures() if p.suffix in (".jpg", ".jpeg")]
    check(
        reference,
        [
            Job(source, p, {"decode_scale": s}, None)
            for p in jpegs
            if p.name != "photo_large.jpeg"
            for s in (2, 4, 8)
        ],
    )


# Each field at the ends of its range and just past them, and a value inside. Values
# past the range check that the binding refuses what C refuses, with C's code.
SETTINGS: list[Mapping[str, object]] = [
    *({"gamma": v} for v in (0.001, 0.0011, 0.45, 2.2, 1000.0, 1000.0001)),
    *(
        {"gray_weights": v}
        for v in (
            (1, 0, 0),
            (0, 1, 0),
            (0, 0, 1),
            (299, 587, 114),
            (8421504, 0, 0),
            (8421505, 0, 0),
            (0, 0, 0),
            (-1, 1, 1),
        )
    ),
    *(
        {"phash_dct_size": d, "phash_reduction_size": r}
        for d, r in (
            *((4, 4), (8, 8), (16, 6), (32, 4)),
            *((7, 8), (33, 8), (32, 3), (32, 9)),
        )
    ),
    *({"radial_projections": v} for v in (39, 40, 4096, 4097)),
    *({"radial_samples": v} for v in (1, 2, 4096, 4097)),
    *({"radial_sigma": v} for v in (0.0, 0.01, 64 / 3, 21.34)),
    *({"bmh_block_size": v} for v in (1, 2, 7, 32, 33)),
    *({"mhash_alpha": v} for v in (1.0, 1.0001, 3.0)),
    *({"mhash_level": v} for v in (-0.5, 0.0, 2.5)),
    {"mhash_alpha": 4.0, "mhash_level": 3.0},
    *({"mhash_size": v} for v in (61, 62, 1000, 4096, 4097)),
    {"whash_mode": "full"},
    {"whash_remove_max_haar_ll": True},
    {"whash_mode": "full", "whash_remove_max_haar_ll": True},
    {"grayscale": True},
    {"grayscale": True, "alpha_mode": "white"},
    *({"alpha_mode": v} for v in ("white", "black", "ignore")),
    {"auto_orient": False},
    *({"max_pixels": v} for v in (0, 1, 4096, 2**64 - 1)),
]
SETTINGS_FIXTURES = ["photo.jpeg", "png/rgba8.png", "photo_rotated_90.jpeg"]


def test_every_setting(reference: Reference) -> None:
    require_fixtures()
    check(
        reference,
        [Job("file", DATA / f, s) for f in SETTINGS_FIXTURES for s in SETTINGS],
    )


# --- Pixels -------------------------------------------------------------------------


def pixel_shapes() -> Iterator[tuple[int, int, int, int]]:
    """(width, height, channels, stride): degenerate sizes, odd sizes, padded rows."""
    for channels in (1, 3, 4):
        for width, height in ((1, 1), (2, 3), (7, 5), (64, 48), (301, 199)):
            row = width * channels
            yield width, height, channels, 0
            yield width, height, channels, row + 13


@pytest.fixture(scope="module")
def pixel_jobs(tmp_path_factory: pytest.TempPathFactory) -> list[Job]:
    directory = tmp_path_factory.mktemp("pixels")
    rng = random.Random(20261011)
    jobs: list[Job] = []
    for width, height, channels, stride in pixel_shapes():
        size = (stride or width * channels) * height
        # Noise, and a gradient that the hashes see as an image rather than as noise.
        noise = rng.randbytes(size)
        gradient = bytes((i * 7 + i // 97) % 256 for i in range(size))
        for kind, raw in (("noise", noise), ("gradient", gradient)):
            path = directory / f"{kind}-{width}x{height}x{channels}-{stride}.raw"
            path.write_bytes(raw)
            shape = (width, height, channels, stride)
            jobs.append(Job("pixels", path, {}, shape))
            if channels == 4:
                jobs.extend(
                    Job("pixels", path, {"alpha_mode": mode}, shape)
                    for mode in ("white", "black", "ignore")
                )
            if channels > 1:
                jobs.append(Job("pixels", path, {"grayscale": True}, shape))
    return jobs


def test_pixels(reference: Reference, pixel_jobs: list[Job]) -> None:
    check(reference, pixel_jobs)


def test_pixels_past_max_pixels(reference: Reference, pixel_jobs: list[Job]) -> None:
    job = next(j for j in pixel_jobs if j.shape and j.shape[:2] == (64, 48))
    check(reference, [dataclasses.replace(job, settings={"max_pixels": 64 * 48 - 1})])


# --- Batches ------------------------------------------------------------------------


Outcome = Mapping[ph.Algorithm, int | ph.Digest] | int


def outcomes(
    results: Iterable[ph.BatchResult[Path] | ph.BatchResult[int]],
) -> list[Outcome]:
    """Each item's hashes, or its error code."""
    out: list[Outcome] = []
    for result in results:
        if result.hashes is not None:
            out.append(result.hashes)
        else:
            assert result.error is not None
            out.append(result.error.code)
    return out


def hashed_alone(path: Path, algorithms: list[ph.Algorithm]) -> Outcome:
    try:
        with ph.ImageContext() as ctx:
            ctx.load_file(path)
            return ctx.hashes(*algorithms)
    except ph.PhashError as e:
        return e.code


@pytest.mark.parametrize("threads", [1, 2, 3, 8])
def test_batches_hash_like_single_images(threads: int) -> None:
    paths = require_fixtures()
    uint64 = [a for a in ph.Algorithm if a < ph.Algorithm.BMH]
    alone = [hashed_alone(p, uint64) for p in paths]
    assert outcomes(ph.hash_files(paths, uint64, threads=threads)) == alone
    buffers = [p.read_bytes() for p in paths]
    assert outcomes(ph.hash_buffers(buffers, uint64, threads=threads)) == alone
