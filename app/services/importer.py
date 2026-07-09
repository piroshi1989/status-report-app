"""測定結果一覧(.xls/.xlsx)の取込.

1 行 = 1 利用者。列名を評価項目(source_column / エイリアス / 項目名)に対応付け、
空セルは「未測定」(value=None)として扱う。BMI 等の派生項目は身長・体重から算出する。
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from .. import repo

# 利用者コード列の候補ヘッダ
CODE_HEADERS = ["利用者コード", "利用者id", "利用者番号", "コード", "id", "利用者"]
NAME_HEADERS = ["氏名", "名前", "利用者名", "name"]
PACEMAKER_HEADERS = ["ペースメーカー", "ペースメーカ", "pacemaker", "pm"]


def _norm(s) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", "", str(s)).strip().lower()


@dataclass
class ParsedRow:
    code: str
    name: Optional[str]
    pacemaker: Optional[int]
    values: dict[int, tuple[Optional[float], str]]  # item_id -> (value, raw_text)
    registered: bool = False
    patient_id: Optional[int] = None

    @property
    def measured_count(self) -> int:
        return sum(1 for v, _ in self.values.values() if v is not None)


@dataclass
class ImportPreview:
    columns_matched: list[tuple[str, Optional[str]]] = field(default_factory=list)  # (col, item_name|None)
    rows: list[ParsedRow] = field(default_factory=list)
    unregistered_codes: list[str] = field(default_factory=list)

    @property
    def matched_count(self) -> int:
        return sum(1 for _, n in self.columns_matched if n)

    @property
    def unmatched_columns(self) -> list[str]:
        return [c for c, n in self.columns_matched if not n]


def read_workbook(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() == ".xls":
        df = pd.read_excel(p, engine="xlrd", header=0, dtype=object)
    else:
        df = pd.read_excel(p, engine="openpyxl", header=0, dtype=object)
    # 完全に空の列/行を捨てる
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    return df


def _to_number(v) -> tuple[Optional[float], str]:
    """セル値 → (数値 or None, 元文字列)。数値化できない/空は None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None, ""
    raw = str(v).strip()
    if raw == "" or raw.lower() in ("nan", "none", "-", "―", "未測定", "未実施"):
        return None, raw
    # "120/80" のような血圧は上(収縮期)を採用
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*[0-9]", raw)
    if m:
        return float(m.group(1)), raw
    m = re.match(r"^[^0-9\-]*(-?[0-9]+(?:\.[0-9]+)?)", raw)
    if m:
        try:
            return float(m.group(1)), raw
        except ValueError:
            return None, raw
    return None, raw


def _build_column_index(conn: sqlite3.Connection):
    """正規化した列名 -> item_id。source_column / 項目名 / エイリアスを統合."""
    idx: dict[str, int] = {}
    items = repo.list_items(conn, include_inactive=True)
    id_by_name = {}
    for it in items:
        id_by_name[it["name"]] = it["id"]
        if it["source_column"]:
            idx[_norm(it["source_column"])] = it["id"]
        idx.setdefault(_norm(it["name"]), it["id"])
    for alias, item_id in repo.alias_map(conn).items():
        idx[_norm(alias)] = item_id
    return idx, id_by_name


