"""Fuzz targets of the binding: properties that hold for any input bytes.

libphash fuzzes its decoders itself, in C. These targets fuzz what the binding adds on
top: the buffers and strides it hands to C, the error mapping, the digest text form and
the comparisons. Each target takes raw bytes and draws its arguments from them, so a
corpus file means the same on every platform and Python; ``tools/fuzz.py`` runs the
targets under atheris, ``tests/test_fuzz_corpus.py`` replays the corpus with pytest.

A target fails by raising. A :class:`libphash.PhashError` is an answer, not a failure:
any input may be refused, but only with one of the documented errors.
"""

from __future__ import annotations

import importlib
import io
import math
from pathlib import Path
from typing import TYPE_CHECKING

import libphash as ph

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
#: The corpus of each target: hand-made seeds and the inputs fuzzing has found.
CORPUS = PROJECT_ROOT / "tests" / "fuzz"
#: libphash's seeds for its own decoder fuzzer: a file per format and EXIF case.
LIBPHASH_SEEDS = PROJECT_ROOT / "native" / "libphash" / "tests" / "fuzz" / "seeds"

#: A hash, or the name of the error that refused the input.
Outcome = int | ph.Digest | str


class Draw:
    """Arguments drawn from the front of the input, the rest left as payload."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def byte(self) -> int:
        """Return the next byte, 0 past the end."""
        if self._pos >= len(self._data):
            return 0
        self._pos += 1
        return self._data[self._pos - 1]

    def below(self, n: int) -> int:
        """Return a number in ``range(n)`` (n <= 256)."""
        return self.byte() % n

    def take(self, n: int) -> bytes:
        """Return up to ``n`` next bytes."""
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def rest(self) -> bytes:
        """Return every byte not drawn yet."""
        chunk = self._data[self._pos :]
        self._pos = len(self._data)
        return chunk


#: The algorithms that compare loaded pixels. mHash costs more than all the others
#: together and reads the same image: it would only slow the target down.
PIXEL_ALGORITHMS = tuple(a for a in ph.Algorithm if a != ph.Algorithm.MHASH)


def _outcomes(
    ctx: ph.ImageContext, algorithms: Iterable[ph.Algorithm]
) -> dict[ph.Algorithm, Outcome]:
    result: dict[ph.Algorithm, Outcome] = {}
    for algo in algorithms:
        try:
            result[algo] = ctx.hash(algo)
        except ph.PhashError as e:
            result[algo] = type(e).__name__
    return result


def _pixels_loader(
    source: ph.PixelArray, order: ph.ChannelOrder = "rgb"
) -> Callable[[ph.ImageContext], None]:
    return lambda ctx: ctx.load_pixels(source, order)


def _load_outcomes(load: Callable[[ph.ImageContext], None]) -> dict[str, Outcome]:
    with ph.ImageContext() as ctx:
        try:
            load(ctx)
        except ph.PhashError as e:
            return {"load": type(e).__name__}
        return {str(a): v for a, v in _outcomes(ctx, PIXEL_ALGORITHMS).items()}


#: libphash's own fuzzer caps images at 4 megapixels too: a file of a few bytes may
#: rightly ask for the default 256, more memory than a fuzzer is given.
LOAD_CONFIG = ph.Config(max_pixels=4 * 1024 * 1024)


def _decode(load: Callable[[ph.ImageContext], None]) -> str | tuple[int, int, int]:
    with ph.ImageContext(LOAD_CONFIG) as ctx:
        try:
            load(ctx)
        except ph.PhashError as e:
            return type(e).__name__
        _outcomes(ctx, ph.Algorithm)
        return ctx.width, ctx.height, ctx.channels


def load(data: bytes) -> None:
    """Check that encoded bytes load alike from memory and from a file, and hash.

    Every hash of a loaded image runs, and only a :class:`libphash.PhashError` may
    refuse it. The hashes of the two loads are not compared: libphash 2.0.1 decodes TGA
    with stb_image, which leaves the rows past the end of a truncated file
    uninitialized, so that such a file hashes differently from load to load.
    """
    from_bytes = _decode(lambda ctx: ctx.load_bytes(data))
    from_file = _decode(lambda ctx: ctx.load_fileobj(io.BytesIO(data)))
    assert from_bytes == from_file, (from_bytes, from_file)


def pixels(data: bytes) -> None:
    """Check that a view of pixels hashes as its C-ordered copy, whatever its layout.

    The view is a crop of a larger array, with a row and a column step, gaps between
    channels, reversed rows or swapped axes: the layouts the binding passes to C without
    a copy (row gaps) and those it copies (anything else). It is loaded as an array and
    as a memoryview, in RGB or BGR order, and each must hash like the contiguous array
    in RGB order with the channels already swapped.
    """
    # numpy is optional, as in the tests; only this target needs it.
    np = importlib.import_module("numpy")

    draw = Draw(data)
    height, width = draw.below(25), draw.below(25)
    channels = (0, 1, 3, 4)[draw.below(4)]
    row_step, col_step = 1 + draw.below(3), 1 + draw.below(3)
    top, left = draw.below(4), draw.below(4)
    flags = draw.byte()
    bgr = channels >= 3 and bool(flags & 1)

    # Gaps between the channels of a pixel: every other channel of a wider array.
    channel_step = 2 if channels and flags & 8 else 1
    rows, cols = top + height * row_step + draw.below(4), left + width * col_step
    shape = (rows, cols) if channels == 0 else (rows, cols, channels * channel_step)
    size = math.prod(shape)
    payload = draw.rest() or b"\0"
    filled = (payload * (size // len(payload) + 1))[:size]
    view = np.frombuffer(filled, dtype=np.uint8).reshape(shape)
    view = view[top : top + height * row_step : row_step, left::col_step][:, :width]
    if channel_step > 1:
        view = view[..., ::channel_step]
    if flags & 2:
        view = view[::-1]
    if flags & 4:
        view = view.swapaxes(0, 1)

    order: ph.ChannelOrder = "bgr" if bgr else "rgb"
    reference = np.ascontiguousarray(view)
    if bgr:
        swap = [2, 1, 0, 3][:channels]
        reference = np.ascontiguousarray(reference[..., swap])
    expected = _load_outcomes(_pixels_loader(reference))
    sources: tuple[ph.PixelArray, ...] = (view, memoryview(view))
    for source in sources:
        got = _load_outcomes(_pixels_loader(source, order))
        assert got == expected, (type(source).__name__, view.strides, got, expected)


_COMPARISONS = (
    "hamming_distance",
    "l2_distance",
    "histogram_intersection",
    "radial_similarity",
    "similarity",
)
#: The range of each comparison's result, from the docstrings.
_RANGES: dict[str, tuple[float, float]] = {
    "histogram_intersection": (0.0, 1.0),
    "radial_similarity": (-1.0, 1.0),
    "l2_distance": (0.0, math.inf),
}


def _digest(draw: Draw) -> ph.Digest | None:
    size = 1 + draw.below(ph.PH_DIGEST_MAX_BYTES + 2)
    kind = draw.below(8) - 1
    try:
        return ph.Digest(draw.take(size), kind)
    except ph.InvalidArgumentError:
        return None


def _check_round_trip(d: ph.Digest) -> None:
    assert ph.Digest.from_hex(d.hex()) == d, d
    assert ph.Digest(bytes(d), d.kind) == d, d


def _check_comparisons(a: ph.Digest, b: ph.Digest) -> None:
    for name in _COMPARISONS:
        try:
            value = getattr(a, name)(b)
        except ph.PhashError:
            continue
        if name == "hamming_distance":
            assert 0 <= value <= 8 * len(a), (name, value, a, b)
            continue
        if name == "similarity":
            kind = a.kind if a.kind != ph.DigestKind.UNSPECIFIED else b.kind
            low, high = (-1.0, 1.0) if kind == ph.DigestKind.COEFFICIENTS else (0, 1)
        else:
            low, high = _RANGES[name]
        assert low <= value <= high, (name, value, a, b)


def digest(data: bytes) -> None:
    """Check that digests from any bytes or text round-trip and compare within range."""
    draw = Draw(data)
    mode = draw.below(3)
    if mode == 0:
        text = draw.rest().decode("latin-1")
        try:
            parsed = ph.Digest.from_hex(text)
        except ph.PhashError:
            return
        _check_round_trip(parsed)
        return
    if mode == 1:
        text = draw.rest().decode("latin-1")
        try:
            value = ph.hash_from_hex(text)
        except ph.PhashError:
            return
        assert 0 <= value < 2**64, value
        assert ph.hash_from_hex(ph.hash_to_hex(value)) == value, value
        return
    a, b = _digest(draw), _digest(draw)
    for d in (a, b):
        if d is not None:
            _check_round_trip(d)
    if a is not None and b is not None:
        _check_comparisons(a, b)


TARGETS: dict[str, Callable[[bytes], None]] = {
    "load": load,
    "pixels": pixels,
    "digest": digest,
}


def seed_dirs(target: str) -> list[Path]:
    """Return the directories of a target's corpus."""
    return [CORPUS / target] + ([LIBPHASH_SEEDS] if target == "load" else [])
