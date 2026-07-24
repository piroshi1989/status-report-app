"""初回起動時の既定マスタ・シード投入.

注意: eval_criteria の閾値は**サンプル値**。実運用の閾値は既存 Excel
(評価項目 改訂案.xlsx)から ``scripts/migrate_excel.py`` で移行して置き換える。
評価エンジンのロジック自体はこのサンプルに依存しない(tests/ で担保)。
"""

from __future__ import annotations

import sqlite3

from . import repo

# (name, unit, category, direction, in_radar, source_column, derived_formula, is_qualitative)
ITEMS = [
    ("身長", "cm", "身体計測", "higher_better", 0, "身長", None, 0),
    ("体重", "kg", "身体計測", "range", 0, "体重", None, 0),
    ("BMI", "", "栄養", "range", 1, None, "bmi", 0),
    ("HbA1c", "%", "検査値", "lower_better", 1, "HbA1c", None, 0),
    ("収縮期血圧", "mmHg", "検査値", "range", 1, "血圧", None, 0),
    ("嚥下機能", "", "口腔・嚥下", "qualitative", 1, "嚥下機能", None, 1),
    ("口腔機能", "", "口腔・嚥下", "qualitative", 1, "口腔機能", None, 1),
    ("聴力1000Hz", "dB", "感覚機能", "lower_better", 0, "聴力1000", None, 0),
    ("聴力4000Hz", "dB", "感覚機能", "lower_better", 0, "聴力4000", None, 0),
    ("骨密度(腰椎)", "%YAM", "身体機能", "higher_better", 1, "骨密度(腰椎)", None, 0),
    ("骨密度(大腿骨)", "%YAM", "身体機能", "higher_better", 1, "骨密度(大腿骨)", None, 0),
    ("Barthel Index", "点", "生活機能", "higher_better", 1, "バーセル", None, 0),
    ("FIM", "点", "生活機能", "higher_better", 1, "FIM", None, 0),
    ("mini-Cog", "点", "認知", "higher_better", 1, "mini-Cog合計", None, 0),
    ("TUG", "秒", "身体機能", "lower_better", 1, "TUG", None, 0),
    ("FRT", "cm", "身体機能", "higher_better", 1, "FRT", None, 0),
    ("握力", "kg", "身体機能", "higher_better", 1, "握力", None, 0),
    ("SMI", "kg/m2", "身体機能", "higher_better", 1, "筋肉量", None, 0),
    ("喫食率", "割", "栄養", "higher_better", 1, "喫食率", None, 0),
    ("片脚立位時間", "秒", "身体機能", "higher_better", 1, "開眼片脚立位", None, 1),
]

# item_name -> list of (condition, list-of-(threshold, score, comment))
# condition = dict(sex=?, age_band=?, pacemaker=?)  省略キーは NULL(全展開)
CRITERIA: dict[str, list[tuple[dict, list[tuple]]]] = {
    "BMI": [
        ({}, [
            (0, 1, "低体重(要栄養介入)"),
            (16.0, 2, "やや低体重"),
            (18.5, 5, "標準"),
            (25.0, 3, "やや過体重"),
            (30.0, 1, "肥満"),
        ]),
    ],
    "HbA1c": [
        ({}, [
            (0, 5, "良好"),
            (7.0, 4, "おおむね良好"),
            (8.0, 3, "やや高値"),
            (9.0, 2, "高値・要注意"),
            (10.0, 1, "要治療"),
        ]),
    ],
    "収縮期血圧": [
        ({}, [
            (0, 3, "低め"),
            (100, 5, "正常"),
            (130, 4, "正常高値"),
            (140, 3, "軽症高血圧"),
            (160, 2, "中等症高血圧"),
            (180, 1, "重症高血圧"),
        ]),
    ],
    "嚥下機能": [
        ({}, [
            (1, 1, "不良"),
            (2, 3, "やや不良"),
            (3, 5, "良好"),
        ]),
    ],
    "口腔機能": [
        ({}, [
            (1, 1, "不良"),
            (2, 3, "やや不良"),
            (3, 5, "良好"),
        ]),
    ],
    "聴力1000Hz": [
        ({}, [(0, 5, "正常"), (30, 4, "軽度低下"), (50, 3, "中等度低下"), (70, 1, "高度低下")]),
    ],
    "聴力4000Hz": [
        ({}, [(0, 5, "正常"), (30, 4, "軽度低下"), (50, 3, "中等度低下"), (70, 1, "高度低下")]),
    ],
    "骨密度(腰椎)": [
        ({}, [(0, 1, "骨粗鬆症"), (70, 2, "骨量減少"), (80, 4, "境界"), (90, 5, "正常")]),
    ],
    "骨密度(大腿骨)": [
        ({}, [(0, 1, "骨粗鬆症"), (70, 2, "骨量減少"), (80, 4, "境界"), (90, 5, "正常")]),
    ],
    "Barthel Index": [
        ({}, [(0, 1, "全介助"), (40, 2, "多くの介助"), (60, 3, "部分介助"), (85, 4, "軽度介助"), (100, 5, "自立")]),
    ],
    "FIM": [
        ({}, [(18, 1, "全介助"), (54, 2, "最大介助"), (90, 3, "中等度介助"), (108, 4, "軽度介助"), (126, 5, "自立")]),
    ],
    "mini-Cog": [
        ({}, [(0, 1, "認知機能低下疑い"), (3, 5, "正常範囲")]),
    ],
    "TUG": [
        ({}, [
            (0, 5, "良好"),
            (10.0, 4, "おおむね良好"),
            (13.5, 3, "転倒リスクあり"),
            (20.0, 2, "移動に介助検討"),
            (30.0, 1, "要介助"),
        ]),
    ],
    "FRT": [
        ({}, [(0, 1, "転倒リスク高"), (15, 3, "やや低下"), (25, 5, "良好")]),
    ],
    "握力": [
        ({"sex": "M"}, [(0, 1, "低下"), (26, 3, "やや低下"), (28, 5, "良好")]),
        ({"sex": "F"}, [(0, 1, "低下"), (16, 3, "やや低下"), (18, 5, "良好")]),
    ],
    "SMI": [
        # 性別・年代依存(サンプル)
        ({"sex": "M"}, [(0, 1, "サルコペニア域"), (6.5, 3, "境界"), (7.0, 5, "良好")]),
        ({"sex": "F"}, [(0, 1, "サルコペニア域"), (5.4, 3, "境界"), (5.7, 5, "良好")]),
        ({"sex": "M", "age_band": "80"}, [(0, 1, "サルコペニア域"), (6.2, 3, "境界"), (6.8, 5, "良好")]),
        ({"sex": "F", "age_band": "80"}, [(0, 1, "サルコペニア域"), (5.1, 3, "境界"), (5.5, 5, "良好")]),
    ],
    "喫食率": [
        ({}, [(0, 1, "摂取不良"), (5, 3, "半量程度"), (8, 4, "おおむね良好"), (10, 5, "全量摂取")]),
    ],
    "片脚立位時間": [
        ({}, [(0, 1, "転倒リスク高"), (5, 2, "低下"), (15, 3, "やや低下"), (30, 4, "良好"), (60, 5, "非常に良好")]),
    ],
}

