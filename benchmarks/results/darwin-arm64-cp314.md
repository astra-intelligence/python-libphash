## Environment

- **date:** 2026-10-13
- **machine:** Apple M3 Pro, 11 CPUs, 36 GiB
- **os:** macOS-26.6.2-arm64-arm-64bit-Mach-O
- **python:** CPython 3.14.7
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
| C | 232 µs / 237 µs | 56.3 ms / 56.6 ms |
| C through cffi | 231 µs / 235 µs (−876 ns, ×0.996) | 56.2 ms / 56.5 ms (−113 µs, ×0.998) |
| load_file(str) | 232 µs / 244 µs (+83.2 ns, ×1) | 56.2 ms / 56.5 ms (−108 µs, ×0.998) |
| load_file(Path) | 231 µs / 235 µs (−542 ns, ×0.998) | 56.1 ms / 56.4 ms (−160 µs, ×0.997) |
| load(str) | 231 µs / 234 µs (−792 ns, ×0.997) | 56.3 ms / 56.5 ms (−8.58 µs, ×1) |

### Loading encoded bytes

The same JPEG already in memory, in the forms a program holds it.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C | 221 µs / 223 µs | 55.9 ms / 56.4 ms |
| C through cffi | 221 µs / 224 µs (−250 ns, ×0.999) | 55.9 ms / 56.2 ms (+82.2 µs, ×1) |
| load_bytes(bytes) | 221 µs / 223 µs (−41.6 ns, ×1) | 55.9 ms / 56 ms (+44.5 µs, ×1) |
| load_bytes(bytearray) | 221 µs / 225 µs (−125 ns, ×0.999) | 55.9 ms / 56.5 ms (+65.7 µs, ×1) |
| load_bytes(memoryview) | 221 µs / 222 µs (−125 ns, ×0.999) | 55.9 ms / 56.2 ms (+61 µs, ×1) |
| load(bytes) | 221 µs / 223 µs (+250 ns, ×1) | 55.9 ms / 56 ms (+1 µs, ×1) |
| load_fileobj(BytesIO) | 221 µs / 226 µs (+250 ns, ×1) | 55.9 ms / 56.1 ms (+41.4 µs, ×1) |
| load_fileobj(open file), open included | 231 µs / 237 µs (+10.3 µs, ×1.05) | 56.5 ms / 56.7 ms (+622 µs, ×1.01) |
| hash_buffers([bytes]), per item | 292 µs / 301 µs (+70.9 µs, ×1.32) | 58.7 ms / 58.8 ms (+2.82 ms, ×1.05) |

### Loading decoded pixels

The same image decoded (by Pillow, untimed) into 8-bit RGB pixels, in the forms numpy, OpenCV and Pillow hand them over.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C | 9.56 µs / 9.71 µs | 1.12 ms / 1.15 ms |
| C through cffi | 9.79 µs / 10 µs (+229 ns, ×1.02) | 1.12 ms / 1.15 ms (−5.63 µs, ×0.995) |
| numpy, contiguous (no copy) | 11.2 µs / 11.5 µs (+1.65 µs, ×1.17) | 1.12 ms / 1.14 ms (−2 µs, ×0.998) |
| numpy, a crop: rows apart (no copy) | 11.9 µs / 12.1 µs (+2.38 µs, ×1.25) | 1.15 ms / 1.17 ms (+25.4 µs, ×1.02) |
| memoryview with a shape (no copy) | 10.5 µs / 10.6 µs (+896 ns, ×1.09) | 1.12 ms / 1.15 ms (−2.42 µs, ×0.998) |
| numpy BGR, channel_order='bgr' (a copy) | 209 µs / 215 µs (+199 µs, ×21.9) | 27.7 ms / 28.4 ms (+26.5 ms, ×24.6) |
| numpy BGR, bgr[..., ::-1] (a copy) | 1.73 ms / 1.75 ms (+1.72 ms, ×181) | 217 ms / 220 ms (+216 ms, ×194) |
| numpy BGR, np.ascontiguousarray(bgr[..., ::-1]) | 420 µs / 429 µs (+411 µs, ×44) | 52.6 ms / 52.8 ms (+51.5 ms, ×46.8) |
| numpy, one channel (h, w) | 4.75 µs / 4.9 µs (−4.81 µs, ×0.497) | 306 µs / 335 µs (−817 µs, ×0.273) |
| Pillow RGB image, load_pil() | 47.8 µs / 49.5 µs (+38.3 µs, ×5) | 6.54 ms / 6.61 ms (+5.41 ms, ×5.82) |
| Pillow RGB image, np.asarray() then load_pixels() | 49.8 µs / 50.4 µs (+40.2 µs, ×5.2) | 6.55 ms / 6.63 ms (+5.43 ms, ×5.83) |

