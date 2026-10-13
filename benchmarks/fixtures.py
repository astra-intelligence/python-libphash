"""The images the benchmarks hash, and the environment they run in.

Two photographs of libphash's test data: ``photo.jpeg`` (400x400), on which the cost of
each call shows, and ``photo_large.jpeg`` (5472x3648, 20 megapixels), on which it
disappears into the C library's work. Their decoded pixels, which the pixel loads and
the C side read, are written once into a working directory. Nothing is fetched.
"""

from __future__ import annotations

import datetime
import os
import platform
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from functools import cached_property
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING

import libphash as ph

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    from .timing import Effort

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "native" / "libphash" / "tests" / "data"
SMALL = DATA / "photo.jpeg"
LARGE = DATA / "photo_large.jpeg"


@dataclass(frozen=True)
class Image:
    """One photograph: its file, its bytes and, on demand, its decoded pixels."""

    label: str
    path: Path
    workdir: Path

    @cached_property
    def data(self) -> bytes:
        """The encoded file."""
        return self.path.read_bytes()

    @cached_property
    def rgb(self) -> npt.NDArray[np.uint8]:
        """The pixels as a C-ordered (height, width, 3) array, decoded by Pillow."""
        import numpy as np  # noqa: PLC0415 -- optional, as in the binding
        from PIL import Image as PILImage  # noqa: PLC0415 -- optional

        with PILImage.open(self.path) as img:
            return np.ascontiguousarray(np.asarray(img.convert("RGB")))

    @cached_property
    def raw(self) -> Path:
        """A file of the packed RGB pixels, for the C side and the memory probes."""
        out = self.workdir / f"{self.path.stem}.rgb"
        if not out.exists():
            out.write_bytes(self.rgb.tobytes())
        return out

    @property
    def width(self) -> int:
        """The width in pixels."""
        return int(self.rgb.shape[1])

    @property
    def height(self) -> int:
        """The height in pixels."""
        return int(self.rgb.shape[0])


def images(effort: Effort, workdir: Path) -> list[Image]:
    """Return the photographs to measure: both, or the small one in the quick mode."""
    small = Image("400×400", SMALL, workdir)
    if effort.quick:
        return [small]
    return [small, Image("20 Mpx", LARGE, workdir)]


def _processor() -> str:
    if sys.platform == "darwin":
        out = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    elif sys.platform == "linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "not installed"


def gil_enabled() -> bool:
    """Return whether the GIL is on: False on a free-threaded build running without."""
    is_enabled = getattr(sys, "_is_gil_enabled", None)
    return bool(is_enabled()) if callable(is_enabled) else True


def environment(effort: Effort) -> dict[str, object]:
    """Return what a reader needs to compare a result with another."""
    import psutil  # noqa: PLC0415 -- a dev dependency, as numpy and Pillow

    threaded = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))
    python = f"{platform.python_implementation()} {platform.python_version()}"
    if threaded:
        python += f" free-threaded (GIL {'on' if gil_enabled() else 'off'})"
    return {
        "date": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "machine": f"{_processor()}, {os.cpu_count()} CPUs, "
        f"{psutil.virtual_memory().total / 2**30:.0f} GiB",
        "os": platform.platform(),
        "python": python,
        "python-libphash": ph.__version__,
        "build_info": ph.build_info(),
        "cffi": _version("cffi"),
        "numpy": _version("numpy"),
        "Pillow": _version("Pillow"),
        "effort": "quick (a check that every case runs; the times mean nothing)"
        if effort.quick
        else f"at least {effort.min_runs} runs and {effort.min_seconds:g} s per case, "
        "after one run to warm up",
    }
