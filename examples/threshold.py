"""Choose a threshold for your own images from pairs you have labeled.

A threshold trades missed copies against false matches, and where it lies depends on
the images and on the edits a copy goes through: measure it. List pairs of images as
"same" picture or "different" in a CSV file (``first,second,label``, paths relative to
the file), and this prints, for each threshold, how many copies it misses and how many
different pairs it takes for copies; the largest threshold without a false match keeps
every margin there is. libphash's guide explains the method and its pitfalls:
https://gudoshnikovn.github.io/libphash/theory/comparing/. Run::

    python examples/threshold.py examples/pairs.csv

prints::

    bits  missed copies  false matches
       0         2 of 6         0 of 6
       2         0 of 6         0 of 6
       4         0 of 6         0 of 6
       6         0 of 6         0 of 6
       8         0 of 6         1 of 6
      10         0 of 6         1 of 6
      12         0 of 6         2 of 6
    largest threshold without a false match: 6 bits
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import libphash as ph


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <pairs.csv>", file=sys.stderr)
        return 1
    table = Path(argv[1])
    same: list[int] = []
    different: list[int] = []
    with table.open(newline="") as f:
        for row in csv.DictReader(f):
            a = ph.hash(table.parent / row["first"])
            b = ph.hash(table.parent / row["second"])
            (same if row["label"] == "same" else different).append(
                ph.hamming_distance(a, b)
            )

    print("bits  missed copies  false matches")
    for bits in range(0, 13, 2):
        missed = sum(d > bits for d in same)
        false = sum(d <= bits for d in different)
        missed_text = f"{missed} of {len(same)}"
        false_text = f"{false} of {len(different)}"
        print(f"{bits:4d}  {missed_text:>13}  {false_text:>13}")
    closest_different = min(different, default=65)
    print(f"largest threshold without a false match: {closest_different - 1} bits")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
