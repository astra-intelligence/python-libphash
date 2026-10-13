# Hashing many images

`hash_files()` hashes a list of files on libphash's own pool of threads, and
`hash_buffers()` a list of encoded images in memory:

```python
import libphash as ph
from libphash import Algorithm

paths = ["photo.jpg", "photo_copy.jpg", "broken.jpg"]
results = ph.hash_files(paths, [Algorithm.PHASH, Algorithm.DHASH], threads=0)
for r in results:
    if r.ok:
        print(r.source, ph.hash_to_hex(r.hashes[Algorithm.PHASH]))
    else:
        print(r.source, type(r.error).__name__)
```

- **One result per item, in order.** A `BatchResult` holds the `source` (the path, or
  the index of the buffer), the `hashes` by algorithm, and the `error`; `ok` says which
  of the two is set. A file that fails does not stop the batch.
- **The 64-bit algorithms** (aHash, dHash, pHash, wHash) are what a batch computes;
  several of them come from one pass over each image. For a digest algorithm, loop over
  the files with one `ImageContext` per thread ([Threads and processes](concurrency.md)).
- **`threads`**: `0` is one worker per CPU the process may use, `1` runs on the calling
  thread, `N` that many workers. Each worker holds one decoded image at a time: peak
  memory is about 4 bytes per pixel of the largest image, plus the file, per worker.
  Bound it with `threads` or `Config.max_pixels`.
- **`config`** applies one `Config` to every item.

## Progress and stopping

```python
def progress(done: int, total: int) -> bool | None:
    print(f"{done}/{total}")
    return None          # False stops the batch

results = ph.hash_files(paths, progress=progress)
```

The callback runs after each item, on whichever thread finished it, one call at a time.
Returning `False` stops the batch: the items not yet started get a `BatchCancelledError`.
An exception raised in the callback stops the batch the same way and is raised again
from `hash_files()` when it returns. Ctrl+C stops a batch running on the main thread
and raises `KeyboardInterrupt` once the items in progress finish; a batch on another
thread, or under an event loop that handles the signal itself, runs to its end.

## From memory

```python
from pathlib import Path

blobs = [Path(p).read_bytes() for p in ["photo.jpg", "photo_copy.jpg"]]
for r in ph.hash_buffers(blobs):
    print(r.source, r.hashes)              # source is the index: 0, 1
```

The buffers are read in place, without a copy, and must not change while the batch
runs.

## Finding the duplicates

Hashing is the expensive part; comparing every pair of 64-bit hashes is cheap for a few
thousand images:

```python
from itertools import combinations

hashed = [(r.source, r.hashes[Algorithm.PHASH]) for r in results if r.ok]
for (a, ha), (b, hb) in combinations(hashed, 2):
    if ph.hamming_distance(ha, hb) <= 6:
        print(a, b)
```

For many more, [Storing and searching](storing.md) compares one hash with a million in a
few milliseconds with numpy, and `examples/bk_tree.py` groups them with an index.
