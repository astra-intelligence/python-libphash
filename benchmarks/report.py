"""The benchmarks' results as Markdown tables, ready for the README and the site."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from .quality import summarize
from .site import COPY_STRENGTHS, RECALL

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .environment import Environment
    from .overhead import OverheadResult
    from .quality import QualityResult
    from .speed import SpeedResult

#: The order algorithm families are listed in.
FAMILIES = (
    "aHash",
    "dHash",
    "pHash",
    "wHash",
    "PDQ",
    "BMH",
    "mHash",
    "Radial",
    "ColorHash",
    "ColorMoments",
)
LIBRARIES = ("libphash", "imagehash", "OpenCV", "pdqhash")


def table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Return a Markdown table; columns after the first two are right-aligned."""
    align = ["---" if i < 2 else "---:" for i in range(len(header))]
    lines = [header, align, *rows]
    return "\n".join("| " + " | ".join(line) + " |" for line in lines) + "\n"


def _order(library: str, algorithm: str) -> tuple[int, int]:
    family = FAMILIES.index(algorithm) if algorithm in FAMILIES else len(FAMILIES)
    lib = LIBRARIES.index(library) if library in LIBRARIES else len(LIBRARIES)
    return family, lib


def environment_md(env: Environment, images: int | None = None) -> str:
    """Return the lines that say what a table was measured on."""
    m = env.machine
    packages = ", ".join(f"{name} {version}" for name, version in env.packages.items())
    lines = [
        f"- Machine: {m['cpu']}, {m['cores']} cores, {m['os']}",
        f"- {env.python}; {packages}",
        f"- libphash: `{env.libphash}`",
    ]
    if env.corpus is not None:
        count = f"{images} photographs" if images is not None else "photographs"
        lines.append(
            f"- Corpus: {count} of libphash's site, copy at commit `{env.corpus[:12]}`"
        )
    lines.append(f"- Measured on {env.date}")
    return "\n".join(lines) + "\n"


def quality_md(result: QualityResult, env: Environment) -> str:
    """Return the separability table and the tables of edits."""
    values = sorted(result.contenders, key=lambda c: _order(c.library, c.algorithm))
    summaries = [(c, summarize(c)) for c in values]
    recall = f"{RECALL:.0%}"
    out = [
        "## Separability\n",
        environment_md(env, result.images),
        f"A copy is a photograph after one moderate edit ({_copies()}). d′ is the gap "
        "between the copies' and the different photographs' values in units of their "
        f"spread; the threshold accepts {recall} of the copies, and the last column "
        "is the share of pairs of different photographs it also accepts. Higher d′ "
        "and fewer false accepts are better.\n",
        table(
            ["Algorithm", "Library", "Metric", "d′", f"False accepts at {recall}"],
            [
                [
                    c.algorithm,
                    c.library,
                    c.metric if c.bits is None else f"{c.metric} (of {c.bits})",
                    f"{s.dprime:.2f}",
                    f"{s.false_accepts:.2%}",
                ]
                for c, s in summaries
            ],
        ),
    ]
    refused = [(c, s.refused) for c, s in summaries if s.refused]
    if refused:
        notes = "; ".join(f"{c.key}: {n}" for c, n in refused)
        out.append(f"Comparisons the library refuses, left out: {notes}.\n")
    for group, title, lead in (
        (
            "transform",
            "## Edits a copy goes through",
            "The share of each edit's variants, over every strength, that the "
            "threshold above accepts as a copy. Higher is more robust.",
        ),
        (
            "content",
            "## Edits that change the picture",
            "The share accepted as a copy of an edit that changes what the picture "
            "shows. Whether a hash should accept it depends on the use.",
        ),
    ):
        names = [e.name for e in values[0].edits if e.group == group] if values else []
        out += [
            f"\n{title}\n",
            lead + "\n",
            table(
                ["Algorithm", "Library", *names],
                [
                    [c.algorithm, c.library, *(f"{s.accepted[n]:.0%}" for n in names)]
                    for c, s in summaries
                ],
            ),
        ]
    return "\n".join(out)


def _copies() -> str:
    return ", ".join(
        f"{name} {strength:g}" for name, strength in COPY_STRENGTHS.items()
    )


def speed_md(result: SpeedResult, env: Environment) -> str:
    """Return the median time per photograph of every contender, and libphash's ways."""
    by_family: dict[str, dict[str, float]] = {}
    for case in result.cases:
        if case.how == "":
            by_family.setdefault(case.algorithm, {})[case.library] = case.time.median
    libraries = [
        lib for lib in LIBRARIES if any(lib in times for times in by_family.values())
    ]

    def cell(times: dict[str, float], lib: str) -> str:
        if lib not in times:
            return ""
        ms = f"{times[lib] * 1e3:.2f} ms"
        base = times.get("libphash")
        if lib == "libphash" or base is None:
            return ms
        return f"{ms} ({times[lib] / base:.1f}×)"

    families = sorted(by_family, key=lambda f: _order("", f))
    batches = [c for c in result.cases if c.how != ""]
    return "\n".join(
        [
            "## Time to hash a photograph\n",
            environment_md(env, result.images),
            "Median time per photograph, decoding included, on one thread; in "
            "parentheses, how many times libphash's time.\n",
            table(
                ["Algorithm", *libraries],
                [
                    [f, *(cell(by_family[f], lib) for lib in libraries)]
                    for f in families
                ],
            ),
            "\nlibphash's four 64-bit hashes (aHash, dHash, pHash, wHash) of each "
            "photograph:\n",
            table(
                ["How", "Per photograph"],
                [[c.how, f"{c.time.median * 1e3:.2f} ms"] for c in batches],
            ),
        ]
    )


def overhead_md(result: OverheadResult, env: Environment) -> str:
    """Return the time of every way of doing each job, against the bare C call."""
    rows = [
        [
            c.job,
            c.how,
            f"{c.time.median * 1e6:.2f} µs",
            f"{c.time.minimum * 1e6:.2f} µs",
        ]
        for c in result.cases
    ]
    return "\n".join(
        [
            "## What the binding adds\n",
            environment_md(dataclasses.replace(env, corpus=None)),
            "Each job on a 400×400 JPEG, through the binding and as the bare C call "
            "through cffi; per call or per image.\n",
            table(["Job", "How", "Median", "Minimum"], rows),
        ]
    )
