# Loading images

`ph.hash()` and `ImageContext.load()` take any of these sources and tell them apart by
type:

| Source | Example | Goes through |
|---|---|---|
| a path | `"photo.jpg"`, `pathlib.Path(...)` | libphash opens and decodes the file |
| encoded bytes | `bytes`, `bytearray`, a 1-D `memoryview` | decoded from memory, without a copy |
| a binary file object | `open(..., "rb")`, `io.BytesIO`, a response body | read to its end, then as bytes |
| an array of pixels | a numpy `uint8` array, a 2-D or 3-D `memoryview` | hashed from the pixels |
| a Pillow image | `PIL.Image.open(...)` | its pixels |

Bytes are always the encoded file, never a path. Each source has its own method on a
context too: `load_file()`, `load_bytes()`, `load_fileobj()`, `load_pixels()`,
`load_pil()`.

```python
import io
from pathlib import Path

import libphash as ph

data = Path("photo.jpg").read_bytes()
assert ph.hash("photo.jpg") == ph.hash(data) == ph.hash(io.BytesIO(data))
```

## Files and encoded data

libphash decodes JPEG with libjpeg-turbo, PNG with libpng and WebP with libwebp; BMP,
GIF (the first frame), TGA, PSD, HDR, PIC and PNM with stb_image. A file is decoded as
it is displayed: the EXIF orientation of a JPEG or PNG is applied (`Config.auto_orient`),
and transparency is composited onto gray (`Config.alpha_mode`).

A load fails with an exception that says why ([Handling errors](errors.md)): a missing
file is a `FileNotFoundError`, a file that is not an image an `UnsupportedFormatError`, a
truncated or damaged one a `CorruptDataError`, and an image larger than
`Config.max_pixels` an `ImageTooLargeError`, raised before any pixel is decoded.

Paths may hold any character on every platform, Windows included.

## Pixels: numpy, OpenCV, Pillow

An image another library has decoded is hashed from its pixels:

```python
import numpy as np
from PIL import Image

with Image.open("photo.png") as img:
    rgb = np.asarray(img.convert("RGB"))       # shape (height, width, 3), uint8
ph.hash(rgb) == ph.hash("photo.png")           # True: the same pixels
```

An array is 8-bit, of shape `(h, w)` (gray), `(h, w, 1)`, `(h, w, 3)` (RGB) or
`(h, w, 4)` (RGBA). OpenCV's arrays are BGR: say so, or the colors are swapped.

```python
with ph.ImageContext() as ctx:
    ctx.load_pixels(rgb[..., ::-1], channel_order="bgr")   # as cv2.imread gives it
    assert ctx.phash() == ph.hash(rgb)
```

An array whose rows are the only gaps, such as a crop `arr[10:-10, 5:-5]`, is passed to
C without a copy; any other layout (reversed or interleaved channels, BGR) is copied once.
Pillow images are converted as needed: `1` to gray, palette and gray-with-alpha to RGBA,
CMYK, YCbCr, HSV and LAB to RGB; 16-bit and float modes are refused, since there is no
single right way to bring them to 8 bits.

Pixels carry no orientation tag: rotate them yourself (Pillow's
`ImageOps.exif_transpose`) if the source had one. A decoder other than libphash's may
also round differently: PNG pixels are the same everywhere, JPEG pixels differ between
decoders by a level here and there, so a JPEG decoded by Pillow or OpenCV hashes a few
bits away from the same file loaded by path.

## Grayscale

`Config(grayscale=True)` decodes to one gray channel, which is faster for the seven
algorithms that work in gray. ColorHash and ColorMoments then raise
`RequiresColorError`.

## Reusing a context

A context holds one image at a time and keeps its buffers when it loads the next, so a
loop over many images reuses one:

```python
with ph.ImageContext() as ctx:
    for path in ["photo.jpg", "photo_copy.jpg"]:
        ctx.load_file(path)
        print(path, ctx.width, ctx.height, ph.hash_to_hex(ctx.phash()))
```

A failed load from a file or bytes leaves the context empty; a failed `load_pixels()`
keeps the image loaded before.
