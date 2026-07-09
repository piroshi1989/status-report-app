"""アップロード一時ファイルの安全な保存・解決.

トークンはこのモジュールが払い出す ``<uuid16進32桁>.<ext>`` のみを正とし、
フォームから戻ってきたトークンは正規表現とディレクトリ包含で検証する。
これによりパストラバーサル(``../`` 等)や想定外拡張子を排除する。
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from . import config

ALLOWED_SUFFIXES = {".xls", ".xlsx"}
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}\.(?:xls|xlsx)$")


def uploads_dir() -> Path:
    d = config.data_dir() / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_upload(content: bytes, filename: str | None) -> str:
    """アップロード内容を保存し、安全なトークン(ファイル名)を返す."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        suffix = ".xlsx"
    token = f"{uuid.uuid4().hex}{suffix}"
    (uploads_dir() / token).write_bytes(content)
    return token


def resolve_token(token: str) -> Path | None:
    """トークンを検証し、uploads 配下の実在ファイルパスを返す。不正なら None."""
    if not _TOKEN_RE.match(token or ""):
        return None
    base = uploads_dir().resolve()
    path = (base / token).resolve()
    if base not in path.parents or not path.is_file():
        return None
    return path
