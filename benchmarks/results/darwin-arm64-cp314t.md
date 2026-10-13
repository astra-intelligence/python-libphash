## Environment

- **date:** 2026-10-13
- **machine:** Apple M3 Pro, 11 CPUs, 36 GiB
- **os:** macOS-26.6.2-arm64-arm-64bit-Mach-O
- **python:** CPython 3.14.7 free-threaded (GIL off)
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
| C | 233 µs / 240 µs | 56.1 ms / 56.4 ms |
| C through cffi | 234 µs / 243 µs (+750 ns, ×1) | 56.3 ms / 56.6 ms (+157 µs, ×1) |
| load_file(str) | 233 µs / 242 µs (+583 ns, ×1) | 56.1 ms / 56.5 ms (−57.3 µs, ×0.999) |
| load_file(Path) | 222 µs / 238 µs (−11.2 µs, ×0.952) | 56.5 ms / 58 ms (+407 µs, ×1.01) |
| load(str) | 233 µs / 240 µs (−84.2 ns, ×1) | 56.1 ms / 56.8 ms (+5.17 µs, ×1) |

### Loading encoded bytes

The same JPEG already in memory, in the forms a program holds it.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C | 223 µs / 225 µs | 56 ms / 56.1 ms |
| C through cffi | 223 µs / 224 µs (−208 ns, ×0.999) | 55.7 ms / 56.3 ms (−244 µs, ×0.996) |
| load_bytes(bytes) | 222 µs / 235 µs (−667 ns, ×0.997) | 55.8 ms / 56 ms (−115 µs, ×0.998) |
| load_bytes(bytearray) | 226 µs / 231 µs (+2.67 µs, ×1.01) | 55.9 ms / 56 ms (−81.9 µs, ×0.999) |
| load_bytes(memoryview) | 223 µs / 231 µs (+83.2 ns, ×1) | 55.8 ms / 56 ms (−173 µs, ×0.997) |
| load(bytes) | 222 µs / 225 µs (−958 ns, ×0.996) | 56.2 ms / 57.5 ms (+232 µs, ×1) |
| load_fileobj(BytesIO) | 224 µs / 224 µs (+708 ns, ×1) | 55.8 ms / 56 ms (−213 µs, ×0.996) |
| load_fileobj(open file), open included | 234 µs / 238 µs (+11 µs, ×1.05) | 56.4 ms / 56.6 ms (+454 µs, ×1.01) |
| hash_buffers([bytes]), per item | 293 µs / 302 µs (+70.3 µs, ×1.32) | 58.7 ms / 59.1 ms (+2.76 ms, ×1.05) |

### Loading decoded pixels

The same image decoded (by Pillow, untimed) into 8-bit RGB pixels, in the forms numpy, OpenCV and Pillow hand them over.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C | 9.56 µs / 9.77 µs | 1.11 ms / 1.14 ms |
| C through cffi | 9.83 µs / 10.2 µs (+272 ns, ×1.03) | 1.13 ms / 1.15 ms (+19.5 µs, ×1.02) |
| numpy, contiguous (no copy) | 11.4 µs / 11.6 µs (+1.81 µs, ×1.19) | 1.14 ms / 1.17 ms (+24.2 µs, ×1.02) |
| numpy, a crop: rows apart (no copy) | 12.1 µs / 12.2 µs (+2.52 µs, ×1.26) | 1.15 ms / 1.17 ms (+36.7 µs, ×1.03) |
| memoryview with a shape (no copy) | 10.6 µs / 11.1 µs (+1.04 µs, ×1.11) | 1.13 ms / 1.15 ms (+20.4 µs, ×1.02) |
| numpy BGR, channel_order='bgr' (a copy) | 209 µs / 216 µs (+199 µs, ×21.8) | 27.8 ms / 28.3 ms (+26.7 ms, ×25) |
| numpy BGR, bgr[..., ::-1] (a copy) | 1.78 ms / 1.8 ms (+1.77 ms, ×186) | 223 ms / 223 ms (+222 ms, ×200) |
| numpy BGR, np.ascontiguousarray(bgr[..., ::-1]) | 420 µs / 428 µs (+411 µs, ×44) | 52.6 ms / 53.3 ms (+51.5 ms, ×47.2) |
| numpy, one channel (h, w) | 4.89 µs / 5.11 µs (−4.67 µs, ×0.511) | 317 µs / 343 µs (−796 µs, ×0.285) |
| Pillow RGB image, load_pil() | 47.2 µs / 48.1 µs (+37.6 µs, ×4.94) | 6.74 ms / 6.97 ms (+5.63 ms, ×6.05) |
| Pillow RGB image, np.asarray() then load_pixels() | 49.3 µs / 50.1 µs (+39.7 µs, ×5.15) | 6.56 ms / 6.7 ms (+5.45 ms, ×5.9) |

