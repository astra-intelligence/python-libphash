from __future__ import annotations

import errno
import os
import signal
import socket
import sys
import threading
from typing import TYPE_CHECKING

import pytest
from conftest import data

import libphash as ph

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def no_wakeup_fd() -> Iterator[None]:
    """Clear a wakeup fd the test runner may have set, so the batch sets its own."""
    previous = signal.set_wakeup_fd(-1)
    yield
    signal.set_wakeup_fd(previous)


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


@pytest.mark.usefixtures("files_read_by")
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


@pytest.mark.usefixtures("files_read_by")
def test_batch_uses_the_config() -> None:
    cfg = ph.Config(phash_reduction_size=4)
    [r] = ph.hash_files([data("photo.jpeg")], config=cfg)
    assert r.hashes is not None
    assert r.hashes[ph.Algorithm.PHASH] == ph.hash(data("photo.jpeg"), config=cfg)


def test_failed_items_carry_their_error(tmp_path: Path, files_read_by: str) -> None:
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"junk")
    empty = tmp_path / "empty.jpg"
    empty.write_bytes(b"")
    missing = tmp_path / "missing.jpg"
    sources = [data("photo.jpeg"), missing, bad, empty]
    results = ph.hash_files(sources)
    assert [r.source for r in results] == sources
    assert results[0].ok
    assert isinstance(results[1].error, FileNotFoundError)
    assert (results[1].error.errno, results[1].error.filename) == (
        errno.ENOENT,
        str(missing),
    )
    assert results[1].hashes is None
    assert "missing.jpg" in str(results[1].error)
    assert repr(results[1].error).startswith("ImageIOError(")
    assert isinstance(results[2].error, ph.UnsupportedFormatError)
    assert type(results[3].error) is ph.ImageIOError
    assert results[3].error.filename == str(empty)
    if files_read_by == "Python":
        # The binding's reader names the cause, as the C library does for one file.
        assert results[1].error.detail == (
            f"Cannot open '{missing}': {os.strerror(errno.ENOENT)}"
        )
        assert results[3].error.detail == f"Cannot read '{empty}': file is empty"


def test_buffers(photo_bytes: bytes) -> None:
    seen: list[tuple[int, int]] = []
    results = ph.hash_buffers(
        [photo_bytes, b"junk", bytearray(photo_bytes)],
        "ahash",
        progress=lambda d, t: seen.append((d, t)),
    )
    assert [r.source for r in results] == [0, 1, 2]
    assert results[0].hashes == {ph.Algorithm.AHASH: ph.hash(photo_bytes, "ahash")}
    assert isinstance(results[1].error, ph.DecodeError)
    assert results[2].hashes == results[0].hashes
    assert sorted(seen) == [(1, 3), (2, 3), (3, 3)]


@pytest.mark.skipif((os.cpu_count() or 1) < 2, reason="one CPU: one worker")
def test_default_threads_are_workers(photo_bytes: bytes) -> None:
    # threads=0 runs the items on libphash's pool; threads=1 on the calling thread.
    idents: set[int] = set()

    def note(_done: int, _total: int) -> None:
        idents.add(threading.get_ident())

    ph.hash_buffers([photo_bytes] * 8, progress=note)
    assert idents
    assert threading.get_ident() not in idents
    idents.clear()
    ph.hash_buffers([photo_bytes] * 8, threads=1, progress=note)
    assert idents == {threading.get_ident()}


def test_digests_cannot_be_batched() -> None:
    with pytest.raises(ph.InvalidArgumentError, match="digest"):
        ph.hash_files(paths(), ["radial"])


def test_empty_batch_and_bad_threads() -> None:
    assert ph.hash_files([]) == []
    with pytest.raises(ph.InvalidArgumentError):
        ph.hash_files(paths(), threads=-1)


@pytest.mark.usefixtures("files_read_by")
def test_progress_counts_to_total() -> None:
    seen: list[tuple[int, int]] = []
    ph.hash_files(paths() * 5, threads=4, progress=lambda d, t: seen.append((d, t)))
    assert [d for d, _ in seen] == list(range(1, 31))
    assert {t for _, t in seen} == {30}


