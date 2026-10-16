"""状況報告書のデータ組み立て(表・レーダー・総合評価)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from .. import repo
from ..seed import layout_item_ids
from ..domain import band_for, measured_display, stars
from .evaluation import EvalResult, evaluate, resolve_group


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
    # 前回セッションのスコア(radar_labels と同じ並び)。比較対象がなければ空。
    radar_prev_scores: list[int] = field(default_factory=list)
    summary: str = ""
    disclaimer: str = ""

    @property
    def radar_items(self) -> list[ReportLine]:
        return [ln for ln in self.lines if ln.in_radar]


# 総合評価: ★4 以上の項目数 → 文言ランク(評価基準 Excel 最終版の計測結果入力シートと同じ区切り。
# 帳票 18 項目中 14 以上=75〜100% / 8〜13=50〜74% / 5〜7=25〜49% / 4 以下=0〜24%)
SUMMARY_GOOD_SCORE = 4
SUMMARY_RANK_MIN_GOOD = [(14, 1), (8, 2), (5, 3)]


def summary_rank(good_count: int) -> int:
    """★4 以上の項目数 → 総合評価文言のランク(1=最良〜4)。設定キー summary_rank_N に対応."""
    for min_good, rank in SUMMARY_RANK_MIN_GOOD:
        if good_count >= min_good:
            return rank
    return 4


WEIGHT_CHANGE_FORMULA = "weight_change_ratio"

# 未測定・比較対象なしを表す表示文字列(「未測定」とは区別する)
DASH = "―"


def measurement_text(m: Optional[sqlite3.Row]) -> str:
    """測定行 → 実測値の表示文字列。行なし/欠測は DASH."""
    if m is None:
        return DASH
    return measured_display(m["raw_text"], m["value"]) or DASH


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


def _weight_loss_value(
    weight_item_id: int,
    measurements: dict[int, sqlite3.Row],
    prev_measurements: dict[int, sqlite3.Row],
) -> Optional[float]:
    """前回セッションからの体重減少率(%)。比較不可なら None."""
    from ..domain import weight_loss_rate

    curr_m = measurements.get(weight_item_id)
    prev_m = prev_measurements.get(weight_item_id)
    return weight_loss_rate(
        prev_m["value"] if prev_m else None,
        curr_m["value"] if curr_m else None,
    )


def _radar_score(score: Optional[int]) -> int:
    """評価 → レーダーの半径。評価なしは 0(中心)."""
    return score or 0


def items_for_patient(conn: sqlite3.Connection, patient: sqlite3.Row, age_band) -> list[sqlite3.Row]:
    """帳票に出す項目。SMI(pm_display=without_pm)と下腿周囲長(with_pm)を差し替える.

    ペースメーカー有の利用者は体組成計が使えないため下腿周囲長を出す。ただし下腿周囲長に
    その利用者の年代・性別の基準が無い場合(評価基準 Excel は 50代以下に PM 有シートが無い)は
    評価できないので SMI に戻す。基準が 1 行も無い(取込前)ときは下腿周囲長を出す。
    """
    items = repo.list_items(conn)

    def usable(it) -> bool:
        rows = repo.criterion_rows_for_item(conn, it["id"])
        return not rows or bool(resolve_group(rows, patient["sex"], age_band, patient["pacemaker"])[1])

    use_alt = bool(patient["pacemaker"]) and any(
        usable(it) for it in items if it["pm_display"] == "with_pm"
    )
    hidden = "without_pm" if use_alt else "with_pm"
    return [it for it in items if it["pm_display"] != hidden]


def _score(item: sqlite3.Row, rows: list, value: Optional[float], sex, age_band, pacemaker
           ) -> tuple[EvalResult, Optional[int], str]:
    """評価結果と、帳票に出す評価・コメント。

    未計測でも ``unmeasured_score`` がある項目(HbA1c=★5・血圧=★1)はその評価を付け、
    コメントは ``unmeasured_comment``、無ければ同じ評価の基準行のコメントを使う。
    """
    result = evaluate(rows, value, sex=sex, age_band=age_band, pacemaker=pacemaker)
    if result.measured or item["unmeasured_score"] is None:
        return result, result.score, result.comment or ""
    score = int(item["unmeasured_score"])
    comment = item["unmeasured_comment"]
    if comment is None:
        _key, group = resolve_group(rows, sex, age_band, pacemaker)
        comment = next((r.comment for r in group if r.score == score and r.comment), "")
    return result, score, comment


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
    # 前回スコアは前回の測定日時点の年代で評価する。誕生日で年代が繰り上がった利用者でも
    # 前回の報告書に印字された★と一致する。
    prev_age_band = (
        band_for(patient["birth_date"], prev_session["measured_on"]) if prev_session else None
    )
    items = items_for_patient(conn, patient, age_band)
    # 総合評価は Excel と同じく帳票の既定 18 行だけで数える(施設独自項目は数えない)
    counted_ids = layout_item_ids(conn)
    weight_item = repo.get_item_by_name(conn, "体重")
    # 前回の体重増減率(レーダーの前回スコア用)は前々回と比べる
    prev_prev_session = (
        repo.previous_session_for_patient(conn, patient_id, prev_session["id"]) if prev_session else None
    )
    prev_prev_measurements = (
        repo.get_measurements(conn, prev_prev_session["id"], patient_id) if prev_prev_session else {}
    )

    data = ReportData(patient=patient, session=session, age=age, age_band=age_band)
    data.disclaimer = repo.get_setting(conn, "disclaimer", "") or ""

    good_count = 0
    any_measured = False   # 未計測時の評価(HbA1c 等)だけでは総合評価を出さない
    for it in items:
        is_weight_change = it["derived_formula"] == WEIGHT_CHANGE_FORMULA
        if is_weight_change and weight_item:
            value, raw_text = _weight_change_value(
                weight_item["id"], measurements, prev_measurements
            )
            # 表示は前回比(%)だが、評価基準は Excel と同じ体重減少率で判定する
            eval_value = _weight_loss_value(weight_item["id"], measurements, prev_measurements)
            prev_eval_value = _weight_loss_value(weight_item["id"], prev_measurements, prev_prev_measurements)
        else:
            m = measurements.get(it["id"])
            value = m["value"] if m else None
            raw_text = (m["raw_text"] if m else "") or ""
            eval_value = value
            prev_m = prev_measurements.get(it["id"])
            prev_eval_value = prev_m["value"] if prev_m else None
        rows = repo.criterion_rows_for_item(conn, it["id"])
        result, score, comment = _score(
            it, rows, eval_value, patient["sex"], age_band, patient["pacemaker"],
        )
        # 体重増減率は比較不可でも「未測定」ではなく raw_text("―")で表す
        measured = result.measured or (is_weight_change and bool(raw_text))
        if not result.measured and score is None:
            comment = "" if is_weight_change else "未測定"
        line = ReportLine(
            item_id=it["id"], name=it["name"], unit=it["unit"] or "",
            category=it["category"] or "", in_radar=bool(it["in_radar"]),
            measured=measured, value=value, raw_text=raw_text,
            score=score, stars=stars(score),
            comment=comment,
            # 体重増減率はそれ自体が前回比なので前回値欄は出さない
            prev_text=DASH if is_weight_change else measurement_text(prev_measurements.get(it["id"])),
        )
        data.lines.append(line)
        if score is not None and it["id"] in counted_ids:
            good_count += score >= SUMMARY_GOOD_SCORE
            any_measured = any_measured or result.measured
        if line.in_radar:
            data.radar_labels.append(it["name"])
            data.radar_scores.append(_radar_score(score))
            if prev_session:
                _r, prev_score, _c = _score(
                    it, rows, prev_eval_value, patient["sex"], prev_age_band, patient["pacemaker"],
                )
                data.radar_prev_scores.append(_radar_score(prev_score))

    if any_measured:
        rank = summary_rank(good_count)
        data.summary = repo.get_setting(conn, f"summary_rank_{rank}", "") or ""
    return data
