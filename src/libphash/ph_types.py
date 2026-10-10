from __future__ import annotations
from enum import Enum
from typing import Any, final
from ._native import ffi, lib

PH_DIGEST_MAX_BYTES: int = 64


class HashMethod(Enum):
    AHASH = "ahash"
    DHASH = "dhash"
    PHASH = "phash"
    WHASH = "whash"
    MHASH = "mhash"
    COLORHASH = "color_hash"


@final
class Digest:
    _data: bytes
    _size: int

    def __init__(self, data: bytes, size: int) -> None:
        if len(data) > PH_DIGEST_MAX_BYTES:
            raise ValueError(f"Data exceeds max size ({PH_DIGEST_MAX_BYTES})")
        self._data = data
        self._size = size

    @property
    def data(self) -> bytes:
        return self._data

    @property
    def size(self) -> int:
        return self._size

    @classmethod
    def from_c_struct(cls, c_digest: Any) -> Digest:
        # c_digest is a cdata ph_digest_t, typed as Any in _native.pyi.
        size = int(c_digest.size)
        raw_buffer = ffi.buffer(c_digest.data, size)
        return cls(bytes(raw_buffer), size)

    def to_c_struct(self) -> Any:
        c_ptr = ffi.new("ph_digest_t *")
        c_ptr.size = self._size
        ffi.memmove(c_ptr.data, self._data, len(self._data))
        return c_ptr

    def distance_hamming(self, other: Digest) -> int:
        if self._size != other._size:
            raise ValueError("Digests must have the same size")
        return lib.ph_hamming_distance_digest(self.to_c_struct(), other.to_c_struct())

    def distance_l2(self, other: Digest) -> float:
        if self._size != other._size:
            raise ValueError("Digests must have the same size")
        return lib.ph_l2_distance(self.to_c_struct(), other.to_c_struct())
