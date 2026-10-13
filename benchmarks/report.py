"""Results: tables of measured values, written as JSON and as Markdown.

A :class:`Table` holds one question: its rows are the ways of doing a piece of work,
its columns the sizes or worker counts it is done at. A table may name a baseline row
or column (C, one worker), and the Markdown then shows every other cell against it.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pathlib import Path

    from .timing import Timing

#: ``s``: seconds per item; ``B``: bytes; ``/s``: items per second; ``ms``: a delay;
#: ``n``: a count.
Unit = Literal["s", "B", "/s", "ms", "n"]


@dataclass
class Cell:
    """One measured value, with the median and the number of runs of a timing."""

    value: float
    median: float | None = None
    runs: int | None = None


@dataclass
class Table:
    """One question and its measured answers."""

    key: str
    title: str
    about: str
    unit: Unit
    #: A row or column that the other cells are shown against.
    baseline_row: str | None = None
    baseline_column: str | None = None
    rows: dict[str, dict[str, Cell]] = field(default_factory=dict[str, dict[str, Cell]])
    columns: list[str] = field(default_factory=list[str])

    def add(self, row: str, column: str, value: float | Timing | None) -> None:
        """Record a value; None (a case that cannot run here) leaves the cell empty."""
        if column not in self.columns:
            self.columns.append(column)
        cells = self.rows.setdefault(row, {})
        if value is None:
            return
        if isinstance(value, (int, float)):
            cells[column] = Cell(float(value))
        else:
            cells[column] = Cell(value.minimum, value.median, value.runs)

    def get(self, row: str, column: str) -> float | None:
        """Return a cell's value, or None."""
        cell = self.rows.get(row, {}).get(column)
        return cell.value if cell else None


@dataclass
class Block:
    """One section of the results: its tables and what they show."""

    key: str
    title: str
    tables: list[Table] = field(default_factory=list[Table])
    notes: list[str] = field(default_factory=list[str])

    def table(  # noqa: PLR0913 -- a table's fields, by name
        self,
        key: str,
        title: str,
        about: str,
        unit: Unit,
        *,
        baseline_row: str | None = None,
        baseline_column: str | None = None,
    ) -> Table:
        """Add a table and return it."""
        t = Table(key, title, about, unit, baseline_row, baseline_column)
        self.tables.append(t)
        return t


@dataclass
class Report:
    """Every block that ran, and the environment it ran in."""

    environment: dict[str, object]
    blocks: list[Block] = field(default_factory=list[Block])


# --- Formatting ----------------------------------------------------------------------


def _num(x: float) -> str:
    """Return three significant digits, never in exponent notation."""
    if x < 0.001:
        return "0"
    text = f"{x:.3g}"
    # 999.6 rounds to "1e+03" in three digits.
    return f"{x:.0f}" if "e" in text else text


def _seconds(v: float) -> str:
    for scale, unit in ((1.0, "s"), (1e-3, "ms"), (1e-6, "µs")):
        if v >= scale:
            return f"{_num(v / scale)} {unit}"
    return f"{_num(v / 1e-9)} ns"


def _bytes(v: float) -> str:
    sign = "-" if v < 0 else ""
    v = abs(v)
    for scale, unit in ((2**30, "GiB"), (2**20, "MiB"), (2**10, "KiB")):
        if v >= scale:
            return f"{sign}{_num(v / scale)} {unit}"
    return f"{sign}{v:.0f} B"


def fmt(value: float, unit: Unit) -> str:
    """Return a value in its unit, with three significant digits."""
    if math.isnan(value):
        return "—"
    if unit == "s":
        return _seconds(value)
    if unit == "B":
        return _bytes(value)
    if unit == "/s":
        return f"{value:,.0f}/s"
    if unit == "ms":
        return f"{_num(value)} ms"
    return f"{value:,.6g}"


def _against(value: float, base: float, unit: Unit) -> str:
    """Return a value set against the baseline's."""
    if unit == "s":
        diff = value - base
        sign = "+" if diff >= 0 else "−"
        return f"{sign}{_seconds(abs(diff))}, ×{_num(value / base)}" if base else ""
    if unit == "/s" and base:
        return f"×{_num(value / base)}"
    return ""


def _cell(table: Table, row: str, column: str) -> str:
    cell = table.rows[row].get(column)
    if cell is None:
        return "—"
    text = fmt(cell.value, table.unit)
    if table.unit == "s" and cell.median is not None:
        text += f" / {fmt(cell.median, 's')}"
    base: float | None = None
    if table.baseline_row is not None and row != table.baseline_row:
        base = table.get(table.baseline_row, column)
    elif table.baseline_column is not None and column != table.baseline_column:
        base = table.get(row, table.baseline_column)
    if base is not None:
        against = _against(cell.value, base, table.unit)
        if against:
            text += f" ({against})"
    return text


def table_markdown(table: Table) -> str:
    """Return a table as Markdown: a heading, what it answers, the grid."""
    lines = [f"### {table.title}", "", table.about, ""]
    lines.append("| | " + " | ".join(table.columns) + " |")
    lines.append("| --- |" + " --- |" * len(table.columns))
    lines += [
        f"| {row} | " + " | ".join(_cell(table, row, c) for c in table.columns) + " |"
        for row in table.rows
    ]
    return "\n".join(lines)


def markdown(report: Report) -> str:
    """Return the whole report as Markdown, the environment first."""
    env = report.environment
    out = ["## Environment", ""]
    out += [f"- **{key}:** {value}" for key, value in env.items()]
    out += [
        "",
        "A time is the minimum / the median of the runs, per item of work; in "
        "parentheses, the difference from the baseline and the ratio to it.",
    ]
    for block in report.blocks:
        out += ["", f"## {block.title}"]
        out += [f"\n{note}" for note in block.notes]
        for table in block.tables:
            out += ["", table_markdown(table)]
    return "\n".join(out) + "\n"


def write(report: Report, out_dir: Path, name: str) -> tuple[Path, Path]:
    """Write ``<name>.json`` and ``<name>.md`` into ``out_dir``; return both paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    js = out_dir / f"{name}.json"
    md = out_dir / f"{name}.md"
    js.write_text(json.dumps(asdict(report), indent=1) + "\n", encoding="utf-8")
    md.write_text(markdown(report), encoding="utf-8")
    return js, md
