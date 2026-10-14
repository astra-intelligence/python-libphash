"""The command line, ``libphash``: ``info``, ``hash``, ``compare``, ``dupes``.

Results go to standard output, one line per item, or as JSON with ``--json``; a file
that cannot be hashed is reported on standard error (in the JSON itself with ``--json``)
and does not stop the others. The exit status is 0 when every file was hashed, 1 when
some were not, and 2 for a wrong command line.
"""

from __future__ import annotations

import argparse
import dataclasses
import io
import json
import os
import platform
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TextIO, cast

from . import (
    Algorithm,
    Config,
    Digest,
    DigestKind,
    ImageContext,
    PhashError,
    build_info,
    can_decode,
    hamming_distance,
    hash_files,
    hash_to_hex,
    libphash_version,
    similarity,
)
from ._algorithms import UINT64_ALGORITHMS
from ._version import __version__
from .exceptions import ImageIOError, NoStructureError

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

#: Suffixes taken from a directory: the formats libphash decodes. A file named on the
#: command line is hashed whatever its name.
IMAGE_SUFFIXES = frozenset(
    {
        ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".gif", ".bmp", ".tga",
        ".psd", ".hdr", ".pic", ".pnm", ".pbm", ".pgm", ".ppm",
    }
)  # fmt: skip

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

_ALGORITHMS = {str(a): a for a in Algorithm}
_FIELDS = {f.name: f for f in dataclasses.fields(Config)}
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def main(argv: Sequence[str] | None = None, prog: str = "libphash") -> int:
    """Run the command line with ``argv`` (``sys.argv[1:]`` by default).

    ``prog`` is the command its help and errors name. Return the exit status.
    """
    parser = _parser(prog)
    args = parser.parse_args(argv)
    try:
        config = parse_config(args.config)
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))
    write_any_file_name(sys.stdout)
    try:
        status: int = args.run(args, config, sys.stdout, sys.stderr)
        sys.stdout.flush()
    except KeyboardInterrupt:
        return 128 + 2
    except BrokenPipeError:
        # The reader went away (`| head`): stop quietly. Python would report the failed
        # flush of stdout at exit, so stdout is pointed at devnull first.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return EXIT_FAILED
    return status


# --- Command line ---------------------------------------------------------------------


def _parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Perceptual image hashing with libphash.",
        epilog=(
            "Exit status: 0 when every file was hashed, 1 when some were not, "
            "2 for a wrong command line."
        ),
    )
    parser.add_argument("--version", action="version", version=_version_line())
    commands = parser.add_subparsers(title="commands", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="write the results as JSON")

    configured = argparse.ArgumentParser(add_help=False)
    configured.add_argument(
        "-c",
        "--config",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help=(
            "a Config field, as auto_orient=false or gray_weights=38,75,15; "
            "repeat for several"
        ),
    )

    info = commands.add_parser(
        "info",
        parents=[common],
        help="versions and build of the bundled libphash, for bug reports",
        description="Print the versions and the build of the bundled libphash.",
    )
    info.set_defaults(run=_run_info, config=[])

    hash_cmd = commands.add_parser(
        "hash",
        parents=[common, configured],
        help="hash image files",
        description=(
            "Print the hashes of image files: 64-bit hashes as 16 hex digits, "
            "digests as kind:hex. A directory is searched recursively for images; "
            "'-' reads one image from standard input."
        ),
    )
    hash_cmd.add_argument("paths", nargs="+", metavar="PATH")
    _algorithm_option(hash_cmd, "algorithms to compute (default: phash)")
    hash_cmd.set_defaults(run=_run_hash)

    compare = commands.add_parser(
        "compare",
        parents=[common, configured],
        help="compare two images",
        description=(
            "Compare two images with each algorithm, by the measures that belong to "
            "it: Hamming distance and similarity for bit hashes, similarity for "
            "ColorHash and Radial, L2 distance for ColorMoments."
        ),
    )
    compare.add_argument("first", metavar="IMAGE")
    compare.add_argument("second", metavar="IMAGE")
    _algorithm_option(compare, "algorithms to compare with (default: phash)")
    compare.set_defaults(run=_run_compare)

    dupes = commands.add_parser(
        "dupes",
        parents=[common, configured],
        help="find images that hash alike",
        description=(
            "Hash every image with a 64-bit algorithm on all CPUs and print the "
            "groups of images whose hashes differ in at most --max-bits bits, one "
            "group per paragraph. Measure the threshold on your own images: "
            "https://gudoshnikovn.github.io/libphash/theory/comparing/"
        ),
    )
    dupes.add_argument("paths", nargs="+", metavar="PATH")
    dupes.add_argument(
        "--max-bits",
        type=_bits,
        required=True,
        metavar="N",
        help="the most bits two hashes of one picture may differ in, 0 to 64",
    )
    dupes.add_argument(
        "-a",
        "--algorithm",
        type=_uint64_algorithm,
        default=Algorithm.PHASH,
        metavar="NAME",
        help="ahash, dhash, phash (default) or whash",
    )
    dupes.add_argument(
        "--threads",
        type=_threads,
        default=0,
        metavar="N",
        help="worker threads; 0 (default) is one per CPU",
    )
    dupes.set_defaults(run=_run_dupes)
    return parser


