"""Memory: what a load copies, what a context holds, what a batch peaks at.

Every case runs in a fresh interpreter (``python -m benchmarks.memory <case>``), so that
one case's peak cannot hide the next one's. The child prepares its input first, in a way
that never holds more memory than the input itself, then records its resident memory,
runs the case once with tracemalloc on, and reports two numbers:

- the peak of the Python allocations the case makes (tracemalloc): the copies the
  binding makes in Python, exactly and the same on every run;
- the rise of the process's peak resident memory over its resident memory before the
  case: the C library's own buffers (the decoded image, the decoder's) on top of that.
"""

from __future__ import annotations

import dataclasses
import gc
import io
import json
import os
import subprocess
import sys
import tracemalloc
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import psutil

import libphash as ph

from .fixtures import ROOT
from .report import Block

if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy.typing as npt

    from .fixtures import Image
    from .timing import Effort

#: The cases of one load: (key, row label).
LOADS = [
    ("load_file", "load_file()"),
    ("load_bytes", "load_bytes(bytes)"),
    ("load_memoryview", "load_bytes(memoryview)"),
    ("load_fileobj", "load_fileobj(open file)"),
    ("load_bytesio", "load_fileobj(BytesIO)"),
    ("numpy", "numpy, contiguous"),
    ("numpy_crop", "numpy, a crop: rows apart"),
    ("numpy_bgr", "numpy BGR, channel_order='bgr'"),
    ("numpy_bgr_reversed", "numpy BGR, bgr[..., ::-1]"),
    ("numpy_bgr_contiguous", "numpy BGR, np.ascontiguousarray(bgr[..., ::-1])"),
    ("pillow", "Pillow RGB image, load_pil()"),
    ("pillow_asarray", "Pillow RGB image, np.asarray()"),
]


@dataclass(frozen=True)
class Spec:
    """One case and its input: the file, and its pixels in ``<raw>.rgb``/``.bgr``."""

    case: str
    path: str
    raw: str
    width: int
    height: int
    count: int = 0
    threads: int = 0


# --- The child ------------------------------------------------------------------


def _peak_rss() -> int:
    if sys.platform == "win32":
        return int(psutil.Process().memory_info().peak_wset)
    import resource  # noqa: PLC0415 -- POSIX only

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux counts kibibytes, macOS bytes.
    return int(peak if sys.platform == "darwin" else peak * 1024)


def _rss() -> int:
    return int(psutil.Process().memory_info().rss)


def _pixels(spec: Spec, suffix: str) -> npt.NDArray[np.uint8]:
    pixels = np.fromfile(f"{spec.raw}.{suffix}", np.uint8)
    shape = (spec.height, spec.width, 3)
    return pixels.reshape(shape)  # pyright: ignore[reportUnknownMemberType]


def _framed(spec: Spec) -> npt.NDArray[np.uint8]:
    """Return the pixels as a crop of a frame of 10 pixels, read in without a copy."""
    framed = np.zeros((spec.height + 20, spec.width + 20, 3), np.uint8)
    with open(f"{spec.raw}.rgb", "rb") as f:
        for r in range(spec.height):
            f.readinto(memoryview(framed[10 + r, 10:-10]).cast("B"))
    return framed[10:-10, 10:-10]


def _encoded(spec: Spec, ctx: ph.ImageContext) -> Callable[[], object]:
    if spec.case == "load_file":
        return lambda: ctx.load_file(spec.path)
    if spec.case == "load_fileobj":

        def from_file() -> None:
            with open(spec.path, "rb") as f:
                ctx.load_fileobj(f)

        return from_file
    with open(spec.path, "rb") as f:
        data = f.read()
    if spec.case == "load_bytes":
        return lambda: ctx.load_bytes(data)
    if spec.case == "load_memoryview":
        return lambda: ctx.load_bytes(memoryview(data))
    return lambda: ctx.load_fileobj(io.BytesIO(data))


def _decoded(  # noqa: PLR0911 -- one return per case
    spec: Spec, ctx: ph.ImageContext
) -> Callable[[], object]:
    if spec.case == "numpy":
        rgb = _pixels(spec, "rgb")
        return lambda: ctx.load_pixels(rgb)
    if spec.case == "numpy_crop":
        crop = _framed(spec)
        return lambda: ctx.load_pixels(crop)
    if spec.case.startswith("numpy_bgr"):
        bgr = _pixels(spec, "bgr")
        if spec.case == "numpy_bgr":
            return lambda: ctx.load_pixels(bgr, "bgr")
        if spec.case == "numpy_bgr_reversed":
            return lambda: ctx.load_pixels(bgr[..., ::-1])
        return lambda: ctx.load_pixels(np.ascontiguousarray(bgr[..., ::-1]))
    from PIL import Image as PILImage  # noqa: PLC0415 -- optional, as in the binding

    img = PILImage.open(spec.path)
    img.load()
    if spec.case == "pillow":
        return lambda: ctx.load_pil(img)
    return lambda: ctx.load_pixels(np.asarray(img))


def _contexts(spec: Spec) -> Callable[[], object]:
    if spec.case == "contexts":
        kept: list[ph.ImageContext] = []
        return lambda: kept.extend(ph.ImageContext() for _ in range(spec.count))

    def loaded() -> None:
        ctx = ph.ImageContext()
        ctx.load_file(spec.path)
        ctx.hashes(*ph.Algorithm)
        if spec.case == "context_closed":
            ctx.close()
        else:
            kept_one.append(ctx)

    kept_one: list[ph.ImageContext] = []
    return loaded


