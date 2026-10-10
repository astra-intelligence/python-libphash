from __future__ import annotations

from typing import Any, Callable, NoReturn, final

from ._algorithms import DigestKind
from ._native import ffi, lib
from ._errors import PH_SUCCESS, make_error
from .exceptions import DigestKindError, InvalidArgumentError

PH_DIGEST_MAX_BYTES: int = int(lib.PH_DIGEST_MAX_BYTES)
_UINT64_MAX = (1 << 64) - 1

# Comparison -> the kinds it accepts (UNSPECIFIED is accepted by all, as in C).
_METRIC_KINDS = {
    "hamming_distance": (DigestKind.BITS,),
    "l2_distance": (DigestKind.VECTOR, DigestKind.VECTOR16),
    "histogram_intersection": (DigestKind.HISTOGRAM,),
    "radial_similarity": (DigestKind.COEFFICIENTS,),
}


@final
class Digest:
    """A multi-byte hash: the bytes and the kind that says how they may be compared.

    BMH and mHash give bit vectors, Radial quantized coefficients, ColorHash a histogram,
    ColorMoments a vector of signed 16-bit features. Each comparison method accepts only
    the kinds it is meaningful for and raises :class:`DigestKindError` for the others;
    :meth:`similarity` picks the comparison that belongs to the kind.

    Digests are immutable, hashable, comparable for equality and picklable. ``hex()`` and
    ``from_hex()`` give a text form that keeps the kind.
    """

    __slots__ = ("_data", "_kind")
    _data: bytes
    _kind: DigestKind

    def __init__(self, data: bytes, kind: DigestKind | int) -> None:
        data = bytes(data)
        if not 0 < len(data) <= PH_DIGEST_MAX_BYTES:
            raise InvalidArgumentError(
                f"a digest holds 1 to {PH_DIGEST_MAX_BYTES} bytes, got {len(data)}"
            )
        try:
            kind = DigestKind(kind)
        except ValueError:
            raise InvalidArgumentError(f"unknown digest kind {kind!r}") from None
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_kind", kind)

    @classmethod
    def from_uint64(cls, value: int) -> Digest:
        """A 64-bit hash as an 8-byte ``BITS`` digest, most significant byte first."""
        return cls(_check_uint64(value).to_bytes(8, "big"), DigestKind.BITS)

    @classmethod
    def from_hex(cls, text: str) -> Digest:
        """Parse the text form written by :meth:`hex` (``"<kind>:<hex>"``)."""
        out = ffi.new("ph_digest_t *")
        code = lib.ph_digest_from_hex(text.encode("ascii", "replace"), out)
        if code != PH_SUCCESS:
            raise make_error(code, context=f"parsing digest {text[:40]!r}")
        return digest_from_c(out)

    @property
    def data(self) -> bytes:
        return self._data

    @property
    def kind(self) -> DigestKind:
        return self._kind

    def __len__(self) -> int:
        return len(self._data)

    def __bytes__(self) -> bytes:
        return self._data

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Digest):
            return NotImplemented
        return self._kind == other._kind and self._data == other._data

    def __hash__(self) -> int:
        return hash((self._kind, self._data))

    def __repr__(self) -> str:
        return f"Digest.from_hex({self.hex()!r})"

    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError("Digest is immutable")

    def __reduce__(self) -> tuple[Any, ...]:
        return (Digest, (self._data, int(self._kind)))

    def hex(self) -> str:
        """Text form: the kind, a colon, the bytes in lowercase hex (``"bits:3fa0..."``)."""
        size = int(lib.PH_DIGEST_HEX_BUFFER_SIZE)
        out = ffi.new("char[]", size)
        code = lib.ph_digest_to_hex(digest_to_c(self), out, size)
        if code != PH_SUCCESS:
            raise make_error(code, context="encoding digest")
        return str(ffi.string(out).decode("ascii"))

    # --- Comparisons -----------------------------------------------------------------

    def _pair(self, other: object, metric: str) -> tuple[Any, Any]:
        if not isinstance(other, Digest):
            raise TypeError(f"expected a Digest, got {type(other).__name__}")
        allowed = _METRIC_KINDS[metric]
        for d in (self, other):
            if d._kind != DigestKind.UNSPECIFIED and d._kind not in allowed:
                _wrong_kind(metric, d._kind)
        if len(self._data) != len(other._data):
            raise InvalidArgumentError(
                f"{metric}: digests of different sizes ({len(self._data)} and {len(other._data)} bytes)"
            )
        return digest_to_c(self), digest_to_c(other)

    def hamming_distance(self, other: Digest) -> int:
        """Number of differing bits between two ``BITS`` digests (BMH, mHash)."""
        a, b = self._pair(other, "hamming_distance")
        return int(
            _sentinel(int(lib.ph_hamming_distance_digest(a, b)), "hamming_distance")
        )

    def l2_distance(self, other: Digest) -> float:
        """Euclidean distance between two feature vectors (ColorMoments)."""
        a, b = self._pair(other, "l2_distance")
        return float(_sentinel(float(lib.ph_l2_distance(a, b)), "l2_distance"))

    def histogram_intersection(self, other: Digest) -> float:
        """Share of color two ``HISTOGRAM`` digests (ColorHash) have in common, 0.0 to 1.0."""
        a, b = self._pair(other, "histogram_intersection")
        return _out_double(
            lib.ph_histogram_intersection, a, b, "histogram_intersection"
        )

    def radial_similarity(self, other: Digest) -> float:
        """Peak cross-correlation of two Radial digests, -1.0 to 1.0.

        Raises :class:`NoStructureError` when either digest is flat (all bytes equal), as
        the Radial hash of an image without angular structure is: any score would be
        invented. :data:`RADIAL_PCC_THRESHOLD` is the source's cut for "same image".
        """
        a, b = self._pair(other, "radial_similarity")
        return _out_double(lib.ph_radial_similarity, a, b, "radial_similarity")

    def similarity(self, other: Digest) -> float:
        """The similarity measure that belongs to the digests' kind.

        ``BITS``: share of equal bits, 0.0 to 1.0. ``HISTOGRAM``: histogram intersection,
        0.0 to 1.0. ``COEFFICIENTS``: radial peak correlation, -1.0 to 1.0. ``VECTOR16``
        (ColorMoments) has no normalized similarity: use :meth:`l2_distance`.
        """
        kind = self._kind if self._kind != DigestKind.UNSPECIFIED else other._kind
        if kind == DigestKind.BITS:
            a, b = self._pair(other, "hamming_distance")
            return float(_sentinel(float(lib.ph_similarity_digest(a, b)), "similarity"))
        if kind == DigestKind.HISTOGRAM:
            return self.histogram_intersection(other)
        if kind == DigestKind.COEFFICIENTS:
            return self.radial_similarity(other)
        if kind == DigestKind.UNSPECIFIED:
            raise DigestKindError(
                "similarity: neither digest states its kind, so the measure is unknown; "
                "call hamming_distance(), l2_distance(), histogram_intersection() or "
                "radial_similarity() explicitly"
            )
        raise DigestKindError(
            f"similarity: {kind.name} digests have no normalized similarity; use l2_distance()"
        )


