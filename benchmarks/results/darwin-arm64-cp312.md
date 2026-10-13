## Environment

- **date:** 2026-10-13
- **machine:** Apple M3 Pro, 11 CPUs, 36 GiB
- **os:** macOS-26.6.2-arm64-arm-64bit
- **python:** CPython 3.12.11
- **python-libphash:** 2.0.1.0
- **build_info:** version=2.0.1 jpeg=libjpeg-turbo png=libpng webp=libwebp zlib=zlib-ng threads=on simd=neon mock=off
- **cffi:** 2.1.1
- **numpy:** 2.5.4
- **Pillow:** 12.3.0
- **effort:** at least 5 runs and 1 s per case, after one run to warm up

A time is the minimum / the median of the runs, per item of work; in parentheses, the difference from the baseline and the ratio to it.

## 1. What a call costs: C, cffi and the binding

### Loading a file

A JPEG file into a context that is kept from load to load.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C | 235 µs / 245 µs | 60 ms / 60.8 ms |
| C through cffi | 229 µs / 242 µs (−6.21 µs, ×0.974) | 58.6 ms / 59.2 ms (−1.4 ms, ×0.977) |
| load_file(str) | 232 µs / 248 µs (−2.46 µs, ×0.99) | 59 ms / 60.1 ms (−943 µs, ×0.984) |
| load_file(Path) | 237 µs / 244 µs (+1.92 µs, ×1.01) | 57.5 ms / 58.7 ms (−2.53 ms, ×0.958) |
| load(str) | 236 µs / 253 µs (+1.13 µs, ×1) | 57.4 ms / 57.8 ms (−2.62 ms, ×0.956) |

### Loading encoded bytes

The same JPEG already in memory, in the forms a program holds it.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C | 237 µs / 610 µs | 57.1 ms / 57.4 ms |
| C through cffi | 235 µs / 604 µs (−2.25 µs, ×0.991) | 57 ms / 57.3 ms (−98.7 µs, ×0.998) |
| load_bytes(bytes) | 236 µs / 613 µs (−1.08 µs, ×0.995) | 56.1 ms / 58.6 ms (−970 µs, ×0.983) |
| load_bytes(bytearray) | 233 µs / 614 µs (−4.63 µs, ×0.981) | 56 ms / 57.6 ms (−1.08 ms, ×0.981) |
| load_bytes(memoryview) | 236 µs / 621 µs (−917 ns, ×0.996) | 55.9 ms / 56.3 ms (−1.18 ms, ×0.979) |
| load(bytes) | 236 µs / 618 µs (−1.67 µs, ×0.993) | 56 ms / 56.3 ms (−1.03 ms, ×0.982) |
| load_fileobj(BytesIO) | 236 µs / 613 µs (−1.04 µs, ×0.996) | 56 ms / 56.3 ms (−1.09 ms, ×0.981) |
| load_fileobj(open file), open included | 253 µs / 659 µs (+15.7 µs, ×1.07) | 56.6 ms / 57.1 ms (−511 µs, ×0.991) |
| hash_buffers([bytes]), per item | 307 µs / 375 µs (+69.3 µs, ×1.29) | 60.5 ms / 61.8 ms (+3.38 ms, ×1.06) |

### Loading decoded pixels

The same image decoded (by Pillow, untimed) into 8-bit RGB pixels, in the forms numpy, OpenCV and Pillow hand them over.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C | 9.79 µs / 10.3 µs | 1.17 ms / 1.28 ms |
| C through cffi | 10.3 µs / 10.6 µs (+541 ns, ×1.06) | 1.15 ms / 1.27 ms (−27.6 µs, ×0.976) |
| numpy, contiguous (no copy) | 11.7 µs / 12.3 µs (+1.88 µs, ×1.19) | 1.14 ms / 1.21 ms (−35.8 µs, ×0.97) |
| numpy, a crop: rows apart (no copy) | 12.3 µs / 12.9 µs (+2.56 µs, ×1.26) | 1.16 ms / 1.27 ms (−10.7 µs, ×0.991) |
| memoryview with a shape (no copy) | 10.9 µs / 11.4 µs (+1.12 µs, ×1.11) | 1.14 ms / 1.17 ms (−31.5 µs, ×0.973) |
| numpy BGR, channel_order='bgr' (a copy) | 222 µs / 227 µs (+212 µs, ×22.7) | 28.2 ms / 28.6 ms (+27 ms, ×24) |
| numpy BGR, bgr[..., ::-1] (a copy) | 1.93 ms / 2 ms (+1.92 ms, ×197) | 233 ms / 235 ms (+232 ms, ×199) |
| numpy BGR, np.ascontiguousarray(bgr[..., ::-1]) | 442 µs / 447 µs (+432 µs, ×45.1) | 54.9 ms / 55.2 ms (+53.7 ms, ×46.8) |
| numpy, one channel (h, w) | 4.82 µs / 5.26 µs (−4.97 µs, ×0.492) | 330 µs / 374 µs (−843 µs, ×0.281) |
| Pillow RGB image, load_pil() | 47.8 µs / 51.5 µs (+38 µs, ×4.88) | 6.79 ms / 7.19 ms (+5.62 ms, ×5.79) |
| Pillow RGB image, np.asarray() then load_pixels() | 49.8 µs / 53.6 µs (+40 µs, ×5.09) | 6.7 ms / 7.1 ms (+5.52 ms, ×5.71) |

