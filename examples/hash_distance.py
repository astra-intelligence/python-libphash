"""Hash two images with the four 64-bit algorithms; print how many bits each pair differs in.

The twin of libphash's ``examples/hash_distance.c``: the same images give the same output.
Run from the repository root::

    python examples/hash_distance.py native/libphash/tests/data/photo.jpeg native/libphash/tests/data/photo_rotated_90.jpeg

prints::

    aHash  000c6461c1c3ffff  1f07634303333f0f  26 bits differ
    dHash  b159cdc98b1f1f1e  6c1e879786e6fcdc  35 bits differ
    pHash  7eb66192bc394247  a7a313dc73c92c25  34 bits differ
    wHash  ffffc38386263100  f2fcccc0c2c6e0f8  26 bits differ
"""

from __future__ import annotations

import sys
from typing import cast

import libphash as ph
from libphash import Algorithm

ALL_FOUR = (Algorithm.AHASH, Algorithm.DHASH, Algorithm.PHASH, Algorithm.WHASH)
NAMES = {Algorithm.AHASH: "aHash", Algorithm.DHASH: "dHash",
         Algorithm.PHASH: "pHash", Algorithm.WHASH: "wHash"}  # fmt: skip


def hash_file(path: str) -> dict[Algorithm, int]:
    """Return aHash, dHash, pHash and wHash of one file, from one pass over the image."""
    with ph.ImageContext() as ctx:
        ctx.load_file(path)
        hashes = ctx.hashes(*ALL_FOUR)
    # The 64-bit algorithms give an int, the others a Digest.
    return {algo: cast("int", hashes[algo]) for algo in ALL_FOUR}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <image-a> <image-b>", file=sys.stderr)
        return 1
    try:
        a, b = hash_file(argv[1]), hash_file(argv[2])
    except ph.PhashError as exc:
        print(exc, file=sys.stderr)
        return 1
    for algo in ALL_FOUR:
        distance = ph.hamming_distance(a[algo], b[algo])
        print(
            f"{NAMES[algo]}  {a[algo]:016x}  {b[algo]:016x}  {distance:2d} bits differ"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
