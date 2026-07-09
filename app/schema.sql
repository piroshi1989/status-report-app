-- 状況報告書作成アプリ スキーマ (SQLite)
-- 個人情報を含むためローカルのみに保存する。

PRAGMA foreign_keys = ON;

-- 患者(利用者)
CREATE TABLE IF NOT EXISTS patients (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL UNIQUE,          -- 利用者コード
    name       TEXT NOT NULL,
    sex        TEXT,                          -- 'M' / 'F'
    birth_date TEXT,                          -- ISO 'YYYY-MM-DD'
    pacemaker  INTEGER NOT NULL DEFAULT 0,    -- 0/1
    note       TEXT,
    med_info   TEXT,                          -- 服薬情報(血糖降下薬など、任意)
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 測定イベント(アップロード単位)
CREATE TABLE IF NOT EXISTS measurement_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_no  INTEGER,                      -- 第n回
    measured_on TEXT,                         -- 評価日 'YYYY-MM-DD'
    source_file TEXT,
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 評価項目マスタ
CREATE TABLE IF NOT EXISTS eval_items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    unit           TEXT,
    category       TEXT,                       -- 帳票の色分けグループ
    sort_order     INTEGER NOT NULL DEFAULT 0,
    direction      TEXT NOT NULL DEFAULT 'higher_better', -- higher_better/lower_better/range/qualitative
    in_radar       INTEGER NOT NULL DEFAULT 1, -- レーダーチャート対象
    source_column  TEXT,                       -- 取込マッピング(測定結果一覧の列名)
    derived_formula TEXT,                       -- 派生項目キー(例: bmi)
    is_qualitative INTEGER NOT NULL DEFAULT 0, -- コード値項目(嚥下機能など)
    is_active      INTEGER NOT NULL DEFAULT 1,
    UNIQUE(name)
);

-- 測定値(縦持ち)
CREATE TABLE IF NOT EXISTS measurements (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES measurement_sessions(id) ON DELETE CASCADE,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    item_id    INTEGER NOT NULL REFERENCES eval_items(id) ON DELETE CASCADE,
    value      REAL,                           -- NULL = 未測定
    raw_text   TEXT,                           -- 元セル文字列
    UNIQUE(session_id, patient_id, item_id)
);

-- 評価基準(閾値と評価・コメントのセット)
-- 1行 = ある条件下での「区間下限値 threshold」に対応する score(1-5)とコメント。
CREATE TABLE IF NOT EXISTS eval_criteria (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL REFERENCES eval_items(id) ON DELETE CASCADE,
    sex         TEXT,                           -- NULL=展開(全性別)
    age_band    TEXT,                           -- '50'/'60'/'70'/'80'/'90' / NULL=展開
    pacemaker   INTEGER,                        -- 0/1 / NULL=展開
    threshold   REAL NOT NULL,                  -- 区間下限値
    score       INTEGER NOT NULL,               -- 1〜5
    comment     TEXT,                           -- 評価コメント / 定性値の表示文言
    description TEXT,                            -- 項目説明(帳票脚注用)
    valid_from  TEXT NOT NULL DEFAULT (date('now','localtime')) -- 改訂日
);
CREATE INDEX IF NOT EXISTS idx_criteria_item ON eval_criteria(item_id);

-- 固定文言等の設定
CREATE TABLE IF NOT EXISTS report_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- 取込列名マッピング(ゆらぎ吸収; source_column の別名 -> item_id)
CREATE TABLE IF NOT EXISTS column_aliases (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    alias   TEXT NOT NULL,
    item_id INTEGER NOT NULL REFERENCES eval_items(id) ON DELETE CASCADE,
    UNIQUE(alias)
);
