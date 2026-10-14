"""What one call costs: the C library, the same call through cffi, the binding's API.

Each piece of work is timed three ways on the same image and the same build: in C
(``benchmarks/c/bench.c``), as the bare C call through cffi that the API makes, and
through the binding's API. The first difference is the price of cffi, the second that of
the binding itself (argument checks, the context's lock, building the result). The other
rows of a table are other ways of doing the same job from Python.
"""

from __future__ import annotations

import functools
import io
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image as PILImage

import libphash as ph
from libphash._native import ffi, lib

from .fixtures import DATA, Image
from .report import Block
from .timing import measure

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from libphash._native import ph_context_t_ptr

    from .cbench import CBench
    from .report import Table
    from .timing import Effort, Timing

C = "C"
CFFI = "C through cffi"
ALGORITHMS = list(ph.Algorithm)
UINT64 = [
    ph.Algorithm.AHASH,
    ph.Algorithm.DHASH,
    ph.Algorithm.PHASH,
    ph.Algorithm.WHASH,
]
#: What ImageContext.hash() calls for a 64-bit algorithm; digests go through
#: ph_compute_digest().
_UINT64_COMPUTE = {
    ph.Algorithm.AHASH: lib.ph_compute_ahash,
    ph.Algorithm.DHASH: lib.ph_compute_dhash,
    ph.Algorithm.PHASH: lib.ph_compute_phash,
    ph.Algorithm.WHASH: lib.ph_compute_whash,
}


def raw_context() -> ph_context_t_ptr:
    """Return a bare ``ph_context_t *``, freed by the garbage collector."""
    out = ffi.new("ph_context_t **")
    if lib.ph_create(out) != lib.PH_SUCCESS:
        raise MemoryError("ph_create() failed")
    return ffi.gc(out[0], lib.ph_free)


def _cffi_hash(raw: ph_context_t_ptr, algo: ph.Algorithm) -> Callable[[], object]:
    compute = _UINT64_COMPUTE.get(algo)
    if compute is not None:
        out = ffi.new("uint64_t *")
        return lambda: compute(raw, out)
    digest = ffi.new("ph_digest_t *")
    return lambda: lib.ph_compute_digest(raw, int(algo), digest)


def run(images: list[Image], cbench: CBench, effort: Effort) -> Block:
    """Measure every table of the block."""
    block = Block("overhead", "1. What a call costs: C, cffi and the binding")
    if cbench.exe is None:
        block.notes.append(f"The C rows are empty: {cbench.reason}.")
    _loads(block, images, cbench, effort)
    _hashes(block, images, cbench, effort)
    _multi(block, images, cbench, effort)
    _whole(block, images, cbench, effort)
    _digests(block, cbench, effort)
    return block


def _timed(
    cbench: CBench,
    effort: Effort,
    c_case: list[object] | None,
    cases: list[tuple[str, Callable[[], object]]],
    items: float = 1,
) -> list[tuple[str, Timing | None]]:
    out: list[tuple[str, Timing | None]] = []
    if c_case is not None:
        out.append((C, cbench.time([c_case], effort)[0]))
    out += [(how, measure(work, items, effort)) for how, work in cases]
    return out


