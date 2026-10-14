"""The benchmark gate: what it holds a pull request to, on results made up for it."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import gate  # noqa: E402 -- the root joins sys.path above


def cell(value: float) -> dict[str, float]:
    return {"value": value}


def result() -> dict[str, Any]:
    """Return a result with a table of each shape the gate reads."""
    return {
        "environment": {},
        "blocks": [
            {
                "key": "overhead",
                "tables": [
                    {
                        "key": "load_file",
                        "title": "Loading a file",
                        "unit": "s",
                        "baseline_row": "C",
                        "columns": ["400x400"],
                        "rows": {
                            "C": {"400x400": cell(200e-6)},
                            "load_file(str)": {"400x400": cell(220e-6)},
                        },
                    },
                    {
                        "key": "hash_loaded_photo",
                        "title": "Hashing a loaded photo",
                        "unit": "s",
                        "baseline_row": None,
                        "columns": ["C", "hash(Algorithm)"],
                        "rows": {
                            "phash": {"C": cell(2e-6), "hash(Algorithm)": cell(3e-6)},
                        },
                    },
                    {
                        "key": "file_to_hash",
                        "title": "From a file to a hash",
                        "unit": "s",
                        "baseline_row": "C: a new context",
                        "columns": ["400x400"],
                        "rows": {
                            "C: a new context": {"400x400": cell(300e-6)},
                            "C: one context": {"400x400": cell(290e-6)},
                            "hash(path)": {"400x400": cell(310e-6)},
                        },
                    },
                    {
                        "key": "compare",
                        "title": "Comparing",
                        "unit": "s",
                        "baseline_row": None,
                        "columns": ["per call"],
                        "rows": {"similarity()": {"per call": cell(1e-7)}},
                    },
                ],
            },
            {
                "key": "memory",
                "tables": [
                    {
                        "key": "load_memory",
                        "title": "What a load holds",
                        "unit": "B",
                        "columns": ["400x400: Python", "400x400: resident"],
                        "rows": {
                            "load_bytes(bytes)": {
                                "400x400: Python": cell(1000),
                                "400x400: resident": cell(5_000_000),
                            },
                        },
                    },
                    {
                        "key": "batch_memory",
                        "title": "A batch",
                        "unit": "B",
                        "columns": ["threads=2"],
                        "rows": {
                            "peak resident rise": {"threads=2": cell(1_000_000)},
                            "Python allocations": {"threads=2": cell(4000)},
                            "libphash's bound": {"threads=2": cell(1_000_000)},
                        },
                    },
                ],
            },
        ],
    }


def table(res: dict[str, Any], block: str, key: str) -> dict[str, Any]:
    return gate.tables(res, block)[key]


def run(
    tmp_path: Path, base: dict[str, Any], head: dict[str, Any], *flags: str
) -> tuple[int, str]:
    paths: list[str] = []
    for name, res in (("base", base), ("head", head)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(res), encoding="utf-8")
        paths.append(str(path))
    summary = tmp_path / "summary.md"
    status = gate.main([*paths, "--summary", str(summary), *flags])
    return status, summary.read_text(encoding="utf-8")


def test_the_same_results_pass(tmp_path: Path) -> None:
    status, summary = run(tmp_path, result(), result())
    assert status == 0
    assert "Every Python allocation as at the base." in summary
    # Loading a file, hashing pHash, hash(path): C rows, C columns and the table
    # without a C cell are not timed.
    assert "No ratio of the 3 grew past its threshold." in summary


def test_a_new_python_copy_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    head = result()
    rows = table(head, "memory", "load_memory")["rows"]
    rows["load_bytes(bytes)"]["400x400: Python"] = cell(1000 + gate.MEMORY_SLACK + 1)
    # Resident memory varies from run to run and is not held to the base.
    rows["load_bytes(bytes)"]["400x400: resident"] = cell(9_000_000)
    status, summary = run(tmp_path, result(), head)
    assert status == 1
    assert "What a load holds / load_bytes(bytes) / 400x400: Python" in summary
    assert capsys.readouterr().out.startswith("::error title=Memory::")


def test_python_allocations_within_the_slack_pass(tmp_path: Path) -> None:
    head = result()
    rows = table(head, "memory", "load_memory")["rows"]
    rows["load_bytes(bytes)"]["400x400: Python"] = cell(1000 - gate.MEMORY_SLACK)
    assert run(tmp_path, result(), head)[0] == 0


def test_a_batch_over_its_bound_fails(tmp_path: Path) -> None:
    head = result()
    rows = table(head, "memory", "batch_memory")["rows"]
    rows["peak resident rise"]["threads=2"] = cell(1_000_000 * gate.BATCH_FACTOR + 1)
    status, summary = run(tmp_path, head, head)
    assert status == 1
    assert "A batch / threads=2: peak resident rise" in summary


def test_a_slower_runner_is_not_a_regression(tmp_path: Path) -> None:
    head = result()
    for t in gate.tables(head, "overhead").values():
        for cells in t["rows"].values():
            for c in cells.values():
                c["value"] *= 3
    assert run(tmp_path, result(), head, "--fail-timing")[0] == 0


@pytest.mark.parametrize(
    ("key", "row", "column", "cheap"),
    [
        ("load_file", "load_file(str)", "400x400", False),
        ("hash_loaded_photo", "phash", "hash(Algorithm)", True),
    ],
)
def test_thresholds_against_c(  # noqa: PLR0913 -- the case and the fixtures
    *,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    key: str,
    row: str,
    column: str,
    cheap: bool,
) -> None:
    base = result()
    warn = gate.WARN_CHEAP if cheap else gate.WARN_WORK
    fail = gate.FAIL_CHEAP if cheap else gate.FAIL_WORK

    def grown(by: float) -> dict[str, Any]:
        head = copy.deepcopy(base)
        c = table(head, "overhead", key)["rows"][row][column]
        c["value"] *= 1 + by
        return head

    status, summary = run(tmp_path, base, grown(warn * 0.9), "--fail-timing")
    assert status == 0
    assert "No ratio of the 3 grew past its threshold." in summary
    assert not capsys.readouterr().out

    status, summary = run(tmp_path, base, grown(warn * 1.1))
    assert status == 0
    assert f"| {row} | {column} |" in summary
    assert capsys.readouterr().out.startswith("::warning title=Time::")

    assert run(tmp_path, base, grown(warn * 1.1), "--fail-timing")[0] == 0
    status = run(tmp_path, base, grown(fail * 1.1), "--fail-timing")[0]
    assert status == 1
    assert "::error title=Time::" in capsys.readouterr().out


def test_cases_on_one_side_only_are_skipped(tmp_path: Path) -> None:
    head = result()
    rows = table(head, "overhead", "load_file")["rows"]
    rows["load_file(Path)"] = {"400x400": cell(1.0)}
    del rows["load_file(str)"]
    head["blocks"][1]["tables"].pop()
    status, summary = run(tmp_path, result(), head)
    assert status == 0
    assert "No ratio of the 2 grew" in summary
