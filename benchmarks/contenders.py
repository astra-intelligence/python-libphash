"""The hashes the benchmarks compare, libphash's and others', behind one interface.

Each contender hashes an image file the way its library is meant to be used in a loop:
libphash reuses one :class:`libphash.ImageContext` and decodes with its own decoders,
OpenCV reuses one hasher object and decodes with ``cv2.imread``, imagehash and pdqhash
take an image Pillow decoded. Each compares two hashes by its own library's measure:
the bits that differ for a bit hash, or the library's score.

The libraries other than libphash are optional (the ``benchmark`` extra); a library
that is not installed contributes no contender.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

import libphash as ph

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


H = TypeVar("H")


class Hasher(Protocol):
    """A contender seen from the benchmarks, whatever type its hashes are."""

    @property
    def library(self) -> str:
        """The library's name."""
        ...

    @property
    def algorithm(self) -> str:
        """The algorithm's family, the same across libraries."""
        ...

    @property
    def metric(self) -> str:
        """What a comparison gives."""
        ...

    @property
    def bits(self) -> int | None:
        """The hash's length in bits, for a hash compared bit by bit."""
        ...

    @property
    def lower_is_closer(self) -> bool:
        """Whether a lower value means more alike."""
        ...

    @property
    def key(self) -> str:
        """The contender's name in results."""
        ...

    @property
    def compute(self) -> Callable[[str], object]:
        """Hash an image file."""
        ...

    def against(self, reference: str) -> Callable[[str], float | None]:
        """Return a function comparing an image file with ``reference``."""
        ...

    def pairs(self, paths: Sequence[str]) -> list[float | None]:
        """Compare every pair of ``paths``."""
        ...


@dataclass(frozen=True)
class Contender(Generic[H]):
    """One library's hash: how it hashes a file and how it compares two hashes."""

    library: str
    #: The algorithm's family, the same name across libraries ("pHash", "Radial").
    algorithm: str
    #: What a comparison gives: "bits that differ" or the library's own score.
    metric: str
    #: The hash's length in bits, for a hash compared bit by bit.
    bits: int | None
    lower_is_closer: bool
    compute: Callable[[str], H]
    #: None where the library refuses to compare the two hashes.
    compare: Callable[[H, H], float | None]

    @property
    def key(self) -> str:
        """Return the contender's name in results: ``library/algorithm``."""
        return f"{self.library}/{self.algorithm}"

    def against(self, reference: str) -> Callable[[str], float | None]:
        """Return a function that compares an image file's hash with ``reference``'s."""
        ref = self.compute(reference)

        def compare(path: str) -> float | None:
            return self.compare(ref, self.compute(path))

        return compare

    def pairs(self, paths: Sequence[str]) -> list[float | None]:
        """Compare every pair ``i < j`` of ``paths``, in row order."""
        hashes = [self.compute(p) for p in paths]
        return [
            self.compare(hashes[i], hashes[j])
            for i in range(len(hashes))
            for j in range(i + 1, len(hashes))
        ]


BITS = "bits that differ"


def contenders() -> list[Hasher]:
    """Return every contender whose library is installed, libphash's first."""
    out = libphash_contenders()
    if importlib.util.find_spec("imagehash") is not None:
        out += imagehash_contenders()
    if importlib.util.find_spec("cv2") is not None:
        out += opencv_contenders()
    if importlib.util.find_spec("pdqhash") is not None:
        out += pdqhash_contenders()
    return out


def by_key(keys: Sequence[str]) -> list[Hasher]:
    """Return the contenders named by ``keys``, in that order."""
    known = {c.key: c for c in contenders()}
    missing = [k for k in keys if k not in known]
    if missing:
        raise ValueError(f"unknown or unavailable contenders: {', '.join(missing)}")
    return [known[k] for k in keys]


# --- libphash ------------------------------------------------------------------------


def libphash_contenders() -> list[Hasher]:
    """Return libphash's nine hashes, with the library's default configuration."""
    ctx = ph.ImageContext()

    def uint64(name: ph.Uint64Name) -> Callable[[str], int]:
        def compute(path: str) -> int:
            ctx.load_file(path)
            return ctx.hash(name)

        return compute

    def digest(name: ph.DigestName) -> Callable[[str], ph.Digest]:
        def compute(path: str) -> ph.Digest:
            ctx.load_file(path)
            return ctx.hash(name)

        return compute

    def hamming(a: int, b: int) -> float:
        return float(ph.hamming_distance(a, b))

    def digest_hamming(a: ph.Digest, b: ph.Digest) -> float:
        return float(a.hamming_distance(b))

    def radial(a: ph.Digest, b: ph.Digest) -> float | None:
        try:
            return a.radial_similarity(b)
        except ph.NoStructureError:
            return None

    def digest_bits(name: ph.DigestName) -> int:
        return ph.digest_info(name)[0] * 8

    lib = "libphash"
    families: list[tuple[str, ph.Uint64Name]] = [
        ("aHash", "ahash"),
        ("dHash", "dhash"),
        ("pHash", "phash"),
        ("wHash", "whash"),
    ]
    out: list[Hasher] = [
        Contender[int](lib, family, BITS, 64, True, uint64(name), hamming)
        for family, name in families
    ]
    out += [
        Contender[ph.Digest](
            lib, "BMH", BITS, digest_bits("bmh"), True, digest("bmh"), digest_hamming
        ),
        Contender[ph.Digest](
            lib,
            "mHash",
            BITS,
            digest_bits("mhash"),
            True,
            digest("mhash"),
            digest_hamming,
        ),
        Contender[ph.Digest](
            lib, "Radial", "peak correlation", None, False, digest("radial"), radial
        ),
        Contender[ph.Digest](
            lib,
            "ColorHash",
            "histogram intersection",
            None,
            False,
            digest("color_hash"),
            ph.Digest.histogram_intersection,
        ),
        Contender[ph.Digest](
            lib,
            "ColorMoments",
            "L2 distance",
            None,
            True,
            digest("color_moments"),
            ph.Digest.l2_distance,
        ),
    ]
    return out


