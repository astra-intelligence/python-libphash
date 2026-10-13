"""The command line of the benchmarks; ``python -m benchmarks --help``."""

from __future__ import annotations

import argparse
import platform
import sys
import sysconfig
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from . import memory, overhead, parallel, search, startup
from .cbench import CBench
from .fixtures import ROOT, environment, images
from .report import Report, write
from .timing import FULL, QUICK

if TYPE_CHECKING:
    from collections.abc import Sequence

BLOCKS = ("overhead", "search", "memory", "parallel", "startup")


def default_name() -> str:
    """Return the results' name for this platform and Python: ``darwin-arm64-cp312``."""
    tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        tag += "t"
    return f"{sys.platform}-{platform.machine().lower()}-{tag}"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the blocks asked for and write their results."""
    parser = argparse.ArgumentParser(prog="python -m benchmarks", description=__doc__)
    parser.add_argument(
        "--blocks",
        default=",".join(BLOCKS),
        help=f"comma-separated, of {', '.join(BLOCKS)} (default: all)",
    )
    parser.add_argument(
        "--quick", action="store_true", help="run every case once, on small inputs"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "benchmarks" / "results",
        help="output directory",
    )
    parser.add_argument("--name", default=default_name(), help="the files' name")
    parser.add_argument(
        "--wheel",
        type=Path,
        action="append",
        default=[],
        help="a wheel to report the size of",
    )
    args = parser.parse_args(argv)
    blocks = [b.strip() for b in str(args.blocks).split(",") if b.strip()]
    unknown = set(blocks) - set(BLOCKS)
    if unknown:
        parser.error(f"unknown blocks: {', '.join(sorted(unknown))}")
    effort = QUICK if args.quick else FULL
    report = Report(environment(effort))
    with tempfile.TemporaryDirectory(prefix="libphash-bench-") as tmp:
        imgs = images(effort, Path(tmp))
        cbench = CBench() if {"overhead", "search"} & set(blocks) else None
        for name in blocks:
            print(f"benchmarks: {name}", file=sys.stderr)  # noqa: T201 -- progress
            if name == "overhead":
                assert cbench is not None  # noqa: S101 -- built above
                report.blocks.append(overhead.run(imgs, cbench, effort))
            elif name == "search":
                assert cbench is not None  # noqa: S101 -- built above
                report.blocks.append(search.run(cbench, effort))
            elif name == "memory":
                report.blocks.append(memory.run(imgs, effort))
            elif name == "parallel":
                report.blocks.append(parallel.run(imgs, effort))
            else:
                report.blocks.append(startup.run(effort, args.wheel))
    js, md = write(report, args.out, args.name)
    print(f"benchmarks: wrote {js}, {md}", file=sys.stderr)  # noqa: T201 -- the outcome
    return 0


if __name__ == "__main__":
    sys.exit(main())
