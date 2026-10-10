from __future__ import annotations

from enum import IntEnum
from typing import Union

from ._native import ffi, lib
from ._errors import PH_SUCCESS
from .exceptions import InvalidArgumentError


class Algorithm(IntEnum):
    """A hash algorithm; the values are libphash's ``ph_algorithm_t``.

    Wherever an algorithm is expected, its libphash name (``"phash"``,
    ``"color_moments"``) is accepted too; ``str(algorithm)`` is that name.
    """

    # Literal values, so that type checkers see the members (libphash never changes an
    # existing value; the tests compare them with the C enum).

    AHASH = 0
    DHASH = 1
    PHASH = 2
    WHASH = 3
    BMH = 4
    MHASH = 5
    RADIAL = 6
    COLOR_HASH = 7
    COLOR_MOMENTS = 8

    def __str__(self) -> str:
        return str(ffi.string(lib.ph_algorithm_name(self.value)).decode())


class DigestKind(IntEnum):
    """What a digest's bytes mean, and so which comparisons it supports (``ph_digest_kind_t``)."""

    UNSPECIFIED = 0
    BITS = 1
    COEFFICIENTS = 2
    VECTOR = 3
    HISTOGRAM = 4
    VECTOR16 = 5


AlgorithmLike = Union["Algorithm", str]

#: The algorithms that produce a 64-bit integer; the others produce a Digest.
UINT64_ALGORITHMS = frozenset(
    Algorithm[name] for name in ("AHASH", "DHASH", "PHASH", "WHASH")
)


def to_algorithm(value: object) -> Algorithm:
    if isinstance(value, Algorithm):
        return value
    if isinstance(value, str):
        out = ffi.new("ph_algorithm_t *")
        if lib.ph_algorithm_from_name(value.encode(), out) != PH_SUCCESS:
            names = ", ".join(str(a) for a in Algorithm)
            raise InvalidArgumentError(
                f"unknown algorithm {value!r}; expected one of {names}"
            )
        return Algorithm(int(out[0]))
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            return Algorithm(value)
        except ValueError:
            pass
    raise InvalidArgumentError(f"expected an Algorithm or its name, got {value!r}")


def uint64_flags(algorithms: list[Algorithm]) -> int:
    """The ph_hash_flags_t bits of uint64 algorithms: bit ``1 << value``."""
    flags = 0
    for algo in algorithms:
        if algo not in UINT64_ALGORITHMS:
            raise InvalidArgumentError(
                f"{algo} produces a digest; only {', '.join(str(a) for a in sorted(UINT64_ALGORITHMS))} "
                "can be computed together or in a batch"
            )
        flags |= 1 << int(algo)
    return flags
