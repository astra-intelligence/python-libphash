"""One Config for every context, a refused value, and what each setting is read by.

The twin of libphash's ``examples/configure.c``. In Python the settings are one
immutable :class:`libphash.Config`, checked when it is created: a value out of range
raises there, naming the field, and no context ever holds it. A context keeps the
Config it was created with, so a different setting is a different context. Run::

    python examples/configure.py native/libphash/tests/data/photo.jpeg

prints::

    BMH digest at block_size 8: 8 bytes
    phash_reduction_size=9: refused
    pHash, 8x8 block: 7eb66192bc394247
    pHash, 6x6 block: 0000000852fb9487
    ColorHash in color:      a digest
    ColorHash in grayscale:  RequiresColorError
"""

from __future__ import annotations

import sys

import libphash as ph

# Every hash to be compared with another is computed with this one Config, so that all
# of them are computed alike.
CONFIG = ph.Config(
    max_pixels=50_000_000, alpha_mode="white", gray_weights=(1, 1, 1), bmh_block_size=8
)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <image>", file=sys.stderr)
        return 1
    path = argv[1]

    # A digest's size follows from the settings; no image is needed to know it.
    size, _ = ph.digest_info("bmh", CONFIG)
    print(f"BMH digest at block_size 8: {size} bytes")

    # A 9x9 block does not fit 64 bits: refused when the Config is made.
    try:
        CONFIG.replace(phash_reduction_size=9)
    except ph.InvalidArgumentError:
        print("phash_reduction_size=9: refused")

    try:
        before = ph.hash(path, config=CONFIG)
        after = ph.hash(path, config=CONFIG.replace(phash_reduction_size=6))
    except ph.PhashError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"pHash, 8x8 block: {before:016x}\npHash, 6x6 block: {after:016x}")

    # A load setting decides how the image is decoded: in grayscale there is no color
    # left for a color hash.
    for name, cfg in (("color", CONFIG), ("grayscale", CONFIG.replace(grayscale=True))):
        try:
            ph.hash(path, "color_hash", config=cfg)
            outcome = "a digest"
        except ph.RequiresColorError as exc:
            outcome = type(exc).__name__
        print(f"ColorHash in {name + ':':<11} {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
