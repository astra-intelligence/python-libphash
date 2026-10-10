import time
import argparse
import pandas as pd
from tabulate import tabulate
import imagehash
from libphash import Config, ImageContext
from benchmarks.utils import get_base_files


def run_speed_test(image_paths, workers=None):
    algorithms = [
        ("ahash", imagehash.average_hash, lambda ctx: ctx.ahash()),
        ("phash", imagehash.phash, lambda ctx: ctx.phash()),
        ("dhash", imagehash.dhash, lambda ctx: ctx.dhash()),
        ("whash", imagehash.whash, lambda ctx: ctx.whash()),
    ]

    results = []
    print(f"Running speed benchmarks on {len(image_paths)} images...")

    for name, ih_func, lp_func in algorithms:
        print(f"  Testing {name}...")

        # imagehash
        start = time.perf_counter()
        for p in image_paths:
            img = imagehash.Image.open(p).convert("RGB")
            _ = ih_func(img)
        ih_time = time.perf_counter() - start

        # libphash
        start = time.perf_counter()
        for p in image_paths:
            with ImageContext(Config(grayscale=True)) as ctx:
                ctx.load_file(p)
                _ = lp_func(ctx)
        lp_time = time.perf_counter() - start

        results.append(
            {
                "Algorithm": name,
                "imagehash (s)": f"{ih_time:.4f}",
                "libphash (s)": f"{lp_time:.4f}",
                "Speedup": f"{ih_time / lp_time:.2f}x",
            }
        )

    print(
        "\n"
        + tabulate(
            pd.DataFrame(results), headers="keys", tablefmt="pipe", showindex=False
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run speed benchmarks.")
    parser.add_argument("--format", choices=["jpeg", "png", "webp"], default="jpeg")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    data_dir = f"benchmarks/data/{args.format}"
    ext = "jpg" if args.format == "jpeg" else args.format
    files = get_base_files(data_dir, ext)[: args.limit]

    if not files:
        print(f"No files found in {data_dir}. Run generate_data.py first.")
    else:
        run_speed_test(files)
