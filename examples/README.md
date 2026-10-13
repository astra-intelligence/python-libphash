# Examples

Each example is one script, run from the repository root with the images of libphash's
test fixtures; its docstring shows the command and what it prints, and
`tests/test_examples.py` runs every one and compares. Four of them are twins of
[libphash's C examples](https://github.com/gudoshnikovn/libphash/tree/main/examples): the
tests build the C one too, give both the same images, and require the same output.

| Example | What it shows |
|---|---|
| [`load_sources.py`](load_sources.py) | One picture from pixels in memory (with a row stride), from an encoded buffer and from a file, and the same hash from each. Twin of `load_sources.c`. |
| [`configure.py`](configure.py) | One `Config` for every context, a value refused when the `Config` is made, and a load setting that changes what a color hash can do. Twin of `configure.c`. |
| [`hash_distance.py`](hash_distance.py) | aHash, dHash, pHash and wHash of two images from one pass each, and the bits each pair differs in. Twin of `hash_distance.c`. |
| [`find_duplicates.py`](find_duplicates.py) | Many files hashed on all CPUs, each hash printed as it would be stored, and every pair within a threshold, closest first. Twin of `find_duplicates.c`. |
| [`sources.py`](sources.py) | One image from a path, bytes, a file object, a numpy array, a Pillow image and OpenCV's BGR array. |
| [`store_sqlite.py`](store_sqlite.py) | Hashes in SQLite: a 64-bit hash as a signed `INTEGER`, a digest as text that keeps its kind, and a Hamming-distance query in SQL. |
| [`nearest_numpy.py`](nearest_numpy.py) | The nearest hashes to a query among many, with `numpy.bitwise_count`. |
| [`bk_tree.py`](bk_tree.py) | Groups of near duplicates found with a BK-tree instead of comparing every pair. |
| [`concurrency.py`](concurrency.py) | A batch from asyncio, a thread pool with one context per thread, and worker processes, with the same hashes. |
| [`threshold.py`](threshold.py) | A threshold chosen from labeled pairs ([`pairs.csv`](pairs.csv)): missed copies and false matches at each one. |

`load_sources.py`, `sources.py` and `nearest_numpy.py` need numpy, `sources.py` Pillow too.
