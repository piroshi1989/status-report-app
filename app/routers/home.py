"""ホーム/ダッシュボード."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request

from .. import repo
from ..deps import get_db
from ..templating import templates

router = APIRouter()


@router.get("/")
def home(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    patient_count = conn.execute("SELECT COUNT(*) c FROM patients WHERE is_active=1").fetchone()["c"]
    item_count = conn.execute("SELECT COUNT(*) c FROM eval_items WHERE is_active=1").fetchone()["c"]
    sessions = repo.list_sessions(conn)[:8]
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "patient_count": patient_count,
            "item_count": item_count,
            "sessions": sessions,
            "active": "home",
        },
    )