### One hash of a loaded image, 400×400

Each hash computed again on an image that a first hash prepared: the grayscale image and the area grid are cached in the context, so the 64-bit hashes cost little more than the call itself.

| | C | C through cffi | hash(Algorithm) | hash('name') | its method, ahash() … |
| --- | --- | --- | --- | --- | --- |
| ahash | 375 ns / 458 ns | 500 ns / 583 ns (+125 ns, ×1.33) | 791 ns / 875 ns (+416 ns, ×2.11) | 1.12 µs / 1.19 µs (+750 ns, ×3) | 758 ns / 817 ns (+383 ns, ×2.02) |
| dhash | 46 µs / 47.1 µs | 46 µs / 47.4 µs (+0 ns, ×1) | 46.5 µs / 47.7 µs (+542 ns, ×1.01) | 47 µs / 47.6 µs (+1 µs, ×1.02) | 46.5 µs / 47.1 µs (+542 ns, ×1.01) |
| phash | 3.46 µs / 3.63 µs | 3.6 µs / 3.63 µs (+139 ns, ×1.04) | 3.83 µs / 4 µs (+375 ns, ×1.11) | 4.2 µs / 4.26 µs (+740 ns, ×1.21) | 3.89 µs / 4.07 µs (+427 ns, ×1.12) |
| whash | 792 ns / 875 ns | 836 ns / 854 ns (+44.3 ns, ×1.06) | 1.1 µs / 1.15 µs (+313 ns, ×1.39) | 1.45 µs / 1.52 µs (+660 ns, ×1.83) | 1.11 µs / 1.14 µs (+319 ns, ×1.4) |
| bmh | 792 ns / 917 ns | 896 ns / 951 ns (+104 ns, ×1.13) | 1.69 µs / 1.79 µs (+896 ns, ×2.13) | 2.04 µs / 2.16 µs (+1.25 µs, ×2.58) | 1.68 µs / 1.75 µs (+884 ns, ×2.12) |
| mhash | 956 µs / 983 µs | 913 µs / 961 µs (−43 µs, ×0.955) | 915 µs / 936 µs (−41.6 µs, ×0.956) | 914 µs / 927 µs (−41.8 µs, ×0.956) | 916 µs / 942 µs (−40.4 µs, ×0.958) |
| radial | 608 µs / 620 µs | 584 µs / 589 µs (−24.6 µs, ×0.96) | 586 µs / 591 µs (−22 µs, ×0.964) | 586 µs / 591 µs (−22.9 µs, ×0.962) | 587 µs / 591 µs (−22 µs, ×0.964) |
| color_hash | 131 µs / 136 µs | 129 µs / 132 µs (−1.79 µs, ×0.986) | 132 µs / 137 µs (+1.92 µs, ×1.01) | 130 µs / 132 µs (−291 ns, ×0.998) | 130 µs / 131 µs (−708 ns, ×0.995) |
| color_moments | 247 µs / 249 µs | 226 µs / 244 µs (−20.7 µs, ×0.916) | 228 µs / 245 µs (−19.4 µs, ×0.922) | 245 µs / 250 µs (−2.42 µs, ×0.99) | 244 µs / 249 µs (−3 µs, ×0.988) |

### Loading and one hash, 400×400

A load of the encoded bytes and the first hash on it, which prepares the grayscale image and the area grid: what one image and one hash cost.

