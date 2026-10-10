import dataclasses
import pickle

import pytest

import libphash as ph
from libphash import Config, ffi, lib


def raw_hashes(path) -> dict:
    """Every hash from a context configured by nothing but ph_create()."""
    out = ffi.new("ph_context_t **")
    assert lib.ph_create(out) == 0
    ctx = out[0]
    try:
        assert lib.ph_load_from_file(ctx, str(path).encode()) == 0
        result = {}
        for algo in ph.Algorithm:
            d = ffi.new("ph_digest_t *")
            assert lib.ph_compute_digest(ctx, int(algo), d) == 0
            result[algo] = bytes(ffi.buffer(d.data, d.size))
        return result
    finally:
        lib.ph_free(ctx)


def test_defaults_are_the_c_library_defaults(photo) -> None:
    expected = raw_hashes(photo)
    with ph.ImageContext(Config()) as ctx:
        ctx.load_file(photo)
        for algo in ph.Algorithm:
            d = ffi.new("ph_digest_t *")
            assert lib.ph_compute_digest(ctx._ptr, int(algo), d) == 0
            assert bytes(ffi.buffer(d.data, d.size)) == expected[algo], algo


def test_default_gray_weights_match_the_getter() -> None:
    out = ffi.new("ph_context_t **")
    assert lib.ph_create(out) == 0
    rgb = ffi.new("int[3]")
    assert lib.ph_context_get_gray_weights(out[0], rgb, rgb + 1, rgb + 2) == 0
    lib.ph_free(out[0])
    assert tuple(rgb) == Config().gray_weights


@pytest.mark.parametrize(
    "field,value",
    [
        ("gamma", 0.0),
        ("phash_reduction_size", 9),
        ("radial_projections", 10),
        ("bmh_block_size", 64),
        ("mhash_size", 10),
        ("gray_weights", (0, 0, 0)),
    ],
)
def test_out_of_range_names_the_field(field: str, value) -> None:
    with pytest.raises(ph.InvalidArgumentError, match=field) as exc:
        Config(**{field: value})
    assert isinstance(exc.value, ValueError)


@pytest.mark.parametrize(
    "field,value",
    [
        ("gamma", float("nan")),
        ("phash_dct_size", 32.0),
        ("whash_mode", "slow"),
        ("alpha_mode", "pink"),
        ("decode_scale", 3),
        ("grayscale", 1),
        ("max_pixels", -1),
        ("gray_weights", [38, 75, 15]),
    ],
)
def test_wrong_types_are_refused(field: str, value) -> None:
    with pytest.raises(ph.InvalidArgumentError, match=field):
        Config(**{field: value})


def test_frozen_replace_pickle() -> None:
    cfg = Config()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.gamma = 2.0  # type: ignore[misc]
    changed = cfg.replace(radial_sigma=2.0)
    assert changed.radial_sigma == 2.0 and cfg.radial_sigma == 3.5
    with pytest.raises(ph.InvalidArgumentError):
        cfg.replace(radial_sigma=100.0)
    assert pickle.loads(pickle.dumps(changed)) == changed


def test_settings_change_hashes(photo) -> None:
    base = ph.hash(photo, "radial")
    assert ph.hash(photo, "radial", config=Config(gamma=2.2)) != base
    assert len(ph.hash(photo, "bmh", config=Config(bmh_block_size=8))) == 8
    small = Config(phash_reduction_size=4)
    assert ph.hash(photo, config=small) < 2**16


def test_grayscale_refuses_color_hashes(photo) -> None:
    gray = Config(grayscale=True)
    assert isinstance(ph.hash(photo, config=gray), int)
    with pytest.raises(ph.RequiresColorError):
        ph.hash(photo, "color_hash", config=gray)


def test_max_pixels(photo) -> None:
    with pytest.raises(ph.ImageTooLargeError):
        ph.hash(photo, config=Config(max_pixels=100))


def test_decode_scale(photo) -> None:
    with ph.ImageContext(Config(decode_scale=2)) as ctx:
        ctx.load_file(photo)
        assert (ctx.width, ctx.height) == (200, 200)


def test_whash_mode_reaches_c() -> None:
    # On a photo both modes reduce to similar 8x8 block means and often agree; on noise
    # they differ.
    import random

    rng = random.Random(1)
    noise = memoryview(bytes(rng.randrange(256) for _ in range(300 * 300 * 3))).cast(
        "B", (300, 300, 3)
    )
    assert ph.hash(noise, "whash") != ph.hash(noise, "whash", config=Config(whash_mode="full"))
