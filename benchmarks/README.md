# Benchmarks

libphash's hashes beside other perceptual hashing libraries, on the photo corpus of
libphash's site and by the site's measures, so that libphash's numbers here are the
numbers on its site.

| Library | Hashes | Decodes with | Compares by |
|---|---|---|---|
| libphash (this binding) | aHash, dHash, pHash, wHash, BMH, mHash, Radial, ColorHash, ColorMoments | its own decoders, one reused `ImageContext` | bits that differ; peak correlation (Radial), histogram intersection (ColorHash), L2 distance (ColorMoments) |
| [imagehash](https://pypi.org/project/ImageHash/) | aHash, dHash, pHash, wHash, ColorHash | Pillow | bits that differ |
| OpenCV [img_hash](https://docs.opencv.org/4.x/d4/d93/group__img__hash.html) | aHash, pHash, BMH, mHash, Radial, ColorMoments | `cv2.imread`, one reused hasher | bits that differ; the hasher's `compare()` otherwise |
| [pdqhash](https://pypi.org/project/pdqhash/) | PDQ (256 bits) | Pillow | bits that differ |

Every library runs with its default parameters. A library that is not installed is left
out of the tables.

## Running

```bash
uv sync --all-extras --inexact     # the benchmark extra: imagehash, OpenCV, pdqhash
uv run python -m benchmarks all    # or quality, speed, overhead
```

Run from the repository root, with the `native/libphash` submodule checked out: the
benchmarks import the corpus, the edits and the measures from its `tools/site`. Each
benchmark prints a Markdown table and writes it to `build/benchmarks/<name>.md`, with the
raw values beside it in `<name>.json`.

| Option | Effect |
|---|---|
| `--images PATH…` | measure these files instead of the corpus |
| `--limit N` | the first `N` photographs of the corpus only |
| `--only KEY…` | these contenders only, as `library/algorithm` (`libphash/pHash`, `OpenCV/BMH`) |
| `--workers N` | processes for the quality benchmark (all cores by default) |
| `--quick` | one timed run per case instead of the site's rules |
| `--cache DIR` | where the corpus is kept |
| `--out DIR` | where the results go |

### The corpus

200 public-domain photographs, the corpus of libphash's site. They come from a copy of
the files at a fixed commit (`gudoshnikovn/libphash-site-corpus`), never from Wikimedia
Commons itself: Commons rewrites a file's metadata when its description is edited, and
the bytes, and so the hashes, would differ between two runs. Every file is checked
against the SHA-256 in the submodule's `tools/site/corpus_photos.tsv`. A benchmark runs
on the whole corpus or not at all, so a missing or mismatched file is an error.

The first run downloads the corpus (about 126 MB) into `~/.cache/libphash-site/`, the
cache libphash's site uses too; later runs read it from there. The commit of the copy and
the manifest belong to the submodule's tag, so they change only with the bundled
libphash.

## Quality

Every photograph is decoded once by Pillow and saved losslessly. This copy is the
reference for every comparison, so the reference and the image that is edited are the
same pixels. Each edit is applied to it at every strength:

| Edit | Strengths | Group |
|---|---|---|
| JPEG quality | 95, 75, **50**, 30, 15, 5 | copy |
| Downscale | 0.75, **0.5**, 0.25, 0.125 | copy |
| Rotation, degrees | 1, **2**, 5, 10, 20, 45 | copy |
| Brightness | 0.5, 0.7, 0.85, **1.15**, 1.3, 1.5 | copy |
| Contrast | 0.5, 0.7, 0.85, **1.15**, 1.3, 1.5 | copy |
| Gamma | 0.5, 0.7, 0.85, **1.2**, 1.5, 2.0 | copy |
| Gaussian blur, px | 0.5, **1**, 2, 4, 8 | copy |
| Noise, σ | 2, **5**, 10, 20, 40 | copy |
| Crop, % of the border | **5**, 10, 20, 30 | copy |
| Local patch | 1, 4, 9, 16 | content |
| Hue rotation, degrees | 30, 90, 180 | content |
| Turn and mirror | 90°, 180°, mirror | content |

Each contender compares every edited image with its reference. It also compares every
pair of distinct references (19,900 pairs for 200 photographs): these are the
*different* photographs.

A *copy* is a photograph after one moderate edit: the strength in bold of each edit in
the copy group. From the copies and the different pairs, the tables give:

- **d′**: the gap between the mean value of the copies and that of the different pairs,
  in units of their pooled spread. Higher is better: copies and different photographs
  land further apart.
- **False accepts at 95 %**: take the threshold that accepts 95 % of the copies; this is
  the share of different pairs it also accepts. Lower is better: it is how often a
  search tuned to find copies returns a photograph that is not one.
- **Edits a copy goes through**: per edit, the share of its variants, over every
  strength, that this threshold accepts. Higher means more robust to that edit.
  Strong edits (JPEG quality 5, a 45° turn) are in the share too, so 100 % is rare.
- **Edits that change the picture**: the same share for edits that change what the
  picture shows. Whether accepting them is good depends on the use: a crop-and-patch
  detector wants a high share, a near-duplicate search for the same content a low one.

d′ and the share of false accepts do not depend on a metric's units, so a 64-bit hash, a
576-bit hash and a correlation score compare directly. Two hashes of the same family in
different libraries can still differ, because each library chooses its own
resizing, color conversion and thresholds. Where libphash refuses a comparison (Radial
of an image with no structure), the value is left out and the table says how many.

The definitions are the code of libphash's site (`tools/site/measure/separability.py`),
imported rather than rewritten.

## Speed

The time to hash a photograph file, decoding included, on one thread, for the first 50
photographs of the corpus: each library decodes as it is meant to be used (see the
first table). The table gives the median time per photograph and, in parentheses, how
many times libphash's time it is.

A second table times libphash's four 64-bit hashes (aHash, dHash, pHash, wHash)
together: from one load per file through `ImageContext.hashes()`, and through
`hash_files()` on one thread and on every core.

Each case runs once to warm up, then at least 5 times and at least one second, at most
300 runs: the rules of libphash's site. The median is the figure to compare; the
minimum is in the JSON. Times depend on the machine, the decoders the build uses and
the other libraries' versions; every table starts with all three.

## Overhead

What the binding adds to the C library. Each job runs on the test suite's 400×400 JPEG,
small enough that the overhead shows:

- through the binding's API, and as the bare C call through cffi that the API makes.
  The difference is the binding's own cost: argument checks, the context's lock,
  building the result;
- `libphash.hash()` with a new context per file, one `ImageContext` reused, and
  `hash_files()`;
- a numpy array passed without a copy (contiguous, or a cropped view with spaced rows)
  and with one copy (BGR order).

Times are per call, or per image for the loop and batch cases.
