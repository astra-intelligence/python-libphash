"""Print the hashes of every libphash fixture, computed by the installed binding.

libphash computes the same values on every platform, so each wheel of a release must
give the same table byte for byte. The wheels workflow writes one table per wheel, with
the Python the wheel is for, and compares them all in one job.

    hash_table.py DATA_DIR > table.txt

A line is ``<fixture> <settings> <algorithm> <value>``: the hash in hex, a digest as
``<kind>:<hex>``, or ``!<code>`` for an error. The settings are a few that change how an
image is decoded or hashed. tests/test_c_parity.py checks the binding against C on each
platform; the tables check that the wheels of all platforms agree with each other.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import libphash as ph

SETTINGS: dict[str, ph.Config] = {
    "default": ph.Config(),
    "grayscale": ph.Config(grayscale=True),
    "decode_scale=2": ph.Config(decode_scale=2),
    "decode_scale=8": ph.Config(decode_scale=8),
    "alpha_mode=white": ph.Config(alpha_mode="white"),
    "alpha_mode=ignore": ph.Config(alpha_mode="ignore"),
    "whash_mode=full": ph.Config(whash_mode="full", whash_remove_max_haar_ll=True),
    "gamma=2.2": ph.Config(gamma=2.2, radial_sigma=1.25, radial_projections=360),
    "mhash_size=1000": ph.Config(mhash_size=1000, mhash_alpha=1.5, mhash_level=2.0),
    "phash=16,6": ph.Config(phash_dct_size=16, phash_reduction_size=6),
    "bmh_block_size=7": ph.Config(bmh_block_size=7),
}


def render(value: int | ph.Digest) -> str:
    """Return a hash as it appears in a table."""
    if isinstance(value, int):
        return f"{value:016x}"
    return f"{int(value.kind)}:{value.data.hex()}"


def table(data: Path) -> list[str]:
    """Return the table of the fixtures under ``data``."""
    fixtures = sorted(p for p in data.rglob("*") if p.is_file() and p.suffix != ".txt")
    lines: list[str] = []
    for path in fixtures:
        name = path.relative_to(data).as_posix()
        for label, config in SETTINGS.items():
            with ph.ImageContext(config) as ctx:
                try:
                    ctx.load_bytes(path.read_bytes())
                except ph.PhashError as e:
                    lines.append(f"{name} {label} load !{e.code}")
                    continue
                for algo in sorted(ph.Algorithm, key=int):
                    try:
                        value = render(ctx.hash(algo))
                    except ph.PhashError as e:
                        value = f"!{e.code}"
                    lines.append(f"{name} {label} {algo} {value}")
    return lines


def main() -> int:
    """Run the command line."""
    parser = argparse.ArgumentParser(
        description="Print the hashes of every fixture under DATA with the binding."
    )
    parser.add_argument("data", type=Path, metavar="DATA")
    data: Path = parser.parse_args().data
    lines = table(data)
    if not lines:
        sys.exit(f"hash_table.py: no fixtures under {data}")
    # Not in the table: it names the SIMD of the machine, which differs by design.
    sys.stderr.write(f"{ph.build_info()}\n")
    # Bytes: a text stream on Windows would end the lines with CRLF.
    sys.stdout.buffer.write(("\n".join(lines) + "\n").encode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
