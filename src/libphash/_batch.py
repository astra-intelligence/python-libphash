from __future__ import annotations

import os
import signal
import socket
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Generic,
    TypeVar,
    cast,
)

from ._algorithms import Algorithm, AlgorithmLike, to_algorithm, uint64_flags
from ._config import Config, apply_config, new_context
from ._errors import PH_ERR_CANCELLED, PH_ERR_IO, PH_SUCCESS, check, make_error
from ._native import ffi, lib
from ._sources import READ_FILES_IN_PYTHON, StrPath, encode_path, read_file
from .exceptions import InvalidArgumentError, PhashError

if TYPE_CHECKING:
    from typing_extensions import Self

    from ._native import ph_batch_buffer_item_t, ph_batch_item_t, void_ptr

#: Called as ``progress(done, total)`` after each finished item; returning ``False``
#: stops the batch (items not yet started get BatchCancelledError).
ProgressCallback = Callable[[int, int], bool | None]

_S = TypeVar("_S")
_P = TypeVar("_P", bound=StrPath)
_Algorithms = AlgorithmLike | Iterable[AlgorithmLike]


@dataclass(frozen=True)
class BatchResult(Generic[_S]):
    """The outcome for one item of a batch.

    :func:`hash_files` gives ``BatchResult[path type]``, :func:`hash_buffers` gives
    ``BatchResult[int]`` (the buffer's index).
    """

    #: The path or buffer index the item was given as.
    source: _S
    #: The hashes by algorithm, or None if the item failed.
    hashes: dict[Algorithm, int] | None
    #: Why the item failed, or None.
    error: PhashError | None

    @property
    def ok(self) -> bool:
        return self.error is None


def hash_files(
    paths: Iterable[_P],
    algorithms: _Algorithms = (Algorithm.PHASH,),
    *,
    config: Config | None = None,
    threads: int = 0,
    progress: ProgressCallback | None = None,
) -> list[BatchResult[_P]]:
    """Hash many image files on libphash's pool of threads.

    Only the 64-bit algorithms (aHash, dHash, pHash, wHash) can be batched. A failed
    file does not stop the batch: its result carries the error. ``threads=0`` uses one
    thread per usable CPU, ``1`` runs on the calling thread. Each worker holds one
    decoded image at a time, so peak memory grows with the thread count (bound it with
    ``threads`` or ``Config.max_pixels``). Ctrl+C stops the batch and raises
    KeyboardInterrupt.
    """
    paths = list(paths)
    if READ_FILES_IN_PYTHON:
        return _files_via_buffers(paths, algorithms, config, threads, progress)
    algos, flags = _algorithms(algorithms)
    encoded = [ffi.new("char[]", encode_path(p)) for p in paths]
    items = ffi.new("ph_batch_item_t[]", len(paths))
    for item, path in zip(items, encoded, strict=True):
        item.path = path
    with _Run(len(paths), config, threads, progress) as run:
        code = lib.ph_hash_files_ex(items, len(paths), flags, run.options)
        run.finish(code)
    return [_result(p, items[i], algos, path=p) for i, p in enumerate(paths)]


def hash_buffers(
    buffers: Iterable[bytes | bytearray | memoryview],
    algorithms: _Algorithms = (Algorithm.PHASH,),
    *,
    config: Config | None = None,
    threads: int = 0,
    progress: ProgressCallback | None = None,
) -> list[BatchResult[int]]:
    """Hash many encoded images held in memory; see :func:`hash_files`.

    ``BatchResult.source`` is the buffer's index. The buffers must not change while the
    call runs.
    """
    algos, flags = _algorithms(algorithms)
    views = [ffi.from_buffer("const uint8_t[]", b) for b in buffers]
    items = ffi.new("ph_batch_buffer_item_t[]", len(views))
    for item, view in zip(items, views, strict=True):
        item.buffer = view
        item.length = len(view)
    with _Run(len(views), config, threads, progress) as run:
        code = lib.ph_hash_buffers_ex(items, len(views), flags, run.options)
        run.finish(code)
    return [_result(i, items[i], algos) for i in range(len(views))]


