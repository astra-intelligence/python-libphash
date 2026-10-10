"""CFFI definition of ``libphash._native``.

The cdef is generated from libphash's public header, so the binding declares exactly
the C API it compiles against. The C side (libphash and its decoders) is built and
linked by the ``build_ext`` command in ``setup.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cffi import FFI

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdef import header_cdef
from native import HEADER

# The batch callbacks: implemented in Python with @ffi.def_extern, so no executable
# closure is created at run time (which ffi.callback would need).
BATCH_CALLBACKS = """
extern "Python" int _libphash_should_continue(void *user_data);
extern "Python" void _libphash_on_progress(size_t done, size_t total, void *user_data);
"""

ffibuilder = FFI()
ffibuilder.cdef(header_cdef(HEADER) + BATCH_CALLBACKS)
ffibuilder.set_source("libphash._native", '#include "libphash.h"')
