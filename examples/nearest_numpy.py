"""Find the nearest hashes to a query among many, with numpy.

The 64-bit hashes of a collection go into one ``uint64`` array; the distance to a query
is the population count of the XOR, computed for all of them at once
(``numpy.bitwise_count``, numpy 2.0 or later). Needs numpy. Run::

    python examples/nearest_numpy.py native/libphash/tests/data/photo.jpeg native/libphash/tests/data/photo_copy.jpeg native/libphash/tests/data/photo_rotated_90.jpeg native/libphash/tests/data/photo.png native/libphash/tests/data/photo_complex.png

prints::

    the 3 nearest to native/libphash/tests/data/photo.jpeg:
       0  native/libphash/tests/data/photo.jpeg
       0  native/libphash/tests/data/photo_copy.jpeg
      31  native/libphash/tests/data/photo_complex.png
"""

from __future__ import annotations

import sys

import numpy as np

import libphash as ph


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <query image> <image>...", file=sys.stderr)
        return 1
    paths = argv[1:]
    results = ph.hash_files(paths, ph.Algorithm.PHASH)
    known = [(r.source, r.hashes[ph.Algorithm.PHASH]) for r in results if r.hashes]
    hashes = np.array([value for _, value in known], dtype=np.uint64)

    query = np.uint64(ph.hash(paths[0]))
    distances = np.bitwise_count(hashes ^ query)
    nearest = distances.argsort(kind="stable")[:3]
    print(f"the {len(nearest)} nearest to {paths[0]}:")
    for i in nearest:
        print(f"  {distances[i]:2d}  {known[i][0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
