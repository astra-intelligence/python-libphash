"""The C reference of the parity tests: ``tests/c/reference.c``, built and run.

The reference is built against the libphash install that the extension links and given
the same jobs as the binding: an image, how it is loaded, and the settings. Each job
gives a line, every algorithm's hash or error code, and the binding's line must equal
the C one byte for byte.

It needs the libphash install of ``tools/native.py`` and CMake, which an editable build
has and an installed wheel has not; without them the tests that use it are skipped, and
with ``LIBPHASH_REQUIRE_C_REFERENCE=1`` (CI) they fail instead.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NoReturn

import pytest

import libphash as ph

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "native" / "libphash" / "tests" / "data"
sys.path.insert(0, str(ROOT / "tools"))
import native  # noqa: E402 -- tools/ joins sys.path just above

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

REQUIRE = "LIBPHASH_REQUIRE_C_REFERENCE"
DEFAULTS = {f.name: f.default for f in dataclasses.fields(ph.Config)}


@dataclass(frozen=True)
class Job:
    """One image, the way it is loaded, and the Config fields that differ from default.

    ``shape`` is (width, height, channels, stride) of the raw pixels a ``pixels`` job
    reads from ``path``.
    """

    source: Literal["file", "memory", "pixels"]
    path: Path
    settings: Mapping[str, object] = field(default_factory=dict[str, object])
    shape: tuple[int, int, int, int] | None = None

    def c_line(self) -> str:
        """Return the job as the reference reads it."""
        fields = [self.source, str(self.path)]
        if self.shape:
            fields += map(str, self.shape)
        return "\t".join(fields + c_settings(self.settings))

    def __str__(self) -> str:
        name = self.path.name if self.source == "pixels" else rel(self.path)
        extra = "".join(f" {k}={v!r}" for k, v in self.settings.items())
        return f"{self.source}:{name}{extra}"


def rel(path: Path) -> str:
    return path.relative_to(DATA).as_posix() if path.is_relative_to(DATA) else str(path)


# Config fields the C API sets together, under the name the reference reads.
GROUPS = {
    "phash": ("phash_dct_size", "phash_reduction_size"),
    "radial": ("radial_projections", "radial_samples", "radial_sigma"),
    "mhash": ("mhash_alpha", "mhash_level", "mhash_size"),
}


def c_value(value: object) -> str:
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, tuple):
        return ",".join(map(c_value, value))  # pyright: ignore[reportUnknownArgumentType]
    return str(value)


def c_settings(settings: Mapping[str, object]) -> list[str]:
    out: list[str] = []
    grouped = {name for names in GROUPS.values() for name in names}
    for key, names in GROUPS.items():
        if any(n in settings for n in names):
            values = [settings.get(n, DEFAULTS[n]) for n in names]
            out.append(f"{key}=" + ",".join(map(c_value, values)))
    out += (f"{k}={c_value(v)}" for k, v in settings.items() if k not in grouped)
    return out


# --- The C side ---------------------------------------------------------------------


def unavailable(reason: str) -> NoReturn:
    if os.environ.get(REQUIRE):
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


def build_reference() -> Path:
    prefix = native.build_dir() / "install"
    if next(prefix.glob("lib*/cmake/phash"), None) is None:
        unavailable(f"no libphash install in {prefix} for the C reference")
    cmake = shutil.which("cmake")
    if cmake is None:
        unavailable("the C reference needs CMake")
    out = native.build_dir() / "reference"
    if native.tools_missing(out):
        shutil.rmtree(out)
    commands: list[list[str]] = []
    if not (out / "CMakeCache.txt").exists():
        configure = [
            cmake,
            "-S",
            str(ROOT / "tests" / "c"),
            "-B",
            str(out),
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_PREFIX_PATH={prefix}",
            *native.generator(),
        ]
        archs = native.osx_architectures()
        if archs:
            configure.append(f"-DCMAKE_OSX_ARCHITECTURES={archs}")
        commands.append(configure)
    commands.append([cmake, "--build", str(out), "--config", "Release"])
    for command in commands:
        run = subprocess.run(command, capture_output=True, text=True, check=False)
        if run.returncode:
            pytest.fail(f"building the C reference failed:\n{run.stdout}{run.stderr}")
    for exe in (out / "reference", out / "Release" / "reference.exe"):
        if exe.exists():
            return exe
    pytest.fail(f"the C reference is not in {out}")


class Reference:
    """The built ``tests/c/reference.c``."""

    def __init__(self, exe: Path) -> None:
        self.exe = exe

    def lines(self, requests: Sequence[str]) -> list[str]:
        """Send the reference one request per line; return its line for each."""
        run = subprocess.run(
            [str(self.exe)],
            input="".join(f"{r}\n" for r in requests),
            capture_output=True,
            text=True,
            check=False,
        )
        assert run.returncode == 0, run.stderr
        lines = run.stdout.splitlines()
        assert len(lines) == len(requests), run.stderr
        return lines

    def run(self, jobs: Sequence[Job]) -> list[str]:
        """Return the reference's line for each job."""
        return self.lines([job.c_line() for job in jobs])


def start_reference() -> Reference:
    """Build the reference, or skip (fail under ``LIBPHASH_REQUIRE_C_REFERENCE``)."""
    ref = Reference(build_reference())
    # Both sides must link the same build: an install rebuilt with other options, or a
    # stale extension, would compare two libraries.
    assert ref.lines(["build_info"]) == [ph.build_info()]
    return ref


# --- The binding's side -------------------------------------------------------------


def load(ctx: ph.ImageContext, job: Job) -> None:
    if job.source == "file":
        ctx.load_file(job.path)
    elif job.source == "memory":
        ctx.load_bytes(job.path.read_bytes())
    else:
        assert job.shape
        width, height, channels, stride = job.shape
        raw = job.path.read_bytes()
        row = width * channels
        if stride in (0, row):
            ctx.load_pixels(memoryview(raw).cast("B", (height, width, channels)))
        else:
            np = pytest.importorskip("numpy")
            rows = np.frombuffer(raw, dtype=np.uint8).reshape(height, stride)
            # A view with the padding between rows: the binding passes the row step
            # to C as the stride.
            ctx.load_pixels(rows[:, :row].reshape(height, width, channels))


def render(value: int | ph.Digest) -> str:
    if isinstance(value, int):
        return f"{value:016x}"
    return f"{int(value.kind)}:{value.data.hex()}"


def binding_line(job: Job) -> str:
    try:
        cfg = ph.Config().replace(**job.settings)
    except ph.PhashError as e:
        return f"config {e.code}"
    with ph.ImageContext(cfg) as ctx:
        try:
            load(ctx, job)
        except ph.PhashError as e:
            return f"load {e.code}"
        fields: list[str] = []
        values: dict[ph.Algorithm, int | ph.Digest] = {}
        for algo in sorted(ph.Algorithm, key=int):
            try:
                values[algo] = ctx.hash(algo)
            except ph.PhashError as e:
                fields.append(f"!{e.code}")
            else:
                fields.append(render(values[algo]))
        # The batched path of a context: the 64-bit hashes share one ph_compute_multi.
        if values:
            assert ctx.hashes(*values) == values, job
        return " ".join(fields)


def check(reference: Reference, jobs: Sequence[Job]) -> None:
    """Require the binding's line of each job to equal the reference's."""
    expected = reference.run(jobs)
    differ = [
        f"{job}\n  C:      {c}\n  Python: {py}"
        for job, c in zip(jobs, expected, strict=True)
        if (py := binding_line(job)) != c
    ]
    assert not differ, "\n".join(differ)
