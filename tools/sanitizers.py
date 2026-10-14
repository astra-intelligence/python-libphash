"""Build and run the binding under Clang's sanitizers (Linux).

The sanitizer jobs of CI run these commands; on Linux with Clang and its runtimes
(``libclang-rt-dev``) they run the same way locally::

    python tools/sanitizers.py build address    # or: thread
    python tools/sanitizers.py run address LOG_DIR -- .venv/bin/python -m pytest
    python tools/sanitizers.py check LOG_DIR

``build`` compiles libphash, its decoders and the extension with the sanitizer, into a
build directory of their own, and installs the package into ``.venv`` (editable) with
``uv sync``. ``address`` is AddressSanitizer with UndefinedBehaviorSanitizer and the
coverage hooks of libFuzzer, so that one build serves the tests and the fuzzers;
``thread`` is ThreadSanitizer.

``run`` starts a command with the sanitizer's runtime preloaded, as the interpreter is
not built with it, and every report written to ``LOG_DIR``, one file per process.
``fuzz`` is the AddressSanitizer build under atheris' copy of the runtime, which carries
libFuzzer and so sees the coverage of the C code.

``check`` fails on any report of a memory error, undefined behaviour or a data race,
and on a leak of the extension's. LeakSanitizer reports every block nothing points to,
and the interpreter holds blocks it never frees, so a leak counts only when the block
was allocated by the extension itself: the first frame of its stack past the
sanitizer's allocator is in ``libphash._native``, which holds libphash, its decoders
and the CFFI wrappers. A suppression file would not do: a suppression matches any frame
of a stack, and every stack of the extension passes through the interpreter's frames.
The tests ask for the leak check when they are done (``tests/conftest.py``); at exit
it is off, as the interpreter's teardown drops the references to its own blocks.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Compiler and linker flags of each build. The extension does not link the runtime
#: (no -shared-libasan), so it takes whichever copy ``run`` preloads. That copy is
#: atheris' for the fuzzers, built by an older LLVM than the runner's Clang; its
#: UndefinedBehaviorSanitizer has no handler for the function type check, which Clang
#: applies to C as part of ``undefined``, so the extension would not load with it.
FLAGS = {
    "address": (
        (
            "-fsanitize=address,undefined,fuzzer-no-link -fno-sanitize=function"
            " -fno-sanitize-recover=all"
        ),
        "-fsanitize=address,undefined",
    ),
    "thread": ("-fsanitize=thread", "-fsanitize=thread"),
}

#: Each frame of a report ends with its module and offset, which ``check`` reads.
FRAME_FORMAT = 'stack_trace_format="    #%n %p %F %L %M"'


def build(sanitizer: str) -> None:
    """Build the package with a sanitizer and install it into ``.venv``."""
    cflags, ldflags = FLAGS[sanitizer]
    env = {
        **os.environ,
        "CC": "clang",
        "CFLAGS": f"{cflags} -fno-omit-frame-pointer -g",
        "LDFLAGS": ldflags,
        "LIBPHASH_BUILD_DIR": str(PROJECT_ROOT / "build" / f"sanitizer-{sanitizer}"),
    }
    command = ["uv", "sync", "--locked", "--all-extras", "--inexact"]
    command += ["--reinstall-package", "python-libphash"]
    if sanitizer == "address":
        command += ["--group", "fuzz"]
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def _clang_runtime(name: str) -> str:
    machine = os.uname().machine
    path = subprocess.run(
        ["clang", f"-print-file-name=libclang_rt.{name}-{machine}.so"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not os.path.isabs(path):
        sys.exit(f"Clang's {name} runtime is missing; install libclang-rt-dev")
    return path


def run_environment(sanitizer: str, log_dir: Path) -> dict[str, str]:
    """Return the environment that runs a command under a sanitizer."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log = f"log_path={log_dir.resolve()}/{sanitizer}"
    env = dict(os.environ)
    if sanitizer == "thread":
        env["LD_PRELOAD"] = _clang_runtime("tsan")
        env["TSAN_OPTIONS"] = f"halt_on_error=1:{log}"
        return env
    if sanitizer == "fuzz":
        import atheris  # noqa: PLC0415 -- only the fuzzers need it  # pyright: ignore[reportMissingModuleSource]

        env["LD_PRELOAD"] = f"{atheris.path()}/asan_with_fuzzer.so"
        # libFuzzer checks for leaks after every input, and the interpreter's caches
        # would look like one; the tests' run checks for leaks instead.
        leaks = "detect_leaks=0"
    else:
        env["LD_PRELOAD"] = _clang_runtime("asan")
        leaks = "detect_leaks=1:leak_check_at_exit=0"
    env["ASAN_OPTIONS"] = f"{leaks}:halt_on_error=1:{log}:{FRAME_FORMAT}"
    env["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
    # Python objects from the system allocator, where ASan sees each of them.
    env["PYTHONMALLOC"] = "malloc"
    return env


EXTENSION = re.compile(r"^_native\.")
RUNTIME = re.compile(r"^(lib(clang_rt\.|asan|ubsan)|asan_with_fuzzer)")
# The last "(module+0xoffset)" of a frame line.
MODULE = re.compile(r"\(([^()\s]+)\+0x[0-9a-f]+\)(?:\s*\(BuildId: [0-9a-f]+\))?\s*$")
LEAK = re.compile(r"^(Direct|Indirect) leak of (\d+) byte\(s\) in (\d+) object\(s\)")
ERROR = re.compile(r"ERROR: AddressSanitizer|runtime error:|WARNING: ThreadSanitizer")


@dataclass(frozen=True)
class Leak:
    """One leak record of a LeakSanitizer report."""

    size: int
    frames: tuple[str, ...]

    @property
    def origin(self) -> str:
        """Return the module of the first frame past the sanitizer's allocator."""
        for frame in self.frames:
            m = MODULE.search(frame)
            module = m.group(1) if m else "?"
            if not RUNTIME.match(module):
                return module
        return "?"


def leaks(text: str) -> list[Leak]:
    """Return the leak records of a log."""
    found: list[Leak] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = LEAK.match(line)
        if not m:
            continue
        frames: list[str] = []
        for frame in lines[i + 1 :]:
            if not frame.lstrip().startswith("#"):
                break
            frames.append(frame)
        found.append(Leak(int(m.group(2)), tuple(frames)))
    return found


def check(log_dir: Path) -> int:
    """Print the findings of every log in a directory; return 1 if any fails."""
    failed = False
    out: list[str] = []
    ignored: Counter[str] = Counter()
    logs = (
        sorted(p for p in log_dir.iterdir() if p.is_file()) if log_dir.is_dir() else []
    )
    for log in logs:
        text = log.read_text(encoding="utf-8", errors="replace")
        if ERROR.search(text):
            failed = True
            out += [f"--- {log.name}: sanitizer report", text]
            continue
        for leak in leaks(text):
            if EXTENSION.match(leak.origin):
                failed = True
                out += [f"--- {log.name}: leak in the extension", *leak.frames]
            else:
                ignored[leak.origin] += leak.size
    out.append(f"{len(logs)} sanitizer log(s) in {log_dir}")
    out += [
        f"  not the extension's, ignored: {size} bytes allocated by {module}"
        for module, size in ignored.most_common()
    ]
    sys.stdout.write("\n".join(out) + "\n")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    """Run the subcommand the arguments name."""
    parser = argparse.ArgumentParser(description="Build and run under sanitizers.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build").add_argument("sanitizer", choices=FLAGS)
    run = sub.add_parser("run")
    run.add_argument("sanitizer", choices=[*FLAGS, "fuzz"])
    run.add_argument("log_dir", type=Path)
    run.add_argument("argv", nargs=argparse.REMAINDER)
    sub.add_parser("check").add_argument("log_dir", type=Path)
    args = parser.parse_args(argv)

    if args.command == "build":
        build(args.sanitizer)
        return 0
    if args.command == "check":
        return check(args.log_dir)
    command: list[str] = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    if not command:
        parser.error("run needs a command after --")
    env = run_environment(args.sanitizer, args.log_dir)
    return subprocess.run(command, env=env, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
