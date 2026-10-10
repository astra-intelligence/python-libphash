import pytest
from libphash import ImageContext, HashMethod, get_hash


@pytest.mark.parametrize(
    "method_name", ["ahash", "dhash", "phash", "whash"]
)
def test_uint64_properties_consistency(sample_jpeg_bytes: bytes, method_name: str):
    """Verify that accessing hash properties multiple times returns consistent results."""
    with ImageContext(bytes_data=sample_jpeg_bytes) as ctx:
        h1 = getattr(ctx, method_name)
        h2 = getattr(ctx, method_name)

        assert isinstance(h1, int)
        assert h1 == h2


def test_get_hash_utility(image_path: str):
    """Verify the high-level get_hash utility function."""
    h1 = get_hash(image_path, method=HashMethod.PHASH)
    h2 = get_hash(image_path, method=HashMethod.AHASH)

    assert isinstance(h1, int)
    assert isinstance(h2, int)
    assert h1 != h2  # Different algorithms should yield different results
