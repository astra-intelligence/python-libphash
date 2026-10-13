# API reference

Everything below is exported from `libphash`; the modules it comes from are private.

| Page | What |
|---|---|
| [Hashing](hashing.md) | `hash()`, `ImageContext`, `Algorithm` |
| [Config](config.md) | `Config`, the settings |
| [Digests and comparison](digests.md) | `Digest`, `DigestKind`, `hamming_distance()`, `similarity()`, the text forms |
| [Batches](batch.md) | `hash_files()`, `hash_buffers()`, `BatchResult` |
| [Errors](errors.md) | `PhashError` and its subclasses |
| [Build and types](build.md) | `libphash_version()`, `build_info()`, `can_decode()`, `digest_info()`, the type aliases and protocols |

The package is typed (`py.typed`): mypy and pyright check calls against these
signatures, and every type a caller needs for their own annotations is exported.
