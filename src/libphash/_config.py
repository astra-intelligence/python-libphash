from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Any, Literal

from ._native import ffi, lib
from .exceptions import InvalidArgumentError, PH_SUCCESS, check, error_string

WHashMode = Literal["fast", "full"]
AlphaMode = Literal["grey", "white", "black", "ignore"]
DecodeScale = Literal[1, 2, 4, 8]

_WHASH_MODES = {"fast": lib.PH_WHASH_FAST, "full": lib.PH_WHASH_FULL}
_ALPHA_MODES = {
    "grey": lib.PH_ALPHA_BLEND_GREY,
    "white": lib.PH_ALPHA_BLEND_WHITE,
    "black": lib.PH_ALPHA_BLEND_BLACK,
    "ignore": lib.PH_ALPHA_IGNORE,
}
_DECODE_SCALES = {
    1: lib.PH_DECODE_SCALE_FULL,
    2: lib.PH_DECODE_SCALE_HALF,
    4: lib.PH_DECODE_SCALE_QUARTER,
    8: lib.PH_DECODE_SCALE_EIGHTH,
}


@dataclass(frozen=True)
class Config:
    """How images are loaded and hashed: every setting of a libphash context.

    The defaults are libphash's. A ``Config`` is checked when it is created, against the
    ranges the C library accepts, so a bad value fails here with the name of the field
    and not at the first hash. It is immutable; :meth:`replace` gives a modified copy.
    The same object configures an :class:`ImageContext`, :func:`hash` and a batch.

    Hash values depend on the settings: two hashes are comparable only when computed
    with equal configurations (and the same libphash version).
    """

    #: Gamma applied before the Radial hash's projections; read by Radial only.
    gamma: float = 1.0
    #: Relative R, G, B weights of the grayscale conversion.
    gray_weights: tuple[int, int, int] = (38, 75, 15)
    #: pHash: side of the DCT grid (``phash_reduction_size``..32).
    phash_dct_size: int = 32
    #: pHash: side of the low-frequency block the hash is made of, 4..8 (the hash has its square in bits).
    phash_reduction_size: int = 8
    #: Radial: number of lines through the center, 40..4096.
    radial_projections: int = 180
    #: Radial: points read on each line, 2..4096.
    radial_samples: int = 128
    #: Radial: Gaussian blur sigma before the projections, (0, 64/3].
    radial_sigma: float = 3.5
    #: BMH: side of the block grid, 2..32 (the digest has its square in bits).
    bmh_block_size: int = 16
    #: mHash: scale base (> 1).
    mhash_alpha: float = 2.0
    #: mHash: scale exponent (>= 0).
    mhash_level: float = 1.0
    #: mHash: normalization side, 62..4096.
    mhash_size: int = 512
    #: wHash: ``"fast"`` (16x16, one Haar level) or ``"full"`` (ImageHash's scale).
    whash_mode: WHashMode = "fast"
    #: wHash: zero the coarsest LL coefficient (ImageHash's ``remove_max_haar_ll``).
    whash_remove_max_haar_ll: bool = False
    #: Decode to one gray channel. Faster; the color algorithms then raise RequiresColorError.
    grayscale: bool = False
    #: How an alpha channel is resolved: blended over grey, white or black, or ignored.
    alpha_mode: AlphaMode = "grey"
    #: Apply the EXIF orientation of JPEG and PNG files and buffers.
    auto_orient: bool = True
    #: Largest image accepted, in pixels; 0 leaves only the library's fixed limit.
    max_pixels: int = 256 * 1024 * 1024
    #: Decode at 1/1, 1/2, 1/4 or 1/8 of the resolution where the decoder can (JPEG).
    decode_scale: DecodeScale = 1

    def __post_init__(self) -> None:
        _check_types(self)
        ctx = _new_context()
        try:
            self._apply(ctx)
        finally:
            lib.ph_free(ctx)

    def replace(self, **changes: Any) -> Config:
        """A copy with the given fields changed (checked like a new Config)."""
        return dataclasses.replace(self, **changes)

    def _apply(self, ctx: Any) -> None:
        """Set every field on a ``ph_context_t``."""
        steps: list[tuple[str, int]] = [
            ("gamma", lib.ph_context_set_gamma(ctx, self.gamma)),
            ("gray_weights", lib.ph_context_set_gray_weights(ctx, *self.gray_weights)),
            (
                "phash_dct_size/phash_reduction_size",
                lib.ph_context_set_phash_params(
                    ctx, self.phash_dct_size, self.phash_reduction_size
                ),
            ),
            (
                "radial_projections/radial_samples/radial_sigma",
                lib.ph_context_set_radial_params(
                    ctx, self.radial_projections, self.radial_samples, self.radial_sigma
                ),
            ),
            (
                "bmh_block_size",
                lib.ph_context_set_block_params(ctx, self.bmh_block_size),
            ),
            (
                "mhash_alpha/mhash_level/mhash_size",
                lib.ph_context_set_mhash_params(
                    ctx, self.mhash_alpha, self.mhash_level, self.mhash_size
                ),
            ),
            (
                "whash_mode",
                lib.ph_context_set_whash_mode(ctx, _WHASH_MODES[self.whash_mode]),
            ),
            (
                "whash_remove_max_haar_ll",
                lib.ph_context_set_whash_remove_max_haar_ll(
                    ctx, int(self.whash_remove_max_haar_ll)
                ),
            ),
            ("grayscale", lib.ph_context_set_load_grayscale(ctx, int(self.grayscale))),
            (
                "alpha_mode",
                lib.ph_context_set_alpha_mode(ctx, _ALPHA_MODES[self.alpha_mode]),
            ),
            ("auto_orient", lib.ph_context_set_auto_orient(ctx, int(self.auto_orient))),
            ("max_pixels", lib.ph_context_set_max_pixels(ctx, self.max_pixels)),
            (
                "decode_scale",
                lib.ph_context_set_decode_scale(ctx, _DECODE_SCALES[self.decode_scale]),
            ),
        ]
        for name, code in steps:
            if code != PH_SUCCESS:
                values = ", ".join(f"{f}={getattr(self, f)!r}" for f in name.split("/"))
                raise InvalidArgumentError(
                    f"Config: {values} is out of range: {error_string(code)}", code=code
                )


