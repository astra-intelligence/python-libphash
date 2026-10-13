"""Parallelism: threads, processes, libphash's own pool, asyncio, the batch callbacks.

cffi releases the GIL for every C call, so threads of Python that each hash on a
context of their own run the C work in parallel; what stays serial is the Python
between the calls. The block measures how far that goes against libphash's own pool
(``hash_files``), process pools of each start method, and a context shared by every
thread (whose lock serializes them: a misuse, measured for its price). It records
whether the binding loads in a subinterpreter, how responsive an asyncio loop stays
while images are hashed, and what the batch's progress callback costs.

Run under a free-threaded Python, the same tables show the scaling without the GIL.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import statistics
import subprocess
import sys
import threading
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import TYPE_CHECKING

import libphash as ph

from .fixtures import ROOT
from .report import Block
from .timing import Effort, measure

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .fixtures import Image

#: The process start methods this platform has.
METHODS = [
    m
    for m in ("spawn", "forkserver", "fork")
    if m in multiprocessing.get_all_start_methods()
]

_worker_ctx: ph.ImageContext | None = None
_local = threading.local()


def _init_worker() -> None:
    global _worker_ctx  # noqa: PLW0603 -- one context per worker process
    _worker_ctx = ph.ImageContext()


def _hash_path(path: str) -> int:
    assert _worker_ctx is not None  # noqa: S101 -- set by the initializer
    _worker_ctx.load_file(path)
    return _worker_ctx.phash()


def _hash_bytes(data: bytes) -> int:
    assert _worker_ctx is not None  # noqa: S101 -- set by the initializer
    _worker_ctx.load_bytes(data)
    return _worker_ctx.phash()


def _ready(_: int) -> int:
    return os.getpid()


def _thread_hash(path: str) -> int:
    ctx: ph.ImageContext | None = getattr(_local, "ctx", None)
    if ctx is None:
        ctx = _local.ctx = ph.ImageContext()
    ctx.load_file(path)
    return ctx.phash()


def worker_counts(effort: Effort) -> list[int]:
    """Return the worker counts to measure: powers of two and every CPU."""
    cpus = os.cpu_count() or 1
    if effort.quick:
        return [1, 2]
    return sorted({n for n in (1, 2, 4, 8) if n <= cpus} | {cpus})


def _threads(
    paths: list[str], n: int, shared: ph.ImageContext | None
) -> Callable[[], object]:
    chunks = [paths[i::n] for i in range(n)]

    def worker(chunk: list[str]) -> None:
        ctx = shared if shared is not None else ph.ImageContext()
        for p in chunk:
            ctx.load_file(p)
            ctx.phash()

    def work() -> None:
        threads = [threading.Thread(target=worker, args=(c,)) for c in chunks]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    return work


def _pool(method: str, n: int) -> ProcessPoolExecutor:
    with warnings.catch_warnings():
        # fork() in a process with threads warns from Python 3.12 on; the threads of
        # the pools above have ended, but the platform may still count its own.
        warnings.simplefilter("ignore", DeprecationWarning)
        pool = ProcessPoolExecutor(
            n, mp_context=multiprocessing.get_context(method), initializer=_init_worker
        )
        list(pool.map(_ready, range(n)))
    return pool


def run(images: list[Image], effort: Effort) -> Block:
    """Measure every table of the block."""
    block = Block("parallel", "4. Parallelism")
    long_effort = Effort(
        min_runs=min(effort.min_runs, 3),
        min_seconds=effort.min_seconds,
        quick=effort.quick,
    )
    _scaling(block, images, long_effort)
    _startup(block, long_effort)
    _asyncio(block, images[-1], effort)
    _callbacks(block, images[0], effort)
    block.notes.append(_subinterpreters())
    return block


def _scaling(block: Block, images: list[Image], effort: Effort) -> None:
    counts = worker_counts(effort)
    cpus = os.cpu_count() or 1
    for img in images:
        small = img is images[0]
        n = effort.scale(1000 if small else 2 * cpus, 8)
        paths = [str(img.path)] * n
        table = block.table(
            f"scaling_{img.path.stem}",
            f"Throughput against workers, {img.label}",
            f"Images per second for {n} loads of the file and their pHash, and the "
            "speedup over one worker. A process pool is started before it is timed "
            "(the next table has that cost) and keeps one context per process.",
            "/s",
            baseline_column="1",
        )

        def rate(work: Callable[[], object], items: int = n) -> float:
            return 1.0 / measure(work, items, effort).minimum

        for w in counts:
            col = str(w)
            table.add("threads, a context each", col, rate(_threads(paths, w, None)))
            if small:
                shared = ph.ImageContext()
                table.add(
                    "threads, one shared context", col, rate(_threads(paths, w, shared))
                )

            def executor(workers: int = w) -> None:
                with ThreadPoolExecutor(workers) as ex:
                    list(ex.map(_thread_hash, paths))

            table.add(
                "ThreadPoolExecutor.map, a context per thread", col, rate(executor)
            )
            table.add(
                "hash_files(threads=N)",
                col,
                rate(lambda: ph.hash_files(paths, threads=w)),
            )
            for method in METHODS:
                with _pool(method, w) as pool:
                    chunk = max(1, n // (4 * w))
                    table.add(
                        f"ProcessPoolExecutor ({method}), paths sent",
                        col,
                        rate(
                            lambda: list(pool.map(_hash_path, paths, chunksize=chunk))
                        ),
                    )
                    if small and method == METHODS[0]:
                        blobs = [img.data] * n
                        table.add(
                            f"ProcessPoolExecutor ({method}), bytes sent",
                            col,
                            rate(
                                lambda: list(
                                    pool.map(_hash_bytes, blobs, chunksize=chunk)
                                )
                            ),
                        )


def _startup(block: Block, effort: Effort) -> None:
    cpus = os.cpu_count() or 1
    workers = effort.scale(cpus, 2)
    table = block.table(
        "pool_startup",
        "Starting a process pool",
        f"A ProcessPoolExecutor of {workers} processes, each importing libphash and "
        "creating its context, until every one has answered; then shut down.",
        "s",
    )

    def start(method: str) -> None:
        with _pool(method, workers):
            pass

    for method in METHODS:
        table.add(method, "start and stop", measure(lambda: start(method), 1, effort))


async def _ticks(job: Callable[[], Awaitable[object]]) -> list[float]:
    """Run ``job`` beside a task that sleeps 1 ms again and again; return its lags."""
    lags: list[float] = []
    done = False

    async def ticker() -> None:
        while not done:
            t0 = time.perf_counter()
            await asyncio.sleep(0.001)
            lags.append(time.perf_counter() - t0 - 0.001)

    task = asyncio.create_task(ticker())
    await asyncio.sleep(0.02)
    lags.clear()
    await job()
    done = True
    await task
    return lags


def _asyncio(block: Block, img: Image, effort: Effort) -> None:
    k = effort.scale(8, 2)
    path = str(img.path)
    table = block.table(
        "asyncio",
        f"An asyncio loop while hashing, {img.label}",
        f"How late a task that sleeps 1 ms again and again wakes up while {k} images "
        "are hashed: the loop's lag. With the GIL released in C, work handed to a "
        "thread leaves the loop responsive.",
        "ms",
    )
    elapsed = 0.0

    async def blocking() -> None:
        nonlocal elapsed
        t0 = time.perf_counter()
        for _ in range(k):
            ph.hash(path)
        elapsed = time.perf_counter() - t0

    async def idle() -> None:
        await asyncio.sleep(elapsed)

    async def to_thread() -> None:
        for _ in range(k):
            await asyncio.to_thread(ph.hash, path)

    async def gathered() -> None:
        await asyncio.gather(*(asyncio.to_thread(ph.hash, path) for _ in range(k)))

    async def batch() -> None:
        await asyncio.to_thread(ph.hash_files, [path] * k)

    jobs: list[tuple[str, Callable[[], Awaitable[object]]]] = [
        ("hash() in the coroutine: blocks the loop", blocking),
        ("idle, as long", idle),
        ("await asyncio.to_thread(hash), one by one", to_thread),
        ("asyncio.gather of to_thread(hash)", gathered),
        ("await asyncio.to_thread(hash_files)", batch),
    ]
    for label, job in jobs:
        lags = sorted(asyncio.run(_ticks(job))) or [0.0]
        table.add(label, "median", 1e3 * statistics.median(lags))
        table.add(label, "p99", 1e3 * lags[min(len(lags) - 1, int(0.99 * len(lags)))])
        table.add(label, "max", 1e3 * lags[-1])


def _callbacks(block: Block, img: Image, effort: Effort) -> None:
    cpus = os.cpu_count() or 1
    n = effort.scale(1000, 8)
    paths = [str(img.path)] * n
    table = block.table(
        "callbacks",
        f"The batch's progress callback, {img.label}",
        f"hash_files() of {n} copies of the file, per image: without a callback and "
        "with a progress callback that does nothing. The callback takes the GIL on a "
        "worker thread of C for every image.",
        "s",
        baseline_row="no callback",
    )

    def nothing(_done: int, _total: int) -> None:
        return None

    for threads in sorted({1, cpus}):
        col = f"threads={threads}"
        table.add(
            "no callback",
            col,
            measure(lambda: ph.hash_files(paths, threads=threads), n, effort),
        )
        table.add(
            "progress callback",
            col,
            measure(
                lambda: ph.hash_files(paths, threads=threads, progress=nothing),
                n,
                effort,
            ),
        )


_SUBINTERPRETER = """
from concurrent import interpreters
interp = interpreters.create()
try:
    interp.exec("import libphash")
    print("libphash imports in a subinterpreter")
except interpreters.ExecutionFailed as e:
    print(f"{e.excinfo.type.__name__}: {e.excinfo.msg}")
finally:
    interp.close()
"""


def _subinterpreters() -> str:
    """Return whether the binding imports in a subinterpreter (Python 3.14+)."""
    if sys.version_info < (3, 14):
        return (
            "Subinterpreters (concurrent.interpreters) need Python 3.14; this run "
            f"is on {sys.version_info.major}.{sys.version_info.minor}."
        )
    run = subprocess.run(
        [sys.executable, "-c", _SUBINTERPRETER],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    answer = (run.stdout.strip() or run.stderr.strip()).splitlines()[-1]
    return (
        "Subinterpreters: `import libphash` in an interpreter of "
        f"`concurrent.interpreters.create()` gives `{answer}`."
    )
