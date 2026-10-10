"""What a benchmark ran on: the machine, the Python, and every library's version."""

from __future__ import annotations

import datetime
import importlib.metadata
import platform
from dataclasses import dataclass
from typing import TYPE_CHECKING

import libphash as ph

from .site import machine

if TYPE_CHECKING:
    from measure.timing import Machine

#: The distributions whose versions decide the numbers.
PACKAGES = (
    "python-libphash",
    "imagehash",
    "opencv-contrib-python-headless",
    "pdqhash",
    "numpy",
    "Pillow",
)


@dataclass(frozen=True)
class Environment:
    """The machine and the software of one run."""

    machine: Machine
    python: str
    #: libphash's build_info(): version, decoders, threads, SIMD.
    libphash: str
    #: Installed version of each of PACKAGES; absent ones are left out.
    packages: dict[str, str]
    #: The commit of the photo corpus's copy, when the run used the corpus.
    corpus: str | None
    date: str


def _version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def environment(corpus: str | None) -> Environment:
    """Describe this machine and its software; ``corpus`` is the corpus's commit."""
    installed = {name: _version(name) for name in PACKAGES}
    packages = {name: v for name, v in installed.items() if v is not None}
    return Environment(
        machine(),
        f"{platform.python_implementation()} {platform.python_version()}",
        ph.build_info(),
        packages,
        corpus,
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
    )
