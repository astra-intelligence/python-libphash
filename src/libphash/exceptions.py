from __future__ import annotations
from ._native import ffi, lib


class PhashError(Exception):
    """Base exception for libphash library."""


class AllocationError(PhashError):
    """Raised when memory allocation fails in the C layer."""


class DecodeError(PhashError):
    """Raised when the image data is in no supported format, or is corrupt."""


class InvalidArgumentError(PhashError):
    """Raised when an invalid argument is passed to the C function."""


class NotImplementedError(PhashError):
    """Raised when a feature is not implemented or disabled at compile-time."""


class EmptyImageError(PhashError):
    """Raised when an operation is requested on an empty context."""


def check_error(err_code: int) -> None:
    """Map a ph_error_t return code to a Python exception."""
    if err_code == lib.PH_SUCCESS:
        return

    errors: dict[int, type[PhashError]] = {
        lib.PH_ERR_ALLOCATION_FAILED: AllocationError,
        lib.PH_ERR_INVALID_ARGUMENT: InvalidArgumentError,
        lib.PH_ERR_EMPTY_IMAGE: EmptyImageError,
        lib.PH_ERR_UNSUPPORTED_FORMAT: DecodeError,
        lib.PH_ERR_CORRUPT_DATA: DecodeError,
        lib.PH_ERR_DECODER_UNAVAILABLE: DecodeError,
    }
    exc_class = errors.get(err_code, PhashError)
    msg = ffi.string(lib.ph_get_error_string(err_code)).decode()
    raise exc_class(msg)
