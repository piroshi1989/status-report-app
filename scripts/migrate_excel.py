#!/usr/bin/env python3
"""評価基準 Excel(「評価項目 改訂案」形式) → eval_items / eval_criteria 移行(CLI).

解析・正規化・置換は画面の「評価基準を Excel から取込」と同じ
``app.services.criteria_importer`` を使う。開発環境で DB を直接更新したいときに使う。

使い方:
    python scripts/migrate_excel.py path/to/評価項目_改訂案.xlsx --dry-run   # 解析結果を表示
    python scripts/migrate_excel.py path/to/評価項目_改訂案.xlsx             # 取込(DB をバックアップ後に置換)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# リポジトリルートを import パスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3  # noqa: E402

from app import config, db, seed  # noqa: E402
from app.services import criteria_importer  # noqa: E402
from app.services.criteria_importer import normalize  # noqa: E402,F401  (互換のため再公開)


def _readonly_conn() -> sqlite3.Connection:
    """--dry-run 用。既存 DB は読み取り専用で開き、無ければメモリ上に既定シードを作る."""
    path = config.db_path()
    if path.exists():
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db._schema_sql())
    seed.apply_seed(conn)
    return conn


def migrate(xlsx: Path, dry_run: bool = False) -> None:
    if dry_run:
        conn = _readonly_conn()
        try:
            _report(criteria_importer.analyze(conn, xlsx))
        finally:
            conn.close()
        return
    db.init_db(seed=True)
    with db.get_conn() as conn:
        preview = criteria_importer.analyze(conn, xlsx)
        _report(preview)
        backup = criteria_importer.backup_db(conn)
        stats = criteria_importer.apply(conn, preview)
        print(f"移行完了: 更新 {stats['updated']} 項目 / 新規 {stats['created']} 項目 / 基準 {stats['rows']} 行")
        print(f"取込前のバックアップ: {backup}")


def _report(preview) -> None:
    if preview.skipped_sheets:
        print("読み飛ばしたシート:", " / ".join(preview.skipped_sheets))
    for w in preview.warnings:
        print("  [確認]", w)
    if preview.unknown:
        print("未対応の項目(取り込まない):", " / ".join(preview.unknown))
    for p in preview.plans:
        mark = "(新規・無効で追加)" if p.is_new else ""
        print(f"■ {p.excel_name} → {p.item_name}{mark}: 基準 {p.current_rows} → {p.row_count} 行")
        for cs in p.cond_sets:
            print(f"    {cs.label}: {len(cs.rows)} 段階")


def main():
    ap = argparse.ArgumentParser(description="評価基準Excel → DB 移行")
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="DBに書かず解析結果を表示")
    args = ap.parse_args()

    if not args.xlsx.exists():
        ap.error(f"ファイルが見つかりません: {args.xlsx}")
    migrate(args.xlsx, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
