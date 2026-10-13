# Configuring

Every setting of a libphash context is a field of one immutable `Config`. Its defaults
are libphash's, and it is checked when it is made: a value out of range raises
`InvalidArgumentError` (a `ValueError`) naming the field, before any image is touched.

```python
import libphash as ph

cfg = ph.Config(max_pixels=50_000_000, alpha_mode="white", bmh_block_size=8)
ph.hash("photo.jpg", "bmh", config=cfg)        # one image
ctx = ph.ImageContext(cfg)                     # a context keeps its Config
ph.hash_files(["photo.jpg"], config=cfg)       # a batch applies it to every item
larger = cfg.replace(max_pixels=0)             # a checked copy with a change
ctx.close()
```

## Hashes are comparable only under the same settings

Every setting except `max_pixels` can change a hash. Two hashes are comparable only when
both were computed with equal configurations (and the same libphash version): compute a
whole collection with one `Config`, and store it, or the fields you changed, beside the
hashes.

## The settings

| Field | Default | Read by | What it does |
|---|---|---|---|
| `auto_orient` | `True` | every algorithm | apply the EXIF orientation of a JPEG or PNG |
| `alpha_mode` | `"grey"` | every algorithm | composite transparency onto grey, `"white"` or `"black"`, or `"ignore"` it |
| `grayscale` | `False` | every algorithm | decode to one gray channel; the color algorithms then refuse |
| `gray_weights` | `(38, 75, 15)` | the gray algorithms | relative R, G, B weights of the gray conversion |
| `max_pixels` | `268435456` | loading | the largest image accepted; `0` leaves only the fixed limits |
| `decode_scale` | `1` | JPEG | decode at 1/1, 1/2, 1/4 or 1/8 of the resolution: faster, hashes move |
| `phash_dct_size` | `32` | pHash | side of the DCT grid |
| `phash_reduction_size` | `8` | pHash | side of the low-frequency block, 4 to 8; the hash has its square in bits |
| `whash_mode` | `"fast"` | wHash | `"fast"` (one Haar level) or `"full"` (ImageHash's scale) |
| `whash_remove_max_haar_ll` | `False` | wHash | zero the coarsest coefficient, as ImageHash's option does |
| `bmh_block_size` | `16` | BMH | side of the block grid, 2 to 32; the digest has its square in bits |
| `mhash_alpha`, `mhash_level`, `mhash_size` | `2.0`, `1.0`, `512` | mHash | the Marr–Hildreth kernel's scale and the normalization size |
| `radial_projections`, `radial_samples`, `radial_sigma` | `180`, `128`, `3.5` | Radial | angles, points per line, blur before the projections |
| `gamma` | `1.0` | Radial | the exponent applied to the normalized pixels |

The API reference of [`Config`](../api/config.md) gives each field's range, and
libphash's [Configuring a context](https://gudoshnikovn.github.io/libphash/guide/configuring/)
and the algorithm pages what each one changes.

A digest's size follows from the settings, without an image:

```python
size, kind = ph.digest_info("bmh", ph.Config(bmh_block_size=8))
assert (size, kind) == (8, ph.DigestKind.BITS)
```

## Limits

An image is refused before it is decoded when its width times its height exceeds
`max_pixels` (256 Mi pixels by default) or one side exceeds 1,000,000 pixels; the second
limit is fixed. The default bounds the memory one load can take, which matters when the
images come from elsewhere: a small file can declare a huge image.
