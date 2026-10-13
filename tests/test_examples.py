"""Every example runs and prints what its docstring shows; the twins print what C does.

An example's docstring holds the command that runs it from the repository root
(``python examples/<name>.py ...``, after a line ending in ``::``) and its output (after
``prints::``). The output was written with libjpeg-turbo decoding JPEG, so a build that
decodes it with stb_image only checks that the examples run. Four examples are twins of
libphash's own C examples, built with the C reference against the same install: each
pair is given the same images, and prints the same lines.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import c_reference
import pytest
from conftest import libjpeg_turbo

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "examples").glob("*.py"))
TWINS = ("load_sources", "configure", "hash_distance", "find_duplicates")


def docstring_blocks(path: Path) -> tuple[list[str], list[str]]:
    """Return an example's command (its arguments) and the output it shows."""
    doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
    command = re.search(r"::\n\n    python (examples/\S+\.py[^\n]*)", doc)
    output = re.search(r"prints::\n\n((?:    .*\n?|\n)+)", doc)
    assert command, f"{path.name}: no command in the docstring"
    assert output, f"{path.name}: no output in the docstring"
    lines = [
        line.removeprefix("    ") for line in output.group(1).rstrip().splitlines()
    ]
    return command.group(1).split(), lines


def arguments(args: list[str], tmp_path: Path) -> list[str]:
    """Point an argument that names no existing file (a file to write) into tmp_path."""
    out: list[str] = []
    for arg in args:
        exists = (ROOT / arg).exists() or not re.fullmatch(r"[\w.-]+\.\w+", arg)
        out.append(arg if exists else str(tmp_path / arg))
    return out


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- the test's own interpreter or a built example
        args, cwd=ROOT, capture_output=True, text=True, check=False
    )


def needs_modules(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                top = name.split(".")[0]
                if top and importlib.util.find_spec(top) is None:
                    pytest.skip(f"{path.name} needs {top}")


def test_every_example_is_listed() -> None:
    readme = (ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    for path in EXAMPLES:
        assert f"({path.name})" in readme, path.name


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_prints_its_documented_output(path: Path, tmp_path: Path) -> None:
    needs_modules(path)
    args, expected = docstring_blocks(path)
    done = run([sys.executable, *arguments(args, tmp_path)])
    assert done.returncode == 0, done.stderr
    if not libjpeg_turbo():
        pytest.skip("the documented output is libjpeg-turbo's")
    assert done.stdout.splitlines() == expected


@pytest.fixture(scope="module")
def c_examples() -> Path:
    return c_reference.build_reference().parent


def c_example(directory: Path, name: str) -> Path:
    for exe in (directory / name, directory / "Release" / f"{name}.exe"):
        if exe.exists():
            return exe
    pytest.fail(f"the C example {name} is not in {directory}")


@pytest.mark.parametrize("name", TWINS)
def test_python_twin_prints_what_c_prints(
    name: str, c_examples: Path, tmp_path: Path
) -> None:
    path = ROOT / "examples" / f"{name}.py"
    needs_modules(path)
    args, _ = docstring_blocks(path)
    args = arguments(args, tmp_path)
    python = run([sys.executable, *args])
    c = run([str(c_example(c_examples, name)), *args[1:]])
    assert python.returncode == c.returncode == 0, python.stderr + c.stderr
    if name == "configure":
        # The Python twin shows Config instead of setters; the hashes and the digest
        # size are the lines the two have in common.
        common = [line for line in python.stdout.splitlines() if "pHash" in line]
        common.append("BMH digest at block_size 8: 8 bytes")
        assert set(common) <= set(c.stdout.splitlines())
    elif name == "find_duplicates":
        # C sorts the pairs with qsort, which may order pairs of equal distance either
        # way.
        assert sorted(python.stdout.splitlines()) == sorted(c.stdout.splitlines())
    else:
        assert python.stdout == c.stdout
