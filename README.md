# python-libphash

Python binding for [libphash](https://github.com/gudoshnikovn/libphash), a C library for perceptual image hashing.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A perceptual hash changes little when an image is resized, recompressed or slightly
edited, unlike a cryptographic hash, which changes completely. Comparing perceptual hashes
finds duplicate and near-duplicate images. libphash computes nine of them in C, with
SIMD-accelerated JPEG, PNG and WebP decoders built in; the wheel carries the whole library.

| Algorithm | Result | Compare with |
|---|---|---|
| `Algorithm.AHASH` — average hash | 64-bit `int` | `hamming_distance`, `similarity` |
| `Algorithm.DHASH` — difference hash | 64-bit `int` | `hamming_distance`, `similarity` |
| `Algorithm.PHASH` — perceptual (DCT) hash | 64-bit `int` | `hamming_distance`, `similarity` |
| `Algorithm.WHASH` — wavelet hash | 64-bit `int` | `hamming_distance`, `similarity` |
| `Algorithm.BMH` — block mean hash | `Digest`, bits | `hamming_distance`, `similarity` |
| `Algorithm.MHASH` — Marr-Hildreth hash | `Digest`, bits | `hamming_distance`, `similarity` |
| `Algorithm.RADIAL` — radial variance hash | `Digest`, coefficients | `radial_similarity` (= `similarity`) |
| `Algorithm.COLOR_HASH` — color histogram | `Digest`, histogram | `histogram_intersection` (= `similarity`) |
| `Algorithm.COLOR_MOMENTS` — color moments | `Digest`, 16-bit vector | `l2_distance` |

`Algorithm` is exported from `libphash`. Wherever an algorithm is expected, its libphash
name is accepted too (`"radial"` for `Algorithm.RADIAL`), and `str(Algorithm.RADIAL)` is
that name.

## Installation

```bash
pip install python-libphash
```

Wheels need nothing else. Building from source (`pip install .` in a clone with
`git submodule update --init --recursive`) needs a C compiler; CMake comes from PyPI.

## Versioning

The version has four numbers, `X.Y.Z.N`:

*   `X.Y.Z` is the version of the bundled libphash: `python-libphash 2.0.1.0` carries libphash 2.0.1.
*   `N` is the revision of the binding on top of it. The first release for a libphash version is `.0`, and the zero is always written out; fixes and additions to the Python side alone are `2.0.1.1`, `2.0.1.2`, …

Hash values depend on the libphash version and on the context settings, so hashes stored for later comparison are comparable only when both were computed with the same `X.Y.Z` and the same settings. To pin the C library while still receiving binding fixes, pin the first three numbers:

```bash
pip install "python-libphash==2.0.1.*"
```

The 1.x releases were numbered independently of libphash (1.4.1 bundles libphash 1.10.4).

## Usage

```python
import libphash as ph
from libphash import Algorithm

h1 = ph.hash("photo.jpg")                     # pHash, an int
h2 = ph.hash("photo_small.jpg")
ph.hamming_distance(h1, h2)                   # 0..64 differing bits
ph.similarity(h1, h2)                         # 1.0 identical, ~0.5 unrelated

d1 = ph.hash("photo.jpg", Algorithm.RADIAL)   # a Digest
d2 = ph.hash("photo_recompressed.jpg", Algorithm.RADIAL)
d1.similarity(d2) >= ph.RADIAL_PCC_THRESHOLD
```

`ph.hash()` takes a path, the encoded bytes of an image, a binary file object
(`open(...)`, `io.BytesIO`), an 8-bit array of pixels (numpy, shape `(h, w)` or
`(h, w, 1|3|4)`) or a Pillow image.

### Several hashes, many images

An `ImageContext` holds one image at a time and reuses its buffers from one image to the
next, so it is the faster way to hash in a loop:

```python
with ph.ImageContext() as ctx:
    for path in paths:
        ctx.load_file(path)
        # {Algorithm: int | Digest}
        hashes = ctx.hashes(Algorithm.PHASH, Algorithm.DHASH, Algorithm.MHASH)
        print(ctx.width, ctx.height, hashes)
```

`load_bytes()`, `load_fileobj()`, `load_pixels(array, channel_order="bgr")` (OpenCV) and
`load_pil()` load from the other sources. A context may be shared between threads (its
calls are serialized); threads that should work in parallel each use their own.

For many files, a batch runs on libphash's own thread pool:

```python
results = ph.hash_files(paths, [Algorithm.PHASH, Algorithm.DHASH], threads=0,
                        progress=lambda done, total: print(done, "/", total))
for r in results:
    if r.ok:
        print(r.source, r.hashes[Algorithm.PHASH])
    else:
        print(r.source, r.error)
```

Batches compute the 64-bit algorithms. `hash_buffers()` does the same for images in memory.

### Configuration

```python
cfg = ph.Config(max_pixels=50_000_000, auto_orient=True, radial_sigma=2.5)
ph.hash("photo.jpg", Algorithm.RADIAL, config=cfg)
ph.ImageContext(cfg)
ph.hash_files(paths, config=cfg)
```

`Config` is immutable and checked when created: an out-of-range value raises
`InvalidArgumentError` naming the field. Hashes are comparable only when computed with
equal configurations.

### Digests

A `Digest` carries its bytes and its kind, which decides how it may be compared: the
wrong metric raises `DigestKindError` instead of returning a meaningless number.
`digest.hex()` / `Digest.from_hex()` give a text form that keeps the kind, for storage;
digests are hashable, comparable for equality and picklable. 64-bit hashes have
`ph.hash_to_hex()` / `ph.hash_from_hex()`.

### Errors

Every error derives from `ph.PhashError` and from the matching built-in exception:

```python
try:
    ph.hash(path)
except FileNotFoundError:        # ImageIOError: missing file, directory, no permission
    ...
except ph.DecodeError:           # UnsupportedFormatError, CorruptDataError,
    ...                          # DecoderUnavailableError, ImageTooLargeError
```

`InvalidArgumentError` is a `ValueError`, `AllocationError` a `MemoryError`,
`DigestKindError` a `TypeError`. `err.code_name` holds the C error code and `err.detail`
the C library's own message for a failed load.

### Build information

```python
ph.libphash_version()   # "2.0.1"
ph.build_info()         # "version=2.0.1 jpeg=libjpeg-turbo png=libpng webp=libwebp ..."
ph.can_decode("webp")   # True
```

## License

MIT, see `LICENSE`. The wheels include libphash and the libraries it bundles
(libjpeg-turbo, libpng, libwebp, zlib-ng, stb_image), each under its own license.
