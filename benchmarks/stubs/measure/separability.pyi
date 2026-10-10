# Separability as libphash's site measures it: tools/site/measure/separability.py.

from collections.abc import Sequence

COPY_STRENGTHS: dict[str, float]
RECALL: float

def separability(
    copies: Sequence[float],
    different: Sequence[float],
    lower_is_closer: bool,
    recall: float = ...,
) -> tuple[float, float, float]: ...
