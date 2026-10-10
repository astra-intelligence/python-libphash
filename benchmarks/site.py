"""What the benchmarks take from libphash's site, so that their numbers match its pages.

The photo corpus (a fixed commit of a copy of public-domain photographs, every file
checked against the SHA-256 its manifest names), the edits a picture goes through, the
strength of each edit that makes a copy, separability, and the name of the machine all
come from ``native/libphash/tools/site``, the code behind the site's figures. A change
there reaches the benchmarks with the next update of the submodule.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

ROOT = Path(__file__).resolve().parent.parent
SITE_TOOLS = ROOT / "native" / "libphash" / "tools" / "site"
sys.path.insert(0, str(SITE_TOOLS))

import fetch_corpus
from measure.separability import COPY_STRENGTHS, RECALL, separability
from measure.timing import machine
from measure.transforms import content_edits, transforms, write_edit

if TYPE_CHECKING:
    from measure.transforms import Edit

__all__ = [
    "COPY_STRENGTHS",
    "MIRROR_COMMIT",
    "RECALL",
    "CorpusError",
    "Variant",
    "machine",
    "photos",
    "separability",
    "variants",
    "write_edit",
]

#: The commit of the corpus's copy the photographs come from.
MIRROR_COMMIT = fetch_corpus.MIRROR_COMMIT


class CorpusError(RuntimeError):
    """The photo corpus is not available in full."""


def photos(cache: str | None = None) -> list[str]:
    """Return the paths of the corpus's photographs, downloading what the cache lacks.

    The cache is the site's (``~/.cache/libphash-site/photos`` unless ``cache`` names
    another). A benchmark is measured on the whole corpus or not at all: a photograph
    that cannot be downloaded, or whose bytes differ from the manifest, raises
    :class:`CorpusError`.
    """
    paths, problems = fetch_corpus.fetch(cache)
    if problems:
        listed = "\n  ".join(problems)
        raise CorpusError(f"{len(problems)} photographs are unavailable:\n  {listed}")
    return paths


@dataclass(frozen=True)
class Variant:
    """One edit at one strength, as the site applies it."""

    #: ``"transform"``: a copy's edit, which a hash should survive; ``"content"``: an
    #: edit that changes what the picture shows.
    group: Literal["transform", "content"]
    name: str
    strength: float | str
    edit: Edit


def variants() -> list[Variant]:
    """Return every edit of the site at every strength, transforms first."""
    out = [
        Variant("transform", name, strength, edit)
        for name, _, steps in transforms()
        for strength, edit in steps
    ]
    out += [
        Variant("content", name, strength, edit)
        for name, _, steps in content_edits()
        for strength, edit in steps
    ]
    return out
