
import json
import math
import os
import sys
import uuid

from datetime import datetime, timezone
from pathlib import Path

import yaml
from PIL import Image


BASE_DIR = Path(__file__).resolve().parent.parent
MAP_DIR = BASE_DIR / "data" / "maps"


def import_ros_map(yaml_file):
    yaml_path = Path(yaml_file).expanduser().resolve()

    if not yaml_path.is_file():
        raise FileNotFoundError(yaml_path)

    with yaml_path.open("r", encoding="utf-8") as f:
        metadata = yaml.safe_load(f)

    if not isinstance(metadata, dict):
        raise ValueError("Invalid ROS map YAML")

    image_path = Path(metadata["image"])

    if not image_path.is_absolute():
        image_path = yaml_path.parent / image_path

    resolution = float(metadata["resolution"])
    origin = [float(v) for v in metadata["origin"]]

    if (
        not math.isfinite(resolution)
        or resolution <= 0
        or len(origin) != 3
        or not all(math.isfinite(v) for v in origin)
    ):
        raise ValueError("Invalid ROS map geometry")

    MAP_DIR.mkdir(parents=True, exist_ok=True)

    map_id = (
        "map_"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "_"
        + uuid.uuid4().hex[:8]
    )

    final_image = MAP_DIR / f"{map_id}.png"
    temp_image = MAP_DIR / f"{map_id}.tmp.png"

    try:
        with Image.open(image_path) as source_image:
            image = source_image.convert("RGB")

        width, height = image.size

        image.save(temp_image, format="PNG")
        os.replace(temp_image, final_image)

        manifest = {
            "map_id": map_id,
            "frame_id": "map",
            "width": width,
            "height": height,
            "resolution": resolution,
            "origin": origin,
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(timespec="seconds"),
            "source": "ros2_map_saver"
        }

        temp_manifest = MAP_DIR / "latest.json.tmp"
        temp_manifest.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8"
        )

        os.replace(
            temp_manifest,
            MAP_DIR / "latest.json"
        )

        print("[MAP] Imported successfully")
        print(f"[MAP] ID: {map_id}")
        print(f"[MAP] Size: {width}x{height}")
        print(f"[MAP] Resolution: {resolution} m/px")

    finally:
        if temp_image.exists():
            temp_image.unlink()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python backend/import_ros_map.py "
            "/path/to/map.yaml"
        )

    import_ros_map(sys.argv[1])
