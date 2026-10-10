# The machine a measurement ran on, as libphash's site names it:
# tools/site/measure/timing.py.

from typing import TypedDict

class Machine(TypedDict):
    cpu: str
    cores: int | None
    os: str

def machine() -> Machine: ...
