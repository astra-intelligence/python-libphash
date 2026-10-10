"""Properties of hashing random images: determinism, equivalent inputs agree."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import libphash as ph

pytest.importorskip("numpy")
pytest.importorskip("PIL")
import numpy as np
from hypothesis.extra import numpy as hnp
from PIL import Image

if TYPE_CHECKING:
    from numpy.typing import NDArray

COLOR = (ph.Algorithm.COLOR_HASH, ph.Algorithm.COLOR_MOMENTS)
GRAY = tuple(a for a in ph.Algorithm if a not in COLOR)

# mHash normalizes every image to 512 x 512, so an example costs milliseconds whatever
# its size; fewer examples than the default keep the module to a few seconds.
examples = settings(max_examples=40, deadline=None)


def images(channels: int) -> st.SearchStrategy[NDArray[np.uint8]]:
    shape = st.tuples(st.integers(1, 48), st.integers(1, 48)).map(
        lambda hw: (*hw, channels) if channels > 1 else hw
    )
    return hnp.arrays(np.dtype(np.uint8), shape)


def outcome(ctx: ph.ImageContext, algorithm: ph.Algorithm) -> object:
    """Return the hash, or the type of the error: equivalent inputs agree on either."""
    try:
        return ctx.hash(algorithm)
    except ph.PhashError as e:
        return type(e)


def outcomes(
    pixels: object,
    algorithms: tuple[ph.Algorithm, ...] = tuple(ph.Algorithm),
    **kw: object,
) -> dict[ph.Algorithm, object]:
    with ph.ImageContext() as ctx:
        ctx.load_pixels(pixels, **kw)  # type: ignore[arg-type]
        return {a: outcome(ctx, a) for a in algorithms}


@examples
@given(images(3))
def test_hashing_is_deterministic(rgb: NDArray[np.uint8]) -> None:
    first = outcomes(rgb)
    assert outcomes(rgb) == first
    with ph.ImageContext() as reused:
        reused.load_pixels(np.zeros((5, 7, 3), np.uint8))
        reused.hashes(*GRAY)
        reused.load_pixels(rgb)
        assert {a: outcome(reused, a) for a in ph.Algorithm} == first


@examples
@given(images(1))
def test_gray_is_rgb_with_equal_channels(gray: NDArray[np.uint8]) -> None:
    expected = outcomes(gray, GRAY)
    assert outcomes(gray[..., None], GRAY) == expected
    assert outcomes(gray[..., None].repeat(3, axis=2), GRAY) == expected
    for algorithm in COLOR:
        with pytest.raises(ph.RequiresColorError):
            ph.hash(gray, algorithm)


@examples
@given(images(3))
def test_opaque_alpha_changes_nothing(rgb: NDArray[np.uint8]) -> None:
    rgba = np.full((*rgb.shape[:2], 4), 255, np.uint8)
    rgba[..., :3] = rgb
    assert outcomes(rgba) == outcomes(rgb)


@examples
@given(images(3))
def test_bgr_is_reversed_rgb(rgb: NDArray[np.uint8]) -> None:
    assert outcomes(
        np.ascontiguousarray(rgb[..., ::-1]), channel_order="bgr"
    ) == outcomes(rgb)


@examples
@given(images(3))
def test_lossless_file_hashes_like_its_pixels(rgb: NDArray[np.uint8]) -> None:
    out = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(out, "PNG")
    with ph.ImageContext() as ctx:
        ctx.load_bytes(out.getvalue())
        assert {a: outcome(ctx, a) for a in ph.Algorithm} == outcomes(rgb)


@examples
@given(images(3))
def test_every_hash_matches_itself(rgb: NDArray[np.uint8]) -> None:
    for algorithm, value in outcomes(rgb).items():
        if isinstance(value, int):
            assert ph.hamming_distance(value, value) == 0
        elif isinstance(value, ph.Digest):
            if value.kind == ph.DigestKind.VECTOR16:
                assert value.l2_distance(value) == 0.0
            elif value.kind == ph.DigestKind.COEFFICIENTS and len(set(value.data)) == 1:
                with pytest.raises(ph.NoStructureError):
                    value.similarity(value)
            else:
                assert abs(value.similarity(value) - 1.0) <= 1e-15, algorithm
