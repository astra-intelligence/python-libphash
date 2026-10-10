"""Exceptions raised by libphash.

Every failure of the C library becomes a subclass of :class:`PhashError`, chosen by its
``ph_error_t`` code. The classes also derive from the built-in exception a Python
programmer would reach for: an unreadable file is an :class:`OSError` (with ``errno``, so
``except FileNotFoundError`` works), a bad argument a :class:`ValueError`, a failed
allocation a :class:`MemoryError`.
"""

from __future__ import annotations

import errno as _errno
import os
from typing import Any

from ._native import ffi, lib

__all__ = [
    "PhashError",
    "ImageIOError",
    "DecodeError",
    "UnsupportedFormatError",
    "CorruptDataError",
    "DecoderUnavailableError",
    "ImageTooLargeError",
    "InvalidArgumentError",
    "AllocationError",
    "EmptyImageError",
    "RequiresColorError",
    "NoStructureError",
    "BatchCancelledError",
    "DigestKindError",
]


class PhashError(Exception):
    """Base class of every libphash error.

    Attributes:
        code: the ``ph_error_t`` value, or 0 for an error raised by the binding itself.
        code_name: the C name of the code (``"PH_ERR_IO"``), or ``""``.
        detail: the C library's description of this failure (for loading: the path and
            the reason), or ``""``.
    """

    code: int
    code_name: str
    detail: str

    def __init__(self, message: str, *, code: int = 0, detail: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.code_name = _CODE_NAMES.get(code, "") if code else ""
        self.detail = detail

    def __reduce__(self) -> tuple[Any, ...]:
        return (_rebuild, (type(self), str(self), self.code, self.detail))


def _rebuild(cls: type[PhashError], message: str, code: int, detail: str) -> PhashError:
    exc = cls.__new__(cls)
    PhashError.__init__(exc, message, code=code, detail=detail)
    return exc


class ImageIOError(PhashError, OSError):
    """The path could not be used as an image source (``PH_ERR_IO``).

    ``errno`` and ``filename`` are filled in when the cause can be told (a missing file,
    a directory, no permission), so the matching :class:`OSError` subclass catches it:
    ``except FileNotFoundError`` sees a missing image file.
    """

    def __init__(self, message: str, *, code: int = 0, detail: str = "") -> None:
        PhashError.__init__(self, message, code=code, detail=detail)

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""

    def __repr__(self) -> str:
        # The errno-specific subclasses are an implementation detail.
        return f"ImageIOError({str(self)!r})"

    def __reduce__(self) -> tuple[Any, ...]:
        return (
            _rebuild_io,
            (type(self), str(self), self.code, self.detail, self.errno, self.filename),
        )


def _rebuild_io(
    cls: type[ImageIOError],
    message: str,
    code: int,
    detail: str,
    err: int | None,
    filename: Any,
) -> ImageIOError:
    exc = cls.__new__(cls)
    ImageIOError.__init__(exc, message, code=code, detail=detail)
    exc.errno = err
    exc.filename = filename
    return exc


class _FileNotFound(ImageIOError, FileNotFoundError):
    pass


class _PermissionDenied(ImageIOError, PermissionError):
    pass


class _IsADirectory(ImageIOError, IsADirectoryError):
    pass


class DecodeError(PhashError):
    """The data could not be decoded into an image. Parent of the four reasons below."""


class UnsupportedFormatError(DecodeError):
    """The data is in no image format libphash recognizes."""


class CorruptDataError(DecodeError):
    """The format was recognized, but the data is malformed or truncated."""


class DecoderUnavailableError(DecodeError):
    """The format was recognized, but this build has no decoder for it."""


class ImageTooLargeError(DecodeError):
    """The image has more pixels than ``Config.max_pixels`` or the library's fixed limit."""


class InvalidArgumentError(PhashError, ValueError):
    """An argument is outside the range the C library accepts."""


class AllocationError(PhashError, MemoryError):
    """A memory allocation failed in the C library."""


class EmptyImageError(PhashError):
    """A hash was requested from a context that holds no image."""


class RequiresColorError(PhashError):
    """A color algorithm was asked for an image loaded in grayscale."""


class NoStructureError(PhashError):
    """A Radial digest has no structure to correlate (a flat image)."""


class BatchCancelledError(PhashError):
    """A batch was stopped before every item was started."""


class DigestKindError(PhashError, TypeError):
    """Two digests were compared by a metric their kind does not support."""


def _code(name: str) -> int:
    return int(getattr(lib, name))


_CLASSES: dict[int, type[PhashError]] = {
    _code("PH_ERR_ALLOCATION_FAILED"): AllocationError,
    _code("PH_ERR_INVALID_ARGUMENT"): InvalidArgumentError,
    _code("PH_ERR_EMPTY_IMAGE"): EmptyImageError,
    _code("PH_ERR_IMAGE_TOO_LARGE"): ImageTooLargeError,
    _code("PH_ERR_UNSUPPORTED_FORMAT"): UnsupportedFormatError,
    _code("PH_ERR_CORRUPT_DATA"): CorruptDataError,
    _code("PH_ERR_DECODER_UNAVAILABLE"): DecoderUnavailableError,
    _code("PH_ERR_IO"): ImageIOError,
    _code("PH_ERR_REQUIRES_COLOR"): RequiresColorError,
    _code("PH_ERR_CANCELLED"): BatchCancelledError,
    _code("PH_ERR_NO_STRUCTURE"): NoStructureError,
}

_CODE_NAMES: dict[int, str] = {
    int(getattr(lib, name)): name
    for name in dir(lib)
    if name.startswith("PH_ERR_") and not name.endswith("_")
}

PH_SUCCESS = int(lib.PH_SUCCESS)
PH_ERR_IO = int(lib.PH_ERR_IO)


def error_string(code: int) -> str:
    return str(ffi.string(lib.ph_get_error_string(code)).decode())


def make_error(
    code: int, *, context: str = "", detail: str = "", path: Any = None
) -> PhashError:
    """Build the exception for a ``ph_error_t``.

    ``context`` says what the binding was doing ("computing phash"); ``detail`` is the C
    library's message for a load, and is passed only by the load functions, the only ones
    that write it.
    """
    cls = _CLASSES.get(code, PhashError)
    text = error_string(code)
    message = detail or text
    if context:
        message = f"{context}: {message}"
    if cls is ImageIOError:
        return _io_error(message, code, detail, path)
    return cls(message, code=code, detail=detail)


def _io_error(message: str, code: int, detail: str, path: Any) -> ImageIOError:
    err: int | None = None
    cls: type[ImageIOError] = ImageIOError
    if path is not None:
        # The C library reports every unusable path as PH_ERR_IO; the file system tells
        # which OSError it is.
        try:
            if os.path.isdir(path):
                err, cls = _errno.EISDIR, _IsADirectory
            elif not os.path.lexists(path) or not os.path.exists(path):
                err, cls = _errno.ENOENT, _FileNotFound
            elif not os.access(path, os.R_OK):
                err, cls = _errno.EACCES, _PermissionDenied
        except (OSError, ValueError):
            pass
    exc = cls(message, code=code, detail=detail)
    exc.errno = err
    exc.filename = os.fsdecode(path) if path is not None else None
    return exc


def check(code: int, *, context: str = "") -> None:
    """Raise the exception for ``code`` unless it is ``PH_SUCCESS``."""
    if code != PH_SUCCESS:
        raise make_error(code, context=context)
