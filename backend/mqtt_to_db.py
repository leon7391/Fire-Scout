
import os
import json
import math
import sqlite3

from pathlib import Path
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "firescout.db"

load_dotenv(BASE_DIR / "backend" / ".env")

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.environ["MQTT_USER"]
MQTT_PASSWORD = os.environ["MQTT_PASSWORD"]
MQTT_TOPIC = os.getenv(
    "MQTT_TOPIC",
    "firescout/nodes/node01/telemetry"
)


def main():
    # Create SQLite database
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(DB_PATH)
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
    """)
    db.commit()

    print(f"Database ready: {DB_PATH}")

    # MQTT connection callback
    def on_connect(client, userdata, flags,
                   reason_code, properties):

        if reason_code.is_failure:
            print(f"MQTT connection failed: {reason_code}")
            return

        print("MQTT Connected!")
        client.subscribe(MQTT_TOPIC, qos=1)
        print(f"Subscribed: {MQTT_TOPIC}")

    # Receive sensor data
    def on_message(client, userdata, msg):
        try:
            payload = json.loads(
                msg.payload.decode("utf-8")
            )

            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object")

            node_id = payload["node_id"]
            temperature = float(payload["temperature"])
            humidity = float(payload["humidity"])
            mq2_raw = int(payload["mq2_raw"])

            # Validate input
            if not isinstance(node_id, str) or not node_id.strip():
                raise ValueError("Invalid node_id")

            if not (
                math.isfinite(temperature)
                and -40 <= temperature <= 125
                and math.isfinite(humidity)
                and 0 <= humidity <= 100
                and 0 <= mq2_raw <= 4095
            ):
                raise ValueError("Invalid sensor values")

            received_at = datetime.now(
                timezone.utc
            ).isoformat(timespec="seconds")

            db.execute("""
                INSERT INTO sensor_readings (
                    received_at,
                    node_id,
                    temperature_c,
                    humidity_pct,
                    mq2_raw
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                received_at,
                node_id,
                temperature,
                humidity,
                mq2_raw
            ))

            db.commit()

            print(
                f"[SAVED] {node_id} | "
                f"Temp: {temperature:.2f} C | "
                f"Hum: {humidity:.2f}% | "
                f"MQ2: {mq2_raw}"
            )

        except (KeyError, ValueError, TypeError,
                UnicodeError) as error:
            print(f"Invalid MQTT data: {error}")

        except sqlite3.Error as error:
            print(f"Database error: {error}")

    # MQTT client
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="firescout-db-subscriber"
    )

    client.username_pw_set(
        MQTT_USER,
        MQTT_PASSWORD
    )

    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(
        min_delay=1,
        max_delay=30
    )

    try:
        print("Connecting to MQTT Broker...")
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_forever()

    except KeyboardInterrupt:
        print("\nStopping database subscriber...")

    finally:
        client.disconnect()
        db.close()


if __name__ == "__main__":
    main()
