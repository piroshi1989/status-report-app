"""状況報告書 PDF のレイアウト(ページ数)回帰テスト.

評価項目が増えると本文が A4 1 ページを超えて改頁されるため、
「全項目ぶんの表 + レーダー + 総合評価 + 注意書き」が 1 ページに収まることを担保する。
"""

from __future__ import annotations

import re


def page_count(pdf_bytes: bytes) -> int:
    """PDF のページ数(ReportLab 出力の /Type /Page オブジェクト数)."""
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf_bytes))


def _make_two_sessions(client, make_xlsx) -> tuple[int, int]:
    """体重増減率まで出る状態(2 回目のセッション)を作り、(patient_id, session_id) を返す."""
    client.post("/patients/new", data={"code": "L1", "name": "頁数確認さん", "sex": "M",
                                       "birth_date": "1940-03-15", "pacemaker": "0"})

    def _upload(weight, session_no, measured_on):
        xlsx = make_xlsx([["L1", 162, weight, 8.4, "145/88", 24, 14.2]])
        with open(xlsx, "rb") as f:
            r = client.post(
                "/upload/analyze",
                files={"file": ("m.xlsx", f, "application/octet-stream")},
                data={"session_no": str(session_no), "measured_on": measured_on},
            )
        token = re.search(r'name="token" value="([^"]+)"', r.text).group(1)
        r2 = client.post(
            "/upload/commit",
            data={"token": token, "orig_name": "m.xlsx", "session_no": str(session_no),
                  "measured_on": measured_on},
            follow_redirects=False,
        )
        return int(r2.headers["location"].split("session_id=")[1])

    _upload(58, 1, "2026-01-10")
    sid2 = _upload(55, 2, "2026-07-10")

    from app import db, repo
    with db.get_conn() as c:
        pid = repo.get_patient_by_code(c, "L1")["id"]
    return pid, sid2


def test_single_report_pdf_fits_on_one_page(client, make_xlsx):
    pid, sid = _make_two_sessions(client, make_xlsx)
    pdf = client.get(f"/report/pdf?session_id={sid}&patient_id={pid}")
    assert pdf.status_code == 200
    assert page_count(pdf.content) == 1


def test_batch_pdf_uses_one_page_per_patient(client, make_xlsx):
    _pid, sid = _make_two_sessions(client, make_xlsx)
    batch = client.post("/batch/generate", data={"session_id": str(sid)})
    assert batch.status_code == 200
    assert page_count(batch.content) == 1


# 1 ページに収められる項目数の目安。将来の項目追加に対する余裕を担保する。
HEADROOM_ITEM_COUNT = 27


def test_report_pdf_keeps_one_page_with_more_items(client, make_xlsx):
    """評価項目が HEADROOM_ITEM_COUNT まで増えても 1 ページを保つこと."""
    from app import db, repo

    with db.get_conn() as c:
        for i in range(HEADROOM_ITEM_COUNT - len(repo.list_items(c))):
            repo.create_item(
                c, name=f"追加項目{i + 1}", unit="点", category="身体機能",
                sort_order=900 + i, direction="higher_better", in_radar=0,
                source_column=None, derived_formula=None, is_qualitative=0,
            )

    pid, sid = _make_two_sessions(client, make_xlsx)
    pdf = client.get(f"/report/pdf?session_id={sid}&patient_id={pid}")
    assert pdf.status_code == 200
    assert page_count(pdf.content) == 1


# 全項目に値が入った状態の代表値(seed の既定項目に対応)
FULL_VALUES = {
    "身長": 162.0, "体重": 55.0, "HbA1c": 8.4, "収縮期血圧": 145.0, "嚥下機能": 2.0,
    "口腔機能": 2.0, "聴力1000Hz": 45.0, "聴力4000Hz": 62.0, "骨密度(腰椎)": 72.0,
    "骨密度(大腿骨)": 68.0, "Barthel Index": 65.0, "FIM": 95.0, "mini-Cog": 2.0,
    "TUG": 14.2, "FRT": 18.0, "握力": 24.0, "SMI": 6.4, "喫食率": 7.0,
    "片脚立位時間": 8.0, "BMI": 21.0,
}


def test_pdf_table_cells_fit_on_one_line(tmp_env):
    """詳細表のどのセルも折り返さないこと.

    列幅を詰めすぎるとセルが 2 行になり、表の高さが倍近くに膨らんで 1 ページに
    収まらなくなる。列を増やすときはこのテストで各列の幅を担保する。
    """
    from reportlab.platypus import Table

    from app import db, repo
    from app.services.pdf import build_flowables
    from app.services.report import build_report

    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid = repo.create_patient(conn, code="F1", name="全項目", sex="M", birth_date="1940-03-15")
        s1 = repo.create_session(conn, 1, "2026-01-10", "f1.xlsx")
        s2 = repo.create_session(conn, 2, "2026-07-10", "f2.xlsx")
        for it in repo.list_items(conn):
            v = FULL_VALUES.get(it["name"])
            if v is None:
                continue
            repo.upsert_measurement(conn, s2, pid, it["id"], v, "145/88" if it["name"] == "収縮期血圧" else "")
            repo.upsert_measurement(conn, s1, pid, it["id"],
                                    58.0 if it["name"] == "体重" else v,
                                    "128/80" if it["name"] == "収縮期血圧" else "")
        data = build_report(conn, pid, s2)

    tbl = next(f for f in build_flowables(data) if isinstance(f, Table))
    inner = 12  # ReportLab Table 既定の LEFTPADDING + RIGHTPADDING(pt)
    wrapped = [
        (r, c, cell.getPlainText())
        for r, row in enumerate(tbl._cellvalues)
        for c, cell in enumerate(row)
        if round(cell.wrap(tbl._argW[c] - inner, 10000)[1] / cell.style.leading) > 1
    ]
    assert wrapped == [], f"折り返しているセル: {wrapped}"
