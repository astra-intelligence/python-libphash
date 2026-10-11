import os
import sys
from pathlib import Path

import pytest

import libphash as ph
import libphash._batch
import libphash._context


@pytest.mark.parametrize(
    "name", ["кот.jpg", "猫の写真.jpg", "🐈 photo.jpg", "with space.jpg"]
)
def test_non_ascii_names(
    tmp_path: Path, photo: Path, photo_bytes: bytes, name: str
) -> None:
    directory = tmp_path / "Фото"
    directory.mkdir()
    path = directory / name
    path.write_bytes(photo_bytes)
    expected = ph.hash(photo)
    assert ph.hash(path) == expected
    assert ph.hash(str(path)) == expected
    with ph.ImageContext() as ctx:
        ctx.load_file(os.fsencode(path))
        assert ctx.phash() == expected
    [r] = ph.hash_files([path])
    assert r.hashes == {ph.Algorithm.PHASH: expected}


def test_missing_non_ascii_path_message(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as exc:
        ph.hash(tmp_path / "нет.jpg")
    assert "нет.jpg" in str(exc.value)


@pytest.mark.skipif(
    sys.platform != "linux", reason="needs a file system that stores raw bytes"
)
def test_name_that_is_not_utf8(tmp_path: Path, photo: Path, photo_bytes: bytes) -> None:
    raw = os.fsencode(tmp_path) + b"/\xff\xfe.jpg"
    with open(raw, "wb") as f:
        f.write(photo_bytes)
    expected = ph.hash(photo)
    assert ph.hash(os.fsdecode(raw)) == expected  # str with surrogate escapes
    with ph.ImageContext() as ctx:
        ctx.load_file(raw)
        assert ctx.phash() == expected


@pytest.mark.skipif(
    sys.platform == "win32", reason="symlinks need privileges on Windows"
)
def test_symlinks(tmp_path: Path, photo: Path) -> None:
    link = tmp_path / "link.jpg"
    link.symlink_to(photo)
    assert ph.hash(link) == ph.hash(photo)
    dangling = tmp_path / "dangling.jpg"
    dangling.symlink_to(tmp_path / "gone.jpg")
    with pytest.raises(FileNotFoundError):
        ph.hash(dangling)


def test_long_path_keeps_the_name(tmp_path: Path) -> None:
    deep = tmp_path / ("d" * 200) / ("e" * 200)
    with pytest.raises(ph.ImageIOError) as exc:
        ph.hash(deep / "image_at_the_end.jpg")
    assert "image_at_the_end.jpg" in str(exc.value)


def test_path_type_is_checked() -> None:
    with pytest.raises(TypeError, match="path"):
        ph.ImageContext().load_file(3.14)  # type: ignore[arg-type]


@pytest.fixture
def files_read_in_python(monkeypatch: pytest.MonkeyPatch) -> None:
    """Take the Windows code path, where the binding reads files itself, on any OS."""
    monkeypatch.setattr(libphash._context, "READ_FILES_IN_PYTHON", True)
    monkeypatch.setattr(libphash._batch, "READ_FILES_IN_PYTHON", True)


@pytest.mark.usefixtures("files_read_in_python")
def test_python_read_path_matches_c(
    tmp_path: Path, photo: Path, photo_bytes: bytes
) -> None:
    path = tmp_path / "кот.jpg"
    path.write_bytes(photo_bytes)
    expected = ph.hash(photo)
    assert ph.hash(path) == expected
    empty = tmp_path / "empty.jpg"
    empty.write_bytes(b"")
    with pytest.raises(FileNotFoundError):
        ph.hash(tmp_path / "missing.jpg")
    with pytest.raises(IsADirectoryError):
        ph.hash(tmp_path)
    with pytest.raises(ph.ImageIOError):
        ph.hash(empty)
    results = ph.hash_files(
        [path, tmp_path / "missing.jpg", empty, path] * 40, threads=2
    )
    assert [r.ok for r in results[:4]] == [True, False, False, True]
    assert results[0].hashes == {ph.Algorithm.PHASH: expected}
    assert isinstance(results[1].error, FileNotFoundError)


@pytest.mark.usefixtures("files_read_in_python")
def test_python_read_path_cancels_across_chunks(
    tmp_path: Path, photo_bytes: bytes
) -> None:
    path = tmp_path / "a.jpg"
    path.write_bytes(photo_bytes)
    results = ph.hash_files([path] * 300, threads=1, progress=lambda d, _t: d < 100)
    assert len(results) == 300
    assert sum(r.ok for r in results) == 100
    assert all(isinstance(r.error, ph.BatchCancelledError) for r in results[100:])
