# Migration guide: 1.x → 2.0

python-libphash 2.0.1.0 bundles libphash 2.0.1; the last 1.x release, 1.4.1, bundles
libphash 1.10.4. Two things change at once, and they need different handling:

- **Hash values.** libphash 2.0 rewrote several algorithms and changed how images are
  prepared. A hash stored by 1.x is in general not comparable with one computed by 2.x,
  and nothing raises an error or a warning when they are compared.
- **The Python API.** The 1.x classes and functions are replaced; code written for 1.x
  fails at import or at the first call. The table at the end of this guide maps every
  1.x name to its replacement.

The C library's own guide, [`MIGRATION.md` of libphash](https://github.com/gudoshnikovn/libphash/blob/v2.0.1/MIGRATION.md),
explains each change to the hashes in full; this guide says what it means from Python.

# Hash values

## Recompute every stored hash

Treat a database of 1.x hashes as incompatible with 2.x. Recompute it from the images
with 2.x before comparing anything new against it; do not mix the two in one
comparison. Store the version with the hashes (`libphash.libphash_version()`), so that
the next change that alters values is visible in your data.

The algorithms whose values change, and why:

| Algorithm | What changes | 1.x behavior restorable? |
|---|---|---|
| aHash | exact area average for the 8×8 reduction; a pixel equal to the mean sets its bit | no |
| pHash | threshold at the median plus 0.1 % of the coefficients' range | no |
| BMH | threshold at the median of the block means, not their mean | no |
| mHash | Marr–Hildreth hash, a 72-byte `Digest` (1.x: a 64-bit `int`) | no |
| ColorHash | a 108-byte color histogram `Digest` (1.x: a 42-bit `int`) | no |
| ColorMoments | 18 bytes of signed 16-bit features; the skewness keeps its sign | no |
| Radial | reimplemented after its source; `gamma` is the exponent itself, not its inverse | no |
| every algorithm, JPEG | libjpeg-turbo's accurate IDCT: a few bits move on most JPEGs | no |
| every algorithm, rotated photos | EXIF orientation applied before hashing | `Config(auto_orient=False)` |
| every algorithm, transparent images | alpha composited onto mid-gray | `Config(alpha_mode="ignore")` |
| every algorithm, WebP loaded as grayscale | folded to gray by the decoder | no |

dHash and wHash keep their definitions; their values still change on JPEGs (the IDCT),
on photos with an EXIF orientation and on images with transparency.

## EXIF orientation is applied by default

Most photographs from phones and cameras store their pixels sideways and an
`Orientation` tag that tells a viewer how to turn them. 2.x hashes the image as it is
displayed: such a photo hashes differently from 1.x, and the same as a copy saved
upright by an editor. This is the change most likely to affect a deduplication database,
because nothing reports it: comparisons with stored 1.x hashes just stop matching.
`Config(auto_orient=False)` hashes the stored pixels, as 1.x did.

## Transparent images are hashed as they look

1.x dropped the alpha channel and hashed the color stored under it, which is invisible
and differs from one encoder to another. 2.x composites the image onto mid-gray when it
loads it (`Config(alpha_mode="white")` or `"black"` chooses another background);
`Config(alpha_mode="ignore")` drops alpha as 1.x did.

## Radial: `gamma` means the opposite

1.x raised pixels to `1 / gamma`, with a default of 2.2; 2.x raises them to `gamma`, with
a default of 1.0. Code that set the gamma explicitly must review the value:
`ctx.set_gamma(2.2)` in 1.x corresponds to `Config(gamma=1 / 2.2)`, though the Radial
hash itself is rewritten and its values change regardless. `gamma` affects only Radial.

# The Python API

## Hashing

1.x read hashes as properties of an `ImageContext` loaded in its constructor. 2.x has a
function for one image and a context for several hashes or many images:

```python
# 1.x
with ImageContext("photo.jpg") as ctx:
    h = ctx.phash
h = get_hash("photo.jpg", HashMethod.PHASH)

# 2.x
import libphash as ph
from libphash import Algorithm

h = ph.hash("photo.jpg")                        # pHash by default
h = ph.hash("photo.jpg", Algorithm.DHASH)
with ph.ImageContext() as ctx:
    ctx.load_file("photo.jpg")
    hashes = ctx.hashes(Algorithm.PHASH, Algorithm.DHASH)
```

The context's hash properties are methods, named after the algorithm (`ctx.ahash()`,
`ctx.dhash()`, `ctx.phash()`, `ctx.whash()`, `ctx.bmh()`, `ctx.mhash()`,
`ctx.color_hash()`); `color_moments_hash` is `ctx.color_moments()` and `radial_hash` is
`ctx.radial()`. A context is created empty and loaded with `load()` or one of the
`load_*` methods, and it can load one image after another.

## mHash and ColorHash return a `Digest`

In 1.x `mhash` and `color_hash` were 64-bit integers. In 2.x they are a `Digest` of 72
and 108 bytes. Compare mHash digests with `hamming_distance()` or `similarity()`, and
ColorHash digests with `histogram_intersection()` or `similarity()`; the 1.x module
function `hamming_distance(a, b)` takes only 64-bit integers.

## Settings are a `Config`

The `set_*` methods of the 1.x context are fields of an immutable `Config`, checked when
it is created. One `Config` configures `hash()`, an `ImageContext` and a batch:

```python
# 1.x
with ImageContext("photo.jpg") as ctx:
    ctx.set_phash_params(dct_size=32, reduction_size=8)
    ctx.set_whash_mode("full")
    h = ctx.phash

# 2.x
cfg = ph.Config(phash_dct_size=32, phash_reduction_size=8, whash_mode="full")
h = ph.hash("photo.jpg", config=cfg)
```

