# The part of atheris the tools use: atheris ships no type information.
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager

def Setup(  # noqa: N802 -- atheris's name
    args: list[str], test_one_input: Callable[[bytes], None]
) -> list[str]: ...
def Fuzz() -> None: ...  # noqa: N802 -- atheris's name
def instrument_imports(
    include: Iterable[str] | None = None, exclude: Iterable[str] | None = None
) -> AbstractContextManager[None]: ...
def path() -> str: ...
