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


@lru_cache(maxsize=1)
def _font() -> fm.FontProperties:
    path = config.font_path()
    if path.exists():
        fm.fontManager.addfont(str(path))
        prop = fm.FontProperties(fname=str(path))
        matplotlib.rcParams["font.family"] = prop.get_name()
        return prop
    return fm.FontProperties()


def build_figure(labels: list[str], scores: list[int], max_score: int = 5):
    """レーダーチャートの Figure/Axes を組み立てて返す(描画位置の検証用に分離)."""
    font = _font()
    if not labels:
        labels = ["データなし"]
        scores = [0]

    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    vals = list(scores)
    # 閉じる
    angles += angles[:1]
    vals += vals[:1]

    fig, ax = plt.subplots(figsize=(5.2, 5.2), subplot_kw=dict(polar=True), dpi=130)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    ax.set_ylim(0, max_score)
    ax.set_yticks(range(1, max_score + 1))
    ax.set_yticklabels([str(i) for i in range(1, max_score + 1)], fontproperties=font, fontsize=8, color="#888")
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontproperties=font, fontsize=9)
    ax.tick_params(axis="x", pad=LABEL_PAD)

    ax.plot(angles, vals, color="#2b6cb0", linewidth=2)
    ax.fill(angles, vals, color="#2b6cb0", alpha=0.25)
    ax.grid(color="#cccccc", linewidth=0.6)
    ax.spines["polar"].set_color("#cccccc")

    return fig, ax


def render_radar(labels: list[str], scores: list[int], max_score: int = 5) -> bytes:
    """レーダーチャートを PNG バイト列で返す."""
    fig, _ax = build_figure(labels, scores, max_score)
    buf = io.BytesIO()
    fig.tight_layout(pad=1.2)
    fig.savefig(buf, format="png", bbox_inches="tight", transparent=False)
    plt.close(fig)
    return buf.getvalue()