### One hash of a loaded image, 400×400

Each hash computed again on an image that a first hash prepared: the grayscale image and the area grid are cached in the context, so the 64-bit hashes cost little more than the call itself.

| | C | C through cffi | hash(Algorithm) | hash('name') | its method, ahash() … |
| --- | --- | --- | --- | --- | --- |
| ahash | 375 ns / 458 ns | 500 ns / 542 ns (+125 ns, ×1.33) | 708 ns / 792 ns (+333 ns, ×1.89) | 1.06 µs / 1.13 µs (+687 ns, ×2.83) | 718 ns / 778 ns (+343 ns, ×1.91) |
| dhash | 45.5 µs / 46.1 µs | 46 µs / 47.1 µs (+500 ns, ×1.01) | 46.6 µs / 47.5 µs (+1.04 µs, ×1.02) | 46.9 µs / 48 µs (+1.38 µs, ×1.03) | 46.5 µs / 47.6 µs (+917 ns, ×1.02) |
| phash | 3.46 µs / 3.54 µs | 3.58 µs / 3.62 µs (+125 ns, ×1.04) | 3.79 µs / 3.92 µs (+334 ns, ×1.1) | 4.15 µs / 4.22 µs (+688 ns, ×1.2) | 3.83 µs / 3.87 µs (+369 ns, ×1.11) |
| whash | 792 ns / 833 ns | 839 ns / 856 ns (+47.2 ns, ×1.06) | 1.06 µs / 1.11 µs (+271 ns, ×1.34) | 1.39 µs / 1.43 µs (+600 ns, ×1.76) | 1.07 µs / 1.09 µs (+275 ns, ×1.35) |
| bmh | 792 ns / 917 ns | 875 ns / 937 ns (+83.4 ns, ×1.11) | 1.5 µs / 1.63 µs (+708 ns, ×1.89) | 1.91 µs / 1.99 µs (+1.11 µs, ×2.41) | 1.55 µs / 1.61 µs (+757 ns, ×1.96) |
| mhash | 941 µs / 956 µs | 912 µs / 926 µs (−29 µs, ×0.969) | 913 µs / 927 µs (−27.8 µs, ×0.97) | 913 µs / 931 µs (−28 µs, ×0.97) | 914 µs / 933 µs (−27.1 µs, ×0.971) |
| radial | 584 µs / 590 µs | 584 µs / 591 µs (+583 ns, ×1) | 586 µs / 591 µs (+2.67 µs, ×1) | 586 µs / 589 µs (+2.04 µs, ×1) | 585 µs / 589 µs (+1.71 µs, ×1) |
| color_hash | 128 µs / 132 µs | 129 µs / 130 µs (+375 ns, ×1) | 130 µs / 131 µs (+1.46 µs, ×1.01) | 130 µs / 131 µs (+1.79 µs, ×1.01) | 130 µs / 134 µs (+1.42 µs, ×1.01) |
| color_moments | 244 µs / 244 µs | 226 µs / 243 µs (−17.4 µs, ×0.929) | 244 µs / 245 µs (+500 ns, ×1) | 228 µs / 245 µs (−15.5 µs, ×0.936) | 228 µs / 245 µs (−15.5 µs, ×0.936) |

