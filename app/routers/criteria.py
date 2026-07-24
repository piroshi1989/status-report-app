"""評価基準マスタ編集."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from .. import repo
from ..deps import get_db
from ..domain import AGE_BANDS, AGE_BAND_LABELS
from ..templating import templates

router = APIRouter(prefix="/criteria")


@router.get("")
def item_list(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    items = repo.list_items(conn, include_inactive=True)
    settings = {
        "facility_name": repo.get_setting(conn, "facility_name", "") or "",
        "report_title": repo.get_setting(conn, "report_title", "状況報告書") or "",
        "disclaimer": repo.get_setting(conn, "disclaimer", "") or "",
        "summary_rank_1": repo.get_setting(conn, "summary_rank_1", "") or "",
        "summary_rank_2": repo.get_setting(conn, "summary_rank_2", "") or "",
        "summary_rank_3": repo.get_setting(conn, "summary_rank_3", "") or "",
        "summary_rank_4": repo.get_setting(conn, "summary_rank_4", "") or "",
    }
    return templates.TemplateResponse(
        "criteria_list.html",
        {"request": request, "items": items, "settings": settings, "active": "criteria"},
    )


@router.get("/new")
def new_item(request: Request):
    return templates.TemplateResponse(
        "item_form.html", {"request": request, "item": None, "active": "criteria"}
    )


@router.post("/new")
def create_item(
    name: str = Form(...),
    unit: str = Form(""),
    category: str = Form(""),
    sort_order: str = Form("0"),
    direction: str = Form("higher_better"),
    in_radar: str = Form(""),
    source_column: str = Form(""),
    derived_formula: str = Form(""),
    is_qualitative: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    item_id = repo.create_item(
        conn, name=name, unit=unit, category=category,
        sort_order=int(sort_order or 0), direction=direction,
        in_radar=1 if in_radar in ("1", "on", "true") else 0,
        source_column=(source_column or None),
        derived_formula=(derived_formula or None),
        is_qualitative=1 if is_qualitative in ("1", "on", "true") else 0,
    )
    return RedirectResponse(f"/criteria/{item_id}", status_code=303)


@router.get("/{item_id}")
def item_detail(item_id: int, request: Request, conn: sqlite3.Connection = Depends(get_db)):
    item = repo.get_item(conn, item_id)
    crit = repo.list_criteria_for_item(conn, item_id)
    return templates.TemplateResponse(
        "criteria_detail.html",
        {
            "request": request, "item": item, "criteria": crit,
            "age_bands": AGE_BANDS, "age_labels": AGE_BAND_LABELS, "active": "criteria",
        },
    )


@router.post("/{item_id}/item")
def update_item(
    item_id: int,
    name: str = Form(...),
    unit: str = Form(""),
    category: str = Form(""),
    sort_order: str = Form("0"),
    direction: str = Form("higher_better"),
    in_radar: str = Form(""),
    source_column: str = Form(""),
    derived_formula: str = Form(""),
    is_qualitative: str = Form(""),
    is_active: str = Form("1"),
    conn: sqlite3.Connection = Depends(get_db),
):
    repo.update_item(
        conn, item_id, name=name, unit=unit, category=category,
        sort_order=int(sort_order or 0), direction=direction,
        in_radar=1 if in_radar in ("1", "on", "true") else 0,
        source_column=(source_column or None),
        derived_formula=(derived_formula or None),
        is_qualitative=1 if is_qualitative in ("1", "on", "true") else 0,
        is_active=1 if is_active in ("1", "on", "true") else 0,
    )
    return RedirectResponse(f"/criteria/{item_id}", status_code=303)


@router.post("/{item_id}/criterion/add")
def add_criterion(
    item_id: int,
    sex: str = Form(""),
    age_band: str = Form(""),
    pacemaker: str = Form(""),
    threshold: str = Form(...),
    score: str = Form(...),
    comment: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    repo.add_criterion(
        conn, item_id,
        (sex or None), (age_band or None),
        (int(pacemaker) if pacemaker in ("0", "1") else None),
        float(threshold), int(score), (comment or None),
    )
    return RedirectResponse(f"/criteria/{item_id}", status_code=303)


@router.post("/{item_id}/criterion/{crit_id}/delete")
def delete_criterion(item_id: int, crit_id: int, conn: sqlite3.Connection = Depends(get_db)):
    repo.delete_criterion(conn, crit_id)
    return RedirectResponse(f"/criteria/{item_id}", status_code=303)


@router.post("/settings")
def save_settings(
    facility_name: str = Form(""),
    report_title: str = Form("状況報告書"),
    disclaimer: str = Form(""),
    summary_rank_1: str = Form(""),
    summary_rank_2: str = Form(""),
    summary_rank_3: str = Form(""),
    summary_rank_4: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
):
    repo.set_setting(conn, "facility_name", facility_name)
    repo.set_setting(conn, "report_title", report_title)
    repo.set_setting(conn, "disclaimer", disclaimer)
    repo.set_setting(conn, "summary_rank_1", summary_rank_1)
    repo.set_setting(conn, "summary_rank_2", summary_rank_2)
    repo.set_setting(conn, "summary_rank_3", summary_rank_3)
    repo.set_setting(conn, "summary_rank_4", summary_rank_4)
    return RedirectResponse("/criteria", status_code=303)
