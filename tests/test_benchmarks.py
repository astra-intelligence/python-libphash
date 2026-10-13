"""The benchmarks run: every block in the quick mode, written as JSON and Markdown.

The quick mode runs each case once on small inputs, so that the harness cannot fall
out of step with the binding; its times mean nothing. With the libphash install of an
editable build, the C side is built and its rows are filled; CI requires it through
``LIBPHASH_REQUIRE_C_REFERENCE``, as the parity tests do.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import pytest
from conftest import SANITIZER

import libphash as ph

pytest.importorskip("numpy", reason="the benchmarks hold pixels and hashes in numpy")
pytest.importorskip("PIL", reason="the benchmarks decode pixels with Pillow")
pytest.importorskip("psutil", reason="the memory benchmarks read resident memory")
pytestmark = pytest.mark.skipif(
    SANITIZER is not None, reason="under a sanitizer, timing measures the sanitizer"
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks import __main__ as cli  # noqa: E402 -- the root joins sys.path above
from benchmarks.report import Unit, fmt  # noqa: E402 -- as above

BLOCKS = cli.BLOCKS


@pytest.mark.parametrize("block", BLOCKS)
def test_block_runs_and_writes_its_tables(block: str, tmp_path: Path) -> None:
    argv = ["--quick", "--blocks", block, "--out", str(tmp_path), "--name", "quick"]
    assert cli.main(argv) == 0
    result = json.loads((tmp_path / "quick.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "quick.md").read_text(encoding="utf-8")

    assert result["environment"]["build_info"] == ph.build_info()
    assert markdown.startswith("## Environment\n")
    (written,) = result["blocks"]
    assert written["key"] == block
    assert written["tables"]
    for table in written["tables"]:
        assert f"### {table['title']}" in markdown
        assert table["rows"], table["key"]
        for row, cells in table["rows"].items():
            for cell in cells.values():
                assert math.isfinite(cell["value"]), (table["key"], row)
                if table["unit"] in ("s", "/s"):
                    assert cell["value"] > 0, (table["key"], row)
    if os.environ.get("LIBPHASH_REQUIRE_C_REFERENCE"):
        assert not any(n.startswith("The C rows are empty") for n in written["notes"])


def test_c_side_fills_its_rows(tmp_path: Path) -> None:
    from benchmarks.cbench import CBench  # noqa: PLC0415 -- after the path is set

    cbench = CBench()
    if cbench.exe is None:
        if os.environ.get("LIBPHASH_REQUIRE_C_REFERENCE"):
            pytest.fail(cbench.reason, pytrace=False)
        pytest.skip(cbench.reason)
    assert cli.main(["--quick", "--blocks", "search", "--out", str(tmp_path)]) == 0
    result = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    (search,) = result["blocks"]
    for table in search["tables"]:
        c_rows = [r for r in table["rows"] if r.startswith("C ")]
        for row in c_rows:
            assert table["rows"][row], (table["key"], row)


def test_unknown_block_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--quick", "--blocks", "nothing", "--out", str(tmp_path)])


@pytest.mark.parametrize(
    ("value", "unit", "text"),
    [
        (1.5e-9, "s", "1.5 ns"),
        (2.5e-6, "s", "2.5 µs"),
        (0.0123, "s", "12.3 ms"),
        (3.0, "s", "3 s"),
        (512, "B", "512 B"),
        (3 * 2**20, "B", "3 MiB"),
        (1234.4, "/s", "1,234/s"),
        (0.25, "ms", "0.25 ms"),
        (float("nan"), "s", "—"),
    ],
)
def test_values_print_in_their_unit(value: float, unit: Unit, text: str) -> None:
    assert fmt(value, unit) == text
