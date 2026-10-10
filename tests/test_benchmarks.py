"""The benchmarks run end to end on the test images, and their stubs match the site."""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

pytest.importorskip("PIL", reason="the benchmarks decode with Pillow")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from conftest import data  # noqa: E402

from benchmarks import __main__ as cli  # noqa: E402 -- the root joins sys.path above
from benchmarks import site  # noqa: E402
from benchmarks.contenders import contenders, libphash_contenders  # noqa: E402
from benchmarks.quality import measure_quality, summarize  # noqa: E402

if TYPE_CHECKING:
    from types import ModuleType

STUBS = ROOT / "benchmarks" / "stubs"
#: Stubs of libphash's site tooling, which the submodule's tag fixes.
SITE_STUBS = (
    "fetch_corpus",
    "measure.separability",
    "measure.timing",
    "measure.transforms",
)


def _images() -> list[str]:
    return [str(data(n)) for n in ("photo.jpeg", "photo_complex.png", "photo.webp")]


def _stub(module: str) -> ast.Module:
    path = STUBS.joinpath(*module.split("."))
    path = path / "__init__.pyi" if path.is_dir() else path.with_suffix(".pyi")
    return ast.parse(path.read_text(encoding="utf-8"))


def _parameters(node: ast.FunctionDef) -> list[tuple[str, bool]]:
    """Return each positional parameter's name and whether it has a default."""
    args = node.args.posonlyargs + node.args.args
    first_default = len(args) - len(node.args.defaults)
    return [(a.arg, i >= first_default) for i, a in enumerate(args)]


@pytest.mark.parametrize("module", SITE_STUBS)
def test_stub_functions_match_the_site(module: str) -> None:
    real: ModuleType = importlib.import_module(module)
    for node in _stub(module).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        fn = getattr(real, node.name, None)
        assert callable(fn), f"{module}.{node.name} is not in the site's code"
        signature = inspect.signature(fn)
        actual = [
            (p.name, p.default is not inspect.Parameter.empty)
            for p in signature.parameters.values()
        ]
        assert actual == _parameters(node), f"{module}.{node.name}{signature}"


@pytest.mark.parametrize("module", SITE_STUBS)
def test_stub_constants_exist_in_the_site(module: str) -> None:
    real = importlib.import_module(module)
    for node in _stub(module).body:
        is_alias = (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.annotation, ast.Name)
            and node.annotation.id == "TypeAlias"
        )
        if isinstance(node, ast.AnnAssign) and not is_alias:
            name = cast("ast.Name", node.target).id
            assert hasattr(real, name), f"{module}.{name} is not in the site's code"


def test_machine_has_the_stubs_keys() -> None:
    (machine_class,) = (
        n
        for n in _stub("measure.timing").body
        if isinstance(n, ast.ClassDef) and n.name == "Machine"
    )
    keys = {
        cast("ast.Name", n.target).id
        for n in machine_class.body
        if isinstance(n, ast.AnnAssign)
    }
    assert set(site.machine()) == keys


def test_every_copy_strength_is_an_edit_the_site_applies() -> None:
    applied = {(v.name, v.strength) for v in site.variants() if v.group == "transform"}
    for name, strength in site.COPY_STRENGTHS.items():
        assert (name, strength) in applied


def test_photos_refuses_an_incomplete_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    def fetch(_cache: str | None = None) -> tuple[list[str], list[str]]:
        return ["a.jpg"], ["b.jpg: HTTP 404"]

    # benchmarks.site imports the site's fetch_corpus and calls it by module.
    monkeypatch.setattr("fetch_corpus.fetch", fetch)
    with pytest.raises(site.CorpusError, match=r"(?s)1 photographs.*b\.jpg"):
        site.photos()


def test_libphash_contenders_are_its_nine_hashes() -> None:
    keys = [c.key for c in libphash_contenders()]
    assert len(keys) == 9
    assert [c.key for c in contenders()[:9]] == keys


def test_quality_compares_every_edit_and_every_pair() -> None:
    images = _images()
    chosen = libphash_contenders()
    result = measure_quality(images, chosen, workers=1)
    assert result.images == len(images)
    edits = site.variants()
    for values in result.contenders:
        assert len(values.different) == len(images) * (len(images) - 1) // 2
        points = [row for e in values.edits for _, row in e.points]
        assert len(points) == len(edits)
        assert all(len(row) == len(images) for row in points)
        s = summarize(values)
        assert s.dprime == s.dprime  # not NaN: the copies and the pairs exist
        assert 0.0 <= s.false_accepts <= 1.0


@pytest.mark.parametrize("benchmark", ["quality", "speed", "overhead"])
def test_command_writes_json_and_markdown(benchmark: str, tmp_path: Path) -> None:
    argv = [benchmark, "--images", *_images(), "--quick", "--out", str(tmp_path)]
    assert cli.main([*argv, "--workers", "1"] if benchmark == "quality" else argv) == 0
    result = json.loads((tmp_path / f"{benchmark}.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / f"{benchmark}.md").read_text(encoding="utf-8")
    assert markdown.startswith("## ")
    assert "| --- |" in markdown
    assert "Corpus:" not in markdown  # measured on --images, not the corpus
    assert result


def test_command_only_measures_the_named_contenders(tmp_path: Path) -> None:
    argv = ["speed", "--images", *_images()[:1], "--quick", "--out", str(tmp_path)]
    assert cli.main([*argv, "--only", "libphash/pHash"]) == 0
    result = json.loads((tmp_path / "speed.json").read_text(encoding="utf-8"))
    keys = {c["key"] for c in result["cases"] if c["how"] == ""}
    assert keys == {"libphash/pHash"}
