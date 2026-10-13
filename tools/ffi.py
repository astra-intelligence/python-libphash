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

#: The batch callbacks as libphash calls them: each enters its extern "Python" function
#: under one lock on a free-threaded CPython, and directly under the GIL. Entering
#: from a thread Python did not create, cffi frees the thread states of such threads
#: that have exited (thread_canary_free_zombies), code written to run under the GIL;
#: without it, two workers entering at once crash the process
#: (https://github.com/python-cffi/cffi/issues/286). The lock makes them enter one at
#: a time; the batch serializes its callbacks on its own lock in Python anyway.
SERIAL_CALLBACKS = r"""
#ifdef Py_GIL_DISABLED
#  ifdef _WIN32
#    include <windows.h>
static SRWLOCK _libphash_callback_lock = SRWLOCK_INIT;
#    define CALLBACK_LOCK() AcquireSRWLockExclusive(&_libphash_callback_lock)
#    define CALLBACK_UNLOCK() ReleaseSRWLockExclusive(&_libphash_callback_lock)
#  else
#    include <pthread.h>
static pthread_mutex_t _libphash_callback_lock = PTHREAD_MUTEX_INITIALIZER;
#    define CALLBACK_LOCK() pthread_mutex_lock(&_libphash_callback_lock)
#    define CALLBACK_UNLOCK() pthread_mutex_unlock(&_libphash_callback_lock)
#  endif
#else
#  define CALLBACK_LOCK() ((void)0)
#  define CALLBACK_UNLOCK() ((void)0)
#endif
static int _libphash_should_continue(void *user_data);
static void _libphash_on_progress(size_t done, size_t total, void *user_data);
static int _libphash_continue_locked(void *user_data) {
    CALLBACK_LOCK();
    int r = _libphash_should_continue(user_data);
    CALLBACK_UNLOCK();
    return r;
}
static void _libphash_progress_locked(size_t done, size_t total, void *user_data) {
    CALLBACK_LOCK();
    _libphash_on_progress(done, total, user_data);
    CALLBACK_UNLOCK();
}
static int (*const _libphash_continue)(void *) = _libphash_continue_locked;
static void (*const _libphash_progress)(size_t, size_t, void *) =
    _libphash_progress_locked;
"""

ffibuilder = FFI()
ffibuilder.cdef(binding_cdef(HEADER))
ffibuilder.set_source("libphash._native", '#include "libphash.h"\n' + SERIAL_CALLBACKS)
