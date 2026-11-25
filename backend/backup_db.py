
import os
import sqlite3

from contextlib import closing
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

DATABASE_PATH = PROJECT_DIR / "data" / "firescout.db"

BACKUP_DIR = Path.home() / "firescout-backups"

MAX_BACKUPS = 14

REQUIRED_TABLES = {
    "sensor_nodes",
    "sensor_readings",
    "system_events",
    "alert_state",
}


def backup_database():
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True
    )
    BACKUP_DIR.chmod(0o700)

    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    backup_path = BACKUP_DIR / (
        f"firescout_{timestamp}.db"
    )

    temp_path = BACKUP_DIR / (
        f".firescout_{timestamp}.tmp"
    )

    print("[BACKUP] Starting SQLite backup...")

    try:
        source_uri = (
            f"file:{DATABASE_PATH}?mode=ro"
        )

        with closing(
            sqlite3.connect(
                source_uri,
                uri=True,
                timeout=30
            )
        ) as source:

            with closing(
                sqlite3.connect(
                    str(temp_path),
                    timeout=30
                )
            ) as destination:

                source.backup(
                    destination,
                    pages=100,
                    sleep=0.05
                )

                result = destination.execute(
                    "PRAGMA quick_check"
                ).fetchone()[0]

                if result != "ok":
                    raise RuntimeError(
                        f"Backup integrity error: {result}"
                    )

                tables = {
                    row[0]
                    for row in destination.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'table'"
                    )
                }

                missing_tables = (
                    REQUIRED_TABLES - tables
                )

                if missing_tables:
                    raise RuntimeError(
                        f"Missing tables: {missing_tables}"
                    )

        os.chmod(temp_path, 0o600)
        temp_path.replace(backup_path)

        print(f"[BACKUP] Saved: {backup_path}")
        print("[BACKUP] Integrity: OK")

        backups = sorted(
            BACKUP_DIR.glob("firescout_*.db"),
            reverse=True
        )

        for old_backup in backups[MAX_BACKUPS:]:
            old_backup.unlink()
            print(
                f"[BACKUP] Removed old: "
                f"{old_backup.name}"
            )

        print("[BACKUP] Completed successfully")

    finally:
        if temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    backup_database()