def _extract(conn: sqlite3.Connection, path: str | Path) -> ImportPreview:
    df = read_workbook(path)
    col_index, id_by_name = _build_column_index(conn)
    item_by_id = {it["id"]: it for it in repo.list_items(conn, include_inactive=True)}

    headers = list(df.columns)
    norm_headers = [_norm(h) for h in headers]

    def find_col(candidates) -> Optional[str]:
        for cand in candidates:
            for h, nh in zip(headers, norm_headers):
                if nh == cand or cand in nh:
                    return h
        return None

    code_col = find_col(CODE_HEADERS) or headers[0]
    name_col = find_col(NAME_HEADERS)
    pm_col = find_col(PACEMAKER_HEADERS)

    # 列 → item_id マッピング
    col_to_item: dict[str, int] = {}
    columns_matched: list[tuple[str, Optional[str]]] = []
    for h, nh in zip(headers, norm_headers):
        if h in (code_col, name_col, pm_col):
            continue
        item_id = col_index.get(nh)
        col_to_item[h] = item_id
        columns_matched.append((str(h), item_by_id[item_id]["name"] if item_id else None))

    preview = ImportPreview(columns_matched=columns_matched)

    for _, r in df.iterrows():
        code_raw = r.get(code_col)
        if code_raw is None or (isinstance(code_raw, float) and pd.isna(code_raw)):
            continue
        code = str(code_raw).strip()
        if code == "" or code.lower() == "nan":
            continue
        # 数値コードの ".0" を除去
        if re.match(r"^\d+\.0$", code):
            code = code[:-2]

        pacemaker = None
        if pm_col is not None:
            pv, _ = _to_number(r.get(pm_col))
            if pv is not None:
                pacemaker = 1 if pv >= 1 else 0
            else:
                pacemaker = 1 if _norm(r.get(pm_col)) in ("有", "あり", "yes", "○") else None

        values: dict[int, tuple[Optional[float], str]] = {}
        for h, item_id in col_to_item.items():
            if item_id is None:
                continue
            num, raw = _to_number(r.get(h))
            values[item_id] = (num, raw)

        _apply_derived(conn, item_by_id, col_to_item, r, values)

        pr = ParsedRow(
            code=code,
            name=(str(r.get(name_col)).strip() if name_col and r.get(name_col) is not None else None),
            pacemaker=pacemaker,
            values=values,
        )
        patient = repo.get_patient_by_code(conn, code)
        if patient:
            pr.registered = True
            pr.patient_id = patient["id"]
        else:
            preview.unregistered_codes.append(code)
        preview.rows.append(pr)

    return preview


def _apply_derived(conn, item_by_id, col_to_item, row, values) -> None:
    """派生項目(BMI 等)を算出して values に格納。既に取込済みならスキップ."""
    # 逆引き: source_column 名 -> value
    def value_of(item_name: str) -> Optional[float]:
        for iid, it in item_by_id.items():
            if it["name"] == item_name:
                v = values.get(iid)
                return v[0] if v else None
        return None

    for iid, it in item_by_id.items():
        formula = it["derived_formula"]
        if not formula:
            continue
        # 直接列があり既に値が入っているならそれを尊重
        if values.get(iid) and values[iid][0] is not None:
            continue
        if formula == "bmi":
            h = value_of("身長")
            w = value_of("体重")
            if h and w and h > 0:
                bmi = w / ((h / 100.0) ** 2)
                values[iid] = (round(bmi, 1), f"派生:BMI={round(bmi,1)}")


def analyze(conn: sqlite3.Connection, path: str | Path) -> ImportPreview:
    return _extract(conn, path)


def commit(
    conn: sqlite3.Connection,
    path: str | Path,
    session_no: Optional[int],
    measured_on: Optional[str],
    source_file: str,
    auto_register: bool = False,
) -> dict:
    """取込を確定。auto_register=True なら未登録コードを仮登録する."""
    preview = _extract(conn, path)
    session_id = repo.create_session(conn, session_no, measured_on, source_file)
    n_measure = 0
    n_new_patient = 0
    for pr in preview.rows:
        if pr.patient_id is None:
            if not auto_register:
                continue
            pid = repo.create_patient(
                conn, code=pr.code, name=(pr.name or pr.code),
                pacemaker=(pr.pacemaker or 0),
            )
            pr.patient_id = pid
            n_new_patient += 1
        elif pr.pacemaker is not None:
            # 取込データに PM 情報があれば患者側を更新しない(登録情報を尊重)
            pass
        for item_id, (value, raw) in pr.values.items():
            repo.upsert_measurement(conn, session_id, pr.patient_id, item_id, value, raw)
            n_measure += 1
    return {
        "session_id": session_id,
        "measurements": n_measure,
        "new_patients": n_new_patient,
        "skipped_unregistered": len(preview.unregistered_codes) if not auto_register else 0,
    }
