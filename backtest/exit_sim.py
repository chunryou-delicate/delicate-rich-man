"""청산 시뮬레이터 — 손절·트레일링스톱 (로드맵 [4]).

선정 규칙(가치+품질 top20/f6)은 고정하고 **청산 방식만** 바꿔 효과를 본다.
두 모델을 나란히:
  - close(낙관): 일별 종가로만 손절 판정. 갭·장중 무시 → 낙관 상한선.
  - gap(현실): 갭다운 시 시가(더 나쁜 가격) 체결, 장중 저가가 손절선 터치 시 손절가 체결.

판정(사전 확정, README): 갭 반영 후에도 base 대비 **칼마·샤프 개선** + "타이트할수록 좋은"
경향 유지되면 견고. 단순 CAGR·MDD 하나만 보지 않음.

사용법:  python -m backtest.exit_sim
한계(v1): 배당 무시, 상폐 종목 0/부분 처리, 손절 체결가 근사.
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


def _ret(df: pd.DataFrame, d0: str, d1: str, stop, trail, gap: bool):
    """[d0,d1] 보유 한 종목 손익. (수익률, 손절여부). gap=True면 갭/장중 반영."""
    seg = df.loc[pd.Timestamp(d0):pd.Timestamp(d1)]
    if len(seg) < 2 or seg["종가"].iloc[0] <= 0:
        return 0.0, False
    entry = seg["종가"].iloc[0]          # d0 종가 매수
    peak = entry
    O, L, C = seg["시가"].values, seg["저가"].values, seg["종가"].values
    for j in range(1, len(seg)):
        if stop:
            lvl = entry * (1 - stop)
            if gap and O[j] <= lvl:           # 갭다운으로 손절선 관통 → 시가 체결(더 나쁨)
                return O[j] / entry - 1, True
            if (L[j] if gap else C[j]) <= lvl:  # gap: 장중 저가 터치→손절가 / close: 종가
                return (-stop if gap else C[j] / entry - 1), True
        if trail:
            lvl = peak * (1 - trail)
            if gap and O[j] <= lvl:
                return O[j] / entry - 1, True
            if (L[j] if gap else C[j]) <= lvl:
                return (lvl / entry - 1 if gap else C[j] / entry - 1), True
        peak = max(peak, C[j])                # 당일 종가로 peak 갱신
    return C[-1] / entry - 1, False


def _simulate(holdings, dates, omap, stop, trail, gap, cost_oneway=0.25):
    equity, monthly, prev = [1.0], [], set()
    for i in range(len(holdings)):
        picks, d0, d1 = holdings[i], dates[i], dates[i + 1]
        rets, stopped = [], 0
        for t in picks:
            df = omap.get(t)
            if df is None or not len(df):
                rets.append(0.0)
                continue
            r, was = _ret(df, d0, d1, stop, trail, gap)
            rets.append(r)
            stopped += was
        port = sum(rets) / len(rets) if rets else 0.0
        cur = set(picks)
        turnover = len(cur - prev) / max(len(cur), 1)
        cost = 2 * (cost_oneway / 100) * turnover + (cost_oneway / 100) * (stopped / max(len(picks), 1))
        equity.append(equity[-1] * (1 + port - cost))
        monthly.append(port - cost)
        prev = cur
    return equity, monthly


def _m(equity, monthly):
    n = len(monthly)
    return (metrics.cagr(equity, n), metrics.mdd(equity),
            metrics.calmar(equity, n), metrics.sharpe(monthly))


CONFIGS = [("base(무손절)", None, None),
           ("고정 -10%", 0.10, None), ("고정 -15%", 0.15, None), ("고정 -20%", 0.20, None),
           ("트레일 15%", None, 0.15), ("트레일 20%", None, 0.20), ("트레일 25%", None, 0.25)]


def main() -> None:
    print("선정 규칙(가치+품질 top20/f6) 실행…", flush=True)
    p = replace(Params(start=START, end=END, top_n=20), use_fscore=True)
    r = run(p)
    dates, holdings = r.dates, r.holdings

    uniq = sorted(set(t for h in holdings for t in h))
    print(f"일별 OHLC 로드: {len(uniq)}종목 (캐시)…", flush=True)
    omap = {}
    for i, t in enumerate(uniq, 1):
        omap[t] = data.daily_ohlc(t, START, END)
        if i % 50 == 0:
            print(f"  {i}/{len(uniq)}", flush=True)
        time.sleep(0.1)

    # 두 모델 각각 그리드
    res = {"close": [], "gap": []}
    for mode in ("close", "gap"):
        for nm, s, tr in CONFIGS:
            eq, mo = _simulate(holdings, dates, omap, s, tr, gap=(mode == "gap"))
            res[mode].append((nm, *_m(eq, mo)))

    # 나란히 출력: close(낙관) vs gap(현실)
    print(f"\n{'설정':13s} | {'close(낙관)':^26s} | {'gap(현실)':^26s}")
    print(f"{'':13s} | {'CAGR':>6s}{'MDD':>7s}{'칼마':>6s}{'샤프':>6s} | {'CAGR':>6s}{'MDD':>7s}{'칼마':>6s}{'샤프':>6s} 판정")
    print("-" * 74)
    bc, bg = res["close"][0], res["gap"][0]     # base
    improved = 0
    for k in range(len(CONFIGS)):
        c, g = res["close"][k], res["gap"][k]
        mark = ""
        if k > 0:
            ok = g[3] > bg[3] and g[4] > bg[4]   # gap 기준 칼마·샤프 개선
            improved += ok
            mark = "✅" if ok else "❌"
        print(f"{c[0]:13s} | {c[1]:6.1f}{c[2]:7.1f}{c[3]:6.2f}{c[4]:6.2f} | "
              f"{g[1]:6.1f}{g[2]:7.1f}{g[3]:6.2f}{g[4]:6.2f} {mark}")
    n = len(CONFIGS) - 1
    print("-" * 74)
    # -10% 낙관 대비 갭 감소
    c10, g10 = res["close"][1], res["gap"][1]
    print(f"고정-10% 칼마: 낙관 {c10[3]:.2f} → 갭 {g10[3]:.2f}  (샤프 {c10[4]:.2f} → {g10[4]:.2f})")
    print(f"판정(gap 기준): {improved}/{n} 설정이 칼마·샤프 동시 개선", flush=True)
    grad = res["gap"][1][3] >= res["gap"][2][3] >= res["gap"][3][3]  # -10 ≥ -15 ≥ -20 칼마
    print(f"'타이트할수록 좋은' 경향(갭 반영): {'유지 ✅' if grad else '깨짐 ❌'}")
    if improved >= (n + 1) // 2 and grad:
        print("→ ✅ 갭 반영 후에도 손절이 견고하게 유효")
    else:
        print("→ ⚠️ 갭 반영 시 약화 — 낙관치는 상한선. 박사님 확인 필요(채택 보류 성향)")
    print("\n※ 배당무시·상폐 0/부분·체결가 근사 편향 상존. gap 모델도 완벽한 장중틱은 아님.")


if __name__ == "__main__":
    main()