# 取込列名のゆらぎ吸収(alias -> item_name)
ALIASES = {
    "身長(cm)": "身長",
    "体重(kg)": "体重",
    "HbA1c(%)": "HbA1c",
    "血圧(収縮期)": "収縮期血圧",
    "収縮期血圧(mmHg)": "収縮期血圧",
    "握力(kg)": "握力",
    "TUG(秒)": "TUG",
    "FRT(cm)": "FRT",
    "SMI(kg/m2)": "SMI",
    "筋肉量(SMI)": "SMI",
    "喫食率(割)": "喫食率",
    "バーセルインデックス": "Barthel Index",
    "Barthel": "Barthel Index",
    "mini-Cog合計点": "mini-Cog",
    "開眼片脚立位時間": "片脚立位時間",
}

SETTINGS = {
    "facility_name": "",
    "report_title": "状況報告書",
    "disclaimer": (
        "※本評価値の一部は当施設独自に設定した基準に基づくものを含みます。"
        "医学的診断を目的としたものではありません。"
    ),
    # 総合評価文言: 測定済み項目の★スコア平均で 1(最良)〜4 を選択(report.py)
    "summary_rank_1": (
        "評価項目において同年代と比較して75%〜100%、基準値もしくは基準値以上の数値が出ており、"
        "心身ともに良い状態です。相対評価が低い項目の改善と、現状を維持できるよう、"
        "日々の体調管理、リハビリを継続していきましょう。"
    ),
    "summary_rank_2": (
        "評価項目において同年代と比較して50%〜74%、基準値もしくは基準値以上の数値が出ています。"
        "今後の生活において、相対評価が低い項目を改善し、より良い心身状態になれるよう"
        "リハビリ、体調管理に努めていきましょう。"
    ),
    "summary_rank_3": (
        "評価項目において同年代と比較して25%〜49%、基準値もしくは基準値以上の数値が出ています。"
        "相対評価が低い項目において、今後の生活に今以上の支障が出ないよう改善に努めていきましょう。"
    ),
    "summary_rank_4": (
        "評価項目において同年代と比較して0%〜24%、基準値もしくは基準値以上の数値が出ています。"
        "現状からの改善に向け、今後1項目でも相対評価が上がるようリハビリ、体調管理に努めていきましょう。"
    ),
    "qualitative_note": (
        "定性値項目はコード値(1:不良〜3:良好 等)で記録し、評価コメントに表示文言を対応させています。"
    ),
}


def apply_seed(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) AS c FROM eval_items").fetchone()["c"]
    if existing == 0:
        _seed_items_and_criteria(conn)
    for k, v in SETTINGS.items():
        if repo.get_setting(conn, k) is None:
            repo.set_setting(conn, k, v)


def _seed_items_and_criteria(conn: sqlite3.Connection) -> None:
    name_to_id: dict[str, int] = {}
    for order, (name, unit, cat, direction, in_radar, src, derived, qual) in enumerate(ITEMS, start=1):
        item_id = repo.create_item(
            conn, name=name, unit=unit, category=cat, sort_order=order,
            direction=direction, in_radar=in_radar, source_column=src,
            derived_formula=derived, is_qualitative=qual,
        )
        name_to_id[name] = item_id

    for name, groups in CRITERIA.items():
        item_id = name_to_id[name]
        for cond, rows in groups:
            for threshold, score, comment in rows:
                repo.add_criterion(
                    conn, item_id,
                    cond.get("sex"), cond.get("age_band"), cond.get("pacemaker"),
                    threshold, score, comment,
                )

    for alias, item_name in ALIASES.items():
        if item_name in name_to_id:
            repo.add_alias(conn, alias, name_to_id[item_name])
