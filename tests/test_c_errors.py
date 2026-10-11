"""Errors that the C library returns only for input the binding rejects first.

The binding checks its arguments before each call, so with the real library these
paths never run; a stand-in ``lib`` that fails one function shows that, should the C
side ever reject what the binding passed, the caller gets the matching exception and
nothing leaks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import libphash as ph
import libphash._batch
import libphash._config
import libphash._context
import libphash._digest
from libphash._native import lib

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from libphash._native import ph_context_t_ptr

ERROR = int(lib.PH_ERR_INVALID_ARGUMENT)


class StandInLib:
    """The real ``lib`` with some functions replaced."""

    def __init__(self, **replaced: Callable[..., object]) -> None:
        self._replaced = replaced

    def __getattr__(self, name: str) -> object:
        return self._replaced.get(name) or getattr(lib, name)


def fail(*_args: object) -> int:
    return ERROR


def failing(*names: str) -> StandInLib:
    return StandInLib(**dict.fromkeys(names, fail))


def test_digest_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ph, "lib", failing("ph_digest_info"))
    with pytest.raises(ph.InvalidArgumentError, match=r"digest_info\(radial\)"):
        ph.digest_info("radial")


def test_compute_multi(monkeypatch: pytest.MonkeyPatch, photo: Path) -> None:
    with ph.ImageContext() as ctx:
        ctx.load(photo)
        monkeypatch.setattr(libphash._context, "lib", failing("ph_compute_multi"))
        with pytest.raises(ph.InvalidArgumentError, match="computing dhash, phash"):
            ctx.hashes("phash", "dhash")


@pytest.mark.parametrize(
    ("function", "call", "context"),
    [
        (
            "ph_digest_to_hex",
            lambda: ph.Digest(b"\1", ph.DigestKind.BITS).hex(),
            "encoding digest",
        ),
        ("ph_hash_to_hex", lambda: ph.hash_to_hex(1), "encoding hash"),
    ],
)
def test_hex_encoding(
    monkeypatch: pytest.MonkeyPatch,
    function: str,
    call: Callable[[], object],
    context: str,
) -> None:
    monkeypatch.setattr(libphash._digest, "lib", failing(function))
    with pytest.raises(ph.InvalidArgumentError, match=context):
        call()


def test_digest_metric_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    d = ph.Digest(b"\1", ph.DigestKind.BITS)
    monkeypatch.setattr(
        libphash._digest,
        "lib",
        StandInLib(ph_hamming_distance_digest=lambda *_args: -1),
    )
    with pytest.raises(ph.InvalidArgumentError, match="rejected the digests"):
        d.hamming_distance(d)


def test_batch_options_init(
    monkeypatch: pytest.MonkeyPatch, photo_bytes: bytes
) -> None:
    monkeypatch.setattr(libphash._batch, "lib", failing("ph_batch_options_init"))
    with pytest.raises(ph.InvalidArgumentError):
        ph.hash_buffers([photo_bytes])


def test_batch_return_code(monkeypatch: pytest.MonkeyPatch, photo_bytes: bytes) -> None:
    monkeypatch.setattr(libphash._batch, "lib", failing("ph_hash_buffers_ex"))
    with pytest.raises(ph.InvalidArgumentError, match="batch"):
        ph.hash_buffers([photo_bytes])


def test_batch_config_frees_the_template(
    monkeypatch: pytest.MonkeyPatch, photo_bytes: bytes
) -> None:
    config = ph.Config()  # validated before the stand-in fails its setters
    freed: list[ph_context_t_ptr] = []

    def free(ctx: ph_context_t_ptr) -> None:
        freed.append(ctx)
        lib.ph_free(ctx)

    monkeypatch.setattr(libphash._config, "lib", failing("ph_context_set_gamma"))
    monkeypatch.setattr(libphash._batch, "lib", StandInLib(ph_free=free))
    with pytest.raises(ph.InvalidArgumentError):
        ph.hash_buffers([photo_bytes], config=config)
    assert len(freed) == 1
