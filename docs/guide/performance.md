# Performance

The work is done in C: decoding and hashing an image costs the same from Python as from
C, and what Python adds is a fraction of a microsecond per call, which disappears next to
the decode. What decides the speed is how the work is arranged.

| Task | Fastest way | What to avoid |
|---|---|---|
| several hashes of one image | `ctx.hashes(...)` on one load | loading the image once per hash |
| many images, one by one | one `ImageContext`, reused | a new context per image (`ph.hash()` in a loop) |
| many files | `hash_files()`: all CPUs, no Python per item | a Python loop on one thread |
| pixels from numpy | a C-ordered RGB array, or a crop of one | BGR or reversed channels, which are copied |
| one query against many hashes | numpy `bitwise_count` over a `uint64` array | a Python loop over `int`s |
| parallel work in Python | threads, each with its own context | one context shared by busy threads |
| memory on large images | `Config.max_pixels`, fewer batch threads | unbounded images from outside |

## What Python adds

Measured on an Apple M3 Pro with a 400×400 JPEG:

| Operation | Through the API | C through cffi |
|---|---|---|
| `ctx.ahash()` on a loaded image | 0.87 µs | 0.58 µs |
| loading the JPEG from bytes | 234 µs | 234 µs |
| `ph.hash()` with a new context | 306 µs | |
| the same with a reused context | 291 µs | |

A call through the API costs about 0.3 µs more than the bare C function: checking the
arguments, the context's lock, building the result. Against a decode of hundreds of
microseconds it is under a thousandth; it shows only in a loop of hashes over an image
already loaded, where `hashes()` computes several from one pass anyway.

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
