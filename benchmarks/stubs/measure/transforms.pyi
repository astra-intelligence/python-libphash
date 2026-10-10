# The edits of libphash's site: tools/site/measure/transforms.py.

from collections.abc import Callable
from typing import TypeAlias

from PIL import Image

#: An edit: the edited image, and the file extension and JPEG quality to save it with.
Edit: TypeAlias = Callable[[Image.Image], tuple[Image.Image, tuple[str, int | None]]]

def transforms() -> list[tuple[str, str, list[tuple[float, Edit]]]]: ...
def content_edits() -> list[tuple[str, str, list[tuple[float | str, Edit]]]]: ...
def write_edit(op: Edit, image: Image.Image, stem: str) -> str: ...
