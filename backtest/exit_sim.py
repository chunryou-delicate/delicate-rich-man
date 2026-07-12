"""청산 시뮬레이터 — 손절·트레일링스톱 (로드맵 [4]).

선정 규칙(가치+품질 top20/f6)은 고정하고, **청산 방식만** 바꿔 효과를 본다.
월 보유 중 일별 종가로 손절/트레일링을 판정 → 조기 청산 시 그 손익까지만 반영(이후 현금).

판정 기준(사전 확정, README): 단순 MDD 감소가 아니라 **칼마(CAGR/|MDD|)·샤프 개선**.
손절이 반등을 잘라 CAGR을 크게 깎으면 실패. 그리드로 여러 설정에서 유지돼야 유효.

사용법:  python -m backtest.exit_sim
한계(v1): 일별 종가 기준(장중 저가 아님), 상폐 종목 부분/0 처리, 배당 무시.
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


def _period_ret(closes: pd.Series, d0: str, d1: str, stop, trail):
    """[d0,d1] 보유 한 종목의 손익. (수익률, 손절여부). 종가 close-to-close 기준."""
    seg = closes.loc[pd.Timestamp(d0):pd.Timestamp(d1)]
    if len(seg) < 2 or seg.iloc[0] <= 0:
        return 0.0, False
    entry = seg.iloc[0]
    peak = entry
    for px in seg.iloc[1:]:
        peak = max(peak, px)
        if stop and px <= entry * (1 - stop):
            return -stop, True                       # 고정 손절 체결(근사)
        if trail and px <= peak * (1 - trail):
            return px / entry - 1, True              # 트레일링 체결
    return seg.iloc[-1] / entry - 1, False


def _simulate(holdings, dates, closes, stop, trail, cost_oneway=0.25):
    equity, monthly, prev = [1.0], [], set()
    for i in range(len(holdings)):
        picks, d0, d1 = holdings[i], dates[i], dates[i + 1]
        rets, stopped = [], 0
        for t in picks:
            c = closes.get(t)
            if c is None or not len(c):
                rets.append(0.0)
                continue
            r, was = _period_ret(c, d0, d1, stop, trail)
            rets.append(r)
            stopped += was
        port = sum(rets) / len(rets) if rets else 0.0
        cur = set(picks)
        turnover = len(cur - prev) / max(len(cur), 1)
        cost = 2 * (cost_oneway / 100) * turnover \
            + (cost_oneway / 100) * (stopped / max(len(picks), 1))   # 손절 추가 매도비용
        equity.append(equity[-1] * (1 + port - cost))
        monthly.append(port - cost)
        prev = cur
    return equity, monthly


def _row(name, equity, monthly):
    n = len(monthly)
    return {
        "name": name,
        "cagr": metrics.cagr(equity, n),
        "mdd": metrics.mdd(equity),
        "calmar": metrics.calmar(equity, n),
        "sharpe": metrics.sharpe(monthly),
    }


def main() -> None:
    print("선정 규칙(가치+품질 top20/f6) 실행…", flush=True)
    p = replace(Params(start=START, end=END, top_n=20), use_fscore=True)
    r = run(p)
    dates, holdings = r.dates, r.holdings

    uniq = sorted(set(t for h in holdings for t in h))
    print(f"일별주가 사전로드: {len(uniq)}종목 (캐시)…", flush=True)
    closes = {}
    for i, t in enumerate(uniq, 1):
        closes[t] = data.daily_close(t, START, END)
        if i % 50 == 0:
            print(f"  {i}/{len(uniq)}", flush=True)
        time.sleep(0.1)

    # 그리드: base + 고정손절 + 트레일링
    configs = [("base(무손절)", None, None),
               ("고정 -10%", 0.10, None), ("고정 -15%", 0.15, None), ("고정 -20%", 0.20, None),
               ("트레일 15%", None, 0.15), ("트레일 20%", None, 0.20), ("트레일 25%", None, 0.25)]
    rows = []
    for nm, s, tr in configs:
        eq, mo = _simulate(holdings, dates, closes, s, tr)
        rows.append(_row(nm, eq, mo))

    base = rows[0]
    print(f"\n{'설정':14s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} {'샤프':>6s}  판정")
    print("-" * 52)
    improved = 0
    for x in rows:
        mark = ""
        if x["name"] != base["name"]:
            ok = x["calmar"] > base["calmar"] and x["sharpe"] > base["sharpe"]
            improved += ok
            mark = "✅" if ok else "❌"
        print(f"{x['name']:14s} {x['cagr']:6.1f} {x['mdd']:7.1f} {x['calmar']:6.2f} {x['sharpe']:6.2f}  {mark}")
    n = len(rows) - 1
    print("-" * 52)
    print(f"판정: {improved}/{n} 설정이 칼마·샤프 동시 개선", flush=True)
    if improved >= (n + 1) // 2:
        print("→ ✅ 청산(손절/트레일링)이 위험대비수익을 일관되게 개선 = 유효")
    else:
        print("→ ❌ 일부만 개선 = 과최적화 의심, 채택 보류")
    print("\n※ 일별 종가 기준(장중 저가 아님)·배당무시·상폐 0/부분 처리 편향 상존.")


if __name__ == "__main__":
    main()
