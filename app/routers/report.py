"""状況報告書プレビュー・個別 PDF."""

from __future__ import annotations

import base64
import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response

from .. import repo
from ..deps import get_db
from ..services import pdf as pdf_svc
from ..services import radar as radar_svc
from ..services.report import build_report
from ..templating import templates

router = APIRouter(prefix="/report")


def _override_key(sid: int, pid: int) -> str:
    return f"summary_override:{sid}:{pid}"


def _load_report(conn, pid: int, sid: int):
    data = build_report(conn, pid, sid)
    override = repo.get_setting(conn, _override_key(sid, pid))
    if override:
        data.summary = override
    return data


@router.get("")
def report_index(
    request: Request,
    session_id: int | None = None,
    patient_id: int | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    sessions = repo.list_sessions(conn)
    if session_id is None and sessions:
        session_id = sessions[0]["id"]

    patients = repo.patients_in_session(conn, session_id) if session_id else []
    if patient_id is None and patients:
        patient_id = patients[0]["id"]

    data = None
    radar_b64 = None
    if session_id and patient_id:
        data = _load_report(conn, patient_id, session_id)
        png = radar_svc.render_radar(data.radar_labels, data.radar_scores,
                                     prev_scores=data.radar_prev_scores)
        radar_b64 = base64.b64encode(png).decode("ascii")

    return templates.TemplateResponse(
        "report.html",
        {
            "request": request, "active": "report",
            "sessions": sessions, "patients": patients,
            "session_id": session_id, "patient_id": patient_id,
            "data": data, "radar_b64": radar_b64,
        },
    )


@router.post("/summary")
def save_summary(
    session_id: int = Form(...),
    patient_id: int = Form(...),
    summary: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    repo.set_setting(conn, _override_key(session_id, patient_id), summary)
    return RedirectResponse(
        f"/report?session_id={session_id}&patient_id={patient_id}", status_code=303
    )


@router.get("/pdf")
def report_pdf(
    session_id: int,
    patient_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    data = _load_report(conn, patient_id, session_id)
    title = repo.get_setting(conn, "report_title", "状況報告書") or "状況報告書"
    pdf_bytes = pdf_svc.render_single(data, title=title)
    fname = f"report_{data.patient['code']}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )
