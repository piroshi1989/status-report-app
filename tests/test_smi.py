"""SMI = 筋肉量(kg) ÷ 身長(m)² の派生と、旧データ(筋肉量 kg を SMI に格納)の移行."""

from __future__ import annotations

import re

import pytest

from app import db, repo, seed
from app.domain import measured_display, smi
from app.services.report import build_report


def test_smi_formula_matches_excel():
    # 評価基準 Excel の計測結果入力シートと同じ値(身長141cm・筋肉量11.2kg → 5.6335…)
    assert smi(11.2, 141) == pytest.approx(5.633519440671999)
    assert smi(None, 141) is None
    assert smi(11.2, None) is None
    assert smi(11.2, 0) is None


def test_measured_display_uses_rounded_derived_text():
    assert measured_display("派生:SMI=5.63", 5.633519) == "5.63"
    assert measured_display("派生:BMI=21.5", 21.5) == "21.5"
    assert measured_display("145/88", 145.0) == "145/88"
    assert measured_display("", 12.0) == "12"
    assert measured_display(None, None) is None


def test_upload_derives_smi_from_muscle_mass(client, make_xlsx):
    client.post("/patients/new", data={"code": "S1", "name": "筋肉さん", "sex": "F",
                                       "birth_date": "1940-01-01", "pacemaker": "0"})
    xlsx = make_xlsx([["S1", 141, 46, 15.0]], headers=["利用者コード", "身長", "体重", "筋肉量"])
    with open(xlsx, "rb") as f:
        r = client.post("/upload/analyze", files={"file": ("m.xlsx", f, "application/octet-stream")},
                        data={"session_no": "1", "measured_on": "2026-07-01"})
    token = re.search(r'name="token" value="([^"]+)"', r.text).group(1)
    r2 = client.post("/upload/commit", data={"token": token, "orig_name": "m.xlsx", "session_no": "1",
                                             "measured_on": "2026-07-01"}, follow_redirects=False)
    sid = int(r2.headers["location"].split("session_id=")[1])

    with db.get_conn() as conn:
        pid = repo.get_patient_by_code(conn, "S1")["id"]
        ms = repo.get_measurements(conn, sid, pid)
        muscle = repo.get_item_by_name(conn, "筋肉量")
        smi_item = repo.get_item_by_name(conn, "SMI")
        assert muscle["is_active"] == 0                    # 帳票には出さない
        assert ms[muscle["id"]]["value"] == 15.0
        assert ms[smi_item["id"]]["value"] == pytest.approx(15.0 / 1.41 ** 2)   # 丸めずに評価
        data = build_report(conn, pid, sid)
    line = next(ln for ln in data.lines if ln.name == "SMI")
    assert line.raw_text == "派生:SMI=7.54"
    assert "筋肉量" not in {ln.name for ln in data.lines}

    rep = client.get(f"/report?session_id={sid}&patient_id={pid}")
    assert "7.54" in rep.text


def _old_style_db():
    """初期版の DB を再現: SMI の取込列が「筋肉量」で、筋肉量 kg がそのまま SMI に入っている."""
    db.init_db(seed=True)
    with db.get_conn() as conn:
        conn.execute("DELETE FROM eval_items WHERE name='筋肉量'")
        conn.execute("UPDATE eval_items SET source_column='筋肉量', derived_formula=NULL WHERE name='SMI'")
        pid = repo.create_patient(conn, code="OLD", name="旧データ", sex="M", birth_date="1945-01-01")
        s1 = repo.create_session(conn, 1, "2026-01-01", "a.xlsx")
        s2 = repo.create_session(conn, 2, "2026-02-01", "b.xlsx")
        h = repo.get_item_by_name(conn, "身長")["id"]
        smi_id = repo.get_item_by_name(conn, "SMI")["id"]
        repo.upsert_measurement(conn, s1, pid, h, 160.0, "160")
        repo.upsert_measurement(conn, s1, pid, smi_id, 18.0, "18")     # 身長あり
        repo.upsert_measurement(conn, s2, pid, smi_id, 17.5, "17.5")   # 身長なし
    return pid, s1, s2, smi_id


def test_backfill_moves_muscle_mass_and_recomputes_smi(tmp_env):
    pid, s1, s2, smi_id = _old_style_db()
    with db.get_conn() as conn:
        seed.apply_seed(conn)
        muscle = repo.get_item_by_name(conn, "筋肉量")
        item = repo.get_item(conn, smi_id)
        assert (item["source_column"], item["derived_formula"]) == (None, "smi")
        assert muscle["is_active"] == 0

        m1 = repo.get_measurements(conn, s1, pid)
        assert m1[muscle["id"]]["value"] == 18.0 and m1[muscle["id"]]["raw_text"] == "18"
        assert m1[smi_id]["value"] == pytest.approx(18.0 / 1.6 ** 2)
        assert m1[smi_id]["raw_text"] == "派生:SMI=7.03"
        m2 = repo.get_measurements(conn, s2, pid)
        assert m2[muscle["id"]]["value"] == 17.5
        assert m2[smi_id]["value"] is None          # 身長が無い回は算出不可 → 未測定

        # 2 回目の起動では何も変えない(算出済みの SMI を筋肉量として再移行しない)
        seed.apply_seed(conn)
        assert repo.get_measurements(conn, s1, pid)[muscle["id"]]["value"] == 18.0
        assert repo.get_measurements(conn, s1, pid)[smi_id]["value"] == pytest.approx(18.0 / 1.6 ** 2)


def test_backfill_skips_customized_smi_item(tmp_env):
    """SMI の取込列を施設側で変えている場合は、勝手に派生へ切り替えない."""
    db.init_db(seed=True)
    with db.get_conn() as conn:
        conn.execute("UPDATE eval_items SET source_column='SMI値', derived_formula=NULL WHERE name='SMI'")
        seed.apply_seed(conn)
        item = repo.get_item_by_name(conn, "SMI")
    assert (item["source_column"], item["derived_formula"]) == ("SMI値", None)
