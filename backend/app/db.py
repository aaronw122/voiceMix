import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _db_path() -> str:
    path = os.environ.get("DB_PATH", "data/voicemix.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def init_db() -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clips (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                object_key TEXT NOT NULL,
                content_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def insert_clip(clip_id: str, title: str, object_key: str, content_type: str = "audio/mpeg") -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            "INSERT INTO clips VALUES (?, ?, ?, ?, ?)",
            (clip_id, title, object_key, content_type, datetime.now(timezone.utc).isoformat()),
        )


def get_clip(clip_id: str) -> dict | None:
    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        return dict(row) if row else None
