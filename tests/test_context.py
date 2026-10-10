import copy
import gc
import pickle
import threading

import pytest

import libphash as ph
from conftest import data


def test_close_is_idempotent_and_use_after_close_raises(photo) -> None:
    ctx = ph.ImageContext()
    ctx.load_file(photo)
    ctx.close()
    ctx.close()
    assert ctx.closed
    for call in (ctx.phash, lambda: ctx.load_file(photo), lambda: ctx.width):
        with pytest.raises(ValueError, match="closed"):
            call()
    assert repr(ctx) == "<ImageContext closed>"


def test_context_manager(photo) -> None:
    with ph.ImageContext() as ctx:
        assert repr(ctx) == "<ImageContext empty>"
        ctx.load_file(photo)
        assert repr(ctx) == "<ImageContext 400x400x3>"
    assert ctx.closed


def test_unclosed_contexts_are_freed(photo) -> None:
    for _ in range(2000):
        ph.ImageContext().load_file(photo)
    gc.collect()


def test_cannot_pickle_or_copy() -> None:
    ctx = ph.ImageContext()
    for op in (pickle.dumps, copy.copy, copy.deepcopy):
        with pytest.raises(TypeError, match="Config"):
            op(ctx)


def test_dimensions_and_state(photo) -> None:
    with ph.ImageContext() as ctx:
        assert not ctx.is_loaded and (ctx.width, ctx.height, ctx.channels) == (0, 0, 0)
        ctx.load_file(photo)
        assert ctx.is_loaded and (ctx.width, ctx.height, ctx.channels) == (400, 400, 3)
    with ph.ImageContext(ph.Config(grayscale=True)) as ctx:
        ctx.load_file(photo)
        assert ctx.channels == 1


def test_failed_file_load_leaves_no_image(photo) -> None:
    with ph.ImageContext() as ctx:
        ctx.load_file(photo)
        with pytest.raises(ph.DecodeError):
            ctx.load_bytes(b"junk")
        assert not ctx.is_loaded
        with pytest.raises(ph.EmptyImageError):
            ctx.phash()


def test_failed_pixel_load_keeps_the_previous_image(photo) -> None:
    with ph.ImageContext(ph.Config(max_pixels=500 * 500)) as ctx:
        ctx.load_file(photo)
        before = ctx.phash()
        with pytest.raises(ph.ImageTooLargeError):
            ctx.load_pixels(memoryview(bytes(600 * 600)).cast("B", (600, 600)))
        assert ctx.phash() == before


def test_context_is_reusable_across_images(photo) -> None:
    other = data("photo.png")
    with ph.ImageContext() as ctx:
        ctx.load_file(photo)
        a = ctx.phash()
        ctx.load_file(other)
        assert ctx.phash() == ph.hash(other)
        ctx.load_file(photo)
        assert ctx.phash() == a


def test_one_context_shared_by_threads(photo) -> None:
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
        except BaseException as e:  # noqa: BLE001
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


def test_own_context_per_thread_matches_sequential(photo) -> None:
    paths = [
        photo,
        data("photo.png"),
        data("photo_rotated_90.jpeg"),
        data("photo_copy.jpeg"),
    ]
    expected = [ph.hash(p, "mhash") for p in paths]
    results: dict[int, list] = {}

    def work(i: int) -> None:
        with ph.ImageContext() as ctx:
            out = []
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
