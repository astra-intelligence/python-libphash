import pickle

import pytest

import libphash as ph
from libphash import Digest, DigestKind


def test_construction_checks_size_and_kind() -> None:
    with pytest.raises(ph.InvalidArgumentError):
        Digest(b"", DigestKind.BITS)
    with pytest.raises(ph.InvalidArgumentError):
        Digest(b"\0" * (ph.PH_DIGEST_MAX_BYTES + 1), DigestKind.BITS)
    with pytest.raises(ph.InvalidArgumentError):
        Digest(b"\0", 99)
    assert Digest(b"\0" * ph.PH_DIGEST_MAX_BYTES, DigestKind.BITS)


def test_immutable_hashable_equal() -> None:
    a = Digest(b"\x01\x02", DigestKind.BITS)
    with pytest.raises(AttributeError):
        a.kind = DigestKind.HISTOGRAM  # type: ignore[misc]
    assert a == Digest(b"\x01\x02", 1)
    assert a != Digest(b"\x01\x02", DigestKind.HISTOGRAM)
    assert len({a, Digest(b"\x01\x02", DigestKind.BITS)}) == 1
    assert bytes(a) == b"\x01\x02" and len(a) == 2


def test_hex_round_trip_keeps_the_kind(photo) -> None:
    for algo in ("bmh", "mhash", "radial", "color_hash", "color_moments"):
        d = ph.hash(photo, algo)
        text = d.hex()
        assert text.startswith(d.kind.name.lower() + ":")
        assert Digest.from_hex(text) == d
        assert eval(repr(d), {"Digest": Digest}) == d


def test_from_hex_rejects_garbage() -> None:
    with pytest.raises(ph.InvalidArgumentError):
        Digest.from_hex("bits:xyz")


def test_pickle(photo) -> None:
    d = ph.hash(photo, "radial")
    assert pickle.loads(pickle.dumps(d)) == d


def test_from_uint64_matches_hex() -> None:
    d = Digest.from_uint64(0x0123456789ABCDEF)
    assert d.kind == DigestKind.BITS
    assert d.hex() == "bits:0123456789abcdef"
    assert ph.hash_to_hex(0x0123456789ABCDEF) == "0123456789abcdef"
    assert ph.hash_from_hex("0123456789abcdef") == 0x0123456789ABCDEF
    assert d.hamming_distance(Digest.from_uint64(0x0123456789ABCDEE)) == 1


def test_uint64_helpers_check_range() -> None:
    assert ph.hamming_distance(0, 2**64 - 1) == 64
    with pytest.raises(ph.InvalidArgumentError):
        ph.hamming_distance(-1, 0)
    with pytest.raises(TypeError):
        ph.hamming_distance(1.0, 0)  # type: ignore[arg-type]


def test_similarity_picks_the_metric_of_the_kind(photo) -> None:
    for algo in ("bmh", "mhash", "color_hash"):
        d = ph.hash(photo, algo)
        assert d.similarity(d) == pytest.approx(1.0)
    radial = ph.hash(photo, "radial")
    assert radial.similarity(radial) == pytest.approx(1.0)
    assert radial.similarity(radial) == radial.radial_similarity(radial)


def test_color_moments_have_no_similarity(photo) -> None:
    d = ph.hash(photo, "color_moments")
    assert d.l2_distance(d) == 0.0
    with pytest.raises(ph.DigestKindError, match="l2_distance"):
        d.similarity(d)


def test_wrong_metric_is_refused(photo) -> None:
    radial = ph.hash(photo, "radial")
    with pytest.raises(ph.DigestKindError, match="radial_similarity"):
        radial.hamming_distance(radial)
    with pytest.raises(TypeError):  # DigestKindError is a TypeError
        ph.hash(photo, "bmh").l2_distance(ph.hash(photo, "bmh"))


def test_different_sizes_are_refused() -> None:
    with pytest.raises(ph.InvalidArgumentError, match="different sizes"):
        Digest(b"\0\0", DigestKind.BITS).hamming_distance(
            Digest(b"\0", DigestKind.BITS)
        )


def test_flat_radial_digest_has_no_structure() -> None:
    flat = Digest(b"\0" * 40, DigestKind.COEFFICIENTS)
    with pytest.raises(ph.NoStructureError):
        flat.similarity(flat)


def test_unspecified_kind() -> None:
    a = Digest(bytes([10, 10]), DigestKind.UNSPECIFIED)
    b = Digest(bytes([14, 13]), DigestKind.UNSPECIFIED)
    assert a.l2_distance(b) == pytest.approx(5.0)
    with pytest.raises(ph.DigestKindError, match="neither digest"):
        a.similarity(b)


def test_digest_info_matches_computed_digests(photo) -> None:
    for algo in ph.Algorithm:
        size, kind = ph.digest_info(algo)
        value = ph.hash(photo, algo)
        if isinstance(value, int):
            assert (size, kind) == (8, DigestKind.BITS)
        else:
            assert (size, kind) == (len(value), value.kind)
    assert ph.digest_info("bmh", ph.Config(bmh_block_size=8)) == (8, DigestKind.BITS)