def _loads(block: Block, images: list[Image], cbench: CBench, effort: Effort) -> None:
    files = block.table(
        "load_file",
        "Loading a file",
        "A JPEG file into a context that is kept from load to load.",
        "s",
        baseline_row=C,
    )
    encoded = block.table(
        "load_bytes",
        "Loading encoded bytes",
        "The same JPEG already in memory, in the forms a program holds it.",
        "s",
        baseline_row=C,
    )
    pixels = block.table(
        "load_pixels",
        "Loading decoded pixels",
        "The same image decoded (by Pillow, untimed) into 8-bit RGB pixels, in the "
        "forms numpy, OpenCV and Pillow hand them over.",
        "s",
        baseline_row=C,
    )
    for img in images:
        raw = raw_context()
        ctx = ph.ImageContext()
        path, spath, data = img.path, str(img.path), img.data
        bpath = spath.encode()
        for how, t in _timed(
            cbench,
            effort,
            ["load_file", spath],
            [
                (CFFI, lambda: lib.ph_load_from_file(raw, bpath)),
                ("load_file(str)", lambda: ctx.load_file(spath)),
                ("load_file(Path)", lambda: ctx.load_file(path)),
                ("load(str)", lambda: ctx.load(spath)),
            ],
        ):
            files.add(how, img.label, t)

        buf = ffi.from_buffer("const uint8_t[]", data)
        array = bytearray(data)
        view = memoryview(data)

        def from_file() -> None:
            with path.open("rb") as f:
                ctx.load_fileobj(f)

        for how, t in _timed(
            cbench,
            effort,
            ["load_memory", spath],
            [
                (CFFI, lambda: lib.ph_load_from_memory(raw, buf, len(data))),
                ("load_bytes(bytes)", lambda: ctx.load_bytes(data)),
                ("load_bytes(bytearray)", lambda: ctx.load_bytes(array)),
                ("load_bytes(memoryview)", lambda: ctx.load_bytes(view)),
                ("load(bytes)", lambda: ctx.load(data)),
                ("load_fileobj(BytesIO)", lambda: ctx.load_fileobj(io.BytesIO(data))),
                ("load_fileobj(open file), open included", from_file),
                ("hash_buffers([bytes]), per item", lambda: ph.hash_buffers([data])),
            ],
        ):
            encoded.add(how, img.label, t)

        _pixel_loads(pixels, img, cbench, effort)


def _pixel_loads(table: Table, img: Image, cbench: CBench, effort: Effort) -> None:
    rgb = img.rgb
    height, width = rgb.shape[:2]
    raw = raw_context()
    pointer = ffi.cast("const uint8_t *", rgb.ctypes.data)
    ctx = ph.ImageContext()
    framed = np.zeros((height + 20, width + 20, 3), np.uint8)
    framed[10:-10, 10:-10] = rgb
    crop = framed[10:-10, 10:-10]  # rows spaced apart: passed with a stride
    bgr = np.ascontiguousarray(rgb[..., ::-1])  # what OpenCV hands over
    packed = rgb.tobytes()
    view = memoryview(packed).cast("B", (height, width, 3))
    pil = PILImage.fromarray(rgb)
    gray = np.ascontiguousarray(rgb[..., 1])
    for how, t in _timed(
        cbench,
        effort,
        ["load_pixels", img.raw, width, height, 3],
        [
            (CFFI, lambda: lib.ph_load_from_pixels(raw, pointer, width, height, 3, 0)),
            ("numpy, contiguous (no copy)", lambda: ctx.load_pixels(rgb)),
            ("numpy, a crop: rows apart (no copy)", lambda: ctx.load_pixels(crop)),
            ("memoryview with a shape (no copy)", lambda: ctx.load_pixels(view)),
            (
                "numpy BGR, channel_order='bgr' (a copy)",
                lambda: ctx.load_pixels(bgr, "bgr"),
            ),
            (
                "numpy BGR, bgr[..., ::-1] (a copy)",
                lambda: ctx.load_pixels(bgr[..., ::-1]),
            ),
            (
                "numpy BGR, np.ascontiguousarray(bgr[..., ::-1])",
                lambda: ctx.load_pixels(np.ascontiguousarray(bgr[..., ::-1])),
            ),
            ("numpy, one channel (h, w)", lambda: ctx.load_pixels(gray)),
            ("Pillow RGB image, load_pil()", lambda: ctx.load_pil(pil)),
            (
                "Pillow RGB image, np.asarray() then load_pixels()",
                lambda: ctx.load_pixels(np.asarray(pil)),
            ),
        ],
    ):
        table.add(how, img.label, t)


