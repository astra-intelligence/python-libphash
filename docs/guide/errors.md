# Handling errors

Every failure of the library raises a subclass of `PhashError`, chosen by the C error
code, which also derives from the built-in exception that fits it:

```python
import libphash as ph

try:
    ph.hash("missing.jpg")
except FileNotFoundError as exc:          # an ImageIOError
    print(exc.filename, exc.code_name)    # missing.jpg PH_ERR_IO
```

| C code | Exception | Also a | Raised when |
|---|---|---|---|
| `PH_ERR_IO` | `ImageIOError` | `OSError` | the path cannot be opened or read, is a directory, or the file is empty |
| `PH_ERR_UNSUPPORTED_FORMAT` | `UnsupportedFormatError` | `DecodeError` | the data is in no format libphash knows |
| `PH_ERR_CORRUPT_DATA` | `CorruptDataError` | `DecodeError` | the format is known, but the data is damaged or truncated |
| `PH_ERR_DECODER_UNAVAILABLE` | `DecoderUnavailableError` | `DecodeError` | the build has no decoder for the format |
| `PH_ERR_IMAGE_TOO_LARGE` | `ImageTooLargeError` | `DecodeError` | the image exceeds `Config.max_pixels` or a fixed limit |
| `PH_ERR_INVALID_ARGUMENT` | `InvalidArgumentError` | `ValueError` | a value is out of range (in a `Config`, an array, a digest) |
| `PH_ERR_ALLOCATION_FAILED` | `AllocationError` | `MemoryError` | memory ran out in C |
| `PH_ERR_EMPTY_IMAGE` | `EmptyImageError` | | a hash of a context that holds no image |
| `PH_ERR_REQUIRES_COLOR` | `RequiresColorError` | | a color hash of an image loaded in grayscale |
| `PH_ERR_NO_STRUCTURE` | `NoStructureError` | | a Radial comparison with a flat image's digest |
| `PH_ERR_CANCELLED` | `BatchCancelledError` | | an item of a batch stopped before it started |
| | `DigestKindError` | `TypeError` | a comparison that does not fit the digest's kind |

`ImageIOError` sets `errno` and `filename` when the cause can be told, so the
`OSError` subclasses catch it: `FileNotFoundError`, `PermissionError`,
`IsADirectoryError`.

Each exception carries the C code as `code` and its name as `code_name`, and, for a
failed load, libphash's own message as `detail` (the path and the reason). Exceptions
pickle, so they cross a process boundary intact.

```python
try:
    ph.hash("broken.jpg")
except ph.DecodeError as exc:
    print(type(exc).__name__, exc.code_name)   # CorruptDataError PH_ERR_CORRUPT_DATA
```

## What to do about each

- `ImageIOError`, `DecodeError`: the file is the problem; report it and go on. In a batch
  the item's result holds the error and the other items are hashed.
- `ImageTooLargeError`: raise `Config.max_pixels` if such images are expected and the
  memory is there; otherwise treat it like a bad file.
- `InvalidArgumentError`: a bug in the calling code or a bad setting; fix the value.
- `RequiresColorError`: load in color (`grayscale=False`) for ColorHash and ColorMoments.
- `NoStructureError`: the image is flat (one color, or radially symmetric): it has no
  Radial similarity to anything. Compare it with another algorithm.
- `DigestKindError`: use the comparison that belongs to the digest (`similarity()` picks
  it).

A misuse the binding itself catches, such as a closed context, raises a plain
`ValueError` or `TypeError`, not a `PhashError`.
