"""Build the CFFI extension, with libphash built by its own CMake project first."""

import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.bdist_wheel import bdist_wheel
from setuptools.command.build_ext import build_ext
from setuptools.command.sdist import sdist

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import sbom
import sdist as reproducible

from native import build_libphash, link_arguments


class BuildExt(build_ext):
    """Build libphash with CMake, then compile and link the CFFI extension against it.

    The C build runs here rather than when setup.py is loaded, so that an sdist is made
    without a compiler or CMake.
    """

    def run(self) -> None:
        """Build libphash, then the extensions with its link arguments."""
        args = link_arguments(build_libphash())
        for ext in self.extensions:
            ext.include_dirs.extend(args["include_dirs"])
            ext.define_macros.extend(args["define_macros"])
            ext.extra_objects.extend(args["extra_objects"])
            ext.libraries.extend(args["libraries"])
            ext.extra_link_args.extend(args["extra_link_args"])
        super().run()


class BdistWheel(bdist_wheel):
    """Add the SBOM of the statically linked libraries to the wheel (PEP 770)."""

    def egg2dist(self, egginfo_path: str, distinfo_path: str) -> None:
        """Write the .dist-info directory, then its sboms/ entry."""
        super().egg2dist(egginfo_path, distinfo_path)
        sbom.write(Path(distinfo_path) / "sboms", self.distribution.get_version())


class Sdist(sdist):
    """Write the sdist so that the same sources give the same bytes."""

    def make_distribution(self) -> None:
        """Make the archives, then rewrite each reproducibly."""
        super().make_distribution()
        for archive in self.archive_files:
            reproducible.normalize(Path(archive))


setup(
    cffi_modules=["tools/ffi.py:ffibuilder"],
    cmdclass={"build_ext": BuildExt, "bdist_wheel": BdistWheel, "sdist": Sdist},
)