| | C | load_bytes() + hash() |
| --- | --- | --- |
| ahash | 276 µs / 283 µs | 273 µs / 279 µs (−3.75 µs, ×0.986) |
| dhash | 283 µs / 287 µs | 280 µs / 287 µs (−2.62 µs, ×0.991) |
| phash | 279 µs / 284 µs | 275 µs / 281 µs (−3.96 µs, ×0.986) |
| whash | 276 µs / 283 µs | 274 µs / 277 µs (−2.37 µs, ×0.991) |
| bmh | 277 µs / 288 µs | 256 µs / 276 µs (−20.9 µs, ×0.924) |
| mhash | 1.19 ms / 1.24 ms | 1.15 ms / 1.18 ms (−44.7 µs, ×0.963) |
| radial | 822 µs / 856 µs | 822 µs / 833 µs (−166 ns, ×1) |
| color_hash | 351 µs / 365 µs | 353 µs / 361 µs (+1.79 µs, ×1.01) |
| color_moments | 466 µs / 478 µs | 467 µs / 477 µs (+1000 ns, ×1) |

### One hash of a loaded image, 20 Mpx

Each hash computed again on an image that a first hash prepared: the grayscale image and the area grid are cached in the context, so the 64-bit hashes cost little more than the call itself.

| | C | C through cffi | hash(Algorithm) | hash('name') | its method, ahash() … |
| --- | --- | --- | --- | --- | --- |
| ahash | 333 ns / 458 ns | 500 ns / 583 ns (+166 ns, ×1.5) | 750 ns / 875 ns (+417 ns, ×2.25) | 1.12 µs / 1.18 µs (+792 ns, ×3.37) | 772 ns / 816 ns (+439 ns, ×2.32) |
| dhash | 4.91 ms / 4.96 ms | 4.92 ms / 4.96 ms (+8.04 µs, ×1) | 4.91 ms / 4.96 ms (+2.83 µs, ×1) | 4.91 ms / 4.96 ms (+1.71 µs, ×1) | 4.9 ms / 4.96 ms (−14.6 µs, ×0.997) |
| phash | 3.42 µs / 3.54 µs | 3.59 µs / 3.63 µs (+175 ns, ×1.05) | 3.92 µs / 4.04 µs (+499 ns, ×1.15) | 4.18 µs / 4.29 µs (+764 ns, ×1.22) | 3.64 µs / 3.9 µs (+220 ns, ×1.06) |
| whash | 875 ns / 958 ns | 942 ns / 994 ns (+67.3 ns, ×1.08) | 1.21 µs / 1.25 µs (+333 ns, ×1.38) | 1.57 µs / 1.62 µs (+692 ns, ×1.79) | 1.22 µs / 1.27 µs (+344 ns, ×1.39) |
| bmh | 708 ns / 792 ns | 824 ns / 856 ns (+116 ns, ×1.16) | 1.62 µs / 1.73 µs (+917 ns, ×2.29) | 2.01 µs / 2.12 µs (+1.3 µs, ×2.84) | 1.62 µs / 1.7 µs (+908 ns, ×2.28) |
| mhash | 35.1 ms / 35.5 ms | 32 ms / 32.2 ms (−3.15 ms, ×0.91) | 32 ms / 32.2 ms (−3.11 ms, ×0.911) | 32.4 ms / 33.1 ms (−2.77 ms, ×0.921) | 32 ms / 32.3 ms (−3.08 ms, ×0.912) |
| radial | 46.8 ms / 47.1 ms | 46.7 ms / 46.9 ms (−103 µs, ×0.998) | 46.8 ms / 47 ms (−33.2 µs, ×0.999) | 46.8 ms / 47.3 ms (−12.9 µs, ×1) | 47.5 ms / 49.8 ms (+695 µs, ×1.01) |
| color_hash | 16.6 ms / 17 ms | 16.6 ms / 16.7 ms (−62.7 µs, ×0.996) | 16.6 ms / 16.7 ms (−43.2 µs, ×0.997) | 16.6 ms / 16.7 ms (−67 µs, ×0.996) | 16.6 ms / 16.7 ms (−76.3 µs, ×0.995) |
| color_moments | 30.7 ms / 30.9 ms | 31.2 ms / 31.4 ms (+458 µs, ×1.01) | 30.6 ms / 30.7 ms (−117 µs, ×0.996) | 30.6 ms / 31.2 ms (−160 µs, ×0.995) | 30.6 ms / 30.7 ms (−143 µs, ×0.995) |

