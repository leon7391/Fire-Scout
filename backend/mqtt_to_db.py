
import os
import re
import json
import math
import sqlite3

from pathlib import Path
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "firescout.db"

load_dotenv(BASE_DIR / "backend" / ".env")

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.environ["MQTT_USER"]
MQTT_PASSWORD = os.environ["MQTT_PASSWORD"]

TOPICS = [
    "firescout/nodes/+/telemetry",
    "firescout/nodes/+/status"
]


def now_utc():
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")

    # Existing sensor data is preserved
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
    db.commit()

    print("FIRE SCOUT Database V2 Ready!")

    def on_connect(client, userdata, flags,
                   reason_code, properties):

        if reason_code.is_failure:
            print("MQTT connection failed:", reason_code)
            return

        print("MQTT Connected!")

        for topic in TOPICS:
            result, mid = client.subscribe(topic, qos=1)
            if result == mqtt.MQTT_ERR_SUCCESS:
                print("Subscribed:", topic)
            else:
                print("Subscribe request failed:", topic)

    def on_message(client, userdata, msg):
        try:
            parts = msg.topic.split("/")

            if (len(parts) != 4 or
                parts[0] != "firescout" or
                parts[1] != "nodes" or
                not re.fullmatch(r"node[0-9]{2,}", parts[2])):
                raise ValueError("Invalid MQTT topic")

            mqtt_node = parts[2]
            message_type = parts[3]

            # node01 -> firescout_node_01
            node_id = "firescout_node_" + mqtt_node[4:]
            timestamp = now_utc()

            if message_type == "telemetry":
                data = json.loads(
                    msg.payload.decode("utf-8")
                )

                if not isinstance(data, dict):
                    raise ValueError("Invalid JSON object")

                if data.get("node_id") != node_id:
                    raise ValueError("node_id does not match topic")

                temp = float(data["temperature"])
                hum = float(data["humidity"])
                raw = data["mq2_raw"]

                if type(raw) is not int:
                    raise ValueError("MQ2 must be an integer")

                if not (
                    math.isfinite(temp)
                    and -40 <= temp <= 125
                    and math.isfinite(hum)
                    and 0 <= hum <= 100
                    and 0 <= raw <= 4095
                ):
                    raise ValueError("Invalid sensor data")

                with db:
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
                    """, (node_id, mqtt_node, timestamp))

                    db.execute("""
                        INSERT INTO sensor_readings (
                            received_at, node_id,
                            temperature_c,
                            humidity_pct, mq2_raw
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        timestamp, node_id,
                        temp, hum, raw
                    ))

                print(
                    f"[SAVED] {node_id} | "
                    f"{temp:.2f} C | "
                    f"{hum:.2f}% | MQ2: {raw}"
                )

            elif message_type == "status":
                status = msg.payload.decode(
                    "utf-8"
                ).strip().lower()

                if status not in ("online", "offline"):
                    raise ValueError("Invalid node status")

                with db:
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
                        node_id, mqtt_node,
                        status, timestamp
                    ))

                print(f"[STATUS] {node_id}: {status}")

        except (ValueError, TypeError, KeyError,
                UnicodeError) as error:
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
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_forever()

    except KeyboardInterrupt:
        print("\nStopping FIRE SCOUT Database...")

    finally:
        client.disconnect()
        db.close()


if __name__ == "__main__":
    main()

