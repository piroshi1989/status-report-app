"""matplotlib によるレーダーチャート生成(画面・PDF 共通)."""

from __future__ import annotations

import io
from functools import lru_cache

import matplotlib

matplotlib.use("Agg")  # GUI 非依存
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .. import config  # noqa: E402

# 項目名と円の間隔(pt)。既定の 4pt だと「骨密度(腰椎)」等の長いラベルが円に食い込む。
# 重ならない最小値は 16pt(実測)で、ラベルが増減しても耐えるよう少し余裕を持たせている。
# 大きくするほど相対的に円が小さくなる(tests/test_radar.py で重なりを担保)。
LABEL_PAD = 20

# 今回=青の実線+塗りつぶし、前回=グレーの破線・塗りなし。前回は比較のための脇役なので
# 塗らずに背面へ置き、今回の形が読み取れる状態を保つ(白黒印刷でも線種で区別できる)。
CURR_COLOR = "#2b6cb0"
PREV_COLOR = "#9aa5b1"

# 凡例の置き場所の候補(図全体の四隅。左上から順に試す。座標は図全体の割合)。項目数や項目名で
# 空いている隅が変わるので、項目名に重ならない最初の隅を選ぶ。円の枠の隅は項目名で埋まるので
# 使えない。図の内側に置くので画像の縦横比も変わらない(tests/test_radar.py で担保)。
LEGEND_CORNERS = [
    ("upper left", (0.01, 0.99)),
    ("upper right", (0.99, 0.99)),
    ("lower left", (0.01, 0.01)),
    ("lower right", (0.99, 0.01)),
]
LEGEND_MARGIN_PX = 4  # 項目名との最低限の間隔


@lru_cache(maxsize=1)
def _font() -> fm.FontProperties:
    path = config.font_path()
    if path.exists():
        fm.fontManager.addfont(str(path))
        prop = fm.FontProperties(fname=str(path))
        matplotlib.rcParams["font.family"] = prop.get_name()
        return prop
    return fm.FontProperties()


def _place_legend(fig, ax, handles: list, font: fm.FontProperties) -> None:
    """凡例を項目名に重ならない隅に置く。どの隅も重なるなら重なりが最小の隅にする."""
    legend_font = font.copy()
    legend_font.set_size(8)
    fig.draw_without_rendering()  # 項目名の最終位置を確定させる
    label_boxes = [lb.get_window_extent() for lb in ax.get_xticklabels()]

    def place(loc, anchor):
        return ax.legend(
            handles=handles, loc=loc, bbox_to_anchor=anchor, bbox_transform=fig.transFigure,
            prop=legend_font, frameon=False, handlelength=2.2, borderaxespad=0.0,
        )

    def overlap_area(legend) -> float:
        box = legend.get_window_extent().padded(LEGEND_MARGIN_PX)
        total = 0.0
        for lb in label_boxes:
            w = min(box.x1, lb.x1) - max(box.x0, lb.x0)
            h = min(box.y1, lb.y1) - max(box.y0, lb.y0)
            if w > 0 and h > 0:
                total += w * h
        return total

    areas = []
    for loc, anchor in LEGEND_CORNERS:
        area = overlap_area(place(loc, anchor))
        if area == 0:
            return
        areas.append((area, loc, anchor))
    _area, loc, anchor = min(areas, key=lambda a: a[0])
    place(loc, anchor)


def build_figure(
    labels: list[str],
    scores: list[int],
    max_score: int = 5,
    prev_scores: list[int] | None = None,
):
    """レーダーチャートの Figure/Axes を組み立てて返す(描画位置の検証用に分離).

    ``prev_scores`` を渡すと前回セッションの系列を重ねる。初回セッション等で
    比較対象がないときは None を渡すこと(従来どおり 1 本だけ・凡例なしになる)。
    """
    font = _font()
    if not labels:
        labels = ["データなし"]
        scores = [0]

    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    vals = list(scores)
    prev_vals = list(prev_scores) if prev_scores else None
    # 閉じる
    angles += angles[:1]
    vals += vals[:1]
    if prev_vals:
        prev_vals += prev_vals[:1]

    fig, ax = plt.subplots(figsize=(5.2, 5.2), subplot_kw=dict(polar=True), dpi=130)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    ax.set_ylim(0, max_score)
    ax.set_yticks(range(1, max_score + 1))
    ax.set_yticklabels([str(i) for i in range(1, max_score + 1)], fontproperties=font, fontsize=8, color="#888")
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontproperties=font, fontsize=9)
    ax.tick_params(axis="x", pad=LABEL_PAD)

    prev_line = None
    if prev_vals:
        # zorder は既定(2)のわずかに下。交差箇所で今回の線が上に出る。
        (prev_line,) = ax.plot(angles, prev_vals, color=PREV_COLOR, linewidth=1.6,
                               linestyle="--", label="前回", zorder=1.9)
    (curr_line,) = ax.plot(angles, vals, color=CURR_COLOR, linewidth=2, label="今回")
    ax.fill(angles, vals, color=CURR_COLOR, alpha=0.25)
    ax.grid(color="#cccccc", linewidth=0.6)
    ax.spines["polar"].set_color("#cccccc")

    # 凡例は最終の配置で項目名との重なりを見るので、レイアウト確定後に置く
    fig.tight_layout(pad=1.2)
    if prev_line is not None:
        _place_legend(fig, ax, [curr_line, prev_line], font)

    return fig, ax


def render_radar(
    labels: list[str],
    scores: list[int],
    max_score: int = 5,
    prev_scores: list[int] | None = None,
) -> bytes:
    """レーダーチャートを PNG バイト列で返す."""
    fig, _ax = build_figure(labels, scores, max_score, prev_scores)
    buf = io.BytesIO()
    # 余白を切り抜かない(tight_layout で項目名は図に収まっている)。切り抜くと縦横比が崩れ、
    # 正方形の枠に流し込む PDF で円が歪む。
    fig.savefig(buf, format="png", transparent=False)
    plt.close(fig)
    return buf.getvalue()
