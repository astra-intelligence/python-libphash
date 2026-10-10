"""Exceptions raised by libphash.

Every failure of the C library becomes a subclass of :class:`PhashError`, chosen by its
``ph_error_t`` code. The classes also derive from the built-in exception a Python
programmer would reach for: an unreadable file is an :class:`OSError` (with ``errno``,
so ``except FileNotFoundError`` works), a bad argument a :class:`ValueError`, a failed
allocation a :class:`MemoryError`.
"""

from __future__ import annotations

from typing import Any

from ._native import lib

__all__ = [
    "AllocationError",
    "BatchCancelledError",
    "CorruptDataError",
    "DecodeError",
    "DecoderUnavailableError",
    "DigestKindError",
    "EmptyImageError",
    "ImageIOError",
    "ImageTooLargeError",
    "InvalidArgumentError",
    "NoStructureError",
    "PhashError",
    "RequiresColorError",
    "UnsupportedFormatError",
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


def _rebuild_io(  # noqa: PLR0913 -- one argument per pickled field
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


class DecodeError(PhashError):
    """The data could not be decoded into an image. Parent of the four reasons below."""


class UnsupportedFormatError(DecodeError):
    """The data is in no image format libphash recognizes."""


class CorruptDataError(DecodeError):
    """The format was recognized, but the data is malformed or truncated."""


class DecoderUnavailableError(DecodeError):
    """The format was recognized, but this build has no decoder for it."""


class ImageTooLargeError(DecodeError):
    """The image is larger than ``Config.max_pixels`` or the library's fixed limits."""


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


_CODE_NAMES: dict[int, str] = {
    int(getattr(lib, name)): name
    for name in dir(lib)
    if name.startswith("PH_ERR_") and not name.endswith("_")
}
