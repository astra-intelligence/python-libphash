"""One picture loaded three ways, and the same pHash from each.

As pixels already in memory (numpy, with a row stride), as an encoded file in memory,
and as a file on disk. The twin of libphash's ``examples/load_sources.c``: the same
output. Needs numpy. Run::

    python examples/load_sources.py frame.ppm

(``frame.ppm`` is the file it writes and then loads) prints::

    pixels           pHash a036b6b65676c8c9
    memory           pHash a036b6b65676c8c9
    file             pHash a036b6b65676c8c9
    one picture, one hash
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import numpy.typing as npt

import libphash as ph

# Each row is padded to 512 bytes: the stride is the distance from one row to the next,
# which need not be the width times the channels.
WIDTH, HEIGHT, STRIDE = 150, 100, 512


def make_frame() -> npt.NDArray[np.uint8]:
    """Return a frame some other code produced: RGB, a gradient with a bright disc."""
    buffer = bytearray(HEIGHT * STRIDE)
    # Rows STRIDE bytes apart, pixels 3, channels 1: the padding stays between rows.
    frame: npt.NDArray[np.uint8] = np.ndarray(
        (HEIGHT, WIDTH, 3), np.uint8, buffer, strides=(STRIDE, 3, 1)
    )
    y, x = np.mgrid[:HEIGHT, :WIDTH]
    frame[..., 0] = x
    frame[..., 1] = y * 2
    frame[..., 2] = 160
    frame[(x - 100) ** 2 + (y - 40) ** 2 < 30 * 30] = (250, 220, 90)
    return frame


def print_phash(ctx: ph.ImageContext, source: str) -> int:
    """Hash what ``ctx`` holds and print it with the name of the source."""
    value = ctx.phash()
    print(f"{source:<16} pHash {ph.hash_to_hex(value)}")
    return value


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <file to write>", file=sys.stderr)
        return 1
    frame = make_frame()
    # The same frame encoded as a binary PPM, whole, in one buffer.
    encoded = f"P6\n{WIDTH} {HEIGHT}\n255\n".encode() + frame.tobytes()
    with ph.ImageContext() as ctx:
        try:
            # --8<-- [start:sources]
            # Pixels: an array of shape (height, width, channels); its row step goes
            # to C as the stride, without a copy.
            ctx.load_pixels(frame)
            from_pixels = print_phash(ctx, "pixels")

            # Memory: an encoded file -- from a network, a database, an archive.
            ctx.load_bytes(encoded)
            from_memory = print_phash(ctx, "memory")

            # File: the same bytes on disk.
            Path(argv[1]).write_bytes(encoded)
            ctx.load_file(argv[1])
            from_file = print_phash(ctx, "file")
            # --8<-- [end:sources]
        except ph.PhashError as exc:
            print(exc, file=sys.stderr)
            return 1
    if not from_pixels == from_memory == from_file:
        print("the three sources disagree")
        return 1
    print("one picture, one hash")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
