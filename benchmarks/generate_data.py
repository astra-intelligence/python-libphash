import os
import random
import argparse
from PIL import Image, ImageDraw
from benchmarks.utils import ensure_dir


def create_base_images(output_dir, count, fmt="JPEG"):
    ensure_dir(output_dir)
    sizes = [(256, 256), (512, 512), (1024, 1024), (1920, 1080)]
    if fmt == "JPEG":
        ext = "jpg"
    elif fmt == "PNG":
        ext = "png"
    elif fmt == "WEBP":
        ext = "webp"
    else:
        ext = "bin"

    print(f"Generating {count} base {fmt} images in {output_dir}...")

    for i in range(count):
        size = random.choice(sizes)
        img = Image.new(
            "RGB",
            size,
            color=(
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            ),
        )

        draw = ImageDraw.Draw(img)
        for _ in range(10):
            x1, y1 = random.randint(0, size[0]), random.randint(0, size[1])
            x2, y2 = random.randint(0, size[0]), random.randint(0, size[1])
            coords = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
            draw.rectangle(
                coords,
                fill=(
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255),
                ),
            )

        img.save(os.path.join(output_dir, f"img_{i:03d}.{ext}"), fmt)
        if (i + 1) % 50 == 0:
            print(f"  Progress: {i + 1}/{count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate base images for benchmarks.")
    parser.add_argument(
        "--count", type=int, default=100, help="Number of images to generate"
    )
    parser.add_argument(
        "--format",
        choices=["jpeg", "png", "webp", "all"],
        default="jpeg",
        help="Image format",
    )
    args = parser.parse_args()

    if args.format in ["jpeg", "all"]:
        create_base_images("benchmarks/data/jpeg", args.count, "JPEG")
    if args.format in ["png", "all"]:
        create_base_images("benchmarks/data/png", args.count, "PNG")
    if args.format in ["webp", "all"]:
        create_base_images("benchmarks/data/webp", args.count, "WEBP")
