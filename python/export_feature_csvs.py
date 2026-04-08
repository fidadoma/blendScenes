from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AlexNet feature .npy files to CSV.")
    parser.add_argument("--input-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    manifest = pd.read_csv(input_dir / "image_manifest.csv")
    image_names = manifest["image_name"]

    for npy_path in sorted(input_dir.glob("*_features.npy")):
      layer = npy_path.stem.replace("_features", "")
      arr = np.load(npy_path)
      cols = ["image_name"] + [f"{layer}_{i+1}" for i in range(arr.shape[1])]
      df = pd.DataFrame(arr, columns=cols[1:])
      df.insert(0, "image_name", image_names)
      out_path = input_dir / f"{layer}_features.csv"
      df.to_csv(out_path, index=False)
      print(out_path)


if __name__ == "__main__":
    main()
