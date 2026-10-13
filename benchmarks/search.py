"""Comparing many hashes: 1 to N and N to N, in a Python loop, with numpy, in C.

The binding compares two hashes per call; a search compares one with many, or every
pair of a collection. Here a Python loop over the binding's calls, a Python loop over
``int.bit_count()``, and numpy's ``bitwise_count`` over an array of hashes are set
against a C loop over ``ph_hamming_distance()``. Every time is per comparison.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

import libphash as ph

from .report import Block
from .timing import measure

if TYPE_CHECKING:
    import numpy.typing as npt

    from .cbench import CBench
    from .timing import Effort

C = "C loop, ph_hamming_distance()"
#: Rows of the N-to-N comparison handled per numpy step: a block of 256 rows of 10^4
#: hashes is 20 MiB of XOR and counts.
BLOCK = 256


def _random(n: int, seed: int = 1) -> npt.NDArray[np.uint64]:
    return np.random.default_rng(seed).integers(0, 2**64, n, dtype=np.uint64)


def _nearest_numpy(q: int, arr: npt.NDArray[np.uint64]) -> int:
    return int(np.bitwise_count(arr ^ np.uint64(q)).argmin())


def _all_pairs_numpy(arr: npt.NDArray[np.uint64]) -> int:
    total = 0
    for start in range(0, len(arr), BLOCK):
        rows = arr[start : start + BLOCK, None]
        total += int(np.bitwise_count(rows ^ arr[None, :]).sum(dtype=np.int64))
    return total


def run(cbench: CBench, effort: Effort) -> Block:
    """Measure every table of the block."""
    block = Block("search", "2. Searching: one against many, every pair")
    sizes = [effort.scale(n, 1000) for n in (10_000, 100_000, 1_000_000)]
    if effort.quick:
        sizes = sizes[:1]
    _one_to_many(block, sizes, cbench, effort)
    _digests(block, sizes[:2], effort)
    _all_pairs(block, cbench, effort)
    return block


def _one_to_many(
    block: Block, sizes: list[int], cbench: CBench, effort: Effort
) -> None:
    table = block.table(
        "nearest_uint64",
        "1 to N: the nearest of N 64-bit hashes",
        "The index of the hash nearest to a query, per hash compared.",
        "s",
        baseline_row=C,
    )
    c_times = cbench.time([["search", n] for n in sizes], effort)
    for n, c in zip(sizes, c_times, strict=True):
        column = f"N = {n:,}"
        arr = _random(n)
        ints = [int(v) for v in arr]
        q = ints[0] ^ 0x0123456789ABCDEF
        hamming = ph.hamming_distance
        table.add(C, column, c)
        table.add(
            "Python loop, hamming_distance()",
            column,
            measure(
                lambda: min(range(n), key=lambda i: hamming(q, ints[i])),
                n,
                effort,
            ),
        )
        table.add(
            "Python loop, (q ^ h).bit_count()",
            column,
            measure(
                lambda: min(range(n), key=lambda i: (q ^ ints[i]).bit_count()),
                n,
                effort,
            ),
        )
        table.add(
            "numpy, bitwise_count(arr ^ q).argmin()",
            column,
            measure(lambda: _nearest_numpy(q, arr), n, effort),
        )
        table.add(
            "numpy, building the uint64 array from a list of int",
            column,
            measure(lambda: np.array(ints, dtype=np.uint64), n, effort),
        )


def _digests(block: Block, sizes: list[int], effort: Effort) -> None:
    size, _ = ph.digest_info(ph.Algorithm.MHASH)
    table = block.table(
        "nearest_digest",
        f"1 to N: the nearest of N mHash digests ({size} bytes)",
        "Digests of the BITS kind compared by Hamming distance, per digest compared.",
        "s",
    )
    for n in sizes:
        column = f"N = {n:,}"
        rng = np.random.default_rng(2)
        matrix: npt.NDArray[np.uint8] = rng.integers(0, 256, (n, size), np.uint8)
        digests = [ph.Digest(row.tobytes(), ph.DigestKind.BITS) for row in matrix]
        query = digests[0]
        words = matrix.view(np.uint64)  # pyright: ignore[reportUnknownMemberType]
        qwords = words[0]
        table.add(
            "Python loop, Digest.hamming_distance()",
            column,
            measure(
                lambda: min(range(n), key=lambda i: query.hamming_distance(digests[i])),
                n,
                effort,
            ),
        )
        table.add(
            "numpy over bytes, bitwise_count(m ^ q).sum(1).argmin()",
            column,
            measure(
                lambda: int(np.bitwise_count(matrix ^ matrix[0]).sum(axis=1).argmin()),
                n,
                effort,
            ),
        )
        table.add(
            "numpy over uint64 words, the same",
            column,
            measure(
                lambda: int(np.bitwise_count(words ^ qwords).sum(axis=1).argmin()),
                n,
                effort,
            ),
        )
        table.add(
            "numpy, building the matrix from Digest.data",
            column,
            measure(
                lambda: np.frombuffer(  # pyright: ignore[reportUnknownMemberType]
                    b"".join(x.data for x in digests), np.uint8
                ),
                n,
                effort,
            ),
        )


def _all_pairs(block: Block, cbench: CBench, effort: Effort) -> None:
    table = block.table(
        "all_pairs",
        "N to N: every pair of N 64-bit hashes",
        "The sum of the distances of all N(N-1)/2 pairs, per pair; numpy works on "
        f"blocks of {BLOCK} rows against all N.",
        "s",
        baseline_row=C,
    )
    sizes = [effort.scale(n, 300) for n in (1_000, 10_000)]
    if effort.quick:
        sizes = sizes[:1]
    c_times = cbench.time([["search_all", n] for n in sizes], effort)
    for n, c in zip(sizes, c_times, strict=True):
        column = f"N = {n:,}"
        arr = _random(n)
        ints = [int(v) for v in arr]
        pairs = n * (n - 1) / 2

        def loop(h: list[int] = ints) -> int:
            return sum(
                (h[i] ^ h[j]).bit_count() for i in range(len(h)) for j in range(i)
            )

        table.add(C, column, c)
        # About 30 ns a pair: 10^4 hashes, 5 * 10^7 pairs, would take seconds per run.
        table.add(
            "Python loop, (a ^ b).bit_count()",
            column,
            measure(loop, pairs, effort) if n <= 1_000 else None,
        )
        # numpy compares every ordered pair, and each hash with itself; its time is per
        # distinct pair all the same, the answer a caller gets.
        table.add(
            "numpy, bitwise_count in blocks",
            column,
            measure(lambda: _all_pairs_numpy(arr), pairs, effort),
        )
