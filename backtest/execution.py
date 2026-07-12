"""실행(execution) 슬롯 — 진입·청산·비용을 선정에서 분리 (로드맵 E0).

기존 엔진은 "월1 시가→종가 일괄매매"가 하드코딩 + look-ahead(선정 d0 종가·매수 d0 시가).
이 모듈은 보유종목(holdings)을 받아 **믿을 수 있는 체결 규약**으로 수익을 계산한다:
  - 매수 = d0 종가(선정과 같은 시점 = look-ahead 제거), 매도 = d1 종가(close-to-close).
  - 슬리피지·비용을 회전율에 비례해 차감.
진입/청산 전략(분할·손절 등)은 이 슬롯 위에 규칙으로 얹는다(추후).

E0 판정은 EXPERIMENT_PLAN·backtest/README 참조: (A)현실화=보수적으로 나빠져야 성공.
사용법:  python -m backtest.execution   (현상태 vs look-ahead수정 vs +슬리피지 분해)
"""
from __future__ import annotations

import sys
import time
from dataclasses import replace

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from . import data, metrics
from .engine import Params, run

START, END = "20150101", "20251231"


def execute(holdings, dates, closes, cost_oneway=0.25, slippage_oneway=0.0):
    """보유종목 → 월수익. 매수=d0 종가, 매도=d1 종가(look-ahead 없음).

    closes: {종목코드: 수정 종가 Series}. 비용·슬리피지는 회전율×양방향 차감.
    """
    equity, monthly, prev = [1.0], [], set()
    friction_rate = (cost_oneway + slippage_oneway) / 100
    for i in range(len(holdings)):
        picks, d0, d1 = holdings[i], dates[i], dates[i + 1]
        rets = []
        for t in picks:
            s = closes.get(t)
            if s is None or not len(s):
                rets.append(0.0)
                continue
            seg = s.loc[pd.Timestamp(d0):pd.Timestamp(d1)]
            if len(seg) < 2 or seg.iloc[0] <= 0:
                rets.append(0.0)
                continue
            rets.append(seg.iloc[-1] / seg.iloc[0] - 1)     # close(d0) → close(d1)
        port = sum(rets) / len(rets) if rets else 0.0
        cur = set(picks)
        turnover = len(cur - prev) / max(len(cur), 1)
        equity.append(equity[-1] * (1 + port - 2 * friction_rate * turnover))
        monthly.append(port - 2 * friction_rate * turnover)
        prev = cur
    return equity, monthly


def _row(nm, equity, monthly):
    n = len(monthly)
    return (nm, metrics.cagr(equity, n), metrics.mdd(equity),
            metrics.calmar(equity, n), metrics.sharpe(monthly))


def main() -> None:
    print("가치+품질(top20/f6) 선정 실행…", flush=True)
    p = replace(Params(start=START, end=END, top_n=20), use_fscore=True)
    r = run(p)

    uniq = sorted(set(t for h in r.holdings for t in h))
    print(f"수정 종가 로드: {len(uniq)}종목 (캐시)…", flush=True)
    closes = {}
    for i, t in enumerate(uniq, 1):
        df = data.daily_ohlc(t, START, END)
        closes[t] = df["종가"] if len(df) else pd.Series(dtype=float)
        time.sleep(0.05)

    rows = []
    # 1) 현상태 = 엔진(시가→종가, 비용0.25%) — look-ahead 있음
    rows.append(_row("현상태(엔진)", r.equity, r.monthly))
    # 2) look-ahead만 수정 = close→close, 비용 동일 0.25%, 슬리피지 0
    rows.append(_row("+look-ahead수정", *execute(r.holdings, r.dates, closes, 0.25, 0.0)))
    # 3) +슬리피지 0.20%(편도) 추가
    rows.append(_row("++슬리피지0.2%", *execute(r.holdings, r.dates, closes, 0.25, 0.20)))
    # 참고: 코스피
    eqk = [1.0]
    for x in r.bench_monthly:
        eqk.append(eqk[-1] * (1 + x))
    kospi = _row("[코스피]", eqk, r.bench_monthly)

    print(f"\n{'단계':16s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} {'샤프':>6s}")
    print("-" * 46)
    print(f"{kospi[0]:16s} {kospi[1]:6.1f} {kospi[2]:7.1f} {kospi[3]:6.2f} {kospi[4]:6.2f}")
    for x in rows:
        print(f"{x[0]:16s} {x[1]:6.1f} {x[2]:7.1f} {x[3]:6.2f} {x[4]:6.2f}")
    print("-" * 46)
    d1 = rows[0][1] - rows[1][1]
    d2 = rows[1][1] - rows[2][1]
    print(f"분해: look-ahead가 CAGR {d1:+.1f}%p, 슬리피지가 {d2:+.1f}%p 부풀림 (합 {d1+d2:+.1f}%p)")
    worse = rows[2][3] <= rows[0][3]
    print(f"판정(A): 현실화 후 칼마 {rows[0][3]:.2f}→{rows[2][3]:.2f} — "
          f"{'✅ 보수적으로 나빠짐(정상)' if worse else '⚠️ 안 나빠짐 → 현실화 덜 됨/버그 의심'}")
    print("\n※ 슬리피지 0.2%(편도)는 소·중형 가치주 가정. 장중 틱 아님. (B)부수효과 재확인 별도.")


if __name__ == "__main__":
    main()
