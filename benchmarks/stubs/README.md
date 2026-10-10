# Type stubs for untyped code the benchmarks import

- `fetch_corpus`, `measure` — libphash's site tooling (`native/libphash/tools/site`),
  imported so that the benchmarks use the site's corpus, edits, copies and separability.
  The site's modules carry no annotations; these stubs declare the subset the benchmarks
  call, as the site's code defines it.
- `pdqhash` — the PDQ hash, which ships no type information.

mypy (`mypy_path`) and basedpyright (`stubPath`) read these instead of the modules.
`tests/test_benchmarks.py` runs the benchmarks on the test images, so a stub that no
longer matches the code it describes fails there.
