"""総合評価文言(★4 以上の項目数による4段階)と未計測時の評価のテスト."""

from __future__ import annotations

import pytest

from app.services.report import summary_rank


@pytest.mark.parametrize(
    "good,expected",
    [
        (18, 1), (14, 1),        # 14 以上 → 75〜100%(最良)
        (13, 2), (8, 2),         # 8〜13 → 50〜74%
        (7, 3), (5, 3),          # 5〜7 → 25〜49%
        (4, 4), (0, 4),          # 4 以下 → 0〜24%
    ],
)
def test_summary_rank_boundaries(good, expected):
    """評価基準 Excel 最終版(計測結果入力シート)と同じ区切り."""
    assert summary_rank(good) == expected


def _report_with(c, code, values: dict):
    from app import repo
    from app.services.report import build_report

    pid = repo.create_patient(conn=c, code=code, name="集計 花子", sex="F", birth_date="1948-01-01")
    sid = repo.create_session(c, None, "2026-07-01", "test")
    for item_name, value in values.items():
        item = repo.get_item_by_name(c, item_name)
        repo.upsert_measurement(c, sid, pid, item["id"], value, str(value))
    return build_report(c, pid, sid)


# seed 基準での★: TUG 9→★5 / 25→★2、FRT 30→★5、握力(女) 20→★5、喫食率 10→★5、
# mini-Cog 4→★5、Barthel 100→★5、FIM 126→★5、骨密度 95→★5。HbA1c は未計測でも★5
GOOD = {"TUG": 9, "FRT": 30, "握力": 20, "喫食率": 10, "mini-Cog": 4, "Barthel Index": 100,
        "FIM": 126, "骨密度(腰椎)": 95, "骨密度(大腿骨)": 95}


@pytest.mark.parametrize(
    "n_good,rank",
    [
        (9, 2),    # ★4以上: 9 項目 + 未計測 HbA1c(★5) = 10 → 50〜74%
        (6, 3),    # 6 + 1 = 7 → 25〜49%
        (3, 4),    # 3 + 1 = 4 → 0〜24%
    ],
)
def test_summary_text_selected_by_good_count(client, n_good, rank):
    from app import db, repo

    with db.get_conn() as c:
        values = dict(list(GOOD.items())[:n_good])
        data = _report_with(c, f"S{rank}", values)
        expected = repo.get_setting(c, f"summary_rank_{rank}")
    assert expected
    assert data.summary == expected


def test_unmeasured_hba1c_is_five_and_blood_pressure_is_one(client):
    from app import db

    with db.get_conn() as c:
        data = _report_with(c, "U1", {"TUG": 9})
    lines = {ln.name: ln for ln in data.lines}
    assert (lines["HbA1c"].score, lines["HbA1c"].stars, lines["HbA1c"].measured) == (5, "★★★★★", False)
    assert lines["HbA1c"].comment == "良好"            # 同じ評価(★5)の基準行のコメント
    assert (lines["収縮期血圧"].score, lines["収縮期血圧"].comment) == (1, "医師にご相談下さい。")
    assert lines["FRT"].score is None and lines["FRT"].comment == "未測定"
    radar = dict(zip(data.radar_labels, data.radar_scores))
    assert radar["HbA1c"] == 5 and radar["収縮期血圧"] == 1


def test_summary_empty_when_no_scored_items(client):
    """帳票に出ない項目(身長)だけ測定 → 未計測時の評価(HbA1c 等)だけでは総合評価を出さない."""
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
