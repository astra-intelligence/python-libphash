"""Store hashes in SQLite, and find an image's near duplicates there.

A 64-bit hash fits SQLite's ``INTEGER``, which is signed: a hash at or above 2**63 is
stored as the negative number with the same 64 bits, and read back the same way. A
digest is stored as its text form, which keeps its kind, so a digest read back still
refuses a comparison that does not fit it. Store the library version and the
settings beside the hashes: hashes are comparable only when both match. Run::

    python examples/store_sqlite.py native/libphash/tests/data/photo.jpeg native/libphash/tests/data/photo_copy.jpeg native/libphash/tests/data/photo_rotated_90.jpeg native/libphash/tests/data/photo.png

prints::

    stored 4 images with libphash 2.0.2
    within 10 bits of native/libphash/tests/data/photo.jpeg:
       0  native/libphash/tests/data/photo.jpeg
       0  native/libphash/tests/data/photo_copy.jpeg
    mHash similarity of the first two, read back: 1.000
"""

from __future__ import annotations

import sqlite3
import sys

import libphash as ph


def to_int64(value: int) -> int:
    """Return the signed 64-bit integer with the bits of an unsigned 64-bit hash."""
    return value - (1 << 64) if value >= 1 << 63 else value


def from_int64(value: int) -> int:
    """Return the unsigned 64-bit hash stored as a signed integer."""
    return value + (1 << 64) if value < 0 else value


def hamming(a: int, b: int) -> int:
    """Hamming distance of two hashes in their stored form, for SQL."""
    return ph.hamming_distance(from_int64(a), from_int64(b))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <image>...", file=sys.stderr)
        return 1
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE images (path TEXT PRIMARY KEY, phash INTEGER NOT NULL,"
        " mhash TEXT NOT NULL, libphash TEXT NOT NULL)"
    )
    db.create_function("hamming", 2, hamming, deterministic=True)

    with ph.ImageContext() as ctx:
        for path in argv[1:]:
            ctx.load_file(path)
            db.execute(
                "INSERT INTO images VALUES (?, ?, ?, ?)",
                (path, to_int64(ctx.phash()), ctx.mhash().hex(), ph.libphash_version()),
            )
    print(f"stored {len(argv) - 1} images with libphash {ph.libphash_version()}")

    query = to_int64(ph.hash(argv[1]))
    print(f"within 10 bits of {argv[1]}:")
    rows = db.execute(
        "SELECT hamming(phash, ?) AS d, path FROM images WHERE d <= 10 ORDER BY d, path",
        (query,),
    )
    for distance, path in rows:
        print(f"  {distance:2d}  {path}")

    a, b = (
        ph.Digest.from_hex(text)
        for (text,) in db.execute("SELECT mhash FROM images ORDER BY rowid LIMIT 2")
    )
    print(f"mHash similarity of the first two, read back: {a.similarity(b):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
