"""I5b — I2+I3 합산 블렌드.

곱 대신 합산: 비중 = a·추세(0/1) + (1-a)·변동성비중. a=0.5 고정. 재입장 점프 완화(최대 a).
관문 원래대로. 부모는 검증된 대표값만(새 튜닝 없음). 신호 t월말 → t+1 체결.

예측(사전): 블렌드는 추세=0에도 (1-a)·vol 남아 위기 방어 희석 → train MDD 쪽에서 죽을 수 있음.
사용법:  python -u -m backtest.i5b_blend
"""
from __future__ import annotations

import sys

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from . import index_data as ix
from .i2_trend import _states, _win
from .i3_vol import _rvol_monthly

TREND = [(8, 0.0), (10, 0.01)]
VOL = [(12, 60), (15, 60)]
A = 0.5
T_CAGR, T_MDD, T_CALMAR, T_VAL_CALMAR, T_TRADES = 6.6, -29.0, 0.24, 0.13, 4.0
C2008 = (pd.Timestamp("2008-05-31"), pd.Timestamp("2009-02-28"))
C2020 = (pd.Timestamp("2020-01-31"), pd.Timestamp("2020-04-30"))


def blend(m, months_index, lvl_full, N, buf, T, L, a=A):
    st = _states(lvl_full, N, buf)
    volw = ((T / 100) / _rvol_monthly(months_index, L)).clip(0, 1)
    pos = {d: i for i, d in enumerate(months_index)}
    rets, ws, turn, reentry, wprev, tprev = [], [], 0.0, 0, None, None
    for r in m.index:
        i = pos[r] - 1
        tsig = st[months_index[i]]
        w = a * (1.0 if tsig else 0.0) + (1 - a) * volw.iloc[i]       # 합산 블렌드
        stock = m.loc[r, "price"] + m.loc[r, "div"] - ix.HOLD_DRAG_YR / 12
        ret = w * stock + (1 - w) * m.loc[r, "cash"]
        if wprev is not None:
            dw = abs(w - wprev); turn += dw; ret -= dw * ix.SWITCH_COST
        if tprev is not None and tsig and not tprev:
            reentry += 1
        rets.append(ret); ws.append(w); wprev = w; tprev = tsig
    return pd.Series(rets, index=m.index), turn, reentry, pd.Series(ws, index=m.index)


def _cret(rr, win):
    cm = (rr.index >= win[0]) & (rr.index <= win[1])
    return (ix.equity(rr[cm])[-1] - 1) * 100


def main() -> None:
    m = ix.monthly("20000101", "20251231")
    months_index = ix._idx_close().resample("ME").last().dropna().index
    lvl_full = months_index.to_series()  # placeholder; use level below
    lvl_full = ix._idx_close().resample("ME").last().dropna()
    years = len(m) / 12

    print(f"I5b 합산 블렌드 (a={A}: 비중 = {A}·추세 + {1-A}·vol)", flush=True)
    print(f"{'추세×vol':16s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} | {'훈MDD':>6s} {'검CAGR':>6s} "
          f"{'검칼마':>6s} {'연회전':>5s} {'재입장':>5s}  5/5")
    print("-" * 82)
    p5, grid = 0, {}
    for N, buf in TREND:
        for T, L in VOL:
            rets, turn, reentry, ws = blend(m, months_index, lvl_full, N, buf, T, L)
            fc, fmd, fca = _win(rets, 2000, 2025)
            _, tmd, _ = _win(rets, 2000, 2012)
            vc, _, vca = _win(rets, 2013, 2019)
            tr = turn / years
            hits = [fc >= T_CAGR, fmd >= T_MDD, fca >= T_CALMAR, vca >= T_VAL_CALMAR, tr <= T_TRADES]
            full = all(hits)
            p5 += full
            grid[(N, buf, T, L)] = (rets, ws, fc, fmd, fca, vc, vca, tr, reentry, tmd, hits)
            tag = 'N%d±%.0f×T%d' % (N, buf * 100, T)
            print(f"{tag:16s} {fc:6.1f} {fmd:7.1f} {fca:6.2f} | {tmd:6.1f} {vc:6.1f} {vca:6.2f} "
                  f"{tr:5.1f} {reentry:5d}  {'✅5/5' if full else str(sum(hits))+'/5'}")
    print("-" * 82)
    print(f"5/5 통과 config: {p5}/4 → 갈래 {'(a) walk-forward' if p5 >= 1 else '(b) 통과후보 없음=종결'}")

    best = max(grid, key=lambda k: grid[k][4])
    rets, ws, fc, fmd, fca, vc, vca, tr, reentry, tmd, hits = grid[best]
    bdrag = vc - 2.7
    print(f"\n=== 최선 {best} 트레이드오프 프로파일 (LESSONS용) ===")
    print(f"위기: 2008 {_cret(rets,C2008):+.0f}% (I2 -7·I3 -20·I5 -5) · 2020 {_cret(rets,C2020):+.0f}%")
    print(f"전체 CAGR {fc:.1f}%(B&H 7.6) · MDD {fmd:.0f}%(B&H -48) · 칼마 {fca:.2f}(B&H 0.16)")
    print(f"훈련 MDD {tmd:.0f}% · 박스피 드래그 {bdrag:+.1f}%p(전략 {vc:.1f} vs B&H 2.7)")
    print(f"② 재입장 {reentry}회(연 {reentry/years:.1f}) · 연회전 {tr:.1f}(I5 2.1·I3 0.7) — 블렌드 점프 완화됐나")


if __name__ == "__main__":
    main()
