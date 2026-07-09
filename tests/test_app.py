"""アプリ全体のスモーク/結合テスト."""

from __future__ import annotations


def test_pages_render(client):
    for path in ["/", "/patients", "/patients/new", "/upload", "/criteria", "/report", "/batch"]:
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"


def test_patient_crud(client):
    r = client.post(
        "/patients/new",
        data={"code": "U001", "name": "山田太郎", "sex": "M",
              "birth_date": "1950-05-01", "pacemaker": "0"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    lst = client.get("/patients")
    assert "山田太郎" in lst.text
    assert "U001" in lst.text


def test_upload_analyze_commit_and_report_pdf(client, make_xlsx):
    # 患者を登録(女性・握力基準の性別依存を確認)
    client.post("/patients/new", data={"code": "P100", "name": "花子", "sex": "F",
                                        "birth_date": "1948-01-01", "pacemaker": "0"})
    xlsx = make_xlsx([
        ["P100", 150, 50, 6.8, "128/80", 20, 9.5],
        ["P200", 165, 60, 9.5, "150/95", 30, 15.0],  # 未登録
    ])

    with open(xlsx, "rb") as f:
        r = client.post(
            "/upload/analyze",
            files={"file": ("measurements.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"session_no": "1", "measured_on": "2026-07-01"},
        )
    assert r.status_code == 200
    assert "P200" in r.text  # 未登録警告
    # token を取り出す
    import re
    token = re.search(r'name="token" value="([^"]+)"', r.text).group(1)

    r2 = client.post(
        "/upload/commit",
        data={"token": token, "orig_name": "measurements.xlsx", "session_no": "1",
              "measured_on": "2026-07-01", "auto_register": "1"},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert "/report?session_id=" in r2.headers["location"]
    sid = int(r2.headers["location"].split("session_id=")[1])

    # 報告書プレビュー
    rep = client.get(f"/report?session_id={sid}")
    assert rep.status_code == 200
    assert "評価詳細" in rep.text
    assert "BMI" in rep.text  # 派生項目が表示される

    # 個別 PDF
    from app import repo, db
    with db.get_conn() as c:
        p = repo.get_patient_by_code(c, "P100")
    pdf = client.get(f"/report/pdf?session_id={sid}&patient_id={p['id']}")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"

    # 一括 PDF
    batch = client.post("/batch/generate", data={"session_id": str(sid), "save_to_disk": "1"})
    assert batch.status_code == 200
    assert batch.content[:4] == b"%PDF"


def test_criteria_add_and_delete(client):
    from app import db, repo
    with db.get_conn() as c:
        item = repo.get_item_by_name(c, "TUG")
        item_id = item["id"]
    r = client.post(
        f"/criteria/{item_id}/criterion/add",
        data={"sex": "", "age_band": "70", "pacemaker": "", "threshold": "5",
              "score": "5", "comment": "テスト良好"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    detail = client.get(f"/criteria/{item_id}")
    assert "テスト良好" in detail.text


def test_derived_bmi_computed(client, make_xlsx):
    client.post("/patients/new", data={"code": "B1", "name": "BMIさん", "sex": "M",
                                        "birth_date": "1955-01-01"})
    xlsx = make_xlsx([["B1", 170, 65, 6.0, "120/70", 35, 8.0]])
    with open(xlsx, "rb") as f:
        r = client.post("/upload/analyze",
                        files={"file": ("m.xlsx", f, "application/octet-stream")},
                        data={"session_no": "1", "measured_on": "2026-07-01"})
    import re
    token = re.search(r'name="token" value="([^"]+)"', r.text).group(1)
    client.post("/upload/commit", data={"token": token, "orig_name": "m.xlsx",
                                        "session_no": "1", "measured_on": "2026-07-01"})
    from app import db, repo
    from app.services.report import build_report
    with db.get_conn() as c:
        p = repo.get_patient_by_code(c, "B1")
        sid = repo.list_sessions(c)[0]["id"]
        data = build_report(c, p["id"], sid)
    bmi_line = next(ln for ln in data.lines if ln.name == "BMI")
    # 65 / (1.7^2) = 22.49...
    assert bmi_line.measured
    assert abs(bmi_line.value - 22.5) < 0.1