def _hashes(block: Block, images: list[Image], cbench: CBench, effort: Effort) -> None:
    for img in images:
        cached = block.table(
            f"hash_loaded_{img.path.stem}",
            f"One hash of a loaded image, {img.label}",
            "Each hash computed again on an image that a first hash prepared: the "
            "grayscale image and the area grid are cached in the context, so the "
            "64-bit hashes cost little more than the call itself.",
            "s",
            baseline_column=C,
        )
        first = block.table(
            f"load_hash_{img.path.stem}",
            f"Loading and one hash, {img.label}",
            "A load of the encoded bytes and the first hash on it, which prepares the "
            "grayscale image and the area grid: what one image and one hash cost.",
            "s",
            baseline_column=C,
        )
        raw = raw_context()
        data = img.data
        lib.ph_load_from_memory(
            raw, ffi.from_buffer("const uint8_t[]", data), len(data)
        )
        ctx = ph.ImageContext()
        ctx.load_bytes(data)
        spath = str(img.path)
        c_cached = cbench.time([["hash", int(a), spath] for a in ALGORITHMS], effort)
        c_first = cbench.time(
            [["load_hash", int(a), spath] for a in ALGORITHMS], effort
        )
        for algo, c_c, c_f in zip(ALGORITHMS, c_cached, c_first, strict=True):
            name = str(algo)
            cached.add(name, C, c_c)
            cached.add(name, CFFI, measure(_cffi_hash(raw, algo), 1, effort))
            cached.add(
                name, "hash(Algorithm)", measure(lambda: ctx.hash(algo), 1, effort)
            )
            cached.add(name, "hash('name')", measure(lambda: ctx.hash(name), 1, effort))
            cached.add(
                name, "its method, ahash() …", measure(getattr(ctx, name), 1, effort)
            )

            def load_hash(a: ph.Algorithm = algo) -> None:
                ctx.load_bytes(data)
                ctx.hash(a)

            first.add(name, C, c_f)
            first.add(name, "load_bytes() + hash()", measure(load_hash, 1, effort))


def _multi(block: Block, images: list[Image], cbench: CBench, effort: Effort) -> None:
    table = block.table(
        "multi",
        "Several hashes of one load",
        "A load of the encoded bytes and the four 64-bit hashes (or all nine). "
        "hashes() computes the 64-bit ones in one ph_compute_multi() call, which "
        "shares their work on the full image.",
        "s",
        baseline_row="C: ph_compute_multi()",
    )
    for img in images:
        data, spath = img.data, str(img.path)
        ctx = ph.ImageContext()
        c_multi, c_separate = cbench.time(
            [["load_multi", spath], ["load_separate", spath]], effort
        )

        def hashes(algos: list[ph.Algorithm]) -> Callable[[], object]:
            def work() -> None:
                ctx.load_bytes(data)
                ctx.hashes(*algos)

            return work

        def separate(algos: list[ph.Algorithm]) -> Callable[[], object]:
            def work() -> None:
                ctx.load_bytes(data)
                for a in algos:
                    ctx.hash(a)

            return work

        table.add("C: ph_compute_multi()", img.label, c_multi)
        table.add("C: four ph_compute_*()", img.label, c_separate)
        table.add("hashes(4 × 64-bit)", img.label, measure(hashes(UINT64), 1, effort))
        table.add("hash() four times", img.label, measure(separate(UINT64), 1, effort))
        table.add("hashes(all 9)", img.label, measure(hashes(ALGORITHMS), 1, effort))
        table.add(
            "hash() nine times", img.label, measure(separate(ALGORITHMS), 1, effort)
        )
        table.add(
            "hash(path) four times, a load each",
            img.label,
            measure(lambda: [ph.hash(spath, a) for a in UINT64], 1, effort),
        )


def _whole(block: Block, images: list[Image], cbench: CBench, effort: Effort) -> None:
    table = block.table(
        "file_to_hash",
        "From a file to its pHash",
        "Per image: a new context for each, one context kept, or a batch on one thread "
        "(threads=1, the calling thread) of 64 copies of the file.",
        "s",
        baseline_row="C: a new context",
    )
    batch = 64
    phash = int(ph.Algorithm.PHASH)
    for img in images:
        spath = str(img.path)
        paths = [spath] * batch
        n = effort.scale(batch, 4)
        c_fresh, c_reused, c_batch = cbench.time(
            [
                ["fresh", phash, spath],
                ["reused", phash, spath],
                ["batch_files", spath, n, 1],
            ],
            effort,
        )
        ctx = ph.ImageContext()

        def reused() -> None:
            ctx.load_file(spath)
            ctx.phash()

        table.add("C: a new context", img.label, c_fresh)
        table.add("C: one context", img.label, c_reused)
        table.add("C: ph_hash_files(), 1 thread", img.label, c_batch)
        table.add(
            "hash(path): a new context",
            img.label,
            measure(lambda: ph.hash(spath), 1, effort),
        )
        table.add("ImageContext, kept", img.label, measure(reused, 1, effort))
        table.add(
            "hash_files(threads=1)",
            img.label,
            measure(lambda: ph.hash_files(paths[:n], threads=1), n, effort),
        )