# --- imagehash -----------------------------------------------------------------------


def imagehash_contenders() -> list[Hasher]:
    """Return ImageHash's hashes of the same families, with its default sizes."""
    import imagehash  # noqa: PLC0415 -- optional
    from PIL import Image  # noqa: PLC0415 -- optional

    def from_file(
        fn: Callable[[Image.Image], imagehash.ImageHash],
    ) -> Callable[[str], imagehash.ImageHash]:
        def compute(path: str) -> imagehash.ImageHash:
            with Image.open(path) as image:
                return fn(image)

        return compute

    def hamming(a: imagehash.ImageHash, b: imagehash.ImageHash) -> float:
        return float(a - b)

    lib = "imagehash"
    hashes: list[tuple[str, int, Callable[[Image.Image], imagehash.ImageHash]]] = [
        # imagehash annotates average_hash() and whash() with parameter types
        # (numpy.mean as a default, its wavelet mode) basedpyright cannot resolve.
        ("aHash", 64, lambda im: imagehash.average_hash(im)),  # pyright: ignore[reportUnknownMemberType]
        ("dHash", 64, lambda im: imagehash.dhash(im)),
        ("pHash", 64, lambda im: imagehash.phash(im)),
        ("wHash", 64, lambda im: imagehash.whash(im)),  # pyright: ignore[reportUnknownMemberType]
        # 14 bins of 3 bits each: imagehash.colorhash()'s default binbits.
        ("ColorHash", 42, lambda im: imagehash.colorhash(im)),
    ]
    return [
        Contender[imagehash.ImageHash](
            lib, family, BITS, bits, True, from_file(fn), hamming
        )
        for family, bits, fn in hashes
    ]


# --- OpenCV --------------------------------------------------------------------------


def opencv_contenders() -> list[Hasher]:
    """Return the hashes of OpenCV's img_hash module (opencv-contrib)."""
    import cv2  # noqa: PLC0415 -- optional
    from cv2.typing import MatLike  # noqa: PLC0415 -- optional

    def with_hasher(
        hasher: cv2.img_hash.ImgHashBase,
    ) -> tuple[Callable[[str], MatLike], Callable[[MatLike, MatLike], float]]:
        def compute(path: str) -> MatLike:
            image = cv2.imread(path)
            if image is None:
                raise OSError(f"OpenCV cannot read {path}")
            return hasher.compute(image)

        def compare(a: MatLike, b: MatLike) -> float:
            return float(hasher.compare(a, b))

        return compute, compare

    lib = "OpenCV"
    hashers: list[tuple[str, str, int | None, bool, cv2.img_hash.ImgHashBase]] = [
        ("aHash", BITS, 64, True, cv2.img_hash.AverageHash.create()),
        ("pHash", BITS, 64, True, cv2.img_hash.PHash.create()),
        (
            "BMH",
            BITS,
            256,
            True,
            cv2.img_hash.BlockMeanHash.create(cv2.img_hash.BLOCK_MEAN_HASH_MODE_0),
        ),
        ("mHash", BITS, 576, True, cv2.img_hash.MarrHildrethHash.create()),
        (
            "Radial",
            "peak correlation",
            None,
            False,
            cv2.img_hash.RadialVarianceHash.create(),
        ),
        (
            "ColorMoments",
            "L2 distance",
            None,
            True,
            cv2.img_hash.ColorMomentHash.create(),
        ),
    ]
    out: list[Hasher] = []
    for family, metric, bits, lower, hasher in hashers:
        compute, compare = with_hasher(hasher)
        out.append(
            Contender[MatLike](lib, family, metric, bits, lower, compute, compare)
        )
    return out


# --- pdqhash -------------------------------------------------------------------------


def pdqhash_contenders() -> list[Hasher]:
    """Return Meta's PDQ hash (256 bits) through the pdqhash package."""
    import numpy as np  # noqa: PLC0415 -- optional
    import pdqhash  # noqa: PLC0415 -- optional
    from numpy.typing import NDArray  # noqa: PLC0415 -- optional
    from PIL import Image  # noqa: PLC0415 -- optional

    def compute(path: str) -> NDArray[np.int64]:
        with Image.open(path) as image:
            pixels = np.asarray(image.convert("RGB"))
        return pdqhash.compute(pixels)[0]

    def hamming(a: NDArray[np.int64], b: NDArray[np.int64]) -> float:
        return float(np.count_nonzero(a != b))

    return [
        Contender[NDArray[np.int64]](
            "pdqhash", "PDQ", BITS, 256, True, compute, hamming
        )
    ]
