"""Memory: repeating an operation does not grow it, and a batch peaks where C says.

Each scenario of the growth test runs once per step; after a warm-up (caches, free
lists, lazy imports) the step is repeated, and neither the Python objects it leaves
behind (tracemalloc) nor the process's resident memory, where a block the C side never
frees shows up, may grow past a bound far below what one leaked object or one leaked
image per step would add.

Under a sanitizer nothing is measured: its allocator keeps freed memory in quarantine
and its shadow memory adds to every block, the interpreter allocates through malloc()
there, which some of its caches fill slowly enough to look like growth, and
LeakSanitizer checks the C side instead.
"""

from __future__ import annotations

import gc
import subprocess
import sys
import sysconfig
import tracemalloc
from typing import TYPE_CHECKING

import psutil
import pytest
from conftest import SANITIZER, data

import libphash as ph
from libphash._sources import READ_FILES_IN_PYTHON

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.skipif(
    SANITIZER is not None, reason="a sanitizer's allocator holds freed memory"
)

STEPS = 400
#: tracemalloc: about 10 bytes per step, less than the smallest Python object.
PYTHON_BOUND = 4 * 1024
#: Resident memory: about 2.5 KiB per step, less than one leaked 32x32 RGB image.
RSS_BOUND = 1024 * 1024

ALGORITHMS = tuple(ph.Algorithm)


def load_file() -> None:
    with ph.ImageContext() as ctx:
        ctx.load_file(data("png/rgb8.png"))
        for algo in ALGORITHMS:
            ctx.hash(algo)


def load_bytes() -> None:
    with ph.ImageContext() as ctx:
        ctx.load_bytes(data("jpeg/s420.jpg").read_bytes())
        ctx.hashes(*ALGORITHMS)


def missing_file() -> None:
    with ph.ImageContext() as ctx, pytest.raises(ph.ImageIOError):
        ctx.load_file(data("png/rgb8.png").with_name("missing.png"))


def corrupt_bytes() -> None:
    with ph.ImageContext() as ctx:
        for name in ("corrupted.jpg", "png/broken_truncated.png", "png/broken_crc.png"):
            with pytest.raises(ph.PhashError):
                ctx.load_bytes(data(name).read_bytes())


def refused_hashes() -> None:
    gray = memoryview(bytes(range(256)) * 4).cast("B", (32, 32))
    flat = memoryview(bytes(32 * 32 * 3)).cast("B", (32, 32, 3))
    with ph.ImageContext() as ctx:
        ctx.load_pixels(gray)
        with pytest.raises(ph.RequiresColorError):
            ctx.color_hash()
        ctx.load_pixels(flat)
        radial = ctx.radial()
    with pytest.raises(ph.NoStructureError):
        radial.similarity(radial)


def copied_pixels() -> None:
    rgba = memoryview(bytes(range(256)) * 32).cast("B", (64, 32, 4))
    with ph.ImageContext() as ctx:
        ctx.load_pixels(rgba[::2], channel_order="bgr")
        for algo in ALGORITHMS:
            ctx.hash(algo)
        with pytest.raises(ValueError, match="shape"):
            ctx.load_pixels(memoryview(bytes(10)))


def unclosed_context() -> None:
    ctx = ph.ImageContext()
    ctx.load_file(data("png/rgb8.png"))
    ctx.phash()
    del ctx


def closed_context() -> None:
    ctx = ph.ImageContext()
    ctx.close()
    with pytest.raises(ValueError, match="closed"):
        ctx.phash()


def invalid_config() -> None:
    with pytest.raises(ph.InvalidArgumentError):
        ph.Config(phash_dct_size=1)


def digests() -> None:
    with ph.ImageContext() as ctx:
        ctx.load_file(data("png/rgb8.png"))
        a, b = ctx.bmh(), ctx.radial()
    assert ph.Digest.from_hex(a.hex()) == a
    a.similarity(a)
    b.similarity(b)
    with pytest.raises(ph.DigestKindError):
        a.l2_distance(a)
    with pytest.raises(ph.PhashError):
        ph.Digest.from_hex("bits:zz")
    ph.digest_info("radial")


def batch() -> None:
    buffers = [data("png/rgb8.png").read_bytes(), b"not an image", b""]
    results = ph.hash_buffers(buffers, ("phash", "dhash"), threads=2)
    assert [r.ok for r in results] == [True, False, False]


