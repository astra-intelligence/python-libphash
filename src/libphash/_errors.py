"""Turning a ``ph_error_t`` into the exception of :mod:`libphash.exceptions`."""

from __future__ import annotations

import errno
import os
from typing import Optional

from ._native import ffi, lib
from .exceptions import (
    AllocationError,
    BatchCancelledError,
    CorruptDataError,
    DecoderUnavailableError,
    EmptyImageError,
    ImageIOError,
    ImageTooLargeError,
    InvalidArgumentError,
    NoStructureError,
    PhashError,
    RequiresColorError,
    UnsupportedFormatError,
)
from ._sources import StrPath

PH_SUCCESS = int(lib.PH_SUCCESS)
PH_ERR_IO = int(lib.PH_ERR_IO)
PH_ERR_CANCELLED = int(lib.PH_ERR_CANCELLED)


# The OSError subclasses an ImageIOError is raised as, so that ``except
# FileNotFoundError`` catches a missing image file. Their repr is ImageIOError's.
class FileNotFoundImageError(ImageIOError, FileNotFoundError):
    pass


class PermissionDeniedImageError(ImageIOError, PermissionError):
    pass


class IsADirectoryImageError(ImageIOError, IsADirectoryError):
    pass


_CLASSES: dict[int, type[PhashError]] = {
    int(lib.PH_ERR_ALLOCATION_FAILED): AllocationError,
    int(lib.PH_ERR_INVALID_ARGUMENT): InvalidArgumentError,
    int(lib.PH_ERR_EMPTY_IMAGE): EmptyImageError,
    int(lib.PH_ERR_IMAGE_TOO_LARGE): ImageTooLargeError,
    int(lib.PH_ERR_UNSUPPORTED_FORMAT): UnsupportedFormatError,
    int(lib.PH_ERR_CORRUPT_DATA): CorruptDataError,
    int(lib.PH_ERR_DECODER_UNAVAILABLE): DecoderUnavailableError,
    PH_ERR_IO: ImageIOError,
    int(lib.PH_ERR_REQUIRES_COLOR): RequiresColorError,
    PH_ERR_CANCELLED: BatchCancelledError,
    int(lib.PH_ERR_NO_STRUCTURE): NoStructureError,
}


def error_string(code: int) -> str:
    """The C library's one-line description of a ``ph_error_t``."""
    return str(ffi.string(lib.ph_get_error_string(code)).decode())


def make_error(
    code: int, *, context: str = "", detail: str = "", path: Optional[StrPath] = None
) -> PhashError:
    """Build the exception for a ``ph_error_t``.

    ``context`` says what the binding was doing ("computing phash"); ``detail`` is the C
    library's message for a load, and is passed only by the load functions, the only ones
    that write it.
    """
    cls = _CLASSES.get(code, PhashError)
    message = detail or error_string(code)
    if context:
        message = f"{context}: {message}"
    if cls is ImageIOError:
        return _io_error(message, code, detail, path)
    return cls(message, code=code, detail=detail)


def _io_error(
    message: str, code: int, detail: str, path: Optional[StrPath]
) -> ImageIOError:
    err: Optional[int] = None
    cls: type[ImageIOError] = ImageIOError
    if path is not None:
        # The C library reports every unusable path as PH_ERR_IO; the file system tells
        # which OSError it is.
        try:
            if os.path.isdir(path):
                err, cls = errno.EISDIR, IsADirectoryImageError
            elif not os.path.exists(path):
                err, cls = errno.ENOENT, FileNotFoundImageError
            elif not os.access(path, os.R_OK):
                err, cls = errno.EACCES, PermissionDeniedImageError
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