### Loading and one hash, 20 Mpx

A load of the encoded bytes and the first hash on it, which prepares the grayscale image and the area grid: what one image and one hash cost.

| | C | load_bytes() + hash() |
| --- | --- | --- |
| ahash | 58.5 ms / 58.8 ms | 59.1 ms / 60.1 ms (+614 µs, ×1.01) |
| dhash | 62.1 ms / 62.3 ms | 62.3 ms / 63 ms (+130 µs, ×1) |
| phash | 58.5 ms / 58.8 ms | 58.5 ms / 58.7 ms (−18.5 µs, ×1) |
| whash | 58.6 ms / 58.8 ms | 58.6 ms / 60.1 ms (+70.8 µs, ×1) |
| bmh | 58.7 ms / 60 ms | 58.6 ms / 58.8 ms (−93.1 µs, ×0.998) |
| mhash | 92.4 ms / 94.8 ms | 89.3 ms / 89.7 ms (−3.17 ms, ×0.966) |
| radial | 104 ms / 105 ms | 104 ms / 106 ms (+433 µs, ×1) |
| color_hash | 72.5 ms / 72.8 ms | 72.6 ms / 72.8 ms (+141 µs, ×1) |
| color_moments | 86.7 ms / 87 ms | 86.6 ms / 86.7 ms (−179 µs, ×0.998) |

### Several hashes of one load

A load of the encoded bytes and the four 64-bit hashes (or all nine). hashes() computes the 64-bit ones in one ph_compute_multi() call, which shares their work on the full image.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C: ph_compute_multi() | 322 µs / 328 µs | 63.4 ms / 63.8 ms |
| C: four ph_compute_*() | 300 µs / 331 µs (−21.5 µs, ×0.933) | 64.2 ms / 65.3 ms (+831 µs, ×1.01) |
| hashes(4 × 64-bit) | 326 µs / 339 µs (+4.58 µs, ×1.01) | 63.6 ms / 64.4 ms (+180 µs, ×1) |
| hash() four times | 324 µs / 328 µs (+2.08 µs, ×1.01) | 63.6 ms / 63.9 ms (+178 µs, ×1) |
| hashes(all 9) | 2.21 ms / 2.24 ms (+1.89 ms, ×6.87) | 190 ms / 193 ms (+127 ms, ×3) |
| hash() nine times | 2.21 ms / 2.24 ms (+1.88 ms, ×6.86) | 190 ms / 191 ms (+127 ms, ×3) |
| hash(path) four times, a load each | 1.12 ms / 1.19 ms (+794 µs, ×3.47) | 240 ms / 240 ms (+176 ms, ×3.78) |

### From a file to its pHash

Per image: a new context for each, one context kept, or a batch on one thread (threads=1, the calling thread) of 64 copies of the file.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C: a new context | 289 µs / 298 µs | 58.8 ms / 59.2 ms |
| C: one context | 283 µs / 289 µs (−5.5 µs, ×0.981) | 59.5 ms / 60.7 ms (+697 µs, ×1.01) |
| C: ph_hash_files(), 1 thread | 287 µs / 290 µs (−1.66 µs, ×0.994) | 59.3 ms / 59.9 ms (+514 µs, ×1.01) |
| hash(path): a new context | 286 µs / 311 µs (−2.92 µs, ×0.99) | 58.8 ms / 59.5 ms (−17.3 µs, ×1) |
| ImageContext, kept | 268 µs / 292 µs (−20.6 µs, ×0.929) | 58.8 ms / 59.1 ms (+37.6 µs, ×1) |
| hash_files(threads=1) | 290 µs / 292 µs (+1.21 µs, ×1) | 59.5 ms / 59.9 ms (+677 µs, ×1.01) |

### Comparing two hashes

One comparison of two hashes of two similar photographs (photo.jpeg and photo_copy.jpeg), and the conversions of a hash.

