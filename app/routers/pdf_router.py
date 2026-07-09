"""一括 PDF 出力."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response

from .. import config, repo
from ..deps import get_db
from ..services import pdf as pdf_svc
from ..services.report import build_report
from ..templating import templates

router = APIRouter(prefix="/batch")


@router.get("")
def batch_form(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    sessions = repo.list_sessions(conn)
    return templates.TemplateResponse(
        "batch.html", {"request": request, "active": "batch", "sessions": sessions}
    )


def _build_datas(conn, session_id: int):
    patients = repo.patients_in_session(conn, session_id)
    datas = []
    for p in patients:
        data = build_report(conn, p["id"], session_id)
        override = repo.get_setting(conn, f"summary_override:{session_id}:{p['id']}")
        if override:
            data.summary = override
        datas.append(data)
    return datas


@router.post("/generate")
def generate(
    session_id: int = Form(...),
    save_to_disk: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    title = repo.get_setting(conn, "report_title", "状況報告書") or "状況報告書"
    datas = _build_datas(conn, session_id)
    pdf_bytes = pdf_svc.render_batch(datas, title=title)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"status_reports_session{session_id}_{stamp}.pdf"

    if save_to_disk in ("1", "on", "true"):
        out = config.output_dir() / fname
        out.write_bytes(pdf_bytes)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
