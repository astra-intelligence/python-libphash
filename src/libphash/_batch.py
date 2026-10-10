from __future__ import annotations

import os
import signal
import socket
import threading
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Sequence

from ._algorithms import Algorithm, AlgorithmLike, to_algorithm, uint64_flags
from ._config import Config, _new_context
from ._native import ffi, lib
from ._sources import READ_FILES_IN_PYTHON, StrPath, encode_path, read_file
from .exceptions import (
    InvalidArgumentError,
    PhashError,
    PH_ERR_IO,
    PH_SUCCESS,
    check,
    make_error,
)

#: Called as ``progress(done, total)`` after each finished item; returning ``False``
#: stops the batch (items not yet started get BatchCancelledError).
ProgressCallback = Callable[[int, int], Optional[bool]]

_PH_ERR_CANCELLED = int(lib.PH_ERR_CANCELLED)


@dataclass(frozen=True)
class BatchResult:
    """The outcome for one item of a batch."""

    #: The path or buffer index the item was given as.
    source: Any
    #: The hashes by algorithm, or None if the item failed.
    hashes: Optional[dict[Algorithm, int]]
    #: Why the item failed, or None.
    error: Optional[PhashError]

    @property
    def ok(self) -> bool:
        return self.error is None


def hash_files(
    paths: Iterable[StrPath],
    algorithms: Sequence[AlgorithmLike] = (Algorithm.PHASH,),
    *,
    config: Config | None = None,
    threads: int = 0,
    progress: ProgressCallback | None = None,
) -> list[BatchResult]:
    """Hash many image files on libphash's pool of threads.

    Only the 64-bit algorithms (aHash, dHash, pHash, wHash) can be batched. A failed file
    does not stop the batch: its result carries the error. ``threads=0`` uses one thread
    per usable CPU, ``1`` runs on the calling thread. Each worker holds one decoded image
    at a time, so peak memory grows with the thread count (bound it with ``threads`` or
    ``Config.max_pixels``). Ctrl+C stops the batch and raises KeyboardInterrupt.
    """
    paths = list(paths)
    if READ_FILES_IN_PYTHON:
        return _files_via_buffers(paths, algorithms, config, threads, progress)
    algos, flags = _algorithms(algorithms)
    encoded = [ffi.new("char[]", encode_path(p)) for p in paths]
    items = ffi.new("ph_batch_item_t[]", len(paths))
    for item, path in zip(items, encoded):
        item.path = path
    with _Run(len(paths), config, threads, progress) as run:
        code = lib.ph_hash_files_ex(items, len(paths), flags, run.options)
        run.finish(code)
    return [_result(p, items[i], algos, path=p) for i, p in enumerate(paths)]


def hash_buffers(
    buffers: Iterable[bytes | bytearray | memoryview],
    algorithms: Sequence[AlgorithmLike] = (Algorithm.PHASH,),
    *,
    config: Config | None = None,
    threads: int = 0,
    progress: ProgressCallback | None = None,
) -> list[BatchResult]:
    """Hash many encoded images held in memory; see :func:`hash_files`.

    ``BatchResult.source`` is the buffer's index. The buffers must not change while the
    call runs.
    """
    algos, flags = _algorithms(algorithms)
    views = [ffi.from_buffer("const uint8_t[]", b) for b in buffers]
    items = ffi.new("ph_batch_buffer_item_t[]", len(views))
    for item, view in zip(items, views):
        item.buffer = view
        item.length = len(view)
    with _Run(len(views), config, threads, progress) as run:
        code = lib.ph_hash_buffers_ex(items, len(views), flags, run.options)
        run.finish(code)
    return [_result(i, items[i], algos) for i in range(len(views))]


def _files_via_buffers(
    paths: list[StrPath],
    algorithms: Sequence[AlgorithmLike],
    config: Config | None,
    threads: int,
    progress: ProgressCallback | None,
) -> list[BatchResult]:
    """hash_files() where the binding reads the files (see READ_FILES_IN_PYTHON).

    Files are read a chunk at a time, so that memory holds a few encoded files per worker
    and not the whole batch.
    """
    algos, _ = _algorithms(algorithms)
    workers = threads if threads > 0 else (os.cpu_count() or 1)
    chunk = max(64, 4 * workers)
    total = len(paths)
    results: list[BatchResult] = []
    stopped = False
    for start in range(0, total, chunk):
        part = paths[start : start + chunk]
        if stopped:
            results += [_cancelled(p) for p in part]
            continue
        data: list[bytes] = []
        failed: dict[int, PhashError] = {}
        for i, p in enumerate(part):
            try:
                content = read_file(p)
                if not content:
                    raise OSError(0, "empty file")
                data.append(content)
            except OSError as e:
                failed[i] = make_error(PH_ERR_IO, detail=f"{e.strerror}: {p!s}", path=p)
                data.append(b"\0")  # placeholder; its result is replaced below
        offset = start

        def chunk_progress(
            done: int, _total: int, offset: int = offset
        ) -> Optional[bool]:
            return progress(offset + done, total) if progress else None

        part_results = hash_buffers(
            data,
            algos,
            config=config,
            threads=threads,
            progress=chunk_progress if progress else None,
        )
        for i, (p, r) in enumerate(zip(part, part_results)):
            if i in failed:
                results.append(BatchResult(p, None, failed[i]))
            else:
                results.append(BatchResult(p, r.hashes, r.error))
            if r.error is not None and r.error.code == _PH_ERR_CANCELLED:
                stopped = True
    return results


