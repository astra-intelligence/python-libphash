import math
import pickle
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from conftest import exactly

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
    assert bytes(a) == b"\x01\x02"
    assert len(a) == 2


def test_hex_round_trip_keeps_the_kind(photo: Path) -> None:
    algos: tuple[ph.DigestName, ...] = (
        "bmh",
        "mhash",
        "radial",
        "color_hash",
        "color_moments",
    )
    for algo in algos:
        d = ph.hash(photo, algo)
        text = d.hex()
        assert text.startswith(d.kind.name.lower() + ":")
        assert Digest.from_hex(text) == d
        assert eval(repr(d), {"Digest": Digest}) == d


def test_from_hex_rejects_garbage() -> None:
    with pytest.raises(ph.InvalidArgumentError):
        Digest.from_hex("bits:xyz")


@pytest.mark.parametrize("tail", ["\0", "\0ff", "\udcff", "\u0444"])
def test_hex_parsers_read_the_whole_text(tail: str) -> None:
    # C stops at a null byte: the text after it must not be dropped unseen.
    with pytest.raises(ph.InvalidArgumentError):
        Digest.from_hex("bits:abcd" + tail)
    with pytest.raises(ph.InvalidArgumentError):
        ph.hash_from_hex("0123456789abcdef" + tail)


def test_pickle(photo: Path) -> None:
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


def test_similarity_picks_the_metric_of_the_kind(photo: Path) -> None:
    algos: tuple[ph.DigestName, ...] = ("bmh", "mhash", "color_hash")
    for algo in algos:
        d = ph.hash(photo, algo)
        assert math.isclose(d.similarity(d), 1.0, rel_tol=1e-6)
    radial = ph.hash(photo, "radial")
    assert math.isclose(radial.similarity(radial), 1.0, rel_tol=1e-6)
    assert radial.similarity(radial) == radial.radial_similarity(radial)


def test_color_moments_have_no_similarity(photo: Path) -> None:
    d = ph.hash(photo, "color_moments")
    assert d.l2_distance(d) == 0.0
    with pytest.raises(ph.DigestKindError, match="l2_distance"):
        d.similarity(d)


def test_wrong_metric_is_refused(photo: Path) -> None:
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
    assert math.isclose(a.l2_distance(b), 5.0, rel_tol=1e-6)
    with pytest.raises(ph.DigestKindError, match="neither digest"):
        a.similarity(b)


def test_digest_info_matches_computed_digests(photo: Path) -> None:
    for algo in ph.Algorithm:
        size, kind = ph.digest_info(algo)
        value = ph.hash(photo, algo)
        if isinstance(value, int):
            assert (size, kind) == (8, DigestKind.BITS)
        else:
            assert (size, kind) == (len(value), value.kind)
    assert ph.digest_info("bmh", ph.Config(bmh_block_size=8)) == (8, DigestKind.BITS)


def test_comparing_with_other_types() -> None:
    d = Digest(b"\1", DigestKind.BITS)
    assert d != b"\1"
    assert (d == 1) is False
    with pytest.raises(TypeError, match="expected a Digest, got bytes"):
        d.hamming_distance(cast("Digest", b"\1"))
    for kind in DigestKind:
        with pytest.raises(TypeError, match="expected a Digest, got int"):
            Digest(b"\1", kind).similarity(cast("Digest", 1))


def test_hash_from_hex_rejects_garbage() -> None:
    with pytest.raises(ph.InvalidArgumentError, match="parsing hash 'xyz'"):
        ph.hash_from_hex("xyz")


BITS = Digest(b"\x0f", DigestKind.BITS)
UNSPECIFIED = Digest(b"\x0f", DigestKind.UNSPECIFIED)


def test_similarity_takes_the_kind_either_digest_states() -> None:
    assert BITS.similarity(UNSPECIFIED) == 1.0
    assert UNSPECIFIED.similarity(BITS) == 1.0
    message = (
        "similarity: neither digest states its kind, so the measure is unknown; call "
        "hamming_distance(), l2_distance(), histogram_intersection() or "
        "radial_similarity() explicitly"
    )
    with pytest.raises(ph.DigestKindError, match=exactly(message)):
        UNSPECIFIED.similarity(UNSPECIFIED)
    vector16 = Digest(b"\0\0", DigestKind.VECTOR16)
    message = (
        "similarity: VECTOR16 digests have no normalized similarity; use l2_distance()"
    )
    with pytest.raises(ph.DigestKindError, match=exactly(message)):
        vector16.similarity(vector16)


@pytest.mark.parametrize(
    ("kind", "metric", "right"),
    [
        (DigestKind.BITS, "l2_distance", "hamming_distance() or similarity()"),
        (DigestKind.VECTOR, "hamming_distance", "l2_distance()"),
        (DigestKind.VECTOR16, "radial_similarity", "l2_distance()"),
        (
            DigestKind.HISTOGRAM,
            "hamming_distance",
            "histogram_intersection() or similarity()",
        ),
        (DigestKind.COEFFICIENTS, "l2_distance", "radial_similarity() or similarity()"),
    ],
)
def test_wrong_kind_names_the_right_metric(
    kind: DigestKind, metric: str, right: str
) -> None:
    d = Digest(b"\0\0", kind)
    message = f"{metric} does not apply to {kind.name} digests; use {right}"
    with pytest.raises(ph.DigestKindError, match=exactly(message)):
        getattr(d, metric)(Digest(b"\0\0", DigestKind.UNSPECIFIED))


def test_equal_digests_hash_alike_and_others_apart() -> None:
    digests = [Digest(bytes([i]), DigestKind.BITS) for i in range(16)]
    assert hash(Digest(b"\1", DigestKind.BITS)) == hash(digests[1])
    assert len({hash(d) for d in digests}) == len(digests)


@pytest.mark.parametrize(
    ("parse", "what"),
    [(Digest.from_hex, "digest"), (ph.hash_from_hex, "hash")],
)
def test_hex_parsers_quote_the_text(parse: Callable[[str], object], what: str) -> None:
    # Non-ASCII text is refused by the C parser, not by the encoder.
    for text in ("bits:é0", "x" * 50):
        with pytest.raises(
            ph.InvalidArgumentError,
            match=f"^parsing {what} {re.escape(repr(text[:40]))}: ",
        ):
            parse(text)


def test_uint64_messages() -> None:
    with pytest.raises(TypeError, match=exactly("a 64-bit hash is an int, got str")):
        ph.hash_to_hex(cast("int", "1"))
    with pytest.raises(TypeError, match=exactly("a 64-bit hash is an int, got bool")):
        ph.hash_to_hex(True)
    message = "a 64-bit hash is in [0, 2**64), got -1"
    with pytest.raises(ph.InvalidArgumentError, match=exactly(message)):
        ph.hash_to_hex(-1)
