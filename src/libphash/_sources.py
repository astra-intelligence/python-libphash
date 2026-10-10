"""Turning what a caller has into C arguments.

A caller has a path, bytes, an array of pixels or a Pillow image.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol, Union, cast, runtime_checkable

from ._native import ffi

#: A file system path, as ``open()`` takes it.
StrPath = Union[str, bytes, "os.PathLike[str]", "os.PathLike[bytes]"]
#: Order of the color channels in an array of pixels: ``"bgr"`` is OpenCV's.
ChannelOrder = Literal["rgb", "bgr"]


class SupportsRead(Protocol):
    """A binary file object: an open file, ``io.BytesIO``, a response body."""

    def read(self) -> bytes: ...


@runtime_checkable
class SupportsArrayInterface(Protocol):
    """An array exposing numpy's ``__array_interface__``.

    A numpy array is one, and so is a Pillow image.
    """

    @property
    def __array_interface__(self) -> Mapping[str, Any]: ...


class PILImage(Protocol):
    """The part of ``PIL.Image.Image`` the binding reads."""

    @property
    def mode(self) -> str: ...
    @property
    def size(self) -> tuple[int, int]: ...
    @property
    def info(self) -> Mapping[Any, Any]: ...
    def tobytes(self) -> bytes: ...
    def convert(self, mode: str) -> PILImage: ...


#: Decoded 8-bit pixels of shape (h, w) or (h, w, 1|3|4): a numpy array, a memoryview.
PixelArray = Union[SupportsArrayInterface, memoryview]

#: Everything :func:`libphash.hash` and :meth:`ImageContext.load` accept: a path,
#: encoded bytes, a binary file object, an array of pixels or a Pillow image. ``bytes``
#: are always encoded image data, never a path.
Source = Union[
    str,
    "os.PathLike[str]",
    "os.PathLike[bytes]",
    bytes,
    bytearray,
    memoryview,
    SupportsArrayInterface,
    SupportsRead,
]

#: Paths reach the C library's narrow-character open(), which on Windows reads the ANSI
#: code page, not the UTF-8 that os.fsencode() gives. On Windows the binding therefore
#: reads the file itself and loads it from memory.
READ_FILES_IN_PYTHON = sys.platform == "win32"


def encode_path(path: StrPath) -> bytes:
    """Return the path as the bytes the C library gets.

    They are the file system encoding of the path: on POSIX, the path's bytes unchanged.
    """
    try:
        return os.fsencode(path)
    except TypeError:
        raise TypeError(
            f"expected a path (str, bytes or os.PathLike), got {type(path).__name__}"
        ) from None


def is_pil_image(obj: object) -> bool:
    module = type(obj).__module__ or ""
    return (
        module.startswith("PIL.") and hasattr(obj, "mode") and hasattr(obj, "tobytes")
    )


@dataclass
class Pixels:
    """Arguments for ph_load_from_pixels().

    ``keepalive`` holds whatever must stay alive during the call.
    """

    pointer: Any
    width: int
    height: int
    channels: int
    stride: int
    keepalive: Any


def pixels_from_array(obj: PixelArray, channel_order: ChannelOrder = "rgb") -> Pixels:
    """Read the pixels of an 8-bit array of shape (h, w) or (h, w, 1|3|4).

    A numpy array whose rows are spaced apart (a crop, ``arr[10:-10, 5:-5]``) is passed
    without a copy, its row step as the C stride; one with gaps or reversed order inside
    a row, or in BGR order, is copied once.
    """
    if channel_order not in ("rgb", "bgr"):
        raise ValueError(f"channel_order must be 'rgb' or 'bgr', got {channel_order!r}")
    iface = getattr(obj, "__array_interface__", None)
    if iface is not None:
        return _from_array_interface(obj, iface, channel_order)
    try:
        # Any object with the buffer protocol and a shape, beyond what PixelArray names.
        view = obj if isinstance(obj, memoryview) else memoryview(cast("Any", obj))
    except TypeError:
        raise TypeError(
            "expected an array of pixels (numpy, memoryview with a shape), "
            f"got {type(obj).__name__}"
        ) from None
    if view.format not in ("B", "c") or view.itemsize != 1:
        raise TypeError(
            f"pixels must be 8-bit unsigned (format 'B'), got format {view.format!r}; "
            "convert the array to uint8 first"
        )
    height, width, channels = _shape(tuple(view.shape or ()))
    if view.c_contiguous and channel_order == "rgb":
        return Pixels(ffi.from_buffer(view), width, height, channels, 0, view)
    data = view.tobytes()
    return _packed(data, width, height, channels, channel_order)


def _from_array_interface(
    obj: object, iface: Mapping[str, Any], channel_order: ChannelOrder
) -> Pixels:
    typestr = iface.get("typestr", "")
    if typestr[1:] != "u1":
        raise TypeError(
            f"pixels must be uint8, got typestr {typestr!r}; "
            "convert the array to uint8 first"
        )
    height, width, channels = _shape(tuple(iface["shape"]))
    strides = iface.get("strides")
    if strides is None:  # C-contiguous
        strides = (width * channels, channels, 1)[: len(iface["shape"])]
    row = strides[0]
    pixel = strides[1]
    channel = strides[2] if len(strides) == 3 else 1
    data = iface.get("data")
    zero_copy = (
        channel_order == "rgb"
        and pixel == channels
        and channel == 1
        and row >= width * channels
    )
    if zero_copy and isinstance(data, tuple):
        pointer = ffi.cast("const uint8_t *", data[0])
        return Pixels(pointer, width, height, channels, row, obj)
    # Any other layout: one C-ordered copy through the buffer protocol.
    try:
        packed = memoryview(cast("Any", obj)).tobytes()
    except TypeError:
        raise TypeError(
            "the array does not expose its data through the buffer protocol"
        ) from None
    return _packed(packed, width, height, channels, channel_order)


def _packed(
    data: bytes, width: int, height: int, channels: int, order: ChannelOrder
) -> Pixels:
    if order == "bgr":
        if channels < 3:
            raise ValueError("channel_order='bgr' needs 3 or 4 channels")
        swapped = bytearray(data)
        swapped[0::channels], swapped[2::channels] = (
            data[2::channels],
            data[0::channels],
        )
        data = bytes(swapped)
    return Pixels(ffi.from_buffer(data), width, height, channels, 0, data)


def _shape(shape: tuple[int, ...]) -> tuple[int, int, int]:
    if len(shape) == 2:
        return shape[0], shape[1], 1
    if len(shape) == 3 and shape[2] in (1, 3, 4):
        return shape[0], shape[1], shape[2]
    raise ValueError(
        f"pixels must have shape (height, width) or (height, width, 1|3|4), got {shape}"
    )


_PIL_DIRECT = {"L": 1, "RGB": 3, "RGBA": 4}
_PIL_UNSUPPORTED = ("I", "I;16", "I;16B", "I;16L", "I;16N", "F")


def pixels_from_pil(img: PILImage) -> Pixels:
    """Read the pixels of a Pillow image.

    ``L``, ``RGB`` and ``RGBA`` are read as they are. ``1`` becomes ``L``; palette and
    gray-with-alpha images become ``RGBA`` (``RGB`` when they carry no transparency);
    ``CMYK``, ``YCbCr``, ``HSV`` and ``LAB`` become ``RGB``. 16-bit, 32-bit integer and
    float modes are refused: there is no single right way to bring them to 8 bits.
    Pillow does not apply the EXIF orientation to the pixels; pass the image through
    ``PIL.ImageOps.exif_transpose`` first if it matters.
    """
    mode = img.mode
    if mode in _PIL_UNSUPPORTED:
        raise TypeError(
            f"Pillow mode {mode!r} is not 8-bit; "
            "convert it (img.convert('L') or 'RGB') first"
        )
    if mode not in _PIL_DIRECT:
        if mode == "1":
            target = "L"
        elif mode in ("P", "PA", "LA", "La", "RGBa"):
            has_alpha = mode != "P" or "transparency" in img.info
            target = "RGBA" if has_alpha else "RGB"
        else:
            target = "RGB"
        img = img.convert(target)
        mode = target
    width, height = img.size
    data = img.tobytes()
    channels = _PIL_DIRECT[mode]
    return Pixels(ffi.from_buffer(data), width, height, channels, 0, data)


def read_file(path: StrPath) -> bytes:
    with open(path, "rb") as f:
        return f.read()