### One hash of a loaded image, 400×400

Each hash computed again on an image that a first hash prepared: the grayscale image and the area grid are cached in the context, so the 64-bit hashes cost little more than the call itself.

| | C | C through cffi | hash(Algorithm) | hash('name') | its method, ahash() … |
| --- | --- | --- | --- | --- | --- |
| ahash | 375 ns / 458 ns | 500 ns / 583 ns (+125 ns, ×1.33) | 708 ns / 833 ns (+333 ns, ×1.89) | 1.08 µs / 1.17 µs (+709 ns, ×2.89) | 750 ns / 785 ns (+375 ns, ×2) |
| dhash | 45.7 µs / 46.3 µs | 45.7 µs / 46.1 µs (−0.349 ns, ×1) | 46.2 µs / 46.5 µs (+459 ns, ×1.01) | 46.7 µs / 48 µs (+1000 ns, ×1.02) | 46.2 µs / 47.3 µs (+459 ns, ×1.01) |
| phash | 3.46 µs / 3.54 µs | 3.57 µs / 3.62 µs (+108 ns, ×1.03) | 3.79 µs / 3.92 µs (+334 ns, ×1.1) | 4.15 µs / 4.24 µs (+688 ns, ×1.2) | 3.83 µs / 3.87 µs (+369 ns, ×1.11) |
| whash | 792 ns / 833 ns | 900 ns / 928 ns (+108 ns, ×1.14) | 1.15 µs / 1.19 µs (+354 ns, ×1.45) | 1.49 µs / 1.54 µs (+700 ns, ×1.88) | 1.15 µs / 1.18 µs (+358 ns, ×1.45) |
| bmh | 792 ns / 917 ns | 910 ns / 1000 ns (+118 ns, ×1.15) | 1.65 µs / 1.77 µs (+854 ns, ×2.08) | 2.05 µs / 2.2 µs (+1.26 µs, ×2.59) | 1.67 µs / 1.78 µs (+882 ns, ×2.11) |
| mhash | 943 µs / 958 µs | 911 µs / 925 µs (−32 µs, ×0.966) | 911 µs / 924 µs (−31.7 µs, ×0.966) | 911 µs / 928 µs (−31.3 µs, ×0.967) | 911 µs / 925 µs (−32.1 µs, ×0.966) |
| radial | 583 µs / 589 µs | 585 µs / 599 µs (+1.5 µs, ×1) | 588 µs / 603 µs (+4.83 µs, ×1.01) | 588 µs / 599 µs (+4.88 µs, ×1.01) | 587 µs / 596 µs (+4.13 µs, ×1.01) |
| color_hash | 129 µs / 131 µs | 129 µs / 131 µs (+334 ns, ×1) | 130 µs / 131 µs (+1.5 µs, ×1.01) | 130 µs / 134 µs (+1.96 µs, ×1.02) | 130 µs / 134 µs (+1.46 µs, ×1.01) |
| color_moments | 244 µs / 249 µs | 244 µs / 245 µs (+292 ns, ×1) | 246 µs / 247 µs (+2.17 µs, ×1.01) | 246 µs / 247 µs (+2.75 µs, ×1.01) | 246 µs / 252 µs (+2.25 µs, ×1.01) |

