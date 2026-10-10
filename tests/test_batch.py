from __future__ import annotations

import os
import signal
import sys
import threading
from typing import TYPE_CHECKING

import pytest
from conftest import data

import libphash as ph

if TYPE_CHECKING:
    from pathlib import Path


def paths() -> list[Path]:
    return [
        data(n)
        for n in (
            "photo.jpeg",
            "photo.png",
            "photo.webp",
            "photo_copy.jpeg",
            "photo_rotated_90.jpeg",
            "photo_large.jpeg",
        )
    ]


@pytest.mark.parametrize("threads", [0, 1, 3])
def test_batch_matches_single_hashes(threads: int) -> None:
    ps = paths()
    results = ph.hash_files(ps, ["phash", "dhash"], threads=threads)
    assert [r.source for r in results] == ps
    for p, r in zip(ps, results, strict=True):
        assert r.ok
        assert r.hashes == {
            ph.Algorithm.DHASH: ph.hash(p, "dhash"),
            ph.Algorithm.PHASH: ph.hash(p, "phash"),
        }


def test_batch_uses_the_config() -> None:
    cfg = ph.Config(phash_reduction_size=4)
    [r] = ph.hash_files([data("photo.jpeg")], config=cfg)
    assert r.hashes is not None
    assert r.hashes[ph.Algorithm.PHASH] == ph.hash(data("photo.jpeg"), config=cfg)


def test_failed_items_carry_their_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"junk")
    results = ph.hash_files([data("photo.jpeg"), tmp_path / "missing.jpg", bad])
    assert results[0].ok
    assert isinstance(results[1].error, FileNotFoundError)
    assert results[1].hashes is None
    assert "missing.jpg" in str(results[1].error)
    assert repr(results[1].error).startswith("ImageIOError(")
    assert isinstance(results[2].error, ph.UnsupportedFormatError)


def test_buffers(photo_bytes: bytes) -> None:
    results = ph.hash_buffers([photo_bytes, b"junk", bytearray(photo_bytes)], "ahash")
    assert [r.source for r in results] == [0, 1, 2]
    assert results[0].hashes == {ph.Algorithm.AHASH: ph.hash(photo_bytes, "ahash")}
    assert isinstance(results[1].error, ph.DecodeError)
    assert results[2].hashes == results[0].hashes


def test_digests_cannot_be_batched() -> None:
    with pytest.raises(ph.InvalidArgumentError, match="digest"):
        ph.hash_files(paths(), ["radial"])


def test_empty_batch_and_bad_threads() -> None:
    assert ph.hash_files([]) == []
    with pytest.raises(ph.InvalidArgumentError):
        ph.hash_files(paths(), threads=-1)


def test_progress_counts_to_total() -> None:
    seen: list[tuple[int, int]] = []
    ph.hash_files(paths() * 5, threads=4, progress=lambda d, t: seen.append((d, t)))
    assert [d for d, _ in seen] == list(range(1, 31))
    assert {t for _, t in seen} == {30}


def test_progress_returning_false_cancels() -> None:
    results = ph.hash_files(paths() * 10, threads=1, progress=lambda d, _t: d < 3)
    assert sum(r.ok for r in results) == 3
    assert all(isinstance(r.error, ph.BatchCancelledError) for r in results[3:])


def test_exception_in_progress_propagates() -> None:
    def boom(_done: int, _total: int) -> None:
        raise RuntimeError("from progress")

    with pytest.raises(RuntimeError, match="from progress"):
        ph.hash_files(paths() * 10, threads=2, progress=boom)


@pytest.mark.skipif(
    sys.platform == "win32", reason="SIGINT delivery differs on Windows"
)
def test_ctrl_c_stops_the_batch() -> None:
    big = [data("photo_large.jpeg")] * 2000
    done: list[int] = []

    def interrupt_once_started(d: int, _t: int) -> None:
        done.append(d)
        if d == 5:
            threading.Thread(target=os.kill, args=(os.getpid(), signal.SIGINT)).start()

    with pytest.raises(KeyboardInterrupt):
        ph.hash_files(big, threads=2, progress=interrupt_once_started)
    assert len(done) < len(big)
