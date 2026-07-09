"""SQLite 接続・初期化ユーティリティ."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import config


def _schema_sql() -> str:
    return (config.app_package_dir() / "schema.sql").read_text(encoding="utf-8")


def connect(db_file: Path | None = None) -> sqlite3.Connection:
    path = db_file or config.db_path()
    # 各リクエストが独立の接続を持ち、同一リクエスト内で(threadpool→event loop の順に)
    # 逐次使用するため check_same_thread=False は安全。
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn(db_file: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_file)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_file: Path | None = None, seed: bool = True) -> None:
    """スキーマを作成し、初回のみ既定のマスタ・シードを投入する."""
    with get_conn(db_file) as conn:
        conn.executescript(_schema_sql())
        if seed:
            from . import seed as seed_mod

            seed_mod.apply_seed(conn)
