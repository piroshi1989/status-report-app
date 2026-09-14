"""評価エンジンの単体テスト."""

from app.services.evaluation import CriterionRow, evaluate, resolve_group
from app.domain import age_to_band, calc_age, stars, weight_change_display, weight_change_ratio


def C(threshold, score, sex=None, age=None, pm=None, comment=None):
    return CriterionRow(sex=sex, age_band=age, pacemaker=pm, threshold=threshold, score=score, comment=comment)


# --- higher_better ---------------------------------------------------------

def test_higher_better_scoring():
    rows = [
        C(0, 1, comment="要改善"),
        C(10, 2),
        C(20, 3),
        C(30, 4),
        C(40, 5, comment="良好"),
    ]
    assert evaluate(rows, 5).score == 1
    assert evaluate(rows, 10).score == 2
    assert evaluate(rows, 25).score == 3
    assert evaluate(rows, 45).score == 5
    assert evaluate(rows, 40).comment == "良好"


def test_below_minimum_takes_lowest_interval():
    rows = [C(10, 1), C(20, 3), C(30, 5)]
    # 最小 threshold 未満でも最小区間(score1)に落ちる
    assert evaluate(rows, 0).score == 1


# --- lower_better ----------------------------------------------------------

def test_lower_better_scoring():
    # 値が小さいほど良い: 区間下限に score を割り当てる
    rows = [
        C(0, 5, comment="正常"),
        C(7.0, 4),
        C(8.0, 3),
        C(9.0, 2),
        C(10.0, 1, comment="要治療"),
    ]
    assert evaluate(rows, 6.5).score == 5
    assert evaluate(rows, 7.5).score == 4
    assert evaluate(rows, 10.5).score == 1
    assert evaluate(rows, 10.5).comment == "要治療"


# --- range (範囲内が最良) --------------------------------------------------

def test_range_scoring():
    # BMI 的な山形。18.5〜25 が最良。
    rows = [
        C(0, 2),
        C(18.5, 5),
        C(25.0, 3),
        C(30.0, 1),
    ]
    assert evaluate(rows, 16).score == 2
    assert evaluate(rows, 22).score == 5
    assert evaluate(rows, 27).score == 3
    assert evaluate(rows, 35).score == 1


# --- 未測定 ---------------------------------------------------------------

def test_not_measured():
    rows = [C(0, 1), C(10, 5)]
    r = evaluate(rows, None)
    assert r.measured is False
    assert r.score is None


# --- 基準解決: 具体性の優先 ------------------------------------------------

def test_resolution_prefers_specific_condition():
    rows = [
        # 全展開
        C(0, 1), C(30, 5),
        # 男性・70代 専用(より具体的)
        C(0, 1, sex="M", age="70"), C(20, 5, sex="M", age="70"),
    ]
    # 男性70代 → 専用基準(threshold 20 で score5)
    r_specific = evaluate(rows, 25, sex="M", age_band="70")
    assert r_specific.resolved_condition == ("M", "70", None)
    assert r_specific.score == 5
    # 女性70代 → 全展開(threshold 30 未満なので score1)
    r_general = evaluate(rows, 25, sex="F", age_band="70")
    assert r_general.resolved_condition == (None, None, None)
    assert r_general.score == 1


def test_resolution_excludes_incompatible():
    rows = [C(0, 3, sex="M"), C(10, 5, sex="M")]
    # 女性は男性専用基準に適合しない → 判定不能(score None)
    r = evaluate(rows, 15, sex="F")
    assert r.score is None


def test_pacemaker_condition():
    rows = [
        C(0, 5),                 # 全展開
        C(0, 1, pm=1),           # PMあり専用
    ]
    key, group = resolve_group(rows, sex="M", age_band="70", pacemaker=1)
    assert key == (None, None, 1)
    key2, _ = resolve_group(rows, sex="M", age_band="70", pacemaker=0)
    assert key2 == (None, None, None)


# --- qualitative(コード値) ------------------------------------------------

def test_qualitative_code_mapping():
    rows = [
        C(1, 2, comment="不良"),
        C(2, 3, comment="やや不良"),
        C(3, 5, comment="良好"),
    ]
    r = evaluate(rows, 3)
    assert r.score == 5
    assert r.comment == "良好"


# --- ドメイン: 年代算出 ----------------------------------------------------

def test_age_and_band():
    assert calc_age("1950-01-01", "2026-07-09") == 76
    assert age_to_band(76) == "70"
    assert age_to_band(55) == "50"   # 50代以上バケット
    assert age_to_band(45) == "50"   # クランプ
    assert age_to_band(95) == "90"   # クランプ


def test_stars():
    assert stars(3) == "★★★☆☆"
    assert stars(5) == "★★★★★"
    assert stars(0) == "☆☆☆☆☆"
    assert stars(None) == "☆☆☆☆☆"


# --- ドメイン: 体重増減率 ---------------------------------------------------

def test_weight_change_ratio_decrease():
    assert weight_change_ratio(50, 45) == 90.0


def test_weight_change_ratio_increase():
    assert weight_change_ratio(50, 53.5) == 107.0


def test_weight_change_ratio_missing_values_is_none():
    assert weight_change_ratio(None, 45) is None
    assert weight_change_ratio(50, None) is None


def test_weight_change_ratio_zero_previous_is_none():
    assert weight_change_ratio(0, 45) is None


def test_weight_change_display_decrease():
    assert weight_change_display(90.0) == "90%(10%減少)"


def test_weight_change_display_increase():
    assert weight_change_display(107.0) == "107%(7%増加)"


def test_weight_change_display_no_change():
    assert weight_change_display(100.0) == "100%(変化なし)"


def test_weight_change_display_none_is_dash():
    assert weight_change_display(None) == "―"
