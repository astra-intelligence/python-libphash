"""The typed stub of ``libphash._native`` states what the built module does."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from libphash._native import ffi, lib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from stub import STUB, generate  # noqa: E402 -- tools/ joins sys.path just above

if TYPE_CHECKING:
    from collections.abc import Callable

    from libphash._native import (
        CData,
        char_array,
        char_ptr,
        ph_batch_item_t,
        ph_batch_item_t_array,
        ph_context_t_ptr,
        ph_context_t_ptr_ptr,
        ph_digest_t_ptr,
        uint8_t_array,
        uint64_t_array,
        uint64_t_ptr,
    )


def _new_cdecls() -> list[str]:
    text = STUB.read_text(encoding="utf-8")
    block = re.findall(r"def new\(\s*self,\s*cdecl: Literal\[(.*?)\]", text, re.DOTALL)
    return sorted({c for b in block for c in re.findall(r'"([^"]+)"', b)})


def test_stub_is_generated_from_the_built_module() -> None:
    assert STUB.read_text(encoding="utf-8") == generate(), (
        "src/libphash/_native.pyi is out of date: run python tools/stub.py"
    )


@pytest.mark.parametrize("cdecl", _new_cdecls())
def test_every_typed_cdecl_allocates(cdecl: str) -> None:
    # The overloads take only literal cdecls; this one is computed.
    new = cast("Callable[..., CData]", ffi.new)
    value = new(cdecl, 1) if cdecl.endswith("[]") else new(cdecl)
    assert ffi.typeof(value).cname == ffi.typeof(cdecl.removeprefix("const ")).cname


def test_cdecls_and_results_are_typed() -> None:
    # Each annotation is checked by mypy and basedpyright against the stub.
    out: ph_context_t_ptr_ptr = ffi.new("ph_context_t **")
    assert lib.ph_create(out) == lib.PH_SUCCESS
    ctx: ph_context_t_ptr = out[0]
    try:
        hashes: uint64_t_array = ffi.new("uint64_t[]", 2)
        second: uint64_t_ptr = hashes + 1
        second[0] = 7
        assert list(hashes) == [0, 7]
        digest: ph_digest_t_ptr = ffi.new("ph_digest_t *")
        assert digest.size == 0
        items: ph_batch_item_t_array = ffi.new("ph_batch_item_t[]", 1)
        item: ph_batch_item_t = items[0]
        assert item.status == 0
        text: char_array = ffi.new("char[]", b"x")
        assert ffi.string(text) == b"x"
        view: uint8_t_array = ffi.from_buffer("const uint8_t[]", b"x")
        assert len(view) == 1
        version: char_ptr = lib.ph_version()
        assert ffi.string(version)
        assert lib.ph_compute_ahash(ctx, hashes) == lib.PH_ERR_EMPTY_IMAGE
    finally:
        lib.ph_free(ctx)
