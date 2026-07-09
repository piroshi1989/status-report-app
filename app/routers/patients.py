"""患者(利用者)管理 CRUD."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from .. import repo
from ..deps import get_db
from ..domain import calc_age, band_for, AGE_BAND_LABELS
from ..templating import templates

router = APIRouter(prefix="/patients")


@router.get("")
def list_patients(request: Request, q: str = "", conn: sqlite3.Connection = Depends(get_db)):
    rows = repo.list_patients(conn, q=q, include_inactive=True)
    patients = []
    for r in rows:
        age = calc_age(r["birth_date"], None)
        band = band_for(r["birth_date"], None)
        patients.append({"row": r, "age": age, "band": AGE_BAND_LABELS.get(band, "")})
    return templates.TemplateResponse(
        "patients_list.html",
        {"request": request, "patients": patients, "q": q, "active": "patients"},
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
