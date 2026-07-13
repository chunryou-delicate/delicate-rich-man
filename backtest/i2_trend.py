"""I2 — 추세필터 (본진, 로드맵 3국면 H1).

지수 ≥ N개월 SMA(±버퍼밴드)면 주식, 아니면 현금(+기준금리). 신호 t월말 → t+1월 체결.
그리드 N=5/8/10/12 × 버퍼 0/±1/±3%. 판정: 사전확정 §1 + 회색지대 규칙(backtest/README).

기여 분해(필수): ①훈련 MDD 개선이 2008 회피에서? ②검증(박스피) whipsaw 연 몇%p?
사용법:  python -u -m backtest.i2_trend
"""
from __future__ import annotations

import sys

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from . import index_data as ix, metrics

NS = [5, 8, 10, 12]
BUFS = [0.0, 0.01, 0.03]
# §1 성공선(I1 사전등록)
T_CAGR, T_MDD, T_CALMAR, T_VAL_CALMAR, T_TRADES = 6.6, -29.0, 0.24, 0.13, 4.0
CRASH = (pd.Timestamp("2008-05-31"), pd.Timestamp("2009-02-28"))   # 2008 위기창


def _states(lvl_full, N, buf):
    sma = lvl_full.rolling(N).mean()
    st, prev = {}, True
    for d in lvl_full.index:
        s = sma.get(d)
        if pd.isna(s):
            st[d] = prev
            continue
        if lvl_full[d] > s * (1 + buf):
            prev = True
        elif lvl_full[d] < s * (1 - buf):
            prev = False
        st[d] = prev
    return st


def strategy(m, lvl_full, N, buf):
    """t+1 체결. (월수익 Series, 스위치수, 월별 주식여부)."""
    st = _states(lvl_full, N, buf)
    months = list(lvl_full.index)
    pos = {months[i]: i for i in range(len(months))}
    rets, invested, switches, last = [], [], 0, None
    for r in m.index:
        sig = st[months[pos[r] - 1]]                    # 직전 월말 신호 → 이번 달 체결
        stock = m.loc[r, "price"] + m.loc[r, "div"] - ix.HOLD_DRAG_YR / 12
        ret = stock if sig else m.loc[r, "cash"]
        if last is not None and sig != last:
            ret -= ix.SWITCH_COST
            switches += 1
        rets.append(ret)
        invested.append(sig)
        last = sig
    return pd.Series(rets, index=m.index), switches, pd.Series(invested, index=m.index)


def _win(rets, y0, y1):
    r = rets[(rets.index.year >= y0) & (rets.index.year <= y1)]
    eq = ix.equity(r)
    n = len(r)
    return metrics.cagr(eq, n, 12), metrics.mdd(eq), metrics.calmar(eq, n, 12)


def main() -> None:
    m = ix.monthly("20000101", "20251231")
    lvl_full = ix._idx_close().resample("ME").last().dropna()
    bh = ix.bh_returns(m)
    years = len(m) / 12

    print("I2 추세필터 그리드 (전체/훈련/검증 + 연매매 + PASS)", flush=True)
    print(f"{'N/버퍼':10s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} | {'훈MDD':>6s} {'검칼마':>6s} "
          f"{'연매매':>5s}  PASS")
    print("-" * 62)
    passes = 0
    grid = {}
    for N in NS:
        for buf in BUFS:
            rets, sw, inv = strategy(m, lvl_full, N, buf)
            fc, fmd, fca = _win(rets, 2000, 2025)
            _, tmd, _ = _win(rets, 2000, 2012)
            _, _, vca = _win(rets, 2013, 2019)
            trades = sw / years
            ok = (fc >= T_CAGR and fmd >= T_MDD and fca >= T_CALMAR
                  and vca >= T_VAL_CALMAR and trades <= T_TRADES)
            passes += ok
            grid[(N, buf)] = (rets, inv, fc, fmd, fca, vca, trades)
            print(f"{'%d/±%.0f%%' % (N, buf*100):10s} {fc:6.1f} {fmd:7.1f} {fca:6.2f} | "
                  f"{tmd:6.1f} {vca:6.2f} {trades:5.1f}  {'✅' if ok else ''}")
    print("-" * 62)
    print(f"그리드 판정: {passes}/12 통과 → "
          f"{'✅ 유효(≥7)' if passes >= 7 else ('🔶 부분유효(6)' if passes == 6 else '❌ 기각(≤5)')}")

    # 기여 분해 — 대표 config(N=10, 버퍼 0 = Faber 고전)
    rets, inv, fc, fmd, fca, vca, trades = grid[(10, 0.0)]
    print(f"\n=== 기여 분해 (N=10, 버퍼 0) ===")
    # ① 2008 회피
    cm = (m.index >= CRASH[0]) & (m.index <= CRASH[1])
    s_cr = ix.equity(rets[cm])[-1] - 1
    b_cr = ix.equity(bh[cm])[-1] - 1
    cash_ratio = (~inv[cm]).mean() * 100
    print(f"① 2008창({CRASH[0].date()}~{CRASH[1].date()}): 전략 {s_cr*100:+.0f}% vs B&H {b_cr*100:+.0f}% "
          f"(그 기간 현금비중 {cash_ratio:.0f}%)")
    _, tmd_s, _ = _win(rets, 2000, 2012); _, tmd_b, _ = _win(bh, 2000, 2012)
    print(f"   훈련 MDD: 전략 {tmd_s:.0f}% vs B&H {tmd_b:.0f}% → 개선 {tmd_b-tmd_s:.0f}%p (2008 회피 기여)")
    # ② 검증 whipsaw
    vc_s, _, _ = _win(rets, 2013, 2019); vc_b, _, _ = _win(bh, 2013, 2019)
    sw_val = sum(1 for j in range(1, len(inv)) if inv.index[j].year in range(2013, 2020)
                 and inv.iloc[j] != inv.iloc[j-1])
    print(f"② 검증(2013-19 박스피): 전략 CAGR {vc_s:.1f}% vs B&H {vc_b:.1f}% → "
          f"차 {vc_s-vc_b:+.1f}%p, 스위치 {sw_val}회/7년")


if __name__ == "__main__":
    main()
