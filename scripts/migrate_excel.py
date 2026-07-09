#!/usr/bin/env python3
"""既存の「評価項目 改訂案.xlsx」(9シート) → eval_items / eval_criteria 移行.

冗長な基準の展開解消(要件 F3)を行う:
  - 各シートは (年代, ペースメーカー有無) に対応。
  - 同一項目の閾値セットが全シートで同一なら (age_band=NULL, pacemaker=NULL) に集約。
  - ペースメーカー有無だけで同一なら pacemaker=NULL に集約。
  - 年代で異なるなら age_band を保持。
  - 男/女で分かれる項目(男BMI/女BMI 等)は項目名の接頭辞から sex 条件に変換。

実データのシート構成・列見出しは実ファイルに合わせて下の定数を調整すること。
本スクリプトは列見出しを候補リストで検出する防御的実装だが、想定と異なる場合は
--dump で生の内容を確認して SHEET_MAP / HEADER_* を修正する。

使い方:
    python scripts/migrate_excel.py path/to/評価項目_改訂案.xlsx
    python scripts/migrate_excel.py path/to/file.xlsx --dry-run
    python scripts/migrate_excel.py path/to/file.xlsx --dump   # シート内容を確認
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

# リポジトリルートを import パスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from app import db, repo  # noqa: E402

# シート名 -> (age_band, pacemaker)。実ファイルのシート名に合わせる。
SHEET_MAP: dict[str, tuple[str | None, int | None]] = {
    "50代以上": ("50", None),
    "60代": ("60", 0),
    "60代PM": ("60", 1),
    "70代": ("70", 0),
    "70代PM": ("70", 1),
    "80代": ("80", 0),
    "80代PM": ("80", 1),
    "90代": ("90", 0),
    "90代PM": ("90", 1),
}

HEADER_ITEM = ["項目", "項目名", "評価項目"]
HEADER_THRESHOLD = ["閾値", "区間", "下限", "基準値"]
HEADER_SCORE = ["相対評価", "評価", "点数", "score"]
HEADER_COMMENT = ["コメント", "評価コメント", "所見"]
HEADER_DESC = ["説明", "項目説明", "備考"]

SEX_PREFIX = {"男": "M", "女": "F"}


def _norm(s) -> str:
    return re.sub(r"\s+", "", str(s)).strip() if s is not None else ""


def _find_col(cols, candidates):
    for cand in candidates:
        for c in cols:
            if cand in _norm(c):
                return c
    return None


def _split_sex(item_name: str) -> tuple[str | None, str]:
    n = _norm(item_name)
    for pref, code in SEX_PREFIX.items():
        if n.startswith(pref):
            return code, n[len(pref):]
    return None, n


def parse_sheet(df: pd.DataFrame):
    """(item_name, sex) -> [(threshold, score, comment, description)] を返す."""
    cols = list(df.columns)
    c_item = _find_col(cols, HEADER_ITEM) or cols[0]
    c_thr = _find_col(cols, HEADER_THRESHOLD)
    c_score = _find_col(cols, HEADER_SCORE)
    c_comment = _find_col(cols, HEADER_COMMENT)
    c_desc = _find_col(cols, HEADER_DESC)

    result: dict[tuple[str, str | None], list[tuple]] = defaultdict(list)
    current_item = None
    for _, row in df.iterrows():
        raw_item = row.get(c_item)
        if raw_item is not None and _norm(raw_item):
            current_item = _norm(raw_item)
        if current_item is None:
            continue
        thr = row.get(c_thr) if c_thr else None
        score = row.get(c_score) if c_score else None
        if pd.isna(thr) if thr is not None else True:
            # 閾値が無い行はスキップ(見出し・空行)
            if score is None or (isinstance(score, float) and pd.isna(score)):
                continue
        try:
            thr_f = float(thr)
            score_i = int(float(score))
        except (TypeError, ValueError):
            continue
        comment = row.get(c_comment) if c_comment else None
        desc = row.get(c_desc) if c_desc else None
        sex, name = _split_sex(current_item)
        result[(name, sex)].append((
            thr_f, score_i,
            None if comment is None or (isinstance(comment, float) and pd.isna(comment)) else str(comment).strip(),
            None if desc is None or (isinstance(desc, float) and pd.isna(desc)) else str(desc).strip(),
        ))
    return result


def collect(xlsx: Path):
    """全シート走査 → {(item, sex): {(age_band, pm): rowset}}."""
    xl = pd.read_excel(xlsx, sheet_name=None, header=0, dtype=object)
    data: dict[tuple[str, str | None], dict[tuple, list]] = defaultdict(dict)
    for sheet_name, df in xl.items():
        key = _norm(sheet_name)
        cond = SHEET_MAP.get(key) or SHEET_MAP.get(sheet_name)
        if cond is None:
            print(f"  [skip] 未対応シート: {sheet_name}")
            continue
        age_band, pm = cond
        parsed = parse_sheet(df)
        for (name, sex), rows in parsed.items():
            data[(name, sex)][(age_band, pm)] = sorted(rows)
    return data


def normalize(cond_rows: dict[tuple, list]):
    """冗長展開の解消。→ [(sex, age_band, pacemaker, rows)] のリストで返す本体側は
    呼び出し元で sex を付与するのでここでは (age_band, pacemaker, rows) を返す."""
    # 全条件で同一?
    rowsets = list(cond_rows.values())
    conds = list(cond_rows.keys())
    if not rowsets:
        return []

    def all_same(sets):
        first = sets[0]
        return all(s == first for s in sets)

    if all_same(rowsets):
        return [(None, None, rowsets[0])]

    # 年代ごとにまとめ、各年代内で PM 差が無ければ pacemaker=NULL
    by_age: dict[str | None, dict[int | None, list]] = defaultdict(dict)
    for (age_band, pm), rows in cond_rows.items():
        by_age[age_band][pm] = rows

    out = []
    for age_band, pm_map in by_age.items():
        pm_rowsets = list(pm_map.values())
        if len(pm_rowsets) > 1 and all_same(pm_rowsets):
            out.append((age_band, None, pm_rowsets[0]))
        else:
            for pm, rows in pm_map.items():
                out.append((age_band, pm, rows))
    return out


def migrate(xlsx: Path, dry_run: bool = False):
    data = collect(xlsx)
    print(f"抽出項目数: {len(data)}")

    if dry_run:
        for (name, sex), cond_rows in sorted(data.items()):
            norm = normalize(cond_rows)
            print(f"■ {name}{'('+sex+')' if sex else ''}: {len(norm)} 条件セット")
            for age_band, pm, rows in norm:
                cond = f"age={age_band or '全'} pm={'全' if pm is None else pm}"
                print(f"    {cond}: {len(rows)} 段階")
        return

    db.init_db(seed=True)
    with db.get_conn() as conn:
        order = 100
        for (name, sex), cond_rows in sorted(data.items()):
            item = repo.get_item_by_name(conn, name)
            if item is None:
                order += 1
                item_id = repo.create_item(conn, name=name, sort_order=order)
            else:
                item_id = item["id"]
            # 既存基準を置換
            repo.delete_criteria_for_item(conn, item_id)
            for age_band, pm, rows in normalize(cond_rows):
                for thr, score, comment, desc in rows:
                    repo.add_criterion(conn, item_id, sex, age_band, pm, thr, score, comment, desc)
        print("移行完了。")


def dump(xlsx: Path):
    xl = pd.read_excel(xlsx, sheet_name=None, header=0, dtype=object)
    for name, df in xl.items():
        print(f"=== シート: {name} ({df.shape[0]}行 x {df.shape[1]}列) ===")
        print("列:", list(df.columns))
        print(df.head(8).to_string())
        print()


def main():
    ap = argparse.ArgumentParser(description="評価項目Excel → DB 移行")
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="DBに書かず解析結果を表示")
    ap.add_argument("--dump", action="store_true", help="シート内容を確認表示")
    args = ap.parse_args()

    if not args.xlsx.exists():
        ap.error(f"ファイルが見つかりません: {args.xlsx}")
    if args.dump:
        dump(args.xlsx)
    else:
        migrate(args.xlsx, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