| | per call |
| --- | --- |
| 64-bit Hamming: C ph_hamming_distance() | 0.793 ns / 0.81 ns |
| 64-bit Hamming: cffi | 69.3 ns / 97.4 ns |
| 64-bit Hamming: hamming_distance() | 229 ns / 250 ns |
| 64-bit Hamming: (a ^ b).bit_count() | 32.6 ns / 36.2 ns |
| 64-bit similarity() | 208 ns / 239 ns |
| bmh Hamming: C | 3.44 ns / 3.45 ns |
| bmh Hamming: Digest | 812 ns / 896 ns |
| color_moments L2: C | 5.82 ns / 5.83 ns |
| color_moments L2: Digest | 808 ns / 875 ns |
| radial radial: C | 86.3 ns / 86.4 ns |
| radial radial: Digest | 980 ns / 1.08 µs |
| color_hash histogram: C | 52.8 ns / 53.2 ns |
| color_hash histogram: Digest | 948 ns / 1.02 µs |
| bmh similarity: C | 3.7 ns / 3.98 ns |
| bmh similarity: Digest | 825 ns / 883 ns |
| Digest(bytes, kind), 72 bytes | 333 ns / 396 ns |
| Digest.hex(), 72 bytes | 614 ns / 656 ns |
| Digest.from_hex(), 72 bytes | 833 ns / 903 ns |
| hash_to_hex(int) | 319 ns / 361 ns |
| f'{h:016x}' | 83.3 ns / 101 ns |

## 2. Searching: one against many, every pair

### 1 to N: the nearest of N 64-bit hashes

The index of the hash nearest to a query, per hash compared.

| | N = 10,000 | N = 100,000 | N = 1,000,000 |
| --- | --- | --- | --- |
| C loop, ph_hamming_distance() | 0.793 ns / 0.794 ns | 0.793 ns / 0.794 ns | 0.794 ns / 0.811 ns |
| Python loop, hamming_distance() | 242 ns / 245 ns (+241 ns, ×305) | 244 ns / 249 ns (+243 ns, ×308) | 249 ns / 251 ns (+248 ns, ×314) |
| Python loop, (q ^ h).bit_count() | 48.9 ns / 50.4 ns (+48.1 ns, ×61.6) | 49 ns / 50.3 ns (+48.2 ns, ×61.8) | 49.8 ns / 50.5 ns (+49.1 ns, ×62.8) |
| numpy, bitwise_count(arr ^ q).argmin() | 0.471 ns / 0.525 ns (−0.322 ns, ×0.594) | 0.311 ns / 0.335 ns (−0.482 ns, ×0.392) | 0.321 ns / 0.334 ns (−0.473 ns, ×0.404) |
| numpy, building the uint64 array from a list of int | 16.7 ns / 16.9 ns (+15.9 ns, ×21) | 17 ns / 17.3 ns (+16.2 ns, ×21.4) | 17.3 ns / 17.4 ns (+16.5 ns, ×21.7) |

### 1 to N: the nearest of N mHash digests (72 bytes)

Digests of the BITS kind compared by Hamming distance, per digest compared.

| | N = 10,000 | N = 100,000 |
| --- | --- | --- |
| Python loop, Digest.hamming_distance() | 860 ns / 877 ns | 893 ns / 902 ns |
| numpy over bytes, bitwise_count(m ^ q).sum(1).argmin() | 21.3 ns / 21.6 ns | 21.2 ns / 21.5 ns |
| numpy over uint64 words, the same | 10.4 ns / 10.5 ns | 10.2 ns / 10.3 ns |
| numpy, building the matrix from Digest.data | 31.3 ns / 32.3 ns | 31.4 ns / 32.1 ns |

### N to N: every pair of N 64-bit hashes

The sum of the distances of all N(N-1)/2 pairs, per pair; numpy works on blocks of 256 rows against all N.

| | N = 1,000 | N = 10,000 |
| --- | --- | --- |
| C loop, ph_hamming_distance() | 0.803 ns / 0.81 ns | 0.803 ns / 0.806 ns |
| Python loop, (a ^ b).bit_count() | 40.3 ns / 41.6 ns (+39.5 ns, ×50.2) | — |
| numpy, bitwise_count in blocks | 1.36 ns / 1.42 ns (+0.561 ns, ×1.7) | 0.791 ns / 0.804 ns (−0.0123 ns, ×0.985) |

## 3. Memory

Each case runs once in a fresh interpreter. *Python* is the peak of the Python allocations the case makes (tracemalloc): the copies the binding makes, exact and the same on every run. *Resident* is the rise of the peak resident memory over the memory before the case: the C library's decoded image and decoder buffers on top of that. libphash keeps a decoded image as 3 bytes per pixel.

### Memory of one load

