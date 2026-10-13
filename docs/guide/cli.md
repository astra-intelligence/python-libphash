# Command line

The package installs a command, `libphash`; `python -m libphash` is the same command
where the scripts directory is not on `PATH`. It needs nothing beyond the package and
covers four tasks: what is installed, the hashes of files, a comparison of two images,
and groups of near-duplicates.

## Hashes of files

`libphash hash` prints a line per file, the hash and the path, as `sha256sum` does:

```console
$ libphash hash photo.jpg photo_copy.jpg
7eb66192bc394247  photo.jpg
7eb66192bc394247  photo_copy.jpg
```

`-a`/`--algorithm` takes one algorithm or several separated by commas (pHash by
default). A 64-bit hash is 16 hex digits; a digest is written with its kind, in the
text form of [`Digest.hex()`](../api/digests.md), so it can be read back with
`Digest.from_hex()`:

```console
$ libphash hash -a phash,dhash,radial photo.jpg
7eb66192bc394247 b159cdc98b1f1f1e coefficients:5c67ff132b6000615f3c7555595f52754d676162665c4f6c5f6860586062605d5a5a6357535c5e61  photo.jpg
```

A directory is searched recursively for the formats libphash decodes, in sorted order;
a file named on the command line is hashed whatever its name, and `-` reads one image
from standard input. A file that cannot be hashed is reported on standard error and
does not stop the others:

```console
$ libphash hash broken.jpg photo.jpg
libphash: broken.jpg: Corrupt JPEG data: 23 extraneous bytes before marker 0x5e
7eb66192bc394247  photo.jpg
```

`--json` writes a JSON object per line, with the error in it instead of on standard
error:

```console
$ libphash hash --json photo.jpg
{"path": "photo.jpg", "hashes": {"phash": "7eb66192bc394247"}}
```

## Comparing two images

`libphash compare` hashes two images with each algorithm and compares them by the
measures that belong to it ([Comparing hashes](https://gudoshnikovn.github.io/libphash/theory/comparing/)):
the Hamming distance and the similarity for bit hashes, the similarity for ColorHash and
Radial, the L2 distance for ColorMoments:

```console
$ libphash compare -a phash,color_hash,color_moments photo.jpg photo_rotated.jpg
phash          distance 34, similarity 0.4688
color_hash     similarity 0.9880
color_moments  l2_distance 2.9401
```

## Near-duplicates

`libphash dupes` hashes every image on all CPUs with a 64-bit algorithm (`-a`: aHash,
dHash, pHash or wHash) and prints the groups of images whose hashes differ in at most
`--max-bits` bits, one group per paragraph. Two images are in one group when a chain of
such pairs joins them. The threshold has no default: it depends on the images and the
algorithm, and is measured on your own data
([Choosing a threshold](https://gudoshnikovn.github.io/libphash/theory/comparing/#choosing-a-threshold),
the example `threshold.py`).

```console
$ libphash dupes --max-bits 10 album
7eb66192bc394247  album/photo.jpg
7eb66192bc394247  album/photo_copy.jpg
```

Every pair of hashes is compared, so the time grows with the square of the number of
images; for a large collection, index the hashes as
[Storing and searching](storing.md) shows.

## Settings

`-c`/`--config FIELD=VALUE` sets a field of [`Config`](../api/config.md) for `hash`,
`compare` and `dupes`, and repeats for several fields. The value is read by the type of
the field: `-c auto_orient=false`, `-c max_pixels=50000000`, `-c gray_weights=38,75,15`.

## For bug reports

`libphash info` prints the versions of the package and of the bundled libphash, the
build (`build_info()`: the decoders and the SIMD the wheel carries), the Python and the
platform; `--json` prints the same as one object. The bug report template asks for it.

## Exit status

| Status | Meaning |
|---|---|
| 0 | every file was hashed |
| 1 | some files were not |
| 2 | a wrong command line |
| 130 | interrupted by Ctrl+C |

Output into a closed pipe (`libphash hash album | head`) stops the command quietly.
