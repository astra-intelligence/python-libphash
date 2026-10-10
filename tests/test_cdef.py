"""The binding declares every function of libphash's public header."""

import sys
from pathlib import Path

from libphash._native import lib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from cdef import header_functions  # noqa: E402

HEADER = ROOT / "native" / "libphash" / "include" / "libphash.h"


def test_every_header_function_is_in_lib() -> None:
    declared = header_functions(HEADER)
    assert len(declared) > 50
    missing = sorted(name for name in declared if not hasattr(lib, name))
    assert missing == []


def test_constants_come_from_the_header() -> None:
    assert lib.PH_DIGEST_MAX_BYTES == 128
    assert lib.PH_SUCCESS == 0