1.x ignored an out-of-range value, or replaced it with a default, and hashed with a
configuration nobody asked for. 2.x raises `InvalidArgumentError` (a `ValueError`) when
the `Config` is created, naming the field.

## Digests carry a kind

A 1.x `Digest(data, size)` was bytes and a length. A 2.x `Digest(data, kind)` carries
its `DigestKind` (bits, coefficients, histogram, …), and each comparison accepts only
the kinds it is meaningful for: comparing two Radial digests by Hamming distance raises
`DigestKindError` (a `TypeError`) instead of returning a number that means nothing.
`len(digest)` is the size. `digest.hex()` and `Digest.from_hex()` give a text form
(`"bits:3fa0…"`) that keeps the kind, and digests are hashable, comparable for equality
and picklable.

## Errors

1.x raised `DecodeError` for every failed load, a missing file included. 2.x raises the
specific cause, and each class derives from the built-in exception that fits it:

| Failure | 1.x | 2.x |
|---|---|---|
| missing file, directory, no permission | `DecodeError` | `ImageIOError`, an `OSError` with `errno` (`FileNotFoundError` catches a missing file) |
| not an image | `DecodeError` | `UnsupportedFormatError` (a `DecodeError`) |
| truncated or malformed image | `DecodeError`, or loaded without an error | `CorruptDataError` (a `DecodeError`) |
| image above the size limit | loaded (no limit) | `ImageTooLargeError` (a `DecodeError`) |
| format without a decoder in the build | `DecodeError` | `DecoderUnavailableError` (a `DecodeError`) |
| out-of-range argument | ignored, or `InvalidArgumentError` | `InvalidArgumentError` (a `ValueError`) |
| hash of a context without an image | `InvalidArgumentError` | `EmptyImageError` |
| color hash of a grayscale image | a meaningless result | `RequiresColorError` |
| memory | `AllocationError` | `AllocationError` (a `MemoryError`) |

`except DecodeError` no longer catches a missing file: catch `OSError` (or
`ImageIOError`) for that, or `PhashError` for every failure of the library.

## Size limits

2.x refuses an image larger than `Config.max_pixels` (256 Mi pixels by default) or wider
or taller than 1,000,000 pixels before decoding it, with `ImageTooLargeError`. 1.x
decoded any size. Raise `max_pixels`, or set it to 0, to accept larger images; the
per-side limit is fixed.

## Python and platforms

2.x requires Python 3.10 or later; 1.4.1 accepted 3.8. Wheels exist for Linux x86-64 and
arm64 (glibc), macOS arm64 and Windows x86-64; x86-64 wheels need a CPU with SSE4.2 and
POPCNT (x86-64-v2). 1.4.1 had wheels for 32-bit x86 Linux and for musl Linux, which 2.x
does not: there pip builds the sdist, which needs a C compiler.

## 1.x names and their replacements

| 1.4.1 | 2.0.1.0 |
|---|---|
| `ImageContext(path=p)` | `ImageContext()` then `ctx.load_file(p)`, or `ph.hash(p, …)` |
| `ImageContext(bytes_data=b)` | `ctx.load_bytes(b)`, or `ph.hash(b, …)` |
| `ImageContext(load_grayscale=True)` | `ImageContext(Config(grayscale=True))` |
| `ctx.load_from_file(p)` / `ctx.load_from_memory(b)` | `ctx.load_file(p)` / `ctx.load_bytes(b)` |
| `ctx.set_gamma(g)` | `Config(gamma=g)` (inverse meaning, see above) |
| `ctx.set_gray_weights(r, g, b)` | `Config(gray_weights=(r, g, b))` |
| `ctx.set_phash_params(dct_size, reduction_size)` | `Config(phash_dct_size=…, phash_reduction_size=…)` |
| `ctx.set_radial_params(projections, samples)` | `Config(radial_projections=…, radial_samples=…)` |
| `ctx.set_block_params(block_size)` | `Config(bmh_block_size=…)` |
| `ctx.set_whash_mode("fast" \| "full")` | `Config(whash_mode="fast" \| "full")` |
| `ctx.set_load_grayscale(True)` | `Config(grayscale=True)` |
| `ctx.ahash`, `dhash`, `phash`, `whash` | `ctx.ahash()`, `dhash()`, `phash()`, `whash()` |
| `ctx.mhash`, `ctx.color_hash` (`int`) | `ctx.mhash()`, `ctx.color_hash()`, a `Digest` |
| `ctx.bmh` | `ctx.bmh()` |
| `ctx.color_moments_hash` | `ctx.color_moments()` |
| `ctx.radial_hash` | `ctx.radial()` |
| `HashMethod.PHASH` (and the others) | `Algorithm.PHASH`, or the name `"phash"` |
| `HashMethod.COLORHASH` | `Algorithm.COLOR_HASH`, or `"color_hash"` |
| `get_hash(path, method)` | `ph.hash(path, algorithm)` |
| `compare_images(a, b, method)` | `ph.hamming_distance(ph.hash(a, algo), ph.hash(b, algo))` |
| `hamming_distance(h1, h2)` | unchanged |
| `Digest(data, size)` | `Digest(data, kind)`; the size is `len(digest)` |
| `digest.size` | `len(digest)` |
| `digest.distance_hamming(other)` | `digest.hamming_distance(other)` |
| `digest.distance_l2(other)` | `digest.l2_distance(other)` (ColorMoments) |
| `ph_can_use_libjpeg()` / `ph_can_use_libpng()` | `ph.can_decode("jpeg")` / `ph.can_decode("png")` |
| `DecodeError` | `DecodeError` and its subclasses, `ImageIOError` for files |
| `AllocationError`, `InvalidArgumentError`, `PhashError` | unchanged |
