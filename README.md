# python-libphash

High-performance Python bindings for [libphash](https://github.com/gudoshnikovn/libphash), a C library for perceptual image hashing.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

## Overview

`libphash` provides multiple algorithms to generate "perceptual hashes" of images. Unlike cryptographic hashes (like MD5 or SHA256), perceptual hashes change only slightly if the image is resized, compressed, or has minor color adjustments. This makes them ideal for finding duplicate or similar images.

### Supported Algorithms

*   **64-bit Hashes (uint64):**
    *   `ahash`: Average Hash
    *   `dhash`: Difference Hash
    *   `phash`: Perceptual Hash (DCT based)
    *   `whash`: Wavelet Hash
    *   `mhash`: Median Hash
    *   `color_hash`: Packed 42-bit HSV-based color hash (compatible with `imagehash.colorhash`).
*   **Digest Hashes (Multi-byte):**
    *   `bmh`: Block Mean Hash (256-bit digest).
    *   `color_moments_hash`: Statistical color distribution digest (mean, variance, skewness, kurtosis).
    *   `radial_hash`: Rotation-invariant Fourier-Mellin transform digest.

## Installation

### Prerequisites
*   A C compiler (GCC/Clang or MSVC)
*   Python 3.8 or higher

### Install from PyPI
```bash
pip install python-libphash
# or using uv
uv add python-libphash
```

### Install from source
```bash
git clone --recursive https://github.com/gudoshnikovn/python-libphash.git
cd python-libphash
pip install .
# or using uv
uv pip install .
```

## Versioning

The version has four numbers, `X.Y.Z.N`:

*   `X.Y.Z` is the version of the bundled libphash: `python-libphash 2.0.1.0` carries libphash 2.0.1.
*   `N` is the revision of the binding on top of it. The first release for a libphash version is `.0`, and the zero is always written out; fixes and additions to the Python side alone are `2.0.1.1`, `2.0.1.2`, …

Hash values depend on the libphash version and on the context settings, so hashes stored for later comparison are comparable only when both were computed with the same `X.Y.Z` and the same settings. To pin the C library while still receiving binding fixes, pin the first three numbers:

```bash
pip install "python-libphash==2.0.1.*"
```

The 1.x releases were numbered independently of libphash (1.4.1 bundles libphash 1.10.4).

## Quick Start

### Quick Start (CLI)
You can quickly compute a hash from the command line after installation:
```bash
python -m libphash.utils --path photo.jpg --method phash
```

### Basic Usage
```python
from libphash import ImageContext, HashMethod, hamming_distance

# Use the context manager for automatic memory management
with ImageContext("photo.jpg") as ctx:
    # Get standard 64-bit hashes
    phash_val = ctx.phash
    dhash_val = ctx.dhash
    
    print(f"pHash: {phash_val:016x}")
    print(f"dHash: {dhash_val:016x}")

# Compare two images
from libphash import compare_images
distance = compare_images("image1.jpg", "image2.jpg", method=HashMethod.PHASH)
print(f"Hamming Distance: {distance}")
```

### Customizing Algorithms & Performance
Fine-tune hashing algorithms for specific use cases. Note that hashes generated with different parameters are **not comparable**.

*   **Ultra-Fast Image Decoding**: `libphash` bundles high-performance decoders for JPEG, PNG, and WebP. It uses `libjpeg-turbo` (TurboJPEG API), `libpng`/`spng`, and `libwebp` with SIMD acceleration (SSE/NEON/AVX2). Image data is loaded via `mmap()` for zero-copy I/O between the file system and the decoder.
    *   **Fallback**: Automatically falls back to `stb_image` for other formats or if bundled decoders are disabled.

```python
with ImageContext("photo.jpg") as ctx:
    # pHash (DCT) resolution
    ctx.set_phash_params(dct_size=32, reduction_size=8)
    
    # Radial Hash precision
    ctx.set_radial_params(projections=40, samples=128)
    
    # Block-based hashes (BMH) grid resolution
    ctx.set_block_params(block_size=16)
    
    # Wavelet Hash (wHash) Mode: "fast" (default) or "full"
    ctx.set_whash_mode("full")
    
    # Custom Grayscale weights (R, G, B)
    ctx.set_gray_weights(38, 75, 15)
    
    print(f"Custom pHash: {ctx.phash:016x}")
```

### Working with Digests (Advanced Hashes)
Algorithms like Radial Hash or Color Hash return a `Digest` object instead of a single integer.

```python
with ImageContext("photo.jpg") as ctx:
    digest = ctx.radial_hash
    print(f"Digest size: {digest.size} bytes")
    print(f"Raw data: {digest.data.hex()}")

# Comparing digests
with ImageContext("photo_v2.jpg") as ctx2:
    digest2 = ctx2.radial_hash
    
    # Hamming distance for bit-wise comparison
    h_dist = digest.distance_hamming(digest2)
    
    # L2 (Euclidean) distance for similarity
    l2_dist = digest.distance_l2(digest2)
```

## API Reference

### `ImageContext`
The main class for loading images and computing hashes.
*   `__init__(path=None, bytes_data=None)`: Load an image from a file path or memory.
*   `set_gamma(gamma: float)`: Set gamma correction.
*   `set_gray_weights(r, g, b)`: Set custom RGB weights for grayscale conversion.
*   `set_phash_params(dct_size, reduction_size)`: Configure pHash DCT resolution.
*   `set_radial_params(projections, samples)`: Configure Radial Hash precision.
*   `set_block_params(block_size)`: Configure BMH/mHash grid resolution.
*   `set_whash_mode(mode="fast")`: Use "fast" (median) or "full" (ImageHash accurate 2D DWT).
*   **Properties**: `ahash`, `dhash`, `phash`, `whash`, `mhash` (returns `int`).
*   **Properties**: `bmh`, `color_hash`, `radial_hash` (returns `Digest`).

### `Digest`
*   `data`: The raw `bytes` of the hash.
*   `size`: Length of the hash in bytes.
*   `distance_hamming(other)`: Calculates bit-wise distance.
*   `distance_l2(other)`: Calculates Euclidean distance.

### Utilities
*   `hamming_distance(h1: int, h2: int)`: Returns the number of differing bits between two 64-bit integers.
*   `ph_can_use_libjpeg()`: Returns `True` if `libjpeg-turbo` is enabled.
*   `ph_can_use_libpng()`: Returns `True` if `libpng` or `spng` is enabled.
*   `get_hash(path, method)`: Quick way to get a hash without manual context management.
*   `compare_images(path1, path2, method)`: Returns the Hamming distance between two image files.

## Performance
Since the core logic is implemented in C and uses SIMD-accelerated decoders (SSE4.2, AVX2, NEON), `libphash` is significantly faster than pure-Python alternatives while maintaining top-tier accuracy.

| Algorithm | imagehash (s) | libphash (s) | Speedup |
| :--- | :--- | :--- | :--- |
| **aHash** | 0.2164 | 0.1033 | **1.92x** |
| **pHash** | 0.3211 | 0.0842 | **3.40x** |
| **dHash** | 0.2017 | 0.1048 | **1.80x** |
| **wHash** | 1.7832 | 0.0869 | **17.16x** |

*Benchmarks ran on 200 images (JPEG).*

## License
This project is licensed under the MIT License - see the LICENSE file for details.

