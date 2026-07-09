"""評価エンジン: 基準解決 → 1〜5判定 → コメント選択.

設計:
- eval_criteria の 1 行 = ある条件(sex/age_band/pacemaker)下での「区間下限値
  ``threshold``」に対応する ``score`` とコメント。
- 同一項目には複数の条件セットが存在しうる(例: 男性・70代 / 全展開)。
  患者の属性に**適合し、かつ最も具体的**な条件セットを選ぶ(基準解決)。
- 判定は方向(higher/lower/range/qualitative)に依らず一様:
  条件セットの行を threshold 昇順に並べ、``threshold <= value`` を満たす最大の
  行の score/comment を採用する(値が最小 threshold 未満なら最小行)。
  各行の threshold が「その score になる区間の下限」を表すため、この一様アルゴリズムで
  higher_better / lower_better / range / qualitative すべてを扱える。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class CriterionRow:
    sex: Optional[str]
    age_band: Optional[str]
    pacemaker: Optional[int]
    threshold: float
    score: int
    comment: Optional[str] = None


@dataclass(frozen=True)
class EvalResult:
    measured: bool
    score: Optional[int]
    comment: Optional[str]
    # どの条件セットで判定したか(デバッグ・帳票脚注用)
    resolved_condition: Optional[tuple] = None


ConditionKey = tuple  # (sex, age_band, pacemaker)


def _compatible(key: ConditionKey, sex, age_band, pacemaker) -> bool:
    k_sex, k_age, k_pm = key
    if k_sex is not None and k_sex != sex:
        return False
    if k_age is not None and k_age != age_band:
        return False
    if k_pm is not None and pacemaker is not None and int(k_pm) != int(pacemaker):
        return False
    return True


def _specificity(key: ConditionKey) -> tuple:
    """具体性スコア。非NULL条件が多いほど、性別+年代指定を優先."""
    k_sex, k_age, k_pm = key
    n = sum(1 for c in key if c is not None)
    return (n, k_sex is not None, k_age is not None, k_pm is not None)


def group_by_condition(rows: Iterable[CriterionRow]) -> dict[ConditionKey, list[CriterionRow]]:
    groups: dict[ConditionKey, list[CriterionRow]] = {}
    for r in rows:
        pm = None if r.pacemaker is None else int(r.pacemaker)
        key = (r.sex, r.age_band, pm)
        groups.setdefault(key, []).append(r)
    return groups


def resolve_group(
    rows: Iterable[CriterionRow], sex, age_band, pacemaker
) -> tuple[Optional[ConditionKey], list[CriterionRow]]:
    """患者属性に適合し最も具体的な条件セットとその閾値行を返す."""
    groups = group_by_condition(rows)
    compatible = [k for k in groups if _compatible(k, sex, age_band, pacemaker)]
    if not compatible:
        return None, []
    best = max(compatible, key=_specificity)
    ordered = sorted(groups[best], key=lambda r: r.threshold)
    return best, ordered


def score_from_group(group_rows: list[CriterionRow], value: float) -> Optional[CriterionRow]:
    """threshold 昇順の行から value が属する区間の行を返す."""
    if not group_rows:
        return None
    chosen = group_rows[0]
    for r in group_rows:
        if value >= r.threshold:
            chosen = r
        else:
            break
    return chosen


def evaluate(
    rows: Iterable[CriterionRow],
    value: Optional[float],
    sex: Optional[str] = None,
    age_band: Optional[str] = None,
    pacemaker: Optional[int] = None,
) -> EvalResult:
    """測定値 ``value`` を評価。value が None(未測定)は measured=False."""
    if value is None:
        return EvalResult(measured=False, score=None, comment=None)
    key, group = resolve_group(rows, sex, age_band, pacemaker)
    if not group:
        return EvalResult(measured=True, score=None, comment=None, resolved_condition=key)
    row = score_from_group(group, float(value))
    if row is None:
        return EvalResult(measured=True, score=None, comment=None, resolved_condition=key)
    return EvalResult(measured=True, score=row.score, comment=row.comment, resolved_condition=key)
