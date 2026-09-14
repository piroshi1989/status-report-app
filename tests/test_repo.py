"""repo.py の単体テスト(セッション履歴まわり)."""

from __future__ import annotations

from app import db, repo


def _make_patient_with_sessions(conn):
    item_id = repo.create_item(
        conn, name="体重", unit="kg", category="身体計測", sort_order=1,
        direction="range", in_radar=0, source_column="体重",
    )
    pid = repo.create_patient(conn, code="P1", name="テスト太郎")
    s1 = repo.create_session(conn, 1, "2026-01-01", "f1.xlsx")
    s2 = repo.create_session(conn, 2, "2026-02-01", "f2.xlsx")
    repo.upsert_measurement(conn, s1, pid, item_id, 50.0, "50")
    repo.upsert_measurement(conn, s2, pid, item_id, 45.0, "45")
    return pid, s1, s2


def test_previous_session_for_patient_returns_prior_session(tmp_env):
    db.init_db(seed=False)
    with db.get_conn() as conn:
        pid, s1, s2 = _make_patient_with_sessions(conn)
        prev = repo.previous_session_for_patient(conn, pid, s2)
        assert prev["id"] == s1


def test_previous_session_for_patient_none_for_first_session(tmp_env):
    db.init_db(seed=False)
    with db.get_conn() as conn:
        pid, s1, s2 = _make_patient_with_sessions(conn)
        assert repo.previous_session_for_patient(conn, pid, s1) is None
