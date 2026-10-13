"""Hash one image from every kind of source: a path, bytes, a file object, numpy, Pillow.

A decoded image (numpy, Pillow, OpenCV) is hashed from its pixels, so it gives the hash
of the file only when its decoder produced the same pixels: true of PNG, not in general
of JPEG, which every decoder rounds its own way. OpenCV's arrays are BGR, and say so
with ``channel_order="bgr"``. Needs numpy and Pillow; OpenCV is used if installed. Run::

    python examples/sources.py native/libphash/tests/data/photo.png

prints::

    path         0100000101000139
    bytes        0100000101000139
    file object  0100000101000139
    numpy        0100000101000139
    Pillow       0100000101000139
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import libphash as ph


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <png image>", file=sys.stderr)
        return 1
    path = Path(argv[1])
    data = path.read_bytes()
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    sources: dict[str, ph.Source] = {
        "path": path,
        "bytes": data,
        "file object": io.BytesIO(data),
        "numpy": np.asarray(image),  # shape (height, width, 3), RGB
        "Pillow": image,
    }
    hashes = {name: ph.hash(source) for name, source in sources.items()}
    for name, value in hashes.items():
        print(f"{name:<12} {ph.hash_to_hex(value)}")

    try:
        import cv2  # noqa: PLC0415 -- optional
    except ImportError:
        return 0
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        print(f"OpenCV cannot read {path}", file=sys.stderr)
        return 1
    with ph.ImageContext() as ctx:
        ctx.load_pixels(bgr, channel_order="bgr")
        if ctx.phash() != hashes["path"]:
            print("OpenCV's pixels hash differently")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
