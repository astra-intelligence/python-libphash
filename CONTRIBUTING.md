# Contributing to python-libphash

Thanks for considering a contribution. This file covers building from source, what a pull
request needs before it can be reviewed, and how versions and releases work. The C
library itself is [libphash](https://github.com/gudoshnikovn/libphash): a change to a
hash, a decoder or the C API belongs there, and reaches this binding with the next
libphash release.

## Getting started

The project is developed with [uv](https://docs.astral.sh/uv/). A C compiler is needed;
CMake and Ninja come from PyPI. On Windows the compiler is MSVC (Visual Studio Build
Tools).

```bash
git clone https://github.com/gudoshnikovn/python-libphash.git
cd python-libphash
git submodule update --init --recursive   # libphash and its vendored decoders
uv sync --all-extras --inexact            # builds the extension in editable mode
uv run pytest
```

`native/libphash` is libphash as a git submodule, pinned to one of its release tags. The
build runs libphash's own CMake project and links the static library into the extension
module, so an installed wheel needs no system libphash. After a change to the C side or
to `tools/`, rebuild with `uv sync --all-extras --inexact --reinstall-package
python-libphash`.

`uv sync` without `--inexact` removes from `.venv` the packages the lock file does not
list.

## Before opening a pull request

Each of these must pass; CI runs them all on every pull request:

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy && uv run basedpyright       # both strict, over src/, tests/ and tools/
uv run python tools/stub.py --check      # src/libphash/_native.pyi matches the module
uv run typos
```

- **Coverage is 100 %** of lines and branches, combined over the platforms CI runs on:

  ```bash
  uv run coverage run -m pytest && uv run coverage combine && uv run coverage report
  ```

  A line that runs only on Windows or only on POSIX counts once combined, so a local
  report on one platform can show it as missed.
- **Every mutant is caught.** CI runs [mutmut](https://github.com/boxed/mutmut) over
  `src/libphash/` weekly and on pull requests that change the package. A surviving
  mutant fails the run unless `tests/equivalent_mutants.json` lists it with the reason
  it cannot be caught. Locally (Linux and macOS):

  ```bash
  LIBPHASH_BUILD_DIR=$PWD/build/libphash-<platform> uv run mutmut run
  uv run python tools/mutants.py
  ```

- **The binding matches C.** `tests/test_c_parity.py` builds a small C program against
  the same libphash install and requires the binding's hashes and error codes to equal
  it for every fixture, setting and pixel layout. It needs CMake; without it the tests
  skip locally and fail in CI.
- **A change to the stub's inputs regenerates it**: `uv run python tools/stub.py`.

Sanitizer builds (AddressSanitizer with UndefinedBehaviorSanitizer, ThreadSanitizer) and
the fuzz targets need Linux with Clang; `tools/sanitizers.py` and `tools/fuzz.py` say
how to run them.

## Style

- Code, comments, docstrings and documentation are in English, with American spelling.
- [ruff](https://docs.astral.sh/ruff/) checks and formats the code. An exception to a
  rule is a per-file ignore with a comment, or `# noqa: CODE -- reason`; never a bare
  `noqa`.
- Docstrings follow PEP 257: a one-line summary in the imperative, then the details.
- Public signatures are fully typed and use protocols rather than `Any`. A type a
  caller needs to annotate their own code is exported from `libphash`.
- The public API is what `libphash/__init__.py` exports; every other module is private
  (`_name.py`) except `exceptions.py`.
- Comments and documentation describe the code as it is, in the present tense. A test
  comment states the contract the test holds.

## Commits and pull requests

- Commit messages: a short summary line, in English, prefixed with the kind of change
  as in the repository's history (`fix:`, `feat:`, `test:`, `docs:`, `ci:`, `build:`,
  `refactor:`, `perf:`), and a body when the reason is not obvious from the diff.
- A change a user of the package can observe (new API, changed behavior, a fixed bug, a
  changed default) adds a line to `CHANGELOG.md` under `[Unreleased]`. A change that
  breaks existing callers goes under `BREAKING CHANGES`, with the way to adapt or a link
  to `MIGRATION.md`.
- Pull requests target `main`, one logical change each. Fork the repository, branch off
  `main`, and open the pull request from your branch.

## Versions

The version has four numbers, `X.Y.Z.N`. `X.Y.Z` is the version of the bundled
libphash; `N` is the revision of the binding on top of it, starting at `0` for each
libphash release and always written out (`2.0.1.0`, then `2.0.1.1`). A change to the
binding alone raises `N`; a new libphash release starts a new `X.Y.Z.0`. Tags are
`vX.Y.Z.N`, and `src/libphash/_version.py` is the only place the version is written.

Hash values depend only on `X.Y.Z` and the configuration: a binding revision never
changes a hash.

## Supported platforms and Python versions

- **Wheels** are built for the platforms libphash's own CI tests: Linux x86-64 and arm64
  (manylinux, glibc), macOS arm64 and Windows x86-64. Elsewhere pip builds the sdist,
  which needs a C compiler. x86-64 wheels need a CPU with SSE4.2 and POPCNT
  (x86-64-v2).
- **Python**: every CPython version from the oldest in `requires-python` to the newest
  release, the free-threaded builds included. A Python version that reaches its end of
  life is dropped in the next `X.Y.Z.0`.
- **Releases**: only the newest release receives fixes. A fix to libphash or one of its
  vendored decoders reaches this package as the next `X.Y.Z.0`, or as a binding
  revision when the binding alone changes.

## Releases

A release is cut from a `release/vX.Y.Z.N` branch. The version in `_version.py`, the
`CHANGELOG.md` entry with its date and the tag must agree; the release workflow
(`release.yml`) checks them, and that the tag is signed and the submodule sits on
libphash's tag, before it uploads anything.

Each libphash release gets its binding:

1. Move `native/libphash` to the new tag
   (`git -C native/libphash checkout vX.Y.Z`, with its submodules updated).
2. Set the version to `X.Y.Z.0` and add the `CHANGELOG.md` entry, taking from libphash's
   changelog what a Python user observes.
3. Regenerate the stub (`uv run python tools/stub.py`) and adapt the binding to any new
   or changed C API; `tests/test_cdef.py` fails for a header function that is neither
   wrapped nor listed as deliberately unwrapped.
4. Run CI, the wheels workflow included (it runs when the submodule changes).

## Reporting a security issue

Do not open a public issue or pull request for a vulnerability. See
[`SECURITY.md`](https://github.com/gudoshnikovn/python-libphash/blob/main/SECURITY.md) for the private channel.

## License

By contributing, you agree that your contribution is licensed under the project's
[MIT license](https://github.com/gudoshnikovn/python-libphash/blob/main/LICENSE).