A load into a new context, from each form of the image.

| | 400×400: Python | 400×400: resident | 20 Mpx: Python | 20 Mpx: resident |
| --- | --- | --- | --- | --- |
| load_file() | 537 B | 1.02 MiB | 543 B | 63.6 MiB |
| load_bytes(bytes) | 10.2 KiB | 1008 KiB | 10.2 KiB | 57.8 MiB |
| load_bytes(memoryview) | 10.5 KiB | 1.02 MiB | 10.5 KiB | 57.8 MiB |
| load_fileobj(open file) | 39.6 KiB | 1.02 MiB | 5.75 MiB | 63.5 MiB |
| load_fileobj(BytesIO) | 10.3 KiB | 1 MiB | 10.3 KiB | 57.8 MiB |
| numpy, contiguous | 10.5 KiB | 528 KiB | 10.5 KiB | 57.2 MiB |
| numpy, a crop: rows apart | 10.6 KiB | 512 KiB | 10.6 KiB | 57.2 MiB |
| numpy BGR, channel_order='bgr' | 1.37 MiB | 1.92 MiB | 171 MiB | 229 MiB |
| numpy BGR, bgr[..., ::-1] | 471 KiB | 992 KiB | 57.1 MiB | 114 MiB |
| numpy BGR, np.ascontiguousarray(bgr[..., ::-1]) | 479 KiB | 992 KiB | 57.1 MiB | 114 MiB |
| Pillow RGB image, load_pil() | 939 KiB | 1.12 MiB | 114 MiB | 191 MiB |
| Pillow RGB image, np.asarray() | 939 KiB | 1.17 MiB | 114 MiB | 191 MiB |

### Contexts

What stays allocated: an empty context (per context, of 1,000), one holding the 20 Mpx image after its nine hashes, the same closed. Resident memory counts pages the allocator keeps for reuse after a free: macOS's allocator keeps the pages of a closed context resident until the system needs them.

| | Python | resident | resident at the peak |
| --- | --- | --- | --- |
| an empty context | 601 B | 15.2 KiB | — |
| holding 20 Mpx, nine hashes | 5.57 KiB | 176 MiB | 176 MiB |
| the same, closed | 4.88 KiB | 176 MiB | 176 MiB |

### Batch memory against threads, 20 Mpx

hash_files() of 22 copies of the file: the rise of peak resident memory, and the bound libphash states (4 bytes per pixel and the file, per worker).

| | threads=1 | threads=2 | threads=4 | threads=8 | threads=11 |
| --- | --- | --- | --- | --- | --- |
| peak resident rise | 82.8 MiB | 165 MiB | 329 MiB | 598 MiB | 764 MiB |
| Python allocations | 15.8 KiB | 16.8 KiB | 17.8 KiB | 19.8 KiB | 21.7 KiB |
| libphash's bound | 81.9 MiB | 164 MiB | 328 MiB | 655 MiB | 901 MiB |

### Repetition

load_bytes() and phash() of 400×400, 10,000 times on one context after as many to warm up: what stays allocated afterwards (tests/test_memory.py holds every path of the binding to a bound).

| | Python, kept | Python, peak | resident, kept |
| --- | --- | --- | --- |
| 10,000 loads and hashes | 0 B | 432 B | 64 KiB |

## 4. Parallelism

Subinterpreters (concurrent.interpreters) need Python 3.14; this run is on 3.12.

### Throughput against workers, 400×400

Images per second for 1000 loads of the file and their pHash, and the speedup over one worker. A process pool is started before it is timed (the next table has that cost) and keeps one context per process.

