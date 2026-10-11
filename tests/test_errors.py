import errno
import os
import pickle
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import data

import libphash as ph
from libphash._errors import make_error
from libphash._native import ffi, lib


@pytest.mark.usefixtures("files_read_by")
def test_missing_file_is_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "nope.jpg"
    with pytest.raises(FileNotFoundError) as exc:
        ph.hash(missing)
    err = exc.value
    assert isinstance(err, ph.ImageIOError)
    assert isinstance(err, ph.PhashError)
    assert err.code_name == "PH_ERR_IO"
    assert (err.errno, err.filename) == (errno.ENOENT, str(missing))
    assert str(err) == err.detail
    assert str(err) == f"Cannot open '{missing}': {os.strerror(errno.ENOENT)}"


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


@pytest.mark.usefixtures("files_read_by")
def test_empty_file_is_an_io_error(tmp_path: Path) -> None:
    path = tmp_path / "empty.jpg"
    path.write_bytes(b"")
    with pytest.raises(ph.ImageIOError) as exc:
        ph.hash(path)
    assert str(exc.value) == f"Cannot read '{path}': file is empty"
    assert (exc.value.errno, exc.value.filename) == (None, str(path))


def test_io_error_without_a_path() -> None:
    err = make_error(int(lib.PH_ERR_IO))
    assert type(err) is ph.ImageIOError
    assert (err.errno, err.filename) == (None, None)


def test_io_error_defaults() -> None:
    err = ph.ImageIOError("cannot")
    assert (str(err), err.code, err.code_name, err.detail) == ("cannot", 0, "", "")
    assert repr(err) == "ImageIOError('cannot')"


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
    err = exc.value
    clone = pickle.loads(pickle.dumps(err))
    assert isinstance(clone, FileNotFoundError)
    assert isinstance(err, ph.ImageIOError)
    assert isinstance(clone, ph.ImageIOError)
    assert (str(clone), repr(clone)) == (str(err), repr(err))
    assert (clone.code, clone.detail) == (err.code, err.detail)
    assert (clone.errno, clone.filename) == (err.errno, err.filename)


def test_builtin_bases() -> None:
    assert issubclass(ph.InvalidArgumentError, ValueError)
    assert issubclass(ph.AllocationError, MemoryError)
    assert issubclass(ph.DigestKindError, TypeError)
    assert issubclass(ph.ImageIOError, OSError)


def test_every_error_code_has_its_own_exception() -> None:
    codes = {
        name: int(getattr(lib, name))
        for name in dir(lib)
        if name.startswith("PH_ERR_") and name != "PH_ERR_FORCE_INT32_"
    }
    classes: set[type[ph.PhashError]] = set()
    for name, code in codes.items():
        err = make_error(code)
        assert type(err) is not ph.PhashError, name
        assert (err.code, err.code_name) == (code, name)
        assert str(err) == ffi.string(lib.ph_get_error_string(code)).decode()
        classes.add(type(err))
    assert len(classes) == len(codes)


def test_an_unknown_code_is_the_base_class() -> None:
    err = make_error(-99)
    assert type(err) is ph.PhashError
    assert (err.code, err.code_name) == (-99, "")
