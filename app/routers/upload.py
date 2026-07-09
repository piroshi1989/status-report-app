"""測定結果一覧のアップロード・取込."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from .. import config
from ..deps import get_db
from ..services import importer
from ..templating import templates

router = APIRouter(prefix="/upload")


def _uploads_dir() -> Path:
    d = config.data_dir() / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("")
def upload_form(request: Request):
    return templates.TemplateResponse(
        "upload.html", {"request": request, "active": "upload"}
    )


@router.post("/analyze")
async def analyze(
    request: Request,
    file: UploadFile = File(...),
    session_no: str = Form(""),
    measured_on: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    suffix = Path(file.filename or "upload.xlsx").suffix.lower() or ".xlsx"
    token = f"{uuid.uuid4().hex}{suffix}"
    saved = _uploads_dir() / token
    saved.write_bytes(await file.read())

    try:
        preview = importer.analyze(conn, saved)
    except Exception as e:  # 取込失敗は画面にエラー表示
        return templates.TemplateResponse(
            "upload.html",
            {"request": request, "active": "upload", "error": f"読み込みに失敗しました: {e}"},
            status_code=400,
        )

    return templates.TemplateResponse(
        "upload_preview.html",
        {
            "request": request, "active": "upload", "preview": preview,
            "token": token, "orig_name": file.filename,
            "session_no": session_no, "measured_on": measured_on,
        },
    )


@router.post("/commit")
def commit(
    token: str = Form(...),
    orig_name: str = Form(""),
    session_no: str = Form(""),
    measured_on: str = Form(""),
    auto_register: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    saved = _uploads_dir() / token
    if not saved.exists():
        return RedirectResponse("/upload", status_code=303)
    stats = importer.commit(
        conn, saved,
        session_no=int(session_no) if session_no.strip().isdigit() else None,
        measured_on=(measured_on or None),
        source_file=orig_name or token,
        auto_register=(auto_register in ("1", "on", "true")),
    )
    return RedirectResponse(f"/report?session_id={stats['session_id']}", status_code=303)
