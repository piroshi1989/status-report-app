"""services/report.py: 体重増減率(前回セッション比較)の単体テスト."""

from __future__ import annotations

from app import db, repo
from app.services.report import build_report


def _weight_item_id(conn):
    return repo.get_item_by_name(conn, "体重")["id"]


def _weight_change_line(data):
    return next(ln for ln in data.lines if ln.name == "体重増減率")


def test_weight_change_shows_decrease_ratio(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid = repo.create_patient(conn, code="P1", name="テスト太郎", sex="M", birth_date="1950-01-01")
        wid = _weight_item_id(conn)
        s1 = repo.create_session(conn, 1, "2026-01-01", "f1.xlsx")
        s2 = repo.create_session(conn, 2, "2026-02-01", "f2.xlsx")
        repo.upsert_measurement(conn, s1, pid, wid, 50.0, "50")
        repo.upsert_measurement(conn, s2, pid, wid, 45.0, "45")

        data = build_report(conn, pid, s2)
        line = _weight_change_line(data)
        assert line.measured
        assert line.value == 90.0
        assert line.raw_text == "90%(10%減少)"


def test_weight_change_shows_increase_ratio(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid = repo.create_patient(conn, code="P1", name="テスト太郎", sex="M", birth_date="1950-01-01")
        wid = _weight_item_id(conn)
        s1 = repo.create_session(conn, 1, "2026-01-01", "f1.xlsx")
        s2 = repo.create_session(conn, 2, "2026-02-01", "f2.xlsx")
        repo.upsert_measurement(conn, s1, pid, wid, 50.0, "50")
        repo.upsert_measurement(conn, s2, pid, wid, 53.5, "53.5")

        data = build_report(conn, pid, s2)
        line = _weight_change_line(data)
        assert line.measured
        assert line.value == 107.0
        assert line.raw_text == "107%(7%増加)"


def test_weight_change_is_dash_on_first_session(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid = repo.create_patient(conn, code="P1", name="テスト太郎", sex="M", birth_date="1950-01-01")
        wid = _weight_item_id(conn)
        s1 = repo.create_session(conn, 1, "2026-01-01", "f1.xlsx")
        repo.upsert_measurement(conn, s1, pid, wid, 50.0, "50")

        data = build_report(conn, pid, s1)
        line = _weight_change_line(data)
        assert line.value is None
        assert line.raw_text == "―"


def test_weight_change_is_dash_when_current_weight_missing(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid = repo.create_patient(conn, code="P1", name="テスト太郎", sex="M", birth_date="1950-01-01")
        wid = _weight_item_id(conn)
        s1 = repo.create_session(conn, 1, "2026-01-01", "f1.xlsx")
        s2 = repo.create_session(conn, 2, "2026-02-01", "f2.xlsx")
        repo.upsert_measurement(conn, s1, pid, wid, 50.0, "50")
        repo.upsert_measurement(conn, s2, pid, wid, None, "")

        data = build_report(conn, pid, s2)
        line = _weight_change_line(data)
        assert line.value is None
        assert line.raw_text == "―"
