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
from .radar import render_radar
from .report import ReportData

FONT_NAME = "IPAexGothic"

_CAT_COLORS = {
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


def _styles(font: str):
    return {
        "title": ParagraphStyle("title", fontName=font, fontSize=15, leading=19, spaceAfter=2),
        "meta": ParagraphStyle("meta", fontName=font, fontSize=9, leading=12, textColor=colors.HexColor("#555")),
        "h2": ParagraphStyle("h2", fontName=font, fontSize=11, leading=14, spaceBefore=6, spaceAfter=3),
        "cell": ParagraphStyle("cell", fontName=font, fontSize=8.5, leading=11),
        "small": ParagraphStyle("small", fontName=font, fontSize=7.5, leading=10, textColor=colors.HexColor("#666")),
        "summary": ParagraphStyle("summary", fontName=font, fontSize=9.5, leading=13),
    }


def _fmt_value(line) -> str:
    if not line.measured:
        return "未測定"
    if line.raw_text and not line.raw_text.startswith("派生:"):
        return line.raw_text
    if line.value is None:
        return "-"
    v = line.value
    return str(int(v)) if float(v).is_integer() else str(v)


def build_flowables(data: ReportData, title: str = "状況報告書") -> list:
    font = _register_font()
    st = _styles(font)
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
    header = ["区分", "評価項目", "実測値", "単位", "相対評価", "★表記", "コメント"]
    table_data = [[Paragraph(h, st["cell"]) for h in header]]
    row_bgs = []
    for i, line in enumerate(data.lines, start=1):
        score_txt = "―" if not line.measured else str(line.score if line.score is not None else "―")
        table_data.append([
            Paragraph(line.category, st["cell"]),
            Paragraph(line.name, st["cell"]),
            Paragraph(_fmt_value(line), st["cell"]),
            Paragraph(line.unit, st["cell"]),
            Paragraph(score_txt, st["cell"]),
            Paragraph(line.stars, st["cell"]),
            Paragraph(line.comment, st["cell"]),
        ])
        row_bgs.append((i, _CAT_COLORS.get(line.category, colors.white)))

    col_widths = [20 * mm, 30 * mm, 20 * mm, 14 * mm, 18 * mm, 24 * mm, 40 * mm]
    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b6cb0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (5, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for idx, bg in row_bgs:
        style.append(("BACKGROUND", (0, idx), (-1, idx), bg))
    tbl.setStyle(TableStyle(style))
    flow.append(tbl)
    flow.append(Spacer(1, 5 * mm))

    # --- レーダーチャート ---
    labels = data.radar_labels
    scores = data.radar_scores
    if labels:
        png = render_radar(labels, scores)
        img = Image(io.BytesIO(png), width=95 * mm, height=95 * mm)
        img.hAlign = "CENTER"
        flow.append(Paragraph("■ 測定結果 相対グラフ", st["h2"]))
        flow.append(img)
        flow.append(Spacer(1, 3 * mm))

    # --- 総合評価 ---
    if data.summary:
        flow.append(Paragraph("■ 総合評価", st["h2"]))
        flow.append(Paragraph(data.summary, st["summary"]))
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


def render_single(data: ReportData, title: str = "状況報告書") -> bytes:
    buf = io.BytesIO()
    doc = _new_doc(buf)
    doc.build(build_flowables(data, title))
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
        flow.extend(build_flowables(data, title))
        first = False
    if not flow:
        flow.append(Paragraph("対象データがありません", _styles(_register_font())["meta"]))
    doc.build(flow)
    return buf.getvalue()
