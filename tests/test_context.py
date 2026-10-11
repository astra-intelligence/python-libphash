import copy
import gc
import pickle
import threading
from pathlib import Path
from typing import cast

import pytest
from conftest import data

import libphash as ph


def test_close_is_idempotent_and_use_after_close_raises(photo: Path) -> None:
    ctx = ph.ImageContext()
    ctx.load_file(photo)
    ctx.close()
    ctx.close()
    assert ctx.closed
    for call in (ctx.phash, lambda: ctx.load_file(photo), lambda: ctx.width):
        with pytest.raises(ValueError, match="closed"):
            call()
    assert repr(ctx) == "<ImageContext closed>"


def test_context_manager(photo: Path) -> None:
    with ph.ImageContext() as ctx:
        assert repr(ctx) == "<ImageContext empty>"
        ctx.load_file(photo)
        assert repr(ctx) == "<ImageContext 400x400x3>"
    assert ctx.closed


def test_unclosed_contexts_are_freed(photo: Path) -> None:
    for _ in range(2000):
        ph.ImageContext().load_file(photo)
    gc.collect()


def test_cannot_pickle_or_copy() -> None:
    ctx = ph.ImageContext()
    for op in (pickle.dumps, copy.copy, copy.deepcopy):
        with pytest.raises(TypeError, match="Config"):
            op(ctx)


def test_dimensions_and_state(photo: Path) -> None:
    with ph.ImageContext() as ctx:
        assert not ctx.is_loaded
        assert (ctx.width, ctx.height, ctx.channels) == (0, 0, 0)
        ctx.load_file(photo)
        assert ctx.is_loaded
        assert (ctx.width, ctx.height, ctx.channels) == (400, 400, 3)
    with ph.ImageContext(ph.Config(grayscale=True)) as ctx:
        ctx.load_file(photo)
        assert ctx.channels == 1


def test_failed_file_load_leaves_no_image(photo: Path) -> None:
    with ph.ImageContext() as ctx:
        ctx.load_file(photo)
        with pytest.raises(ph.DecodeError):
            ctx.load_bytes(b"junk")
        assert not ctx.is_loaded
        with pytest.raises(ph.EmptyImageError):
            ctx.phash()


def test_failed_pixel_load_keeps_the_previous_image(photo: Path) -> None:
    with ph.ImageContext(ph.Config(max_pixels=500 * 500)) as ctx:
        ctx.load_file(photo)
        before = ctx.phash()
        with pytest.raises(ph.ImageTooLargeError):
            ctx.load_pixels(memoryview(bytes(600 * 600)).cast("B", (600, 600)))
        assert ctx.phash() == before


def test_context_is_reusable_across_images(photo: Path) -> None:
    other = data("photo.png")
    with ph.ImageContext() as ctx:
        ctx.load_file(photo)
        a = ctx.phash()
        ctx.load_file(other)
        assert ctx.phash() == ph.hash(other)
        ctx.load_file(photo)
        assert ctx.phash() == a


def test_one_context_shared_by_threads(photo: Path) -> None:
    paths = [photo, data("photo.png"), data("photo_rotated_90.jpeg")]
    expected = {p: ph.hash(p, "radial") for p in paths}
    ctx = ph.ImageContext()
    errors: list[BaseException] = []

    def work(i: int) -> None:
        try:
            for j in range(30):
                p = paths[(i + j) % len(paths)]
                ctx.load_file(p)
                ctx.radial()  # must not crash, whichever image is loaded by then
        except BaseException as e:  # noqa: BLE001 -- reported by the main thread
            errors.append(e)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    ctx.load_file(photo)
    assert ctx.radial() == expected[photo]
    ctx.close()


def test_own_context_per_thread_matches_sequential(photo: Path) -> None:
    paths = [
        photo,
        data("photo.png"),
        data("photo_rotated_90.jpeg"),
        data("photo_copy.jpeg"),
    ]
    expected = [ph.hash(p, "mhash") for p in paths]
    results: dict[int, list[ph.Digest]] = {}

    def work(i: int) -> None:
        with ph.ImageContext() as ctx:
            out: list[ph.Digest] = []
            for p in paths * 5:
                ctx.load_file(p)
                out.append(ctx.mhash())
            results[i] = out

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for out in results.values():
        assert out == expected * 5


def test_close_while_other_threads_hash(photo: Path) -> None:
    # A thread that loses the race to close() gets ValueError, never a freed context.
    ctx = ph.ImageContext()
    ctx.load_file(photo)
    expected = ctx.phash()
    started = threading.Barrier(9)
    errors: list[BaseException] = []

    def work() -> None:
        started.wait()
        try:
            while True:
                assert ctx.phash() == expected
        except ValueError:
            pass
        except BaseException as e:  # noqa: BLE001 -- reported by the main thread
            errors.append(e)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    started.wait()
    ctx.close()
    for t in threads:
        t.join()
    assert errors == []


def test_config_property() -> None:
    config = ph.Config(phash_reduction_size=4)
    assert ph.ImageContext(config).config is config
    assert ph.ImageContext().config == ph.Config()
    with pytest.raises(TypeError, match="expected a Config, got dict"):
        ph.ImageContext(cast("ph.Config", {}))


def test_load_bytes_needs_a_buffer() -> None:
    with pytest.raises(TypeError, match="bytes-like encoded image data, got str"):
        ph.ImageContext().load_bytes(cast("bytes", "photo.jpeg"))


class _Reader:
    def __init__(self, data: object) -> None:
        self.data = data

    def read(self) -> bytes:
        return cast("bytes", self.data)


def test_load_fileobj_takes_what_read_returns(photo_bytes: bytes) -> None:
    expected = ph.hash(photo_bytes)
    for content in (photo_bytes, bytearray(photo_bytes), memoryview(photo_bytes)):
        with ph.ImageContext() as ctx:
            ctx.load_fileobj(_Reader(content))
            assert ctx.phash() == expected
    with pytest.raises(TypeError, match=r"_Reader.read\(\) returned str, not bytes"):
        ph.ImageContext().load_fileobj(_Reader("text"))


def test_hashes_of_digests_only(photo: Path) -> None:
    with ph.ImageContext() as ctx:
        ctx.load(photo)
        assert ctx.hashes("radial", "bmh") == {
            ph.Algorithm.RADIAL: ctx.radial(),
            ph.Algorithm.BMH: ctx.bmh(),
        }
