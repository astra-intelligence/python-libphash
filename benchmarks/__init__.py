"""Benchmarks of the binding: what Python adds to libphash, and how to pay least for it.

Every table answers either "what does Python cost over the C library" or "which way of
using the binding is fastest or leanest". Other libraries are not measured here.

    uv run python -m benchmarks                    # all, into benchmarks/results/
    uv run python -m benchmarks --blocks parallel  # some blocks
    uv run python -m benchmarks --quick --out DIR  # every case once, in seconds

The blocks:

1. ``overhead`` — one call in C, through cffi, through the API: loads from every
   source, every hash, several hashes of one load, file to hash, comparisons;
2. ``search`` — 1 to N and N to N over hashes: Python loops, numpy, C;
3. ``memory`` — copies of a load, contexts, a batch against its threads, repetition;
4. ``parallel`` — threads, libphash's pool, process pools, asyncio, callbacks,
   subinterpreters;
5. ``startup`` — import time and installed size.

The results are JSON and Markdown with the environment at the top (machine, Python,
``build_info()``). The C side, ``benchmarks/c/bench.c``, is built against the libphash
install of the editable build; ``tests/test_benchmarks.py`` runs every block in the
quick mode.
"""
