# Performance

The work is done in C: decoding and hashing an image costs the same from Python as from
C, and what Python adds is a fraction of a microsecond per call, which disappears next to
the decode. What decides the speed is how the work is arranged.

Measured on an Apple M3 Pro (11 CPUs), CPython 3.12, with a 400×400 JPEG and a
20-megapixel one (`benchmarks/` in the repository runs the same measurements anywhere):

| Task | Fastest way | What to avoid | Measured |
|---|---|---|---|
| loading | a path, bytes, or a numpy array that is contiguous or a crop of one | reading a file into Python first when you have its path | 0.5 KiB against 5.75 MiB of Python memory (20 Mpx) |
| OpenCV frames (BGR) | `load_pixels(frame, channel_order="bgr")` | `frame[..., ::-1]` | 28 ms against 233 ms (20 Mpx) |
| Pillow | give libphash the file or the bytes | `load_pil()` on a large image | `load_pil()` costs 5.6 ms and 114 MiB more (20 Mpx) |
| several hashes of one image | one load, then `hashes()` | loading once per hash | 0.33 ms against 1.12 ms |
| many files | `hash_files(threads=0)` | one context shared by threads | ×6.9 against ×0.96 |
| asyncio | `asyncio.to_thread()` | hashing in the coroutine | event loop blocked 1 ms against 497 ms |
| one query against many hashes | numpy `bitwise_count` over a `uint64` array | `ph.hamming_distance()` in a loop | 0.3 ns against 245 ns per hash |
| comparing pairs in a Python loop | `(a ^ b).bit_count()` | `ph.hamming_distance()` | 33 ns against 229 ns |
| large images | one context per thread; bound `threads` and `max_pixels` | many contexts holding images | 176 MiB per context holding 20 Mpx |

## What Python adds

| Operation (400×400 JPEG) | C | C through cffi | The API |
|---|---|---|---|
| aHash of a loaded image | 375 ns | 500 ns | 791 ns |
| load from bytes and hash | 279 µs | | 275 µs |

A call through the API costs 0.3 to 0.4 µs more than the bare C function (checking the
arguments, the context's lock, building the result); an algorithm given by name adds
about 0.35 µs. Against a decode of hundreds of microseconds this is within the noise:
from an image to its hash, Python costs nothing measurable.

## Parallelism

`hash_files()` reaches ×6.8 on 11 CPUs (22,900 images of 400×400 a second); threads with
their own contexts and process pools reach ×6.3 to ×6.5, and at 20 megapixels every one
of them ×7.2. On free-threaded 3.14t the numbers are the same: the GIL, released by every
call into C, was never the limit. The module does not load in subinterpreters (cffi's
modules use single-phase initialization). `import libphash` takes 14.7 ms.

## The context and the GIL

Each call into C releases the GIL, so threads with their own contexts hash on as many
CPUs as there are threads. A context shared by threads serializes them on its lock: safe,
but no faster than one thread. [Threads and processes](concurrency.md) has the rules.

## Memory

Bytes, `memoryview`s and arrays whose rows are the only gaps are read in place. A decoded
image takes 3 bytes per pixel (1 in grayscale) in its context; a batch holds one image
per worker, about 4 bytes per pixel of the largest image plus its file. `max_pixels`
(256 Mi pixels by default) bounds what one load can take.

## The C side

How fast each algorithm is, and what the decoders cost, is measured on libphash's
[Performance](https://gudoshnikovn.github.io/libphash/guide/performance/) page: the
numbers there are the numbers here, plus the fraction above.
