# CLAUDE.md — status-report-app

介護施設の測定結果を評価し「状況報告書」PDF を出力するローカル Web アプリ。
FastAPI + Jinja2 + SQLite。matplotlib(レーダー)/ ReportLab(PDF)。配布は Nuitka standalone(フォルダ配布)。

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
    importer.py       測定結果 .xls/.xlsx 取込・列マッピング・派生(BMI)・未登録警告
    patient_importer.py 利用者 .xls/.xlsx 一括取込(新規/更新・空欄は非上書き)・テンプレ生成
    criteria_importer.py 評価基準Excel(評価項目 改訂案形式)取込: シート=年代±PM・項目名マッピング・正規化・置換
    report.py         報告書データ組み立て(表・レーダー・総合評価)
    radar.py          matplotlib レーダー(画面/PDF 共通・PNG)
    pdf.py            ReportLab 個別/一括 PDF(IPAexフォント登録)
  routers/            home/patients/upload/report/criteria/pdf_router
  templates/ static/  Jinja2 テンプレート・CSS・同梱フォント
scripts/migrate_excel.py  評価基準Excel取込の CLI 版(criteria_importer を使う)
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
- `seed.py` の閾値は**サンプル**。実運用値は基準マスタ画面の「評価基準を Excel から取込」
  (`/criteria/import`、取込前に `data/backups/` へ DB を自動バックアップ)で置換する。
  Excel 項目名→アプリ項目名は `criteria_importer.EXCEL_ITEM_MAP`。Excel 側の判定は
  VLOOKUP 近似一致(=測定値以下で最大の下限値)で評価エンジンと同じ。
- 体重増減率は前回比(107%表記)で表示し、評価は Excel と同じ**体重減少率**
  (前回−今回)÷前回×100 で行う(`report._weight_loss_value`)。
- 年代バンド '50' は「50代以下」(59歳以下を一括)。
- PDF はコメント長で表の高さが変わるため、`pdf.fitted_flowables` が `FIT_STEPS`
  (表の文字 8→6pt・レーダー縮小)から A4 1 ページに収まる最大段階を選ぶ。
- テンプレート呼び出しは `templates.TemplateResponse("name.html", {"request": request, ...})` 記法(ラッパが新 API に変換)。
- 取込の「空欄」は `None`(未入力=非上書き)、`0`/`無` とは区別する。`_is_blank` で `NaN`/`NaT` を先に弾く。
- `routers/patients.py` / `routers/criteria.py` の `/import*` は静的パスなので `/{pid}`・`/{item_id}` 系より**先に**定義すること。
- フォームのチェックボックスは外すと送信されないので、`Form("")` を既定にする(`Form("1")` だと外せない)。
- Starlette は新シグネチャ、SQLite 接続は `check_same_thread=False`(リクエスト毎に独立接続)。
- 配布は Nuitka standalone(`scripts/build_nuitka.ps1` / `.sh`)。`config.py` は PyInstaller
  (`sys._MEIPASS`)と Nuitka(`__compiled__`)を判別。書き込み先(data/output)は実 exe 隣、
  リソース(templates/static/schema.sql)は `--include-data-*` で同梱し `__file__` 相対で解決。
- アップロード token は `app/uploads.py` の `save_upload`/`resolve_token` 経由(パストラバーサル対策)。