def _case(spec: Spec) -> Callable[[], object]:
    """Prepare the case's input and return the case."""
    ctx = ph.ImageContext()
    if spec.case.startswith("load_"):
        return _encoded(spec, ctx)
    if spec.case.startswith(("numpy", "pillow")):
        return _decoded(spec, ctx)
    if spec.case.startswith("context"):
        return _contexts(spec)
    if spec.case == "batch":
        paths = [spec.path] * spec.count
        return lambda: ph.hash_files(paths, threads=spec.threads)
    if spec.case == "repeat":
        with open(spec.path, "rb") as f:
            data = f.read()

        def repeat() -> None:
            for _ in range(spec.count):
                ctx.load_bytes(data)
                ctx.phash()

        repeat()  # the warm-up: caches, free lists, the context's buffers
        return repeat
    raise ValueError(f"unknown case {spec.case!r}")


def child(spec: Spec) -> dict[str, int]:
    """Run one case in this process and return what it took."""
    work = _case(spec)
    gc.collect()
    rss = _rss()
    tracemalloc.start()
    work()
    gc.collect()
    python_kept, python_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "python_peak": python_peak,
        "python_kept": python_kept,
        "rss_rise": max(0, _peak_rss() - rss),
        "rss_after": _rss() - rss,
    }


# --- The parent -----------------------------------------------------------------


def _probe(spec: Spec) -> dict[str, int]:
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.memory",
            json.dumps(dataclasses.asdict(spec)),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    if run.returncode:
        raise RuntimeError(f"memory case {spec.case} failed:\n{run.stderr}")
    result: dict[str, int] = json.loads(run.stdout.splitlines()[-1])
    return result


def _spec(img: Image, case: str, count: int = 0, threads: int = 0) -> Spec:
    raw = img.raw.with_suffix("")
    bgr = raw.with_suffix(".bgr")
    if not bgr.exists():
        bgr.write_bytes(img.rgb[..., ::-1].tobytes())
    return Spec(case, str(img.path), str(raw), img.width, img.height, count, threads)


def run(images: list[Image], effort: Effort) -> Block:
    """Measure every table of the block."""
    block = Block("memory", "3. Memory")
    block.notes.append(
        "Each case runs once in a fresh interpreter. *Python* is the peak of the "
        "Python allocations the case makes (tracemalloc): the copies the binding "
        "makes, exact and the same on every run. *Resident* is the rise of the peak "
        "resident memory over the memory before the case: the C library's decoded "
        "image and decoder buffers on top of that. libphash keeps a decoded image as "
        "3 bytes per pixel."
    )
    loads = block.table(
        "load_memory",
        "Memory of one load",
        "A load into a new context, from each form of the image.",
        "B",
    )
    for img in images:
        for key, label in LOADS:
            r = _probe(_spec(img, key))
            loads.add(label, f"{img.label}: Python", r["python_peak"])
            loads.add(label, f"{img.label}: resident", r["rss_rise"])

    large = images[-1]
    count = 1000
    contexts = block.table(
        "contexts",
        "Contexts",
        f"What stays allocated: an empty context (per context, of {count:,}), one "
        f"holding the {large.label} image after its nine hashes, the same closed. "
        "Resident memory counts pages the allocator keeps for reuse after a free: "
        "macOS's allocator keeps the pages of a closed context resident until the "
        "system needs them.",
        "B",
    )
    r = _probe(_spec(large, "contexts", count=count))
    contexts.add("an empty context", "Python", r["python_kept"] / count)
    contexts.add("an empty context", "resident", r["rss_after"] / count)
    for case, label in (
        ("context_loaded", f"holding {large.label}, nine hashes"),
        ("context_closed", "the same, closed"),
    ):
        r = _probe(_spec(large, case))
        contexts.add(label, "Python", r["python_kept"])
        contexts.add(label, "resident", r["rss_after"])
        contexts.add(label, "resident at the peak", r["rss_rise"])

    _batch(block, large, effort)

    small = images[0]
    steps = effort.scale(10_000, 200)
    repeat = block.table(
        "repeat",
        "Repetition",
        f"load_bytes() and phash() of {small.label}, {steps:,} times on one context "
        "after as many to warm up: what stays allocated afterwards "
        "(tests/test_memory.py holds every path of the binding to a bound).",
        "B",
    )
    r = _probe(_spec(small, "repeat", count=steps))
    row = f"{steps:,} loads and hashes"
    repeat.add(row, "Python, kept", r["python_kept"])
    repeat.add(row, "Python, peak", r["python_peak"])
    repeat.add(row, "resident, kept", r["rss_after"])
    return block


def _batch(block: Block, img: Image, effort: Effort) -> None:
    cpus = os.cpu_count() or 1
    counts = sorted({1, 2, 4, 8, cpus} if not effort.quick else {1, 2})
    n = effort.scale(2 * cpus, 2)
    table = block.table(
        "batch_memory",
        f"Batch memory against threads, {img.label}",
        f"hash_files() of {n} copies of the file: the rise of peak resident memory, "
        "and the bound libphash states (4 bytes per pixel and the file, per worker).",
        "B",
    )
    estimate = 4 * img.width * img.height + len(img.data)
    for t in counts:
        r = _probe(_spec(img, "batch", count=n, threads=t))
        column = f"threads={t}"
        table.add("peak resident rise", column, r["rss_rise"])
        table.add("Python allocations", column, r["python_peak"])
        table.add("libphash's bound", column, estimate * min(t, n))


if __name__ == "__main__":
    answer = child(Spec(**json.loads(sys.argv[1])))
    print(json.dumps(answer))  # noqa: T201 -- the answer to the parent
