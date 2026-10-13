"""Check built wheels and sdists before they are published.

Run from the project root on each artifact::

    python tools/audit.py dist/*.whl dist/*.tar.gz

A wheel must hold the package and nothing else, declare its licenses and carry every
license file, carry the SBOM of what it links (``.dist-info/sboms/``) for its own
version, and its extension module must export only ``PyInit__native`` and depend only on
the system libraries a wheel may assume: the decoders linked into it stay invisible to
other copies of the same libraries in the process (Pillow, OpenCV). An sdist must
carry what an offline build reads, its licenses and nothing of the development tree,
written reproducibly. Every problem is printed and the exit status is 1 if there was
any; with ``GITHUB_STEP_SUMMARY`` set, a table of the artifacts and their sizes is
added to the job summary. The binary checks read ELF, Mach-O and PE files with LIEF.
"""

from __future__ import annotations

import email.message
import email.parser
import json
import os
import re
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import cast

from setuptools.config.pyprojecttoml import read_configuration

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Libraries an extension module may import, by binary format: what every target
#: system has (manylinux_2_28's policy for Linux; the C runtime on Windows) and the
#: Python DLL. Matched case-insensitively against the start of the name.
ALLOWED_LIBRARIES = {
    "ELF": (
        "libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2", "librt.so.1",
        "ld-linux-x86-64.so.2", "ld-linux-aarch64.so.1", "libgcc_s.so.1",
    ),
    "MachO": ("/usr/lib/libSystem.B.dylib",),
    "PE": (
        "kernel32.dll", "vcruntime140.dll", "vcruntime140_1.dll", "api-ms-win-crt-",
        "python3",
    ),
}  # fmt: skip

#: What an sdist must and must not contain, as paths inside its top directory.
SDIST_REQUIRED = (
    "PKG-INFO",
    "pyproject.toml",
    "setup.py",
    "LICENSE",
    "src/libphash/__init__.py",
    "src/libphash/_native.pyi",
    "src/libphash/py.typed",
    "tools/cdef.py",
    "tools/ffi.py",
    "tools/native.py",
    "tools/sbom.py",
    "tools/sdist.py",
    "native/libphash/CMakeLists.txt",
    "native/libphash/include/libphash.h",
    "native/libphash/THIRD-PARTY-NOTICES.md",
    "native/libphash/vendor/libjpeg-turbo/CMakeLists.txt",
    "native/libphash/vendor/libpng/png.h",
    "native/libphash/vendor/libwebp/CMakeLists.txt",
    "native/libphash/vendor/zlib-ng/CMakeLists.txt",
    "native/libphash/vendor/stb_image.h",
)
SDIST_FORBIDDEN = re.compile(
    r"(^|/)\.git(/|$)|(^|/)\.github/|^tests/|^tmp/|^build/|^dist/|^benchmarks/"
    r"|^native/libphash/(tests|docs|examples|tasks|tmp|papers)/|\.DS_Store$"
)


def _pyproject() -> dict[str, object]:
    project: dict[str, object] = read_configuration(PROJECT_ROOT / "pyproject.toml")[
        "project"
    ]
    return project


def _license_files() -> list[str]:
    files = _pyproject()["license-files"]
    if not isinstance(files, list):
        raise TypeError("pyproject.toml: license-files is not a list")
    return [str(f) for f in cast("list[object]", files)]


# --- Wheels ---------------------------------------------------------------------------


def audit_wheel(path: Path) -> list[str]:
    """Return the problems of one wheel."""
    problems: list[str] = []
    name, version, *_ = path.name.removesuffix(".whl").split("-")
    dist_info = f"{name}-{version}.dist-info"
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        problems += _wheel_files(names, dist_info)
        metadata = email.parser.Parser().parsestr(
            wheel.read(f"{dist_info}/METADATA").decode()
        )
        problems += _metadata(metadata, version, names, dist_info)
        problems += _sbom(wheel, f"{dist_info}/sboms/python-libphash.cdx.json", version)
        modules = [n for n in names if re.fullmatch(r"libphash/_native\..*(so|pyd)", n)]
        if len(modules) != 1:
            problems.append(f"expected one extension module, found {modules}")
        for module in modules:
            problems += _binary(wheel.read(module), module)
    return problems


def _wheel_files(names: list[str], dist_info: str) -> list[str]:
    allowed = re.compile(
        r"libphash/[a-z_]+\.py|libphash/_native\.pyi|libphash/py\.typed"
        r"|libphash/_native\..*(so|pyd)"
        rf"|{re.escape(dist_info)}/(METADATA|WHEEL|RECORD|top_level\.txt"
        r"|licenses/.+|sboms/.+)"
    )
    return [
        f"unexpected file in the wheel: {n}" for n in names if not allowed.fullmatch(n)
    ]


