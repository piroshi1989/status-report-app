"""ReportLab による状況報告書 PDF 生成(個別・一括)."""

from __future__ import annotations

import io
from functools import lru_cache
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .. import config
from ..domain import measured_display
from .radar import render_radar
from .report import ReportData

FONT_NAME = "IPAexGothic"

# 本文全体が A4 1 ページに収まるよう調整した値(tests/test_pdf_layout.py で担保)。
RADAR_SIZE_MM = 80       # レーダーの一辺(mm)
TABLE_FONT_SIZE = 8      # 詳細表の文字サイズ(pt)
TABLE_CELL_PADDING = 1   # 詳細表セルの上下余白(pt)
TABLE_WIDTH_MM = 178     # 詳細表の全幅(本文幅 180mm)

# 評価コメントの長さで表の高さが変わるため、1 ページに収まるまで表の文字とレーダーを
# 段階的に小さくする(大きい順に試す)。(表の文字サイズ pt, レーダーの一辺 mm)
FIT_STEPS = [(8.0, 80), (7.5, 78), (7.0, 76), (6.5, 72), (6.0, 68), (6.0, 60)]

# コメント以外の列幅(mm、8pt 時に 1 行に収まる最小幅の実測値に余裕を足したもの)。
# 区分/評価項目/前回/今回/単位/相対評価/★表記。残りの幅をすべてコメント列に充てる。
# 詰めるとセルが 2 行になり表の高さが倍増する(test_pdf_table_cells_fit_on_one_line)。
BASE_COL_WIDTHS_MM = [20, 25, 17, 24, 14, 17, 20]
_CELL_HPAD_MM = 12 / 72 * 25.4   # Table 既定の左右パディング合計(12pt)。文字幅と違い縮まない

_CAT_COLORS = {
    # 評価基準 Excel 最終版の区分
    "看護": colors.HexColor("#f0f7ee"),
    "体力": colors.HexColor("#eef2f7"),
    "身体計測": colors.HexColor("#eef2f7"),
    "栄養": colors.HexColor("#fff4e6"),
    "検査値": colors.HexColor("#f0f7ee"),
    "口腔・嚥下": colors.HexColor("#fdeef3"),
    "感覚機能": colors.HexColor("#eef7f6"),
    "身体機能": colors.HexColor("#eef2f7"),
    "生活機能": colors.HexColor("#f4eefa"),
    "認知": colors.HexColor("#f7f3ea"),
}


@lru_cache(maxsize=1)
def _register_font() -> str:
    path = config.font_path()
    if path.exists():
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, str(path)))
            return FONT_NAME
        except Exception:
            pass
    return "Helvetica"


def _styles(font: str, table_font_size: float = TABLE_FONT_SIZE):
    return {
        "title": ParagraphStyle("title", fontName=font, fontSize=15, leading=19, spaceAfter=2),
        "meta": ParagraphStyle("meta", fontName=font, fontSize=9, leading=12, textColor=colors.HexColor("#555")),
        "h2": ParagraphStyle("h2", fontName=font, fontSize=11, leading=14, spaceBefore=6, spaceAfter=3),
        "cell": ParagraphStyle("cell", fontName=font, fontSize=table_font_size,
                               leading=table_font_size + 2.5),
        "small": ParagraphStyle("small", fontName=font, fontSize=7.5, leading=10, textColor=colors.HexColor("#666")),
        "summary": ParagraphStyle("summary", fontName=font, fontSize=9.5, leading=13),
    }


def _fmt_value(line) -> str:
    if not line.measured:
        return "未測定"
    return measured_display(line.raw_text, line.value) or "-"


def col_widths(table_font_size: float = TABLE_FONT_SIZE) -> list[float]:
    """詳細表の列幅(pt)。文字サイズに比例して固定列を詰め、余りをコメント列に回す."""
    scale = table_font_size / TABLE_FONT_SIZE
    fixed = [(w - _CELL_HPAD_MM) * scale + _CELL_HPAD_MM for w in BASE_COL_WIDTHS_MM]
    return [w * mm for w in fixed] + [(TABLE_WIDTH_MM - sum(fixed)) * mm]