### Loading and one hash, 400×400

A load of the encoded bytes and the first hash on it, which prepares the grayscale image and the area grid: what one image and one hash cost.

| | C | load_bytes() + hash() |
| --- | --- | --- |
| ahash | 270 µs / 275 µs | 274 µs / 284 µs (+3.75 µs, ×1.01) |
| dhash | 278 µs / 281 µs | 279 µs / 285 µs (+1.37 µs, ×1) |
| phash | 273 µs / 275 µs | 275 µs / 282 µs (+2.62 µs, ×1.01) |
| whash | 270 µs / 277 µs | 274 µs / 280 µs (+3.88 µs, ×1.01) |
| bmh | 271 µs / 278 µs | 273 µs / 284 µs (+1.96 µs, ×1.01) |
| mhash | 1.18 ms / 1.19 ms | 1.15 ms / 1.16 ms (−26.8 µs, ×0.977) |
| radial | 822 µs / 846 µs | 823 µs / 836 µs (+875 ns, ×1) |
| color_hash | 353 µs / 366 µs | 354 µs / 359 µs (+1.08 µs, ×1) |
| color_moments | 466 µs / 474 µs | 472 µs / 480 µs (+6.38 µs, ×1.01) |

### One hash of a loaded image, 20 Mpx

Each hash computed again on an image that a first hash prepared: the grayscale image and the area grid are cached in the context, so the 64-bit hashes cost little more than the call itself.

| | C | C through cffi | hash(Algorithm) | hash('name') | its method, ahash() … |
| --- | --- | --- | --- | --- | --- |
| ahash | 417 ns / 458 ns | 500 ns / 583 ns (+83.4 ns, ×1.2) | 750 ns / 833 ns (+333 ns, ×1.8) | 1.08 µs / 1.14 µs (+667 ns, ×2.6) | 754 ns / 783 ns (+338 ns, ×1.81) |
| dhash | 4.92 ms / 5.02 ms | 4.91 ms / 5.13 ms (−12.8 µs, ×0.997) | 5 ms / 5.08 ms (+77 µs, ×1.02) | 4.9 ms / 4.96 ms (−17.1 µs, ×0.997) | 4.89 ms / 4.95 ms (−27.4 µs, ×0.994) |
| phash | 3.46 µs / 3.54 µs | 3.32 µs / 3.59 µs (−133 ns, ×0.961) | 3.79 µs / 3.92 µs (+333 ns, ×1.1) | 4.16 µs / 4.23 µs (+698 ns, ×1.2) | 3.8 µs / 3.92 µs (+342 ns, ×1.1) |
| whash | 875 ns / 958 ns | 997 ns / 1.01 µs (+122 ns, ×1.14) | 1.24 µs / 1.27 µs (+361 ns, ×1.41) | 1.58 µs / 1.68 µs (+708 ns, ×1.81) | 1.25 µs / 1.28 µs (+375 ns, ×1.43) |
| bmh | 708 ns / 792 ns | 887 ns / 923 ns (+179 ns, ×1.25) | 1.65 µs / 1.77 µs (+938 ns, ×2.32) | 2.09 µs / 2.21 µs (+1.39 µs, ×2.96) | 1.64 µs / 1.73 µs (+933 ns, ×2.32) |
| mhash | 35.1 ms / 35.3 ms | 31.9 ms / 32.4 ms (−3.14 ms, ×0.911) | 31.9 ms / 32.1 ms (−3.13 ms, ×0.911) | 31.9 ms / 32.2 ms (−3.17 ms, ×0.91) | 31.9 ms / 32.2 ms (−3.18 ms, ×0.909) |
| radial | 46.7 ms / 47 ms | 46.7 ms / 47 ms (−32.3 µs, ×0.999) | 46.6 ms / 47.1 ms (−118 µs, ×0.997) | 46.6 ms / 46.9 ms (−114 µs, ×0.998) | 46.7 ms / 47.2 ms (−25.3 µs, ×0.999) |
| color_hash | 16.6 ms / 16.7 ms | 16.5 ms / 16.7 ms (−71.8 µs, ×0.996) | 16.5 ms / 16.7 ms (−20.1 µs, ×0.999) | 16.6 ms / 16.7 ms (−7.5 µs, ×1) | 16.6 ms / 16.7 ms (−6.42 µs, ×1) |
| color_moments | 30.7 ms / 30.9 ms | 30.8 ms / 30.9 ms (+103 µs, ×1) | 30.8 ms / 30.9 ms (+131 µs, ×1) | 30.6 ms / 30.9 ms (−14.6 µs, ×1) | 30.7 ms / 30.9 ms (−4.08 µs, ×1) |

