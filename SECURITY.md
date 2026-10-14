# Security policy

## Supported versions

| Version | Supported |
|---|---|
| newest `2.x` release | yes |
| older `2.x` releases | no: upgrade to the newest |
| `1.x` | no: see [`MIGRATION.md`](https://github.com/gudoshnikovn/python-libphash/blob/main/MIGRATION.md) to upgrade |

Only the newest release receives fixes. The hash values of a release depend on the
bundled libphash version (`X.Y.Z` of `X.Y.Z.N`); see `CHANGELOG.md` before moving to a
new `X.Y.Z`.

## Reporting a vulnerability

Report it privately through
[GitHub Security Advisories](https://github.com/gudoshnikovn/python-libphash/security/advisories/new)
("Report a vulnerability" under the repository's Security tab), not in a public issue.
Include:

- the package version and the output of `python -c "import libphash; print(libphash.build_info())"`;
- the platform (OS, architecture, Python version, whether free-threaded);
- a minimal reproducer: usually an input file or buffer and the call that receives it;
- what happened (crash, sanitizer report, hang, memory growth, wrong result with a
  security consequence) and what you expected.

An acknowledgment comes within 7 days, and a fix or a mitigation plan within 90 days of
confirmation, sooner for a crash on untrusted input. This is the best effort of a single
maintainer, not a contractual guarantee.

## Where vulnerabilities live

The package decodes images with libphash and the decoders it vendors (libjpeg-turbo,
libpng, libwebp, zlib-ng, stb_image), all linked statically into the extension module.
A vulnerability in decoding is almost always in one of them:

- In libphash or a vendored decoder, it is fixed in a libphash release, and this
  package follows with `X.Y.Z.0` for that release within 14 days. Report it to libphash
  ([its security policy](https://github.com/gudoshnikovn/libphash/blob/main/SECURITY.md));
  a report here is forwarded.
- In the binding itself (the Python code, the cffi glue, memory handed between Python
  and C), the fix is the next binding revision, `X.Y.Z.N+1`.

`libphash.build_info()` names the libphash version and the decoder libraries a wheel
carries; `CHANGELOG.md` lists the version of each vendored library a release bundles.

## Threat model

The package is for hashing images that may come from anywhere: decoding untrusted files
and buffers is its expected use.

In scope:

- Memory safety: an out-of-bounds access, a use after free, a read of uninitialized
  memory, reachable from the public API with a file, bytes, a file object, an array or a
  Pillow image an attacker controls.
- Resource exhaustion that evades a documented limit (`Config.max_pixels`, the fixed
  limit of 1,000,000 pixels per side).
- A crash of the interpreter from any call of the public API, whatever its arguments.

Out of scope:

- **Collisions and evasion.** Perceptual hashes are deterministic and unkeyed: someone
  who can choose the images can make two different images hash alike, or alter an image
  until it no longer matches. The package is for deduplicating a collection its owner
  controls, not for moderation, blocklists or checking the integrity of untrusted input.
  See libphash's
  [What a perceptual hash is not](https://gudoshnikovn.github.io/libphash/theory/perceptual-hashing/#what-a-perceptual-hash-is-not).
- Memory and time spent on a large image within the limits the caller configured:
  raising `max_pixels` accepts that cost.
- An array whose shape, strides or buffer misdescribe its memory, built through
  `ctypes`, `numpy.lib.stride_tricks.as_strided` or a hand-written
  `__array_interface__`: the pixels are read as the array describes them.

## How the package is tested

The binding's tests run under AddressSanitizer with UndefinedBehaviorSanitizer and
LeakSanitizer, and under ThreadSanitizer, in CI. Fuzz targets cover what the binding adds
over libphash, which fuzzes its decoders in C: encoded input, pixel arrays of every
layout, and the text form and comparisons of digests. Their corpus is replayed by the
test suite on every platform.

## Verifying a release

Wheels and the sdist are published to PyPI by the release workflow of this repository
through Trusted Publishing, with PEP 740 attestations that tie each file to the workflow
run and the tagged commit. PyPI shows them on each file's page; to check a file with
[pypi-attestations](https://pypi.org/project/pypi-attestations/):

```bash
pypi-attestations verify pypi --repository https://github.com/gudoshnikovn/python-libphash \
    pypi:python_libphash-2.0.1.1.tar.gz
```

The same files are attached to the GitHub Release with build provenance attestations:

```bash
gh attestation verify python_libphash-2.0.1.1.tar.gz --repo gudoshnikovn/python-libphash
```

Each wheel carries a software bill of materials (CycloneDX, in
`*.dist-info/sboms/`) naming libphash and every library linked into it, with versions.

## Withdrawing a release

A release found to be defective is not replaced under the same version. The fix is the
next release; a vulnerability is announced with a GitHub Security Advisory, which
reaches `pip-audit` and other tools that read the GitHub Advisory Database and OSV.
