
import os
import re
import json
import math
import time
import sqlite3

from pathlib import Path
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from event_rules import (
    init_event_tables,
    evaluate_telemetry,
    add_event,
)


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "firescout.db"

load_dotenv(BASE_DIR / "backend" / ".env")

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.environ["MQTT_USER"]
MQTT_PASSWORD = os.environ["MQTT_PASSWORD"]

TEMP_ALERT_C = float(os.getenv("TEMP_ALERT_C", "40"))
MQ2_ALERT_RAW = int(os.getenv("MQ2_ALERT_RAW", "2500"))

TOPICS = [
    "firescout/nodes/+/telemetry",
    "firescout/nodes/+/status",
    "firescout/nodes/+/heartbeat",
]


def now_utc():
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(DB_PATH, timeout=15)
    db.execute("PRAGMA journal_mode=WAL")

    db.executescript("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at TEXT NOT NULL,
            node_id TEXT NOT NULL,
            temperature_c REAL NOT NULL,
            humidity_pct REAL NOT NULL,
            mq2_raw INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sensor_node_time
        ON sensor_readings(node_id, received_at);

        CREATE TABLE IF NOT EXISTS sensor_nodes (
            node_id TEXT PRIMARY KEY,
            mqtt_node TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'unknown',
            last_seen TEXT,
            last_status_at TEXT,
            map_id TEXT,
            map_x REAL,
            map_y REAL,
            map_frame TEXT NOT NULL DEFAULT 'map'
        );
    """)

    init_event_tables(db)

    print("FIRE SCOUT Database V3 Ready!")

    def on_connect(
        client, userdata, flags, reason_code, properties
    ):
        if reason_code.is_failure:
            print("MQTT connection failed:", reason_code)
            return

        print("MQTT Connected!")

        for topic in TOPICS:
            result, _ = client.subscribe(topic, qos=1)

            if result == mqtt.MQTT_ERR_SUCCESS:
                print("Subscribed:", topic)
            else:
                print("Subscription failed:", topic)
    class DuplicateTelemetry(Exception):
        pass
    def on_message(client, userdata, msg):
        try:
            parts = msg.topic.split("/")

            if (
                len(parts) != 4
                or parts[0] != "firescout"
                or parts[1] != "nodes"
                or not re.fullmatch(r"node[0-9]{2,}", parts[2])
                or parts[3] not in (
                    "telemetry",
                    "status",
                    "heartbeat"
)
            ):
                raise ValueError("Invalid MQTT topic")

            mqtt_node = parts[2]
            message_type = parts[3]
            node_id = "firescout_node_" + mqtt_node[4:]

            timestamp = now_utc()

            if message_type == "telemetry":
                data = json.loads(
                    msg.payload.decode("utf-8")
                )

                if not isinstance(data, dict):
                    raise ValueError("Expected JSON object")

                if data.get("node_id") != node_id:
                    raise ValueError(
                        "node_id does not match MQTT topic"
                    )

                has_boot_id = "boot_id" in data
                has_seq = "seq" in data

                if has_boot_id != has_seq:
                    raise ValueError(
                        "Telemetry must contain both boot_id and seq"
                    )

                if has_boot_id:
                    boot_id = data["boot_id"]
                    seq = data["seq"]

                    if (
                        not isinstance(boot_id, str)
                        or not re.fullmatch(r"[0-9a-fA-F]{8}", boot_id)
                    ):
                        raise ValueError("Invalid boot_id")

                    if type(seq) is not int or seq < 1:
                        raise ValueError("Invalid telemetry seq")
                else:
                    boot_id = None
                    seq = None

                temp = float(data["temperature"])
                hum = float(data["humidity"])
                raw = data["mq2_raw"]

                if type(raw) is not int:
                    raise ValueError("Invalid MQ2 type")

                if not (
                    math.isfinite(temp)
                    and -40 <= temp <= 125
                    and math.isfinite(hum)
                    and 0 <= hum <= 100
                    and 0 <= raw <= 4095
                ):
                    raise ValueError("Invalid sensor values")

                is_simulated = (
                    data.get("simulated") is True
                )

                received_epoch = int(time.time())

                with db:
                    previous = db.execute("""
                        SELECT status
                        FROM sensor_nodes
                        WHERE node_id = ?
                    """, (node_id,)).fetchone()

                    db.execute("""
                        INSERT INTO sensor_nodes (
                            node_id, mqtt_node,
                            status, last_seen
                        )
                        VALUES (?, ?, 'online', ?)
                        ON CONFLICT(node_id)
                        DO UPDATE SET
                            status = 'online',
                            last_seen = excluded.last_seen
                    """, (
                        node_id,
                        mqtt_node,
                        timestamp
                    ))

                    
                    cursor = db.execute("""
                        INSERT INTO sensor_readings (
                            received_at,
                            node_id,
                            temperature_c,
                            humidity_pct,
                            mq2_raw,
                            boot_id,
                            seq
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(node_id, boot_id, seq)
                        WHERE boot_id IS NOT NULL
                        AND seq IS NOT NULL
                        DO NOTHING
                    """, (
                        timestamp,
                        node_id,
                        data["temperature"],
                        data["humidity"],
                        data["mq2_raw"],
                        boot_id,
                        seq
                    ))

                    if cursor.rowcount == 0:
                        raise DuplicateTelemetry(
                            f"{node_id} | boot_id={boot_id} | seq={seq}"
                        )

                    reading_id = cursor.lastrowid

                    evaluate_telemetry(
                        db,
                        node_id,
                        temp,
                        raw,
                        timestamp,
                        received_epoch,
                        reading_id,
                        is_simulated,
                        TEMP_ALERT_C,
                        MQ2_ALERT_RAW
                    )

                    if previous and previous[0] == "offline":
                        add_event(
                            db, node_id,
                            "node_online",
                            "info",
                            "Node resumed sending telemetry",
                            timestamp,
                            source="telemetry",
                            is_simulated=is_simulated,
                            reading_id=reading_id
                        )

                print(
                    f"[SAVED] {node_id} | "
                    f"Temp: {temp:.2f} C | "
                    f"Hum: {hum:.2f}% | "
                    f"MQ2: {raw}"
                )

            elif message_type == "status":
                status = msg.payload.decode(
                    "utf-8"
                ).strip().lower()

                if status not in ("online", "offline"):
                    raise ValueError("Invalid node status")

                with db:
                    previous = db.execute("""
                        SELECT status
                        FROM sensor_nodes
                        WHERE node_id = ?
                    """, (node_id,)).fetchone()

                    db.execute("""
                        INSERT INTO sensor_nodes (
                            node_id, mqtt_node,
                            status, last_status_at
                        )
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(node_id)
                        DO UPDATE SET
                            status = excluded.status,
                            last_status_at = excluded.last_status_at
                    """, (
                        node_id,
                        mqtt_node,
                        status,
                        timestamp
                    ))

                    if previous is None or previous[0] != status:
                        add_event(
                            db, node_id,
                            f"node_{status}",
                            "warning" if status == "offline"
                            else "info",
                            f"Node status changed to {status}",
                            timestamp,
                            source="mqtt_status"
                        )

                print(f"[STATUS] {node_id}: {status}")

            elif message_type == "heartbeat":
                data = json.loads(
                    msg.payload.decode("utf-8")
                )

                if not isinstance(data, dict):
                    raise ValueError("Invalid heartbeat JSON")

                if data.get("node_id") != node_id:
                    raise ValueError(
                        "Heartbeat node_id mismatch"
                    )

                uptime = data.get("uptime_ms")
                rssi = data.get("wifi_rssi")
                sht31_ok = data.get("sht31_ok")

                if (
                    type(uptime) is not int
                    or uptime < 0
                    or type(rssi) is not int
                    or not -127 <= rssi <= 0
                    or type(sht31_ok) is not bool
                ):
                    raise ValueError(
                        "Invalid heartbeat fields"
                    )

                with db:
                    previous = db.execute("""
                        SELECT sht31_ok
                        FROM sensor_nodes
                        WHERE node_id = ?
                    """, (node_id,)).fetchone()

                    db.execute("""
                        INSERT INTO sensor_nodes (
                            node_id,
                            mqtt_node,
                            status,
                            last_heartbeat_at,
                            wifi_rssi,
                            uptime_ms,
                            sht31_ok
                        )
                        VALUES (?, ?, 'online', ?, ?, ?, ?)
                        ON CONFLICT(node_id)
                        DO UPDATE SET
                            status = 'online',
                            last_heartbeat_at =
                                excluded.last_heartbeat_at,
                            wifi_rssi = excluded.wifi_rssi,
                            uptime_ms = excluded.uptime_ms,
                            sht31_ok = excluded.sht31_ok
                    """, (
                        node_id,
                        mqtt_node,
                        timestamp,
                        rssi,
                        uptime,
                        int(sht31_ok)
                    ))

                    old_health = (
                        previous[0]
                        if previous is not None
                        else None
                    )

                    if not sht31_ok and old_health != 0:
                        add_event(
                            db,
                            node_id,
                            "sensor_fault",
                            "warning",
                            "SHT31 sensor unavailable",
                            timestamp,
                            source="heartbeat"
                        )

                    elif sht31_ok and old_health == 0:
                        add_event(
                            db,
                            node_id,
                            "sensor_recovered",
                            "info",
                            "SHT31 sensor recovered",
                            timestamp,
                            source="heartbeat"
                        )

                print(
                    f"[HEARTBEAT] {node_id} | "
                    f"RSSI: {rssi} dBm | "
                    f"Uptime: {uptime} ms | "
                    f"SHT31: {'OK' if sht31_ok else 'FAULT'}"
                )
        except DuplicateTelemetry as exc:
            print(f"[DUPLICATE] Skipped: {exc}")
        except (
            ValueError, TypeError, KeyError,
            UnicodeError, json.JSONDecodeError
        ) as error:
            print("[INVALID]", error)

        except sqlite3.Error as error:
            print("[DATABASE ERROR]", error)

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="firescout-db-subscriber"
    )

    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(1, 30)

    try:
        print("Connecting to MQTT Broker...")
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_forever()

    except KeyboardInterrupt:
        print("\nStopping FIRE SCOUT Database...")

    finally:
        client.disconnect()
        db.close()


if __name__ == "__main__":
    main()

