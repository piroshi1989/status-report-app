"""レーダーチャートの描画に関するテスト."""

from __future__ import annotations

import numpy as np

from app.services.radar import build_figure

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