### Loading and one hash, 400×400

A load of the encoded bytes and the first hash on it, which prepares the grayscale image and the area grid: what one image and one hash cost.

| | C | load_bytes() + hash() |
| --- | --- | --- |
| ahash | 271 µs / 276 µs | 271 µs / 277 µs (+541 ns, ×1) |
| dhash | 279 µs / 285 µs | 279 µs / 283 µs (+167 ns, ×1) |
| phash | 274 µs / 278 µs | 274 µs / 284 µs (+125 ns, ×1) |
| whash | 272 µs / 277 µs | 273 µs / 280 µs (+1.12 µs, ×1) |
| bmh | 271 µs / 275 µs | 274 µs / 284 µs (+3.25 µs, ×1.01) |
| mhash | 1.18 ms / 1.19 ms | 1.15 ms / 1.17 ms (−26.6 µs, ×0.977) |
| radial | 819 µs / 829 µs | 820 µs / 831 µs (+792 ns, ×1) |
| color_hash | 353 µs / 358 µs | 353 µs / 358 µs (+83.4 ns, ×1) |
| color_moments | 466 µs / 472 µs | 467 µs / 480 µs (+833 ns, ×1) |

### One hash of a loaded image, 20 Mpx

Each hash computed again on an image that a first hash prepared: the grayscale image and the area grid are cached in the context, so the 64-bit hashes cost little more than the call itself.

| | C | C through cffi | hash(Algorithm) | hash('name') | its method, ahash() … |
| --- | --- | --- | --- | --- | --- |
| ahash | 375 ns / 458 ns | 458 ns / 583 ns (+83 ns, ×1.22) | 708 ns / 833 ns (+333 ns, ×1.89) | 1.04 µs / 1.12 µs (+666 ns, ×2.78) | 722 ns / 752 ns (+347 ns, ×1.93) |
| dhash | 4.9 ms / 4.94 ms | 4.91 ms / 4.96 ms (+9.46 µs, ×1) | 4.9 ms / 4.96 ms (+3.71 µs, ×1) | 4.91 ms / 4.99 ms (+9.71 µs, ×1) | 4.91 ms / 4.99 ms (+16.7 µs, ×1) |
| phash | 3.46 µs / 3.54 µs | 3.57 µs / 3.62 µs (+117 ns, ×1.03) | 3.79 µs / 3.92 µs (+333 ns, ×1.1) | 4.14 µs / 4.22 µs (+677 ns, ×1.2) | 3.8 µs / 3.86 µs (+340 ns, ×1.1) |
| whash | 875 ns / 958 ns | 946 ns / 976 ns (+71.5 ns, ×1.08) | 1.17 µs / 1.21 µs (+292 ns, ×1.33) | 1.49 µs / 1.54 µs (+617 ns, ×1.7) | 1.18 µs / 1.2 µs (+301 ns, ×1.34) |
| bmh | 750 ns / 792 ns | 818 ns / 845 ns (+68.2 ns, ×1.09) | 1.5 µs / 1.6 µs (+750 ns, ×2) | 1.89 µs / 1.98 µs (+1.14 µs, ×2.51) | 1.5 µs / 1.57 µs (+750 ns, ×2) |
| mhash | 35 ms / 35.2 ms | 31.9 ms / 32.1 ms (−3.08 ms, ×0.912) | 32 ms / 32.1 ms (−3.01 ms, ×0.914) | 31.9 ms / 32.2 ms (−3.02 ms, ×0.914) | 32 ms / 32.1 ms (−3 ms, ×0.914) |
| radial | 46.7 ms / 47.1 ms | 46.7 ms / 47.1 ms (−18.2 µs, ×1) | 46.6 ms / 47.1 ms (−136 µs, ×0.997) | 46.8 ms / 47.2 ms (+94 µs, ×1) | 46.9 ms / 47 ms (+112 µs, ×1) |
| color_hash | 16.6 ms / 16.9 ms | 16.5 ms / 16.7 ms (−34.3 µs, ×0.998) | 16.6 ms / 16.7 ms (−29.5 µs, ×0.998) | 16.5 ms / 16.7 ms (−34 µs, ×0.998) | 16.5 ms / 16.7 ms (−61 µs, ×0.996) |
| color_moments | 30.8 ms / 30.9 ms | 30.6 ms / 30.6 ms (−200 µs, ×0.993) | 30.6 ms / 30.7 ms (−189 µs, ×0.994) | 30.6 ms / 30.7 ms (−194 µs, ×0.994) | 30.5 ms / 30.6 ms (−219 µs, ×0.993) |

