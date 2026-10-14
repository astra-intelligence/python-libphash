from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Literal, NoReturn, cast, overload

from ._algorithms import Algorithm, AlgorithmLike, to_algorithm, uint64_flags
from ._config import Config, apply_config, new_context
from ._digest import Digest, digest_from_c
from ._errors import PH_SUCCESS, make_error
from ._native import ffi, lib
from ._sources import (
    READ_FILES_IN_PYTHON,
    ChannelOrder,
    PILImage,
    PixelArray,
    Pixels,
    Source,
    StrPath,
    SupportsArrayInterface,
    SupportsRead,
    encode_path,
    is_pil_image,
    pixels_from_array,
    pixels_from_pil,
    read_file,
)

if TYPE_CHECKING:
    from typing_extensions import Self

    from ._native import ph_context_t_ptr

#: Names of the algorithms that produce a 64-bit ``int``.
Uint64Name = Literal["ahash", "dhash", "phash", "whash"]
#: Names of the algorithms that produce a :class:`Digest`.
DigestName = Literal["bmh", "mhash", "radial", "color_hash", "color_moments"]
#: The algorithms that produce a 64-bit ``int``.
Uint64Algorithm = Literal[
    Algorithm.AHASH, Algorithm.DHASH, Algorithm.PHASH, Algorithm.WHASH
]
#: The algorithms that produce a :class:`Digest`.
DigestAlgorithm = Literal[
    Algorithm.BMH,
    Algorithm.MHASH,
    Algorithm.RADIAL,
    Algorithm.COLOR_HASH,
    Algorithm.COLOR_MOMENTS,
]

_UINT64_COMPUTE = {
    Algorithm.AHASH: lib.ph_compute_ahash,
    Algorithm.DHASH: lib.ph_compute_dhash,
    Algorithm.PHASH: lib.ph_compute_phash,
    Algorithm.WHASH: lib.ph_compute_whash,
}


