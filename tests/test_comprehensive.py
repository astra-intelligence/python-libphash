import pytest
from libphash import ImageContext, PhashError


def test_context_parameters(image_path: str):
    """Verify that parameters can be set without errors."""
    with ImageContext(image_path) as ctx:
        ctx.set_gamma(1.8)
        ctx.set_gray_weights(30, 60, 10)
        ctx.set_phash_params(dct_size=16, reduction_size=4)
        ctx.set_whash_mode("full")

        # Accessing hash should work with custom params
        h = ctx.phash
        assert isinstance(h, int)


def test_load_grayscale_logic(image_path: str):
    """Verify grayscale loading speed/consistency."""
    with ImageContext(image_path, load_grayscale=True) as ctx:
        h1 = ctx.ahash

    with ImageContext(image_path, load_grayscale=False) as ctx:
        h2 = ctx.ahash

    # aHash is grayscale-based, so results should be very close or identical
    # depending on how color weights were normalized in libphash.
    assert isinstance(h1, int)
    assert h1 == h2


def test_error_invalid_file():
    """Verify exception on missing file."""
    with pytest.raises(PhashError, match="could not be opened"):
        ImageContext("non_existent_file.jpg")


def test_error_empty_memory():
    """Verify exception on empty buffer."""
    with pytest.raises(PhashError):
        ImageContext(bytes_data=b"")


def test_context_reloading(image_path: str):
    """Verify that a single context can be reused for multiple images."""
    from PIL import Image
    import io

    with ImageContext(image_path) as ctx:
        h1 = ctx.phash

        # Create a completely different image in memory
        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")

        ctx.load_from_memory(buf.getvalue())
        h2 = ctx.phash
        assert h1 != h2


def test_concurrent_usage(image_path: str):
    """Basic thread-safety check (no segmentation faults)."""
    import threading

    def worker():
        for _ in range(10):
            with ImageContext(image_path) as ctx:
                _ = ctx.phash
                _ = ctx.ahash

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
