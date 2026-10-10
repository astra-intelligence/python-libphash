# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`python-libphash` is the Python binding for [libphash](https://github.com/gudoshnikovn/libphash), a perceptual image hashing library in C. The binding is built with CFFI in API mode: the C sources of libphash are compiled into the extension module `libphash._native`, so a wheel carries the whole library and needs no system libphash.

- **`native/libphash`** — libphash as a git submodule. It always points at a release tag of libphash (`vX.Y.Z`), never at an intermediate commit.
- **Local libphash sources:** `/Users/gudoshnikov_na/Programming/C/libphash`. Read the header, `CHANGELOG.md`, `docs/` and the C code there; do not download libphash. That repository is current C development and may be ahead of the submodule — compare by tag (`git -C native/libphash describe --tags`).

## Versioning

The binding version always has four numbers, `X.Y.Z.N`: `X.Y.Z` is the version of the bundled libphash, `N` is the binding revision on top of it. The first binding for a libphash release is `N = 0`, written out (`2.0.1.0`, then `2.0.1.1`, …); the next libphash release starts at `X.Y.Z.0` again. Tags are `vX.Y.Z.N`. The 1.x line was numbered independently of libphash (1.4.1 bundles libphash 1.10.4).

## Build & test

The project is developed with [uv](https://docs.astral.sh/uv/) (`.python-version`, `uv.lock`).

```bash
git submodule update --init --recursive   # libphash and its vendored decoders
uv sync --extra dev                       # builds the extension in editable mode
uv run pytest                             # tests in tests/, fixtures from native/libphash/tests/data
uv run ruff check . && uv run mypy src
uv build                                  # sdist + wheel into dist/
```

The extension is built by `src/libphash/_build.py` (`cffi_modules` in `setup.py`): `ffibuilder.cdef(...)` declares the C API visible to Python, `set_source(...)` compiles the libphash sources and links the vendored decoders it builds with CMake.

## Architecture

- **`src/libphash/_build.py`** — CFFI build script: the `cdef`, the libphash sources and the decoder build.
- **`src/libphash/_native.pyi`** — type stub for the generated `ffi`/`lib`.
- **`src/libphash/context.py`** — `ImageContext`: owns one `ph_context_t*`, loads an image (path or bytes), exposes settings and one property per hash.
- **`src/libphash/ph_types.py`** — `Digest` (wrapper over `ph_digest_t`) and `HashMethod`.
- **`src/libphash/exceptions.py`** — `PhashError` hierarchy and `check_error()`, which maps a `ph_error_t` to an exception.
- **`src/libphash/utils.py`** — module-level helpers (`get_hash`, `compare_images`, `hamming_distance`, decoder availability).
- **`tests/`** — pytest suite; **`benchmarks/`** — speed and quality comparison with other libraries (datasets in `benchmarks/data/`, not tracked).
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
