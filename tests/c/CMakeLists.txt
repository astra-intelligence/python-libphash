# The C reference of tests/test_c_parity.py, built against the libphash install that the
# extension links (tools/native.py):
#   cmake -S tests/c -B <dir> -DCMAKE_PREFIX_PATH=<libphash install prefix>
#   cmake --build <dir> --config Release
cmake_minimum_required(VERSION 3.21)
project(libphash_reference C)

find_package(phash 2 REQUIRED CONFIG)

add_executable(reference reference.c)
target_link_libraries(reference PRIVATE phash::phash)