def build_flowables(
    data: ReportData,
    title: str = "状況報告書",
    table_font_size: float = TABLE_FONT_SIZE,
    radar_size_mm: float = RADAR_SIZE_MM,
    radar_png: bytes | None = None,
) -> list:
    font = _register_font()
    st = _styles(font, table_font_size)
    flow: list = []

    p = data.patient
    age_txt = f"{data.age}歳" if data.age is not None else "―"
    sex_txt = {"M": "男", "F": "女"}.get(p["sex"], "")
    measured_on = data.session["measured_on"] or ""

    flow.append(Paragraph(title, st["title"]))
    meta = f"氏名: {p['name']}　（{sex_txt} {age_txt}）　利用者コード: {p['code']}　評価日: {measured_on}"
    if data.session["session_no"]:
        meta += f"　第{data.session['session_no']}回"
    flow.append(Paragraph(meta, st["meta"]))
    flow.append(Spacer(1, 4 * mm))

    # --- 詳細表 ---
    header = ["区分", "評価項目", "前回", "今回", "単位", "相対評価", "★表記", "コメント"]
    table_data = [[Paragraph(h, st["cell"]) for h in header]]
    row_bgs = []
    for i, line in enumerate(data.lines, start=1):
        # 未計測でも評価が付く項目(HbA1c=★5 等)は評価を出す
        score_txt = "―" if line.score is None else str(line.score)
        table_data.append([
            Paragraph(line.category, st["cell"]),
            Paragraph(line.name, st["cell"]),
            Paragraph(line.prev_text, st["cell"]),
            Paragraph(_fmt_value(line), st["cell"]),
            Paragraph(line.unit, st["cell"]),
            Paragraph(score_txt, st["cell"]),
            Paragraph(line.stars, st["cell"]),
            Paragraph(line.comment, st["cell"]),
        ])
        row_bgs.append((i, _CAT_COLORS.get(line.category, colors.white)))

    tbl = Table(table_data, colWidths=col_widths(table_font_size), repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), table_font_size),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b6cb0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (6, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), TABLE_CELL_PADDING),
        ("BOTTOMPADDING", (0, 0), (-1, -1), TABLE_CELL_PADDING),
    ]
    for idx, bg in row_bgs:
        style.append(("BACKGROUND", (0, idx), (-1, idx), bg))
    tbl.setStyle(TableStyle(style))
    flow.append(tbl)
    flow.append(Spacer(1, 5 * mm))

    # --- レーダーチャート(左)と総合評価(右)を横に並べる ---
    radar_cell: list = []
    if data.radar_labels:
        png = radar_png or _radar_png(data)
        radar_cell = [
            Paragraph("■ 測定結果 相対グラフ", st["h2"]),
            Image(io.BytesIO(png), width=radar_size_mm * mm, height=radar_size_mm * mm),
        ]
    summary_cell: list = []
    if data.summary:
        summary_cell = [Paragraph("■ 総合評価", st["h2"]), Paragraph(data.summary, st["summary"])]
    if radar_cell and summary_cell:
        left_w = (radar_size_mm + 4) * mm
        bottom = Table([[radar_cell, summary_cell]], colWidths=[left_w, TABLE_WIDTH_MM * mm - left_w])
        bottom.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        flow.append(bottom)
    else:
        flow.extend(radar_cell or summary_cell)
    flow.append(Spacer(1, 3 * mm))

    # --- 注意書き ---
    if data.disclaimer:
        flow.append(Paragraph(data.disclaimer, st["small"]))

    return flow


def _new_doc(buf) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title="状況報告書",
    )


def _radar_png(data: ReportData) -> bytes:
    return render_radar(data.radar_labels, data.radar_scores, prev_scores=data.radar_prev_scores)


def _flow_height(flow: list, width: float, height: float) -> float:
    total = 0.0
    for f in flow:
        _w, h = f.wrap(width, height)
        total += h + f.getSpaceBefore() + f.getSpaceAfter()
    return total


def fitted_flowables(data: ReportData, title: str = "状況報告書") -> tuple[list, float]:
    """A4 1 ページに収まる最大の文字サイズで組んだ本文と、その文字サイズを返す.

    どの段階でも収まらない場合は最小の段階で組む(2 ページ目に溢れる)。
    """
    doc = _new_doc(io.BytesIO())
    pad = 12  # Frame 既定の上下・左右パディング合計(pt)
    width, height = doc.width - pad, doc.height - pad
    png = _radar_png(data) if data.radar_labels else None
    for size, radar_mm in FIT_STEPS:
        flow = build_flowables(data, title, table_font_size=size, radar_size_mm=radar_mm, radar_png=png)
        if _flow_height(flow, width, height) <= height:
            return flow, size
    return flow, size


def render_single(data: ReportData, title: str = "状況報告書") -> bytes:
    buf = io.BytesIO()
    doc = _new_doc(buf)
    doc.build(fitted_flowables(data, title)[0])
    return buf.getvalue()


def render_batch(datas: Iterable[ReportData], title: str = "状況報告書") -> bytes:
    from reportlab.platypus import PageBreak

    buf = io.BytesIO()
    doc = _new_doc(buf)
    flow: list = []
    first = True
    for data in datas:
        if not first:
            flow.append(PageBreak())
        flow.extend(fitted_flowables(data, title)[0])
        first = False
    if not flow:
        flow.append(Paragraph("対象データがありません", _styles(_register_font())["meta"]))
    doc.build(flow)
    return buf.getvalue()