def batch_callback_error() -> None:
    def progress(done: int, total: int) -> bool:
        raise KeyError(done, total)

    with pytest.raises(KeyError):
        ph.hash_buffers(
            [data("png/rgb8.png").read_bytes()] * 2, progress=progress, threads=2
        )


SCENARIOS: dict[str, Callable[[], None]] = {
    f.__name__: f
    for f in (
        load_file,
        load_bytes,
        missing_file,
        corrupt_bytes,
        refused_hashes,
        copied_pixels,
        unclosed_context,
        closed_context,
        invalid_config,
        digests,
        batch,
        batch_callback_error,
    )
}


def _repeat(step: Callable[[], None]) -> None:
    for _ in range(STEPS):
        step()
    gc.collect()


def _growth(step: Callable[[], None], measure: Callable[[], int]) -> int:
    """Return the smaller growth of ``measure`` over two runs of the steps.

    A leak grows memory in both. A table the interpreter enlarges once (the interned
    strings, a free list), when the tests before this one have brought it to the edge,
    grows it in one only.
    """
    growths: list[int] = []
    for _ in range(2):
        before = measure()
        _repeat(step)
        growths.append(measure() - before)
    return min(growths)


def _traced() -> int:
    return tracemalloc.get_traced_memory()[0]


#: The scenarios whose callbacks run on libphash's worker threads.
WORKER_CALLBACKS = {"batch", "batch_callback_error"}

# On a free-threaded build, cffi 2.1.1 leaves the argument tuple of an extern "Python"
# callback behind for every thread of C that calls one: it clears the state of an
# exited thread from another thread, which leaves the exited thread's freelists
# uncleared (https://github.com/python-cffi/cffi/issues/286). The callbacks of a batch
# take arguments, and each batch starts its own workers, so these scenarios grow by a
# few hundred bytes per step there; a callback through ctypes from the same threads
# leaves nothing. Strict: the scenarios pass once cffi frees them, and the mark is then
# removed.
_CFFI_THREAD_LEAK = pytest.mark.xfail(
    bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
    reason="cffi keeps the argument tuples of each C thread that calls back "
    "(python-cffi/cffi#286)",
    strict=True,
)


@pytest.mark.parametrize(
    "step",
    [
        pytest.param(
            step,
            id=name,
            marks=[_CFFI_THREAD_LEAK] if name in WORKER_CALLBACKS else [],
        )
        for name, step in SCENARIOS.items()
    ],
)
def test_no_growth(step: Callable[[], None]) -> None:
    _repeat(step)
    rss_growth = _growth(step, lambda: psutil.Process().memory_info().rss)
    tracemalloc.start()
    try:
        python_growth = _growth(step, _traced)
    finally:
        tracemalloc.stop()

    assert python_growth <= PYTHON_BOUND, f"Python objects grew by {python_growth} B"
    assert rss_growth <= RSS_BOUND, f"resident memory grew by {rss_growth} B"


# Prints how far the peak resident memory of the process rose over a batch of copies
# of one image, two per worker: ru_maxrss (KiB on Linux, bytes on macOS) or, on
# Windows, the peak working set.
_PEAK_SCRIPT = """
import sys
import libphash as ph

def peak():
    if sys.platform == "win32":
        import psutil
        return psutil.Process().memory_info().peak_wset
    import resource
    scale = 1 if sys.platform == "darwin" else 1024
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale

path, threads = sys.argv[1], int(sys.argv[2])
ph.hash(path)
before = peak()
assert all(r.ok for r in ph.hash_files([path] * 2 * threads, threads=threads))
print(peak() - before)
"""


@pytest.mark.parametrize("threads", [1, 3])
def test_batch_peak_is_an_image_per_worker(threads: int) -> None:
    # libphash's batch guide: a worker holds about 4 bytes per pixel and the file. Where
    # the binding reads the files itself (READ_FILES_IN_PYTHON), it also holds the
    # encoded files of the chunk it hands to C, here every file of the batch.
    path = data("photo_large.jpeg")
    size = path.stat().st_size
    pixels = 5472 * 3648
    files = 2 * threads if READ_FILES_IN_PYTHON else threads
    estimate = threads * 4 * pixels + files * size
    out = subprocess.run(  # noqa: S603 -- this Python, with a fixed script
        [sys.executable, "-c", _PEAK_SCRIPT, str(path), str(threads)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    growth = int(out)
    assert growth <= estimate * 1.1 + 16 * 2**20, (growth, estimate)
