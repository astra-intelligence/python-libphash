# The photo corpus of libphash's site: tools/site/fetch_corpus.py.

MIRROR_COMMIT: str
MANIFEST: str

def fetch(cache: str | None = None) -> tuple[list[str], list[str]]: ...
def read_manifest() -> list[dict[str, str]]: ...
