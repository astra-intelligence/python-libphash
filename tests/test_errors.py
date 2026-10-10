import os
import pickle
import sys
from pathlib import Path
from typing import Callable

import pytest
from conftest import data

import libphash as ph


def test_missing_file_is_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "nope.jpg"
    with pytest.raises(FileNotFoundError) as exc:
        ph.hash(missing)
    err = exc.value
    assert isinstance(err, ph.ImageIOError)
    assert isinstance(err, ph.PhashError)
    assert err.code_name == "PH_ERR_IO"
    assert err.filename == str(missing)
    assert "nope.jpg" in str(err)


def test_directory_is_a_directory(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError):
        ph.hash(tmp_path)


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="POSIX permissions"
)
def test_unreadable_file_is_permission_error(
    tmp_path: Path, photo_bytes: bytes
) -> None:
    path = tmp_path / "locked.jpg"
    path.write_bytes(photo_bytes)
    path.chmod(0)
    try:
        with pytest.raises(PermissionError):
            ph.hash(path)
    finally:
        path.chmod(0o600)


def test_empty_file_is_an_io_error(tmp_path: Path) -> None:
    path = tmp_path / "empty.jpg"
    path.write_bytes(b"")
    with pytest.raises(ph.ImageIOError):
        ph.hash(path)


def test_decode_errors() -> None:
    with pytest.raises(ph.UnsupportedFormatError) as exc:
        ph.hash(b"definitely not an image")
    assert isinstance(exc.value, ph.DecodeError)
    with pytest.raises(ph.CorruptDataError):
        ph.hash(data("png/broken_truncated.png"))
    with pytest.raises(ph.DecodeError):
        ph.hash(data("corrupted.jpg"))


def test_decode_bomb_is_too_large() -> None:
    with pytest.raises(ph.ImageTooLargeError):
        ph.hash(data("decode_bomb.png"))


def test_load_errors_carry_the_c_detail(tmp_path: Path) -> None:
    with pytest.raises(ph.ImageIOError) as exc:
        ph.hash(tmp_path / "nope.jpg")
    assert "nope.jpg" in exc.value.detail


def test_hash_error_does_not_carry_a_previous_load_detail(tmp_path: Path) -> None:
    with ph.ImageContext() as ctx:
        with pytest.raises(ph.ImageIOError):
            ctx.load_file(tmp_path / "nope.jpg")
        with pytest.raises(ph.EmptyImageError) as exc:
            ctx.phash()
    assert "nope.jpg" not in str(exc.value)
    assert exc.value.detail == ""
    assert "computing phash" in str(exc.value)


@pytest.mark.parametrize(
    "make",
    [
        lambda: ph.ImageContext().phash(),
        lambda: ph.hash(b"junk"),
        lambda: ph.Config(gamma=-1.0),
    ],
)
def test_exceptions_pickle(make: Callable[[], object]) -> None:
    with pytest.raises(ph.PhashError) as exc:
        make()
    clone = pickle.loads(pickle.dumps(exc.value))
    assert type(clone) is type(exc.value)
    assert str(clone) == str(exc.value)
    assert clone.code == exc.value.code


def test_io_exception_pickles_with_errno(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as exc:
        ph.hash(tmp_path / "nope.jpg")
    clone = pickle.loads(pickle.dumps(exc.value))
    assert isinstance(clone, FileNotFoundError)
    assert clone.errno == exc.value.errno


def test_builtin_bases() -> None:
    assert issubclass(ph.InvalidArgumentError, ValueError)
    assert issubclass(ph.AllocationError, MemoryError)
    assert issubclass(ph.DigestKindError, TypeError)
    assert issubclass(ph.ImageIOError, OSError)
