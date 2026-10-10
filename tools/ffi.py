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
from cdef import binding_cdef
from native import HEADER

ffibuilder = FFI()
ffibuilder.cdef(binding_cdef(HEADER))
ffibuilder.set_source("libphash._native", '#include "libphash.h"')
