"""Every comparison against a reference written from libphash's documented formula.

libphash computes its comparisons in exact integers and rounds once at the end, so the
references below, in Python's IEEE doubles, give the same float to the last bit: the
tests compare with ``==``, not with a tolerance. They run on the golden digests of the
C test fixtures and on random digests.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_golden import ENTRIES, UINT64

import libphash as ph
from libphash import Digest, DigestKind

MAX = ph.PH_DIGEST_MAX_BYTES


# --- References -----------------------------------------------------------------------


def ref_hamming(a: bytes, b: bytes) -> int:
    return sum((x ^ y).bit_count() for x, y in zip(a, b, strict=True))


def ref_similarity(a: bytes, b: bytes) -> float:
    return 1.0 - ref_hamming(a, b) / (len(a) * 8.0)


def ref_l2_vector16(a: bytes, b: bytes) -> float:
    total = 0.0
    for i in range(0, len(a), 2):
        va = int.from_bytes(a[i : i + 2], "big", signed=True) / 128.0
        vb = int.from_bytes(b[i : i + 2], "big", signed=True) / 128.0
        total += (va - vb) * (va - vb)
    return math.sqrt(total)


def ref_l2_vector(a: bytes, b: bytes) -> float:
    total = 0.0
    for x, y in zip(a, b, strict=True):
        total += float(x - y) * float(x - y)
    return math.sqrt(total)


def ref_histogram_intersection(a: bytes, b: bytes) -> float:
    sum_a, sum_b = sum(a), sum(b)
    if sum_a == 0 or sum_b == 0:
        return 1.0 if sum_a == sum_b else 0.0
    overlap = sum(min(x * sum_b, y * sum_a) for x, y in zip(a, b, strict=True))
    return overlap / float(sum_a * sum_b)


def ref_radial(a: bytes, b: bytes) -> float | None:
    """Peak Pearson correlation over cyclic shifts of b; None for a flat digest."""
    n = len(a)
    var_a = n * sum(x * x for x in a) - sum(a) ** 2
    var_b = n * sum(y * y for y in b) - sum(b) ** 2
    if var_a <= 0 or var_b <= 0:
        return None
    peak = max(
        n * sum(a[i] * b[(i - d) % n] for i in range(n)) - sum(a) * sum(b)
        for d in range(n)
    )
    return min(1.0, max(-1.0, peak / math.sqrt(float(var_a) * float(var_b))))


# --- Golden digests -------------------------------------------------------------------


def golden_values(algorithm: ph.Algorithm) -> list[bytes]:
    return sorted({bytes.fromhex(e.hex) for e in ENTRIES if e.algorithm == algorithm})


def pairs(algorithm: ph.Algorithm) -> list[tuple[bytes, bytes]]:
    values = golden_values(algorithm)
    if len(values) < 2:
        pytest.skip("golden files are missing (native/libphash not checked out?)")
    return [(a, b) for a in values for b in values]


@pytest.mark.parametrize("algorithm", UINT64)
def test_uint64_metrics(algorithm: ph.Algorithm) -> None:
    for a, b in pairs(algorithm):
        x, y = int.from_bytes(a, "big"), int.from_bytes(b, "big")
        assert ph.hamming_distance(x, y) == ref_hamming(a, b)
        assert ph.similarity(x, y) == 1.0 - ref_hamming(a, b) / 64.0


@pytest.mark.parametrize("algorithm", [ph.Algorithm.BMH, ph.Algorithm.MHASH])
def test_bit_metrics(algorithm: ph.Algorithm) -> None:
    for a, b in pairs(algorithm):
        da, db = Digest(a, DigestKind.BITS), Digest(b, DigestKind.BITS)
        assert da.hamming_distance(db) == ref_hamming(a, b)
        assert da.similarity(db) == ref_similarity(a, b)


def test_color_moments_l2() -> None:
    for a, b in pairs(ph.Algorithm.COLOR_MOMENTS):
        da, db = Digest(a, DigestKind.VECTOR16), Digest(b, DigestKind.VECTOR16)
        assert da.l2_distance(db) == ref_l2_vector16(a, b)


def test_color_hash_intersection() -> None:
    for a, b in pairs(ph.Algorithm.COLOR_HASH):
        da, db = Digest(a, DigestKind.HISTOGRAM), Digest(b, DigestKind.HISTOGRAM)
        assert da.histogram_intersection(db) == ref_histogram_intersection(a, b)
        assert da.similarity(db) == ref_histogram_intersection(a, b)


def test_radial_similarity() -> None:
    compared = 0
    for a, b in pairs(ph.Algorithm.RADIAL):
        da, db = Digest(a, DigestKind.COEFFICIENTS), Digest(b, DigestKind.COEFFICIENTS)
        expected = ref_radial(a, b)
        if expected is None:
            with pytest.raises(ph.NoStructureError):
                da.radial_similarity(db)
            continue
        assert da.radial_similarity(db) == expected
        assert da.similarity(db) == expected
        compared += 1
    assert compared > 0


# --- Random digests -------------------------------------------------------------------


def same_size_pair(
    min_size: int = 1, step: int = 1
) -> st.SearchStrategy[tuple[bytes, bytes]]:
    sizes = st.integers(min_size, MAX // step).map(lambda n: n * step)
    return sizes.flatmap(
        lambda n: st.tuples(
            st.binary(min_size=n, max_size=n), st.binary(min_size=n, max_size=n)
        )
    )


@given(st.integers(0, 2**64 - 1), st.integers(0, 2**64 - 1))
def test_random_uint64(x: int, y: int) -> None:
    assert ph.hamming_distance(x, y) == (x ^ y).bit_count()
    assert ph.hamming_distance(x, y) == ph.hamming_distance(y, x)
    assert ph.similarity(x, y) == 1.0 - (x ^ y).bit_count() / 64.0
    assert ph.hash_from_hex(ph.hash_to_hex(x)) == x


@given(same_size_pair())
def test_random_bits(pair: tuple[bytes, bytes]) -> None:
    a, b = pair
    da, db = Digest(a, DigestKind.BITS), Digest(b, DigestKind.BITS)
    assert da.hamming_distance(db) == db.hamming_distance(da) == ref_hamming(a, b)
    assert da.similarity(db) == db.similarity(da) == ref_similarity(a, b)
    assert da.hamming_distance(da) == 0
    assert da.similarity(da) == 1.0


@given(same_size_pair(step=2))
def test_random_vector16(pair: tuple[bytes, bytes]) -> None:
    a, b = pair
    da, db = Digest(a, DigestKind.VECTOR16), Digest(b, DigestKind.VECTOR16)
    assert da.l2_distance(db) == db.l2_distance(da) == ref_l2_vector16(a, b)
    assert da.l2_distance(da) == 0.0


@given(same_size_pair())
def test_random_vector(pair: tuple[bytes, bytes]) -> None:
    a, b = pair
    da, db = Digest(a, DigestKind.VECTOR), Digest(b, DigestKind.VECTOR)
    assert da.l2_distance(db) == db.l2_distance(da) == ref_l2_vector(a, b)


@given(same_size_pair())
def test_random_histograms(pair: tuple[bytes, bytes]) -> None:
    a, b = pair
    da, db = Digest(a, DigestKind.HISTOGRAM), Digest(b, DigestKind.HISTOGRAM)
    expected = ref_histogram_intersection(a, b)
    assert da.histogram_intersection(db) == db.histogram_intersection(da) == expected
    assert da.histogram_intersection(da) == 1.0


@given(st.lists(st.integers(0, 255 // 4), min_size=1, max_size=MAX), st.integers(1, 4))
def test_proportional_histograms_intersect_fully(bins: list[int], k: int) -> None:
    # Two empty histograms are equally devoid of pixels and score 1.0 too.
    a = Digest(bytes(bins), DigestKind.HISTOGRAM)
    scaled = Digest(bytes(x * k for x in bins), DigestKind.HISTOGRAM)
    assert a.histogram_intersection(scaled) == scaled.histogram_intersection(a) == 1.0


@given(same_size_pair())
def test_random_radial(pair: tuple[bytes, bytes]) -> None:
    a, b = pair
    da, db = Digest(a, DigestKind.COEFFICIENTS), Digest(b, DigestKind.COEFFICIENTS)
    expected = ref_radial(a, b)
    if expected is None:
        with pytest.raises(ph.NoStructureError):
            da.radial_similarity(db)
        with pytest.raises(ph.NoStructureError):
            db.radial_similarity(da)
        return
    assert da.radial_similarity(db) == db.radial_similarity(da) == expected
    assert da.radial_similarity(da) == ref_radial(a, a)


@given(same_size_pair(), st.sampled_from(list(DigestKind)))
def test_unspecified_kind_is_compared_as_the_other_side(
    pair: tuple[bytes, bytes], kind: DigestKind
) -> None:
    a, b = pair
    untagged = Digest(a, DigestKind.UNSPECIFIED)
    if kind in (DigestKind.BITS, DigestKind.UNSPECIFIED):
        assert untagged.hamming_distance(Digest(b, kind)) == ref_hamming(a, b)
    if kind == DigestKind.HISTOGRAM:
        assert untagged.histogram_intersection(Digest(b, kind)) == (
            ref_histogram_intersection(a, b)
        )


@given(st.binary(min_size=1, max_size=MAX), st.sampled_from(list(DigestKind)))
def test_random_digest_text_round_trip(data: bytes, kind: DigestKind) -> None:
    digest = Digest(data, kind)
    assert Digest.from_hex(digest.hex()) == digest
