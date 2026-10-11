"""Build libphash with its own CMake project for the ``libphash._native`` extension.

libphash is configured the way its release builds are, built and installed into a
private prefix; the extension then links the static archives that the install lists
in ``libphash.pc``. The binding never repeats libphash's build logic (decoder selection,
compiler flags, the x86-64 baseline, FP contraction), so a wheel carries the same
library that libphash's CI tests.

Environment:
  LIBPHASH_BUILD_DIR   where the CMake build and install go
                       (default: build/libphash-<platform>)
  LIBPHASH_CMAKE_ARGS  extra arguments for the CMake configure step
  CMAKE_GENERATOR      the CMake generator (default: Visual Studio for the running
                       Python's architecture on Windows, Ninja elsewhere if installed)
  ARCHFLAGS            on macOS, the target architecture (``-arch x86_64``), as
                       cibuildwheel sets it
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import TypedDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NATIVE_DIR = PROJECT_ROOT / "native" / "libphash"
HEADER = NATIVE_DIR / "include" / "libphash.h"


def osx_architectures() -> str | None:
    """Return the CMake architectures that ``ARCHFLAGS`` asks for, if it does."""
    archs = re.findall(r"-arch\s+(\S+)", os.environ.get("ARCHFLAGS", ""))
    return ";".join(archs) if archs else None


def build_dir() -> Path:
    """Return the directory that holds libphash's CMake build and install."""
    if "LIBPHASH_BUILD_DIR" in os.environ:
        return Path(os.environ["LIBPHASH_BUILD_DIR"]).resolve()
    tag = sysconfig.get_platform()
    archs = osx_architectures()
    if archs and not tag.endswith(archs.replace(";", "-")):
        tag += "-" + archs.replace(";", "-")
    return PROJECT_ROOT / "build" / f"libphash-{tag}"


def _cmake() -> str:
    cmake = shutil.which("cmake")
    if cmake is None:
        sys.exit(
            "python-libphash: building from source needs CMake >= 3.21 and a C "
            "compiler; `pip install cmake` provides CMake."
        )
    return cmake


# The Visual Studio platform of each Windows build of CPython.
_VS_PLATFORMS = {"win-amd64": "x64", "win32": "Win32", "win-arm64": "ARM64"}


def generator() -> list[str]:
    """Return the CMake generator arguments for a fresh build tree.

    On Windows the generator is Visual Studio for the architecture of the running
    Python: the extension is compiled by MSVC, which links only archives that MSVC
    built, and with Ninja CMake would take whichever compiler comes first on PATH
    (MinGW's gcc on GitHub's runners). Elsewhere Ninja is used when it is installed.
    A generator chosen through ``CMAKE_GENERATOR`` is left to CMake.
    """
    if "CMAKE_GENERATOR" in os.environ:
        return []
    if sys.platform == "win32":
        platform = _VS_PLATFORMS.get(sysconfig.get_platform())
        return ["-A", platform] if platform else []
    return ["-G", "Ninja"] if shutil.which("ninja") else []


def tools_missing(cmake_dir: Path) -> bool:
    """Tell whether a CMake build tree points at a cmake or ninja that no longer exists.

    pip and uv build in a temporary environment that provides cmake and ninja and is
    deleted afterwards, while the build tree is kept for the next build. The paths of
    those tools are written into the generated build files, the cache, and the caches
    of the vendored decoders' own builds, so such a tree cannot be configured again.
    """
    cache = cmake_dir / "CMakeCache.txt"
    if not cache.exists():
        return False
    text = cache.read_text(encoding="utf-8", errors="replace")
    for key in ("CMAKE_COMMAND", "CMAKE_MAKE_PROGRAM"):
        m = re.search(rf"^{key}:\w+=(.+)$", text, flags=re.MULTILINE)
        if m and os.path.isabs(m.group(1)) and not os.path.exists(m.group(1)):
            return True
    return False


# The environment variables that change what CMake or the compiler produce.
_BUILD_ENVIRONMENT = (
    "CC",
    "CFLAGS",
    "CPPFLAGS",
    "LDFLAGS",
    "AR",
    "MACOSX_DEPLOYMENT_TARGET",
    "SDKROOT",
    "CMAKE_GENERATOR",
    "CMAKE_GENERATOR_PLATFORM",
    "CMAKE_GENERATOR_TOOLSET",
    "CMAKE_TOOLCHAIN_FILE",
)


def _inputs_digest(cmake: str, configure: list[str]) -> str:
    """Return a digest of everything the libphash install is built from.

    The configure arguments, the CMake version, the build environment, and the path,
    size and modification time of every file of native/libphash: the same digest
    means a configure and build would produce the same install.
    """
    version = subprocess.run(
        [cmake, "--version"], capture_output=True, text=True, check=True
    ).stdout
    h = hashlib.sha256()
    h.update("\0".join(configure).encode())
    h.update(version.encode())
    for name in _BUILD_ENVIRONMENT:
        h.update(f"\0{name}={os.environ.get(name, '')}".encode())
    for root, dirs, files in os.walk(NATIVE_DIR):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(files):
            path = os.path.join(root, name)
            st = os.stat(path)
            h.update(f"\0{path}\0{st.st_size}\0{st.st_mtime_ns}".encode())
    return h.hexdigest()


