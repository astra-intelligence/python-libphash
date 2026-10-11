"""The photo corpus of libphash's site hashes in the binding as in C.

Two hundred photographs of about a megapixel, a fixed commit of libphash-site-corpus
fetched and checked against their SHA-256 by libphash's ``fetch_corpus.py``. Its own
workflow runs this with ``LIBPHASH_CORPUS`` naming the file that lists the photographs;
other runs do not collect it.
"""

from __future__ import annotations

import os
from pathlib import Path

from c_reference import Job, Reference, check

# The number of photographs of the corpus's manifest; fetch_corpus.py --strict fails
# rather than give fewer.
PHOTOS = 200


def test_the_corpus_hashes_as_in_c(reference: Reference) -> None:
    listing = Path(os.environ["LIBPHASH_CORPUS"])
    photos = [Path(line) for line in listing.read_text().splitlines() if line]
    assert len(photos) == PHOTOS
    check(
        reference,
        [
            job
            for photo in photos
            for job in (
                Job("file", photo),
                Job("memory", photo),
                Job("file", photo, {"grayscale": True}),
                Job("file", photo, {"decode_scale": 4}),
            )
        ],
    )
