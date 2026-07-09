"""アプリ全体のパス・設定を集約するモジュール.

PyInstaller の onefile 実行(``sys.frozen``)と通常の Python 実行の両方で
正しくパスを解決する。DB や output フォルダは exe と同じ階層(通常実行では
リポジトリ直下)に置き、静的ファイル・テンプレート・フォントはバンドルされた
リソース側を参照する。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """テンプレート・静的ファイル・フォント等の読み取り専用リソースの基準ディレクトリ.

    PyInstaller onefile では ``sys._MEIPASS`` に展開される。
    """
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def app_package_dir() -> Path:
    """``app`` パッケージ(templates/static を含む)のディレクトリ."""
    if _is_frozen():
        return resource_dir() / "app"
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    """DB や出力を書き込む、書き込み可能なデータディレクトリ.

    環境変数 ``STATUS_REPORT_DATA_DIR`` で上書き可能。
    frozen 実行では exe と同じ階層、通常実行ではリポジトリ直下の ``data/``。
    """
    override = os.environ.get("STATUS_REPORT_DATA_DIR")
    if override:
        base = Path(override)
    elif _is_frozen():
        base = Path(sys.executable).resolve().parent / "data"
    else:
        base = Path(__file__).resolve().parent.parent / "data"
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
    if override:
        base = Path(override)
    elif _is_frozen():
        base = Path(sys.executable).resolve().parent / "output"
    else:
        base = Path(__file__).resolve().parent.parent / "output"
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
