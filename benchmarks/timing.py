"""Timing a piece of work the way libphash's site times its cases.

One warm-up run, then at least :data:`MIN_RUNS` runs and :data:`MIN_SECONDS`, at most
:data:`MAX_RUNS`; the minimum and the median are kept (``tools/site/stages/timing.c``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

MIN_RUNS = 5
MAX_RUNS = 300
MIN_SECONDS = 1.0


@dataclass(frozen=True)
class Timing:
    """The time of one item of work, in seconds."""

    minimum: float
    median: float
    runs: int


def measure(
    work: Callable[[], object],
    items: int = 1,
    *,
    min_runs: int = MIN_RUNS,
    min_seconds: float = MIN_SECONDS,
) -> Timing:
    """Time ``work``, which handles ``items`` items per run; the time of one item."""
    work()
    times: list[float] = []
    start = time.perf_counter()
    while len(times) < MAX_RUNS and (
        len(times) < min_runs or time.perf_counter() - start < min_seconds
    ):
        t0 = time.perf_counter()
        work()
        times.append((time.perf_counter() - t0) / items)
    times.sort()
    return Timing(times[0], times[len(times) // 2], len(times))
