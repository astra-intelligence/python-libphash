import functools
import os
import re
import sys
from pathlib import Path
from typing import cast

import c_reference
import pytest
from c_reference import Reference, start_reference

import libphash as ph
import libphash._batch
import libphash._context

# The photo corpus is fetched over the network by a workflow of its own, which names the
# list of its files in LIBPHASH_CORPUS; other runs do not collect its test at all.
collect_ignore = [] if os.environ.get("LIBPHASH_CORPUS") else ["test_corpus.py"]

DATA = c_reference.DATA


# libjpeg-turbo decodes JPEG unless the build was configured without it; stb_image then
# does, with its own IDCT, no arithmetic coding and no decode scaling. The question is
# asked inside tests, not at import: collection never calls into the package, so a
# broken build or a mutant fails the tests that use it instead of the whole session.
@functools.cache
def libjpeg_turbo() -> bool:
    return ph.can_decode("jpeg")


def needs_libjpeg_turbo(why: str) -> None:
    if not libjpeg_turbo():
        pytest.skip(f"stb_image decodes JPEG in this build: {why}")


def data(name: str) -> Path:
    path = DATA / name
    if not path.exists():
        pytest.skip(f"fixture {name} is missing (native/libphash not checked out?)")
    return path


@pytest.fixture(scope="session")
def reference() -> Reference:
    return start_reference()


@pytest.fixture
def photo() -> Path:
    return data("photo.jpeg")


@pytest.fixture
def photo_bytes(photo: Path) -> bytes:
    return photo.read_bytes()


@pytest.fixture(params=["C", "Python"])
def files_read_by(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> str:
    """Run the test with libphash opening the files, then with the binding reading them.

    The binding reads files itself on Windows (READ_FILES_IN_PYTHON); either way gives
    the same hashes and the same errors.
    """
    reader = cast("str", request.param)
    if reader == "C" and sys.platform == "win32":
        pytest.skip("on Windows the binding always reads the files")
    for module in (libphash._context, libphash._batch):
        monkeypatch.setattr(module, "READ_FILES_IN_PYTHON", reader == "Python")
    return reader


def exactly(message: str) -> str:
    """Return a ``pytest.raises(match=...)`` pattern for the whole message."""
    return f"^{re.escape(message)}$"
