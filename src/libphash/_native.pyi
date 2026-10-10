# The CFFI module generated from libphash.h; its members mirror the C API one to one.
from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

class _FFI:
    def def_extern(
        self, name: str = ..., error: Any = ..., onerror: Any = ...
    ) -> Callable[[_F], _F]: ...
    def __getattr__(self, name: str) -> Any: ...

ffi: _FFI
lib: Any
