"""The decoders linked into the module do not clash with other copies in the process.

Pillow and OpenCV carry their own libjpeg, libpng, libwebp and zlib. The extension
exports only PyInit__native, so whichever is imported first, each library keeps its own
copy: libphash's hashes and Pillow's pixels are the same in every import order.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import subprocess
import sys

import pytest
from conftest import data

import libphash as ph

MODULES = ["libphash", "PIL.Image", "cv2"]


def present(name: str) -> bool:
    return importlib.util.find_spec(name.split(".")[0]) is not None


SCRIPT = """
import hashlib, importlib, json, sys
for name in sys.argv[3:]:
    importlib.import_module(name)
import libphash
from PIL import Image
out = {"jpeg": libphash.hash(sys.argv[1]), "png": libphash.hash(sys.argv[2])}
with Image.open(sys.argv[1]) as img:
    out["pillow"] = hashlib.sha256(img.convert("RGB").tobytes()).hexdigest()
print(json.dumps(out))
"""


@pytest.mark.parametrize(
    "order",
    list(itertools.permutations([m for m in MODULES if present(m)])),
    ids="-".join,
)
def test_import_order_changes_nothing(order: tuple[str, ...]) -> None:
    if not present("PIL"):
        pytest.skip("needs Pillow")
    jpeg, png = data("photo.jpeg"), data("photo.png")
    done = subprocess.run(  # noqa: S603 -- the test's own interpreter
        [sys.executable, "-c", SCRIPT, str(jpeg), str(png), *order],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout)
    assert result["jpeg"] == ph.hash(jpeg)
    assert result["png"] == ph.hash(png)
    baseline = subprocess.run(  # noqa: S603 -- the test's own interpreter
        [sys.executable, "-c", SCRIPT, str(jpeg), str(png), "PIL.Image"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result["pillow"] == json.loads(baseline.stdout)["pillow"]