### Loading and one hash, 20 Mpx

A load of the encoded bytes and the first hash on it, which prepares the grayscale image and the area grid: what one image and one hash cost.

| | C | load_bytes() + hash() |
| --- | --- | --- |
| ahash | 58.5 ms / 58.7 ms | 58.6 ms / 58.8 ms (+77 µs, ×1) |
| dhash | 62.2 ms / 62.4 ms | 62.2 ms / 62.4 ms (−35.5 µs, ×0.999) |
| phash | 58.6 ms / 58.8 ms | 58.6 ms / 59.5 ms (+64 µs, ×1) |
| whash | 58.5 ms / 58.7 ms | 58.6 ms / 58.7 ms (+110 µs, ×1) |
| bmh | 58.6 ms / 58.8 ms | 58.6 ms / 58.9 ms (+9.96 µs, ×1) |
| mhash | 92.5 ms / 93.4 ms | 89.3 ms / 89.5 ms (−3.2 ms, ×0.965) |
| radial | 104 ms / 105 ms | 104 ms / 108 ms (+235 µs, ×1) |
| color_hash | 72.7 ms / 74.4 ms | 72.5 ms / 72.8 ms (−108 µs, ×0.999) |
| color_moments | 86.8 ms / 87.1 ms | 86.6 ms / 89.3 ms (−184 µs, ×0.998) |

### Several hashes of one load

A load of the encoded bytes and the four 64-bit hashes (or all nine). hashes() computes the 64-bit ones in one ph_compute_multi() call, which shares their work on the full image.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C: ph_compute_multi() | 322 µs / 327 µs | 63.5 ms / 63.7 ms |
| C: four ph_compute_*() | 321 µs / 327 µs (−792 ns, ×0.998) | 63.5 ms / 63.8 ms (−6.83 µs, ×1) |
| hashes(4 × 64-bit) | 325 µs / 331 µs (+3.42 µs, ×1.01) | 63.5 ms / 63.9 ms (+23.1 µs, ×1) |
| hash() four times | 325 µs / 332 µs (+3.08 µs, ×1.01) | 63.5 ms / 63.8 ms (+52.2 µs, ×1) |
| hashes(all 9) | 2.21 ms / 2.24 ms (+1.89 ms, ×6.87) | 190 ms / 191 ms (+126 ms, ×2.99) |
| hash() nine times | 2.21 ms / 2.24 ms (+1.89 ms, ×6.86) | 190 ms / 193 ms (+126 ms, ×2.99) |
| hash(path) four times, a load each | 1.18 ms / 1.2 ms (+854 µs, ×3.65) | 241 ms / 241 ms (+177 ms, ×3.79) |

### From a file to its pHash

