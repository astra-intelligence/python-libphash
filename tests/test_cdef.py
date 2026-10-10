"""Every function of libphash's public header is reachable from Python."""

import re
import sys
from pathlib import Path

from libphash._native import lib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from cdef import header_functions  # noqa: E402

HEADER = ROOT / "native" / "libphash" / "include" / "libphash.h"
PACKAGE = ROOT / "src" / "libphash"

#: Functions the binding deliberately does not call, and why.
NOT_WRAPPED = {
    "ph_compute_bmh": "ph_compute_digest computes every digest algorithm",
    "ph_compute_color_hash": "ph_compute_digest computes every digest algorithm",
    "ph_compute_color_moments_hash": "ph_compute_digest computes every digest algorithm",
    "ph_compute_mhash": "ph_compute_digest computes every digest algorithm",
    "ph_compute_radial_hash": "ph_compute_digest computes every digest algorithm",
    "ph_hash_files": "ph_hash_files_ex with default options is the same call",
    "ph_hash_buffers": "ph_hash_buffers_ex with default options is the same call",
    "ph_context_get_gray_weights": "Config holds the weights it sets",
    "ph_version_number": "libphash_version() gives the same version",
}


def test_every_header_function_is_in_lib() -> None:
    declared = header_functions(HEADER)
    assert len(declared) > 50
    assert sorted(n for n in declared if not hasattr(lib, n)) == []


def test_every_header_function_is_wrapped_or_listed() -> None:
    source = " ".join(p.read_text(encoding="utf-8") for p in PACKAGE.glob("*.py"))
    used = {n for n in header_functions(HEADER) if re.search(rf"\blib\.{n}\b", source)}
    unwrapped = header_functions(HEADER) - used
    assert sorted(unwrapped - NOT_WRAPPED.keys()) == [], (
        "wrap these or list them in NOT_WRAPPED"
    )
    assert sorted(NOT_WRAPPED.keys() & used) == [], (
        "wrapped now: remove from NOT_WRAPPED"
    )


def test_constants_come_from_the_header() -> None:
    assert lib.PH_DIGEST_MAX_BYTES == 128
    assert lib.PH_SUCCESS == 0
