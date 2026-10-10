"""Perceptual image hashing: Python binding for the libphash C library.

>>> import libphash as ph
>>> h = ph.hash("cat.jpg")                      # 64-bit pHash, an int
>>> ph.hamming_distance(h, ph.hash("cat_small.jpg"))
>>> d = ph.hash("cat.jpg", "radial")            # a Digest
>>> d.similarity(ph.hash("cat_rotated.jpg", "radial"))

:class:`ImageContext` keeps an image and its configuration for several hashes and
reuses its buffers across images; :func:`hash_files` hashes many files on a thread pool.
"""

from __future__ import annotations

from typing import Any, Literal, overload

from ._algorithms import Algorithm, AlgorithmLike, DigestKind, to_algorithm
from ._batch import BatchResult, ProgressCallback, hash_buffers, hash_files
from ._config import (
    AlphaMode,
    Config,
    DecodeScale,
    WHashMode,
    apply_config,
    new_context,
)
from ._context import (
    DigestAlgorithm,
    DigestName,
    ImageContext,
    Uint64Algorithm,
    Uint64Name,
)
from ._digest import (
    PH_DIGEST_MAX_BYTES,
    RADIAL_PCC_THRESHOLD,
    Digest,
    hamming_distance,
    hash_from_hex,
    hash_to_hex,
    similarity,
)
from ._errors import PH_SUCCESS, make_error
from ._native import ffi, lib
from ._sources import (
    ChannelOrder,
    PILImage,
    PixelArray,
    Source,
    StrPath,
    SupportsArrayInterface,
    SupportsRead,
)
from ._version import __version__ as __version__
from .exceptions import (
    AllocationError,
    BatchCancelledError,
    CorruptDataError,
    DecodeError,
    DecoderUnavailableError,
    DigestKindError,
    EmptyImageError,
    ImageIOError,
    ImageTooLargeError,
    InvalidArgumentError,
    NoStructureError,
    PhashError,
    RequiresColorError,
    UnsupportedFormatError,
)

__all__ = [
    "PH_DIGEST_MAX_BYTES",
    "RADIAL_PCC_THRESHOLD",
    "Algorithm",
    "AlgorithmLike",
    "AllocationError",
    "AlphaMode",
    "BatchCancelledError",
    "BatchResult",
    "ChannelOrder",
    "Config",
    "CorruptDataError",
    "DecodeError",
    "DecodeScale",
    "DecoderUnavailableError",
    "Digest",
    "DigestAlgorithm",
    "DigestKind",
    "DigestKindError",
    "DigestName",
    "EmptyImageError",
    "ImageContext",
    "ImageIOError",
    "ImageTooLargeError",
    "InvalidArgumentError",
    "NoStructureError",
    "PILImage",
    "PhashError",
    "PixelArray",
    "ProgressCallback",
    "RequiresColorError",
    "Source",
    "StrPath",
    "SupportsArrayInterface",
    "SupportsRead",
    "Uint64Algorithm",
    "Uint64Name",
    "UnsupportedFormatError",
    "WHashMode",
    "build_info",
    "can_decode",
    "digest_info",
    "hamming_distance",
    "hash",
    "hash_buffers",
    "hash_files",
    "hash_from_hex",
    "hash_to_hex",
    "libphash_version",
    "similarity",
]


@overload
def hash(
    source: Source,
    algorithm: Uint64Algorithm | Uint64Name = ...,
    *,
    config: Config | None = ...,
) -> int: ...
@overload
def hash(
    source: Source,
    algorithm: DigestAlgorithm | DigestName,
    *,
    config: Config | None = ...,
) -> Digest: ...
@overload
def hash(
    source: Source, algorithm: AlgorithmLike, *, config: Config | None = ...
) -> int | Digest: ...


def hash(
    source: Source,
    algorithm: AlgorithmLike = Algorithm.PHASH,
    *,
    config: Config | None = None,
) -> int | Digest:
    """Hash one image.

    ``source`` is a path, encoded bytes, a binary file object, an array of pixels or a
    Pillow image. Returns an ``int`` for aHash, dHash, pHash and wHash, a
    :class:`Digest` for the others.
    """
    with ImageContext(config) as ctx:
        ctx.load(source)
        return ctx.hash(algorithm)


def libphash_version() -> str:
    """Return the version of the bundled libphash (``"2.0.1"``).

    It is the first three numbers of ``__version__``.
    """
    return str(ffi.string(lib.ph_version()).decode())


def build_info() -> str:
    """Return how the bundled libphash was built.

    The string lists the version, decoders, threads and SIMD:
    ``"version=2.0.1 jpeg=libjpeg-turbo png=libpng ..."``.
    """
    return str(ffi.string(lib.ph_get_build_info()).decode())


def can_decode(fmt: Literal["jpeg", "png", "webp"]) -> bool:
    """Return whether this build has a native decoder for the format.

    JPEG and PNG decode without one too (through stb_image); WebP does not.
    """
    checks: dict[str, Any] = {
        "jpeg": lib.ph_can_use_jpeg,
        "png": lib.ph_can_use_png,
        "webp": lib.ph_can_use_webp,
    }
    if fmt not in checks:
        raise ValueError(f"fmt must be 'jpeg', 'png' or 'webp', got {fmt!r}")
    return bool(checks[fmt]())


def digest_info(
    algorithm: AlgorithmLike, config: Config | None = None
) -> tuple[int, DigestKind]:
    """Return the size in bytes and the kind of the hashes ``algorithm`` produces.

    No image is needed: the answer depends only on ``config``, which makes it fit for
    sizing a database column, say. A 64-bit hash is 8 ``BITS`` bytes.
    """
    algo = to_algorithm(algorithm)
    ctx = new_context()
    try:
        apply_config(config if config is not None else Config(), ctx)
        size = ffi.new("size_t *")
        kind = ffi.new("ph_digest_kind_t *")
        code = lib.ph_digest_info(ctx, int(algo), size, kind)
        if code != PH_SUCCESS:
            raise make_error(code, context=f"digest_info({algo})")
        return int(size[0]), DigestKind(int(kind[0]))
    finally:
        lib.ph_free(ctx)