### Loading and one hash, 20 Mpx

A load of the encoded bytes and the first hash on it, which prepares the grayscale image and the area grid: what one image and one hash cost.

| | C | load_bytes() + hash() |
| --- | --- | --- |
| ahash | 59.2 ms / 60.2 ms | 58.5 ms / 58.8 ms (−636 µs, ×0.989) |
| dhash | 62.2 ms / 62.4 ms | 62.2 ms / 62.3 ms (−10.3 µs, ×1) |
| phash | 58.6 ms / 59.1 ms | 58.6 ms / 59.3 ms (−12.4 µs, ×1) |
| whash | 58.6 ms / 58.7 ms | 58.6 ms / 58.7 ms (−25.4 µs, ×1) |
| bmh | 58.5 ms / 58.7 ms | 58.6 ms / 58.8 ms (+21.5 µs, ×1) |
| mhash | 92.7 ms / 93 ms | 89.4 ms / 90.1 ms (−3.31 ms, ×0.964) |
| radial | 106 ms / 108 ms | 104 ms / 104 ms (−2.37 ms, ×0.978) |
| color_hash | 72.6 ms / 72.7 ms | 72.6 ms / 73.6 ms (+35.2 µs, ×1) |
| color_moments | 86.8 ms / 86.9 ms | 86.7 ms / 87 ms (−96.1 µs, ×0.999) |

### Several hashes of one load

A load of the encoded bytes and the four 64-bit hashes (or all nine). hashes() computes the 64-bit ones in one ph_compute_multi() call, which shares their work on the full image.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C: ph_compute_multi() | 308 µs / 326 µs | 63.5 ms / 63.7 ms |
| C: four ph_compute_*() | 321 µs / 334 µs (+12.9 µs, ×1.04) | 63.5 ms / 63.8 ms (+72.4 µs, ×1) |
| hashes(4 × 64-bit) | 324 µs / 327 µs (+15.6 µs, ×1.05) | 63.5 ms / 63.9 ms (+12.3 µs, ×1) |
| hash() four times | 323 µs / 330 µs (+15 µs, ×1.05) | 63.5 ms / 63.8 ms (+13.5 µs, ×1) |
| hashes(all 9) | 2.21 ms / 2.26 ms (+1.9 ms, ×7.16) | 190 ms / 191 ms (+126 ms, ×2.99) |
| hash() nine times | 2.21 ms / 2.24 ms (+1.9 ms, ×7.17) | 190 ms / 193 ms (+127 ms, ×3) |
| hash(path) four times, a load each | 1.18 ms / 1.2 ms (+876 µs, ×3.84) | 240 ms / 242 ms (+177 ms, ×3.78) |

### From a file to its pHash

Per image: a new context for each, one context kept, or a batch on one thread (threads=1, the calling thread) of 64 copies of the file.