def _metadata(
    metadata: email.message.Message, version: str, names: list[str], dist_info: str
) -> list[str]:
    problems: list[str] = []
    project = _pyproject()
    if metadata["Version"] != version:
        problems.append(
            f"METADATA Version {metadata['Version']} != file name {version}"
        )
    if metadata["License-Expression"] != project["license"]:
        problems.append(f"License-Expression is {metadata['License-Expression']!r}")
    if metadata["Requires-Python"] != project["requires-python"]:
        problems.append(f"Requires-Python is {metadata['Requires-Python']!r}")
    declared = [str(f) for f in metadata.get_all("License-File") or []]
    expected = _license_files()
    if declared != expected:
        problems.append(f"License-File entries {declared} != {expected}")
    problems += [
        f"license file missing from the wheel: {f}"
        for f in declared
        if f"{dist_info}/licenses/{f}" not in names
    ]
    return problems


def _sbom(wheel: zipfile.ZipFile, member: str, version: str) -> list[str]:
    try:
        doc = json.loads(wheel.read(member))
    except KeyError:
        return [f"no SBOM: {member}"]
    problems: list[str] = []
    if doc.get("bomFormat") != "CycloneDX":
        problems.append("the SBOM is not CycloneDX")
    if doc["metadata"]["component"]["version"] != version:
        problems.append("the SBOM names another package version")
    libphash = [c for c in doc["components"] if c["name"] == "libphash"]
    if [c["version"] for c in libphash] != [version.rsplit(".", 1)[0]]:
        problems.append("the SBOM's libphash version is not X.Y.Z of the package's")
    return problems


def _binary(data: bytes, member: str) -> list[str]:
    import lief  # noqa: PLC0415 -- only the binary check needs it

    # One overload of lief.parse (a file object) is untyped in its stub.
    binary = lief.parse(list(data))  # pyright: ignore[reportUnknownMemberType]
    if isinstance(binary, lief.ELF.Binary):
        fmt, libraries = "ELF", [_text(n) for n in binary.libraries]
    elif isinstance(binary, lief.MachO.Binary):
        fmt, libraries = "MachO", [_text(d.name) for d in binary.libraries]
    elif isinstance(binary, lief.PE.Binary):
        fmt, libraries = "PE", [_text(i.name) for i in binary.imports]
    else:
        return [f"{member}: not an ELF, Mach-O or PE binary"]
    # Mach-O symbols carry the C compiler's leading underscore.
    exported = {_text(f.name) for f in binary.exported_functions}
    if fmt == "MachO":
        exported = {e.removeprefix("_") for e in exported}
    problems: list[str] = []
    if exported != {"PyInit__native"}:
        extra = sorted(exported - {"PyInit__native"})[:20]
        problems.append(f"{member}: exports more than PyInit__native: {extra}")
    allowed = tuple(a.lower() for a in ALLOWED_LIBRARIES[fmt])
    problems += [
        f"{member}: depends on {library}"
        for library in libraries
        if not library.lower().startswith(allowed)
    ]
    return problems


def _text(value: str | bytes) -> str:
    return value if isinstance(value, str) else value.decode(errors="replace")


# --- sdists ---------------------------------------------------------------------------


def audit_sdist(path: Path) -> list[str]:
    """Return the problems of one sdist."""
    problems: list[str] = []
    with tarfile.open(path) as sdist:
        members = sdist.getmembers()
    top = path.name.removesuffix(".tar.gz")
    names: set[str] = set()
    for member in members:
        parts = PurePosixPath(member.name).parts
        if parts[0] != top:
            problems.append(f"entry outside {top}/: {member.name}")
            continue
        inner = "/".join(parts[1:])
        names.add(inner)
        if inner and SDIST_FORBIDDEN.search(inner):
            problems.append(f"development file in the sdist: {inner}")
        if (member.uid, member.gid, member.uname, member.gname) != (0, 0, "", ""):
            problems.append(f"owner not cleared (not reproducible): {member.name}")
    problems += [
        f"missing from the sdist: {r}" for r in SDIST_REQUIRED if r not in names
    ]
    for license_file in _pyproject()["license-files"]:  # type: ignore[attr-defined]
        if license_file not in names:
            problems.append(f"license file missing from the sdist: {license_file}")
    return problems


# --- Command line ---------------------------------------------------------------------


def main(paths: list[str]) -> int:
    """Audit every artifact named; return the exit status."""
    if not paths:
        print("usage: python tools/audit.py ARTIFACT...", file=sys.stderr)  # noqa: T201
        return 2
    rows: list[str] = []
    failed = False
    for name in paths:
        path = Path(name)
        problems = audit_wheel(path) if path.suffix == ".whl" else audit_sdist(path)
        size = path.stat().st_size / 1024 / 1024
        rows.append(f"| `{path.name}` | {size:.2f} MiB | {len(problems) or 'ok'} |")
        for problem in problems:
            print(f"{path.name}: {problem}")  # noqa: T201
        print(f"{path.name}: {'FAILED' if problems else 'ok'} ({size:.2f} MiB)")  # noqa: T201
        failed = failed or bool(problems)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as f:
            f.write("| Artifact | Size | Problems |\n|---|---|---|\n")
            f.write("\n".join(rows) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
