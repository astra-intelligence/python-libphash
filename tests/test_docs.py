"""The code on the documentation pages and in the README runs.

Each page's ``python`` blocks run in order in one namespace, as a reader would type
them, in a directory holding the images the pages name (copies of libphash's fixtures).
A failure names the page and the block (``loading.md[2]``) in its traceback. A block
included from ``examples/`` is left to tests/test_examples.py.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

import pytest
from conftest import data

ROOT = Path(__file__).resolve().parents[1]
PAGES = [*sorted((ROOT / "docs").rglob("*.md")), ROOT / "README.md"]
BLOCK = re.compile(r"^```python\n(.*?)^```", re.MULTILINE | re.DOTALL)

#: The file names the pages use, and the fixture each one is a copy of.
IMAGES = {
    "photo.jpg": "photo.jpeg",
    "photo_copy.jpg": "photo_copy.jpeg",
    "photo_rotated.jpg": "photo_rotated_90.jpeg",
    "photo.png": "photo.png",
    "broken.jpg": "corrupted.jpg",
}


def blocks(page: Path) -> list[str]:
    text = page.read_text(encoding="utf-8")
    return [b for b in BLOCK.findall(text) if "--8<--" not in b]


def test_pages_have_code() -> None:
    assert sum(len(blocks(p)) for p in PAGES) > 20


@pytest.mark.parametrize(
    "page",
    [p for p in PAGES if blocks(p)],
    ids=lambda p: p.relative_to(ROOT).as_posix(),
)
def test_page_code_runs(
    page: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = blocks(page)
    for module in ("numpy", "PIL"):
        used = any(f"import {module}" in b or f"from {module}" in b for b in code)
        if used and importlib.util.find_spec(module) is None:
            pytest.skip(f"{page.name} needs {module}")
    for name, fixture in IMAGES.items():
        shutil.copy(data(fixture), tmp_path / name)
    monkeypatch.chdir(tmp_path)
    namespace: dict[str, object] = {"__name__": "__docs__"}
    for i, block in enumerate(code):
        # The documentation's own code, run as a reader would.
        exec(compile(block, f"{page.name}[{i}]", "exec"), namespace)  # noqa: S102
