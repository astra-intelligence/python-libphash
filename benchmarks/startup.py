"""Starting and installing: the time of ``import libphash``, the size of the package.

The import is timed in fresh interpreters, against an interpreter that imports nothing;
``-X importtime`` gives the part of it that is libphash's own modules and the extension.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import libphash as ph

from .fixtures import ROOT
from .report import Block
from .timing import Effort, measure

if TYPE_CHECKING:
    from collections.abc import Sequence


def _python(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, check=True, cwd=ROOT
    )


def _importtime() -> float:
    """Return the cumulative import time of libphash by ``-X importtime``, seconds."""
    err = _python("-X", "importtime", "-c", "import libphash").stderr
    for line in err.splitlines():
        m = re.match(r"import time:\s+\d+ \|\s+(\d+) \|\s*libphash$", line)
        if m:
            return int(m.group(1)) * 1e-6
    raise RuntimeError(f"no libphash line in -X importtime:\n{err}")


def run(effort: Effort, wheels: Sequence[Path] = ()) -> Block:
    """Measure every table of the block."""
    block = Block("startup", "5. Starting and installing")
    imports = block.table(
        "import",
        "import libphash",
        "A fresh interpreter that imports libphash, against one that imports nothing; "
        "-X importtime's cumulative time of the package.",
        "s",
        baseline_row="python -c pass",
    )
    proc = Effort(
        min_runs=max(effort.min_runs, 1),
        min_seconds=effort.min_seconds,
        quick=effort.quick,
    )
    imports.add(
        "python -c pass", "wall time", measure(lambda: _python("-c", "pass"), 1, proc)
    )
    imports.add(
        "python -c 'import libphash'",
        "wall time",
        measure(lambda: _python("-c", "import libphash"), 1, proc),
    )
    runs = effort.scale(10, 1)
    times = sorted(_importtime() for _ in range(runs))
    imports.add("python -c 'import libphash'", "-X importtime, the package", times[0])

    sizes = block.table(
        "size",
        "Size",
        "The extension module (libphash and its decoders, linked statically) and, when "
        "given, the wheel.",
        "B",
    )
    spec = importlib.util.find_spec("libphash._native")
    if spec is None or spec.origin is None:
        raise RuntimeError("the extension module libphash._native is not found")
    ext = Path(spec.origin)
    sizes.add(f"extension module ({ext.name})", "bytes", ext.stat().st_size)
    package = Path(ph.__file__).parent
    python_files = sum(p.stat().st_size for p in package.glob("*.py"))
    sizes.add("the package's .py files", "bytes", python_files)
    for wheel in wheels:
        sizes.add(f"wheel ({wheel.name})", "bytes", os.path.getsize(wheel))
    return block
