"""The binding across processes: spawn, forkserver and fork.

What crosses a process boundary is pickled: a path, a Config, a Digest and an error do,
and an ImageContext refuses to. A context or a batch pool created before a fork keeps
working in the child, because libphash holds no global state and a batch starts its
threads for each call.
"""

from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import TYPE_CHECKING

import pytest
from conftest import data

import libphash as ph

if TYPE_CHECKING:
    from multiprocessing.connection import Connection
    from pathlib import Path

START_METHODS = [
    m
    for m in ("spawn", "forkserver", "fork")
    if m in multiprocessing.get_all_start_methods()
]


def images() -> list[Path]:
    return [data(n) for n in ("photo.jpeg", "photo.png", "photo_rotated_90.jpeg")]


@pytest.mark.parametrize("method", START_METHODS)
def test_hashes_in_worker_processes(method: str) -> None:
    config = ph.Config(grayscale=True, phash_reduction_size=6)
    paths = images()
    expected = [ph.hash(p, "mhash", config=config) for p in paths]
    context = multiprocessing.get_context(method)
    with ProcessPoolExecutor(2, mp_context=context) as pool:
        digests = list(pool.map(ph.hash, paths, ["mhash"] * len(paths), chunksize=1))
        assert digests == [ph.hash(p, "mhash") for p in paths]
        configured = [pool.submit(ph.hash, p, "mhash", config=config) for p in paths]
        assert [f.result() for f in configured] == expected
        batch = pool.submit(ph.hash_files, paths, threads=2).result()
        assert [r.hashes for r in batch] == [r.hashes for r in ph.hash_files(paths)]
        with pytest.raises(ph.CorruptDataError) as exc:
            pool.submit(ph.hash, data("corrupted.jpg")).result()
        assert exc.value.code_name == "PH_ERR_CORRUPT_DATA"


def use_inherited(ctx: ph.ImageContext, paths: list[Path], conn: Connection) -> None:
    # The child's copy of the context, loaded before the fork; then a batch, whose
    # threads start in the child.
    conn.send((ctx.phash(), [r.hashes for r in ph.hash_files(paths, threads=3)]))
    conn.close()


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(), reason="no fork on Windows"
)
def test_context_loaded_before_a_fork_works_in_the_child() -> None:
    paths = images()
    ph.hash_files(paths, threads=3)  # a pool has run in the parent before the fork
    with ph.ImageContext() as ctx:
        ctx.load_file(paths[0])
        context = multiprocessing.get_context("fork")
        receive, send = context.Pipe(duplex=False)
        child = context.Process(target=use_inherited, args=(ctx, paths, send))
        child.start()
        send.close()
        result = receive.recv()
        child.join(timeout=60)
        assert child.exitcode == 0
        assert result == (ctx.phash(), [r.hashes for r in ph.hash_files(paths)])


def test_a_context_does_not_cross_processes() -> None:
    context = multiprocessing.get_context("spawn")
    with (
        ph.ImageContext() as ctx,
        ProcessPoolExecutor(1, mp_context=context) as pool,
        pytest.raises(TypeError, match="Config"),
    ):
        pool.submit(ctx.phash).result()
