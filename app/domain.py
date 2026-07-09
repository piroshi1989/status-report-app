"""年代算出・★表記など、UI/評価/帳票で共有するドメインロジック."""

from __future__ import annotations

from datetime import date

# 評価基準の年代バンド。'50' は「50代以上」= 最若年の基準バケット(59歳以下を一括)。
AGE_BANDS = ["50", "60", "70", "80", "90"]

AGE_BAND_LABELS = {
    "50": "50代以上",
    "60": "60代",
    "70": "70代",
    "80": "80代",
    "90": "90代",
}


def parse_date(value: str | date | None) -> date | None:
    from datetime import datetime

    if value is None or value == "":
        return None
    # datetime は date のサブクラスなので、先に date へ落とす(Excel の日付セル対策)
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if text == "":
        return None
    # "1949-03-03 00:00:00" のような文字列も許容
    text = text.split(" ")[0].split("T")[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def calc_age(birth: str | date | None, on: str | date | None) -> int | None:
    """``on`` 時点の満年齢."""
    b = parse_date(birth)
    o = parse_date(on) or date.today()
    if b is None:
        return None
    years = o.year - b.year - ((o.month, o.day) < (b.month, b.day))
    return years


def age_to_band(age: int | None) -> str | None:
    """満年齢 → 年代バンド。floor(age/10)*10 を [50,90] にクランプ."""
    if age is None:
        return None
    decade = (age // 10) * 10
    decade = max(50, min(90, decade))
    return str(decade)


def band_for(birth: str | date | None, on: str | date | None) -> str | None:
    return age_to_band(calc_age(birth, on))


def stars(score: int | None, max_score: int = 5) -> str:
    """score n → ★×n + ☆×(max-n)。未測定(None)は ☆×max."""
    if score is None:
        return "☆" * max_score
    n = max(0, min(max_score, int(score)))
    return "★" * n + "☆" * (max_score - n)
