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
    prev_text: str = "―"


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


def summary_rank(avg_score: float) -> int:
    """★スコア平均 → 総合評価文言のランク(1=最良〜4)。設定キー summary_rank_N に対応."""
    if avg_score >= 4:
        return 1
    if avg_score >= 3:
        return 2
    if avg_score >= 2:
        return 3
    return 4


WEIGHT_CHANGE_FORMULA = "weight_change_ratio"

# 未測定・比較対象なしを表す表示文字列(「未測定」とは区別する)
DASH = "―"


def measurement_text(m: Optional[sqlite3.Row]) -> str:
    """測定行 → 実測値の表示文字列。行なし/欠測は DASH."""
    if m is None:
        return DASH
    raw = (m["raw_text"] or "").strip()
    if raw and not raw.startswith("派生:"):
        return raw
    v = m["value"]
    if v is None:
        return DASH
    return str(int(v)) if float(v).is_integer() else str(v)


def _weight_change_value(
    weight_item_id: int,
    measurements: dict[int, sqlite3.Row],
    prev_measurements: dict[int, sqlite3.Row],
) -> tuple[Optional[float], str]:
    """前回セッションと比較した体重比率(%)と表示文字列を返す。比較不可なら (None, DASH)."""
    from ..domain import weight_change_display, weight_change_ratio

    curr_m = measurements.get(weight_item_id)
    prev_m = prev_measurements.get(weight_item_id)
    ratio = weight_change_ratio(
        prev_m["value"] if prev_m else None,
        curr_m["value"] if curr_m else None,
    )
    return ratio, weight_change_display(ratio)


def build_report(conn: sqlite3.Connection, patient_id: int, session_id: int) -> ReportData:
    from ..domain import calc_age

    patient = repo.get_patient(conn, patient_id)
    session = repo.get_session(conn, session_id)
    measured_on = session["measured_on"] if session else None
    age = calc_age(patient["birth_date"], measured_on)
    age_band = band_for(patient["birth_date"], measured_on)

    measurements = repo.get_measurements(conn, session_id, patient_id)
    prev_session = repo.previous_session_for_patient(conn, patient_id, session_id)
    prev_measurements = (
        repo.get_measurements(conn, prev_session["id"], patient_id) if prev_session else {}
    )
    items = repo.list_items(conn)
    weight_item = repo.get_item_by_name(conn, "体重")

    data = ReportData(patient=patient, session=session, age=age, age_band=age_band)
    data.disclaimer = repo.get_setting(conn, "disclaimer", "") or ""

    score_sum = total_scored = 0
    for it in items:
        is_weight_change = it["derived_formula"] == WEIGHT_CHANGE_FORMULA
        if is_weight_change and weight_item:
            value, raw_text = _weight_change_value(
                weight_item["id"], measurements, prev_measurements
            )
        else:
            m = measurements.get(it["id"])
            value = m["value"] if m else None
            raw_text = (m["raw_text"] if m else "") or ""
        rows = repo.criterion_rows_for_item(conn, it["id"])
        result = evaluate(
            rows, value,
            sex=patient["sex"], age_band=age_band,
            pacemaker=patient["pacemaker"],
        )
        # 体重増減率は比較不可でも「未測定」ではなく raw_text("―")で表す
        measured = result.measured or (is_weight_change and bool(raw_text))
        comment = result.comment or ""
        if not result.measured:
            comment = "" if is_weight_change else "未測定"
        line = ReportLine(
            item_id=it["id"], name=it["name"], unit=it["unit"] or "",
            category=it["category"] or "", in_radar=bool(it["in_radar"]),
            measured=measured, value=value, raw_text=raw_text,
            score=result.score, stars=stars(result.score if measured else None),
            comment=comment,
            # 体重増減率はそれ自体が前回比なので前回値欄は出さない
            prev_text=DASH if is_weight_change else measurement_text(prev_measurements.get(it["id"])),
        )
        data.lines.append(line)
        if result.measured and result.score is not None:
            total_scored += 1
            score_sum += result.score
        if line.in_radar:
            data.radar_labels.append(it["name"])
            data.radar_scores.append(result.score if (result.measured and result.score) else 0)

    if total_scored:
        rank = summary_rank(score_sum / total_scored)
        data.summary = repo.get_setting(conn, f"summary_rank_{rank}", "") or ""
    return data