def _algorithm_option(parser: argparse.ArgumentParser, help_text: str) -> None:
    names = ", ".join(_ALGORITHMS)
    parser.add_argument(
        "-a",
        "--algorithm",
        dest="algorithms",
        type=_algorithm_list,
        action="extend",
        metavar="NAME[,NAME...]",
        help=f"{help_text}; any of {names}",
    )


def _algorithm_list(text: str) -> list[Algorithm]:
    out: list[Algorithm] = []
    for name in text.split(","):
        algo = _ALGORITHMS.get(name.strip().lower())
        if algo is None:
            names = ", ".join(_ALGORITHMS)
            raise argparse.ArgumentTypeError(
                f"unknown algorithm {name!r}; expected one of {names}"
            )
        out.append(algo)
    return out


def _uint64_algorithm(text: str) -> Algorithm:
    [algo] = _algorithm_list(text)
    if algo not in UINT64_ALGORITHMS:
        raise argparse.ArgumentTypeError(
            f"{algo} is not a 64-bit hash; expected ahash, dhash, phash or whash"
        )
    return algo


def _bits(text: str) -> int:
    value = _integer(text)
    if not 0 <= value <= 64:
        raise argparse.ArgumentTypeError(f"expected 0 to 64 bits, got {value}")
    return value


def _threads(text: str) -> int:
    value = _integer(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"expected 0 or more threads, got {value}")
    return value


