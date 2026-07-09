"""共通フィクスチャ: 一時 DB とテストクライアント."""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STATUS_REPORT_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("STATUS_REPORT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STATUS_REPORT_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("STATUS_REPORT_NO_BROWSER", "1")
    yield tmp_path


@pytest.fixture()
def client(tmp_env):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def make_xlsx(tmp_path):
    """簡易な測定結果一覧 xlsx を生成するファクトリ."""
    from openpyxl import Workbook

    def _make(rows, headers=None):
        headers = headers or ["利用者コード", "身長", "体重", "HbA1c", "血圧", "握力", "TUG"]
        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for r in rows:
            ws.append(r)
        path = tmp_path / "measurements.xlsx"
        wb.save(path)
        return path

    return _make
