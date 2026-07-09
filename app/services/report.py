"""状況報告書のデータ組み立て(表・レーダー・総合評価)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from .. import repo
from ..domain import band_for, stars
from .evaluation import evaluate


@dataclass
class ReportLine:
    item_id: int
    name: str
    unit: str
    category: str
    in_radar: bool
    measured: bool
    value: Optional[float]
    raw_text: str
    score: Optional[int]
    stars: str
    comment: str


@dataclass
class ReportData:
    patient: sqlite3.Row
    session: sqlite3.Row
    age: Optional[int]
    age_band: Optional[str]
    lines: list[ReportLine] = field(default_factory=list)
    radar_labels: list[str] = field(default_factory=list)
    radar_scores: list[int] = field(default_factory=list)
    summary: str = ""
    disclaimer: str = ""

    @property
    def radar_items(self) -> list[ReportLine]:
        return [ln for ln in self.lines if ln.in_radar]


def build_report(conn: sqlite3.Connection, patient_id: int, session_id: int) -> ReportData:
    from ..domain import calc_age

    patient = repo.get_patient(conn, patient_id)
    session = repo.get_session(conn, session_id)
    measured_on = session["measured_on"] if session else None
    age = calc_age(patient["birth_date"], measured_on)
    age_band = band_for(patient["birth_date"], measured_on)

    measurements = repo.get_measurements(conn, session_id, patient_id)
    items = repo.list_items(conn)

    data = ReportData(patient=patient, session=session, age=age, age_band=age_band)
    data.disclaimer = repo.get_setting(conn, "disclaimer", "") or ""

    good = poor = total_scored = 0
    for it in items:
        m = measurements.get(it["id"])
        value = m["value"] if m else None
        raw_text = (m["raw_text"] if m else "") or ""
        rows = repo.criterion_rows_for_item(conn, it["id"])
        result = evaluate(
            rows, value,
            sex=patient["sex"], age_band=age_band,
            pacemaker=patient["pacemaker"],
        )
        comment = result.comment or ""
        if not result.measured:
            comment = "未測定"
        line = ReportLine(
            item_id=it["id"], name=it["name"], unit=it["unit"] or "",
            category=it["category"] or "", in_radar=bool(it["in_radar"]),
            measured=result.measured, value=value, raw_text=raw_text,
            score=result.score, stars=stars(result.score if result.measured else None),
            comment=comment,
        )
        data.lines.append(line)
        if result.measured and result.score is not None:
            total_scored += 1
            if result.score >= 4:
                good += 1
            elif result.score <= 2:
                poor += 1
        if line.in_radar:
            data.radar_labels.append(it["name"])
            data.radar_scores.append(result.score if (result.measured and result.score) else 0)

    template = repo.get_setting(conn, "summary_template", "") or ""
    try:
        data.summary = template.format(total=total_scored, good=good, poor=poor)
    except Exception:
        data.summary = template
    return data
