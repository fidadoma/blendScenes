from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn

from places365_alexnet import Places365AlexNet


DEFAULT_PROTOTXT = Path("python/models/places365_caffe/deploy_alexnet_places365.prototxt")
DEFAULT_CAFFEMODEL = Path("python/models/places365_caffe/alexnet_places365.caffemodel")
DEFAULT_OUTPUT = Path("python/models/places365/alexnet_places365.pth.tar")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert AlexNet Places365 Caffe weights to a PyTorch checkpoint."
    )
    parser.add_argument("--prototxt", type=Path, default=DEFAULT_PROTOTXT)
    parser.add_argument("--caffemodel", type=Path, default=DEFAULT_CAFFEMODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--metadata-json",
        type=Path,
        default=None,
        help="Optional metadata JSON path. Defaults next to the output checkpoint.",
    )
    return parser.parse_args()


def get_caffe_param(net: cv2.dnn.Net, layer_name: str, param_index: int) -> np.ndarray:
    layer_id = net.getLayerId(layer_name)
    if layer_id <= 0:
        raise KeyError(f"Layer not found in Caffe net: {layer_name}")
    return net.getParam(layer_id, param_index)


def copy_param(target: nn.Module, weight: np.ndarray, bias: np.ndarray) -> None:
    target.weight.data.copy_(torch.from_numpy(weight))
    target.bias.data.copy_(torch.from_numpy(bias.reshape(-1)))


def convert_alexnet(net: cv2.dnn.Net) -> nn.Module:
    model = Places365AlexNet(num_classes=365)
    model.eval()

    # Convert the first conv layer from Caffe's BGR convention to RGB input.
    conv1_weight = get_caffe_param(net, "conv1", 0)[:, ::-1, :, :].copy()
    conv1_bias = get_caffe_param(net, "conv1", 1)
    copy_param(model.conv1, conv1_weight, conv1_bias)
    copy_param(model.conv2, get_caffe_param(net, "conv2", 0), get_caffe_param(net, "conv2", 1))
    copy_param(model.conv3, get_caffe_param(net, "conv3", 0), get_caffe_param(net, "conv3", 1))
    copy_param(model.conv4, get_caffe_param(net, "conv4", 0), get_caffe_param(net, "conv4", 1))
    copy_param(model.conv5, get_caffe_param(net, "conv5", 0), get_caffe_param(net, "conv5", 1))
    copy_param(model.fc6, get_caffe_param(net, "fc6", 0), get_caffe_param(net, "fc6", 1))
    copy_param(model.fc7, get_caffe_param(net, "fc7", 0), get_caffe_param(net, "fc7", 1))
    copy_param(model.fc8, get_caffe_param(net, "fc8", 0), get_caffe_param(net, "fc8", 1))
    return model


def main() -> None:
    args = parse_args()
    prototxt = args.prototxt.resolve()
    caffemodel = args.caffemodel.resolve()
    output = args.output.resolve()
    metadata_json = args.metadata_json.resolve() if args.metadata_json else output.with_suffix(".json")

    output.parent.mkdir(parents=True, exist_ok=True)
    net = cv2.dnn.readNetFromCaffe(str(prototxt), str(caffemodel))
    model = convert_alexnet(net)

    checkpoint = {
        "arch": "alexnet",
        "num_classes": 365,
        "source_format": "caffe",
        "source_prototxt": str(prototxt),
        "source_caffemodel": str(caffemodel),
        "input_preprocessing": {
            "input_size": [227, 227],
            "pixel_scale": 255.0,
            "channel_order": "RGB",
            "mean_rgb": [123.0, 117.0, 104.0],
            "notes": "conv1 weights converted from Caffe BGR to RGB ordering",
        },
        "state_dict": model.state_dict(),
    }
    torch.save(checkpoint, output)

    metadata = {
        "output_checkpoint": str(output),
        "source_prototxt": str(prototxt),
        "source_caffemodel": str(caffemodel),
        "state_dict_keys": list(model.state_dict().keys()),
    }
    metadata_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Saved converted checkpoint to {output}")
    print(f"Saved metadata to {metadata_json}")


if __name__ == "__main__":
    main()