def _new_context() -> Any:
    out = ffi.new("ph_context_t **")
    check(lib.ph_create(out), context="creating a context")
    return out[0]


def _check_types(cfg: Config) -> None:
    def fail(name: str, expected: str) -> None:
        raise InvalidArgumentError(
            f"Config: {name} must be {expected}, got {getattr(cfg, name)!r}"
        )

    for name in ("gamma", "radial_sigma", "mhash_alpha", "mhash_level"):
        value = getattr(cfg, name)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            fail(name, "a finite number")
    for name in (
        "phash_dct_size",
        "phash_reduction_size",
        "radial_projections",
        "radial_samples",
        "bmh_block_size",
        "mhash_size",
        "max_pixels",
    ):
        value = getattr(cfg, name)
        if isinstance(value, bool) or not isinstance(value, int):
            fail(name, "an int")
    if not (0 <= cfg.max_pixels < 1 << 64):
        fail("max_pixels", "in [0, 2**64)")
    weights = cfg.gray_weights
    if (
        not isinstance(weights, tuple)
        or len(weights) != 3
        or any(isinstance(w, bool) or not isinstance(w, int) for w in weights)
    ):
        fail("gray_weights", "a tuple of three ints")
    for name in ("whash_remove_max_haar_ll", "grayscale", "auto_orient"):
        if not isinstance(getattr(cfg, name), bool):
            fail(name, "a bool")
    if cfg.whash_mode not in _WHASH_MODES:
        fail("whash_mode", "one of " + ", ".join(map(repr, _WHASH_MODES)))
    if cfg.alpha_mode not in _ALPHA_MODES:
        fail("alpha_mode", "one of " + ", ".join(map(repr, _ALPHA_MODES)))
    if isinstance(cfg.decode_scale, bool) or cfg.decode_scale not in _DECODE_SCALES:
        fail("decode_scale", "1, 2, 4 or 8")
