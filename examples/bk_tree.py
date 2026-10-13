"""Group near-duplicate images with a BK-tree instead of comparing every pair.

A BK-tree indexes the hashes by their Hamming distance to one another, so a query
"everything within N bits" visits a part of the collection instead of all of it; the
groups are the images linked by a chain of such matches. Comparing every pair (as
``find_duplicates.py`` does) is simpler and fine for a few thousand images. Run::

    python examples/bk_tree.py 6 native/libphash/tests/data/photo.jpeg native/libphash/tests/data/photo_copy.jpeg native/libphash/tests/data/jpeg/s420.jpg native/libphash/tests/data/jpeg/s444.jpg native/libphash/tests/data/photo.png

prints::

    group of 2:
      native/libphash/tests/data/photo.jpeg
      native/libphash/tests/data/photo_copy.jpeg
    group of 2:
      native/libphash/tests/data/jpeg/s420.jpg
      native/libphash/tests/data/jpeg/s444.jpg
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import libphash as ph


@dataclass
class Node:
    """A hash, the items that have it, and children keyed by their distance to it."""

    value: int
    items: list[str]
    children: dict[int, Node] = field(default_factory=dict)


class BKTree:
    """A BK-tree of 64-bit hashes under the Hamming distance."""

    def __init__(self) -> None:
        self.root: Node | None = None

    def add(self, value: int, item: str) -> None:
        """Index ``item`` under its hash ``value``."""
        if self.root is None:
            self.root = Node(value, [item])
            return
        node = self.root
        while True:
            d = ph.hamming_distance(value, node.value)
            if d == 0:
                node.items.append(item)
                return
            if d not in node.children:
                node.children[d] = Node(value, [item])
                return
            node = node.children[d]

    def search(self, value: int, max_bits: int) -> list[str]:
        """Return the items whose hash is within ``max_bits`` of ``value``."""
        found: list[str] = []
        pending = [self.root] if self.root else []
        while pending:
            node = pending.pop()
            d = ph.hamming_distance(value, node.value)
            if d <= max_bits:
                found += node.items
            # Only children at a distance within max_bits of d can hold a match.
            for key, child in node.children.items():
                if d - max_bits <= key <= d + max_bits:
                    pending.append(child)
        return found


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(f"usage: {argv[0]} <max-bits> <image>...", file=sys.stderr)
        return 1
    max_bits = int(argv[1])
    hashes = {
        r.source: r.hashes[ph.Algorithm.PHASH]
        for r in ph.hash_files(argv[2:], ph.Algorithm.PHASH)
        if r.hashes
    }
    tree = BKTree()
    for path, value in hashes.items():
        tree.add(value, path)

    # Each image not yet grouped starts a group, which grows by its matches' matches.
    grouped: set[str] = set()
    for path in hashes:
        if path in grouped:
            continue
        group, pending = {path}, [path]
        while pending:
            for match in tree.search(hashes[pending.pop()], max_bits):
                if match not in group:
                    group.add(match)
                    pending.append(match)
        grouped |= group
        if len(group) > 1:
            print(f"group of {len(group)}:")
            for member in sorted(group, key=list(hashes).index):
                print(f"  {member}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
