"""レーダーチャートの描画に関するテスト."""

from __future__ import annotations

import struct

import numpy as np
import pytest

from app import db, repo
from app.services.radar import build_figure, render_radar
from app.services.report import build_report

# 実運用のレーダー項目(帳票の 18 項目)
LABELS = [
    "HbA1c", "収縮期血圧", "嚥下機能", "口腔機能", "聴力1000Hz", "聴力4000Hz",
    "骨密度(大腿骨)", "骨密度(腰椎)", "Barthel Index", "FIM", "mini-Cog", "TUG", "FRT",
    "握力", "SMI", "BMI", "体重増減率", "喫食率",
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


def _labels_hit_by_legend(labels: list[str]) -> list[str]:
    n = len(labels)
    fig, ax = build_figure(labels, [3] * n, prev_scores=[5] * n)
    fig.canvas.draw()
    legend_bb = ax.get_legend().get_window_extent()
    return [lb.get_text() for lb in ax.get_xticklabels()
            if lb.get_window_extent().overlaps(legend_bb)]


@pytest.mark.parametrize("pacemaker", [0, 1], ids=["SMI", "下腿周囲長"])
def test_legend_does_not_overlap_labels_on_the_actual_report(tmp_env, pacemaker):
    """帳票の項目で、凡例が項目名に重ならないこと(項目構成が変わっても追従する)."""
    db.init_db(seed=True)
    with db.get_conn() as conn:
        pid = repo.create_patient(conn, code="R", name="r", sex="M", birth_date="1945-01-01",
                                  pacemaker=pacemaker)
        sid = repo.create_session(conn, 1, "2026-07-01", "a.xlsx")
        labels = build_report(conn, pid, sid).radar_labels

    assert len(labels) == 18
    assert _labels_hit_by_legend(labels) == []


@pytest.mark.parametrize(
    "labels",
    [
        pytest.param([("体重減少率" if x == "体重増減率" else x) for x in LABELS], id="施設で改名"),
        pytest.param(LABELS + ["施設独自項目A", "施設独自項目B"], id="独自項目を追加"),
        pytest.param(LABELS[:16], id="項目が減った場合"),
    ],
)
def test_legend_moves_away_from_labels_when_items_change(labels):
    """項目名や項目数が変わって凡例の場所に項目名が来ても、重ならない場所へ逃げること."""
    assert _labels_hit_by_legend(labels) == []


def test_legend_stays_outside_the_chart_circle():
    fig, ax = build_figure(LABELS, [5] * len(LABELS), prev_scores=[5] * len(LABELS))
    fig.canvas.draw()
    cx, cy, r = _center_and_radius(ax)

    bb = ax.get_legend().get_window_extent()
    dx = max(bb.x0 - cx, 0.0, cx - bb.x1)
    dy = max(bb.y0 - cy, 0.0, cy - bb.y1)
    assert float(np.hypot(dx, dy)) >= r


def test_chart_is_unchanged_when_there_is_no_previous_session():
    """初回セッション(前回なし)は従来どおり 1 本だけ・凡例なし."""
    fig, ax = build_figure(LABELS, [3] * len(LABELS))

    assert len(ax.lines) == 1
    assert ax.get_legend() is None


def test_image_is_square_so_the_pdf_does_not_distort_the_circle():
    """PDF は画像を正方形の枠に流し込むので、画像も正方形でないと円が歪む."""
    n = len(LABELS)
    assert _png_aspect(render_radar(LABELS, [3] * n)) == 1
    assert _png_aspect(render_radar(LABELS, [3] * n, prev_scores=[5] * n)) == 1


@pytest.mark.parametrize("long_label", ["体重増減率", "施設独自の長い評価項目の名前"])
def test_labels_and_legend_are_not_cut_off_by_the_image_edge(long_label):
    labels = LABELS[:-2] + [long_label, LABELS[-1]]
    n = len(labels)
    fig, ax = build_figure(labels, [3] * n, prev_scores=[5] * n)
    fig.canvas.draw()
    page = fig.bbox

    boxes = [lb.get_window_extent() for lb in ax.get_xticklabels()]
    boxes.append(ax.get_legend().get_window_extent())
    cut = [b for b in boxes
           if b.x0 < page.x0 or b.y0 < page.y0 or b.x1 > page.x1 or b.y1 > page.y1]

    assert cut == []


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
