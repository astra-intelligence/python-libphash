"""The binding's X.Y.Z.N version agrees with the libphash it bundles."""

import re
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest

import libphash
from libphash._native import ffi, lib

NATIVE_DIR = Path(__file__).resolve().parent.parent / "native" / "libphash"


def c_version() -> str:
    return str(ffi.string(lib.ph_version()).decode())


def test_version_has_four_numbers() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", libphash.__version__)


def test_first_three_numbers_are_the_bundled_libphash() -> None:
    assert libphash.__version__.rsplit(".", 1)[0] == c_version()


def test_distribution_metadata_matches() -> None:
    # PEP 440 keeps a trailing .0: 2.0.1.0 is not normalized to 2.0.1.
    assert version("python-libphash") == libphash.__version__


def test_submodule_is_on_the_release_tag() -> None:
    try:
        git = ["git", "-C", str(NATIVE_DIR), "describe", "--tags", "--exact-match"]
        tag = subprocess.run(  # noqa: S603 -- a fixed git command
            git,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("native/libphash is not a git checkout on a tag")
    assert tag == f"v{c_version()}"


def test_version_number_encodes_the_version() -> None:
    major, minor, patch = (int(n) for n in c_version().split("."))
    assert lib.ph_version_number() == major * 1_000_000 + minor * 1000 + patch
