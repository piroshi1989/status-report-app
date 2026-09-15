"""レーダーチャートの描画に関するテスト."""

from __future__ import annotations

import struct

import numpy as np

from app.services.radar import build_figure, render_radar

# 実運用のレーダー項目(in_radar=1 の既定項目)
LABELS = [
    "BMI", "HbA1c", "収縮期血圧", "嚥下機能", "口腔機能", "骨密度(腰椎)", "骨密度(大腿骨)",
    "Barthel Index", "FIM", "mini-Cog", "TUG", "FRT", "握力", "SMI", "喫食率", "片脚立位時間",
]


def _center_and_radius(ax, max_score=5):
    """描画座標系での円の中心と半径."""
    cx, cy = ax.transData.transform((0, 0))
    pts = [ax.transData.transform((t, max_score))
           for t in np.linspace(0, 2 * np.pi, 16, endpoint=False)]
    return cx, cy, max(float(np.hypot(px - cx, py - cy)) for px, py in pts)


def test_labels_do_not_overlap_the_chart_circle():
    """項目名がグラフの円に食い込まないこと."""
    fig, ax = build_figure(LABELS, [3] * len(LABELS))
    fig.canvas.draw()
    cx, cy, r = _center_and_radius(ax)

    overlapping = []
    for label in ax.get_xticklabels():
        bb = label.get_window_extent()
        # 中心から矩形までの最短距離
        dx = max(bb.x0 - cx, 0.0, cx - bb.x1)
        dy = max(bb.y0 - cy, 0.0, cy - bb.y1)
        if float(np.hypot(dx, dy)) < r:
            overlapping.append((label.get_text(), round(float(np.hypot(dx, dy)) - r, 1)))

    assert overlapping == [], f"円に食い込んでいるラベル(不足px): {overlapping}"


def _png_aspect(png: bytes) -> float:
    """PNG バイト列の 幅/高さ。PDF は正方形の枠に流し込むので 1 から離れるほど円が歪む."""
    w, h = struct.unpack(">II", png[16:24])
    return w / h


def _lines_by_label(ax) -> dict:
    return {ln.get_label(): ln for ln in ax.lines}


def test_previous_scores_are_drawn_as_a_second_series():
    """前回スコアを渡すと、今回とは別の系列として描かれること."""
    curr = [3] * len(LABELS)
    prev = [5] * len(LABELS)
    fig, ax = build_figure(LABELS, curr, prev_scores=prev)

    lines = _lines_by_label(ax)
    assert set(lines) == {"今回", "前回"}
    # 閉じるために先頭を末尾へ足しているぶんを除いて比較
    assert list(lines["前回"].get_ydata())[:-1] == prev
    assert list(lines["今回"].get_ydata())[:-1] == curr


def test_previous_series_is_a_dashed_grey_line_behind_the_current_one():
    """前回は塗りつぶさないグレーの破線で、今回より背面にあること."""
    fig, ax = build_figure(LABELS, [3] * len(LABELS), prev_scores=[5] * len(LABELS))

    prev_line, curr_line = _lines_by_label(ax)["前回"], _lines_by_label(ax)["今回"]
    assert prev_line.get_linestyle() != "-", "前回は破線で今回と区別する"
    assert prev_line.get_color() != curr_line.get_color()
    assert prev_line.get_zorder() < curr_line.get_zorder()
    # 塗りは今回のぶん 1 つだけ(前回を塗ると今回が読み取れなくなる)
    assert len(ax.patches) == 1


def test_legend_says_which_series_is_which():
    fig, ax = build_figure(LABELS, [3] * len(LABELS), prev_scores=[5] * len(LABELS))

    legend = ax.get_legend()
    assert legend is not None, "どちらが前回か分かる凡例が要る"
    assert [t.get_text() for t in legend.get_texts()] == ["今回", "前回"]


def test_legend_does_not_overlap_the_item_labels():
    """凡例は円の外・項目名の隙間に置く(項目名に重ねない)."""
    fig, ax = build_figure(LABELS, [3] * len(LABELS), prev_scores=[5] * len(LABELS))
    fig.canvas.draw()

    legend_bb = ax.get_legend().get_window_extent()
    hit = [lb.get_text() for lb in ax.get_xticklabels()
           if lb.get_window_extent().overlaps(legend_bb)]

    assert hit == [], f"凡例と重なっている項目名: {hit}"


def test_chart_is_unchanged_when_there_is_no_previous_session():
    """初回セッション(前回なし)は従来どおり 1 本だけ・凡例なし."""
    fig, ax = build_figure(LABELS, [3] * len(LABELS))

    assert len(ax.lines) == 1
    assert ax.get_legend() is None


def test_previous_series_does_not_distort_the_image():
    """凡例を足しても画像の縦横比が変わらないこと.

    PDF はこの PNG を 82mm 角の枠に流し込むため、凡例で図が横に伸びると円が潰れ、
    A4 1 ページに収める前提(tests/test_pdf_layout.py)も崩れる.
    """
    scores = [3] * len(LABELS)
    without = _png_aspect(render_radar(LABELS, scores))
    with_prev = _png_aspect(render_radar(LABELS, scores, prev_scores=[5] * len(LABELS)))

    assert abs(with_prev - without) <= 0.03, f"縦横比が {without:.3f} → {with_prev:.3f} に変化"


def test_labels_still_clear_the_circle_with_two_series():
    """2 本描いても項目名が円に食い込まないこと."""
    fig, ax = build_figure(LABELS, [3] * len(LABELS), prev_scores=[5] * len(LABELS))
    fig.canvas.draw()
    cx, cy, r = _center_and_radius(ax)

    overlapping = []
    for label in ax.get_xticklabels():
        bb = label.get_window_extent()
        dx = max(bb.x0 - cx, 0.0, cx - bb.x1)
        dy = max(bb.y0 - cy, 0.0, cy - bb.y1)
        if float(np.hypot(dx, dy)) < r:
            overlapping.append(label.get_text())

    assert overlapping == [], f"円に食い込んでいるラベル: {overlapping}"
