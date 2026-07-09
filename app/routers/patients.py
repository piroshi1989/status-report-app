"""患者(利用者)管理 CRUD."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

from .. import config, repo
from ..deps import get_db
from ..domain import calc_age, band_for, AGE_BAND_LABELS
from ..services import patient_importer
from ..templating import templates

router = APIRouter(prefix="/patients")


def _uploads_dir() -> Path:
    d = config.data_dir() / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("")
def list_patients(
    request: Request,
    q: str = "",
    created: int | None = None,
    updated: int | None = None,
    skipped: int | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    rows = repo.list_patients(conn, q=q, include_inactive=True)
    patients = []
    for r in rows:
        age = calc_age(r["birth_date"], None)
        band = band_for(r["birth_date"], None)
        patients.append({"row": r, "age": age, "band": AGE_BAND_LABELS.get(band, "")})
    import_result = None
    if created is not None or updated is not None:
        import_result = {"created": created or 0, "updated": updated or 0, "skipped": skipped or 0}
    return templates.TemplateResponse(
        "patients_list.html",
        {"request": request, "patients": patients, "q": q, "active": "patients",
         "import_result": import_result},
    )


@router.get("/new")
def new_patient(request: Request):
    return templates.TemplateResponse(
        "patient_form.html",
        {"request": request, "patient": None, "active": "patients", "error": None},
    )


@router.post("/new")
def create_patient(
    request: Request,
    code: str = Form(...),
    name: str = Form(""),
    sex: str = Form(""),
    birth_date: str = Form(""),
    pacemaker: str = Form("0"),
    note: str = Form(""),
    med_info: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    if repo.get_patient_by_code(conn, code):
        return templates.TemplateResponse(
            "patient_form.html",
            {"request": request, "patient": None, "active": "patients",
             "error": f"利用者コード {code} は既に登録されています。"},
            status_code=400,
        )
    repo.create_patient(
        conn, code=code, name=name, sex=(sex or None), birth_date=(birth_date or None),
        pacemaker=1 if pacemaker in ("1", "on", "true") else 0, note=note, med_info=med_info,
    )
    return RedirectResponse("/patients", status_code=303)


# --- Excel 一括取込 --------------------------------------------------------
# 静的パスなので {pid} ルートより先に定義する。

@router.get("/import")
def import_form(request: Request):
    return templates.TemplateResponse(
        "patients_import.html", {"request": request, "active": "patients", "error": None},
    )


@router.get("/import/template")
def import_template():
    xlsx = patient_importer.build_template()
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="patients_template.xlsx"'},
    )


@router.post("/import/analyze")
async def import_analyze(
    request: Request,
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_db),
):
    suffix = Path(file.filename or "patients.xlsx").suffix.lower() or ".xlsx"
    token = f"{uuid.uuid4().hex}{suffix}"
    saved = _uploads_dir() / token
    saved.write_bytes(await file.read())

    try:
        preview = patient_importer.analyze(conn, saved)
    except Exception as e:
        return templates.TemplateResponse(
            "patients_import.html",
            {"request": request, "active": "patients", "error": f"読み込みに失敗しました: {e}"},
            status_code=400,
        )

    if preview.missing_headers:
        return templates.TemplateResponse(
            "patients_import.html",
            {"request": request, "active": "patients",
             "error": f"必須列が見つかりません: {'/'.join(preview.missing_headers)}"},
            status_code=400,
        )

    return templates.TemplateResponse(
        "patients_import_preview.html",
        {"request": request, "active": "patients", "preview": preview,
         "token": token, "orig_name": file.filename},
    )


@router.post("/import/commit")
def import_commit(
    token: str = Form(...),
    update_existing: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    saved = _uploads_dir() / token
    if not saved.exists():
        return RedirectResponse("/patients/import", status_code=303)
    stats = patient_importer.commit(
        conn, saved, update_existing=(update_existing in ("1", "on", "true")),
    )
    qs = f"created={stats['created']}&updated={stats['updated']}&skipped={stats['skipped']}"
    return RedirectResponse(f"/patients?{qs}", status_code=303)


@router.get("/{pid}/edit")
def edit_patient(pid: int, request: Request, conn: sqlite3.Connection = Depends(get_db)):
    patient = repo.get_patient(conn, pid)
    return templates.TemplateResponse(
        "patient_form.html",
        {"request": request, "patient": patient, "active": "patients", "error": None},
    )


@router.post("/{pid}/edit")
def update_patient(
    pid: int,
    name: str = Form(""),
    sex: str = Form(""),
    birth_date: str = Form(""),
    pacemaker: str = Form("0"),
    note: str = Form(""),
    med_info: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    repo.update_patient(
        conn, pid, name=name, sex=(sex or None), birth_date=(birth_date or None),
        pacemaker=1 if pacemaker in ("1", "on", "true") else 0, note=note, med_info=med_info,
    )
    return RedirectResponse("/patients", status_code=303)


@router.post("/{pid}/toggle")
def toggle_active(pid: int, conn: sqlite3.Connection = Depends(get_db)):
    p = repo.get_patient(conn, pid)
    if p:
        repo.set_patient_active(conn, pid, not p["is_active"])
    return RedirectResponse("/patients", status_code=303)
