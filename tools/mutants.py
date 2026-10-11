"""Check mutmut's results against the list of equivalent mutants.

Run after ``mutmut run``, from the project root::

    python tools/mutants.py

Every mutant must be caught (killed, timed out or crashed) or be listed in
``tests/equivalent_mutants.json`` with the reason no test can tell it from the original.
The script fails on a mutant that is neither, and on a listed mutant that no longer
survives, so that the list stays true. A mutant is named by its function and the lines
it changes, not by mutmut's number, which shifts when the function changes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EQUIVALENTS = PROJECT_ROOT / "tests" / "equivalent_mutants.json"
CAUGHT = ("killed", "timeout", "segfault")


class _Entry(TypedDict):
    function: str
    reason: str
    mutants: list[list[str]]


@dataclass(frozen=True)
class Mutant:
    """One of mutmut's mutants: its id, its status and what it changes."""

    name: str
    status: str

    @property
    def function(self) -> str:
        """The mutated function as ``module.Class.method`` or ``module.function``."""
        mangled = re.sub(r"__mutmut_\d+$", "", self.name)
        module, _, local = mangled.rpartition(".")
        if local.startswith("xǁ"):
            _, cls, method = local.split("ǁ")
            return f"{module}.{cls}.{method}"
        return f"{module}.{local.removeprefix('x_')}"

    def diff(self) -> tuple[str, ...]:
        """Return the removed and added lines, each stripped after its sign."""
        shown = _mutmut("show", self.name)
        return tuple(
            line[0] + line[1:].strip()
            for line in shown.splitlines()
            if line[:1] in "-+" and not line.startswith(("---", "+++"))
        )


def _mutmut(*args: str) -> str:
    return subprocess.run(  # noqa: S603 -- mutmut from the environment, fixed arguments
        [sys.executable, "-m", "mutmut", *args],
        check=True,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    ).stdout


def results() -> list[Mutant]:
    """Every mutant of the last ``mutmut run`` with its status."""
    mutants: list[Mutant] = []
    for line in _mutmut("results", "--all", "true").splitlines():
        name, sep, status = line.strip().rpartition(": ")
        if sep:
            mutants.append(Mutant(name, status))
    return mutants


def equivalents() -> set[tuple[str, tuple[str, ...]]]:
    """Return the listed equivalent mutants as (function, diff) pairs."""
    with EQUIVALENTS.open(encoding="utf-8") as f:
        listed: list[_Entry] = json.load(f)["equivalent"]
    return {
        (entry["function"], tuple(diff))
        for entry in listed
        for diff in entry["mutants"]
    }


def main() -> int:
    """Report the mutants; return 1 if any is unexplained or the list is stale."""
    mutants = results()
    if not mutants:
        sys.stderr.write("no mutmut results: run `mutmut run` first\n")
        return 1
    listed = equivalents()
    unexplained: list[tuple[Mutant, tuple[str, ...]]] = []
    equivalent: set[tuple[str, tuple[str, ...]]] = set()
    for mutant in mutants:
        if mutant.status in CAUGHT:
            continue
        key = (mutant.function, mutant.diff())
        if mutant.status == "survived" and key in listed:
            equivalent.add(key)
        else:
            unexplained.append((mutant, key[1]))
    stale = sorted(listed - equivalent)

    counts = Counter(m.status for m in mutants)
    caught = sum(counts[s] for s in CAUGHT)
    lines = [
        "## Mutation testing",
        "",
        f"{len(mutants)} mutants: {caught} caught "
        f"({100 * caught / len(mutants):.1f} %), {len(equivalent)} equivalent, "
        f"{len(unexplained)} unexplained.",
        "",
        ", ".join(f"{status}: {n}" for status, n in sorted(counts.items())),
    ]
    for mutant, diff in unexplained:
        lines += ["", f"### {mutant.name} ({mutant.status})", "", "```diff"]
        lines += [*diff, "```"]
    for function, diff in stale:
        lines += ["", f"### listed but not surviving: {function}", "", "```diff"]
        lines += [*diff, "```"]
    report = "\n".join(lines)
    sys.stdout.write(report + "\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report + "\n")
    return 1 if unexplained or stale else 0


if __name__ == "__main__":
    sys.exit(main())
