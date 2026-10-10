from __future__ import annotations

from pathlib import Path
from typing import cast
from ._native import lib  # type: ignore
from .context import ImageContext
from .ph_types import HashMethod


def hamming_distance(h1: int, h2: int) -> int:
    """Calculate Hamming distance between two uint64 hashes."""
    return int(lib.ph_hamming_distance(int(h1), int(h2)))  # type: ignore


def get_hash(path: str | Path, method: HashMethod = HashMethod.PHASH) -> int:
    """Convenience function to get a hash for a file."""
    with ImageContext(path=path) as ctx:
        return cast(int, getattr(ctx, method.value))


def compare_images(
    path1: str | Path, path2: str | Path, method: HashMethod = HashMethod.PHASH
) -> int:
    """Convenience function to compare two images."""
    with ImageContext(path=path1) as ctx1, ImageContext(path=path2) as ctx2:
        h1 = cast(int, getattr(ctx1, method.value))
        h2 = cast(int, getattr(ctx2, method.value))
        return hamming_distance(h1, h2)


def ph_can_use_libjpeg() -> bool:
    """Check if libjpeg-turbo is available for fast JPEG decoding."""
    return bool(lib.ph_can_use_jpeg())


def ph_can_use_libpng() -> bool:
    """Check if libpng is available for fast PNG decoding."""
    return bool(lib.ph_can_use_png())
