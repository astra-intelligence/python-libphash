---
name: Bug report
about: Something crashes, raises unexpectedly, or does not match the documentation
title: ""
labels: bug
---

## What happened

<!-- What you did, what you expected, what happened instead. -->

## Environment

<!-- Required: a wrong hash or a failed decode often depends on the decoder a wheel
     carries, and on whether it was built from the sdist. Paste the output of:

     python -c "import sys, platform, libphash; print(libphash.__version__, sys.version, platform.platform(), libphash.build_info(), sep='\n')"
-->

```text

```

- Installed from: <!-- a PyPI wheel / the sdist / a clone -->

## Minimal reproducer

<!-- The smallest code that shows the problem. Attach the image if the bug is about
     decoding or a hash value and the image can be shared: without it a decoder-specific
     bug is usually not reproducible. -->

```python

```

## Output

<!-- The traceback, with the exception's `code_name` and `detail` if it is a
     PhashError, or a sanitizer report. -->
