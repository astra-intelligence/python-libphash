"""The speed benchmark: how long each contender takes to hash a photograph file.

Every contender hashes the same photographs, decoding included, one after another on
one thread, as :mod:`benchmarks.contenders` describes. libphash's ways of hashing many
files with its four 64-bit hashes are timed beside them: the four from one load
(``ImageContext.hashes()``), and ``hash_files()`` on one thread and on every core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import libphash as ph

from .contenders import contenders
from .timing import MIN_RUNS, MIN_SECONDS, Timing, measure

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from .contenders import Hasher

#: libphash's 64-bit hashes, which a batch computes together.
UINT64: tuple[ph.Uint64Name, ...] = ("ahash", "dhash", "phash", "whash")


@dataclass(frozen=True)
class SpeedCase:
    """The time to hash one photograph one way."""

    key: str
    library: str
    #: The algorithm family, or what a libphash case computes ("4 hashes").
    algorithm: str
    #: How the case hashes, where the library offers more than one way.
    how: str
    time: Timing


@dataclass(frozen=True)
class SpeedResult:
    """The speed benchmark's times, per photograph."""

    images: int
    cases: list[SpeedCase]


def _loop(compute: Callable[[str], object], paths: Sequence[str]) -> Callable[[], None]:
    def work() -> None:
        for p in paths:
            compute(p)

    return work


def libphash_batches(paths: Sequence[str]) -> list[tuple[str, Callable[[], object]]]:
    """Return libphash's ways of computing the four 64-bit hashes of every file."""
    ctx = ph.ImageContext()

    def one_load() -> None:
        for p in paths:
            ctx.load_file(p)
            ctx.hashes(*UINT64)

    return [
        ("one load per file", one_load),
        ("hash_files(), 1 thread", lambda: ph.hash_files(paths, UINT64, threads=1)),
        ("hash_files(), all cores", lambda: ph.hash_files(paths, UINT64)),
    ]


def measure_speed(
    paths: Sequence[str],
    hashers: Sequence[Hasher] | None = None,
    *,
    min_runs: int = MIN_RUNS,
    min_seconds: float = MIN_SECONDS,
) -> SpeedResult:
    """Time every contender (all of them by default) on ``paths``."""
    chosen = list(hashers) if hashers is not None else contenders()
    n = len(paths)
    cases = [
        SpeedCase(
            c.key,
            c.library,
            c.algorithm,
            "",
            measure(
                _loop(c.compute, paths), n, min_runs=min_runs, min_seconds=min_seconds
            ),
        )
        for c in chosen
    ]
    cases += [
        SpeedCase(
            f"libphash/4 hashes/{how}",
            "libphash",
            "4 hashes",
            how,
            measure(work, n, min_runs=min_runs, min_seconds=min_seconds),
        )
        for how, work in libphash_batches(paths)
    ]
    return SpeedResult(n, cases)
