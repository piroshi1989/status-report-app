"""帳票の項目・区分・並び順(評価基準 Excel 最終版「グラフ①」)と、SMI/下腿周囲長の差し替え."""

from __future__ import annotations

import sqlite3

from app import db, repo, seed
from app.services.report import build_report

FINAL_ORDER = [
    "HbA1c", "収縮期血圧", "嚥下機能", "口腔機能", "聴力1000Hz", "聴力4000Hz",
    "骨密度(大腿骨)", "骨密度(腰椎)",
    "Barthel Index", "FIM", "mini-Cog", "TUG", "FRT", "握力",
    "SMI", "BMI", "体重増減率", "喫食率",
]


def _report_names(conn, pacemaker: int):
    pid = repo.create_patient(conn, code=f"P{pacemaker}", name="x", sex="M",
                              birth_date="1945-01-01", pacemaker=pacemaker)
    sid = repo.create_session(conn, 1, "2026-07-01", "a.xlsx")
    return [ln.name for ln in build_report(conn, pid, sid).lines], build_report(conn, pid, sid)


def test_fresh_db_report_has_final_18_items_in_order(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        names, data = _report_names(conn, 0)
        assert names == FINAL_ORDER
        assert data.radar_labels == FINAL_ORDER          # レーダーも 18 項目すべて
        cats = {ln.name: ln.category for ln in data.lines}
        assert (cats["HbA1c"], cats["握力"], cats["喫食率"]) == ("看護", "体力", "栄養")
        inactive = {it["name"] for it in repo.list_items(conn, include_inactive=True) if not it["is_active"]}
        assert {"身長", "体重", "筋肉量", "片脚立位時間", "視力", "CRP"} <= inactive


def test_pacemaker_patient_sees_calf_instead_of_smi(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        names, data = _report_names(conn, 1)
    assert "SMI" not in names
    assert names[names.index("BMI") - 1] == "下腿周囲長"   # SMI と同じ位置
    assert "下腿周囲長" in data.radar_labels


def _legacy_db(path):
    """初期版のスキーマ(新しい列なし)・項目構成の DB を作る."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    schema = (db._schema_sql()
              .replace("    unmeasured_score   INTEGER,                -- 未計測時に付ける評価(NULL=評価なし。例: HbA1c は 5)\n", "")
              .replace("    unmeasured_comment TEXT,                   -- 未計測時のコメント(NULL=同じ評価の基準行のコメント)\n", "")
              .replace("    pm_display     TEXT,                       -- 帳票に出す対象: NULL=全員 / 'with_pm' / 'without_pm'\n", ""))
    assert "pm_display" not in schema
    conn.executescript(schema)
    # 取込列名は初期版の seed と同じ(SMI は筋肉量をそのまま取り込んでいた)
    src = {name: src for name, _u, _c, _d, _r, src, _dv, _q in seed.ITEMS}
    src["SMI"] = "筋肉量"
    for i, name in enumerate(["身長", "体重", "HbA1c", "収縮期血圧", "SMI", "片脚立位時間", "施設独自項目"], 1):
        conn.execute(
            "INSERT INTO eval_items (name, category, sort_order, in_radar, source_column) VALUES (?,?,?,1,?)",
            (name, "旧区分", i, src.get(name, name)),
        )
    conn.commit()
    conn.close()


def test_existing_db_gets_columns_and_layout_once(tmp_env):
    from app import config

    _legacy_db(config.db_path())
    db.init_db(seed=True)
    with db.get_conn() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(eval_items)")}
        assert {"unmeasured_score", "unmeasured_comment", "pm_display"} <= cols
        hba1c = repo.get_item_by_name(conn, "HbA1c")
        assert (hba1c["category"], hba1c["sort_order"], hba1c["unmeasured_score"]) == ("看護", 1, 5)
        assert repo.get_item_by_name(conn, "片脚立位時間")["is_active"] == 0
        assert repo.get_item_by_name(conn, "SMI")["pm_display"] == "without_pm"
        calf = repo.get_item_by_name(conn, "下腿周囲長")
        assert (calf["is_active"], calf["pm_display"], calf["in_radar"]) == (1, "with_pm", 1)
        custom = repo.get_item_by_name(conn, "施設独自項目")
        assert (custom["category"], custom["is_active"]) == ("旧区分", 1)   # 独自項目は触らない

        # 施設がその後に画面で変えた設定は、次の起動で戻さない
        conn.execute("UPDATE eval_items SET is_active=1 WHERE name='片脚立位時間'")
    db.init_db(seed=True)
    with db.get_conn() as conn:
        assert repo.get_item_by_name(conn, "片脚立位時間")["is_active"] == 1


def test_item_form_saves_unmeasured_and_pm_display(client):
    with db.get_conn() as conn:
        item = repo.get_item_by_name(conn, "FRT")
    form = {
        "name": item["name"], "unit": item["unit"] or "", "category": item["category"] or "",
        "sort_order": str(item["sort_order"]), "direction": item["direction"],
        "in_radar": "1", "is_active": "1",
        "unmeasured_score": "3", "unmeasured_comment": "測れませんでした", "pm_display": "with_pm",
    }
    assert client.post(f"/criteria/{item['id']}/item", data=form, follow_redirects=False).status_code == 303
    with db.get_conn() as conn:
        saved = repo.get_item(conn, item["id"])
    assert (saved["unmeasured_score"], saved["unmeasured_comment"], saved["pm_display"]) == (
        3, "測れませんでした", "with_pm")
    page = client.get(f"/criteria/{item['id']}")
    assert "測れませんでした" in page.text


def test_previous_radar_score_for_weight_change_uses_session_before(tmp_env):
    db.init_db(seed=True)
    with db.get_conn() as conn:
        item = repo.get_item_by_name(conn, "体重増減率")
        repo.add_criterion(conn, item["id"], None, None, None, -100, 5, "正常")
        repo.add_criterion(conn, item["id"], None, None, None, 3, 2, "リスク高")
        wid = repo.get_item_by_name(conn, "体重")["id"]
        pid = repo.create_patient(conn, code="W", name="W", sex="F", birth_date="1950-01-01")
        sessions = [repo.create_session(conn, i, f"2026-0{i}-01", "x") for i in (1, 2, 3)]
        for sid, w in zip(sessions, (50.0, 45.0, 45.0)):   # 2 回目に 10% 減、3 回目は変化なし
            repo.upsert_measurement(conn, sid, pid, wid, w, str(w))
        data = build_report(conn, pid, sessions[2])
    i = data.radar_labels.index("体重増減率")
    assert (data.radar_scores[i], data.radar_prev_scores[i]) == (5, 2)


# --- レビュー指摘の回帰テスト -----------------------------------------------------

def test_unmeasured_score_is_shown_in_score_column(client):
    """未計測の HbA1c(★5)は相対評価欄にも 5 を出す(―にしない)."""
    from app.services.pdf import build_flowables
    from reportlab.platypus import Table

    with db.get_conn() as conn:
        pid = repo.create_patient(conn, code="U", name="x", sex="F", birth_date="1945-01-01")
        sid = repo.create_session(conn, 1, "2026-07-01", "a.xlsx")
        repo.upsert_measurement(conn, sid, pid, repo.get_item_by_name(conn, "TUG")["id"], 9.0, "9")
        data = build_report(conn, pid, sid)
    tbl = next(f for f in build_flowables(data) if isinstance(f, Table))
    rows = [[c.getPlainText() for c in r] for r in tbl._cellvalues]
    hba1c = next(r for r in rows if r[1] == "HbA1c")
    assert (hba1c[3], hba1c[5], hba1c[6]) == ("未測定", "5", "★★★★★")
    page = client.get(f"/report?session_id={sid}&patient_id={pid}")
    assert '<td class="center">5</td>' in page.text


def test_layout_finds_items_renamed_by_facility(tmp_env):
    from app import config

    _legacy_db(config.db_path())
    with db.get_conn() as conn:
        conn.execute("UPDATE eval_items SET name='身長(cm)' WHERE name='身長'")
        conn.execute("UPDATE eval_items SET name='血圧' WHERE name='収縮期血圧'")
    db.init_db(seed=True)
    with db.get_conn() as conn:
        assert repo.get_item_by_name(conn, "身長(cm)")["is_active"] == 0
        bp = repo.get_item_by_name(conn, "血圧")
        assert (bp["category"], bp["sort_order"], bp["unmeasured_score"]) == ("看護", 2, 1)
        assert repo.get_item_by_name(conn, "収縮期血圧") is None   # 重複して作らない


def test_custom_items_are_not_counted_in_summary(tmp_env):
    """総合評価の区切り(14/8/5)は Excel の 18 行が前提なので、独自項目は数えない."""
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid = repo.create_patient(conn, code="C", name="x", sex="F", birth_date="1948-01-01")
        sid = repo.create_session(conn, 1, "2026-07-01", "a.xlsx")
        repo.upsert_measurement(conn, sid, pid, repo.get_item_by_name(conn, "TUG")["id"], 9.0, "9")
        for i in range(5):   # ★5 の独自項目を 5 つ
            iid = repo.create_item(conn, name=f"独自{i}", sort_order=900 + i, in_radar=0)
            repo.add_criterion(conn, iid, None, None, None, 0, 5, "良い")
            repo.upsert_measurement(conn, sid, pid, iid, 1.0, "1")
        data = build_report(conn, pid, sid)
        expected = repo.get_setting(conn, "summary_rank_4")   # TUG + 未計測 HbA1c = 2 個
    assert data.summary == expected


def test_pacemaker_patient_in_fifties_falls_back_to_smi(tmp_env):
    """下腿周囲長に 50代以下(PM 有)の基準が無いときは SMI で評価する."""
    db.init_db(seed=True)
    with db.get_conn() as conn:
        calf = repo.get_item_by_name(conn, "下腿周囲長")["id"]
        repo.add_criterion(conn, calf, "M", "60", 1, 0, 1, "低い")
        repo.add_criterion(conn, calf, "M", "60", 1, 34, 5, "良い")
        names_50, _ = _report_names(conn, 1)               # 1945 年生 → 81 歳
        pid = repo.create_patient(conn, code="Y", name="y", sex="M", birth_date="1970-01-01", pacemaker=1)
        sid = repo.create_session(conn, 9, "2026-07-01", "b.xlsx")
        young = [ln.name for ln in build_report(conn, pid, sid).lines]
        pid6 = repo.create_patient(conn, code="Z", name="z", sex="M", birth_date="1962-01-01", pacemaker=1)
        sixties = [ln.name for ln in build_report(conn, pid6, sid).lines]
    assert "SMI" in young and "下腿周囲長" not in young      # 56 歳: 基準なし → SMI
    assert "下腿周囲長" in sixties and "SMI" not in sixties  # 64 歳: 60代の基準あり
    assert "SMI" in names_50                                  # 81 歳: 80代の基準なし → SMI
