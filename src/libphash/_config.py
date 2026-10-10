from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Any, Literal, NoReturn, cast

from ._native import ffi, lib
from ._errors import PH_SUCCESS, check, error_string
from .exceptions import InvalidArgumentError

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
        ctx = new_context()
        try:
            apply_config(self, ctx)
        finally:
            lib.ph_free(ctx)

    def replace(self, **changes: Any) -> Config:
        """A copy with the given fields changed (checked like a new Config)."""
        return dataclasses.replace(self, **changes)


def apply_config(cfg: Config, ctx: Any) -> None:
    """Set every field of ``cfg`` on a ``ph_context_t``."""
    steps: list[tuple[str, int]] = [
        ("gamma", lib.ph_context_set_gamma(ctx, cfg.gamma)),
        ("gray_weights", lib.ph_context_set_gray_weights(ctx, *cfg.gray_weights)),
        (
            "phash_dct_size/phash_reduction_size",
            lib.ph_context_set_phash_params(
                ctx, cfg.phash_dct_size, cfg.phash_reduction_size
            ),
        ),
        (
            "radial_projections/radial_samples/radial_sigma",
            lib.ph_context_set_radial_params(
                ctx, cfg.radial_projections, cfg.radial_samples, cfg.radial_sigma
            ),
        ),
        (
            "bmh_block_size",
            lib.ph_context_set_block_params(ctx, cfg.bmh_block_size),
        ),
        (
            "mhash_alpha/mhash_level/mhash_size",
            lib.ph_context_set_mhash_params(
                ctx, cfg.mhash_alpha, cfg.mhash_level, cfg.mhash_size
            ),
        ),
        (
            "whash_mode",
            lib.ph_context_set_whash_mode(ctx, _WHASH_MODES[cfg.whash_mode]),
        ),
        (
            "whash_remove_max_haar_ll",
            lib.ph_context_set_whash_remove_max_haar_ll(
                ctx, int(cfg.whash_remove_max_haar_ll)
            ),
        ),
        ("grayscale", lib.ph_context_set_load_grayscale(ctx, int(cfg.grayscale))),
        (
            "alpha_mode",
            lib.ph_context_set_alpha_mode(ctx, _ALPHA_MODES[cfg.alpha_mode]),
        ),
        ("auto_orient", lib.ph_context_set_auto_orient(ctx, int(cfg.auto_orient))),
        ("max_pixels", lib.ph_context_set_max_pixels(ctx, cfg.max_pixels)),
        (
            "decode_scale",
            lib.ph_context_set_decode_scale(ctx, _DECODE_SCALES[cfg.decode_scale]),
        ),
    ]
    for name, code in steps:
        if code != PH_SUCCESS:
            values = ", ".join(f"{f}={getattr(cfg, f)!r}" for f in name.split("/"))
            raise InvalidArgumentError(
                f"Config: {values} is out of range: {error_string(code)}", code=code
            )


def new_context() -> Any:
    out = ffi.new("ph_context_t **")
    check(lib.ph_create(out), context="creating a context")
    return out[0]


def _check_types(cfg: Config) -> None:
    # The annotations do not bind an untyped caller; every value is checked as an object.
    def fail(name: str, expected: str) -> NoReturn:
        raise InvalidArgumentError(
            f"Config: {name} must be {expected}, got {getattr(cfg, name)!r}"
        )

    def value(name: str) -> object:
        return getattr(cfg, name)

    for name in ("gamma", "radial_sigma", "mhash_alpha", "mhash_level"):
        v = value(name)
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
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
        if not _is_int(value(name)):
            fail(name, "an int")
    if not (0 <= cfg.max_pixels < 1 << 64):
        fail("max_pixels", "in [0, 2**64)")
    weights = value("gray_weights")
    items = cast("tuple[object, ...]", weights) if isinstance(weights, tuple) else ()
    if len(items) != 3 or not all(_is_int(w) for w in items):
        fail("gray_weights", "a tuple of three ints")
    for name in ("whash_remove_max_haar_ll", "grayscale", "auto_orient"):
        if not isinstance(value(name), bool):
            fail(name, "a bool")
    if value("whash_mode") not in _WHASH_MODES:
        fail("whash_mode", "one of " + ", ".join(map(repr, _WHASH_MODES)))
    if value("alpha_mode") not in _ALPHA_MODES:
        fail("alpha_mode", "one of " + ", ".join(map(repr, _ALPHA_MODES)))
    scale = value("decode_scale")
    if not _is_int(scale) or scale not in _DECODE_SCALES:
        fail("decode_scale", "1, 2, 4 or 8")


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)
