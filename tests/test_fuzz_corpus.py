"""The fuzz corpus, replayed: every input of tests/fuzz/ holds its target's property.

tools/fuzz.py runs the targets under atheris in the sanitizer job; here their corpus,
inputs found by fuzzing included, runs on every platform without atheris.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import fuzz_targets  # noqa: E402 -- tools/ joins sys.path just above


def corpus(target: str) -> list[Path]:
    dirs = fuzz_targets.seed_dirs(target)
    return sorted(p for d in dirs if d.is_dir() for p in d.iterdir() if p.is_file())


CASES = [
    pytest.param(target, path, id=f"{target}/{path.name}")
    for target in fuzz_targets.TARGETS
    for path in corpus(target)
]


@pytest.mark.parametrize(("target", "path"), CASES)
def test_corpus_input(target: str, path: Path) -> None:
    if target == "pixels":
        pytest.importorskip("numpy")
    fuzz_targets.TARGETS[target](path.read_bytes())


def test_every_target_has_a_corpus() -> None:
    assert all(corpus(target) for target in fuzz_targets.TARGETS)


def test_ci_fuzzes_every_target() -> None:
    workflows = ROOT / ".github" / "workflows"
    loop = re.search(r"for target in (.+); do", (workflows / "ci.yml").read_text())
    matrix = re.search(r"target: \[ (.+) \]", (workflows / "fuzz.yml").read_text())
    assert loop is not None
    assert matrix is not None
    assert loop.group(1).split() == list(fuzz_targets.TARGETS)
    assert [t.strip() for t in matrix.group(1).split(",")] == list(fuzz_targets.TARGETS)
