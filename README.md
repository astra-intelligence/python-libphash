# python-libphash

Perceptual image hashing in Python, with the [libphash](https://github.com/gudoshnikovn/libphash)
C library inside.

[![CI](https://github.com/gudoshnikovn/python-libphash/actions/workflows/ci.yml/badge.svg)](https://github.com/gudoshnikovn/python-libphash/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/python-libphash.svg)](https://pypi.org/project/python-libphash/)
[![Python](https://img.shields.io/pypi/pyversions/python-libphash.svg)](https://pypi.org/project/python-libphash/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/gudoshnikovn/python-libphash/blob/main/LICENSE)

A perceptual hash changes little when an image is resized, recompressed or slightly
edited, so comparing hashes finds the copies of a picture among many images; an
unrelated picture lands about half the bits away. The package computes nine algorithms
in C, decodes JPEG, PNG and WebP with libraries linked into the wheel, and gives the same
hash for the same file on every platform, bit for bit libphash's.

**[Documentation](https://gudoshnikovn.github.io/python-libphash/)** · the theory
(algorithms, comparing, choosing a threshold) is on
[libphash's site](https://gudoshnikovn.github.io/libphash/).

```bash
pip install python-libphash
```

Wheels for Linux (x86-64, arm64), macOS (arm64) and Windows (x86-64), CPython 3.10 and
later, free-threaded builds included; elsewhere pip builds from source with a C compiler.

```python
import libphash as ph
from libphash import Algorithm

a = ph.hash("photo.jpg")                       # pHash, a 64-bit int
b = ph.hash("photo_copy.jpg")
print(ph.hamming_distance(a, b))               # 0..64 bits differ: 0 for a copy

r = ph.hash("photo.jpg", Algorithm.RADIAL)     # a Digest
print(r.similarity(ph.hash("photo_rotated.jpg", Algorithm.RADIAL)))

results = ph.hash_files(["photo.jpg", "photo_copy.jpg"], threads=0)   # all CPUs
```

`ph.hash()` takes a path, encoded bytes, a file object, a numpy array of pixels or a
Pillow image; `ImageContext` computes several hashes of one image and reuses its buffers
from image to image; `Config` holds every setting of libphash and checks it.

From a shell, `libphash hash`, `compare` and `dupes` do the same for files
(`python -m libphash` where the command is not on `PATH`):

```bash
libphash dupes --max-bits 10 ~/Pictures
```

## Scope

Hashes are deterministic and unkeyed: they find the copies of a picture in a collection
you control. They are not for moderation, blocklists or checking untrusted input, since
anyone who can choose the images can make two pictures hash alike or keep a copy from
matching. Decoding files from anywhere is the expected use, and a crash on one is a
vulnerability: see [SECURITY.md](https://github.com/gudoshnikovn/python-libphash/blob/main/SECURITY.md).

## Versions

The version is `X.Y.Z.N`: `X.Y.Z` is the bundled libphash, `N` the revision of the
binding. Hash values depend on `X.Y.Z` and the settings only, so
`pip install "python-libphash==2.0.2.*"` keeps a stored collection comparable while
taking the binding's fixes. Upgrading from 1.x changes hash values and the API: read
[MIGRATION.md](https://github.com/gudoshnikovn/python-libphash/blob/main/MIGRATION.md).

## License

MIT, see [LICENSE](https://github.com/gudoshnikovn/python-libphash/blob/main/LICENSE). The
wheels include libphash and the libraries it bundles (libjpeg-turbo, libpng, libwebp,
zlib-ng, stb_image), each under its own license, carried in the wheel.
