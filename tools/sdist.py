"""Make an sdist archive reproducible: the same sources give the same bytes.

setuptools writes the archive with each file's modification time, the time of the run
for the directories and for the gzip header, and the owner of the checkout. The
archive is rewritten with its entries sorted, owners cleared, permissions reduced to
0644 and 0755, no gzip timestamp, and, when ``SOURCE_DATE_EPOCH`` is set (the release
workflow sets it to the time of the tagged commit), every entry dated to it. Without
the variable the files keep their own times, and the metadata setuptools generates
(``PKG-INFO``) has the time of the build.
"""

from __future__ import annotations

import gzip
import io
import os
import tarfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def normalize(archive: Path) -> None:
    """Rewrite the ``.tar.gz`` at ``archive`` in place, reproducibly."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    with tarfile.open(archive, "r:gz") as source:
        members = sorted(source.getmembers(), key=lambda m: m.name)
        files = {m.name: _read(source, m) for m in members if m.isfile()}
        newest = max((m.mtime for m in members if m.isfile()), default=0)
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=tarfile.GNU_FORMAT) as target:
        for member in members:
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            executable = member.isdir() or member.mode & 0o100
            member.mode = 0o755 if executable else 0o644
            if epoch is not None:
                member.mtime = int(epoch)
            elif member.isdir():
                member.mtime = newest
            data = files.get(member.name)
            target.addfile(member, io.BytesIO(data) if data is not None else None)
    with (
        archive.open("wb") as raw,
        gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0
        ) as compressed,
    ):
        compressed.write(out.getvalue())


def _read(source: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    stream = source.extractfile(member)
    if stream is None:
        raise RuntimeError(f"no data for {member.name}")
    return stream.read()
