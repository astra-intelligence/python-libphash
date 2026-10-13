# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The
version is `X.Y.Z.N`: `X.Y.Z` is the bundled libphash, `N` the revision of the binding
(`CONTRIBUTING.md`, "Versions"). What changes in libphash itself is in
[its changelog](https://github.com/gudoshnikovn/libphash/blob/main/CHANGELOG.md); this
one says what a Python user observes.

## [Unreleased]

Nothing yet.

## [2.0.1.0] - Unreleased

The first release on libphash 2 (2.0.1; 1.4.1 bundles libphash 1.10.4), with a new
Python API. **Hash values change**, and code written for 1.x does not run unchanged:
read [`MIGRATION.md`](https://github.com/gudoshnikovn/python-libphash/blob/main/MIGRATION.md) before upgrading.

### BREAKING CHANGES

- **Stored hashes must be recomputed.** libphash 2.0 changes the values of every
  algorithm on some inputs: aHash, pHash and BMH threshold differently, mHash, ColorHash,
  ColorMoments and Radial are rewritten, JPEG is decoded with the accurate IDCT, photos
  are turned upright by their EXIF orientation, and transparent images are composited
  onto gray. Nothing reports the difference: a 1.x hash compared with a 2.x one simply
  stops matching. `MIGRATION.md` lists each change and the two that `Config` can undo
  (`auto_orient=False`, `alpha_mode="ignore"`).
- **A new API replaces the 1.x one.** `hash()` hashes one image from any source; an
  `ImageContext` is created empty, loads image after image with `load_*()` methods and
  computes hashes with `hash()`, `hashes()` or a method per algorithm; every setting is a field of
  an immutable `Config`. `HashMethod`, `get_hash()`, `compare_images()`,
  `ph_can_use_libjpeg()`, `ph_can_use_libpng()`, the `set_*()` methods and the
  constructor arguments `path`, `bytes_data` and `load_grayscale` are gone;
  `MIGRATION.md` maps each to its replacement.
- **mHash and ColorHash return a `Digest`** (72 and 108 bytes), not an `int`. The
  context's hash properties are methods (`ctx.phash()`), and `color_moments_hash` and
  `radial_hash` are `color_moments()` and `radial()`.
- **`Digest` carries its kind.** It is created as `Digest(data, kind)` instead of
  `Digest(data, size)`; `len(digest)` replaces `size`. Its comparisons are
  `hamming_distance()`, `l2_distance()`, `histogram_intersection()`,
  `radial_similarity()` and `similarity()`, and each refuses a digest of a kind it does
  not apply to with `DigestKindError`. `distance_hamming()` and `distance_l2()` are gone.
- **Failures raise specific exceptions.** A missing or unreadable file raises
  `ImageIOError`, an `OSError` with `errno` (`FileNotFoundError` catches a missing file),
  where 1.x raised `DecodeError`; `except DecodeError` no longer catches it. A failed
  decode raises one of the four subclasses of `DecodeError`: `UnsupportedFormatError`,
  `CorruptDataError`, `DecoderUnavailableError`, `ImageTooLargeError`.
  `InvalidArgumentError` is a `ValueError`, `AllocationError` a `MemoryError`. A hash
  of an empty context raises `EmptyImageError`, a color hash of a grayscale image
  `RequiresColorError`.
- **Settings are checked.** A `Config` with a value outside the range libphash accepts
  raises `InvalidArgumentError` naming the field, where a 1.x setter ignored the value or
  replaced it with a default.
- **Images over 256 Mi pixels, or over 1,000,000 pixels on a side, are refused** with
  `ImageTooLargeError` before they are decoded. `Config(max_pixels=…)` moves the first
  limit; the second is fixed.
- **Radial's `gamma` is the exponent itself**, default 1.0; 1.x raised pixels to
  `1 / gamma`, default 2.2.
- **Python 3.10 or later** is required (1.4.1: 3.8, with wheels from 3.9).
- **x86-64 wheels need a CPU with SSE4.2 and POPCNT** (x86-64-v2), the baseline
  libphash is built and tested for; the 1.4.1 wheels ran on any x86-64 CPU.
- **The version has four numbers**, `X.Y.Z.N`, where `X.Y.Z` is the bundled libphash.

### Added

- `hash(source, algorithm, config=)` accepts a path, encoded bytes, a binary file
  object, an 8-bit array of pixels (numpy or anything with `__array_interface__`; RGB,
  BGR, gray, with or without alpha, any strides) and a Pillow image. An array whose
  only gaps are between rows is hashed without a copy.
- `Algorithm`, an enum of the nine algorithms, accepted wherever an algorithm is; each
  algorithm's libphash name (`"radial"`) is accepted too.
- `ImageContext.hashes()` computes several hashes of one image, the 64-bit ones in a
  single pass over the image.
- `hash_files()` and `hash_buffers()` hash many images on libphash's thread pool, with
  a progress callback that can stop the batch, a `BatchResult` per item, and Ctrl+C that
  stops the batch and raises `KeyboardInterrupt`.
- `Config`: every setting of libphash 2.0.1, among them `auto_orient`, `alpha_mode`,
  `max_pixels`, `decode_scale` (JPEG decoded at 1/2, 1/4 or 1/8), the mHash and Radial
  parameters and `whash_remove_max_haar_ll`.
- `similarity()` for two 64-bit hashes and `Digest.similarity()`, each with the measure
  that belongs to the algorithm; `RADIAL_PCC_THRESHOLD`.
- Text forms that keep the kind: `Digest.hex()`, `Digest.from_hex()` (`"bits:3fa0…"`,
  interchangeable with libphash's), `hash_to_hex()`, `hash_from_hex()`;
  `Digest.from_uint64()`.
- `libphash_version()`, `build_info()`, `can_decode()`, `digest_info()`.
- **A documentation site: <https://gudoshnikovn.github.io/python-libphash/>.** Guides to
  installing, loading, configuring, errors, batches, threads and processes, storage and
  search, and performance, the API reference from the docstrings, and the examples; the
  theory links to libphash's site. The code on every page runs in the test suite.
- A command, `libphash` (and `python -m libphash`): `hash` prints the hashes of files
  and directories, `compare` compares two images by the measures of each algorithm,
  `dupes` groups near-duplicates within a given number of bits, `info` prints the
  versions and the build for bug reports; `--json` for scripts.
- `examples/`: runnable scripts, each checked by the tests against the output its
  docstring shows: loading from every source, configuration, duplicates in a batch,
  SQLite storage, nearest hashes with numpy, a BK-tree, concurrency, and choosing a
  threshold. Four are twins of libphash's C examples and print the same output.
- Exceptions carry the C error (`code`, `code_name`) and, for a failed load, libphash's
  own message (`detail`); they pickle.
- Type information: the package is typed (`py.typed`) and checked with mypy and
  basedpyright in strict mode, and exports the types its signatures use (`Source`,
  `StrPath`, `PixelArray`, `AlgorithmLike`, the `Config` literals, the protocols).
- Thread safety: a context may be shared between threads, its calls are serialized;
  `Config`, `Digest`, results and errors are immutable and pickle, so they cross
  process boundaries.
- A software bill of materials in every wheel (`.dist-info/sboms/`, CycloneDX): libphash
  and each library linked into it, with its version and license. The license of each
  bundled library is in the wheel and the sdist, and `License-Expression` covers them
  all.
- Releases are published with PEP 740 attestations on PyPI and build provenance on the
  GitHub Release (`SECURITY.md`, "Verifying a release"); the sdist is reproducible.
- Wheels for Linux arm64 and Windows x86-64, and for the free-threaded builds of
  CPython 3.14 and later. A wheel per platform for CPython with the GIL, tagged `abi3`:
  it installs on every CPython from 3.10 on, a later one included. Paths with any characters, Cyrillic, CJK and emoji included, load on Windows.

### Changed

- **libphash is built by its own CMake project** and linked statically: the build of
  the wheel is the build libphash tests, with libjpeg-turbo, libpng, libwebp and zlib-ng
  vendored. The extension module exports one symbol, `PyInit__native`, so the bundled
  decoders cannot clash with another copy of the same libraries in the process (Pillow,
  OpenCV).
- **The same image gives the same hash on every platform**: arm64 and x86-64, Linux,
  macOS and Windows.
- **PNG is decoded with libpng on every platform**; the 1.4.1 wheels for Linux used
  spng 0.7.4, which has had no release since May 2023.
- **zlib is linked into the wheel** (zlib-ng); the 1.4.1 wheels for Linux used the
  system's zlib.
- cffi 2.0 or later is required (1.4.1: 1.15).
- Bundled libraries: libphash 2.0.1, libjpeg-turbo 3.2.0, libpng 1.6.59, libwebp 1.6.0,
  zlib-ng 2.3.3, stb_image 2.30.

### Fixed

- `__version__` is the package's version (1.4.1 reported `1.4.0`).
- A truncated JPEG or PNG, and a PNG whose critical chunk has a bad checksum, raise
  `CorruptDataError` with every decoder.

### Removed

- The `benchmarks/` directory of the source tree.
- Wheels for 32-bit x86 Linux and for musl Linux, which libphash does not test. pip
  builds the sdist there; it needs a C compiler.

### Security

- Bundled libpng 1.6.59. The 1.4.1 wheel for macOS carries libpng 1.6.56, affected by
  CVE-2026-46675, a use-after-free in `png_read_end()` after an incomplete `zTXt`,
  `iTXt` or `iCCP` decompression, and by a double free after an allocation failure;
  libphash's PNG decoder does not call `png_read_end()` on that path. The 1.4.1 wheels
  for Linux decode PNG with spng 0.7.4, which is no longer maintained.
- Images are refused before they are decoded when they exceed `Config.max_pixels` or
  the per-side limit: 1.x decoded an image of any declared size, so a small file could
  make it allocate gigabytes (a decompression bomb).
- Pixel counts are computed without integer overflow on large images.
- A `Digest` holds at most `PH_DIGEST_MAX_BYTES` bytes and its size is its length: in
  1.x, `Digest(data, size)` took the size from the caller, and a comparison read `size`
  bytes from a 64-byte buffer.
- On the 32-bit x86 wheels of 1.x, a large BMH block size (`set_block_params()`)
  overflowed the size of a scratch buffer, and the hash wrote past it on the heap. The
  block size is 2 to 32 (`Config.bmh_block_size`), and sizes are computed with overflow
  checks.

## 1.x

The 1.x releases were numbered independently of libphash. Their notes are in the
[GitHub releases](https://github.com/gudoshnikovn/python-libphash/releases) of the
repository.

| Version | libphash |
|---|---|
| 1.4.1 | 1.10.4 |
| 1.4.0 | 1.10.1 |
| 1.3.0 | 1.9.0 |
| 1.2.0 | 1.6.1 |
| 1.1.0 | 1.3.0 |
| 1.0.3 | 1.2.0 |

[Unreleased]: https://github.com/gudoshnikovn/python-libphash/compare/v2.0.1.0...HEAD
[2.0.1.0]: https://github.com/gudoshnikovn/python-libphash/compare/v1.4.1...v2.0.1.0
