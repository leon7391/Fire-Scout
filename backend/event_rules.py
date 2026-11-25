
def init_event_tables(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS system_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            node_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            value REAL,
            threshold REAL,
            source TEXT NOT NULL DEFAULT 'telemetry',
            is_simulated INTEGER NOT NULL DEFAULT 0,
            reading_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS alert_state (
            node_id TEXT NOT NULL,
            rule_code TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 0,
            high_count INTEGER NOT NULL DEFAULT 0,
            clear_count INTEGER NOT NULL DEFAULT 0,
            last_sample_epoch INTEGER,
            PRIMARY KEY (node_id, rule_code)
        );

        CREATE INDEX IF NOT EXISTS idx_events_time
        ON system_events(created_at);
    """)

    # Compatible with preliminary V3 tables
    upgrades = {
        "system_events": {
            "source": "TEXT NOT NULL DEFAULT 'telemetry'",
            "is_simulated": "INTEGER NOT NULL DEFAULT 0",
            "reading_id": "INTEGER",
        },
        "alert_state": {
            "high_count": "INTEGER NOT NULL DEFAULT 0",
            "clear_count": "INTEGER NOT NULL DEFAULT 0",
            "last_sample_epoch": "INTEGER",
        },
    }

    for table, columns in upgrades.items():
        existing = {
            row[1]
            for row in db.execute(f"PRAGMA table_info({table})")
        }

        for column, definition in columns.items():
            if column not in existing:
                db.execute(
                    f"ALTER TABLE {table} "
                    f"ADD COLUMN {column} {definition}"
                )

    db.commit()


def add_event(
    db, node_id, event_type, severity, message,
    timestamp, value=None, threshold=None,
    source="telemetry", is_simulated=False,
    reading_id=None
):
    db.execute("""
        INSERT INTO system_events (
            created_at, node_id, event_type,
            severity, message, value, threshold,
            source, is_simulated, reading_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp, node_id, event_type,
        severity, message, value, threshold,
        source, int(is_simulated), reading_id
    ))

    print(f"[EVENT] {node_id}: {event_type}")


def evaluate_rule(
    db, node_id, rule_code, value, threshold,
    clear_margin, timestamp, epoch, reading_id,
    is_simulated=False, required_samples=3
):
    row = db.execute("""
        SELECT active, high_count, clear_count,
               last_sample_epoch
        FROM alert_state
        WHERE node_id = ? AND rule_code = ?
    """, (node_id, rule_code)).fetchone()

    active, high_count, clear_count, last_epoch = (
        row if row else (0, 0, 0, None)
    )

    # Do not join samples separated by a long gap
    if last_epoch is not None:
        if epoch - last_epoch > 10 or epoch < last_epoch:
            high_count = 0
            clear_count = 0

    if value >= threshold:
        high_count = min(
            high_count + 1, required_samples
        )
        clear_count = 0

        if not active and high_count >= required_samples:
            active = 1
            add_event(
                db, node_id,
                f"{rule_code}_suspicious",
                "warning",
                "Experimental threshold exceeded",
                timestamp, value, threshold,
                is_simulated=is_simulated,
                reading_id=reading_id
            )

    elif value <= threshold - clear_margin:
        clear_count = min(
            clear_count + 1, required_samples
        )
        high_count = 0

        if active and clear_count >= required_samples:
            active = 0
            add_event(
                db, node_id,
                f"{rule_code}_normalized",
                "info",
                "Value returned below test threshold",
                timestamp, value, threshold,
                is_simulated=is_simulated,
                reading_id=reading_id
            )

    else:
        high_count = 0
        clear_count = 0

    db.execute("""
        INSERT INTO alert_state (
            node_id, rule_code, active,
            high_count, clear_count, last_sample_epoch
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(node_id, rule_code)
        DO UPDATE SET
            active = excluded.active,
            high_count = excluded.high_count,
            clear_count = excluded.clear_count,
            last_sample_epoch = excluded.last_sample_epoch
    """, (
        node_id, rule_code, active,
        high_count, clear_count, epoch
    ))


def evaluate_telemetry(
    db, node_id, temp, mq2_raw,
    timestamp, epoch, reading_id,
    is_simulated, temp_limit, mq2_limit
):
    evaluate_rule(
        db, node_id, "temperature",
        temp, temp_limit, 2.0,
        timestamp, epoch, reading_id,
        is_simulated
    )

    evaluate_rule(
        db, node_id, "mq2_raw",
        mq2_raw, mq2_limit, 100,
        timestamp, epoch, reading_id,
        is_simulated
    )

