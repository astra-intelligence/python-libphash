# Threads and processes

## What runs in parallel

Every call into C releases the GIL, so hashing in several threads runs on several CPUs
even on a Python with the GIL. The rules:

- **An `ImageContext` is safe to share** between threads: its calls are serialized on a
  lock of the context, so threads sharing one take turns. Threads that should work in
  parallel each use their own context.
- **`Config`, `Digest`, `BatchResult` and the exceptions are immutable** and safe
  anywhere.
- **A batch** (`hash_files()`) runs its own threads in C; several batches may run at once
  from different threads.

```python
import threading
from concurrent.futures import ThreadPoolExecutor

import libphash as ph

local = threading.local()

def phash(path: str) -> int:
    if not hasattr(local, "ctx"):
        local.ctx = ph.ImageContext()          # one context per thread
    local.ctx.load_file(path)
    return local.ctx.phash()

with ThreadPoolExecutor(max_workers=4) as pool:
    hashes = list(pool.map(phash, ["photo.jpg", "photo_copy.jpg"]))
```

For a list of files `hash_files()` does the same with less Python in the loop; threads of
your own suit work that does more per image, such as the digest algorithms, which a batch
does not compute.

## Free-threaded Python

The wheels for the free-threaded builds (3.14t and later) declare the module safe to run
without the GIL, and the rules above stay the same: the context's lock serializes a shared
context, and own contexts run in parallel, the Python code around them included.

## Processes

`Config`, `Digest`, `BatchResult` and every `PhashError` pickle, so they cross to and
from worker processes. A context does not: it holds C memory, and each process creates
its own. Under `fork`, a context created before the fork works in the child.

```python
from concurrent.futures import ProcessPoolExecutor

def hash_slice(paths: list[str]) -> list[int]:
    results = ph.hash_files(paths, threads=1)   # one worker thread per process
    return [r.hashes[ph.Algorithm.PHASH] for r in results if r.hashes]
```

A process pool pays off when the work per image is mostly Python; for hashing alone, one
batch with all the CPUs has less overhead.

## asyncio

A hash blocks the thread that runs it. From a coroutine, run it in a thread, and the
event loop stays free while C works (the GIL is released):

```python
import asyncio

async def main() -> None:
    results = await asyncio.to_thread(ph.hash_files, ["photo.jpg", "photo_copy.jpg"])
    print(len(results))

asyncio.run(main())
```

A batch run this way is not stopped by Ctrl+C: it runs to its end on its thread, while
the event loop handles the signal. A `progress` callback that returns `False` when the
program shuts down stops it early.

`examples/concurrency.py` runs all three and checks that they give the same hashes.
