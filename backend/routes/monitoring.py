
import csv
import io

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ..database import fetch_all, fetch_one


router = APIRouter(
    prefix="/api",
    tags=["FIRE SCOUT Monitoring V3"]
)


def build_filters(node_id, event_type, hours):
    since = (
        datetime.now(timezone.utc)
        - timedelta(hours=hours)
    ).isoformat(timespec="seconds")

    conditions = ["created_at >= :since"]
    params = {"since": since}

    if node_id:
        conditions.append("node_id = :node_id")
        params["node_id"] = node_id

    if event_type:
        conditions.append("event_type = :event_type")
        params["event_type"] = event_type

    return " AND ".join(conditions), params


@router.get("/events")
def get_events(
    node_id: str | None = None,
    event_type: str | None = None,
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(100, ge=1, le=500)
):
    where, params = build_filters(
        node_id, event_type, hours
    )

    params["limit"] = limit

    return fetch_all(f"""
        SELECT
            id, created_at, node_id, event_type,
            severity, message, value, threshold,
            source, is_simulated, reading_id
        FROM system_events
        WHERE {where}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
    """, params)


@router.get("/statistics")
def get_statistics(
    node_id: str | None = None,
    hours: int = Query(24, ge=1, le=720)
):
    since = (
        datetime.now(timezone.utc)
        - timedelta(hours=hours)
    ).isoformat(timespec="seconds")

    params = {"since": since}

    node_filter = ""

    if node_id:
        node_filter = " AND node_id = :node_id"
        params["node_id"] = node_id

    readings = fetch_one(f"""
        SELECT
            COUNT(*) AS total_samples,
            ROUND(AVG(temperature_c), 2) AS avg_temp,
            ROUND(MIN(temperature_c), 2) AS min_temp,
            ROUND(MAX(temperature_c), 2) AS max_temp,
            ROUND(AVG(humidity_pct), 2) AS avg_humidity,
            MIN(mq2_raw) AS min_mq2,
            MAX(mq2_raw) AS max_mq2
        FROM sensor_readings
        WHERE received_at >= :since
        {node_filter}
    """, params)

    events = fetch_one(f"""
        SELECT
            COUNT(*) AS total_events,
            COALESCE(SUM(
                CASE WHEN severity = 'warning'
                THEN 1 ELSE 0 END
            ), 0) AS warning_events
        FROM system_events
        WHERE created_at >= :since
        {node_filter}
    """, params)

    return {
        "period_hours": hours,
        "node_id": node_id,
        **readings,
        **events
    }


@router.get("/alerts/active")
def get_active_alerts():
    return fetch_all("""
        SELECT
            node_id,
            rule_code,
            active,
            high_count,
            clear_count,
            last_sample_epoch
        FROM alert_state
        WHERE active = 1
        ORDER BY node_id, rule_code
    """)


@router.get("/events/export")
def export_events(
    node_id: str | None = None,
    event_type: str | None = None,
    hours: int = Query(24, ge=1, le=720)
):
    where, params = build_filters(
        node_id, event_type, hours
    )

    params["limit"] = 5000

    events = fetch_all(f"""
        SELECT
            id, created_at, node_id, event_type,
            severity, message, value, threshold,
            source, is_simulated
        FROM system_events
        WHERE {where}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
    """, params)

    fields = [
        "id", "created_at", "node_id",
        "event_type", "severity", "message",
        "value", "threshold", "source",
        "is_simulated"
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(fields)

    def csv_safe(value):
        if isinstance(value, str) and value.startswith(
            ("=", "+", "-", "@", "\t", "\r", "\n")
        ):
            return "'" + value
        return value

    for event in events:
        writer.writerow([
            csv_safe(event.get(field))
            for field in fields
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                'attachment; filename="firescout_events.csv"'
        }
    )


@router.get("/events/{event_id}")
def get_event_detail(event_id: int):
    event = fetch_one("""
        SELECT
            e.*,
            r.received_at AS reading_received_at,
            r.temperature_c,
            r.humidity_pct,
            r.mq2_raw
        FROM system_events AS e
        LEFT JOIN sensor_readings AS r
            ON r.id = e.reading_id
        WHERE e.id = :event_id
    """, {"event_id": event_id})

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Event not found"
        )

    return event