@pytest.mark.usefixtures("files_read_by")
def test_progress_returning_false_cancels() -> None:
    sources = paths() * 10
    results = ph.hash_files(sources, threads=1, progress=lambda d, _t: d < 3)
    assert [r.source for r in results] == sources
    assert sum(r.ok for r in results) == 3
    assert all(isinstance(r.error, ph.BatchCancelledError) for r in results[3:])


@pytest.mark.usefixtures("files_read_by")
def test_exception_in_progress_propagates_and_stops() -> None:
    calls: list[int] = []

    def boom(done: int, _total: int) -> None:
        calls.append(done)
        raise RuntimeError("from progress")

    with pytest.raises(RuntimeError, match="from progress"):
        ph.hash_files(paths() * 10, threads=1, progress=boom)
    assert calls == [1]
    with pytest.raises(RuntimeError, match="from progress"):
        ph.hash_files(paths() * 10, threads=2, progress=boom)


# threads=1 runs the callbacks on the calling thread, where KeyboardInterrupt arrives
# inside a callback; with workers it arrives once the call returns, and the batch
# learns of it through the wakeup fd.
@pytest.mark.skipif(
    sys.platform == "win32", reason="SIGINT delivery differs on Windows"
)
@pytest.mark.parametrize("threads", [1, 2])
@pytest.mark.parametrize("with_progress", [True, False])
@pytest.mark.usefixtures("no_wakeup_fd")
def test_ctrl_c_stops_the_batch(threads: int, *, with_progress: bool) -> None:
    big = [data("photo_large.jpeg")] * 2000
    done: list[int] = []

    def count(d: int, _t: int) -> None:
        done.append(d)

    timer = threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGINT))
    timer.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            ph.hash_files(
                big, threads=threads, progress=count if with_progress else None
            )
    finally:
        timer.cancel()
    assert len(done) < len(big)


def test_batches_from_several_threads_at_once() -> None:
    # Each call has its own pool and its own callbacks' state.
    expected = ph.hash_files(paths())
    results: dict[int, list[ph.BatchResult[Path]]] = {}
    progress: dict[int, list[int]] = {}

    def work(i: int) -> None:
        seen: list[int] = []
        results[i] = ph.hash_files(
            paths() * 3, threads=2, progress=lambda d, _t: seen.append(d)
        )
        progress[i] = seen

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 4
    for i, result in results.items():
        assert [r.hashes for r in result] == [r.hashes for r in expected] * 3
        assert progress[i] == list(range(1, len(paths()) * 3 + 1))


def test_no_algorithm() -> None:
    with pytest.raises(ph.InvalidArgumentError, match="no algorithm given"):
        ph.hash_files(paths(), [])


@pytest.mark.usefixtures("files_read_by")
def test_progress_is_not_called_after_it_stops_the_batch() -> None:
    # Items already running on other workers finish, but do not report.
    calls: list[int] = []

    def stop(d: int, _t: int) -> bool:
        calls.append(d)
        return False

    results = ph.hash_files(paths() * 10, threads=4, progress=stop)
    assert calls == [1]
    assert any(isinstance(r.error, ph.BatchCancelledError) for r in results)


def test_batch_without_the_wakeup_fd(
    monkeypatch: pytest.MonkeyPatch, photo_bytes: bytes
) -> None:
    def refuse(_fd: int, /, **_kwargs: object) -> int:
        raise ValueError("set_wakeup_fd only works in main thread")

    monkeypatch.setattr(signal, "set_wakeup_fd", refuse)
    [result] = ph.hash_buffers([photo_bytes], "ahash")
    assert result.hashes == {ph.Algorithm.AHASH: ph.hash(photo_bytes, "ahash")}


def test_batch_leaves_an_owned_wakeup_fd_alone(photo_bytes: bytes) -> None:
    # An event loop that set the wakeup fd keeps it through the batch.
    reader, writer = socket.socketpair()
    writer.setblocking(False)
    previous = signal.set_wakeup_fd(writer.fileno())
    try:
        [result] = ph.hash_buffers([photo_bytes], "ahash")
        assert result.ok
    finally:
        assert signal.set_wakeup_fd(previous) == writer.fileno()
        reader.close()
        writer.close()
