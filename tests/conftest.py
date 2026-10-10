from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "native" / "libphash" / "tests" / "data"


def data(name: str) -> Path:
    path = DATA / name
    if not path.exists():
        pytest.skip(f"fixture {name} is missing (native/libphash not checked out?)")
    return path


@pytest.fixture
def photo() -> Path:
    return data("photo.jpeg")


@pytest.fixture
def photo_bytes(photo: Path) -> bytes:
    return photo.read_bytes()