def _cancelled(source: Any) -> BatchResult:
    return BatchResult(source, None, make_error(_PH_ERR_CANCELLED))


def _algorithms(algorithms: Sequence[AlgorithmLike]) -> tuple[list[Algorithm], int]:
    if isinstance(algorithms, (str, Algorithm)):
        algorithms = [algorithms]
    algos = sorted({to_algorithm(a) for a in algorithms})
    if not algos:
        raise InvalidArgumentError("no algorithm given")
    return algos, uint64_flags(algos)


def _result(
    source: Any, item: Any, algos: list[Algorithm], path: Any = None
) -> BatchResult:
    status = int(item.status)
    if status != PH_SUCCESS:
        return BatchResult(source, None, make_error(status, context=str(source), path=path))
    # Slots follow ascending flag bits, which is ascending Algorithm value.
    return BatchResult(
        source, {a: int(item.hashes[i]) for i, a in enumerate(algos)}, None
    )


class _Run:
    """Options, callbacks and Ctrl+C handling around one batch call."""

    def __init__(
        self,
        total: int,
        config: Config | None,
        threads: int,
        progress: ProgressCallback | None,
    ) -> None:
        if isinstance(threads, bool) or not isinstance(threads, int) or threads < 0:
            raise InvalidArgumentError(f"threads must be an int >= 0, got {threads!r}")
        self.total = total
        self.config = config if config is not None else Config()
        self.threads = threads
        self.progress = progress
        self.lock = threading.Lock()
        self.done = 0
        self.stop = False
        self.error: BaseException | None = None
        self.interrupted = False
        self.wakeup: socket.socket | None = None
        self.previous_wakeup = -1
        self.template: Any = None
        self.handle: Any = None
        self.options: Any = None

    def __enter__(self) -> _Run:
        self.template = _new_context()
        self.config._apply(self.template)
        self.options = ffi.new("ph_batch_options_t *")
        check(lib.ph_batch_options_init(self.options))
        self.handle = ffi.new_handle(self)
        self.options.config = self.template
        self.options.threads = self.threads
        self.options.should_continue = lib._libphash_should_continue
        self.options.user_data = self.handle
        if self.progress is not None:
            self.options.on_progress = lib._libphash_on_progress
        self._watch_sigint()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._unwatch_sigint()
        lib.ph_free(self.template)
        self.template = None

    def finish(self, code: int) -> None:
        """Check the batch's return code, re-raising a callback's exception."""
        if self.error is not None:
            raise self.error
        if code not in (PH_SUCCESS, _PH_ERR_CANCELLED):
            raise make_error(code, context="batch")

    # Ctrl+C: while the batch runs, the main thread is inside C and Python's SIGINT
    # handler cannot run. Its C-level handler still writes the signal number to the
    # wakeup fd, which should_continue polls; KeyboardInterrupt follows as usual once
    # the call returns.
    def _watch_sigint(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        reader, writer = socket.socketpair()
        reader.setblocking(False)
        writer.setblocking(False)
        try:
            previous = signal.set_wakeup_fd(writer.fileno(), warn_on_full_buffer=False)
        except (ValueError, OSError):
            reader.close()
            writer.close()
            return
        if previous != -1:
            # Someone (an event loop) owns the wakeup fd; leave it to them.
            signal.set_wakeup_fd(previous)
            reader.close()
            writer.close()
            return
        self.wakeup = reader
        self._writer = writer

    def _unwatch_sigint(self) -> None:
        if self.wakeup is not None:
            signal.set_wakeup_fd(-1)
            self.wakeup.close()
            self._writer.close()
            self.wakeup = None

    def should_continue(self) -> bool:
        with self.lock:
            if self.stop:
                return False
            if self.wakeup is not None:
                try:
                    received = self.wakeup.recv(64)
                except (BlockingIOError, InterruptedError):
                    received = b""
                if int(signal.SIGINT) in received:
                    self.interrupted = True
                    self.stop = True
                    return False
            return True

    def on_progress(self) -> None:
        if self.progress is None:
            return
        with self.lock:
            self.done += 1
            done = self.done
            if self.stop:
                return
            try:
                if self.progress(done, self.total) is False:
                    self.stop = True
            except BaseException as e:  # noqa: BLE001 -- re-raised from finish()
                self.error = e
                self.stop = True


@ffi.def_extern()  # type: ignore[untyped-decorator]
def _libphash_should_continue(user_data: Any) -> int:
    try:
        run: _Run = ffi.from_handle(user_data)
        return 1 if run.should_continue() else 0
    except BaseException:  # noqa: BLE001 -- a callback must not raise into C
        return 0


@ffi.def_extern()  # type: ignore[untyped-decorator]
def _libphash_on_progress(done: int, total: int, user_data: Any) -> None:
    try:
        run: _Run = ffi.from_handle(user_data)
        run.on_progress()
    except BaseException:  # noqa: BLE001 -- a callback must not raise into C
        pass
