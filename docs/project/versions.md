# Versions

The version has four numbers, `X.Y.Z.N`:

- `X.Y.Z` is the version of the bundled libphash: python-libphash 2.0.1.0 carries
  libphash 2.0.1.
- `N` is the revision of the binding on top of it. The first release for a libphash
  version is `.0`, and the zero is always written; fixes and additions to the Python side
  alone are `2.0.1.1`, `2.0.1.2`, and so on.

Each libphash release gets its binding, `X.Y.Z.0`. Tags are `vX.Y.Z.N`.

## What changes the hashes

Hash values depend on the libphash version and on the configuration, never on the
binding revision. Two hashes are comparable when both were computed with the same
`X.Y.Z` and equal settings. A libphash release that changes an algorithm's values says
so in its changelog, and so does this package's changelog for the `X.Y.Z.0` that brings
it.

To keep a stored collection comparable while still receiving the binding's fixes, pin
the first three numbers:

```bash
pip install "python-libphash==2.0.1.*"
```

To see what is installed:

```python
import libphash as ph

ph.__version__            # '2.0.1.0'
ph.libphash_version()     # '2.0.1'
```

## Support

Only the newest release receives fixes; a vulnerability in libphash or one of its
decoders is fixed in a libphash release and reaches this package as the next `X.Y.Z.0`.
Python versions are supported from the oldest in `requires-python` to the newest
release; one that reaches its end of life is dropped in the next `X.Y.Z.0`.

The 1.x releases were numbered independently of libphash (1.4.1 bundles libphash
1.10.4); [Migrating from 1.x](../guide/migration.md) covers the move to 2.x.
