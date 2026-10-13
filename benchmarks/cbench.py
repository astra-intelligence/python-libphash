"""The C side of the benchmarks: ``benchmarks/c/bench.c``, built and run.

The program is built against the libphash install that the extension links
(``tools/native.py``), the way ``tests/c_reference.py`` builds the parity tests'
reference, so that a C time and the binding's time are those of one build. Without the
install (an installed wheel) or CMake, the C cells of the tables stay empty.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import libphash as ph

from .fixtures import ROOT
from .timing import Timing

sys.path.insert(0, str(ROOT / "tools"))
import native

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from .timing import Effort


class CUnavailableError(Exception):
    """The C side cannot be built here; the message says why."""


def build() -> Path:
    """Build the program if needed and return it."""
    prefix = native.build_dir() / "install"
    if next(prefix.glob("lib*/cmake/phash"), None) is None:
        raise CUnavailableError(f"no libphash install in {prefix}")
    cmake = shutil.which("cmake")
    if cmake is None:
        raise CUnavailableError("CMake is not on PATH")
    out = native.build_dir() / "bench"
    if native.tools_missing(out):
        shutil.rmtree(out)
    commands: list[list[str]] = []
    if not (out / "CMakeCache.txt").exists():
        configure = [
            cmake,
            "-S",
            str(ROOT / "benchmarks" / "c"),
            "-B",
            str(out),
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_PREFIX_PATH={prefix}",
            *native.generator(),
        ]
        archs = native.osx_architectures()
        if archs:
            configure.append(f"-DCMAKE_OSX_ARCHITECTURES={archs}")
        commands.append(configure)
    commands.append([cmake, "--build", str(out), "--config", "Release"])
    for command in commands:
        run = subprocess.run(command, capture_output=True, text=True, check=False)
        if run.returncode:
            raise CUnavailableError(f"building it failed:\n{run.stdout}{run.stderr}")
    for exe in (out / "bench", out / "Release" / "bench.exe"):
        if exe.exists():
            return exe
    raise CUnavailableError(f"the program is not in {out}")


class CBench:
    """The built program, or the reason it is missing."""

    def __init__(self) -> None:
        self.exe: Path | None = None
        self.reason = ""
        try:
            exe = build()
        except CUnavailableError as e:
            self.reason = str(e)
            return
        run = subprocess.run(
            [str(exe), "1", "0"],
            input="build_info\n",
            capture_output=True,
            text=True,
            check=False,
        )
        # Both sides must link the same build: an install rebuilt with other options,
        # or a stale extension, would compare two libraries.
        if run.stdout.strip() != ph.build_info():
            self.reason = (
                f"it links {run.stdout.strip()!r}, the extension {ph.build_info()!r}"
            )
            return
        self.exe = exe

    def time(
        self, cases: Sequence[Sequence[object]], effort: Effort
    ) -> list[Timing | None]:
        """Time each case (its fields, as bench.c reads them); None where it fails."""
        if self.exe is None:
            return [None] * len(cases)
        lines = ["\t".join(map(str, case)) + "\n" for case in cases]
        run = subprocess.run(
            [str(self.exe), str(effort.min_runs), str(effort.min_seconds)],
            input="".join(lines),
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode:
            raise RuntimeError(f"benchmarks/c/bench.c failed:\n{run.stderr}")
        out: list[Timing | None] = []
        for line in run.stdout.splitlines():
            if line.startswith("error"):
                out.append(None)
                continue
            values = json.loads(line)
            out.append(Timing(values["min"], values["median"], values["runs"]))
        if len(out) != len(cases):
            raise RuntimeError(
                f"benchmarks/c/bench.c answered too few cases:\n{run.stderr}"
            )
        return out