| | 1 | 2 | 4 | 8 | 11 |
| --- | --- | --- | --- | --- | --- |
| threads, a context each | 3,412/s | 6,667/s (×1.95) | 13,237/s (×3.88) | 18,931/s (×5.55) | 21,562/s (×6.32) |
| threads, one shared context | 3,449/s | 3,350/s (×0.971) | 3,321/s (×0.963) | 3,299/s (×0.957) | 3,296/s (×0.956) |
| ThreadPoolExecutor.map, a context per thread | 3,314/s | 6,325/s (×1.91) | 12,034/s (×3.63) | 18,606/s (×5.61) | 21,226/s (×6.4) |
| hash_files(threads=N) | 3,346/s | 6,729/s (×2.01) | 13,086/s (×3.91) | 19,713/s (×5.89) | 22,886/s (×6.84) |
| ProcessPoolExecutor (spawn), paths sent | 3,424/s | 6,740/s (×1.97) | 12,842/s (×3.75) | 18,633/s (×5.44) | 21,649/s (×6.32) |
| ProcessPoolExecutor (spawn), bytes sent | 3,576/s | 6,963/s (×1.95) | 13,297/s (×3.72) | 19,678/s (×5.5) | 22,168/s (×6.2) |
| ProcessPoolExecutor (forkserver), paths sent | 3,410/s | 6,785/s (×1.99) | 12,920/s (×3.79) | 19,222/s (×5.64) | 19,911/s (×5.84) |
| ProcessPoolExecutor (fork), paths sent | 3,430/s | 6,766/s (×1.97) | 12,963/s (×3.78) | 19,405/s (×5.66) | 22,201/s (×6.47) |

### Throughput against workers, 20 Mpx

Images per second for 22 loads of the file and their pHash, and the speedup over one worker. A process pool is started before it is timed (the next table has that cost) and keeps one context per process.

| | 1 | 2 | 4 | 8 | 11 |
| --- | --- | --- | --- | --- | --- |
| threads, a context each | 17/s | 33/s (×1.98) | 59/s (×3.52) | 99/s (×5.92) | 120/s (×7.21) |
| ThreadPoolExecutor.map, a context per thread | 17/s | 33/s (×1.97) | 59/s (×3.47) | 99/s (×5.89) | 122/s (×7.23) |
| hash_files(threads=N) | 17/s | 33/s (×1.96) | 59/s (×3.48) | 98/s (×5.82) | 122/s (×7.22) |
| ProcessPoolExecutor (spawn), paths sent | 17/s | 30/s (×1.83) | 58/s (×3.53) | 98/s (×5.92) | 120/s (×7.22) |
| ProcessPoolExecutor (forkserver), paths sent | 17/s | 30/s (×1.81) | 59/s (×3.48) | 98/s (×5.83) | 123/s (×7.32) |
| ProcessPoolExecutor (fork), paths sent | 17/s | 30/s (×1.8) | 59/s (×3.49) | 98/s (×5.85) | 121/s (×7.21) |

### Starting a process pool

A ProcessPoolExecutor of 11 processes, each importing libphash and creating its context, until every one has answered; then shut down.

| | start and stop |
| --- | --- |
| spawn | 136 ms / 147 ms |
| forkserver | 58.9 ms / 62.8 ms |
| fork | 9.94 ms / 11 ms |

### An asyncio loop while hashing, 20 Mpx

How late a task that sleeps 1 ms again and again wakes up while 8 images are hashed: the loop's lag. With the GIL released in C, work handed to a thread leaves the loop responsive.

| | median | p99 | max |
| --- | --- | --- | --- |
| hash() in the coroutine: blocks the loop | 497 ms | 497 ms | 497 ms |
| idle, as long | 0.293 ms | 0.374 ms | 0.47 ms |
| await asyncio.to_thread(hash), one by one | 0.274 ms | 0.346 ms | 0.374 ms |
| asyncio.gather of to_thread(hash) | 0.298 ms | 0.494 ms | 0.494 ms |
| await asyncio.to_thread(hash_files) | 0.297 ms | 1.06 ms | 1.06 ms |

### The batch's progress callback, 400×400

hash_files() of 1000 copies of the file, per image: without a callback and with a progress callback that does nothing. The callback takes the GIL on a worker thread of C for every image.

| | threads=1 | threads=11 |
| --- | --- | --- |
| no callback | 303 µs / 306 µs | 43.7 µs / 44.2 µs |
| progress callback | 293 µs / 301 µs (−10.5 µs, ×0.966) | 44 µs / 45 µs (+315 ns, ×1.01) |

## 5. Starting and installing

### import libphash

A fresh interpreter that imports libphash, against one that imports nothing; -X importtime's cumulative time of the package.

| | wall time | -X importtime, the package |
| --- | --- | --- |
| python -c pass | 14.6 ms / 15.8 ms | — |
| python -c 'import libphash' | 29.2 ms / 30 ms (+14.7 ms, ×2) | 12.2 ms |

### Size

The extension module (libphash and its decoders, linked statically) and, when given, the wheel.

| | bytes |
| --- | --- |
| extension module (_native.abi3.so) | 1.23 MiB |
| the package's .py files | 69 KiB |