def build_libphash() -> Path:
    """Configure, build and install libphash; return the install prefix.

    A build tree whose tools are gone (see ``tools_missing``) is not configured
    again: when the install was built from the same inputs, it is used as it is, and
    otherwise the tree is built from scratch. cibuildwheel builds the wheel of each
    Python in a fresh environment, so every wheel after the first reuses the install.
    """
    if not (NATIVE_DIR / "CMakeLists.txt").exists():
        sys.exit(
            "python-libphash: native/libphash is empty; run "
            "`git submodule update --init --recursive`."
        )
    cmake = _cmake()
    build_root = build_dir()
    cmake_dir = build_root / "build"
    prefix = build_root / "install"
    configure = [
        "-S",
        str(NATIVE_DIR),
        "-B",
        str(cmake_dir),
        "-DCMAKE_BUILD_TYPE=Release",
        # The extension is a shared object that links these archives.
        "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
        "-DPHASH_BUILD_SHARED=OFF",
        "-DPHASH_BUILD_TESTS=OFF",
        # A missing vendored decoder fails the build instead of producing a wheel that
        # decodes JPEG with stb_image and so gives different hashes.
        "-DPHASH_STRICT_DEPS=ON",
        # A wheel runs on CPUs other than the build machine's.
        "-DPHASH_OPTIMIZE_NATIVE=OFF",
        f"-DCMAKE_INSTALL_PREFIX={prefix}",
    ]
    archs = osx_architectures()
    if archs:
        configure.append(f"-DCMAKE_OSX_ARCHITECTURES={archs}")
    configure += shlex.split(os.environ.get("LIBPHASH_CMAKE_ARGS", ""))
    generator_args = generator()

    digest_file = build_root / "inputs.sha256"
    digest = _inputs_digest(cmake, configure + generator_args)
    if tools_missing(cmake_dir):
        built = digest_file.read_text() if digest_file.exists() else ""
        if built == digest and next(prefix.glob("lib*/pkgconfig/libphash.pc"), None):
            return prefix
        shutil.rmtree(cmake_dir)
    digest_file.unlink(missing_ok=True)
    if not (cmake_dir / "CMakeCache.txt").exists():
        configure += generator_args

    jobs = str(os.cpu_count() or 1)
    subprocess.check_call([cmake, *configure])
    subprocess.check_call(
        [cmake, "--build", str(cmake_dir), "--config", "Release", "--parallel", jobs]
    )
    subprocess.check_call([cmake, "--install", str(cmake_dir), "--config", "Release"])
    digest_file.write_text(digest)
    return prefix


class LinkArguments(TypedDict):
    """The ``setuptools.Extension`` fields that link libphash."""

    include_dirs: list[str]
    define_macros: list[tuple[str, str | None]]
    extra_objects: list[str]
    libraries: list[str]
    extra_link_args: list[str]


def _read_pc(pc: Path) -> dict[str, str]:
    """Return the fields of a pkg-config file (``Cflags``, ``Libs``, …), expanded."""
    # Forward slashes: the fields are split with shell quoting, which would take the
    # backslashes of a Windows path as escapes.
    variables = {"pcfiledir": pc.parent.as_posix()}
    fields: dict[str, str] = {}
    for line in pc.read_text(encoding="utf-8").splitlines():
        expanded = re.sub(r"\$\{(\w+)\}", lambda m: variables[m.group(1)], line)
        if re.match(r"^\w+=", expanded):
            key, _, value = expanded.partition("=")
            variables[key] = value.strip()
        elif ":" in expanded:
            key, _, value = expanded.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def link_arguments(prefix: Path) -> LinkArguments:
    """Read ``libphash.pc`` from the install prefix into ``Extension`` arguments."""
    fields = _read_pc(next(prefix.glob("lib*/pkgconfig/libphash.pc")))
    args: LinkArguments = {
        "include_dirs": [],
        "define_macros": [],
        "extra_objects": [],
        "libraries": [],
        "extra_link_args": [],
    }
    for flag in shlex.split(fields.get("Cflags", "")):
        if flag.startswith("-I"):
            args["include_dirs"].append(flag[2:])
        elif flag.startswith("-D"):
            name, _, value = flag[2:].partition("=")
            args["define_macros"].append((name, value or None))

    libs = shlex.split(fields.get("Libs", "")) + shlex.split(
        fields.get("Libs.private", "")
    )
    lib_dirs = [Path(f[2:]) for f in libs if f.startswith("-L")]
    if sys.platform == "win32":
        # libphash.pc names the archives as on Unix, while MSVC builds name some files
        # otherwise (libwebpdecoder.lib, zlibstatic.lib). The install's lib directory
        # holds exactly libphash and the archives it links, and the MSVC linker takes
        # them in any order, so all of them are linked.
        for d in lib_dirs:
            args["extra_objects"] += sorted(str(f) for f in d.glob("*.lib"))
    for flag in libs:
        if flag.startswith("-L") or (flag.startswith("-l") and sys.platform == "win32"):
            continue
        if not flag.startswith("-l"):
            args["extra_link_args"].append(flag)
            continue
        name = flag[2:]
        # An archive of the install is linked by its path: with -lz the linker could
        # pick the system zlib over the bundled zlib-ng.
        archive = next(
            (d / f"lib{name}.a" for d in lib_dirs if (d / f"lib{name}.a").exists()),
            None,
        )
        if archive is not None:
            args["extra_objects"].append(str(archive))
        else:
            args["libraries"].append(name)

    # Only PyInit__native leaves the extension; the vendored decoders' symbols stay
    # inside it and cannot interpose on another copy of the same library.
    if sys.platform == "darwin":
        args["extra_link_args"].append("-Wl,-exported_symbol,_PyInit__native")
    elif sys.platform.startswith("linux"):
        args["extra_link_args"].append("-Wl,--exclude-libs,ALL")
    return args
