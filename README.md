# 状況報告書作成アプリ (status-report-app)

介護施設の利用者測定結果を評価し、「状況報告書」を PDF 帳票として出力するローカル Web アプリです。
既存の 2 つの Excel(測定結果一覧 / 評価項目 改訂案 9 シート)を Python 製に置き換えたものです。

- **ローカル完結**: 個人情報(氏名・生年月日等)は端末内の SQLite にのみ保存し、外部送信は一切行いません。
- **exe 起動 → ブラウザ表示**: 起動すると空きポートで内部サーバが立ち上がり、既定ブラウザで画面が開きます。
- **PDF 一括出力**: 1 回分の測定結果から全利用者の報告書を 1 つの PDF にまとめて生成できます。

## 主な機能

| 画面 | 内容 |
|---|---|
| ホーム | 登録数・最近の測定回のショートカット |
| 測定結果取込 | `.xls` / `.xlsx` をアップロード → プレビュー(未登録利用者の警告)→ 確定 |
| 利用者 | 登録・検索・編集・有効/無効(論理削除)・**Excel 一括取込** |
| 状況報告書 | 利用者×測定回を選び、評価表 + レーダーチャート + 総合評価を表示・個別 PDF 出力 |
| 一括PDF | 測定回を選び、全利用者分を 1 PDF で生成・保存 |
| 評価基準マスタ | 評価項目・閾値・コメント・★表記・帳票文言の編集 |

## 利用者の Excel 一括取込

「利用者」画面の **Excel一括取込** から `.xls` / `.xlsx` を取り込めます。
画面から入力用テンプレート(`patients_template.xlsx`)をダウンロードできます。

- 1 行 = 1 利用者。**利用者コードのみ必須**。
- 列名はゆらぎを吸収(`利用者コード` / `コード` / `ID`、`ペースメーカー` / `PM` など)。
- 性別は `男` `女` `M` `F` `男性` `女性`、ペースメーカーは `有` `無` `1` `0` `○` `×` を解釈。
- 生年月日は Excel の日付セル・`1950-05-01` / `1950/5/1` / `1950年5月1日` / シリアル値に対応。
- 既存の利用者コードは**更新**(チェックを外せばスキップ)。
  **空欄の項目は既存の値を上書きしません**(例: 氏名だけ直したいとき他を空欄にできる)。
- 解釈できない値やファイル内のコード重複は**エラー行**としてプレビューに表示し、その行だけスキップします。

> 測定結果取込の「未登録を仮登録」はコードと氏名しか埋まりません。
> 性別・生年月日は評価基準の解決に必要なので、先に利用者を一括取込しておくことを推奨します。

## 評価ロジックの要点

- 評価基準 `eval_criteria` の 1 行は「ある条件下での区間下限値 `threshold` に対応する相対評価(1〜5)とコメント」です。
- 判定は評価方向(大きいほど良い / 小さいほど良い / 範囲内が良い / 定性値)に依らず一様で、
  **測定値以下で最大の閾値の行**の score/comment を採用します。
- 条件は `性別 / 年代 / ペースメーカー有無`。**NULL = 全展開**。
  患者属性に適合し、かつ**最も具体的な条件セット**が優先されます(性別+年代 > 年代のみ > 全展開)。
- 年代は生年月日と評価日から自動算出: `floor(年齢/10)*10` を 50〜90 にクランプ(50 は「50代以上」バケット)。
- 未測定(空セル)は常に許容し、帳票では「未測定 / ☆☆☆☆☆」と表示します。

## 開発環境での実行

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python run.py                     # サーバ起動 + ブラウザ自動オープン
```

ブラウザを自動で開きたくない場合:

```bash
STATUS_REPORT_NO_BROWSER=1 python run.py
```

### 環境変数

| 変数 | 既定 | 用途 |
|---|---|---|
| `STATUS_REPORT_DB` | `data/status_report.db` | DB ファイルパス |
| `STATUS_REPORT_DATA_DIR` | `data/` | DB・アップロード一時ファイルの保存先 |
| `STATUS_REPORT_OUTPUT_DIR` | `output/` | 一括 PDF の保存先 |
| `STATUS_REPORT_PORT` | 自動(空きポート) | 使用ポート固定 |
| `STATUS_REPORT_NO_BROWSER` | (未設定) | `1` でブラウザ自動オープン無効 |

## テスト

```bash
pytest -q
```

評価エンジンの単体テスト、アプリ結合テスト(取込→報告書→PDF)を含みます。
実 Excel を用いた**回帰テスト**(既存Excelと同じ評価値になることの検証)は、
`tests/fixtures/criteria.xlsx` と `tests/fixtures/expected.csv` を配置すると自動で有効になります。

## 既存 Excel からの基準移行

「評価項目 改訂案.xlsx」(9 シート)を評価基準マスタへ取り込みます。
冗長にコピーされた基準は条件付き(NULL=全展開)に正規化されます。

```bash
python scripts/migrate_excel.py path/to/評価項目_改訂案.xlsx --dump      # まず内容確認
python scripts/migrate_excel.py path/to/評価項目_改訂案.xlsx --dry-run   # 解析結果を確認
python scripts/migrate_excel.py path/to/評価項目_改訂案.xlsx            # DB へ反映
```

実ファイルのシート名・列見出しが想定と異なる場合は、`scripts/migrate_excel.py` 冒頭の
`SHEET_MAP` / `HEADER_*` を調整してください。

## Windows 配布用 exe のビルド

```bash
pip install -r requirements-dev.txt
pyinstaller status_report.spec
# dist/状況報告書アプリ.exe が生成される
```

タグ push(`v*`)で GitHub Actions(windows-latest)が自動ビルドし、Releases に exe を添付します。

> **SmartScreen について**: 未署名 exe のため、初回起動時に Windows SmartScreen の警告が出ることがあります。
> 「詳細情報」→「実行」で起動できます。社内配布時は許可リスト登録を検討してください。

## データのバックアップ

すべてのデータは `data/status_report.db`(SQLite 単一ファイル)に保存されます。
アプリ終了後にこのファイルをコピーするだけでバックアップ・復元できます。

## 同梱フォント

日本語表示に IPAexゴシック(`app/static/fonts/ipaexg.ttf`)を同梱しています。
IPA Font License Agreement v1.0 に基づき再配布しています。詳細は [NOTICE.md](NOTICE.md) を参照してください。

## ライセンス

本アプリのソースコードは [LICENSE](LICENSE)(MIT)の下で提供されます。
同梱フォントのライセンスは上記のとおり別途 IPA Font License です。
