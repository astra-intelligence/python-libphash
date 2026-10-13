"""The regression gate: a pull request's benchmarks held to those of its base.

``python -m benchmarks.gate BASE.json HEAD.json [--summary FILE] [--fail-timing]``

Both files are written by one job on one machine, from the base of the pull request and
from its head, with ``--blocks overhead,memory``. Two kinds of number are held:

- **Memory, exactly.** Every Python-allocation cell of the memory block (tracemalloc,
  the same on every run) equals the base's within :data:`MEMORY_SLACK`: a new copy in
  Python fails. The peak resident rise of a batch stays within :data:`BATCH_FACTOR`
  times libphash's bound for its threads.
- **Time, against C.** A runner's speed varies from job to job and from minute to
  minute, so no absolute time is compared: each cell of an overhead table is divided by
  the C cell of its table (its baseline row, or its ``C`` column), and that ratio is
  compared with the base's. A ratio that grows by more than :data:`WARN_CHEAP` (a call
  whose C cell takes under :data:`CHEAP` seconds) or :data:`WARN_WORK` (a load or a
  hash of a whole image) is reported as a warning; with ``--fail-timing``, growth
  beyond :data:`FAIL_CHEAP` or :data:`FAIL_WORK` fails. Rows that time C itself, and
  tables without a C cell, are published, not gated.

A cell that only one side has (a case added or removed) is skipped. The exit status is
1 when a check fails and 0 otherwise; GitHub annotations go to standard output, and a
Markdown summary to ``--summary``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

#: How far a Python-allocation cell may move, in bytes: allocator rounding, not a copy.
MEMORY_SLACK = 1024
#: The bound on a batch's peak resident rise, as a multiple of libphash's estimate.
BATCH_FACTOR = 1.1
#: A C cell faster than this, in seconds, is a cheap call, where cffi's share is large.
CHEAP = 10e-6
WARN_CHEAP = 0.15
WARN_WORK = 0.05
FAIL_CHEAP = 0.25
FAIL_WORK = 0.10

Table = dict[str, Any]


@dataclass(frozen=True)
class Ratio:
    """One timed cell, against its C cell, at the base and at the head."""

    table: str
    row: str
    column: str
    base: float
    head: float
    cheap: bool

    @property
    def growth(self) -> float:
        """Return how much the ratio grew, 0.1 for 10 %."""
        return self.head / self.base - 1

    def exceeds(self, *, fail: bool) -> bool:
        """Say whether the growth passes the warning or the failure threshold."""
        if fail:
            return self.growth > (FAIL_CHEAP if self.cheap else FAIL_WORK)
        return self.growth > (WARN_CHEAP if self.cheap else WARN_WORK)


def tables(result: dict[str, Any], block: str) -> dict[str, Table]:
    """Return the tables of one block of a result, by key."""
    for b in result["blocks"]:
        if b["key"] == block:
            return {t["key"]: t for t in b["tables"]}
    return {}


def value(table: Table, row: str, column: str) -> float | None:
    """Return a cell's value, or None where the table has no such cell."""
    cell = table["rows"].get(row, {}).get(column)
    return None if cell is None else float(cell["value"])


def memory_failures(base: dict[str, Any], head: dict[str, Any]) -> Iterator[str]:
    """Yield a line for each memory cell that breaks its bound."""
    before = tables(base, "memory")
    for key, table in tables(head, "memory").items():
        for column in table["columns"]:
            if "Python" not in column:
                continue
            for row in table["rows"]:
                b = value(before.get(key, {"rows": {}}), row, column)
                h = value(table, row, column)
                if b is not None and h is not None and abs(h - b) > MEMORY_SLACK:
                    yield (
                        f"{table['title']} / {row} / {column}: "
                        f"{h:,.0f} B, the base {b:,.0f} B"
                    )
        if key == "batch_memory":
            for column in table["columns"]:
                rise = value(table, "peak resident rise", column)
                bound = value(table, "libphash's bound", column)
                if rise is None or bound is None or rise <= BATCH_FACTOR * bound:
                    continue
                yield (
                    f"{table['title']} / {column}: peak resident rise {rise:,.0f} B, "
                    f"over {BATCH_FACTOR} times libphash's bound of {bound:,.0f} B"
                )


def ratios(base: dict[str, Any], head: dict[str, Any]) -> Iterator[Ratio]:
    """Yield each timed cell of the overhead block that both sides have."""
    before = tables(base, "overhead")
    for key, table in tables(head, "overhead").items():
        if table["unit"] != "s" or key not in before:
            continue
        for row in table["rows"]:
            if row == "C" or row.startswith("C:"):
                continue
            for column in table["columns"]:
                if column == "C":
                    continue
                b, h = (_ratio(t, row, column) for t in (before[key], table))
                if b is None or h is None:
                    continue
                yield Ratio(table["title"], row, column, b[0], h[0], b[1] < CHEAP)


def _ratio(table: Table, row: str, column: str) -> tuple[float, float] | None:
    """Return a cell over its C cell, and the C cell; None without either."""
    if table["baseline_row"]:
        if row == table["baseline_row"]:
            return None
        reference = value(table, table["baseline_row"], column)
    elif "C" in table["columns"]:
        reference = value(table, row, "C")
    else:
        return None
    cell = value(table, row, column)
    if cell is None or not reference:
        return None
    return cell / reference, reference


def main(argv: Sequence[str] | None = None) -> int:
    """Compare the two results; return 1 when a check fails."""
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.gate",
        description="Hold the benchmarks of a pull request to those of its base.",
    )
    parser.add_argument("base", type=Path, help="the base's results (JSON)")
    parser.add_argument("head", type=Path, help="the head's results (JSON)")
    parser.add_argument("--summary", type=Path, help="write a Markdown summary here")
    parser.add_argument(
        "--fail-timing", action="store_true", help="fail on timing, not only warn"
    )
    args = parser.parse_args(argv)
    base = cast("dict[str, Any]", json.loads(args.base.read_text(encoding="utf-8")))
    head = cast("dict[str, Any]", json.loads(args.head.read_text(encoding="utf-8")))

    memory = list(memory_failures(base, head))
    timed = list(ratios(base, head))
    failing = [r for r in timed if args.fail_timing and r.exceeds(fail=True)]
    slower = [r for r in timed if r.exceeds(fail=False)]

    for line in memory:
        print(f"::error title=Memory::{line}")  # noqa: T201 -- an annotation
    for r in slower:
        level = "error" if r in failing else "warning"
        print(  # noqa: T201 -- an annotation
            f"::{level} title=Time::{r.table} / {r.row} / {r.column}: "
            f"{r.growth:+.0%} against C"
        )
    if args.summary:
        args.summary.write_text(_summary(memory, timed, slower), encoding="utf-8")
    return 1 if memory or failing else 0


def _summary(memory: list[str], timed: list[Ratio], slower: list[Ratio]) -> str:
    lines = ["## Benchmarks against the base", "", "### Memory", ""]
    lines += [f"- {m}" for m in memory] or ["Every Python allocation as at the base."]
    lines += ["", "### Time against C", ""]
    if slower:
        lines += ["| Table | Row | Column | Growth |", "|---|---|---|---|"]
        lines += [
            f"| {r.table} | {r.row} | {r.column} | {r.growth:+.1%} |" for r in slower
        ]
    else:
        lines.append(f"No ratio of the {len(timed)} grew past its threshold.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
