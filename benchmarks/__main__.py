"""Command line: ``python -m benchmarks {quality,speed,overhead,all}``."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .contenders import contenders
from .environment import environment
from .overhead import measure_overhead
from .quality import measure_quality
from .report import overhead_md, quality_md, speed_md
from .site import MIRROR_COMMIT, CorpusError, photos
from .speed import measure_speed
from .timing import MIN_RUNS, MIN_SECONDS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from _typeshed import DataclassInstance

OUT = Path(__file__).resolve().parent.parent / "build" / "benchmarks"
#: Photographs the speed benchmark times, out of the corpus.
SPEED_IMAGES = 50


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m benchmarks",
        description="Benchmark libphash against other perceptual hashing libraries.",
    )
    p.add_argument("benchmark", choices=("quality", "speed", "overhead", "all"))
    p.add_argument(
        "--images",
        nargs="+",
        metavar="PATH",
        help="measure these images instead of the photo corpus",
    )
    p.add_argument(
        "--limit", type=int, metavar="N", help="use the first N photographs only"
    )
    p.add_argument(
        "--cache",
        metavar="DIR",
        help="the photo corpus's cache (the site's by default)",
    )
    p.add_argument(
        "--only",
        nargs="+",
        metavar="KEY",
        help="contenders to measure, as library/algorithm (libphash/pHash)",
    )
    p.add_argument("--workers", type=int, help="processes for the quality benchmark")
    p.add_argument("--quick", action="store_true", help="one run per timing")
    p.add_argument("--out", type=Path, default=OUT, help=f"output directory ({OUT})")
    return p


def _write(out: Path, name: str, result: DataclassInstance, markdown: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    data = dataclasses.asdict(result)
    (out / f"{name}.json").write_text(json.dumps(data) + "\n", encoding="utf-8")
    (out / f"{name}.md").write_text(markdown, encoding="utf-8")
    print(markdown)  # noqa: T201 -- the command's output


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmarks ``argv`` asks for; the exit status."""
    args = _parser().parse_args(argv)
    run = args.benchmark
    # The overhead benchmark times the test suite's photograph, not the corpus.
    on_corpus = run != "overhead" and not args.images
    try:
        paths = photos(args.cache) if on_corpus else list(args.images or [])
    except CorpusError as e:
        print(f"error: {e}", file=sys.stderr)  # noqa: T201
        return 1
    if args.limit is not None:
        paths = paths[: args.limit]
    env = environment(MIRROR_COMMIT if on_corpus else None)
    chosen = contenders()
    if args.only:
        chosen = [c for c in chosen if c.key in set(args.only)]
    min_runs, min_seconds = (1, 0.0) if args.quick else (MIN_RUNS, MIN_SECONDS)
    if run in ("quality", "all"):
        q = measure_quality(paths, chosen, workers=args.workers)
        _write(args.out, "quality", q, quality_md(q, env))
    if run in ("speed", "all"):
        s = measure_speed(
            paths[:SPEED_IMAGES], chosen, min_runs=min_runs, min_seconds=min_seconds
        )
        _write(args.out, "speed", s, speed_md(s, env))
    if run in ("overhead", "all"):
        o = measure_overhead(min_runs=min_runs, min_seconds=min_seconds)
        _write(args.out, "overhead", o, overhead_md(o, env))
    return 0


if __name__ == "__main__":
    sys.exit(main())
