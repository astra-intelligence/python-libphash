"""Timing a piece of work the way libphash's site times its cases.

One run to warm up, then runs until there have been at least ``min_runs`` of them and
``min_seconds`` have passed, at most :data:`MAX_RUNS`; the minimum and the median of the
runs are kept. The minimum is the number to compare between two builds, the median the
one a caller meets. A run repeats work shorter than :data:`MIN_RUN_SECONDS` until it
lasts that long, so that the clock's resolution and its cost do not show.
``benchmarks/c/bench.c`` times its cases the same way.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

MIN_RUNS = 5
MIN_SECONDS = 1.0
MAX_RUNS = 100_000
MIN_RUN_SECONDS = 50e-6


@dataclass(frozen=True)
class Effort:
    """How long each case runs: the full measurement, or a quick check that it runs.

    In the quick mode, :meth:`scale` also shrinks the work itself (images per batch,
    hashes per search).
    """

    min_runs: int = MIN_RUNS
    min_seconds: float = MIN_SECONDS
    quick: bool = False

    def scale(self, full: int, quick: int) -> int:
        """Return ``quick`` in the quick mode, ``full`` otherwise."""
        return quick if self.quick else full


FULL = Effort()
QUICK = Effort(min_runs=1, min_seconds=0.0, quick=True)


@dataclass(frozen=True)
class Timing:
    """The time of one item of work, in seconds."""

    minimum: float
    median: float
    runs: int


def measure(
    work: Callable[[], object], items: float = 1, effort: Effort = FULL
) -> Timing:
    """Time ``work``, which handles ``items`` items per run; the time of one item."""
    t0 = time.perf_counter()
    work()
    once = time.perf_counter() - t0
    repeat = int(MIN_RUN_SECONDS / once) + 1 if once < MIN_RUN_SECONDS else 1
    loop = range(repeat)
    times: list[float] = []
    start = time.perf_counter()
    while len(times) < MAX_RUNS and (
        len(times) < effort.min_runs or time.perf_counter() - start < effort.min_seconds
    ):
        t0 = time.perf_counter()
        for _ in loop:
            work()
        times.append((time.perf_counter() - t0) / (items * repeat))
    times.sort()
    return Timing(times[0], times[len(times) // 2], len(times))
