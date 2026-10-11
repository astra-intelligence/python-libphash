"""The binding computes what libphash computes, compared with libphash called from C.

``tests/c/reference.c`` is built against the libphash install that the extension links
and given the same jobs as the binding: an image, how it is loaded, and the settings.
Each job gives a line, every algorithm's hash or error code, and the binding's line must
equal the C one byte for byte. The golden files pin the values of a handful of photos;
these tests reach every fixture of libphash, every setting at the ends of its range,
and the errors, so a setting passed to the wrong setter, a value narrowed differently
from C, a load path that decodes differently or an error code mapped wrongly shows up
as a difference.

The reference needs the libphash install of ``tools/native.py`` and CMake, which an
editable build has and an installed wheel has not; without them the tests are skipped,
and with ``LIBPHASH_REQUIRE_C_REFERENCE=1`` (CI) they fail instead.
"""

from __future__ import annotations

import dataclasses
import os
import random
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NoReturn

import pytest
from conftest import DATA

import libphash as ph

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import native  # noqa: E402 -- tools/ joins sys.path just above

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

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


@pytest.fixture(scope="session")
def reference() -> Reference:
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
    expected = reference.run(jobs)
    differ = [
        f"{job}\n  C:      {c}\n  Python: {py}"
        for job, c in zip(jobs, expected, strict=True)
        if (py := binding_line(job)) != c
    ]
    assert not differ, "\n".join(differ)


# --- Fixtures -----------------------------------------------------------------------


def fixtures() -> list[Path]:
    return sorted(p for p in DATA.rglob("*") if p.is_file() and p.suffix != ".txt")


def require_fixtures() -> list[Path]:
    paths = fixtures()
    if not paths:
        pytest.skip("fixtures are missing (native/libphash not checked out?)")
    return paths


@pytest.mark.parametrize("source", ["file", "memory"])
def test_every_fixture(reference: Reference, source: Literal["file", "memory"]) -> None:
    # Broken files included: the error code is part of the result.
    check(reference, [Job(source, p) for p in require_fixtures()])


@pytest.mark.parametrize("source", ["file", "memory"])
def test_jpeg_fixtures_at_every_decode_scale(
    reference: Reference, source: Literal["file", "memory"]
) -> None:
    jpegs = [p for p in require_fixtures() if p.suffix in (".jpg", ".jpeg")]
    check(
        reference,
        [
            Job(source, p, {"decode_scale": s}, None)
            for p in jpegs
            if p.name != "photo_large.jpeg"
            for s in (2, 4, 8)
        ],
    )


# Each field at the ends of its range and just past them, and a value inside. Values
# past the range check that the binding refuses what C refuses, with C's code.
SETTINGS: list[Mapping[str, object]] = [
    *({"gamma": v} for v in (0.001, 0.0011, 0.45, 2.2, 1000.0, 1000.0001)),
    *(
        {"gray_weights": v}
        for v in (
            (1, 0, 0),
            (0, 1, 0),
            (0, 0, 1),
            (299, 587, 114),
            (8421504, 0, 0),
            (8421505, 0, 0),
            (0, 0, 0),
            (-1, 1, 1),
        )
    ),
    *(
        {"phash_dct_size": d, "phash_reduction_size": r}
        for d, r in (
            *((4, 4), (8, 8), (16, 6), (32, 4)),
            *((7, 8), (33, 8), (32, 3), (32, 9)),
        )
    ),
    *({"radial_projections": v} for v in (39, 40, 4096, 4097)),
    *({"radial_samples": v} for v in (1, 2, 4096, 4097)),
    *({"radial_sigma": v} for v in (0.0, 0.01, 64 / 3, 21.34)),
    *({"bmh_block_size": v} for v in (1, 2, 7, 32, 33)),
    *({"mhash_alpha": v} for v in (1.0, 1.0001, 3.0)),
    *({"mhash_level": v} for v in (-0.5, 0.0, 2.5)),
    {"mhash_alpha": 4.0, "mhash_level": 3.0},
    *({"mhash_size": v} for v in (61, 62, 1000, 4096, 4097)),
    {"whash_mode": "full"},
    {"whash_remove_max_haar_ll": True},
    {"whash_mode": "full", "whash_remove_max_haar_ll": True},
    {"grayscale": True},
    {"grayscale": True, "alpha_mode": "white"},
    *({"alpha_mode": v} for v in ("white", "black", "ignore")),
    {"auto_orient": False},
    *({"max_pixels": v} for v in (0, 1, 4096, 2**64 - 1)),
]
SETTINGS_FIXTURES = ["photo.jpeg", "png/rgba8.png", "photo_rotated_90.jpeg"]


