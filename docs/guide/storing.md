# Storing and searching

A hash is computed once and compared many times. This page says what to store with it,
how to store each kind, and how to search a large collection from Python.
libphash's [Storing and searching hashes](https://gudoshnikovn.github.io/libphash/guide/storing/)
measures the cost of a search and when an index pays off.

## What a hash does not record

Two hashes are comparable only when both were computed with:

- **the same algorithm**: store its name, `str(Algorithm.PHASH)` is `"phash"`, and
  `Algorithm` accepts it back;
- **the same settings**: the `Config`, or the fields that differ from the default;
- **the same libphash version**, `ph.libphash_version()` (the first three numbers of
  the package version): a release that changes an algorithm's values says so in its
  changelog;
- **the same JPEG decoder**: `ph.can_decode("jpeg")` is true for libjpeg-turbo, which
  every wheel has; a build decoding JPEG with stb_image hashes JPEGs a few bits away.

## 64-bit hashes

A 64-bit hash is an `int` from 0 to 2**64 − 1. As text it is 16 hex digits, which sort
like the numbers:

```python
import libphash as ph

h = ph.hash("photo.jpg")
text = ph.hash_to_hex(h)               # '7eb66192bc394247'
assert ph.hash_from_hex(text) == h
```

Databases store 64-bit integers signed (SQLite's `INTEGER`, PostgreSQL's `BIGINT`): a
hash at or above 2**63 does not fit as it is. Store the signed integer with the same 64
bits, and turn it back when reading:

```python
def to_int64(value: int) -> int:
    return value - (1 << 64) if value >= 1 << 63 else value

def from_int64(value: int) -> int:
    return value + (1 << 64) if value < 0 else value

assert from_int64(to_int64(2**64 - 1)) == 2**64 - 1
```

The Hamming distance of the stored forms is the distance of the hashes, since the bits
are the same.

## Digests

A `Digest`'s text form keeps its kind: `"bits:…"`, `"coefficients:…"`,
`"histogram:…"`, `"vector16:…"`. Read back with `Digest.from_hex()`, a digest still
refuses the comparisons that do not fit it. The form is libphash's own, so C and Python
read each other's.

```python
d = ph.hash("photo.jpg", "mhash")
stored = d.hex()                        # 'bits:…', 72 bytes as 144 hex digits
assert ph.Digest.from_hex(stored) == d
```

For a binary column, store `bytes(d)` and the kind (`int(d.kind)`), and rebuild it as
`ph.Digest(data, kind)`. Digests are hashable and compare equal by value, so they serve
as dictionary keys and in sets.

## Searching

Comparing one hash with every stored one is a loop in Python, or one vector operation
with numpy, which is far faster for a large collection:

```python
import numpy as np

hashes = np.array([ph.hash(p) for p in ["photo.jpg", "photo_copy.jpg", "photo.png"]],
                  dtype=np.uint64)
query = np.uint64(ph.hash("photo.jpg"))
distances = np.bitwise_count(hashes ^ query)        # numpy 2.0 or later
nearest = np.argsort(distances, kind="stable")[:2]
```

`examples/store_sqlite.py` keeps the hashes in SQLite with a Hamming-distance function
in SQL, `examples/nearest_numpy.py` searches with numpy, and `examples/bk_tree.py`
indexes them in a BK-tree, which visits a part of the collection per query.
