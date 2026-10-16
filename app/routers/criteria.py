"""評価基準マスタ編集."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from .. import repo, uploads
from ..deps import get_db
from ..domain import AGE_BANDS, AGE_BAND_LABELS
from ..services import criteria_importer
from ..templating import templates

router = APIRouter(prefix="/criteria")


@router.get("")
def item_list(
    request: Request,
    imported: int | None = None,
    created: int | None = None,
    backup: str = "",
    conn: sqlite3.Connection = Depends(get_db),
):
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
        {"request": request, "items": items, "settings": settings, "active": "criteria",
         "import_result": (
             {"imported": imported, "created": created or 0, "backup": backup}
             if imported is not None else None
         )},
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


# --- 評価基準 Excel 取込 -----------------------------------------------------
# 静的パスなので {item_id} ルートより先に定義する。

def _import_form(request: Request, error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        "criteria_import.html",
        {"request": request, "active": "criteria", "error": error},
        status_code=status_code,
    )


@router.get("/import")
def import_form(request: Request):
    return _import_form(request)


@router.post("/import/analyze")
async def import_analyze(
    request: Request,
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_db),
):
    token = uploads.save_upload(await file.read(), file.filename)
    saved = uploads.resolve_token(token)
    try:
        preview = criteria_importer.analyze(conn, saved)
    except Exception as e:
        return _import_form(request, f"読み込みに失敗しました: {e}", status_code=400)
    if not preview.plans:
        return _import_form(
            request, "評価基準のシート(「60代」「70代　ペースメーカー」など)が見つかりませんでした。",
            status_code=400,
        )
    return templates.TemplateResponse(
        "criteria_import_preview.html",
        {"request": request, "active": "criteria", "preview": preview,
         "token": token, "orig_name": file.filename},
    )


@router.post("/import/commit")
def import_commit(token: str = Form(...), conn: sqlite3.Connection = Depends(get_db)):
    saved = uploads.resolve_token(token)
    if saved is None:
        return RedirectResponse("/criteria/import", status_code=303)
    preview = criteria_importer.analyze(conn, saved)
    backup = criteria_importer.backup_db(conn)
    stats = criteria_importer.apply(conn, preview)
    qs = f"imported={stats['updated'] + stats['created']}&created={stats['created']}&backup={backup.name}"
    return RedirectResponse(f"/criteria?{qs}", status_code=303)


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
    # チェックボックスは外すと送信されないため、既定値は「無効」にする
    is_active: str = Form(""),
    unmeasured_score: str = Form(""),
    unmeasured_comment: str = Form(""),
    pm_display: str = Form(""),
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
        unmeasured_score=int(unmeasured_score) if unmeasured_score in ("1", "2", "3", "4", "5") else None,
        unmeasured_comment=(unmeasured_comment.strip() or None),
        pm_display=pm_display if pm_display in ("with_pm", "without_pm") else None,
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