def digest_from_c(c_digest: Any) -> Digest:
    """A Digest from a ``ph_digest_t *``."""
    return Digest(bytes(ffi.buffer(c_digest.data, c_digest.size)), int(c_digest.kind))


def digest_to_c(digest: Digest) -> Any:
    """A new ``ph_digest_t *`` holding ``digest``."""
    data = digest.data
    c_digest = ffi.new("ph_digest_t *")
    c_digest.size = len(data)
    c_digest.kind = int(digest.kind)
    ffi.memmove(c_digest.data, data, len(data))
    return c_digest


def _wrong_kind(metric: str, kind: DigestKind) -> NoReturn:
    right = {
        DigestKind.BITS: "hamming_distance() or similarity()",
        DigestKind.VECTOR: "l2_distance()",
        DigestKind.VECTOR16: "l2_distance()",
        DigestKind.HISTOGRAM: "histogram_intersection() or similarity()",
        DigestKind.COEFFICIENTS: "radial_similarity() or similarity()",
    }[kind]
    raise DigestKindError(
        f"{metric} does not apply to {kind.name} digests; use {right}"
    )


def _sentinel(value: Any, metric: str) -> Any:
    # The checks in _pair leave the C library nothing to reject; -1 here would be a
    # contract the binding missed.
    if value < 0:
        raise InvalidArgumentError(f"{metric}: the C library rejected the digests")
    return value


def _out_double(
    func: Callable[[Any, Any, Any], int], a: Any, b: Any, metric: str
) -> float:
    out = ffi.new("double *")
    code = func(a, b, out)
    if code != PH_SUCCESS:
        raise make_error(code, context=metric)
    return float(out[0])


def _check_uint64(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"a 64-bit hash is an int, got {type(value).__name__}")
    if not 0 <= value <= _UINT64_MAX:
        raise InvalidArgumentError(f"a 64-bit hash is in [0, 2**64), got {value}")
    return value


def hamming_distance(a: int, b: int) -> int:
    """Number of differing bits between two 64-bit hashes, 0 to 64."""
    return int(lib.ph_hamming_distance(_check_uint64(a), _check_uint64(b)))


def similarity(a: int, b: int) -> float:
    """Share of equal bits between two 64-bit hashes: 1.0 identical, near 0.5 unrelated."""
    return float(lib.ph_similarity(_check_uint64(a), _check_uint64(b)))


def hash_to_hex(value: int) -> str:
    """A 64-bit hash as 16 lowercase hex digits, most significant first."""
    out = ffi.new("char[]", 17)
    code = lib.ph_hash_to_hex(_check_uint64(value), out, 17)
    if code != PH_SUCCESS:
        raise make_error(code, context="encoding hash")
    return str(ffi.string(out).decode("ascii"))


def hash_from_hex(text: str) -> int:
    """Parse the 16 hex digits written by :func:`hash_to_hex`."""
    out = ffi.new("uint64_t *")
    code = lib.ph_hash_from_hex(text.encode("ascii", "replace"), out)
    if code != PH_SUCCESS:
        raise make_error(code, context=f"parsing hash {text[:40]!r}")
    return int(out[0])


RADIAL_PCC_THRESHOLD: float = float(lib.PH_RADIAL_PCC_THRESHOLD)
