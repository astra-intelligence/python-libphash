import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_ext import build_ext

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from native import build_libphash, link_arguments  # noqa: E402


class BuildExt(build_ext):
    """Build libphash with CMake, then compile and link the CFFI extension against it.

    The C build runs here rather than when setup.py is loaded, so that an sdist is made
    without a compiler or CMake.
    """

    def run(self) -> None:
        args = link_arguments(build_libphash())
        for ext in self.extensions:
            ext.include_dirs.extend(args["include_dirs"])
            ext.define_macros.extend(args["define_macros"])
            ext.extra_objects.extend(args["extra_objects"])
            ext.libraries.extend(args["libraries"])
            ext.extra_link_args.extend(args["extra_link_args"])
        super().run()


setup(
    cffi_modules=["tools/ffi.py:ffibuilder"],
    cmdclass={"build_ext": BuildExt},
)
