"""総合評価文言(★平均による4段階)のテスト."""

from __future__ import annotations

import pytest

from app.services.report import summary_rank


@pytest.mark.parametrize(
    "avg,expected",
    [
        (5.0, 1), (4.0, 1),          # 4以上 → 最良
        (3.99, 2), (3.0, 2),         # 3以上4未満
        (2.99, 3), (2.0, 3),         # 2以上3未満
        (1.99, 4), (1.0, 4),         # 2未満
    ],
)
def test_summary_rank_boundaries(avg, expected):
    assert summary_rank(avg) == expected


# (HbA1c値, TUG値) → 期待ランク。seed 基準: HbA1c 6.8→★5 / 8.5→★3 / 9.5→★2 / 10.5→★1、
# TUG 14→★3 / 25→★2
@pytest.mark.parametrize(
    "hba1c,tug,rank",
    [
        (6.8, 14, 1),    # (5+3)/2 = 4.0
        (8.5, 14, 2),    # (3+3)/2 = 3.0
        (9.5, 25, 3),    # (2+2)/2 = 2.0
        (10.5, 25, 4),   # (1+2)/2 = 1.5
    ],
)
def test_summary_text_selected_by_average(client, hba1c, tug, rank):
    from app import db, repo
    from app.services.report import build_report

    with db.get_conn() as c:
        pid = repo.create_patient(
            conn=c, code=f"S{rank}", name="集計 花子", sex="F", birth_date="1948-01-01"
        )
        sid = repo.create_session(c, None, "2026-07-01", "test")
        for item_name, value in [("HbA1c", hba1c), ("TUG", tug)]:
            item = repo.get_item_by_name(c, item_name)
            repo.upsert_measurement(c, sid, pid, item["id"], value, str(value))
        data = build_report(c, pid, sid)
        expected = repo.get_setting(c, f"summary_rank_{rank}")

    assert expected  # seed 済みであること
    assert data.summary == expected


def test_summary_empty_when_no_scored_items(client):
    """測定はあるが基準がなく score が付かない項目(身長)のみ → 総合評価は空."""
    from app import db, repo
    from app.services.report import build_report

    with db.get_conn() as c:
        pid = repo.create_patient(
            conn=c, code="S9", name="身長のみ", sex="M", birth_date="1950-01-01"
        )
        sid = repo.create_session(c, None, "2026-07-01", "test")
        item = repo.get_item_by_name(c, "身長")
        repo.upsert_measurement(c, sid, pid, item["id"], 165.0, "165")
        data = build_report(c, pid, sid)

    assert data.summary == ""


def test_summary_override_wins_over_rank_text(client):
    """報告書画面の手修正(override)はランク文言より優先される(回帰)."""
    from app import db, repo

    with db.get_conn() as c:
        pid = repo.create_patient(
            conn=c, code="S8", name="上書き 花子", sex="F", birth_date="1948-01-01"
        )
        sid = repo.create_session(c, None, "2026-07-01", "test")
        item = repo.get_item_by_name(c, "HbA1c")
        repo.upsert_measurement(c, sid, pid, item["id"], 6.8, "6.8")

    r = client.post(
        "/report/summary",
        data={"session_id": str(sid), "patient_id": str(pid), "summary": "手修正した総合評価です"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    page = client.get(f"/report?session_id={sid}&patient_id={pid}")
    assert "手修正した総合評価です" in page.text


def test_summary_empty_when_nothing_measured(client):
    from app import db, repo
    from app.services.report import build_report

    with db.get_conn() as c:
        pid = repo.create_patient(
            conn=c, code="S0", name="未測定 太郎", sex="M", birth_date="1950-01-01"
        )
        sid = repo.create_session(c, None, "2026-07-01", "test")
        data = build_report(c, pid, sid)

    assert data.summary == ""
