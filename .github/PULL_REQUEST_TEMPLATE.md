## Summary

<!-- What this changes and why. Link an issue if there is one. -->

## Checklist

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check . && uv run ruff format --check .` are clean
- [ ] `uv run mypy && uv run basedpyright` are clean
- [ ] `uv run python tools/stub.py --check` passes (regenerated if the C side or
      `tools/` changed)
- [ ] Coverage stays at 100 % and new code is covered by tests
- [ ] `CHANGELOG.md` has a line under `[Unreleased]`, or the change is invisible to
      users of the package
- [ ] Documentation and docstrings describe the new behavior

## Does this change any hash value?

<!-- A binding revision never changes a hash: hash values come from libphash. If this
     change does, explain why. -->