Per image: a new context for each, one context kept, or a batch on one thread (threads=1, the calling thread) of 64 copies of the file.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C: a new context | 285 µs / 290 µs | 59.1 ms / 59.3 ms |
| C: one context | 284 µs / 289 µs (−1.58 µs, ×0.994) | 58.9 ms / 59.1 ms (−200 µs, ×0.997) |
| C: ph_hash_files(), 1 thread | 286 µs / 288 µs (+1.01 µs, ×1) | 59.3 ms / 59.9 ms (+214 µs, ×1) |
| hash(path): a new context | 277 µs / 299 µs (−7.92 µs, ×0.972) | 59 ms / 59.3 ms (−62.8 µs, ×0.999) |
| ImageContext, kept | 266 µs / 289 µs (−18.7 µs, ×0.935) | 59 ms / 59.2 ms (−110 µs, ×0.998) |
| hash_files(threads=1) | 291 µs / 299 µs (+6.03 µs, ×1.02) | 59.2 ms / 59.8 ms (+149 µs, ×1) |

### Comparing two hashes

One comparison of two hashes of two similar photographs (photo.jpeg and photo_copy.jpeg), and the conversions of a hash.

| | per call |
| --- | --- |
| 64-bit Hamming: C ph_hamming_distance() | 0.739 ns / 0.794 ns |
| 64-bit Hamming: cffi | 72.8 ns / 93.7 ns |
| 64-bit Hamming: hamming_distance() | 219 ns / 250 ns |
| 64-bit Hamming: (a ^ b).bit_count() | 30.3 ns / 37.9 ns |
| 64-bit similarity() | 229 ns / 250 ns |
| bmh Hamming: C | 3.21 ns / 3.45 ns |
| bmh Hamming: Digest | 791 ns / 875 ns |
| color_moments L2: C | 5.42 ns / 5.83 ns |
| color_moments L2: Digest | 823 ns / 885 ns |
| radial radial: C | 86.3 ns / 88 ns |
| radial radial: Digest | 979 ns / 1.04 µs |
| color_hash histogram: C | 49.5 ns / 53.2 ns |
| color_hash histogram: Digest | 950 ns / 1.01 µs |
| bmh similarity: C | 3.7 ns / 3.98 ns |
| bmh similarity: Digest | 847 ns / 917 ns |
| Digest(bytes, kind), 72 bytes | 291 ns / 333 ns |
| Digest.hex(), 72 bytes | 594 ns / 646 ns |
| Digest.from_hex(), 72 bytes | 770 ns / 854 ns |
| hash_to_hex(int) | 333 ns / 375 ns |
| f'{h:016x}' | 83.2 ns / 93.8 ns |

## 4. Parallelism

Subinterpreters: `import libphash` in an interpreter of `concurrent.interpreters.create()` gives `ImportError: module _native does not support loading in subinterpreters`.

### Throughput against workers, 400×400

Images per second for 1000 loads of the file and their pHash, and the speedup over one worker. A process pool is started before it is timed (the next table has that cost) and keeps one context per process.

| | 1 | 2 | 4 | 8 | 11 |
| --- | --- | --- | --- | --- | --- |
| threads, a context each | 3,444/s | 6,802/s (×1.97) | 13,252/s (×3.85) | 18,979/s (×5.51) | 21,387/s (×6.21) |
| threads, one shared context | 3,437/s | 3,286/s (×0.956) | 3,429/s (×0.998) | 3,554/s (×1.03) | 3,559/s (×1.04) |
| ThreadPoolExecutor.map, a context per thread | 3,322/s | 6,384/s (×1.92) | 12,124/s (×3.65) | 18,659/s (×5.62) | 21,399/s (×6.44) |
| hash_files(threads=N) | 3,409/s | 6,739/s (×1.98) | 13,124/s (×3.85) | 19,764/s (×5.8) | 23,024/s (×6.75) |
| ProcessPoolExecutor (spawn), paths sent | 3,443/s | 6,731/s (×1.96) | 12,807/s (×3.72) | 18,692/s (×5.43) | 21,409/s (×6.22) |
| ProcessPoolExecutor (spawn), bytes sent | 3,569/s | 7,021/s (×1.97) | 13,343/s (×3.74) | 18,980/s (×5.32) | 22,305/s (×6.25) |
| ProcessPoolExecutor (forkserver), paths sent | 2,751/s | 5,456/s (×1.98) | 10,422/s (×3.79) | 16,120/s (×5.86) | 18,973/s (×6.9) |
| ProcessPoolExecutor (fork), paths sent | 3,411/s | 6,768/s (×1.98) | 12,954/s (×3.8) | 19,245/s (×5.64) | 22,272/s (×6.53) |

