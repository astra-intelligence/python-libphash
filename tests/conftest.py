import os
from pathlib import Path

import c_reference
import pytest
from c_reference import Reference, start_reference

import libphash as ph

# The photo corpus is fetched over the network by a workflow of its own, which names the
# list of its files in LIBPHASH_CORPUS; other runs do not collect its test at all.
collect_ignore = [] if os.environ.get("LIBPHASH_CORPUS") else ["test_corpus.py"]

DATA = c_reference.DATA

# libjpeg-turbo decodes JPEG unless the build was configured without it; stb_image then
# does, with its own IDCT, no arithmetic coding and no decode scaling.
LIBJPEG_TURBO = ph.can_decode("jpeg")


def needs_libjpeg_turbo(why: str) -> None:
    if not LIBJPEG_TURBO:
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