| | 400×400 | 20 Mpx |
| --- | --- | --- |
| C: a new context | 285 µs / 294 µs | 58.8 ms / 59.2 ms |
| C: one context | 284 µs / 292 µs (−333 ns, ×0.999) | 59 ms / 59.4 ms (+155 µs, ×1) |
| C: ph_hash_files(), 1 thread | 288 µs / 299 µs (+2.98 µs, ×1.01) | 59.2 ms / 59.4 ms (+407 µs, ×1.01) |
| hash(path): a new context | 278 µs / 299 µs (−6.54 µs, ×0.977) | 58.8 ms / 59.4 ms (−12.4 µs, ×1) |
| ImageContext, kept | 271 µs / 290 µs (−13.8 µs, ×0.951) | 59 ms / 59.3 ms (+164 µs, ×1) |
| hash_files(threads=1) | 290 µs / 294 µs (+4.78 µs, ×1.02) | 59.2 ms / 59.4 ms (+391 µs, ×1.01) |

### Comparing two hashes

One comparison of two hashes of two similar photographs (photo.jpeg and photo_copy.jpeg), and the conversions of a hash.

| | per call |
| --- | --- |
| 64-bit Hamming: C ph_hamming_distance() | 0.792 ns / 0.795 ns |
| 64-bit Hamming: cffi | 69.3 ns / 97 ns |
| 64-bit Hamming: hamming_distance() | 219 ns / 250 ns |
| 64-bit Hamming: (a ^ b).bit_count() | 34.1 ns / 41.6 ns |
| 64-bit similarity() | 229 ns / 260 ns |
| bmh Hamming: C | 3.21 ns / 3.45 ns |
| bmh Hamming: Digest | 875 ns / 958 ns |
| color_moments L2: C | 5.42 ns / 5.83 ns |
| color_moments L2: Digest | 883 ns / 933 ns |
| radial radial: C | 86.3 ns / 86.4 ns |
| radial radial: Digest | 1.03 µs / 1.1 µs |
| color_hash histogram: C | 52.8 ns / 53.2 ns |
| color_hash histogram: Digest | 1.01 µs / 1.07 µs |
| bmh similarity: C | 3.7 ns / 3.98 ns |
| bmh similarity: Digest | 917 ns / 986 ns |
| Digest(bytes, kind), 72 bytes | 306 ns / 347 ns |
| Digest.hex(), 72 bytes | 639 ns / 722 ns |
| Digest.from_hex(), 72 bytes | 833 ns / 917 ns |
| hash_to_hex(int) | 347 ns / 403 ns |
| f'{h:016x}' | 93.7 ns / 114 ns |

## 4. Parallelism

Subinterpreters: `import libphash` in an interpreter of `concurrent.interpreters.create()` gives `ImportError: module _native does not support loading in subinterpreters`.

### Throughput against workers, 400×400

Images per second for 1000 loads of the file and their pHash, and the speedup over one worker. A process pool is started before it is timed (the next table has that cost) and keeps one context per process.

| | 1 | 2 | 4 | 8 | 11 |
| --- | --- | --- | --- | --- | --- |
| threads, a context each | 3,403/s | 6,757/s (×1.99) | 13,182/s (×3.87) | 18,608/s (×5.47) | 20,472/s (×6.02) |
| threads, one shared context | 3,427/s | 3,286/s (×0.959) | 3,397/s (×0.991) | 3,538/s (×1.03) | 3,518/s (×1.03) |
| ThreadPoolExecutor.map, a context per thread | 3,328/s | 6,474/s (×1.95) | 12,437/s (×3.74) | 19,191/s (×5.77) | 22,449/s (×6.75) |
| hash_files(threads=N) | 3,432/s | 6,712/s (×1.96) | 13,083/s (×3.81) | 19,510/s (×5.68) | 22,941/s (×6.68) |
| ProcessPoolExecutor (spawn), paths sent | 3,412/s | 6,678/s (×1.96) | 12,846/s (×3.77) | 18,535/s (×5.43) | 21,251/s (×6.23) |
| ProcessPoolExecutor (spawn), bytes sent | 3,580/s | 6,968/s (×1.95) | 13,255/s (×3.7) | 19,749/s (×5.52) | 22,567/s (×6.3) |
| ProcessPoolExecutor (forkserver), paths sent | 3,318/s | 6,500/s (×1.96) | 12,374/s (×3.73) | 18,138/s (×5.47) | 20,644/s (×6.22) |
| ProcessPoolExecutor (fork), paths sent | 3,432/s | 6,767/s (×1.97) | 12,975/s (×3.78) | 18,530/s (×5.4) | 22,381/s (×6.52) |

