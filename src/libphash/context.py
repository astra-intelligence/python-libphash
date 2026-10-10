from __future__ import annotations
from pathlib import Path
from typing import Any, final, Callable
from ._native import ffi, lib
from .exceptions import check_error
from .ph_types import Digest


@final
class ImageContext:
    _ptr: Any
    _ctx_ptr_ptr: Any

    def __init__(
        self,
        path: str | Path | None = None,
        bytes_data: bytes | None = None,
        load_grayscale: bool = False,
    ) -> None:
        self._ctx_ptr_ptr = ffi.new("ph_context_t **")
        check_error(lib.ph_create(self._ctx_ptr_ptr))
        self._ptr = self._ctx_ptr_ptr[0]

        if load_grayscale:
            self.set_load_grayscale(True)

        try:
            if path is not None:
                self.load_from_file(path)
            elif bytes_data is not None:
                self.load_from_memory(bytes_data)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if hasattr(self, "_ptr") and self._ptr is not None:
            lib.ph_free(self._ptr)
            self._ptr = None

    def __enter__(self) -> ImageContext:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, *args: Any) -> None:
        self.close()

    def load_from_file(self, path: str | Path) -> None:
        check_error(lib.ph_load_from_file(self._ptr, str(path).encode()))

    def load_from_memory(self, data: bytes) -> None:
        check_error(lib.ph_load_from_memory(self._ptr, data, len(data)))

    def set_gamma(self, gamma: float) -> None:
        lib.ph_context_set_gamma(self._ptr, float(gamma))

    def set_gray_weights(self, r: int, g: int, b: int) -> None:
        lib.ph_context_set_gray_weights(self._ptr, r, g, b)

    def set_phash_params(self, dct_size: int, reduction_size: int) -> None:
        lib.ph_context_set_phash_params(self._ptr, dct_size, reduction_size)

    def set_radial_params(self, projections: int, samples: int) -> None:
        lib.ph_context_set_radial_params(self._ptr, projections, samples)

    def set_block_params(self, block_size: int) -> None:
        lib.ph_context_set_block_params(self._ptr, block_size)

    def set_whash_mode(self, mode: str) -> None:
        """
        Sets the operating mode for Wavelet Hash (wHash).
        :param mode: "fast" (default 15x speedup) or "full" (ImageHash accurate).
        """
        if mode == "fast":
            lib.ph_context_set_whash_mode(self._ptr, lib.PH_WHASH_FAST)
        elif mode == "full":
            lib.ph_context_set_whash_mode(self._ptr, lib.PH_WHASH_FULL)
        else:
            raise ValueError(f"Unknown whash mode: {mode}")

    def set_load_grayscale(self, enable: bool) -> None:
        """
        Controls whether images are loaded as grayscale by default.
        Enabling this provides significant speedup for grayscale-only hashes.
        """
        lib.ph_context_set_load_grayscale(self._ptr, 1 if enable else 0)

    def _uint64_prop(self, func: Callable[[Any, Any], int]) -> int:
        out = ffi.new("uint64_t *")
        check_error(func(self._ptr, out))
        return int(out[0])

    def _digest_prop(self, func: Callable[[Any, Any], int]) -> Digest:
        out = ffi.new("ph_digest_t *")
        check_error(func(self._ptr, out))
        return Digest.from_c_struct(out[0])

    @property
    def ahash(self) -> int:
        return self._uint64_prop(lib.ph_compute_ahash)

    @property
    def dhash(self) -> int:
        return self._uint64_prop(lib.ph_compute_dhash)

    @property
    def phash(self) -> int:
        return self._uint64_prop(lib.ph_compute_phash)

    @property
    def whash(self) -> int:
        return self._uint64_prop(lib.ph_compute_whash)

    @property
    def mhash(self) -> int:
        return self._uint64_prop(lib.ph_compute_mhash)

    @property
    def color_hash(self) -> int:
        return self._uint64_prop(lib.ph_compute_color_hash)

    @property
    def bmh(self) -> Digest:
        return self._digest_prop(lib.ph_compute_bmh)

    @property
    def color_moments_hash(self) -> Digest:
        return self._digest_prop(lib.ph_compute_color_moments_hash)

    @property
    def radial_hash(self) -> Digest:
        return self._digest_prop(lib.ph_compute_radial_hash)
