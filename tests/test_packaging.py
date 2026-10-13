"""What the build adds around the module: the SBOM and the reproducible sdist."""

import gzip
import io
import json
import tarfile
from pathlib import Path
from typing import cast

import pytest
import sbom
import sdist

import libphash as ph


def test_sbom_names_libphash_at_the_bundled_version() -> None:
    [libphash] = [c for c in sbom.components() if c["name"] == "libphash"]
    assert libphash["version"] == ph.libphash_version()


def test_sbom_names_every_decoder_the_build_reports() -> None:
    names = {c["name"] for c in sbom.components()}
    info = dict(item.split("=", 1) for item in ph.build_info().split())
    for key in ("jpeg", "png", "webp", "zlib"):
        if info[key] != "none":
            assert info[key] in names
    assert {"stb_image", "stb_image_resize2"} <= names


def test_sbom_versions_and_licenses() -> None:
    for c in sbom.components():
        assert c["version"].replace(".", "").isdigit(), c
        assert c["purl"].endswith(f"@{c['version']}")
        assert c["license"]


def test_sbom_document_is_cyclonedx_and_reproducible(tmp_path: Path) -> None:
    doc = sbom.sbom("2.0.1.0")
    assert doc["bomFormat"] == "CycloneDX"
    assert doc["specVersion"] == "1.6"
    assert "timestamp" not in json.dumps(doc)
    components = cast("list[dict[str, object]]", doc["components"])
    [dependencies] = cast("list[dict[str, list[str]]]", doc["dependencies"])
    assert len(dependencies["dependsOn"]) == len(components)
    first = sbom.write(tmp_path / "a", "2.0.1.0").read_bytes()
    assert sbom.write(tmp_path / "b", "2.0.1.0").read_bytes() == first
    assert json.loads(first) == doc


def test_a_missing_version_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match=r"CMakeLists\.txt"):
        sbom.components(tmp_path)


def _archive(path: Path, mtime: int, mode: int) -> None:
    with tarfile.open(path, "w:gz") as tar:
        for name, data in (("pkg/b.txt", b"b"), ("pkg/a.sh", b"#!/bin/sh\n")):
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.uid, info.uname = len(data), mtime, 501, "me"
            info.mode = mode if name.endswith(".sh") else 0o664
            tar.addfile(info, io.BytesIO(data))
        info = tarfile.TarInfo("pkg")
        info.type, info.mtime, info.mode = tarfile.DIRTYPE, mtime + 7, 0o775
        tar.addfile(info)


def test_sdist_is_rewritten_reproducibly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    a, b = tmp_path / "a.tar.gz", tmp_path / "b.tar.gz"
    _archive(a, 1_000, 0o775)
    _archive(b, 2_000, 0o775)
    assert a.read_bytes() != b.read_bytes()
    sdist.normalize(a)
    sdist.normalize(b)
    assert a.read_bytes() == b.read_bytes()
    with gzip.open(a) as stream:
        assert stream.read()
    with tarfile.open(a) as tar:
        members = tar.getmembers()
        assert [m.name for m in members] == ["pkg", "pkg/a.sh", "pkg/b.txt"]
        assert [oct(m.mode) for m in members] == ["0o755", "0o755", "0o644"]
        assert {(m.uid, m.gid, m.uname, m.gname) for m in members} == {(0, 0, "", "")}
        assert {m.mtime for m in members} == {1_700_000_000}
        script = tar.extractfile("pkg/a.sh")
        assert script is not None
        assert script.read() == b"#!/bin/sh\n"


def test_sdist_without_epoch_keeps_file_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    a = tmp_path / "a.tar.gz"
    _archive(a, 1_000, 0o644)
    sdist.normalize(a)
    with tarfile.open(a) as tar:
        times = {m.name: m.mtime for m in tar.getmembers()}
        modes = {m.name: m.mode for m in tar.getmembers()}
    # Directories take the newest file's time, not the time of the run.
    assert times == {"pkg": 1_000, "pkg/a.sh": 1_000, "pkg/b.txt": 1_000}
    assert modes["pkg/a.sh"] == 0o644
