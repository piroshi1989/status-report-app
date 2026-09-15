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
LABEL_PAD = 18

# 今回=青の実線+塗りつぶし、前回=グレーの破線・塗りなし。前回は比較のための脇役なので
# 塗らずに背面へ置き、今回の形が読み取れる状態を保つ(白黒印刷でも線種で区別できる)。
CURR_COLOR = "#2b6cb0"
PREV_COLOR = "#9aa5b1"


@lru_cache(maxsize=1)
def _font() -> fm.FontProperties:
    path = config.font_path()
    if path.exists():
        fm.fontManager.addfont(str(path))
        prop = fm.FontProperties(fname=str(path))
        matplotlib.rcParams["font.family"] = prop.get_name()
        return prop
    return fm.FontProperties()


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

    if prev_line is not None:
        legend_font = font.copy()
        legend_font.set_size(8)
        # 円の外・図の左上の余白に置く。ここは項目名のぶんで既に確保されている領域なので
        # 画像の縦横比が変わらない(tests/test_radar.py で担保)。
        ax.legend(
            handles=[curr_line, prev_line], loc="upper left",
            bbox_to_anchor=(-0.02, 1.04), prop=legend_font,
            frameon=False, handlelength=2.2, borderaxespad=0.0,
        )

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
    fig.tight_layout(pad=1.2)
    fig.savefig(buf, format="png", bbox_inches="tight", transparent=False)
    plt.close(fig)
    return buf.getvalue()