def _digest(path: Path, algo: ph.Algorithm) -> ph.Digest:
    with ph.ImageContext() as ctx:
        ctx.load_file(path)
        value = ctx.hash(algo)
    if not isinstance(value, ph.Digest):
        raise TypeError(f"{algo} gives no digest")
    return value


def _digests(block: Block, cbench: CBench, effort: Effort) -> None:
    table = block.table(
        "compare",
        "Comparing two hashes",
        "One comparison of two hashes of two similar photographs (photo.jpeg and "
        "photo_copy.jpeg), and the conversions of a hash.",
        "s",
    )
    a_path, b_path = DATA / "photo.jpeg", DATA / "photo_copy.jpeg"
    rows: list[tuple[str, ph.Algorithm | None, str, Callable[[], object] | None]] = []
    ha, hb = ph.hash(a_path), ph.hash(b_path)
    rows += [
        ("64-bit Hamming: C ph_hamming_distance()", None, "hamming", None),
        ("64-bit Hamming: cffi", None, "", lambda: lib.ph_hamming_distance(ha, hb)),
        (
            "64-bit Hamming: hamming_distance()",
            None,
            "",
            lambda: ph.hamming_distance(ha, hb),
        ),
        (
            "64-bit Hamming: (a ^ b).bit_count()",
            None,
            "",
            lambda: (ha ^ hb).bit_count(),  # noqa: PLW0108 -- the XOR is timed too
        ),
        ("64-bit similarity()", None, "", lambda: ph.similarity(ha, hb)),
    ]
    metrics = [
        ("Hamming", ph.Algorithm.BMH, "hamming", ph.Digest.hamming_distance),
        ("L2", ph.Algorithm.COLOR_MOMENTS, "l2", ph.Digest.l2_distance),
        ("radial", ph.Algorithm.RADIAL, "radial", ph.Digest.radial_similarity),
        (
            "histogram",
            ph.Algorithm.COLOR_HASH,
            "histogram",
            ph.Digest.histogram_intersection,
        ),
        ("similarity", ph.Algorithm.BMH, "similarity", ph.Digest.similarity),
    ]
    for label, algo, metric, method in metrics:
        da, db = _digest(a_path, algo), _digest(b_path, algo)
        rows.append((f"{algo} {label}: C", algo, metric, None))
        rows.append(
            (f"{algo} {label}: Digest", algo, "", functools.partial(method, da, db))
        )
    digest = _digest(a_path, ph.Algorithm.MHASH)
    text = digest.hex()
    rows += [
        (
            "Digest(bytes, kind), 72 bytes",
            None,
            "",
            lambda: ph.Digest(digest.data, ph.DigestKind.BITS),
        ),
        ("Digest.hex(), 72 bytes", None, "", digest.hex),
        ("Digest.from_hex(), 72 bytes", None, "", lambda: ph.Digest.from_hex(text)),
        ("hash_to_hex(int)", None, "", lambda: ph.hash_to_hex(ha)),
        ("f'{h:016x}'", None, "", lambda: f"{ha:016x}"),
    ]
    c_cases: list[list[object]] = []
    for _, of, metric, work in rows:
        if work is None:
            if of is None:
                c_cases.append(["hamming", 10_000])
            else:
                c_cases.append(["metric", metric, int(of), a_path, b_path])
    c_times = iter(cbench.time(c_cases, effort))
    for label, _, _, work in rows:
        table.add(
            label,
            "per call",
            next(c_times) if work is None else measure(work, 1, effort),
        )
