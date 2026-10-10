"""The overhead benchmark: what the Python binding adds to the C library's work.

Each case is timed twice, through the binding's API and as the bare C call through
cffi that the API makes, on the same image: the difference is the binding's own cost
(argument checks, the context's lock, building the result). The remaining cases compare
the binding's ways of doing one job: a new context per image or one reused, an array of
pixels passed without a copy or copied, a loop or a batch.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import libphash as ph
from libphash._native import ffi, lib

from .timing import MIN_RUNS, MIN_SECONDS, Timing, measure

if TYPE_CHECKING:
    from collections.abc import Callable

    from libphash._native import ph_context_t_ptr

#: The test suite's photograph (400x400 JPEG): small, so that the overhead shows.
IMAGE = (
    Path(__file__).resolve().parent.parent
    / "native"
    / "libphash"
    / "tests"
    / "data"
    / "photo.jpeg"
)
#: Images per run of the loop and batch cases.
BATCH = 64


@dataclass(frozen=True)
class OverheadCase:
    """One way of doing a job, and its time per call."""

    job: str
    how: str
    time: Timing


@dataclass(frozen=True)
class OverheadResult:
    """The overhead benchmark's times."""

    image: str
    cases: list[OverheadCase]


def _raw_context() -> ph_context_t_ptr:
    out = ffi.new("ph_context_t **")
    if lib.ph_create(out) != lib.PH_SUCCESS:
        raise MemoryError("ph_create() failed")
    return ffi.gc(out[0], lib.ph_free)


def _cases(path: str) -> list[tuple[str, str, Callable[[], object], int]]:
    """Return ``(job, how, work, items per run)`` for every case."""
    data = Path(path).read_bytes()
    raw = _raw_context()
    if lib.ph_load_from_memory(raw, data, len(data)) != lib.PH_SUCCESS:
        raise ValueError(f"libphash cannot load {path}")
    out = ffi.new("uint64_t *")
    ctx = ph.ImageContext()
    ctx.load_bytes(data)
    loaded = ph.ImageContext()
    paths = [path] * BATCH

    def loop() -> None:
        for p in paths:
            loaded.load_file(p)
            loaded.ahash()

    cases: list[tuple[str, str, Callable[[], object], int]] = [
        (
            "aHash of a loaded image",
            "C through cffi",
            lambda: lib.ph_compute_ahash(raw, out),
            1,
        ),
        ("aHash of a loaded image", "ImageContext.ahash()", ctx.ahash, 1),
        (
            "load encoded bytes",
            "C through cffi",
            lambda: lib.ph_load_from_memory(raw, data, len(data)),
            1,
        ),
        (
            "load encoded bytes",
            "ImageContext.load_bytes()",
            lambda: ctx.load_bytes(data),
            1,
        ),
        (
            "file to aHash",
            "libphash.hash(), a new context",
            lambda: ph.hash(path, "ahash"),
            1,
        ),
        ("file to aHash", "one ImageContext, reused", loop, BATCH),
        (
            "file to aHash",
            "hash_files(), 1 thread",
            lambda: ph.hash_files(paths, "ahash", threads=1),
            BATCH,
        ),
    ]
    if importlib.util.find_spec("numpy") is not None:
        cases += _pixel_cases(path)
    return cases


def _pixel_cases(path: str) -> list[tuple[str, str, Callable[[], object], int]]:
    import numpy as np  # noqa: PLC0415 -- optional
    from PIL import Image  # noqa: PLC0415 -- optional

    with Image.open(path) as image:
        rgb = np.ascontiguousarray(np.asarray(image.convert("RGB")))
    framed = np.zeros((rgb.shape[0] + 20, rgb.shape[1] + 20, 3), np.uint8)
    framed[10:-10, 10:-10] = rgb
    crop = framed[10:-10, 10:-10]  # rows spaced apart: passed with a stride
    bgr = np.ascontiguousarray(rgb[..., ::-1])
    raw = _raw_context()
    pointer = ffi.cast("const uint8_t *", rgb.ctypes.data)
    height, width = rgb.shape[:2]
    ctx = ph.ImageContext()
    job = "load pixels (numpy)"
    return [
        (
            job,
            "C through cffi",
            lambda: lib.ph_load_from_pixels(raw, pointer, width, height, 3, 0),
            1,
        ),
        (job, "contiguous array, no copy", lambda: ctx.load_pixels(rgb), 1),
        (job, "cropped view, no copy", lambda: ctx.load_pixels(crop), 1),
        (job, "BGR, one copy", lambda: ctx.load_pixels(bgr, "bgr"), 1),
    ]


def measure_overhead(
    path: str | None = None,
    *,
    min_runs: int = MIN_RUNS,
    min_seconds: float = MIN_SECONDS,
) -> OverheadResult:
    """Time every case on ``path`` (the test suite's photograph by default)."""
    image = path or str(IMAGE)
    return OverheadResult(
        image,
        [
            OverheadCase(
                job,
                how,
                measure(work, items, min_runs=min_runs, min_seconds=min_seconds),
            )
            for job, how, work, items in _cases(image)
        ],
    )
