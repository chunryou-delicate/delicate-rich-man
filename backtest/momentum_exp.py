"""E1 모멘텀 (2차) + 가치와의 국면 상관.

1차는 펌프/분할 아티팩트로 오염(트레일링 중앙 +218%) → 무효. 2차 수정:
- **펌프 필터**: 트레일링 >200% 배제(분할·펌핑 아티팩트의 극단 제거).
- **12-1 표준**(최근 1개월 스킵, 단기 반전 회피) + RS 3/6/12 그리드.
- 신호는 벌크 price_change(빠름·캐시), 수익은 E0 현실 토대(수정주가 close→close + 슬리피지).

가설: 가치가 국면의존이니 정반대 모멘텀은 다른 국면 패턴 → 저상관/반대면 결합이 상쇄.
판정: ①모멘텀 train/validate가 가치와 반대인가 ②가치상관 낮은가 ③목표C. 전체 CAGR 아님.

한계: price_change 등락률은 수정 아님 → 분할 잔여 아티팩트 일부 leak(펌프필터로 극단만 제거).
정밀판(전 유니버스 수정주가)은 비용 큼 → 진단엔 이 근사로 충분.
사용법:  python -u -m backtest.momentum_exp
"""
from __future__ import annotations

import sys
import time
from dataclasses import replace

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)   # 백그라운드 flush

from . import data
from .engine import Params, _select
from .execution import execute
from .turnover_exp import _slice_metrics, _kospi_metrics

START, END = "20150101", "20251231"
LB_START = "20140101"
LS = [3, 6, 12]
SKIP = 1                 # 최근 1개월 스킵
CAP_PUMP = 200           # 트레일링(%) 상한 — 펌프/아티팩트 배제


def _universe(D, cap_floor=500, vol_floor=5):
    cap = data.market_cap(D)
    m = (cap["시가총액"] / 1e8 >= cap_floor) & (cap["거래대금"] / 1e8 >= vol_floor)
    return cap[m].index


def _pc(look, D, tries=4):
    for k in range(tries):
        try:
            pc = data.price_change(look, D)
            if len(pc) and "등락률" in pc.columns:
                return pc
        except Exception:
            pass
        time.sleep(1.0 * (k + 1))
    return None


def momentum_holdings(all_dates, start_idx, L, top_n=20):
    """직전 L개월(최근1개월 스킵) 상대강도 상위 top_n. 벌크 price_change + 펌프필터."""
    dates = all_dates[start_idx:]
    hold = []
    for i in range(start_idx, len(all_dates) - 1):
        d_start, d_end = all_dates[i - L], all_dates[i - SKIP]     # 스킵: 최근 1개월 제외
        pc = _pc(d_start, d_end)
        if pc is None:
            hold.append([])
            continue
        cand = pc.loc[pc.index.intersection(_universe(all_dates[i]))]
        cand = cand[cand["등락률"] <= CAP_PUMP]                     # 펌프 배제
        hold.append(cand.nlargest(top_n, "등락률").index.tolist())
    return dates, hold


def _corr(a, b, dates, y0, y1):
    idx = [i for i in range(len(a)) if y0 <= int(dates[i][:4]) <= y1]
    if len(idx) < 3:
        return float("nan")
    return pd.Series([a[i] for i in idx]).corr(pd.Series([b[i] for i in idx]))


def main() -> None:
    all_dates = data.rebalance_dates(LB_START, END, "M")
    first2015 = next(i for i, d in enumerate(all_dates) if d[:4] >= "2015")
    start_idx = max(first2015, max(LS))
    print(f"첫 리밸 {all_dates[start_idx]}, {len(all_dates)-start_idx-1}회", flush=True)

    mruns, allh = {}, set()
    for L in LS:
        print(f"모멘텀 {L}-1 선정(벌크)…", flush=True)
        dts, hold = momentum_holdings(all_dates, start_idx, L)
        mruns[L] = (dts, hold)
        for h in hold:
            allh.update(h)

    pv = replace(Params(start=START, end=END, top_n=20), use_fscore=True)
    vdts = all_dates[start_idx:]
    vhold = [_select(d0, pv) for d0 in vdts[:-1]]
    for h in vhold:
        allh.update(h)

    print(f"수정주가 로드: {len(allh)}종목(보유분만)…", flush=True)
    closes = {}
    for i, t in enumerate(sorted(allh), 1):
        df = data.daily_ohlc(t, START, END)
        closes[t] = df["종가"] if len(df) else pd.Series(dtype=float)
        if i % 100 == 0:
            print(f"  {i}/{len(allh)}", flush=True)
        time.sleep(0.03)

    veq, vmo = execute(vhold, vdts, closes, 0.25, 0.20)
    vfull = _slice_metrics(vdts, veq, vmo, 2015, 2025, 12)
    vtr = _slice_metrics(vdts, veq, vmo, 2015, 2019, 12)
    vva = _slice_metrics(vdts, veq, vmo, 2020, 2022, 12)

    km = _kospi_metrics(2015, 2025)
    print(f"\n{'전략':10s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} | {'train':>6s} {'valid':>6s} | "
          f"{'가치상관(전/훈/검)':>16s}", flush=True)
    print("-" * 74)
    print(f"{'코스피':10s} {km[0]:6.1f} {km[1]:7.1f} {km[2]:6.2f}")
    print(f"{'가치+품질':10s} {vfull[0]:6.1f} {vfull[1]:7.1f} {vfull[2]:6.2f} | "
          f"{vtr[0]:6.1f} {vva[0]:6.1f} | (기준)")
    for L in LS:
        dts, hold = mruns[L]
        eq, mo = execute(hold, dts, closes, 0.25, 0.20)
        full = _slice_metrics(dts, eq, mo, 2015, 2025, 12)
        tr = _slice_metrics(dts, eq, mo, 2015, 2019, 12)
        va = _slice_metrics(dts, eq, mo, 2020, 2022, 12)
        cf = _corr(vmo, mo, dts, 2015, 2025)
        ct = _corr(vmo, mo, dts, 2015, 2019)
        cv = _corr(vmo, mo, dts, 2020, 2022)
        print(f"{'모멘텀'+str(L)+'-1':10s} {full[0]:6.1f} {full[1]:7.1f} {full[2]:6.2f} | "
              f"{tr[0]:6.1f} {va[0]:6.1f} | {cf:5.2f}/{ct:5.2f}/{cv:5.2f}", flush=True)
    print("-" * 74)
    print("판정: ①모멘텀 train/validate가 가치와 반대인가(가치 train-/validate+) "
          "②가치상관 낮은가. 12-1·펌프필터(>200% 배제).")


if __name__ == "__main__":
    main()
