"""E6-① 저회전 단독 실험 — 리밸 주기(월/분기/반기) 그리드.

선정(가치+품질 top20/f6)·유니버스 고정, **리밸 주기만** 바꿔 회전율↓ 효과를 본다.
수익은 E0 현실 토대(close→close + 슬리피지 0.2%)로 계산. 훈련→검증 확인.

목표=C 성공선(사전): base(월) 대비 CAGR을 코스피 근처로 되돌리고 MDD를 시장 이하로.
사용법:  python -m backtest.turnover_exp
"""
from __future__ import annotations

import sys
import time
from dataclasses import replace

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from . import data, metrics
from .engine import Params, _select
from .execution import execute

START, END = "20150101", "20251231"
P = replace(Params(start=START, end=END, top_n=20), use_fscore=True)


def _slice_metrics(dates, equity, monthly, y0, y1, ppy):
    """[y0,y1]년 구간 지표. ppy=연당 기간수(월12·분기4·반기2)."""
    idx = [i for i, d in enumerate(dates) if y0 <= int(d[:4]) <= y1]
    if len(idx) < 2:
        return None
    a, b = idx[0], idx[-1]
    eq = [v / equity[a] for v in equity[a:b + 1]]
    mo = monthly[a:b]
    n = len(mo)
    return (metrics.cagr(eq, n, ppy), metrics.mdd(eq), metrics.calmar(eq, n, ppy), metrics.sharpe(mo, ppy))


def _turnover(holdings):
    prev, tot = set(), 0.0
    for h in holdings:
        cur = set(h)
        tot += len(cur - prev) / max(len(cur), 1)
        prev = cur
    return tot / len(holdings)          # 리밸당 평균 교체율


def _kospi_metrics(y0, y1):
    k = data.kospi(START, END)
    seg = k[[y0 <= d.year <= y1 for d in k.index]]
    if len(seg) < 2:
        return None
    m = seg.resample("ME").last().dropna()      # 월말 기준(전략 월 측정과 일치)
    eq = [float(v / m.iloc[0]) for v in m]
    mo = m.pct_change().dropna().tolist()
    n = len(mo)
    return (metrics.cagr(eq, n, 12), metrics.mdd(eq), metrics.calmar(eq, n, 12), metrics.sharpe(mo, 12))


def main() -> None:
    freqs = [("월", "M"), ("분기", "Q"), ("반기", "H")]
    # 각 주기 선정 → 보유
    runs = {}
    allt = set()
    for nm, f in freqs:
        dts = data.rebalance_dates(START, END, f)
        print(f"{nm} 리밸 {len(dts)}회 선정…", flush=True)
        hold = [_select(d0, P) for d0 in dts[:-1]]
        runs[f] = (dts, hold)
        for h in hold:
            allt.update(h)

    print(f"수정 종가 로드: {len(allt)}종목(캐시)…", flush=True)
    closes = {}
    for i, t in enumerate(sorted(allt), 1):
        df = data.daily_ohlc(t, START, END)
        closes[t] = df["종가"] if len(df) else pd.Series(dtype=float)
        time.sleep(0.03)

    print(f"\n{'주기':6s} {'회전/년':>7s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} {'샤프':>6s} | "
          f"{'훈련CAGR/MDD':>12s} {'검증CAGR/MDD':>12s}")
    print("-" * 78)
    km = _kospi_metrics(2015, 2025)
    print(f"{'코스피':6s} {'—':>7s} {km[0]:6.1f} {km[1]:7.1f} {km[2]:6.2f} {km[3]:6.2f}")
    per_year = {"M": 12, "Q": 4, "H": 2}
    for nm, f in freqs:
        dts, hold = runs[f]
        ppy = per_year[f]
        eq, mo = execute(hold, dts, closes, 0.25, 0.20)
        full = _slice_metrics(dts, eq, mo, 2015, 2025, ppy)
        tr = _slice_metrics(dts, eq, mo, 2015, 2019, ppy)
        va = _slice_metrics(dts, eq, mo, 2020, 2022, ppy)
        turn_yr = _turnover(hold) * per_year[f]
        print(f"{nm:6s} {turn_yr*100:6.0f}% {full[0]:6.1f} {full[1]:7.1f} {full[2]:6.2f} {full[3]:6.2f} | "
              f"{tr[0]:5.1f}/{tr[1]:5.0f}  {va[0]:5.1f}/{va[1]:5.0f}")
    print("-" * 78)
    print("성공선(목표C): CAGR 코스피(7.3) 근처 복귀 + MDD < -34.6 + 훈련·검증 일관.")
    print("※ E0 현실 토대(슬리피지 0.2%). 회전/년 = 리밸당 교체율 × 연 리밸수.")


if __name__ == "__main__":
    main()
