# Quick start

```bash
pip install python-libphash
```

The wheel carries the C library and its decoders: nothing else is installed or needed.

## Hash an image and compare

```python
import libphash as ph

a = ph.hash("photo.jpg")                   # pHash, a 64-bit int
b = ph.hash("photo_copy.jpg")
ph.hamming_distance(a, b)                  # 0..64 bits differ
ph.similarity(a, b)                        # 1.0 for equal hashes, ~0.5 unrelated
print(ph.hash_to_hex(a))                   # 16 hex digits, for storage
```

A distance of a few bits means the same picture; how many is "a few" depends on the
algorithm and on the edits your copies go through:
[Comparing hashes](https://gudoshnikovn.github.io/libphash/theory/comparing/) on libphash's
site explains how to choose the threshold, and `examples/threshold.py` measures it on
pairs you label.

## Choose an algorithm

`ph.hash()` computes pHash unless told otherwise. Each algorithm is a member of
`Algorithm`, and its libphash name works too:

```python
from libphash import Algorithm

d = ph.hash("photo.jpg", Algorithm.DHASH)  # an int
r = ph.hash("photo.jpg", "radial")         # a Digest
r.similarity(ph.hash("photo_rotated.jpg", "radial"))
```

| Algorithm | Result | Compare with |
|---|---|---|
| `AHASH`, `DHASH`, `PHASH`, `WHASH` | 64-bit `int` | `hamming_distance()`, `similarity()` |
| `BMH`, `MHASH` | `Digest` of bits | `Digest.hamming_distance()`, `Digest.similarity()` |
| `RADIAL` | `Digest` of coefficients | `Digest.similarity()` (peak correlation) |
| `COLOR_HASH` | `Digest`, a histogram | `Digest.similarity()` (histogram intersection) |
| `COLOR_MOMENTS` | `Digest`, 16-bit features | `Digest.l2_distance()` |

A digest refuses a comparison that does not fit its kind with `DigestKindError`, rather
than return a number that means nothing. Which algorithm suits which use is measured on
libphash's [Choosing an algorithm](https://gudoshnikovn.github.io/libphash/theory/choosing/).

## Several hashes of one image, many images

```python
with ph.ImageContext() as ctx:
    ctx.load_file("photo.jpg")
    hashes = ctx.hashes(Algorithm.PHASH, Algorithm.DHASH, Algorithm.MHASH)
    print(ctx.width, ctx.height, hashes[Algorithm.PHASH])

results = ph.hash_files(["photo.jpg", "photo_copy.jpg", "missing.jpg"])
for r in results:
    print(r.source, r.hashes if r.ok else r.error)
```

A context decodes the image once for all its hashes, and keeps its buffers from one image
to the next; `hash_files()` hashes a list of files on all CPUs, and a file that fails
does not stop the others. [Hashing many images](batch.md) has the details.

## Next

- [Loading images](loading.md): bytes, file objects, numpy, Pillow and OpenCV.
- [Configuring](configuring.md): the settings, and which ones change the hash.
- [Storing and searching](storing.md): hashes in a database, nearest neighbors.