def test_every_setting(reference: Reference) -> None:
    require_fixtures()
    check(
        reference,
        [Job("file", DATA / f, s) for f in SETTINGS_FIXTURES for s in SETTINGS],
    )


# --- Pixels -------------------------------------------------------------------------


def pixel_shapes() -> Iterator[tuple[int, int, int, int]]:
    """(width, height, channels, stride): degenerate sizes, odd sizes, padded rows."""
    for channels in (1, 3, 4):
        for width, height in ((1, 1), (2, 3), (7, 5), (64, 48), (301, 199)):
            row = width * channels
            yield width, height, channels, 0
            yield width, height, channels, row + 13


@pytest.fixture(scope="module")
def pixel_jobs(tmp_path_factory: pytest.TempPathFactory) -> list[Job]:
    directory = tmp_path_factory.mktemp("pixels")
    rng = random.Random(20261011)
    jobs: list[Job] = []
    for width, height, channels, stride in pixel_shapes():
        size = (stride or width * channels) * height
        # Noise, and a gradient that the hashes see as an image rather than as noise.
        noise = rng.randbytes(size)
        gradient = bytes((i * 7 + i // 97) % 256 for i in range(size))
        for kind, raw in (("noise", noise), ("gradient", gradient)):
            path = directory / f"{kind}-{width}x{height}x{channels}-{stride}.raw"
            path.write_bytes(raw)
            shape = (width, height, channels, stride)
            jobs.append(Job("pixels", path, {}, shape))
            if channels == 4:
                jobs.extend(
                    Job("pixels", path, {"alpha_mode": mode}, shape)
                    for mode in ("white", "black", "ignore")
                )
            if channels > 1:
                jobs.append(Job("pixels", path, {"grayscale": True}, shape))
    return jobs


def test_pixels(reference: Reference, pixel_jobs: list[Job]) -> None:
    check(reference, pixel_jobs)


def test_pixels_past_max_pixels(reference: Reference, pixel_jobs: list[Job]) -> None:
    job = next(j for j in pixel_jobs if j.shape and j.shape[:2] == (64, 48))
    check(reference, [dataclasses.replace(job, settings={"max_pixels": 64 * 48 - 1})])


# --- Batches ------------------------------------------------------------------------


Outcome = Mapping[ph.Algorithm, int | ph.Digest] | int


def outcomes(
    results: Iterable[ph.BatchResult[Path] | ph.BatchResult[int]],
) -> list[Outcome]:
    """Each item's hashes, or its error code."""
    out: list[Outcome] = []
    for result in results:
        if result.hashes is not None:
            out.append(result.hashes)
        else:
            assert result.error is not None
            out.append(result.error.code)
    return out


def hashed_alone(path: Path, algorithms: list[ph.Algorithm]) -> Outcome:
    try:
        with ph.ImageContext() as ctx:
            ctx.load_file(path)
            return ctx.hashes(*algorithms)
    except ph.PhashError as e:
        return e.code


@pytest.mark.parametrize("threads", [1, 2, 3, 8])
def test_batches_hash_like_single_images(threads: int) -> None:
    paths = require_fixtures()
    uint64 = [a for a in ph.Algorithm if a < ph.Algorithm.BMH]
    alone = [hashed_alone(p, uint64) for p in paths]
    assert outcomes(ph.hash_files(paths, uint64, threads=threads)) == alone
    buffers = [p.read_bytes() for p in paths]
    assert outcomes(ph.hash_buffers(buffers, uint64, threads=threads)) == alone
