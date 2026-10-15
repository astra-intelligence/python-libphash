"""Find the pictures that appear more than once among many files.

Hashes every file with pHash on all CPUs, prints each hash as it would be stored, then
every pair within a threshold, closest first. The threshold is the most bits two hashes
of one picture may differ in; measure it on your own images (``threshold.py``). The twin
of libphash's ``examples/find_duplicates.c``: the same files give the same output. Run::

    python examples/find_duplicates.py 7 native/libphash/tests/data/photo.jpeg native/libphash/tests/data/photo_copy.jpeg native/libphash/tests/data/photo.png

prints::

    # algorithm=phash version=2000002 native-jpeg=1
    7eb66192bc394247  native/libphash/tests/data/photo.jpeg
    7eb66192bc394247  native/libphash/tests/data/photo_copy.jpeg
    0100000101000139  native/libphash/tests/data/photo.png
     0 bits  native/libphash/tests/data/photo.jpeg  native/libphash/tests/data/photo_copy.jpeg
    pairs within 7 bits: 1
"""

from __future__ import annotations

import sys
from itertools import combinations

import libphash as ph


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(f"usage: {argv[0]} <max-bits> <image>...", file=sys.stderr)
        return 1
    try:
        max_bits = int(argv[1])
    except ValueError:
        max_bits = -1
    if not 0 <= max_bits <= 64:
        print("max-bits must be a number from 0 to 64", file=sys.stderr)
        return 1

    # Every file hashed with pHash on all CPUs; a file that cannot be read fails alone.
    results = ph.hash_files(argv[2:], ph.Algorithm.PHASH)

    # A stored hash carries what decides its value: the algorithm, the library version,
    # and whether JPEG went through libjpeg-turbo or stb_image. The settings are the
    # defaults here; a program that changes them stores them too.
    major, minor, patch = (int(n) for n in ph.libphash_version().split("."))
    version = major * 1_000_000 + minor * 1000 + patch
    jpeg = int(ph.can_decode("jpeg"))
    print(f"# algorithm={ph.Algorithm.PHASH} version={version} native-jpeg={jpeg}")
    hashed: list[tuple[str, int]] = []
    for result in results:
        if result.hashes is None:
            print(result.error, file=sys.stderr)
        else:
            value = result.hashes[ph.Algorithm.PHASH]
            print(f"{ph.hash_to_hex(value)}  {result.source}")
            hashed.append((result.source, value))

    # Every pair compared once: n * (n - 1) / 2 Hamming distances.
    pairs = [
        (ph.hamming_distance(ha, hb), a, b)
        for (a, ha), (b, hb) in combinations(hashed, 2)
        if ph.hamming_distance(ha, hb) <= max_bits
    ]
    for distance, a, b in sorted(pairs, key=lambda p: p[0]):
        print(f"{distance:2d} bits  {a}  {b}")
    print(f"pairs within {max_bits} bits: {len(pairs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
