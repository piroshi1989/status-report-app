# CLAUDE.md — status-report-app

介護施設の測定結果を評価し「状況報告書」PDF を出力するローカル Web アプリ。
FastAPI + Jinja2 + SQLite。matplotlib(レーダー)/ ReportLab(PDF)。配布は PyInstaller onefile。

## 構成

```
run.py                エントリ(app.server.run を呼ぶ)
app/
  config.py           パス解決(frozen/通常・環境変数上書き)
  db.py               SQLite 接続・schema.sql 適用・初回シード
  schema.sql          スキーマ DDL
  domain.py           年代算出(floor→[50,90]クランプ)・★表記
  repo.py             データアクセス層(全 SQL・conn を引数に取る)
  seed.py             既定の評価項目・サンプル基準・エイリアス・固定文言
  templating.py       Jinja2 ラッパ(Starlette 新シグネチャへ橋渡し)
  deps.py             FastAPI DB 依存
  main.py             FastAPI アプリ(lifespan で init_db)
  server.py           空きポート起動 + ブラウザオープン
  services/
    evaluation.py     基準解決 + 一様スコアリング(純関数・テスト対象)
    importer.py       .xls/.xlsx 取込・列マッピング・派生(BMI)・未登録警告
    report.py         報告書データ組み立て(表・レーダー・総合評価)
    radar.py          matplotlib レーダー(画面/PDF 共通・PNG)
    pdf.py            ReportLab 個別/一括 PDF(IPAexフォント登録)
  routers/            home/patients/upload/report/criteria/pdf_router
  templates/ static/  Jinja2 テンプレート・CSS・同梱フォント
scripts/migrate_excel.py  既存9シートExcel→基準の正規化移行
tests/                評価単体・アプリ結合・(実データ回帰=fixture任意)
```

## 評価エンジンの中核ルール(services/evaluation.py)

- `eval_criteria` 1 行 = 条件(sex/age_band/pacemaker, NULL=全展開)下の「区間下限 threshold → score(1-5) + comment」。
- **基準解決**: 患者属性に適合し最も具体的(非NULL条件が多い)な条件セットを選ぶ。
- **スコアリング**: 方向に依らず「測定値以下で最大の threshold」の行を採用(higher/lower/range/qualitative を一様処理)。
- 未測定(value=None)は measured=False、★☆表記は ☆×5。

## 開発

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
python run.py
```

## 注意

- 個人情報はローカル SQLite のみ。外部送信しない。`*.db` / `data/` / `output/` は Git 管理外。
- `seed.py` の閾値は**サンプル**。実運用値は `scripts/migrate_excel.py` で移行して置換する。
- テンプレート呼び出しは `templates.TemplateResponse("name.html", {"request": request, ...})` 記法(ラッパが新 API に変換)。
- Starlette は新シグネチャ、SQLite 接続は `check_same_thread=False`(リクエスト毎に独立接続)。
