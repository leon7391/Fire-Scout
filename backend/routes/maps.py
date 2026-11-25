
import json
import re

from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(
    prefix="/api/maps",
    tags=["FIRE SCOUT Maps"]
)

MAP_DIR = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "maps"
)

LATEST_FILE = MAP_DIR / "latest.json"

MAP_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


@router.get("/current")
def get_current_map():
    if not LATEST_FILE.is_file():
        return {
            "available": False,
            "status": "waiting_for_map"
        }

    try:
        metadata = json.loads(
            LATEST_FILE.read_text(encoding="utf-8")
        )

        map_id = metadata["map_id"]

        if (
            not isinstance(map_id, str)
            or not MAP_ID_PATTERN.fullmatch(map_id)
        ):
            raise ValueError("Invalid map ID")

        image_path = MAP_DIR / f"{map_id}.png"

        if not image_path.is_file():
            raise ValueError("Map image not found")

        return {
            "available": True,
            "map_id": map_id,
            "frame_id": metadata["frame_id"],
            "width": metadata["width"],
            "height": metadata["height"],
            "resolution": metadata["resolution"],
            "origin": metadata["origin"],
            "updated_at": metadata["updated_at"],
            "source": metadata.get("source", "unknown"),
            "image_url": f"/api/maps/{map_id}/image"
        }

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Map metadata unavailable: {exc}"
        )


@router.get("/{map_id}/image")
def get_map_image(map_id: str):
    if not MAP_ID_PATTERN.fullmatch(map_id):
        raise HTTPException(
            status_code=404,
            detail="Invalid map ID"
        )

    image_path = MAP_DIR / f"{map_id}.png"

    if not image_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Map image not found"
        )

    return FileResponse(
        path=image_path,
        media_type="image/png",
        headers={"Cache-Control": "no-store"}
    )