### Throughput against workers, 20 Mpx

Images per second for 22 loads of the file and their pHash, and the speedup over one worker. A process pool is started before it is timed (the next table has that cost) and keeps one context per process.

| | 1 | 2 | 4 | 8 | 11 |
| --- | --- | --- | --- | --- | --- |
| threads, a context each | 17/s | 33/s (×1.96) | 59/s (×3.47) | 99/s (×5.85) | 121/s (×7.17) |
| ThreadPoolExecutor.map, a context per thread | 17/s | 33/s (×1.95) | 59/s (×3.49) | 99/s (×5.84) | 108/s (×6.4) |
| hash_files(threads=N) | 17/s | 33/s (×1.96) | 59/s (×3.48) | 99/s (×5.9) | 122/s (×7.2) |
| ProcessPoolExecutor (spawn), paths sent | 17/s | 30/s (×1.81) | 59/s (×3.49) | 97/s (×5.76) | 122/s (×7.23) |
| ProcessPoolExecutor (forkserver), paths sent | 16/s | 29/s (×1.81) | 55/s (×3.48) | 94/s (×5.9) | 119/s (×7.47) |
| ProcessPoolExecutor (fork), paths sent | 17/s | 30/s (×1.81) | 58/s (×3.45) | 99/s (×5.86) | 118/s (×6.99) |

### Starting a process pool

A ProcessPoolExecutor of 11 processes, each importing libphash and creating its context, until every one has answered; then shut down.

| | start and stop |
| --- | --- |
| spawn | 150 ms / 156 ms |
| forkserver | 66.8 ms / 71.3 ms |
| fork | 20.3 ms / 22 ms |

### An asyncio loop while hashing, 20 Mpx

How late a task that sleeps 1 ms again and again wakes up while 8 images are hashed: the loop's lag. With the GIL released in C, work handed to a thread leaves the loop responsive.

| | median | p99 | max |
| --- | --- | --- | --- |
| hash() in the coroutine: blocks the loop | 479 ms | 479 ms | 479 ms |
| idle, as long | 0.309 ms | 0.491 ms | 1.22 ms |
| await asyncio.to_thread(hash), one by one | 0.273 ms | 0.331 ms | 0.358 ms |
| asyncio.gather of to_thread(hash) | 0.362 ms | 5.45 ms | 5.45 ms |
| await asyncio.to_thread(hash_files) | 0.337 ms | 2.75 ms | 2.75 ms |

### The batch's progress callback, 400×400

hash_files() of 1000 copies of the file, per image: without a callback and with a progress callback that does nothing. The callback takes the GIL on a worker thread of C for every image.

| | threads=1 | threads=11 |
| --- | --- | --- |
| no callback | 295 µs / 297 µs | 43.9 µs / 44.3 µs |
| progress callback | 291 µs / 293 µs (−4.1 µs, ×0.986) | 43.9 µs / 44.3 µs (−10.3 ns, ×1) |

## 5. Starting and installing

### import libphash

A fresh interpreter that imports libphash, against one that imports nothing; -X importtime's cumulative time of the package.

| | wall time | -X importtime, the package |
| --- | --- | --- |
| python -c pass | 14.9 ms / 15.4 ms | — |
| python -c 'import libphash' | 30.1 ms / 30.8 ms (+15.2 ms, ×2.02) | 12.3 ms |

### Size

The extension module (libphash and its decoders, linked statically) and, when given, the wheel.

| | bytes |
| --- | --- |
| extension module (_native.cpython-314t-darwin.so) | 1.23 MiB |
| the package's .py files | 69 KiB |
