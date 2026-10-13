"""Run one fuzz target of ``tools/fuzz_targets.py`` under atheris (libFuzzer).

    python tools/fuzz.py TARGET [libFuzzer options] [CORPUS_DIR ...]

The arguments after the target go to libFuzzer as they are: ``-max_total_time=60``,
``-artifact_prefix=crashes/``, corpus directories, ``-merge=1 MIN_DIR CORPUS_DIR`` to
minimize a corpus. libFuzzer writes the inputs it finds into the first directory; the
target's seeds (``tests/fuzz/<target>/``, and libphash's seeds for ``load``) follow the
given directories, after a temporary one when none is given, and are only read.
atheris instruments the package's Python code for coverage; the C side of the binding
is checked by running the fuzzer in the AddressSanitizer build of the sanitizer job,
where a read past a buffer stops it as an assertion does.

An input that fails a target goes into ``tests/fuzz/<target>/`` once the bug is fixed:
``tests/test_fuzz_corpus.py`` replays that corpus on every platform.

atheris has wheels for Linux x86-64 only; it is in the ``fuzz`` dependency group.
"""

from __future__ import annotations

import shlex
import sys
import tempfile
from pathlib import Path

# typings/atheris.pyi describes it where atheris itself is not installed.
import atheris  # pyright: ignore[reportMissingModuleSource]

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    """Fuzz the target named by the first argument."""
    with atheris.instrument_imports(include=["libphash", "fuzz_targets"]):
        import fuzz_targets  # noqa: PLC0415 -- instrumented as it is imported

    if len(sys.argv) < 2 or sys.argv[1] not in fuzz_targets.TARGETS:
        names = ", ".join(fuzz_targets.TARGETS)
        sys.exit(f"usage: fuzz.py TARGET [libFuzzer options]; targets: {names}")
    name, args = sys.argv[1], sys.argv[2:]
    if not any(not a.startswith("-") for a in args):
        args.append(tempfile.mkdtemp(prefix=f"fuzz-{name}-"))
    args += [str(d) for d in fuzz_targets.seed_dirs(name) if d.is_dir()]
    # libFuzzer's -merge and -fork modes start the fuzzer again through system(), as
    # argv[0] followed by options: argv[0] is the command that leads back here.
    command = shlex.join([sys.executable, str(Path(__file__).resolve()), name])
    atheris.Setup([command, *args], fuzz_targets.TARGETS[name])
    atheris.Fuzz()


if __name__ == "__main__":
    main()
