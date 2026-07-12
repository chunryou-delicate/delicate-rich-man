"""E1 모멘텀 단독 + 가치와의 국면 상관.

가설: 가치가 국면의존(train 죽고 validate 삶)이니, 정반대 성격 모멘텀은 다른 국면 패턴.
저상관/반대면 결합이 국면의존을 상쇄. 선정=유니버스 직전 L개월 RS 상위 top20(가치 무관).
수익=E0 현실 토대(슬리피지 0.2%). KRX 시세만(아카이브 불요), 12m RS 위해 2014 lookback.

사용법:  python -m backtest.momentum_exp
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
from .turnover_exp import _slice_metrics, _kospi_metrics

START, END = "20150101", "20251231"
LB_START = "20140101"            # 12개월 lookback 확보용
LS = [3, 6, 12]                  # RS 기간(개월) 그리드


def _universe(D, cap_floor=500, vol_floor=5):
    cap = data.market_cap(D)
    m = (cap["시가총액"] / 1e8 >= cap_floor) & (cap["거래대금"] / 1e8 >= vol_floor)
    return cap[m].index


def _pc(look, D, tries=4):
    """price_change transient 실패(pykrx None 반환) 재시도 + 검증."""
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
    dates = all_dates[start_idx:]
    hold = []
    for i in range(start_idx, len(all_dates) - 1):
        D, look = all_dates[i], all_dates[i - L]        # i>=start_idx>=max(LS) → i-L>=0
        pc = _pc(look, D)
        if pc is None:
            hold.append([])                              # 조회 실패 → 그 달 현금
            continue
        cand = pc.loc[pc.index.intersection(_universe(D))]
        hold.append(cand.nlargest(top_n, "등락률").index.tolist())
    return dates, hold


def _corr(a, b, dates, y0, y1):
    idx = [i for i in range(len(a)) if y0 <= int(dates[i][:4]) <= y1]
    if len(idx) < 3:
        return float("nan")
    return pd.Series([a[i] for i in idx]).corr(pd.Series([b[i] for i in idx]))


def main() -> None:
    all_dates = data.rebalance_dates(LB_START, END, "M")
    # 주의: pykrx ohlcv가 ~2872행 상한이라 달력이 2014-04부터 시작(2014-01~03 없음).
    # start_idx는 2015 시작 & i-L>=0(모든 L 동일 리밸일) 보장. lookback은 price_change로 확보.
    first2015 = next(i for i, d in enumerate(all_dates) if d[:4] >= "2015")
    start_idx = max(first2015, max(LS))
    print(f"첫 리밸 {all_dates[start_idx]} (lookback 확보), 총 {len(all_dates)-start_idx-1}회", flush=True)

    runs, allt = {}, set()
    for L in LS:
        print(f"모멘텀 RS{L}개월 선정…", flush=True)
        dts, hold = momentum_holdings(all_dates, start_idx, L)
        runs[L] = (dts, hold)
        for h in hold:
            allt.update(h)

    # 가치+품질(상관 비교용) — 모멘텀과 동일 날짜로 정렬(상관 정확)
    pv = replace(Params(start=START, end=END, top_n=20), use_fscore=True)
    vdts = all_dates[start_idx:]
    vhold = [_select(d0, pv) for d0 in vdts[:-1]]
    for h in vhold:
        allt.update(h)

    print(f"수정 종가 로드: {len(allt)}종목(모멘텀 신규 다수 → KRX)…", flush=True)
    closes = {}
    for i, t in enumerate(sorted(allt), 1):
        df = data.daily_ohlc(t, START, END)
        closes[t] = df["종가"] if len(df) else pd.Series(dtype=float)
        if i % 100 == 0:
            print(f"  {i}/{len(allt)}", flush=True)
        time.sleep(0.04)

    veq, vmo = execute(vhold, vdts, closes, 0.25, 0.20)   # 가치 월수익(현실)
    vfull = _slice_metrics(vdts, veq, vmo, 2015, 2025, 12)
    vtr = _slice_metrics(vdts, veq, vmo, 2015, 2019, 12)
    vva = _slice_metrics(vdts, veq, vmo, 2020, 2022, 12)

    km = _kospi_metrics(2015, 2025)
    print(f"\n{'전략':10s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} | {'train':>6s} {'valid':>6s} | "
          f"{'가치상관(전/훈/검)':>16s}")
    print("-" * 74)
    print(f"{'코스피':10s} {km[0]:6.1f} {km[1]:7.1f} {km[2]:6.2f}")
    print(f"{'가치+품질':10s} {vfull[0]:6.1f} {vfull[1]:7.1f} {vfull[2]:6.2f} | "
          f"{vtr[0]:6.1f} {vva[0]:6.1f} | (기준)")
    for L in LS:
        dts, hold = runs[L]
        eq, mo = execute(hold, dts, closes, 0.25, 0.20)
        full = _slice_metrics(dts, eq, mo, 2015, 2025, 12)
        tr = _slice_metrics(dts, eq, mo, 2015, 2019, 12)
        va = _slice_metrics(dts, eq, mo, 2020, 2022, 12)
        cf = _corr(vmo, mo, dts, 2015, 2025)
        ct = _corr(vmo, mo, dts, 2015, 2019)
        cv = _corr(vmo, mo, dts, 2020, 2022)
        print(f"{'모멘텀RS'+str(L):10s} {full[0]:6.1f} {full[1]:7.1f} {full[2]:6.2f} | "
              f"{tr[0]:6.1f} {va[0]:6.1f} | {cf:5.2f}/{ct:5.2f}/{cv:5.2f}")
    print("-" * 74)
    print("판정: ①모멘텀 train/validate가 가치와 반대인가(가치는 train-/validate+) "
          "②가치상관 낮은가(저상관=결합 상쇄 기대). 전체 CAGR 아님.")


if __name__ == "__main__":
    main()
