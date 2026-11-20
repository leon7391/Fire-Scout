
import os

from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / "backend" / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///data/firescout.db"
)

url = make_url(DATABASE_URL)

if url.get_backend_name() == "sqlite":
    db_path = Path(url.database)

    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path

    if not db_path.is_file():
        raise RuntimeError(
            f"Database not found: {db_path}"
        )

    url = url.set(database=str(db_path))

    engine = create_engine(
        url,
        connect_args={
            "check_same_thread": False,
            "timeout": 10
        },
        pool_pre_ping=True
    )

else:
    engine = create_engine(
        url,
        pool_pre_ping=True
    )


def fetch_all(query, params=None):
    with engine.connect() as conn:
        result = conn.execute(
            text(query),
            params or {}
        )

        return [
            dict(row)
            for row in result.mappings().all()
        ]


def fetch_one(query, params=None):
    with engine.connect() as conn:
        result = conn.execute(
            text(query),
            params or {}
        )

        row = result.mappings().first()

        return dict(row) if row else None