class ImageContext:
    """One image and the configuration to hash it with: a libphash ``ph_context_t``.

    Load an image with one of the ``load_*`` methods, then compute any number of hashes
    from it; loading the next image reuses the context's buffers, which makes a context
    kept across a loop faster than :func:`hash` per image.

    A context is safe to share between threads: the calls into C are serialized on a
    lock of the context. Threads that work in parallel each need their own context (or a
    batch, :func:`hash_files`). Close it with :meth:`close` or a ``with`` block; one
    left to the garbage collector is freed too.
    """

    __slots__ = ("__weakref__", "_config", "_lock", "_ptr")

    def __init__(self, config: Config | None = None) -> None:
        self._lock = threading.Lock()
        self._config = _config_or_default(config)
        ptr = new_context()
        self._ptr: ph_context_t_ptr | None = ffi.gc(ptr, lib.ph_free)
        apply_config(self._config, self._ptr)

    # --- Lifecycle -------------------------------------------------------------------

    def close(self) -> None:
        """Free the C context. Idempotent; any later use raises ValueError."""
        with self._lock:
            if self._ptr is not None:
                ffi.release(self._ptr)
                self._ptr = None

    @property
    def closed(self) -> bool:
        return self._ptr is None

    def __enter__(self) -> Self:
        self._live()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        if self._ptr is None:
            return "<ImageContext closed>"
        if not self.is_loaded:
            return "<ImageContext empty>"
        return f"<ImageContext {self.width}x{self.height}x{self.channels}>"

    def __reduce__(self) -> NoReturn:
        raise TypeError("ImageContext cannot be pickled; pickle its Config instead")

    def __copy__(self) -> NoReturn:
        raise TypeError(
            "ImageContext cannot be copied; create one from its Config instead"
        )

    def __deepcopy__(self, memo: object) -> NoReturn:
        self.__copy__()

    def _live(self) -> ph_context_t_ptr:
        ptr = self._ptr
        if ptr is None:
            raise ValueError("operation on a closed ImageContext")
        return ptr

    # --- State -----------------------------------------------------------------------

    @property
    def config(self) -> Config:
        return self._config

    @property
    def is_loaded(self) -> bool:
        with self._lock:
            return bool(lib.ph_is_loaded(self._live()))

    def _dimensions(self) -> tuple[int, int, int]:
        out = ffi.new("int[]", 3)
        with self._lock:
            lib.ph_context_get_dimensions(self._live(), out, out + 1, out + 2)
        return int(out[0]), int(out[1]), int(out[2])

    @property
    def width(self) -> int:
        """Width of the loaded image (after orientation and decode scale), 0 if none."""
        return self._dimensions()[0]

    @property
    def height(self) -> int:
        return self._dimensions()[1]

    @property
    def channels(self) -> int:
        """3 for color, 1 for grayscale.

        An alpha channel is resolved at load and not kept.
        """
        return self._dimensions()[2]

    # --- Loading ---------------------------------------------------------------------

    def load(self, source: Source) -> None:
        """Load whatever ``source`` is.

        ``source`` is a path, encoded bytes, a binary file object, an array of pixels or
        a Pillow image. Bytes are always the encoded file, never a path.
        """
        if isinstance(source, (str, os.PathLike)):
            self.load_file(source)
        elif isinstance(source, (bytes, bytearray)):
            self.load_bytes(source)
        elif isinstance(source, memoryview):
            if source.ndim in (2, 3):
                self.load_pixels(source)
            else:
                self.load_bytes(source)
        elif is_pil_image(source):
            self.load_pil(cast("PILImage", source))
        elif isinstance(source, SupportsArrayInterface):
            self.load_pixels(source)
        elif callable(getattr(source, "read", None)):
            self.load_fileobj(source)
        else:
            raise TypeError(
                "expected a path, bytes, a binary file object, an array of pixels or a "
                f"Pillow image, got {type(source).__name__}"
            )

    def load_file(self, path: StrPath) -> None:
        """Load an image file. On failure the context holds no image."""
        encoded = encode_path(path)
        if READ_FILES_IN_PYTHON:
            self.load_bytes(read_file(path))
            return
        with self._lock:
            ptr = self._live()
            code = lib.ph_load_from_file(ptr, encoded)
            if code != PH_SUCCESS:
                raise make_error(code, detail=self._last_message(ptr), path=path)

    def load_bytes(self, data: bytes | bytearray | memoryview) -> None:
        """Load an encoded image (JPEG, PNG, WebP, ...) from memory, without a copy.

        The buffer must not change while the call runs. On failure the context holds no
        image.
        """
        try:
            buf = ffi.from_buffer("const uint8_t[]", data)
        except TypeError:
            raise TypeError(
                f"expected bytes-like encoded image data, got {type(data).__name__}"
            ) from None
        with self._lock:
            ptr = self._live()
            code = lib.ph_load_from_memory(ptr, buf, len(buf))
            if code != PH_SUCCESS:
                raise make_error(code, detail=self._last_message(ptr))

    def load_fileobj(self, fileobj: SupportsRead) -> None:
        """Read a binary file object to its end and load the bytes.

        The object is an open file, an ``io.BytesIO``, a response body or anything else
        with a ``read()`` that returns bytes.
        """
        self.load_bytes(_read_all(fileobj))

    def load_pixels(
        self, pixels: PixelArray, channel_order: ChannelOrder = "rgb"
    ) -> None:
        """Load decoded pixels.

        ``pixels`` is an 8-bit array of shape (h, w), (h, w, 1), (h, w, 3) or (h, w, 4),
        e.g. a numpy ``uint8`` array. ``channel_order="bgr"`` reads OpenCV's order. The
        pixels are copied into the context, and no EXIF orientation applies. On failure
        the previously loaded image stays loaded.
        """
        self._load_pixels(pixels_from_array(pixels, channel_order))

    def load_pil(self, image: PILImage) -> None:
        """Load a Pillow image.

        :func:`pixels_from_pil` describes how each mode is read.
        """
        self._load_pixels(pixels_from_pil(image))

    def _load_pixels(self, px: Pixels) -> None:
        with self._lock:
            ptr = self._live()
            code = lib.ph_load_from_pixels(
                ptr, px.pointer, px.width, px.height, px.channels, px.stride
            )
            if code != PH_SUCCESS:
                # libphash writes no message for a pixel load.
                raise make_error(code)
        del px

    @staticmethod
    def _last_message(ptr: ph_context_t_ptr) -> str:
        # Never NULL: an empty string when the last load set no message.
        msg = lib.ph_get_last_error_message(ptr)
        return str(ffi.string(msg).decode("utf-8", "replace"))

    # --- Hashing ---------------------------------------------------------------------

    @overload
    def hash(self, algorithm: Uint64Algorithm | Uint64Name = ...) -> int: ...
    @overload
    def hash(self, algorithm: DigestAlgorithm | DigestName) -> Digest: ...
    @overload
    def hash(self, algorithm: AlgorithmLike) -> int | Digest: ...

    def hash(self, algorithm: AlgorithmLike = Algorithm.PHASH) -> int | Digest:
        """Compute one hash of the loaded image.

        Returns an ``int`` for aHash, dHash, pHash and wHash, a :class:`Digest` for the
        others.
        """
        algo = to_algorithm(algorithm)
        with self._lock:
            return _compute(self._live(), algo)

    def hashes(self, *algorithms: AlgorithmLike) -> dict[Algorithm, int | Digest]:
        """Compute several hashes at once, all of the same loaded image.

        The 64-bit ones share their work on the full image (one ``ph_compute_multi``
        call); digests are computed one by one. No other thread loads an image in
        between.
        """
        algos = [to_algorithm(a) for a in algorithms] or [Algorithm.PHASH]
        uint64 = sorted({a for a in algos if a in _UINT64_COMPUTE})
        result: dict[Algorithm, int | Digest] = {}
        with self._lock:
            ptr = self._live()
            if uint64:
                out = ffi.new("uint64_t[]", len(uint64))
                code = lib.ph_compute_multi(ptr, uint64_flags(uint64), out)
                if code != PH_SUCCESS:
                    raise make_error(
                        code, context="computing " + ", ".join(map(str, uint64))
                    )
                # Slots follow ascending flag bits, which is ascending Algorithm value.
                result.update(zip(uint64, (int(v) for v in out), strict=True))
            for algo in algos:
                if algo not in result:
                    result[algo] = _compute(ptr, algo)
        return {a: result[a] for a in algos}

    def ahash(self) -> int:
        """Average hash: each cell of an 8x8 grayscale reduction against their mean."""
        return self.hash(Algorithm.AHASH)

    def dhash(self) -> int:
        """Difference hash: horizontal neighbor comparisons in a 9x8 reduction."""
        return self.hash(Algorithm.DHASH)

    def phash(self) -> int:
        """Perceptual hash: the low-frequency DCT block of a reduction.

        Each coefficient is compared with the block's median.
        """
        return self.hash(Algorithm.PHASH)

    def whash(self) -> int:
        """Wavelet hash: the low-frequency Haar band of a reduction.

        Each coefficient is compared with the band's median.
        """
        return self.hash(Algorithm.WHASH)

    def bmh(self) -> Digest:
        """Block mean hash: one bit per block of a ``bmh_block_size`` grid (BITS)."""
        return self.hash(Algorithm.BMH)

    def mhash(self) -> Digest:
        """Marr-Hildreth hash: a Laplacian-of-Gaussian response (BITS).

        Nine bits per window, 576 bits in all.
        """
        return self.hash(Algorithm.MHASH)

    def radial(self) -> Digest:
        """Radial variance hash: rotation-tolerant projections (COEFFICIENTS)."""
        return self.hash(Algorithm.RADIAL)

    def color_hash(self) -> Digest:
        """Color histogram, compared by histogram intersection (HISTOGRAM)."""
        return self.hash(Algorithm.COLOR_HASH)

    def color_moments(self) -> Digest:
        """Color moments per channel (VECTOR16).

        The mean, the standard deviation and the cube root of the third moment.
        """
        return self.hash(Algorithm.COLOR_MOMENTS)


def _compute(ptr: ph_context_t_ptr, algo: Algorithm) -> int | Digest:
    """Compute one hash; the caller holds the context's lock."""
    compute = _UINT64_COMPUTE.get(algo)
    if compute is not None:
        out64 = ffi.new("uint64_t *")
        code = compute(ptr, out64)
        if code != PH_SUCCESS:
            raise make_error(code, context=f"computing {algo}")
        return int(out64[0])
    digest = ffi.new("ph_digest_t *")
    code = lib.ph_compute_digest(ptr, int(algo), digest)
    if code != PH_SUCCESS:
        raise make_error(code, context=f"computing {algo}")
    return digest_from_c(digest)


def _config_or_default(config: object) -> Config:
    if config is None:
        return Config()
    if not isinstance(config, Config):
        raise TypeError(f"expected a Config, got {type(config).__name__}")
    return config


def _read_all(fileobj: SupportsRead) -> bytes | bytearray | memoryview:
    data = cast("object", fileobj.read())  # checked: an untyped read() may return str
    if isinstance(data, (bytes, bytearray)):
        return data
    if isinstance(data, memoryview):
        return cast("memoryview", data)
    raise TypeError(
        f"{type(fileobj).__name__}.read() returned {type(data).__name__}, not bytes"
    )
