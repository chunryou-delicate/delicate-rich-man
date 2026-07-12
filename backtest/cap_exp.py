"""E6-② 대형주 단독 — 국면의존 진단 (cap하한 그리드).

E6-①이 밝힌 "선정 국면의존"이 **종목 크기 탓이냐 팩터 탓이냐** 판별.
선정=가치+품질(top20/f6)·월 리밸 고정, **cap하한만** 바꿈. E0 현실 토대(슬리피지 0.2%).

핵심 판정 = train(2015-19)/validate(2020-22) 일관성 (전체 수익 아님):
- 대형주도 train 음수·validate만 양수 → "크기 무관 국면의존" 확정.
- 대형주가 train도 견디면 → 크기가 원인, 살릴 여지.

사용법:  python -m backtest.cap_exp
"""
from __future__ import annotations

import sys
import time
from dataclasses import replace

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from . import data
from .engine import Params, _select
from .execution import execute
from .turnover_exp import _slice_metrics, _kospi_metrics, START, END

CAPS = [500, 3000, 10000, 30000]     # 억. 500=현재, 30000=3조↑ 초대형


def main() -> None:
    P0 = replace(Params(start=START, end=END, top_n=20), use_fscore=True)
    dts = data.rebalance_dates(START, END, "M")
    runs, allt = {}, set()
    for cap in CAPS:
        p = replace(P0, cap_floor=cap)
        print(f"cap≥{cap}억 선정…", flush=True)
        hold = [_select(d0, p) for d0 in dts[:-1]]
        runs[cap] = hold
        for h in hold:
            allt.update(h)

    print(f"수정 종가 로드: {len(allt)}종목 (대형주는 신규 → KRX 조회)…", flush=True)
    closes = {}
    for i, t in enumerate(sorted(allt), 1):
        df = data.daily_ohlc(t, START, END)
        closes[t] = df["종가"] if len(df) else pd.Series(dtype=float)
        if i % 100 == 0:
            print(f"  {i}/{len(allt)}", flush=True)
        time.sleep(0.05)

    km = _kospi_metrics(2015, 2025)
    print(f"\n{'cap하한':8s} {'평균보유':>6s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} | "
          f"{'★train':>7s} {'★validate':>9s}  진단")
    print("-" * 72)
    print(f"{'코스피':8s} {'—':>6s} {km[0]:6.1f} {km[1]:7.1f} {km[2]:6.2f}")
    all_train_neg = True
    for cap in CAPS:
        hold = runs[cap]
        eq, mo = execute(hold, dts, closes, 0.25, 0.20)
        full = _slice_metrics(dts, eq, mo, 2015, 2025, 12)
        tr = _slice_metrics(dts, eq, mo, 2015, 2019, 12)
        va = _slice_metrics(dts, eq, mo, 2020, 2022, 12)
        avgh = sum(len(h) for h in hold) / len(hold)
        train_ok = tr[0] > 0
        all_train_neg = all_train_neg and (not train_ok)
        diag = "train도 견딤 ← 살릴여지" if train_ok else "train 음수(국면의존)"
        print(f"{'≥'+str(cap)+'억':8s} {avgh:6.1f} {full[0]:6.1f} {full[1]:7.1f} {full[2]:6.2f} | "
              f"{tr[0]:7.1f} {va[0]:9.1f}  {diag}")
    print("-" * 72)
    print("진단 결론:", "✅ 모든 cap에서 train 음수 → **크기 무관 국면의존**(팩터 탓 확정)"
          if all_train_neg else "△ 일부 cap train 견딤 → 크기가 원인일 수 있음(추가 판단)")
    print("※ 핵심은 train/validate 일관성. 전체 CAGR에 속지 말 것. 저빈도 아님(월 고정).")


if __name__ == "__main__":
    main()
