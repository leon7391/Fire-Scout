
import os

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .database import fetch_all, fetch_one


app = FastAPI(
    title="FIRE SCOUT API",
    description="Fire Monitoring and Robot Management",
    version="1.0.0"
)

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


def calculate_status(node):

    if node["status"] == "offline":
        return "offline"

    last_seen = node.get("last_seen")

    if not last_seen:
        return "unknown"

    if isinstance(last_seen, str):
        last_seen = datetime.fromisoformat(
            last_seen.replace("Z", "+00:00")
        )

    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(
            tzinfo=timezone.utc
        )

    now = datetime.now(timezone.utc)

    elapsed = (now - last_seen).total_seconds()

    if elapsed > NODE_TIMEOUT:
        return "offline"

    return "online"


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

    node["current_status"] = calculate_status(node)

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
        node["current_status"] = calculate_status(node)

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
