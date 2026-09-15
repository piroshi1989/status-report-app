"""services/report.py: 各項目の「前回値」表示の単体テスト."""

from __future__ import annotations

from app import db, repo
from app.services.radar import render_radar
from app.services.report import build_report

DASH = "―"


def _line(data, name):
    return next(ln for ln in data.lines if ln.name == name)


def _setup(conn):
    pid = repo.create_patient(conn, code="P1", name="テスト太郎", sex="M", birth_date="1950-01-01")
    s1 = repo.create_session(conn, 1, "2026-01-01", "f1.xlsx")
    s2 = repo.create_session(conn, 2, "2026-02-01", "f2.xlsx")
    return pid, s1, s2


def test_prev_text_shows_previous_session_value(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid, s1, s2 = _setup(conn)
        iid = repo.get_item_by_name(conn, "HbA1c")["id"]
        repo.upsert_measurement(conn, s1, pid, iid, 7.9, "")
        repo.upsert_measurement(conn, s2, pid, iid, 8.4, "")

        line = _line(build_report(conn, pid, s2), "HbA1c")
        assert line.prev_text == "7.9"


def test_prev_text_prefers_raw_text(tmp_env):
    """血圧のように raw_text を持つ項目は、前回値も raw_text で出す."""
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid, s1, s2 = _setup(conn)
        iid = repo.get_item_by_name(conn, "収縮期血圧")["id"]
        repo.upsert_measurement(conn, s1, pid, iid, 128.0, "128/80")
        repo.upsert_measurement(conn, s2, pid, iid, 145.0, "145/88")

        line = _line(build_report(conn, pid, s2), "収縮期血圧")
        assert line.prev_text == "128/80"


def test_prev_text_is_dash_on_first_session(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid, s1, _s2 = _setup(conn)
        iid = repo.get_item_by_name(conn, "HbA1c")["id"]
        repo.upsert_measurement(conn, s1, pid, iid, 7.9, "")

        line = _line(build_report(conn, pid, s1), "HbA1c")
        assert line.prev_text == DASH


def test_prev_text_is_dash_when_not_measured_last_time(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid, s1, s2 = _setup(conn)
        hba1c = repo.get_item_by_name(conn, "HbA1c")["id"]
        tug = repo.get_item_by_name(conn, "TUG")["id"]
        repo.upsert_measurement(conn, s1, pid, hba1c, 7.9, "")  # 前回は HbA1c だけ測定
        repo.upsert_measurement(conn, s2, pid, hba1c, 8.4, "")
        repo.upsert_measurement(conn, s2, pid, tug, 14.2, "")

        line = _line(build_report(conn, pid, s2), "TUG")
        assert line.prev_text == DASH


def test_weight_change_row_has_no_prev_text(tmp_env):
    """体重増減率はそれ自体が前回比なので、前回値欄は出さない."""
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid, s1, s2 = _setup(conn)
        wid = repo.get_item_by_name(conn, "体重")["id"]
        repo.upsert_measurement(conn, s1, pid, wid, 50.0, "")
        repo.upsert_measurement(conn, s2, pid, wid, 45.0, "")

        data = build_report(conn, pid, s2)
        assert _line(data, "体重").prev_text == "50"
        assert _line(data, "体重増減率").prev_text == DASH


# --- 表示(画面 / PDF) ---

def _pdf_table_rows(data):
    """PDF の詳細表を [[セル文字列, ...], ...] で取り出す."""
    from reportlab.platypus import Table

    from app.services.pdf import build_flowables

    tbl = next(f for f in build_flowables(data) if isinstance(f, Table))
    return [[c.getPlainText() for c in row] for row in tbl._cellvalues]


def test_pdf_table_has_prev_column(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid, s1, s2 = _setup(conn)
        iid = repo.get_item_by_name(conn, "HbA1c")["id"]
        repo.upsert_measurement(conn, s1, pid, iid, 7.9, "")
        repo.upsert_measurement(conn, s2, pid, iid, 8.4, "")

        rows = _pdf_table_rows(build_report(conn, pid, s2))

    header = rows[0]
    assert "前回" in header
    prev_col = header.index("前回")
    hba1c = next(r for r in rows if r[1] == "HbA1c")
    assert hba1c[prev_col] == "7.9"


def test_report_page_shows_prev_value(client, make_xlsx):
    client.post("/patients/new", data={"code": "PV1", "name": "前回値さん", "sex": "M",
                                       "birth_date": "1950-01-01", "pacemaker": "0"})

    def _upload(weight, session_no, measured_on):
        import re
        xlsx = make_xlsx([["PV1", 160, weight, 6.0, "120/70", 30, 8.0]])
        with open(xlsx, "rb") as f:
            r = client.post("/upload/analyze",
                            files={"file": ("m.xlsx", f, "application/octet-stream")},
                            data={"session_no": str(session_no), "measured_on": measured_on})
        token = re.search(r'name="token" value="([^"]+)"', r.text).group(1)
        r2 = client.post("/upload/commit",
                         data={"token": token, "orig_name": "m.xlsx",
                               "session_no": str(session_no), "measured_on": measured_on},
                         follow_redirects=False)
        return int(r2.headers["location"].split("session_id=")[1])

    _upload(58, 1, "2026-01-10")
    sid2 = _upload(55, 2, "2026-07-10")
    with db.get_conn() as c:
        pid = repo.get_patient_by_code(c, "PV1")["id"]

    rep = client.get(f"/report?session_id={sid2}&patient_id={pid}")
    assert rep.status_code == 200
    assert "<th>前回</th>" in rep.text
    assert "58" in rep.text  # 前回の体重


# --- レーダー(前回との二重表示) ---

def _radar(data, name):
    """(今回スコア, 前回スコア) を項目名で引く."""
    i = data.radar_labels.index(name)
    return data.radar_scores[i], data.radar_prev_scores[i]


def test_radar_prev_scores_come_from_the_previous_session(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid, s1, s2 = _setup(conn)
        iid = repo.get_item_by_name(conn, "HbA1c")["id"]
        repo.upsert_measurement(conn, s1, pid, iid, 7.9, "")  # → 4(おおむね良好)
        repo.upsert_measurement(conn, s2, pid, iid, 8.4, "")  # → 3(やや高値)

        assert _radar(build_report(conn, pid, s2), "HbA1c") == (3, 4)


def test_radar_prev_scores_are_empty_on_first_session(tmp_env):
    """比較対象がなければ前回系列は描かない(空リスト)."""
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid, s1, _s2 = _setup(conn)
        iid = repo.get_item_by_name(conn, "HbA1c")["id"]
        repo.upsert_measurement(conn, s1, pid, iid, 7.9, "")

        data = build_report(conn, pid, s1)
        assert data.radar_labels != []
        assert data.radar_prev_scores == []


def test_radar_prev_score_is_zero_when_not_measured_last_time(tmp_env):
    """前回未測定は今回の未測定と同じ扱いで 0(中心)."""
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid, s1, s2 = _setup(conn)
        hba1c = repo.get_item_by_name(conn, "HbA1c")["id"]
        tug = repo.get_item_by_name(conn, "TUG")["id"]
        repo.upsert_measurement(conn, s1, pid, hba1c, 7.9, "")  # 前回は HbA1c だけ測定
        repo.upsert_measurement(conn, s2, pid, tug, 14.2, "")

        assert _radar(build_report(conn, pid, s2), "TUG")[1] == 0


def test_radar_prev_scores_use_the_age_band_of_the_previous_session(tmp_env):
    """前回スコアは前回の測定日時点の年代で評価する(前回の報告書の★と一致させる).

    SMI は 80 代だけ基準が緩い(男性 6.5 → 6.2)。79 歳から 80 歳になった利用者は、
    同じ 6.4 kg/m2 でも前回 1・今回 3 になるのが正しい。
    """
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid = repo.create_patient(conn, code="P80", name="誕生日太郎", sex="M",
                                  birth_date="1946-06-01")
        s1 = repo.create_session(conn, 1, "2026-01-10", "f1.xlsx")  # 79歳 → 70代
        s2 = repo.create_session(conn, 2, "2026-07-10", "f2.xlsx")  # 80歳 → 80代
        iid = repo.get_item_by_name(conn, "SMI")["id"]
        repo.upsert_measurement(conn, s1, pid, iid, 6.4, "")
        repo.upsert_measurement(conn, s2, pid, iid, 6.4, "")

        assert _radar(build_report(conn, pid, s2), "SMI") == (3, 1)


def _pixels(png: bytes) -> bytes:
    import io

    from reportlab.lib.utils import ImageReader

    return ImageReader(io.BytesIO(png)).getRGBData()


def _pdf_radar_pixels(data) -> bytes:
    """PDF に埋め込まれるレーダー画像のピクセル."""
    from reportlab.platypus import Image

    from app.services.pdf import build_flowables

    img = next(f for f in build_flowables(data) if isinstance(f, Image))
    return img._img.getRGBData()


def test_pdf_radar_is_drawn_with_both_sessions(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid, s1, s2 = _setup(conn)
        iid = repo.get_item_by_name(conn, "HbA1c")["id"]
        repo.upsert_measurement(conn, s1, pid, iid, 7.9, "")
        repo.upsert_measurement(conn, s2, pid, iid, 8.4, "")
        data = build_report(conn, pid, s2)

    drawn = _pdf_radar_pixels(data)
    assert drawn == _pixels(render_radar(data.radar_labels, data.radar_scores,
                                         prev_scores=data.radar_prev_scores))
    assert drawn != _pixels(render_radar(data.radar_labels, data.radar_scores))


def test_report_page_radar_is_drawn_with_both_sessions(client):
    """画面プレビューのレーダーも PDF と同じ二重表示になること."""
    import base64
    import re

    with db.get_conn() as conn:
        pid, s1, s2 = _setup(conn)
        iid = repo.get_item_by_name(conn, "HbA1c")["id"]
        repo.upsert_measurement(conn, s1, pid, iid, 7.9, "")
        repo.upsert_measurement(conn, s2, pid, iid, 8.4, "")
        data = build_report(conn, pid, s2)

    rep = client.get(f"/report?session_id={s2}&patient_id={pid}")
    assert rep.status_code == 200
    served = base64.b64decode(re.search(r'data:image/png;base64,([^"]+)"', rep.text).group(1))
    assert served == render_radar(data.radar_labels, data.radar_scores,
                                  prev_scores=data.radar_prev_scores)
    assert served != render_radar(data.radar_labels, data.radar_scores)
