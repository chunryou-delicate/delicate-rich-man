"""성과 지표 — 수익률 시계열 → CAGR·MDD·샤프 등."""
from __future__ import annotations

import math


def cagr(equity: list[float], n_periods: int, ppy: int = 12) -> float:
    """연평균 복리수익률(%). n_periods=기간 수, ppy=연당 기간 수(월=12·분기=4·반기=2)."""
    if n_periods <= 0 or equity[0] <= 0:
        return 0.0
    years = n_periods / ppy
    return (equity[-1] / equity[0]) ** (1 / years) * 100 - 100


def total_return(equity: list[float]) -> float:
    return (equity[-1] / equity[0] - 1) * 100


def mdd(equity: list[float]) -> float:
    """최대낙폭(%) — 고점 대비 최대 하락. 음수로 반환."""
    peak = equity[0]
    worst = 0.0
    for v in equity:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst * 100


def calmar(equity: list[float], n_periods: int, ppy: int = 12) -> float:
    """칼마 = CAGR / |MDD|. 위험(낙폭) 대비 수익. 높을수록 좋음."""
    m = mdd(equity)
    if m == 0:
        return 0.0
    return cagr(equity, n_periods, ppy) / abs(m)


def sharpe(rets: list[float], ppy: int = 12, rf_annual: float = 0.0) -> float:
    """기간수익률 리스트 → 연율화 샤프. ppy=연당 기간 수(월=12·분기=4·반기=2)."""
    if len(rets) < 2:
        return 0.0
    rf_p = rf_annual / 100 / ppy
    ex = [r - rf_p for r in rets]
    mean = sum(ex) / len(ex)
    var = sum((r - mean) ** 2 for r in ex) / (len(ex) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return mean / sd * math.sqrt(ppy)


def win_rate_vs(monthly_rets: list[float], bench_rets: list[float]) -> float:
    """벤치마크를 이긴 달의 비율(%)."""
    wins = sum(1 for a, b in zip(monthly_rets, bench_rets) if a > b)
    return wins / len(monthly_rets) * 100 if monthly_rets else 0.0