def _integer(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number, got {text!r}") from None


def parse_config(assignments: list[str]) -> Config:
    """Build a Config from ``field=value`` strings; Config checks the values."""
    changes: dict[str, object] = {}
    for assignment in assignments:
        name, sep, text = assignment.partition("=")
        name = name.strip()
        if not sep:
            raise ValueError(f"--config expects FIELD=VALUE, got {assignment!r}")
        if name not in _FIELDS:
            fields = ", ".join(_FIELDS)
            raise ValueError(f"unknown Config field {name!r}; fields: {fields}")
        changes[name] = _parse_value(name, text.strip())
    return Config().replace(**changes)


def _parse_value(name: str, text: str) -> object:
    default = _FIELDS[name].default
    if isinstance(default, bool):
        if text.lower() in _TRUE:
            return True
        if text.lower() in _FALSE:
            return False
        raise ValueError(f"{name}: expected true or false, got {text!r}")
    if isinstance(default, tuple):
        return tuple(_number(name, part, int) for part in text.split(","))
    if isinstance(default, int):
        return _number(name, text, int)
    if isinstance(default, float):
        return _number(name, text, float)
    return text


def _number(name: str, text: str, kind: type[int | float]) -> int | float:
    try:
        return kind(text.strip())
    except ValueError:
        raise ValueError(f"{name}: expected a number, got {text!r}") from None


# --- Commands -------------------------------------------------------------------------


def _run_info(args: argparse.Namespace, _cfg: Config, out: TextIO, _err: TextIO) -> int:
    info = {
        "python-libphash": __version__,
        "libphash": libphash_version(),
        "build": build_info(),
        "decoders": [f for f in ("jpeg", "png", "webp") if can_decode(f)],
        "python": f"{platform.python_implementation()} {platform.python_version()}",
        "gil": _gil(),
        "platform": platform.platform(),
    }
    if args.json:
        json.dump(info, out, indent=2)
        out.write("\n")
        return EXIT_OK
    width = max(len(key) for key in info)
    for key, value in info.items():
        text = " ".join(value) if isinstance(value, list) else value
        out.write(f"{key:<{width}}  {text}\n")
    return EXIT_OK


def _gil() -> str:
    """Say whether the GIL is on, and whether the interpreter can run without it."""
    is_enabled = getattr(sys, "_is_gil_enabled", None)
    if is_enabled is None:
        return "enabled"
    return "enabled" if is_enabled() else "disabled (free-threaded)"


def _run_hash(
    args: argparse.Namespace, config: Config, out: TextIO, err: TextIO
) -> int:
    algorithms: list[Algorithm] = args.algorithms or [Algorithm.PHASH]
    status = EXIT_OK
    with ImageContext(config) as ctx:
        for path in _expand(args.paths):
            try:
                if path == "-":
                    ctx.load_bytes(sys.stdin.buffer.read())
                else:
                    ctx.load_file(path)
                hashes = ctx.hashes(*algorithms)
            except PhashError as exc:
                status = EXIT_FAILED
                if args.json:
                    out.write(json.dumps({"path": path, "error": _error(exc)}) + "\n")
                else:
                    _report(err, path, exc)
                continue
            texts = {str(a): _text(hashes[a]) for a in algorithms}
            if args.json:
                out.write(json.dumps({"path": path, "hashes": texts}) + "\n")
            else:
                out.write(f"{' '.join(texts.values())}  {path}\n")
    return status


def _run_compare(
    args: argparse.Namespace, config: Config, out: TextIO, err: TextIO
) -> int:
    algorithms: list[Algorithm] = args.algorithms or [Algorithm.PHASH]
    hashes: list[dict[Algorithm, int | Digest]] = []
    for path in (args.first, args.second):
        with ImageContext(config) as ctx:
            try:
                ctx.load_file(path)
                hashes.append(ctx.hashes(*algorithms))
            except PhashError as exc:
                if args.json:
                    json.dump({"path": path, "error": _error(exc)}, out, indent=2)
                    out.write("\n")
                else:
                    _report(err, path, exc)
                return EXIT_FAILED
    first, second = hashes
    results = {str(a): _measures(first[a], second[a]) for a in algorithms}
    if args.json:
        json.dump(results, out, indent=2)
        out.write("\n")
        return EXIT_OK
    width = max(len(name) for name in results)
    for name, measures in results.items():
        text = ", ".join(_measure_text(key, value) for key, value in measures.items())
        out.write(f"{name:<{width}}  {text}\n")
    return EXIT_OK


def _measures(a: int | Digest, b: int | Digest) -> dict[str, int | float | None]:
    """Return the measures that belong to the hashes' kind, by name."""
    if not (isinstance(a, Digest) and isinstance(b, Digest)):
        a, b = cast("int", a), cast("int", b)
        return {"distance": hamming_distance(a, b), "similarity": similarity(a, b)}
    if a.kind == DigestKind.BITS:
        return {"distance": a.hamming_distance(b), "similarity": a.similarity(b)}
    if a.kind == DigestKind.VECTOR16:
        return {"l2_distance": a.l2_distance(b)}
    try:
        return {"similarity": a.similarity(b)}
    except NoStructureError:
        # A flat image has no Radial structure to correlate: no score exists.
        return {"similarity": None}


def _measure_text(name: str, value: float | None) -> str:
    if value is None:
        return f"{name} none (an image without structure)"
    if isinstance(value, int):
        return f"{name} {value}"
    return f"{name} {value:.4f}"


def _run_dupes(
    args: argparse.Namespace, config: Config, out: TextIO, err: TextIO
) -> int:
    algo: Algorithm = args.algorithm
    paths = list(_expand(args.paths))
    results = hash_files(paths, algo, config=config, threads=args.threads)
    hashed: list[tuple[str, int]] = []
    failed: list[tuple[str, PhashError]] = []
    for result in results:
        if result.hashes is not None:
            hashed.append((result.source, result.hashes[algo]))
        else:
            failed.append((result.source, cast("PhashError", result.error)))
    groups = group_hashes(hashed, args.max_bits)
    status = EXIT_FAILED if failed else EXIT_OK
    if args.json:
        doc = {
            "groups": [
                [{"path": p, "hash": hash_to_hex(h)} for p, h in g] for g in groups
            ],
            "errors": [{"path": p, "error": _error(e)} for p, e in failed],
        }
        json.dump(doc, out, indent=2)
        out.write("\n")
        return status
    for path, exc in failed:
        _report(err, path, exc)
    for i, group in enumerate(groups):
        if i:
            out.write("\n")
        for path, value in group:
            out.write(f"{hash_to_hex(value)}  {path}\n")
    return status


def group_hashes(
    hashed: list[tuple[str, int]], max_bits: int
) -> list[list[tuple[str, int]]]:
    """Group the images linked by a chain of pairs within ``max_bits`` of each other.

    Every pair is compared once. The groups and the images in each keep the order of
    ``hashed``; images alone in their group are left out.
    """
    parent = list(range(len(hashed)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, (_, a) in enumerate(hashed):
        for j in range(i + 1, len(hashed)):
            if (a ^ hashed[j][1]).bit_count() <= max_bits:
                parent[root(j)] = root(i)
    members: dict[int, list[tuple[str, int]]] = {}
    for i, item in enumerate(hashed):
        members.setdefault(root(i), []).append(item)
    return [group for group in members.values() if len(group) > 1]


# --- Helpers --------------------------------------------------------------------------


def write_any_file_name(stream: TextIO) -> None:
    """Let the output stream write every file name it is given.

    A POSIX file name is bytes, which need not decode in the file system encoding: the
    command line and os.walk() give the undecodable bytes as surrogates, written back as
    those bytes, the name as ``ls`` prints it. A Windows file name is Unicode, which the
    console's code page may not hold: a character it lacks is written as an escape.
    Either way the output goes on instead of stopping at UnicodeEncodeError.
    """
    if isinstance(stream, io.TextIOWrapper) and stream.errors == "strict":
        errors = "backslashreplace" if sys.platform == "win32" else "surrogateescape"
        stream.reconfigure(errors=errors)


def _expand(paths: Sequence[str]) -> Iterator[str]:
    """Yield the files named, and the images in the directories named, in order.

    A directory is walked recursively, its entries sorted by name, and contributes the
    files whose suffix is in IMAGE_SUFFIXES. Anything else is yielded as given, so that
    a missing file is reported by the load.
    """
    for path in paths:
        if path != "-" and Path(path).is_dir():
            for root, dirs, files in os.walk(path):
                dirs.sort()
                for name in sorted(files):
                    if Path(name).suffix.lower() in IMAGE_SUFFIXES:
                        yield os.path.join(root, name)
        else:
            yield path


def _text(value: int | Digest) -> str:
    return hash_to_hex(value) if isinstance(value, int) else value.hex()


def _error(exc: PhashError) -> dict[str, str]:
    # An ImageIOError is raised as a private subclass per errno; name the public one.
    name = "ImageIOError" if isinstance(exc, ImageIOError) else type(exc).__name__
    return {"type": name, "code": exc.code_name, "message": str(exc)}


def _report(err: TextIO, path: str, exc: PhashError) -> None:
    # Most messages of a failed load name the file already.
    message = str(exc)
    if path not in message:
        message = f"{path}: {message}"
    err.write(f"libphash: {message}\n")


def _version_line() -> str:
    return f"python-libphash {__version__} (libphash {libphash_version()})"