def _files_via_buffers(
    paths: list[_P],
    algorithms: _Algorithms,
    config: Config | None,
    threads: int,
    progress: ProgressCallback | None,
) -> list[BatchResult[_P]]:
    """hash_files() where the binding reads the files (see READ_FILES_IN_PYTHON).

    Files are read a chunk at a time, so that memory holds a few encoded files per
    worker and not the whole batch.
    """
    algos, _ = _algorithms(algorithms)
    workers = threads if threads > 0 else (os.cpu_count() or 1)
    chunk = max(64, 4 * workers)
    total = len(paths)
    results: list[BatchResult[_P]] = []
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
            except OSError as e:  # noqa: PERF203 -- each file fails on its own
                failed[i] = make_error(PH_ERR_IO, detail=f"{e.strerror}: {p!s}", path=p)
                data.append(b"\0")  # placeholder; its result is replaced below
        offset = start

        def chunk_progress(done: int, _total: int, offset: int = offset) -> bool | None:
            return progress(offset + done, total) if progress else None

        part_results = hash_buffers(
            data,
            algos,
            config=config,
            threads=threads,
            progress=chunk_progress if progress else None,
        )
        for i, (p, r) in enumerate(zip(part, part_results, strict=True)):
            if i in failed:
                results.append(BatchResult(p, None, failed[i]))
            else:
                results.append(BatchResult(p, r.hashes, r.error))
            if r.error is not None and r.error.code == PH_ERR_CANCELLED:
                stopped = True
    return results


def _cancelled(source: _S) -> BatchResult[_S]:
    return BatchResult(source, None, make_error(PH_ERR_CANCELLED))


def _algorithms(algorithms: _Algorithms) -> tuple[list[Algorithm], int]:
    if isinstance(algorithms, (str, Algorithm)):
        algos = [to_algorithm(algorithms)]
    else:
        algos = sorted({to_algorithm(a) for a in algorithms})
    if not algos:
        raise InvalidArgumentError("no algorithm given")
    return algos, uint64_flags(algos)


def _result(
    source: _S,
    item: ph_batch_item_t | ph_batch_buffer_item_t,
    algos: list[Algorithm],
    path: StrPath | None = None,
) -> BatchResult[_S]:
    status = int(item.status)
    if status != PH_SUCCESS:
        return BatchResult(
            source, None, make_error(status, context=str(source), path=path)
        )
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
        self.total = total
        self.config = config if config is not None else Config()
        self.threads = _check_threads(threads)
        self.progress = progress
        self.lock = threading.Lock()
        self.done = 0
        self.stop = False
        self.error: BaseException | None = None
        self.wakeup: socket.socket | None = None
        self.options = ffi.new("ph_batch_options_t *")
        check(lib.ph_batch_options_init(self.options))
        self.handle = ffi.new_handle(self)
        self.options.threads = self.threads
        self.options.should_continue = lib._libphash_should_continue
        self.options.user_data = self.handle
        if self.progress is not None:
            self.options.on_progress = lib._libphash_on_progress

    def __enter__(self) -> Self:
        template = new_context()
        try:
            apply_config(self.config, template)
        except BaseException:
            lib.ph_free(template)
            raise
        self.options.config = template
        _escaped.error = None
        self._watch_sigint()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._unwatch_sigint()
        lib.ph_free(self.options.config)
        self.options.config = ffi.NULL

    def finish(self, code: int) -> None:
        """Check the batch's return code, re-raising a callback's exception."""
        escaped, _escaped.error = _escaped.error, None
        if escaped is not None:
            raise escaped
        if self.error is not None:
            raise self.error
        if code not in (PH_SUCCESS, PH_ERR_CANCELLED):
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
                    self.stop = True
                    return False
            return True

    def on_progress(self) -> None:
        # The callback is registered only with a progress function.
        progress = cast("ProgressCallback", self.progress)
        with self.lock:
            self.done += 1
            done = self.done
            if self.stop:
                return
            try:
                if progress(done, self.total) is False:
                    self.stop = True
            except BaseException as e:  # noqa: BLE001 -- re-raised from finish()
                self.error = e
                self.stop = True


def _check_threads(threads: object) -> int:
    if isinstance(threads, bool) or not isinstance(threads, int) or threads < 0:
        raise InvalidArgumentError(f"threads must be an int >= 0, got {threads!r}")
    return threads


class _Escaped(threading.local):
    error: BaseException | None = None


# An exception that leaves a callback never reaches C: cffi passes it to
# _keep_escaped and returns 0 to C, which stops the batch. Such an exception can
# arrive as the callback is entered, before any line of it runs: KeyboardInterrupt,
# when the calling thread runs the callbacks (threads=1). It is kept per thread and
# re-raised by finish() on the calling thread; on a worker thread it only stops the
# batch, since the calling thread cannot see it.
_escaped = _Escaped()


def _keep_escaped(
    _type: type[BaseException] | None, value: BaseException | None, _tb: object
) -> None:
    _escaped.error = value


@ffi.def_extern(name="_libphash_should_continue", onerror=_keep_escaped)
def should_continue_callback(user_data: void_ptr) -> int:
    run = cast("_Run", ffi.from_handle(user_data))
    return 1 if run.should_continue() else 0


@ffi.def_extern(name="_libphash_on_progress", onerror=_keep_escaped)
def on_progress_callback(_done: int, _total: int, user_data: void_ptr) -> None:
    run = cast("_Run", ffi.from_handle(user_data))
    run.on_progress()
