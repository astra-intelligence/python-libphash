# The C side of the benchmarks (benchmarks/cbench.py), built against the libphash install
# that the extension links (tools/native.py):
#   cmake -S benchmarks/c -B <dir> -DCMAKE_PREFIX_PATH=<libphash install prefix>
#   cmake --build <dir> --config Release
cmake_minimum_required(VERSION 3.21)
project(libphash_bench C)

find_package(phash 2 REQUIRED CONFIG)

add_executable(bench bench.c)
target_link_libraries(bench PRIVATE phash::phash)
