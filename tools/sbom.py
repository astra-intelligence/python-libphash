"""Write the software bill of materials of the extension module.

The wheel links libphash and the libraries it vendors statically, so no installer can
see them; the SBOM names each one with its version, read from the sources the build
compiles (never written by hand), its license and where it comes from. The format is
CycloneDX 1.6 JSON, placed in the wheel's ``.dist-info/sboms/`` (PEP 770) by
``setup.py`` and attached to the GitHub Release. The output has no timestamp or serial
number, so the same sources give the same bytes.

Run as a script, it prints the SBOM of the checkout::

    python tools/sbom.py [--version X.Y.Z.N]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TypedDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIBPHASH = PROJECT_ROOT / "native" / "libphash"
FILE_NAME = "python-libphash.cdx.json"


class Component(TypedDict):
    """One library linked into the extension."""

    name: str
    version: str
    license: str
    purl: str
    url: str


def _read(path: Path, pattern: str) -> str:
    """Return the first group of ``pattern`` in the file, or fail naming both."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError(f"no version: cannot read {path}: {exc}") from exc
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise RuntimeError(f"no version in {path} (pattern {pattern!r})")
    return match.group(1)


def components(root: Path = LIBPHASH) -> list[Component]:
    """Return libphash and every library it links in, with versions from ``root``."""
    vendor = root / "vendor"
    notices = root / "THIRD-PARTY-NOTICES.md"

    def stb(header: str) -> str:
        # THIRD-PARTY-NOTICES.md names the copied-in stb headers' versions.
        pattern = rf"\*\*Vendored version:\*\* v([\d.]+)[^\n]*`vendor/{header}`"
        return _read(notices, pattern)

    def component(name: str, version: str, spdx: str, repo: str) -> Component:
        return {
            "name": name,
            "version": version,
            "license": spdx,
            "purl": f"pkg:github/{repo}@{version}",
            "url": f"https://github.com/{repo}",
        }

    return [
        component(
            "libphash",
            _read(root / "CMakeLists.txt", r"project\(libphash VERSION ([\d.]+)"),
            "MIT",
            "gudoshnikovn/libphash",
        ),
        component(
            "libjpeg-turbo",
            _read(
                vendor / "libjpeg-turbo" / "CMakeLists.txt", r"^set\(VERSION ([\d.]+)"
            ),
            "IJG AND Zlib",
            "libjpeg-turbo/libjpeg-turbo",
        ),
        component(
            "libpng",
            _read(
                vendor / "libpng" / "png.h",
                r'^#define PNG_LIBPNG_VER_STRING "([\d.]+)"',
            ),
            "libpng-2.0",
            "pnggroup/libpng",
        ),
        component(
            "libwebp",
            _read(
                vendor / "libwebp" / "configure.ac",
                r"^AC_INIT\(\[libwebp\], \[([\d.]+)\]",
            ),
            "BSD-3-Clause",
            "webmproject/libwebp",
        ),
        component(
            "zlib-ng",
            _read(
                vendor / "zlib-ng" / "zlib-ng.h.in",
                r'^#define ZLIBNG_VERSION "([\d.]+)"',
            ),
            "Zlib",
            "zlib-ng/zlib-ng",
        ),
        component("stb_image", stb("stb_image.h"), "MIT OR Unlicense", "nothings/stb"),
        component(
            "stb_image_resize2",
            stb("stb_image_resize2.h"),
            "MIT OR Unlicense",
            "nothings/stb",
        ),
    ]


def sbom(version: str, root: Path = LIBPHASH) -> dict[str, object]:
    """Return the CycloneDX document for python-libphash ``version``."""
    parts = components(root)
    libraries: list[dict[str, object]] = [
        {
            "type": "library",
            "bom-ref": c["purl"],
            "name": c["name"],
            "version": c["version"],
            "licenses": [{"expression": c["license"]}],
            "purl": c["purl"],
            "externalReferences": [{"type": "vcs", "url": c["url"]}],
        }
        for c in parts
    ]
    package = f"pkg:pypi/python-libphash@{version}"
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "library",
                "bom-ref": package,
                "name": "python-libphash",
                "version": version,
                "licenses": [{"expression": "MIT"}],
                "purl": package,
            },
        },
        "components": libraries,
        "dependencies": [
            {"ref": package, "dependsOn": [c["purl"] for c in parts]},
        ],
    }


def write(directory: Path, version: str, root: Path = LIBPHASH) -> Path:
    """Write the SBOM into ``directory`` and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / FILE_NAME
    text = json.dumps(sbom(version, root), indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _package_version() -> str:
    return _read(
        PROJECT_ROOT / "src" / "libphash" / "_version.py", r'__version__ = "([^"]+)"'
    )


def main() -> None:
    """Print the SBOM of the checkout."""
    parser = argparse.ArgumentParser(description="Print the SBOM of the checkout.")
    parser.add_argument("--version", default=None, help="package version to name")
    args = parser.parse_args()
    version = args.version or _package_version()
    json.dump(sbom(version), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
