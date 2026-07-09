"""既存Excelとの回帰テスト(要件 Phase 2/12)。

実ファイルが tests/fixtures/ に置かれた場合のみ実行する:
  - tests/fixtures/criteria.xlsx  … 評価項目 改訂案.xlsx(9シート)
  - tests/fixtures/expected.csv   … 既存Excelで算出した期待評価値
                                     列: code, item, value, expected_score

期待CSVが用意できたら、このテストで「アプリの評価値が既存Excelと一致すること」を担保する。
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
CRITERIA_XLSX = FIXTURES / "criteria.xlsx"
EXPECTED_CSV = FIXTURES / "expected.csv"


pytestmark = pytest.mark.skipif(
    not (CRITERIA_XLSX.exists() and EXPECTED_CSV.exists()),
    reason="実Excel fixture (criteria.xlsx / expected.csv) が未配置のためスキップ",
)


def test_scores_match_existing_excel(tmp_env):
    """既存Excelの評価値とアプリの評価値が一致する。"""
    import subprocess
    import sys

    from app import db, repo
    from app.services.evaluation import evaluate
    from app.domain import band_for

    # 実基準を移行
    subprocess.run(
        [sys.executable, "scripts/migrate_excel.py", str(CRITERIA_XLSX)],
        check=True,
    )

    mismatches = []
    with db.get_conn() as conn:
        with open(EXPECTED_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                item = repo.get_item_by_name(conn, row["item"])
                assert item, f"項目 {row['item']} が見つからない"
                patient = repo.get_patient_by_code(conn, row["code"])
                sex = patient["sex"] if patient else None
                band = band_for(patient["birth_date"], None) if patient else None
                pm = patient["pacemaker"] if patient else None
                rows = repo.criterion_rows_for_item(conn, item["id"])
                res = evaluate(rows, float(row["value"]), sex=sex, age_band=band, pacemaker=pm)
                if res.score != int(row["expected_score"]):
                    mismatches.append((row["code"], row["item"], row["value"], res.score, row["expected_score"]))

    assert not mismatches, f"不一致 {len(mismatches)} 件: {mismatches[:10]}"
