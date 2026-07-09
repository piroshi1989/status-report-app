"""migrate_excel の冗長基準正規化ロジックのテスト."""

from scripts.migrate_excel import normalize


def test_all_same_collapses_to_null():
    rows = [(0.0, 1, None, None), (10.0, 5, None, None)]
    cond_rows = {
        ("50", None): rows, ("60", 0): rows, ("60", 1): rows,
        ("70", 0): rows, ("70", 1): rows,
    }
    out = normalize(cond_rows)
    assert out == [(None, None, rows)]


def test_pacemaker_collapses_within_age():
    r70 = [(0.0, 1, None, None), (20.0, 5, None, None)]
    r80 = [(0.0, 1, None, None), (18.0, 5, None, None)]
    cond_rows = {
        ("70", 0): r70, ("70", 1): r70,   # PM で同一 → pacemaker NULL
        ("80", 0): r80, ("80", 1): r80,
    }
    out = normalize(cond_rows)
    conds = {(a, p) for a, p, _ in out}
    assert conds == {("70", None), ("80", None)}


def test_pacemaker_kept_when_differs():
    r_no = [(0.0, 1, None, None), (20.0, 5, None, None)]
    r_pm = [(0.0, 1, None, None), (25.0, 5, None, None)]
    cond_rows = {("70", 0): r_no, ("70", 1): r_pm}
    out = normalize(cond_rows)
    conds = {(a, p) for a, p, _ in out}
    assert conds == {("70", 0), ("70", 1)}
