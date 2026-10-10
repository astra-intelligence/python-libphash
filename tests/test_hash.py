import io

import pytest

import libphash as ph
from conftest import data

UINT64 = ["ahash", "dhash", "phash", "whash"]
DIGESTS = ["bmh", "mhash", "radial", "color_hash", "color_moments"]


def test_algorithm_names_come_from_the_c_library() -> None:
    assert [str(a) for a in ph.Algorithm] == UINT64 + DIGESTS
    assert len(ph.Algorithm) == ph.lib.PH_ALGORITHM_COUNT
    for algo in ph.Algorithm:
        assert ph.ffi.string(ph.lib.ph_algorithm_name(algo)).decode() == str(algo)
        assert algo.value == getattr(ph.lib, f"PH_ALGO_{algo.name}")
    for kind in ph.DigestKind:
        assert kind.value == getattr(ph.lib, f"PH_DIGEST_KIND_{kind.name}")


@pytest.mark.parametrize("name", UINT64)
def test_uint64_algorithms_return_int(photo, name: str) -> None:
    value = ph.hash(photo, name)
    assert isinstance(value, int) and 0 <= value < 2**64
    assert ph.hash(photo, ph.Algorithm[name.upper()]) == value


@pytest.mark.parametrize(
    "name,kind",
    [
        ("bmh", "BITS"),
        ("mhash", "BITS"),
        ("radial", "COEFFICIENTS"),
        ("color_hash", "HISTOGRAM"),
        ("color_moments", "VECTOR16"),
    ],
)
def test_digest_algorithms_return_tagged_digest(photo, name: str, kind: str) -> None:
    digest = ph.hash(photo, name)
    assert isinstance(digest, ph.Digest)
    assert digest.kind == ph.DigestKind[kind]


def test_default_algorithm_is_phash(photo) -> None:
    assert ph.hash(photo) == ph.hash(photo, "phash")


def test_unknown_algorithm() -> None:
    with pytest.raises(ph.InvalidArgumentError, match="unknown algorithm"):
        ph.hash(data("photo.jpeg"), "sha256")


def test_every_source_type_gives_the_same_hash(photo, photo_bytes) -> None:
    expected = ph.hash(photo)
    assert ph.hash(str(photo)) == expected
    assert ph.hash(photo_bytes) == expected
    assert ph.hash(bytearray(photo_bytes)) == expected
    assert ph.hash(memoryview(photo_bytes)) == expected
    assert ph.hash(io.BytesIO(photo_bytes)) == expected
    with open(photo, "rb") as f:
        assert ph.hash(f) == expected


def test_bytes_are_image_data_not_a_path(photo) -> None:
    with pytest.raises(ph.UnsupportedFormatError):
        ph.hash(str(photo).encode())


def test_unsupported_source_type() -> None:
    with pytest.raises(TypeError, match="expected a path"):
        ph.hash(12345)


def test_formats(photo) -> None:
    for name in ("photo.png", "photo.webp", "photo.jpeg"):
        assert isinstance(ph.hash(data(name)), int)


def test_hashes_matches_single_calls(photo) -> None:
    with ph.ImageContext() as ctx:
        ctx.load_file(photo)
        everything = ctx.hashes(*ph.Algorithm)
        assert list(everything) == list(ph.Algorithm)
        for algo, value in everything.items():
            assert ctx.hash(algo) == value


def test_hashes_keeps_the_requested_order(photo) -> None:
    with ph.ImageContext() as ctx:
        ctx.load_file(photo)
        assert list(ctx.hashes("whash", "radial", "ahash")) == [
            ph.Algorithm.WHASH,
            ph.Algorithm.RADIAL,
            ph.Algorithm.AHASH,
        ]


def test_named_methods(photo) -> None:
    with ph.ImageContext() as ctx:
        ctx.load_file(photo)
        for algo in ph.Algorithm:
            assert getattr(ctx, str(algo))() == ctx.hash(algo)


def test_near_duplicates_are_close(photo) -> None:
    a = ph.hash(photo)
    assert ph.hamming_distance(a, ph.hash(data("photo_copy.jpeg"))) <= 4
    assert ph.similarity(a, a) == 1.0


def test_info() -> None:
    assert ph.build_info().startswith(f"version={ph.libphash_version()} ")
    assert "mock=off" in ph.build_info()
    for fmt in ("jpeg", "png", "webp"):
        assert ph.can_decode(fmt) is True
    with pytest.raises(ValueError):
        ph.can_decode("gif")
