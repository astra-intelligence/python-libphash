"""The ``libphash`` command: its output agrees with the API, its exit status with it."""

import importlib.metadata
import io
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TextIO, cast

import pytest
from conftest import data

import libphash as ph
from libphash import _cli
from libphash._cli import main


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    status = main(list(argv))
    out, err = capsys.readouterr()
    return status, out, err


def usage_error(capsys: pytest.CaptureFixture[str], *argv: str) -> str:
    with pytest.raises(SystemExit) as exc:
        main(list(argv))
    assert exc.value.code == 2
    return capsys.readouterr().err


# --- info -----------------------------------------------------------------------------


def test_info_names_the_versions_and_the_build(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status, out, _ = run(capsys, "info")
    assert status == 0
    lines = dict(line.split(None, 1) for line in out.splitlines())
    assert lines["python-libphash"] == ph.__version__
    assert lines["libphash"] == ph.libphash_version()
    assert lines["build"] == ph.build_info()
    decoders = [f for f in ("jpeg", "png", "webp") if ph.can_decode(f)]
    assert lines["decoders"] == " ".join(decoders)


def test_info_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run(capsys, "info", "--json")
    assert status == 0
    info = json.loads(out)
    assert info["python-libphash"] == ph.__version__
    assert info["build"] == ph.build_info()
    assert info["decoders"] == [f for f in ("jpeg", "png", "webp") if ph.can_decode(f)]


def test_info_says_whether_the_gil_is_enabled(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "_is_gil_enabled", lambda: False, raising=False)
    assert json.loads(run(capsys, "info", "--json")[1])["gil"] == (
        "disabled (free-threaded)"
    )
    monkeypatch.setattr(sys, "_is_gil_enabled", lambda: True, raising=False)
    assert json.loads(run(capsys, "info", "--json")[1])["gil"] == "enabled"
    monkeypatch.delattr(sys, "_is_gil_enabled", raising=False)
    assert json.loads(run(capsys, "info", "--json")[1])["gil"] == "enabled"


def test_version_option(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert (
        out == f"python-libphash {ph.__version__} (libphash {ph.libphash_version()})\n"
    )


def test_a_command_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    assert "required" in usage_error(capsys)


# --- hash -----------------------------------------------------------------------------


def test_hash_prints_phash_and_the_path(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    status, out, err = run(capsys, "hash", str(photo))
    assert (status, err) == (0, "")
    assert out == f"{ph.hash_to_hex(ph.hash(photo))}  {photo}\n"


def test_hash_prints_each_algorithm_in_order(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    status, out, _ = run(capsys, "hash", str(photo), "-a", "radial, dhash", "-a", "bmh")
    assert status == 0
    radial = ph.hash(photo, "radial").hex()
    dhash = ph.hash_to_hex(ph.hash(photo, "dhash"))
    bmh = ph.hash(photo, "bmh").hex()
    assert out == f"{radial} {dhash} {bmh}  {photo}\n"


def test_hash_as_json_lines(capsys: pytest.CaptureFixture[str], photo: Path) -> None:
    status, out, err = run(capsys, "hash", "--json", str(photo), "-a", "PHASH,mhash")
    assert (status, err) == (0, "")
    assert json.loads(out) == {
        "path": str(photo),
        "hashes": {
            "phash": ph.hash_to_hex(ph.hash(photo)),
            "mhash": ph.hash(photo, "mhash").hex(),
        },
    }


def test_hash_applies_the_config(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    cfg = ph.Config(phash_reduction_size=6, gray_weights=(1, 1, 1), radial_sigma=2.0)
    argv = ["hash", str(photo), "-a", "phash,radial"]
    argv += ["-c", "phash_reduction_size=6", "--config", " gray_weights = 1,1,1 "]
    argv += ["-c", "radial_sigma=2"]
    expected = [ph.hash_to_hex(ph.hash(photo, config=cfg))]
    expected.append(ph.hash(photo, "radial", config=cfg).hex())
    assert run(capsys, *argv)[1] == f"{' '.join(expected)}  {photo}\n"


@pytest.mark.parametrize(
    ("assignment", "config"),
    [
        ("auto_orient=OFF", ph.Config(auto_orient=False)),
        ("grayscale=yes", ph.Config(grayscale=True)),
        ("whash_mode=full", ph.Config(whash_mode="full")),
        ("alpha_mode=black", ph.Config(alpha_mode="black")),
        ("decode_scale=2", ph.Config(decode_scale=2)),
        ("mhash_alpha=2.5", ph.Config(mhash_alpha=2.5)),
    ],
)
def test_config_values_are_parsed_by_the_field_type(
    assignment: str, config: ph.Config
) -> None:
    assert _cli.parse_config([assignment]) == config


@pytest.mark.parametrize(
    ("assignment", "message"),
    [
        ("auto_orient", "expects FIELD=VALUE"),
        ("colour=1", "unknown Config field 'colour'"),
        ("auto_orient=maybe", "auto_orient: expected true or false"),
        ("max_pixels=many", "max_pixels: expected a number"),
        ("gray_weights=1,x,1", "gray_weights: expected a number"),
        ("radial_sigma=wide", "radial_sigma: expected a number"),
        ("phash_reduction_size=99", "phash_reduction_size"),
        ("whash_mode=slow", "whash_mode"),
    ],
)
def test_a_bad_config_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], photo: Path, assignment: str, message: str
) -> None:
    assert message in usage_error(capsys, "hash", str(photo), "-c", assignment)


def test_an_unknown_algorithm_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    err = usage_error(capsys, "hash", str(photo), "-a", "phash,sha256")
    assert "unknown algorithm 'sha256'" in err


def test_hash_reads_standard_input(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    photo: Path,
    photo_bytes: bytes,
) -> None:
    stdin = io.TextIOWrapper(io.BytesIO(photo_bytes))
    monkeypatch.setattr(sys, "stdin", stdin)
    assert run(capsys, "hash", "-")[1] == f"{ph.hash_to_hex(ph.hash(photo))}  -\n"


def test_a_directory_contributes_its_images_recursively_and_sorted(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, photo: Path
) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "a").mkdir()
    shutil.copy(photo, tmp_path / "b" / "x.JPG")
    shutil.copy(photo, tmp_path / "a" / "y.jpeg")
    shutil.copy(photo, tmp_path / "z.png.txt")
    (tmp_path / "notes.txt").write_text("not an image")
    _, out, _ = run(capsys, "hash", str(tmp_path))
    paths = [line.split("  ", 1)[1] for line in out.splitlines()]
    assert paths == [
        os.path.join(tmp_path / "a", "y.jpeg"),
        os.path.join(tmp_path / "b", "x.JPG"),
    ]


def test_a_file_that_fails_is_reported_and_the_others_hashed(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, photo: Path
) -> None:
    missing = tmp_path / "missing.jpg"
    corrupt = data("corrupted.jpg")
    status, out, err = run(capsys, "hash", str(missing), str(corrupt), str(photo))
    assert status == 1
    assert out == f"{ph.hash_to_hex(ph.hash(photo))}  {photo}\n"
    lines = err.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith(f"libphash: Cannot open '{missing}'")
    # Each line names the file once, whether or not libphash's message does.
    assert lines[1].startswith(f"libphash: {corrupt}: ")
    assert lines[1].count(str(corrupt)) == 1


def test_a_failure_without_the_path_in_its_message_gets_it(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    status, _, err = run(capsys, "hash", str(photo), "-c", "max_pixels=10")
    assert status == 1
    assert err == (f"libphash: {photo}: {_message(photo, ph.Config(max_pixels=10))}\n")


def _message(path: Path, cfg: ph.Config) -> str:
    with pytest.raises(ph.PhashError) as exc:
        ph.hash(path, config=cfg)
    return str(exc.value)


def test_a_failure_as_json(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    missing = tmp_path / "missing.jpg"
    status, out, err = run(capsys, "hash", "--json", str(missing))
    assert (status, err) == (1, "")
    record = json.loads(out)
    assert record["path"] == str(missing)
    # The public class, not the errno-specific subclass it is raised as.
    assert record["error"]["type"] == "ImageIOError"
    assert record["error"]["code"] == "PH_ERR_IO"
    assert "No such file" in record["error"]["message"]
    corrupt = data("corrupted.jpg")
    out = run(capsys, "hash", "--json", str(corrupt))[1]
    assert json.loads(out)["error"]["type"] == "CorruptDataError"


# --- compare --------------------------------------------------------------------------


def test_compare_uses_the_measures_of_each_kind(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    other = data("photo_rotated_90.jpeg")
    names = "phash,bmh,color_hash,color_moments,radial"
    status, out, _ = run(capsys, "compare", str(photo), str(other), "-a", names)
    assert status == 0
    a, b = (ph.ImageContext() for _ in range(2))
    a.load_file(photo)
    b.load_file(other)
    pa, pb = a.phash(), b.phash()
    bmh, cmh = (a.bmh(), b.bmh()), (a.color_hash(), b.color_hash())
    cm, rad = (a.color_moments(), b.color_moments()), (a.radial(), b.radial())
    assert out.splitlines() == [
        (
            f"phash          distance {ph.hamming_distance(pa, pb)}, "
            f"similarity {ph.similarity(pa, pb):.4f}"
        ),
        (
            f"bmh            distance {bmh[0].hamming_distance(bmh[1])}, "
            f"similarity {bmh[0].similarity(bmh[1]):.4f}"
        ),
        f"color_hash     similarity {cmh[0].similarity(cmh[1]):.4f}",
        f"color_moments  l2_distance {cm[0].l2_distance(cm[1]):.4f}",
        f"radial         similarity {rad[0].similarity(rad[1]):.4f}",
    ]


def test_compare_as_json(capsys: pytest.CaptureFixture[str], photo: Path) -> None:
    other = data("photo_copy.jpeg")
    out = run(capsys, "compare", "--json", str(photo), str(other), "-a", "dhash")[1]
    assert json.loads(out) == {"dhash": {"distance": 0, "similarity": 1.0}}


def test_compare_radial_without_structure(capsys: pytest.CaptureFixture[str]) -> None:
    flat = data("photo.png")
    if any(ph.hash(flat, "radial").data):
        pytest.skip("the fixture has angular structure")
    argv = ["compare", str(flat), str(flat), "-a", "radial"]
    assert run(capsys, *argv)[1] == (
        "radial  similarity none (an image without structure)\n"
    )
    out = run(capsys, "compare", "--json", *argv[1:])[1]
    assert json.loads(out) == {"radial": {"similarity": None}}


def test_compare_fails_on_the_first_image_that_fails(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, photo: Path
) -> None:
    missing = tmp_path / "missing.jpg"
    status, out, err = run(capsys, "compare", str(photo), str(missing))
    assert (status, out) == (1, "")
    assert err.startswith(f"libphash: Cannot open '{missing}'")
    status, out, err = run(capsys, "compare", "--json", str(missing), str(photo))
    assert (status, err) == (1, "")
    assert json.loads(out)["path"] == str(missing)


# --- dupes ----------------------------------------------------------------------------


def test_dupes_groups_images_within_the_threshold(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    copy = data("photo_copy.jpeg")
    rotated = data("photo_rotated_90.jpeg")
    corrupt = data("corrupted.jpg")
    paths = [str(p) for p in (photo, rotated, corrupt, copy)]
    status, out, err = run(capsys, "dupes", "--max-bits", "0", "--threads", "2", *paths)
    assert status == 1
    h = ph.hash_to_hex(ph.hash(photo))
    assert out == f"{h}  {photo}\n{h}  {copy}\n"
    assert err.startswith(f"libphash: {corrupt}: ")


def test_dupes_separates_groups_and_chains_pairs() -> None:
    assert _cli.group_hashes([("a", 0b0), ("b", 0b11), ("c", 0b1)], 1) == [
        [("a", 0b0), ("b", 0b11), ("c", 0b1)]
    ]
    assert _cli.group_hashes(
        [("a", 0), ("b", 2**64 - 1), ("c", 0), ("d", 2**64 - 1)], 0
    ) == [
        [("a", 0), ("c", 0)],
        [("b", 2**64 - 1), ("d", 2**64 - 1)],
    ]
    assert _cli.group_hashes([("a", 0), ("b", 0b111)], 2) == []
    assert _cli.group_hashes([("a", 0), ("b", 0b111)], 3) == [[("a", 0), ("b", 0b111)]]


def test_dupes_prints_a_blank_line_between_groups(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    png = data("photo.png")
    paths = [str(p) for p in (photo, png, photo, png)]
    status, out, _ = run(capsys, "dupes", "--max-bits", "0", *paths)
    assert status == 0
    h, g = ph.hash_to_hex(ph.hash(photo)), ph.hash_to_hex(ph.hash(png))
    assert out == f"{h}  {photo}\n{h}  {photo}\n\n{g}  {png}\n{g}  {png}\n"


def test_dupes_as_json(capsys: pytest.CaptureFixture[str], photo: Path) -> None:
    copy = data("photo_copy.jpeg")
    corrupt = data("corrupted.jpg")
    argv = ["dupes", "--json", "--max-bits", "3", "-a", "dhash"]
    status, out, err = run(capsys, *argv, str(photo), str(copy), str(corrupt))
    assert (status, err) == (1, "")
    doc = json.loads(out)
    h = ph.hash_to_hex(ph.hash(photo, "dhash"))
    assert doc["groups"] == [
        [{"path": str(photo), "hash": h}, {"path": str(copy), "hash": h}]
    ]
    assert [e["path"] for e in doc["errors"]] == [str(corrupt)]
    assert doc["errors"][0]["error"]["code"] == "PH_ERR_CORRUPT_DATA"
    status, out, _ = run(capsys, *argv, str(photo))
    assert status == 0
    assert json.loads(out) == {"groups": [], "errors": []}


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--max-bits", "65"], "expected 0 to 64 bits, got 65"),
        (["--max-bits", "-1"], "expected 0 to 64 bits, got -1"),
        (["--max-bits", "few"], "expected a number, got 'few'"),
        (["--max-bits", "1", "--threads", "-1"], "expected 0 or more threads"),
        (["--max-bits", "1", "-a", "radial"], "radial is not a 64-bit hash"),
        (["--max-bits", "1", "-a", "phash,dhash"], "-a/--algorithm"),
        ([], "--max-bits"),
    ],
)
def test_dupes_usage_errors(
    capsys: pytest.CaptureFixture[str], photo: Path, argv: list[str], message: str
) -> None:
    assert message in usage_error(capsys, "dupes", str(photo), *argv)


def test_dupes_accepts_the_bounds(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    for bits in ("0", "64"):
        assert run(capsys, "dupes", "--max-bits", bits, str(photo))[0] == 0


# --- Interruption and output ----------------------------------------------------------


def test_ctrl_c_exits_with_130(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, photo: Path
) -> None:
    def interrupted(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(_cli, "hash_files", interrupted)
    assert run(capsys, "dupes", "--max-bits", "1", str(photo))[0] == 130


class ClosedPipe(io.StringIO):
    """Standard output whose reader has gone away; its descriptor is a real file."""

    def __init__(self, fd: int) -> None:
        super().__init__()
        self._fd = fd

    def write(self, _s: str) -> int:  # noqa: D102 -- io.StringIO's
        raise BrokenPipeError

    def fileno(self) -> int:  # noqa: D102 -- io.StringIO's
        return self._fd


def test_a_closed_pipe_stops_quietly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, photo: Path
) -> None:
    with (tmp_path / "out").open("w") as target:
        monkeypatch.setattr(sys, "stdout", ClosedPipe(target.fileno()))
        assert main(["hash", str(photo)]) == 1


def test_python_dash_m(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["libphash", "info"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("libphash", run_name="__main__")
    assert exc.value.code == 0


def test_python_dash_m_names_itself_in_the_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["libphash", "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("libphash", run_name="__main__")
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("usage: python -m libphash ")


def test_the_libphash_command_is_main() -> None:
    scripts = importlib.metadata.entry_points(group="console_scripts")
    (script,) = scripts.select(name="libphash")
    assert script.load() is main


def test_python_dash_m_in_a_process(photo: Path) -> None:
    done = subprocess.run(  # noqa: S603 -- the test's own interpreter
        [sys.executable, "-m", "libphash", "hash", str(photo), str(photo) + ".none"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 1
    assert done.stdout == f"{ph.hash_to_hex(ph.hash(photo))}  {photo}\n"
    assert done.stderr.startswith("libphash: ")


def test_compare_and_dupes_apply_the_config(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    cfg = ph.Config(phash_reduction_size=4)
    h = ph.hash(photo, config=cfg)
    out = run(
        capsys, "compare", str(photo), str(photo), "-c", "phash_reduction_size=4"
    )[1]
    assert out == "phash  distance 0, similarity 1.0000\n"
    argv = [
        "dupes",
        "--max-bits",
        "0",
        "--threads",
        "0",
        "-c",
        "phash_reduction_size=4",
    ]
    out = run(capsys, *argv, str(photo), str(photo))[1]
    assert out == f"{ph.hash_to_hex(h)}  {photo}\n" * 2
    # A smaller grid gives a different hash, so the default config would not print it.
    assert h != ph.hash(photo)


def test_info_has_exactly_its_fields(capsys: pytest.CaptureFixture[str]) -> None:
    info = json.loads(run(capsys, "info", "--json")[1])
    assert list(info) == [
        "python-libphash",
        "libphash",
        "build",
        "decoders",
        "python",
        "gil",
        "platform",
    ]
    assert info["python"].endswith(sys.version.split()[0])


def test_usage_errors_list_the_choices(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    err = usage_error(capsys, "hash", str(photo), "-a", "sha1")
    assert "expected one of ahash, dhash, phash, whash, bmh, mhash" in err
    err = usage_error(capsys, "hash", str(photo), "-c", "colour=1")
    assert "fields: gamma, gray_weights, phash_dct_size" in err


def test_a_config_value_may_contain_an_equals_sign(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    err = usage_error(capsys, "hash", str(photo), "-c", "whash_mode=a=b")
    assert "whash_mode" in err
    assert "'a=b'" in err


# --- Help, and what reaches the library ----------------------------------------------

ALGORITHM_NAMES = (
    "any of ahash, dhash, phash, whash, bmh, mhash, radial, color_hash, color_moments"
)
HELP: dict[tuple[str, ...], list[str]] = {
    (): [
        "usage: libphash",
        "Perceptual image hashing with libphash.",
        (
            "Exit status: 0 when every file was hashed, 1 when some were not, 2 for a "
            "wrong command line."
        ),
        "commands:",
        "versions and build of the bundled libphash, for bug reports",
        "hash image files",
        "compare two images",
        "find images that hash alike",
    ],
    ("info",): [
        "Print the versions and the build of the bundled libphash.",
        "--json",
        "write the results as JSON",
    ],
    ("hash",): [
        "PATH [PATH ...]",
        (
            "Print the hashes of image files: 64-bit hashes as 16 hex digits, digests "
            "as kind:hex. A directory is searched recursively for images; '-' reads "
            "one image from standard input."
        ),
        "--algorithm NAME[,NAME...]",
        f"algorithms to compute (default: phash); {ALGORITHM_NAMES}",
        "--config FIELD=VALUE",
        (
            "a Config field, as auto_orient=false or gray_weights=38,75,15; repeat for "
            "several"
        ),
        "write the results as JSON",
    ],
    ("compare",): [
        "IMAGE IMAGE",
        (
            "Compare two images with each algorithm, by the measures that belong to "
            "it: Hamming distance and similarity for bit hashes, similarity for "
            "ColorHash and Radial, L2 distance for ColorMoments."
        ),
        f"algorithms to compare with (default: phash); {ALGORITHM_NAMES}",
    ],
    ("dupes",): [
        "PATH [PATH ...]",
        (
            "Hash every image with a 64-bit algorithm on all CPUs and print the groups "
            "of images whose hashes differ in at most --max-bits bits, one group per "
            "paragraph. Measure the threshold on your own images: "
            "https://gudoshnikovn.github.io/libphash/theory/comparing/"
        ),
        "--max-bits N",
        "the most bits two hashes of one picture may differ in, 0 to 64",
        "--algorithm NAME",
        "ahash, dhash, phash (default) or whash",
        "--threads N",
        "worker threads; 0 (default) is one per CPU",
    ],
}


@pytest.mark.parametrize("command", list(HELP), ids=lambda c: " ".join(c) or "main")
def test_help_says_what_each_command_does(
    capsys: pytest.CaptureFixture[str], command: tuple[str, ...]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main([*command, "--help"])
    assert exc.value.code == 0
    # argparse wraps the text to the terminal's width.
    text = " ".join(capsys.readouterr().out.split())
    for phrase in HELP[command]:
        # Whole: no letters glued to either end.
        assert re.search(rf"(?<![A-Za-z]){re.escape(phrase)}(?![A-Za-z])", text), phrase


def test_json_is_indented_by_two(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    out = run(capsys, "info", "--json")[1]
    assert out == json.dumps(json.loads(out), indent=2) + "\n"
    out = run(capsys, "compare", "--json", str(photo), str(photo))[1]
    assert out == json.dumps(json.loads(out), indent=2) + "\n"
    out = run(capsys, "dupes", "--json", "--max-bits", "0", str(photo))[1]
    assert out == json.dumps(json.loads(out), indent=2) + "\n"
    out = run(capsys, "compare", "--json", str(photo), str(photo) + ".none")[1]
    assert out == json.dumps(json.loads(out), indent=2) + "\n"
    assert set(json.loads(out)) == {"path", "error"}


def test_compare_applies_the_config(
    capsys: pytest.CaptureFixture[str], photo: Path
) -> None:
    other = data("photo_rotated_90.jpeg")
    cfg = ph.Config(phash_reduction_size=4)
    a, b = ph.hash(photo, config=cfg), ph.hash(other, config=cfg)
    argv = ["compare", "--json", str(photo), str(other), "-c", "phash_reduction_size=4"]
    distance = json.loads(run(capsys, *argv)[1])["phash"]["distance"]
    assert distance == ph.hamming_distance(a, b)
    assert distance != ph.hamming_distance(ph.hash(photo), ph.hash(other))


def test_dupes_passes_the_threads_and_reports_the_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    real = ph.hash_files

    def spy(
        paths: list[str], algorithm: ph.Algorithm, *, config: ph.Config, threads: int
    ) -> list[ph.BatchResult[str]]:
        calls.append(threads)
        return real(paths, algorithm, config=config, threads=threads)

    monkeypatch.setattr(_cli, "hash_files", spy)
    corrupt = data("corrupted.jpg")
    _, _, err = run(capsys, "dupes", "--max-bits", "1", "--threads", "3", str(corrupt))
    run(capsys, "dupes", "--max-bits", "1", str(corrupt))
    assert calls == [3, 0]
    assert "the data is corrupt" in err


def test_a_directory_named_dash_is_still_standard_input(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    photo: Path,
    photo_bytes: bytes,
) -> None:
    (tmp_path / "-").mkdir()
    shutil.copy(photo, tmp_path / "-" / "inside.jpg")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(photo_bytes)))
    assert run(capsys, "hash", "-")[1] == f"{ph.hash_to_hex(ph.hash(photo))}  -\n"


@pytest.mark.parametrize(
    ("platform", "written"),
    [
        ("linux", b"b\xff.jpg"),
        ("darwin", b"b\xff.jpg"),
        ("win32", b"b\\udcff.jpg"),
    ],
)
def test_output_takes_any_file_name(
    monkeypatch: pytest.MonkeyPatch, platform: str, written: bytes
) -> None:
    # An undecodable POSIX name reaches the output as its bytes; a Windows name the
    # code page lacks, as an escape. Neither stops the output.
    monkeypatch.setattr(sys, "platform", platform)
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="ascii")
    _cli.write_any_file_name(stream)
    stream.write("b\udcff.jpg")
    stream.flush()
    assert raw.getvalue() == written


def test_output_errors_chosen_by_the_caller_are_kept() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="replace")
    _cli.write_any_file_name(stream)
    assert stream.errors == "replace"
    # A stream that is not a TextIOWrapper cannot be reconfigured and is left alone.
    _cli.write_any_file_name(cast("TextIO", SimpleNamespace(errors="strict")))


def test_main_lets_stdout_write_any_file_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert sys.stdout.errors == "strict"
    run(capsys, "info")
    assert sys.stdout.errors != "strict"


@pytest.mark.skipif(
    sys.platform != "linux", reason="needs a file system that stores raw bytes"
)
def test_hash_prints_a_name_that_is_not_utf8(tmp_path: Path, photo: Path) -> None:
    name = os.fsencode(tmp_path) + b"/\xff\xfe.jpg"
    shutil.copyfile(photo, name)
    done = subprocess.run(  # noqa: S603 -- the test's own interpreter
        [sys.executable, "-m", "libphash", "hash", str(tmp_path)],
        capture_output=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout == ph.hash_to_hex(ph.hash(photo)).encode() + b"  " + name + b"\n"
