"""Build libphash with its own CMake project for the ``libphash._native`` extension.

libphash is configured the way its release builds are, built and installed into a
private prefix; the extension then links the static archives that the install lists
in ``libphash.pc``. The binding never repeats libphash's build logic (decoder selection,
compiler flags, the x86-64 baseline, FP contraction), so a wheel carries the same
library that libphash's CI tests.

Environment:
  LIBPHASH_BUILD_DIR   where the CMake build and install go (default: build/libphash-<platform>)
  LIBPHASH_CMAKE_ARGS  extra arguments for the CMake configure step
  ARCHFLAGS            on macOS, the target architecture (``-arch x86_64``), as cibuildwheel sets it
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NATIVE_DIR = PROJECT_ROOT / "native" / "libphash"
HEADER = NATIVE_DIR / "include" / "libphash.h"


def _osx_architectures() -> str | None:
    archs = re.findall(r"-arch\s+(\S+)", os.environ.get("ARCHFLAGS", ""))
    return ";".join(archs) if archs else None


def _build_dir() -> Path:
    if "LIBPHASH_BUILD_DIR" in os.environ:
        return Path(os.environ["LIBPHASH_BUILD_DIR"]).resolve()
    tag = sysconfig.get_platform()
    archs = _osx_architectures()
    if archs and not tag.endswith(archs.replace(";", "-")):
        tag += "-" + archs.replace(";", "-")
    return PROJECT_ROOT / "build" / f"libphash-{tag}"


def _cmake() -> str:
    cmake = shutil.which("cmake")
    if cmake is None:
        sys.exit(
            "python-libphash: building from source needs CMake >= 3.21 and a C compiler; "
            "`pip install cmake` provides CMake."
        )
    return cmake


def _drop_stale_cache(cmake_dir: Path) -> None:
    """Remove a CMake build tree whose cached tools no longer exist.

    pip and uv build in a temporary environment that provides cmake and ninja and is
    deleted afterwards, while the build tree is kept for the next build; a cache that
    points at the deleted tools would fail every later configure.
    """
    cache = cmake_dir / "CMakeCache.txt"
    if not cache.exists():
        return
    text = cache.read_text(encoding="utf-8", errors="replace")
    for key in ("CMAKE_COMMAND", "CMAKE_MAKE_PROGRAM"):
        m = re.search(rf"^{key}:\w+=(.+)$", text, flags=re.MULTILINE)
        if m and os.path.isabs(m.group(1)) and not os.path.exists(m.group(1)):
            shutil.rmtree(cmake_dir)
            return


def build_libphash() -> Path:
    """Configure, build and install libphash; return the install prefix."""
    if not (NATIVE_DIR / "CMakeLists.txt").exists():
        sys.exit(
            "python-libphash: native/libphash is empty; run "
            "`git submodule update --init --recursive`."
        )
    cmake = _cmake()
    build_dir = _build_dir()
    cmake_dir = build_dir / "build"
    prefix = build_dir / "install"
    _drop_stale_cache(cmake_dir)
    configure = [
        cmake,
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
    if shutil.which("ninja") and not (cmake_dir / "CMakeCache.txt").exists():
        configure += ["-G", "Ninja"]
    archs = _osx_architectures()
    if archs:
        configure.append(f"-DCMAKE_OSX_ARCHITECTURES={archs}")
    configure += shlex.split(os.environ.get("LIBPHASH_CMAKE_ARGS", ""))

    jobs = str(os.cpu_count() or 1)
    subprocess.check_call(configure)
    subprocess.check_call(
        [cmake, "--build", str(cmake_dir), "--config", "Release", "--parallel", jobs]
    )
    subprocess.check_call([cmake, "--install", str(cmake_dir), "--config", "Release"])
    return prefix


def link_arguments(prefix: Path) -> dict[str, list]:
    """Read ``libphash.pc`` from the install prefix into ``Extension`` arguments."""
    pc = next(prefix.glob("lib*/pkgconfig/libphash.pc"))
    variables = {"pcfiledir": str(pc.parent)}
    fields: dict[str, str] = {}
    for line in pc.read_text(encoding="utf-8").splitlines():
        expanded = re.sub(r"\$\{(\w+)\}", lambda m: variables[m.group(1)], line)
        if re.match(r"^\w+=", expanded):
            key, _, value = expanded.partition("=")
            variables[key] = value.strip()
        elif ":" in expanded:
            key, _, value = expanded.partition(":")
            fields[key.strip()] = value.strip()

    args: dict[str, list] = {
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

    lib_dirs: list[Path] = []
    libs = shlex.split(fields.get("Libs", "")) + shlex.split(
        fields.get("Libs.private", "")
    )
    for flag in libs:
        if flag.startswith("-L"):
            lib_dirs.append(Path(flag[2:]))
        elif flag.startswith("-l"):
            name = flag[2:]
            # An archive of the install is linked by its path: with -lz the linker
            # could pick the system zlib over the bundled zlib-ng.
            candidates = [d / f"lib{name}.a" for d in lib_dirs] + [
                d / f"{name}.lib" for d in lib_dirs
            ]
            archive = next((c for c in candidates if c.exists()), None)
            if archive is not None:
                args["extra_objects"].append(str(archive))
            else:
                args["libraries"].append(name)
        else:
            args["extra_link_args"].append(flag)

    # Only PyInit__native leaves the extension; the vendored decoders' symbols stay
    # inside it and cannot interpose on another copy of the same library.
    if sys.platform == "darwin":
        args["extra_link_args"].append("-Wl,-exported_symbol,_PyInit__native")
    elif sys.platform.startswith("linux"):
        args["extra_link_args"].append("-Wl,--exclude-libs,ALL")
    return args
