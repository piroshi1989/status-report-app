"""seed.py の単体テスト(既存 DB への項目バックフィル)."""

from __future__ import annotations

from app import db, repo, seed


def test_apply_seed_creates_weight_change_item_on_fresh_db(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        item = repo.get_item_by_name(conn, "体重増減率")
        assert item is not None
        assert item["derived_formula"] == "weight_change_ratio"


def test_apply_seed_backfills_weight_change_item_on_existing_db(tmp_env):
    # 「体重増減率」導入前に既にシード済みだった DB を模す
    db.init_db(seed=True)
    with db.get_conn() as conn:
        conn.execute("DELETE FROM eval_items WHERE name='体重増減率'")

    with db.get_conn() as conn:
        seed.apply_seed(conn)

    with db.get_conn() as conn:
        item = repo.get_item_by_name(conn, "体重増減率")
        assert item is not None
