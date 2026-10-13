# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`python-libphash` is the Python binding for [libphash](https://github.com/gudoshnikovn/libphash), a perceptual image hashing library in C. The binding is built with CFFI in API mode: libphash and its vendored decoders are linked statically into the extension module `libphash._native`, so a wheel carries the whole library and needs no system libphash.

- **`native/libphash`** — libphash as a git submodule. It always points at a release tag of libphash (`vX.Y.Z`), never at an intermediate commit.
- **Local libphash sources:** `/Users/gudoshnikov_na/Programming/C/libphash`. Read the header, `CHANGELOG.md`, `docs/` and the C code there; do not download libphash. That repository is current C development and may be ahead of the submodule — compare by tag (`git -C native/libphash describe --tags`).

## Versioning

The binding version always has four numbers, `X.Y.Z.N`: `X.Y.Z` is the version of the bundled libphash, `N` is the binding revision on top of it. The first binding for a libphash release is `N = 0`, written out (`2.0.1.0`, then `2.0.1.1`, …); the next libphash release starts at `X.Y.Z.0` again. Tags are `vX.Y.Z.N`. The 1.x line was numbered independently of libphash (1.4.1 bundles libphash 1.10.4).

## Build & test

The project is developed with [uv](https://docs.astral.sh/uv/) (`.python-version`, `uv.lock`).

```bash
git submodule update --init --recursive   # libphash and its vendored decoders
uv sync --all-extras --inexact            # builds the extension in editable mode
uv run pytest                             # tests in tests/, fixtures from native/libphash/tests/data
uv run coverage run -m pytest && uv run coverage combine && uv run coverage report  # 100 % in CI, combined over platforms
LIBPHASH_BUILD_DIR=$PWD/build/libphash-<platform> uv run mutmut run && uv run python tools/mutants.py  # not on Windows
uv run ruff check . && uv run ruff format --check .
uv run mypy && uv run basedpyright                         # both strict, over src/, tests/, tools/, benchmarks/
uv run python tools/stub.py --check                        # _native.pyi matches the built module
uv run typos
uv build                                  # sdist + wheel into dist/
uv run python -m benchmarks              # the cost of Python over libphash, into benchmarks/results/
# Linux with Clang and libclang-rt-dev; the build replaces the editable install in .venv
uv run --no-project python tools/sanitizers.py build address   # or: thread
.venv/bin/python tools/sanitizers.py run address logs -- .venv/bin/python -m pytest
.venv/bin/python tools/sanitizers.py run fuzz logs -- .venv/bin/python tools/fuzz.py pixels -max_total_time=60
.venv/bin/python tools/sanitizers.py check logs
```

`uv sync` without `--inexact` removes packages that are not in the lock file from `.venv`.
After a change to the C side or to `tools/`, rebuild with `uv sync --all-extras --inexact --reinstall-package python-libphash`, then regenerate the stub with `uv run python tools/stub.py`.

How the extension is built:

- **`tools/native.py`** — builds libphash with its own CMake project (static, PIC, `PHASH_STRICT_DEPS=ON`, tests off) into `build/libphash-<platform>/` and reads the installed `libphash.pc` into link arguments. The binding never repeats libphash's build flags: decoder selection, the x86-64-v2 baseline, `-ffp-contract=off` and hidden visibility come from libphash's CMake. Only `PyInit__native` is exported from the extension.
- **`tools/cdef.py`** — generates the CFFI `cdef` from `native/libphash/include/libphash.h`: every function and constant of the header, nothing written by hand.
- **`tools/ffi.py`** — the CFFI builder (`cffi_modules` in `setup.py`).
- **`tools/stub.py`** — generates `src/libphash/_native.pyi` from the built module through cffi's introspection: a class per pointer and array type (`uint64_t_ptr`, `ph_digest_t_array`), struct fields, every `lib` function with the header's parameter names, `ffi.new`/`cast`/`from_buffer` overloaded on literal cdecls. Parameter types follow cffi's rules (a `T *` takes exactly `T *`/`T[]` or `ffi.NULL`; character pointers also take `bytes`). The classes exist only for type checkers: import them under `TYPE_CHECKING`. A test fails when the committed stub differs from the generated one.
- **`tools/sanitizers.py`** — the sanitizer builds (Clang; `address` is ASan + UBSan + libFuzzer's coverage hooks, `thread` is TSan) in `build/sanitizer-<name>/`, runs with the runtime preloaded into the uninstrumented interpreter, and `check`, which fails on any report and on a leak whose block the extension itself allocated (the interpreter's own unfreed blocks are ignored; `tests/conftest.py` asks LeakSanitizer for the check when the tests are done).
- **`tools/fuzz_targets.py`** — fuzz targets of what the binding adds over libphash (which fuzzes its decoders in C): `load` (encoded bytes), `pixels` (array layouts against their C-ordered copy), `digest` (text form, round trips, comparison ranges). **`tools/fuzz.py`** runs one under atheris (Linux x86-64, `fuzz` dependency group); `typings/atheris.pyi` types the part of atheris the tools use. The corpus is `tests/fuzz/<target>/`, replayed on every platform by `tests/test_fuzz_corpus.py`.
- **`setup.py`** — `build_ext` runs the CMake build before compiling the extension, so an sdist is made without a compiler; `bdist_wheel` adds the SBOM (`tools/sbom.py`: CycloneDX, every statically linked library with the version read from its sources) to `.dist-info/sboms/`; `sdist` rewrites the archive reproducibly (`tools/sdist.py`: sorted, owners cleared, dated to `SOURCE_DATE_EPOCH`).
- **`tools/audit.py`** — checks a built wheel (only `PyInit__native` exported, only system libraries imported, read with LIEF; contents, license files, `License-Expression`, SBOM) or sdist (what an offline build needs, nothing of the development tree, reproducible) before it is published.
- **`MANIFEST.in`** — the sdist carries only what libphash's CMake build reads (`CMakeLists.txt`, `cmake/`, `include/`, `src/`, `vendor/`, licenses), enough to build offline; not the tests, which need libphash's fixtures.
- **Licenses** — `license` in `pyproject.toml` is the SPDX expression of everything the wheel links, and `license-files` carries each library's license into the wheel.

Wheels are built for the platforms libphash's own CI supports: Linux x86-64 and arm64 (manylinux), macOS arm64, Windows x86-64 (`[tool.cibuildwheel]` in `pyproject.toml`). The module uses only the limited API (cffi), so `setup.py` tags a wheel built under the GIL `cp310-abi3`: cibuildwheel builds it on 3.10 and tests it on each later CPython; each free-threaded CPython, which has no stable ABI, gets its own wheel. Elsewhere pip builds the sdist; `tools/native.py` still honours `ARCHFLAGS` on macOS and the Python's architecture on Windows. Platforms are verified in CI on native runners, never under emulation.

## Architecture

The public API is what `src/libphash/__init__.py` exports; every other module is private (`_name.py`) except `exceptions.py`.

- **`__init__.py`** — `hash()` (one image, any source), `libphash_version()`, `build_info()`, `can_decode()`, `digest_info()`, and the re-exports.
- **`_context.py`** — `ImageContext`: owns one `ph_context_t*` (freed by `ffi.gc` or `close()`; use after close is a `ValueError`), serializes its C calls on a lock, `load_*` methods and the hash methods. `int` for the 64-bit algorithms, `Digest` for the rest.
- **`_config.py`** — `Config`, a frozen dataclass of every context setting, validated on creation by applying it to a scratch context. Its defaults are libphash's; a test checks `Config()` hashes like a bare `ph_create()` context.
- **`_digest.py`** — `Digest` (bytes + `DigestKind`, immutable; each comparison accepts only its kinds) and the 64-bit helpers.
- **`_algorithms.py`** — `Algorithm` and `DigestKind` enums (literal values, checked against the C enums by a test) and name/flag conversion.
- **`_batch.py`** — `hash_files()` / `hash_buffers()` over `ph_hash_*_ex`; callbacks are `extern "Python"` (`@ffi.def_extern`), entered through C wrappers in `tools/ffi.py` that take a lock on a free-threaded CPython (cffi frees exited threads' states assuming a GIL, cffi issue #286); a callback's exception is re-raised after the call; Ctrl+C reaches `should_continue` through `signal.set_wakeup_fd`.
- **`_cli.py`** — the command line (`libphash` in `[project.scripts]`, `python -m libphash` through `__main__.py`): `info`, `hash`, `compare`, `dupes`, standard library only; exit status 0, 1 when some file failed, 2 for a wrong command line, 130 on Ctrl+C.
- **`_sources.py`** — paths (`os.fsencode`; on Windows files are read in Python, because libphash opens paths with the ANSI code page), arrays (zero-copy when rows are the only gaps), Pillow modes.
- **`exceptions.py`** — the `PhashError` tree, nothing else. **`_errors.py`** — `make_error()` maps a `ph_error_t` to it. `ph_get_last_error_message()` is attached only to load errors: libphash writes it only on loads, so after a failed hash it holds a previous load's detail.
- **`_native.pyi`** — generated stub for `ffi`/`lib` (see `tools/stub.py`); **`py.typed`** marks the package as typed.

Typing: the package passes mypy and basedpyright in strict mode, and every type a caller needs to annotate their own code (`Source`, `StrPath`, `PixelArray`, `AlgorithmLike`, the `Config` literals, the protocols) is exported from `libphash`. Public signatures use protocols, not `Any`. A runtime check of an argument for untyped callers takes it as `object`, so neither checker calls the check unnecessary.
Lint: ruff with a broad rule set and pep257 docstrings (`pyproject.toml`); every exception to a rule is a per-file ignore with a comment or a `# noqa: CODE -- reason`, never a bare `noqa`.
- **`tests/`** — pytest suite (`test_cdef.py` fails when a header function is neither wrapped nor listed as deliberately unwrapped).
  `test_c_parity.py` builds `tests/c/reference.c` (through `c_reference.py`) against the libphash install of `tools/native.py` and requires the binding's hashes and error codes to equal C's for every fixture, setting and pixel layout; without the install or CMake it skips, and CI sets `LIBPHASH_REQUIRE_C_REFERENCE=1` so that it fails instead. `test_corpus.py` does the same for libphash's 200-photo site corpus and is collected only when `LIBPHASH_CORPUS` names the list of fetched photos. `test_memory.py` repeats every path (success, errors, GC, batch, callbacks) and bounds the growth of Python objects (tracemalloc) and resident memory (psutil), and holds the peak of a batch to libphash's estimate (4 bytes per pixel and the file, per worker); under a sanitizer it skips, and LeakSanitizer checks the C side.
- **`benchmarks/`** — what the binding costs over libphash and which way of using it is fastest or leanest; never other libraries. `python -m benchmarks [--blocks …] [--quick]` runs five blocks (`overhead`: one call in C, through cffi and through the API; `search`: 1 to N and N to N in Python loops, numpy and C; `memory`: copies of each load, contexts, a batch against its threads, each case in a fresh interpreter; `parallel`: threads, `hash_files`, process pools of each start method, asyncio lag, callbacks, subinterpreters; `startup`: import time and size) and writes JSON and Markdown with the environment on top. Timing follows libphash's site: a warm-up run, then at least 5 runs and 1 s, minimum and median. `benchmarks/c/bench.c` is the C side, built against the install of `tools/native.py` like the parity reference. `benchmarks/results/` holds measured runs, named `<platform>-<machine>-<python tag>`. `tests/test_benchmarks.py` runs every block in the quick mode. `benchmarks/gate.py` holds a pull request to its base: the Python allocations of the memory block within 1 KiB and a batch within 1.1 times libphash's bound fail; each timing over its table's C cell, against the base's ratio, warns past 15 % (a C cell under 10 µs) or 5 %, and with `--fail-timing` fails past 25 % or 10 %.
- **`.github/workflows/`** — `ci.yml` (lint, types, zizmor and pip-audit, tests on every platform, their line and branch coverage combined and held at 100 %, sdist, the wheel with cffi at its lower bound, the test suite under ASan/UBSan/LSan and under TSan, a minute of each fuzz target) on every push and PR; `fuzz.yml` (a quarter of an hour per fuzz target) weekly, by hand and when a target or the corpus changes; `wheels.yml` when a build file changes and from `release.yml`: every wheel by cibuildwheel (configuration in `pyproject.toml`) and the sdist, each audited by `tools/audit.py` and twine, the sdist built twice and compared and built offline, each wheel's hash table (`tools/hash_table.py`) compared across all platforms byte for byte, and a build with JPEG decoded by stb_image; `release.yml` on a tag `vX.Y.Z.N`: checks that the tag is signed and names the version, the dated CHANGELOG entry and the submodule's tag, then publishes the artifacts of `wheels.yml` to PyPI (Trusted Publishing, attestations, environment `pypi`; a `rcK` tag to TestPyPI) and to a GitHub Release with the SBOM, checksums and build provenance, and verifies what PyPI serves; `bench.yml` on a pull request that changes what is measured: the overhead and memory blocks of its base and of its head in one job, compared by `benchmarks/gate.py`; `corpus.yml` (the photo corpus, network) weekly, by hand and when the submodule changes; `mutation.yml` (mutmut over `src/libphash/`) weekly, by hand and when the package changes: every mutant is caught or listed in `tests/equivalent_mutants.json` with its reason, and `tools/mutants.py` fails on any other survivor and on a listed mutant that no longer survives. `libphash-release-check.yml` opens a tracking issue weekly when `native/libphash` is behind libphash's newest release tag.

Code, comments, docstrings and tracked documentation are in English.

## Project workflow

The backlog lives in `tmp/tasks/` (Russian-language, ignored by git): `tmp/tasks/README.md` lists the tasks in order with their status and a log of the user's decisions — **read it before starting work** and update it when a task starts or finishes. Tasks marked ⚠ need the approach agreed with the user before any code is written.

Branching: a `release/vX.Y.Z.N` branch is cut from `main`; each task gets its own `feature/...` branch. **History is linear — no merge commits.** A finished feature branch is rebased onto the release branch and integrated with `git merge --ff-only`; the release branch reaches `main` the same way, by explicit user decision only. External contributors follow `CONTRIBUTING.md` (fork, branch off `main`, PR) — a separate flow; do not mix the two.

Commits and tags are signed with SSH (configured in `.git/config`), author `gudoshnikovn <gudoshnikovna@gmail.com>`. Commit messages carry no `Co-Authored-By` trailer.

**Tracked text describes the final state**, as in libphash. A reader of the repository sees only released versions; what happened on a release branch in between — intermediate implementations, reverted decisions, reviews — does not exist for them.

- Comments, docstrings, docs, README, build files and CI use the present tense: "X is Y because Z", with a rejected alternative in the conditional ("would …"). No "used to", "no longer", "previously", "now", "again", "before this fix". A test comment states the contract the test holds, not the bug that prompted it.
- An edit replaces text; it never appends a correction.
- Tracked text, commit messages included, contains no task IDs (`T-05`, "task 7"), no paths into `tmp/`, and no "pre-release" or "development build".
- Only `CHANGELOG.md` and `MIGRATION.md` compare a release with the previous one; check every such comparison against the tag (`git show v1.4.1:<path>`), not against branch history or memory.
- When a value or a name changes, `git grep` for the old one across the tree and update every copy.
- How a decision was reached belongs in the commit message body and in `tmp/tasks/`, not in the tree.
