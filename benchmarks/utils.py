import os
import glob
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter
from libphash import Config, ImageContext


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def get_base_files(data_dir, extension="jpg"):
    return sorted(glob.glob(os.path.join(data_dir, f"*.{extension}")))


def generate_augmentations(base_path, output_dir, fmt="JPEG"):
    """
    Generate deterministic augmentations for a single base image.
    Returns list of (path, base_name)
    """
    img = Image.open(base_path).convert("RGB")
    base_name = Path(base_path).stem
    results = []

    ext = "jpg" if fmt == "JPEG" else "png"

    # 0. Base as target format
    p0 = os.path.join(output_dir, f"{base_name}_base.{ext}")
    img.save(p0, fmt)
    results.append((p0, base_name))

    # 1. Resize/Compression
    p1 = os.path.join(output_dir, f"{base_name}_aug_comp.{ext}")
    img_res = img.resize((img.width // 2, img.height // 2))
    if fmt == "JPEG":
        img_res.save(p1, "JPEG", quality=30)
    else:
        img_res.save(p1, "PNG")
    results.append((p1, base_name))

    # 2. Color Shift
    p2 = os.path.join(output_dir, f"{base_name}_aug_color.{ext}")
    img_b = ImageEnhance.Brightness(img).enhance(1.5)
    img_c = ImageEnhance.Contrast(img_b).enhance(0.8)
    img_c.save(p2, fmt)
    results.append((p2, base_name))

    # 3. Blur + Crop
    p3 = os.path.join(output_dir, f"{base_name}_aug_blur.{ext}")
    img_blur = img.filter(ImageFilter.GaussianBlur(1.5))
    w, h = img_blur.size
    img_crop = img_blur.crop(
        (int(w * 0.05), int(h * 0.05), int(w * 0.95), int(h * 0.95))
    )
    img_crop.save(p3, fmt)
    results.append((p3, base_name))

    return results


def get_hash_lp(path, algo_name, ctx=None, mode=None):
    """Get hash from libphash context."""
    if ctx is None:
        config = Config(grayscale=True)
        if mode and algo_name == "whash":
            config = config.replace(whash_mode=mode)
        with ImageContext(config) as local_ctx:
            local_ctx.load_file(path)
            return local_ctx.hash(algo_name)
    ctx.load_file(path)
    return ctx.hash(algo_name)


def get_hash_ih(path, ih_func):
    """Get hash from imagehash (Pillow)."""
    img = Image.open(path).convert("RGB")
    return ih_func(img)


def generate_complex_augmentations(base_path, output_dir, fmt="JPEG"):
    """
    Generate complex augmentations to challenge hash robustness.
    1. 90/180/270 degree rotations
    2. Small partial rotations (2-5 degrees)
    3. Heavy noise
    4. Extreme aspect ratio change
    5. Partial occlusion / border pads
    """
    import numpy as np
    from PIL import ImageEnhance, ImageFilter

    img = Image.open(base_path).convert("RGB")
    base_name = Path(base_path).stem
    results = []
    ext = "jpg" if fmt == "JPEG" else "png"

    # 1. Official 90-degree rotations
    for angle in [90, 180, 270]:
        p = os.path.join(output_dir, f"{base_name}_rot{angle}.{ext}")
        img.rotate(angle, expand=True).save(p, fmt)
        results.append((p, base_name))

    # 2. Small tilt (challenges dHash/aHash)
    p_tilt = os.path.join(output_dir, f"{base_name}_tilt.{ext}")
    img.rotate(3, expand=True, resample=Image.BICUBIC).save(p_tilt, fmt)
    results.append((p_tilt, base_name))

    # 3. Heavy Gaussian Noise
    p_noise = os.path.join(output_dir, f"{base_name}_noise.{ext}")
    img_arr = np.array(img).astype(float)
    noise = np.random.normal(0, 30, img_arr.shape)
    img_noise = Image.fromarray(np.clip(img_arr + noise, 0, 255).astype(np.uint8))
    img_noise.save(p_noise, fmt)
    results.append((p_noise, base_name))

    # 4. Aspect Ratio Stretch (16:9 -> 4:3)
    p_stretch = os.path.join(output_dir, f"{base_name}_stretch.{ext}")
    img.resize((img.width, int(img.height * 0.75))).save(p_stretch, fmt)
    results.append((p_stretch, base_name))

    # 5. Brightness + Contrast + Blur
    p_heavy = os.path.join(output_dir, f"{base_name}_heavy.{ext}")
    img_h = ImageEnhance.Brightness(img).enhance(0.7)
    img_h = ImageEnhance.Contrast(img_h).enhance(1.8)
    img_h.filter(ImageFilter.BoxBlur(2)).save(p_heavy, fmt)
    results.append((p_heavy, base_name))

    return results
