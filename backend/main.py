
import os

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .database import fetch_all, fetch_one

from .routes.monitoring import router as monitoring_router
from .routes.maps import router as maps_router

app = FastAPI(
    title="FIRE SCOUT API",
    description="Fire Monitoring and Robot Management",
    version="1.0.0"
)

app.include_router(maps_router)
app.include_router(monitoring_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"]
)

NODE_TIMEOUT = int(
    os.getenv("NODE_TIMEOUT_SECONDS", "15")
)
TELEMETRY_TIMEOUT = int(
    os.getenv("TELEMETRY_TIMEOUT_SECONDS", "8")
)

HEARTBEAT_TIMEOUT = int(
    os.getenv("HEARTBEAT_TIMEOUT_SECONDS", "15")
)

def get_age_seconds(value):
    if not value:
        return None

    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return (
            datetime.now(timezone.utc)
            - value.astimezone(timezone.utc)
        ).total_seconds()

    except (ValueError, TypeError, AttributeError):
        return None


def calculate_node_states(node):
    telemetry_age = get_age_seconds(
        node.get("last_seen")
    )

    heartbeat_age = get_age_seconds(
        node.get("last_heartbeat_at")
    )

    valid_ages = [
        age
        for age in (telemetry_age, heartbeat_age)
        if age is not None and age >= -5
    ]

    # Connectivity: use both telemetry and heartbeat
    if node.get("status") == "offline":
        connection_status = "offline"

    elif not valid_ages:
        connection_status = "unknown"

    elif min(valid_ages) <= NODE_TIMEOUT:
        connection_status = "online"

    else:
        connection_status = "offline"

    # Telemetry freshness
    if telemetry_age is None:
        telemetry_status = "no_data"

    elif -5 <= telemetry_age <= TELEMETRY_TIMEOUT:
        telemetry_status = "fresh"

    else:
        telemetry_status = "stale"

    # Sensor health from recent heartbeat
    sht31_ok = node.get("sht31_ok")

    heartbeat_is_fresh = (
        heartbeat_age is not None
        and -5 <= heartbeat_age <= HEARTBEAT_TIMEOUT
    )

    if (
        connection_status != "online"
        or not heartbeat_is_fresh
        or sht31_ok is None
    ):
        sensor_health = "unknown"

    elif sht31_ok == 1:
        sensor_health = "ok"

    else:
        sensor_health = "fault"

    return {
        "connection_status": connection_status,
        "telemetry_status": telemetry_status,
        "sensor_health": sensor_health,
}

def get_node_or_404(node_id):

    node = fetch_one("""
        SELECT *
        FROM sensor_nodes
        WHERE node_id = :node_id
    """, {"node_id": node_id})

    if node is None:
        raise HTTPException(
            status_code=404,
            detail="Node not found"
        )

    node.update(calculate_node_states(node))

    node["current_status"] = node["connection_status"]

    return node


@app.get("/")
def root():
    return {
        "project": "FIRE SCOUT",
        "api_version": "1.0.0",
        "status": "running"
    }


@app.get("/api/health")
def health():

    fetch_one("SELECT 1 AS connected")

    return {
        "api": "online",
        "database": "connected"
    }


@app.get("/api/nodes")
def get_nodes():

    nodes = fetch_all("""
        SELECT *
        FROM sensor_nodes
        ORDER BY node_id
    """)

    for node in nodes:
        node.update(calculate_node_states(node))

        node["current_status"] = node["connection_status"]

    return nodes


@app.get("/api/nodes/{node_id}")
def get_node(node_id: str):

    return get_node_or_404(node_id)


@app.get("/api/nodes/{node_id}/latest")
def get_latest(node_id: str):

    get_node_or_404(node_id)

    reading = fetch_one("""
        SELECT *
        FROM sensor_readings
        WHERE node_id = :node_id
        ORDER BY id DESC
        LIMIT 1
    """, {"node_id": node_id})

    if reading is None:
        raise HTTPException(
            status_code=404,
            detail="No sensor readings"
        )

    return reading


@app.get("/api/nodes/{node_id}/history")
def get_history(
    node_id: str,
    limit: int = Query(100, ge=1, le=1000)
):

    get_node_or_404(node_id)

    readings = fetch_all("""
        SELECT *
        FROM sensor_readings
        WHERE node_id = :node_id
        ORDER BY id DESC
        LIMIT :limit
    """, {
        "node_id": node_id,
        "limit": limit
    })

    return list(reversed(readings))


@app.get("/api/overview")
def get_overview():

    nodes = get_nodes()

    readings = fetch_one("""
        SELECT COUNT(*) AS total
        FROM sensor_readings
    """)

    return {
        "total_nodes": len(nodes),

        "online_nodes": sum(
            n["current_status"] == "online"
            for n in nodes
        ),

        "offline_nodes": sum(
            n["current_status"] == "offline"
            for n in nodes
        ),

        "unknown_nodes": sum(
            n["current_status"] == "unknown"
            for n in nodes
        ),

        "total_readings": readings["total"]
    }