### Throughput against workers, 20 Mpx

Images per second for 22 loads of the file and their pHash, and the speedup over one worker. A process pool is started before it is timed (the next table has that cost) and keeps one context per process.

| | 1 | 2 | 4 | 8 | 11 |
| --- | --- | --- | --- | --- | --- |
| threads, a context each | 17/s | 33/s (×1.96) | 59/s (×3.48) | 97/s (×5.77) | 123/s (×7.28) |
| ThreadPoolExecutor.map, a context per thread | 17/s | 33/s (×1.96) | 58/s (×3.45) | 99/s (×5.84) | 124/s (×7.33) |
| hash_files(threads=N) | 17/s | 33/s (×1.97) | 59/s (×3.49) | 99/s (×5.93) | 123/s (×7.32) |
| ProcessPoolExecutor (spawn), paths sent | 17/s | 30/s (×1.78) | 58/s (×3.46) | 96/s (×5.68) | 119/s (×7.06) |
| ProcessPoolExecutor (forkserver), paths sent | 15/s | 27/s (×1.8) | 52/s (×3.48) | 90/s (×6) | 111/s (×7.4) |
| ProcessPoolExecutor (fork), paths sent | 17/s | 30/s (×1.81) | 59/s (×3.48) | 99/s (×5.87) | 121/s (×7.2) |

### Starting a process pool

A ProcessPoolExecutor of 11 processes, each importing libphash and creating its context, until every one has answered; then shut down.

| | start and stop |
| --- | --- |
| spawn | 123 ms / 137 ms |
| forkserver | 61.3 ms / 66.4 ms |
| fork | 10 ms / 11.2 ms |

### An asyncio loop while hashing, 20 Mpx

How late a task that sleeps 1 ms again and again wakes up while 8 images are hashed: the loop's lag. With the GIL released in C, work handed to a thread leaves the loop responsive.

| | median | p99 | max |
| --- | --- | --- | --- |
| hash() in the coroutine: blocks the loop | 480 ms | 480 ms | 480 ms |
| idle, as long | 0.295 ms | 0.38 ms | 0.462 ms |
| await asyncio.to_thread(hash), one by one | 0.272 ms | 0.298 ms | 0.399 ms |
| asyncio.gather of to_thread(hash) | 0.29 ms | 0.938 ms | 0.938 ms |
| await asyncio.to_thread(hash_files) | 0.292 ms | 0.393 ms | 0.393 ms |

### The batch's progress callback, 400×400

hash_files() of 1000 copies of the file, per image: without a callback and with a progress callback that does nothing. The callback takes the GIL on a worker thread of C for every image.

| | threads=1 | threads=11 |
| --- | --- | --- |
| no callback | 292 µs / 296 µs | 43.5 µs / 43.9 µs |
| progress callback | 293 µs / 294 µs (+1.2 µs, ×1) | 44 µs / 50.6 µs (+549 ns, ×1.01) |

## 5. Starting and installing

### import libphash

A fresh interpreter that imports libphash, against one that imports nothing; -X importtime's cumulative time of the package.

| | wall time | -X importtime, the package |
| --- | --- | --- |
| python -c pass | 13.9 ms / 14.9 ms | — |
| python -c 'import libphash' | 27.8 ms / 28.4 ms (+13.9 ms, ×2) | 11.3 ms |

### Size

The extension module (libphash and its decoders, linked statically) and, when given, the wheel.

| | bytes |
| --- | --- |
| extension module (_native.abi3.so) | 1.23 MiB |
| the package's .py files | 69 KiB |
