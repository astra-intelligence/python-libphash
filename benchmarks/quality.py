"""The quality benchmark: every contender on the corpus, under the site's edits.

For each photograph, every edit of the site at every strength is applied to it, and
each contender compares the edited image with the original (robustness); every pair of
distinct originals is compared too (discrimination). The originals are decoded once, by
Pillow, and saved losslessly, so that the reference an edit is compared with and the
image that is edited are the same pixels: libphash's site measures the same way.

From these values, :func:`summarize` gives each contender's separability as the site
defines it: d', the threshold that accepts 95 % of the copies (an original after one
moderate edit), and the share of different photographs that threshold also accepts.
Because d' and that share do not depend on the units of a metric, they compare a bit
hash with a correlation score.
"""

from __future__ import annotations

import concurrent.futures
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from .contenders import by_key, contenders
from .site import COPY_STRENGTHS, RECALL, separability, variants, write_edit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .contenders import Hasher


@dataclass
class EditValues:
    """One edit's comparisons for one contender: per strength, a value per image."""

    name: str
    group: str
    #: ``(strength, [value per image])``; a value is None where the library refused.
    points: list[tuple[float | str, list[float | None]]] = field(
        default_factory=list[tuple[float | str, list[float | None]]]
    )


@dataclass
class ContenderValues:
    """Every comparison of one contender over the corpus."""

    key: str
    library: str
    algorithm: str
    metric: str
    bits: int | None
    lower_is_closer: bool
    edits: list[EditValues]
    #: One value per pair of distinct originals, ``i < j`` in row order.
    different: list[float | None]


@dataclass
class QualityResult:
    """The quality benchmark's raw values."""

    images: int
    contenders: list[ContenderValues]


def _robustness(job: tuple[str, str, tuple[str, ...]]) -> dict[str, list[float | None]]:
    """Measure every edit of one original for the named contenders.

    Runs in a worker process. The original's lossless copy is written to ``reference``
    and kept for the comparison of pairs; each edited file is removed once every
    contender has hashed it.
    """
    path, reference, keys = job
    with Image.open(path) as image:
        base = image.convert("RGB")
    base.save(reference)
    stem = os.path.splitext(reference)[0]
    compare = {c.key: c.against(reference) for c in by_key(keys)}
    out: dict[str, list[float | None]] = {k: [] for k in keys}
    for i, v in enumerate(variants()):
        edited = write_edit(v.edit, base, f"{stem}-{i}")
        try:
            for key, against in compare.items():
                out[key].append(against(edited))
        finally:
            os.remove(edited)
    return out


def _pairs(job: tuple[str, tuple[str, ...]]) -> list[float | None]:
    key, references = job
    return by_key([key])[0].pairs(references)


def measure_quality(
    paths: Sequence[str],
    hashers: Sequence[Hasher] | None = None,
    *,
    workers: int | None = None,
) -> QualityResult:
    """Measure robustness and discrimination of ``hashers`` (all of them by default)."""
    chosen = list(hashers) if hashers is not None else contenders()
    keys = tuple(c.key for c in chosen)
    edits = variants()
    with (
        tempfile.TemporaryDirectory() as tmp,
        concurrent.futures.ProcessPoolExecutor(workers) as pool,
    ):
        references = tuple(str(Path(tmp, f"{i:04d}.ppm")) for i in range(len(paths)))
        jobs = [(p, r, keys) for p, r in zip(paths, references, strict=True)]
        per_image = list(pool.map(_robustness, jobs))
        different = list(pool.map(_pairs, [(k, references) for k in keys]))

    results: list[ContenderValues] = []
    for c, pairs in zip(chosen, different, strict=True):
        by_edit: dict[str, EditValues] = {}
        for i, v in enumerate(edits):
            values = by_edit.setdefault(v.name, EditValues(v.name, v.group))
            values.points.append((v.strength, [row[c.key][i] for row in per_image]))
        results.append(
            ContenderValues(
                c.key,
                c.library,
                c.algorithm,
                c.metric,
                c.bits,
                c.lower_is_closer,
                list(by_edit.values()),
                pairs,
            )
        )
    return QualityResult(len(paths), results)


@dataclass(frozen=True)
class Separability:
    """How well a contender tells copies from different photographs."""

    dprime: float
    #: The value that accepts :data:`~benchmarks.site.RECALL` of the copies.
    threshold: float
    #: The share of different pairs the threshold also accepts.
    false_accepts: float
    #: Per edit, the share of its variants (every strength) the threshold accepts.
    accepted: dict[str, float]
    #: Comparisons the library refused, left out of the numbers above.
    refused: int


def summarize(values: ContenderValues) -> Separability:
    """Return the separability of one contender's values, as the site computes it."""
    copies: list[float] = []
    refused = sum(v is None for v in values.different)
    for edit in values.edits:
        for strength, row in edit.points:
            refused += sum(v is None for v in row)
            if edit.group == "transform" and strength == COPY_STRENGTHS[edit.name]:
                copies += [v for v in row if v is not None]
    different = [v for v in values.different if v is not None]
    dprime, threshold, false_accepts = separability(
        copies, different, values.lower_is_closer, RECALL
    )

    def accepts(v: float) -> bool:
        return v <= threshold if values.lower_is_closer else v >= threshold

    accepted: dict[str, float] = {}
    for edit in values.edits:
        measured = [v for _, vs in edit.points for v in vs if v is not None]
        accepted[edit.name] = (
            sum(map(accepts, measured)) / len(measured) if measured else 0.0
        )
    return Separability(
        float(dprime), float(threshold), float(false_accepts), accepted, refused
    )
