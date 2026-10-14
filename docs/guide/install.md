# Installing

```bash
pip install python-libphash
```

## Wheels

Wheels exist for the platforms libphash's own CI builds and tests:

| Platform | Wheel |
|---|---|
| Linux x86-64 (glibc 2.28 or later) | `manylinux_2_28_x86_64` |
| Linux arm64 (glibc 2.28 or later) | `manylinux_2_28_aarch64` |
| macOS arm64 (11 or later) | `macosx_11_0_arm64` |
| Windows x86-64 | `win_amd64` |

for every CPython from 3.10 on, and for the free-threaded builds from 3.14t on: one
`abi3` wheel per platform serves every CPython with the GIL, a later release of Python
included, and each free-threaded version has a wheel of its own. Each
wheel links libphash and its decoders statically (libjpeg-turbo, libpng, libwebp,
zlib-ng, stb_image), and needs only the system's C library: no system libpng or libjpeg
is used, and the decoders inside cannot clash with another copy of the same libraries in
the process, such as Pillow's or OpenCV's.

**x86-64 wheels need a CPU with SSE4.2 and POPCNT** (x86-64-v2: Intel since 2008, AMD
since 2011), the baseline libphash is built for. libjpeg-turbo and libwebp choose faster
instructions (AVX2) at run time where the CPU has them.

To see what an installed wheel carries:

```python
import libphash as ph

print(ph.__version__)            # 2.0.1.1
print(ph.libphash_version())     # 2.0.1
print(ph.build_info())           # version=2.0.1 jpeg=libjpeg-turbo png=libpng ...
```

Each wheel also carries a software bill of materials, `python_libphash-*.dist-info/sboms/`,
naming every library linked into it with its version.

## Building from source

On any other platform pip builds the sdist, which needs a C compiler (GCC or Clang;
Visual Studio Build Tools on Windows). CMake and Ninja come from PyPI. The sdist carries
libphash and its vendored decoders, so the build needs no network once the build
requirements are installed.

From a clone:

```bash
git clone https://github.com/gudoshnikovn/python-libphash.git
cd python-libphash
git submodule update --init --recursive
pip install .
```

The build runs libphash's own CMake project with its release settings (static, the full
decoder set, `-ffp-contract=off`, hidden symbols), so a source build hashes like a wheel.
On macOS, `ARCHFLAGS` chooses the architecture (`ARCHFLAGS="-arch x86_64"`); on Windows,
the architecture of the Python running the build does.

Building without the native JPEG decoder is possible, and changes JPEG hashes by a few
bits: stb_image decodes JPEG to slightly different pixels than libjpeg-turbo, so its
hashes are compared with libjpeg-turbo's by distance, never by equality.
`LIBPHASH_CMAKE_ARGS="-DPHASH_USE_LIBJPEG_TURBO=OFF" pip install .` builds that way, and
`build_info()` then says `jpeg=stb_image`.

## Versions

The version has four numbers, `X.Y.Z.N`: `X.Y.Z` is the bundled libphash, `N` the
revision of the binding. Hash values depend on `X.Y.Z` and the configuration only, so to
keep the hashes of a stored collection comparable while still receiving fixes of the
binding, pin the first three:

```bash
pip install "python-libphash==2.0.1.*"
```

[Versions](../project/versions.md) explains the scheme.
