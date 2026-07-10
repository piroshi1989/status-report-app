"""アプリ全体のパス・設定を集約するモジュール.

配布は Nuitka standalone(--standalone、フォルダ配布)を想定。PyInstaller と
通常の Python 実行にも対応する。
- 読み取り専用リソース(templates/static/フォント/schema.sql)はバンドル側を参照。
- DB や output などの**書き込み先は実 exe と同じ階層**に置く(通常実行はリポジトリ直下)。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_pyinstaller() -> bool:
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def _is_nuitka() -> bool:
    # Nuitka は各コンパイル済みモジュールに __compiled__ を注入する。
    return "__compiled__" in globals()


def is_frozen() -> bool:
    return _is_pyinstaller() or _is_nuitka()


def exe_dir() -> Path:
    """配布された実行ファイル(exe)が置かれているディレクトリ.

    Nuitka standalone / PyInstaller とも ``sys.executable`` が実 exe を指す。
    """
    return Path(sys.executable).resolve().parent


def app_package_dir() -> Path:
    """``app`` パッケージ(templates/static/schema.sql を含む)のディレクトリ."""
    if _is_pyinstaller():
        return Path(sys._MEIPASS) / "app"  # type: ignore[attr-defined]
    # Nuitka standalone と通常実行は __file__ の相対構造がそのまま使える。
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    """リソースの基準ディレクトリ(app パッケージの 1 つ上)."""
    return app_package_dir().parent


def _writable_base() -> Path:
    if is_frozen():
        return exe_dir()
    return Path(__file__).resolve().parent.parent  # リポジトリ直下


def data_dir() -> Path:
    """DB・アップロード一時ファイルを書き込むディレクトリ(環境変数で上書き可)."""
    override = os.environ.get("STATUS_REPORT_DATA_DIR")
    base = Path(override) if override else _writable_base() / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    override = os.environ.get("STATUS_REPORT_DB")
    if override:
        p = Path(override)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return data_dir() / "status_report.db"


def output_dir() -> Path:
    override = os.environ.get("STATUS_REPORT_OUTPUT_DIR")
    base = Path(override) if override else _writable_base() / "output"
    base.mkdir(parents=True, exist_ok=True)
    return base


def templates_dir() -> Path:
    return app_package_dir() / "templates"


def static_dir() -> Path:
    return app_package_dir() / "static"


def font_path() -> Path:
    """バンドルした日本語フォント(IPAexゴシック)."""
    return static_dir() / "fonts" / "ipaexg.ttf"


# --- サーバ起動オプション -------------------------------------------------

def auto_open_browser() -> bool:
    """起動時に既定ブラウザを開くか。``STATUS_REPORT_NO_BROWSER=1`` で無効化."""
    return os.environ.get("STATUS_REPORT_NO_BROWSER", "") not in ("1", "true", "True")


def preferred_port() -> int:
    return int(os.environ.get("STATUS_REPORT_PORT", "0") or "0")
