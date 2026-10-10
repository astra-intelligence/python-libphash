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
uv run ruff check . && uv run ruff format --check .
uv run mypy && uv run basedpyright                         # both strict, over src/, tests/, tools/
uv run python tools/stub.py --check                        # _native.pyi matches the built module
uv run typos
uv build                                  # sdist + wheel into dist/
```

`uv sync` without `--inexact` removes packages that are not in the lock file from `.venv`.
After a change to the C side or to `tools/`, rebuild with `uv sync --all-extras --inexact --reinstall-package python-libphash`, then regenerate the stub with `uv run python tools/stub.py`.

How the extension is built:

- **`tools/native.py`** — builds libphash with its own CMake project (static, PIC, `PHASH_STRICT_DEPS=ON`, tests off) into `build/libphash-<platform>/` and reads the installed `libphash.pc` into link arguments. The binding never repeats libphash's build flags: decoder selection, the x86-64-v2 baseline, `-ffp-contract=off` and hidden visibility come from libphash's CMake. Only `PyInit__native` is exported from the extension.
- **`tools/cdef.py`** — generates the CFFI `cdef` from `native/libphash/include/libphash.h`: every function and constant of the header, nothing written by hand.
- **`tools/ffi.py`** — the CFFI builder (`cffi_modules` in `setup.py`).
- **`tools/stub.py`** — generates `src/libphash/_native.pyi` from the built module through cffi's introspection: a class per pointer and array type (`uint64_t_ptr`, `ph_digest_t_array`), struct fields, every `lib` function with the header's parameter names, `ffi.new`/`cast`/`from_buffer` overloaded on literal cdecls. Parameter types follow cffi's rules (a `T *` takes exactly `T *`/`T[]` or `ffi.NULL`; character pointers also take `bytes`). The classes exist only for type checkers: import them under `TYPE_CHECKING`. A test fails when the committed stub differs from the generated one.
- **`setup.py`** — `build_ext` runs the CMake build before compiling the extension, so an sdist is made without a compiler.
- **`MANIFEST.in`** — the sdist carries only what libphash's CMake build reads (`CMakeLists.txt`, `cmake/`, `include/`, `src/`, `vendor/`, licenses), enough to build offline.

On macOS, `ARCHFLAGS="-arch x86_64"` cross-builds an x86-64 wheel (as cibuildwheel does). Other platforms are verified in CI, never under emulation.

## Architecture

The public API is what `src/libphash/__init__.py` exports; every other module is private (`_name.py`) except `exceptions.py`.

- **`__init__.py`** — `hash()` (one image, any source), `libphash_version()`, `build_info()`, `can_decode()`, `digest_info()`, and the re-exports.
- **`_context.py`** — `ImageContext`: owns one `ph_context_t*` (freed by `ffi.gc` or `close()`; use after close is a `ValueError`), serializes its C calls on a lock, `load_*` methods and the hash methods. `int` for the 64-bit algorithms, `Digest` for the rest.
- **`_config.py`** — `Config`, a frozen dataclass of every context setting, validated on creation by applying it to a scratch context. Its defaults are libphash's; a test checks `Config()` hashes like a bare `ph_create()` context.
- **`_digest.py`** — `Digest` (bytes + `DigestKind`, immutable; each comparison accepts only its kinds) and the 64-bit helpers.
- **`_algorithms.py`** — `Algorithm` and `DigestKind` enums (literal values, checked against the C enums by a test) and name/flag conversion.
- **`_batch.py`** — `hash_files()` / `hash_buffers()` over `ph_hash_*_ex`; callbacks are `extern "Python"` (`@ffi.def_extern`); a callback's exception is re-raised after the call; Ctrl+C reaches `should_continue` through `signal.set_wakeup_fd`.
- **`_sources.py`** — paths (`os.fsencode`; on Windows files are read in Python, because libphash opens paths with the ANSI code page), arrays (zero-copy when rows are the only gaps), Pillow modes.
- **`exceptions.py`** — the `PhashError` tree, nothing else. **`_errors.py`** — `make_error()` maps a `ph_error_t` to it. `ph_get_last_error_message()` is attached only to load errors: libphash writes it only on loads, so after a failed hash it holds a previous load's detail.
- **`_native.pyi`** — generated stub for `ffi`/`lib` (see `tools/stub.py`); **`py.typed`** marks the package as typed.

Typing: the package passes mypy and basedpyright in strict mode, and every type a caller needs to annotate their own code (`Source`, `StrPath`, `PixelArray`, `AlgorithmLike`, the `Config` literals, the protocols) is exported from `libphash`. Public signatures use protocols, not `Any`. A runtime check of an argument for untyped callers takes it as `object`, so neither checker calls the check unnecessary.
Lint: ruff with a broad rule set and pep257 docstrings (`pyproject.toml`); every exception to a rule is a per-file ignore with a comment or a `# noqa: CODE -- reason`, never a bare `noqa`.
- **`tests/`** — pytest suite (`test_cdef.py` fails when a header function is neither wrapped nor listed as deliberately unwrapped).
- **`.github/workflows/`** — CI; wheels are built with cibuildwheel (configuration in `pyproject.toml`).

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
