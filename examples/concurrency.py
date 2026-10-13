"""Hash many files concurrently: a batch, threads from asyncio, and processes.

* ``hash_files`` runs libphash's own pool of threads; from asyncio it goes to a thread
  (``asyncio.to_thread``) so the event loop stays free.
* Threads of your own each need their own ``ImageContext`` (one per thread, kept in a
  ``threading.local``): one shared context serializes the work on its lock.
* Processes (``ProcessPoolExecutor``) suit a corpus too large for one machine's memory
  budget per process, or work that does more in Python per image than hashing; give each
  a slice of the files. Results and errors pickle.

All three give the same hashes. Run::

    python examples/concurrency.py native/libphash/tests/data/photo.jpeg native/libphash/tests/data/photo_copy.jpeg native/libphash/tests/data/photo.png native/libphash/tests/data/photo_complex.webp

prints::

    batch from asyncio:  4 files
    threads:             4 files
    processes:           4 files
    the same hashes three ways
"""

from __future__ import annotations

import asyncio
import sys
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import libphash as ph

_local = threading.local()


def hash_in_thread(path: str) -> int:
    """Hash one file with this thread's own context."""
    ctx = getattr(_local, "ctx", None)
    if ctx is None:
        ctx = _local.ctx = ph.ImageContext()
    ctx.load_file(path)
    return ctx.phash()


def hash_slice(paths: list[str]) -> dict[str, int]:
    """Hash a slice of the files in a worker process, on a batch of its own."""
    results = ph.hash_files(paths, ph.Algorithm.PHASH, threads=1)
    return {r.source: r.hashes[ph.Algorithm.PHASH] for r in results if r.hashes}


async def with_asyncio(paths: list[str]) -> dict[str, int]:
    results = await asyncio.to_thread(ph.hash_files, paths, ph.Algorithm.PHASH)
    return {r.source: r.hashes[ph.Algorithm.PHASH] for r in results if r.hashes}


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths:
        print(f"usage: {argv[0]} <image>...", file=sys.stderr)
        return 1

    batch = asyncio.run(with_asyncio(paths))
    print(f"batch from asyncio:  {len(batch)} files")

    with ThreadPoolExecutor(max_workers=4) as pool:
        threads = dict(zip(paths, pool.map(hash_in_thread, paths), strict=True))
    print(f"threads:             {len(threads)} files")

    slices = [paths[i::2] for i in range(2)]
    processes: dict[str, int] = {}
    with ProcessPoolExecutor(max_workers=2) as pool:
        for part in pool.map(hash_slice, slices):
            processes.update(part)
    print(f"processes:           {len(processes)} files")

    if not batch == threads == processes:
        print("the hashes differ")
        return 1
    print("the same hashes three ways")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
