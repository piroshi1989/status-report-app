"""FastAPI 依存関係(DB 接続)."""

from __future__ import annotations

from typing import Iterator

import sqlite3

from . import db


def get_db() -> Iterator[sqlite3.Connection]:
    conn = db.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
