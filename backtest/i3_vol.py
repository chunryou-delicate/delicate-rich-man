"""I3 — 변동성 타겟팅 (3국면 H2).

주식비중 = clip(목표변동성T / 실현변동성(L일), 0, 1). on/off 아닌 연속 조정 → 박스피 whipsaw↓.
신호 t월말 → t+1월 체결. 그리드 T=10/12/15% × L=20/60일. 판정: §1 + 회색지대(≥4/6 유효).

기여 분해(I2와 같은 축): 위기 방어(2008·2020) / 박스피 출혈 / 회전율.
+ I3 함정: 실현변동성 후행 → 위기별 감속 타이밍(며칠 만에 비중↓). + I2 최선 비교표.
사용법:  python -u -m backtest.i3_vol
"""
from __future__ import annotations

import sys

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from . import index_data as ix, metrics
from .i2_trend import strategy as trend_strategy, _win

TS = [10, 12, 15]
LS = [20, 60]
T_CAGR, T_MDD, T_CALMAR, T_VAL_CALMAR, T_TRADES = 6.6, -29.0, 0.24, 0.13, 4.0
C2008 = (pd.Timestamp("2008-05-31"), pd.Timestamp("2009-02-28"))
C2020 = (pd.Timestamp("2020-01-31"), pd.Timestamp("2020-04-30"))


def _rvol_monthly(months_index, L):
    """각 월말의 실현변동성(연율): 최근 L거래일 일수익 std × √252."""
    dret = ix._idx_close().pct_change().dropna()
    rvol = dret.rolling(L).std() * (252 ** 0.5)
    return rvol.reindex(months_index, method="ffill")


def strategy(m, months_index, T, L):
    """비중=clip(T/rvol,0,1), t+1 체결. (월수익, 연회전, 월별 비중)."""
    rvol_m = _rvol_monthly(months_index, L)
    w_all = ((T / 100) / rvol_m).clip(0, 1)
    pos = {d: i for i, d in enumerate(months_index)}
    rets, ws, turn, wprev = [], [], 0.0, None
    for r in m.index:
        w = w_all.iloc[pos[r] - 1]                       # 직전 월말 비중
        stock = m.loc[r, "price"] + m.loc[r, "div"] - ix.HOLD_DRAG_YR / 12
        ret = w * stock + (1 - w) * m.loc[r, "cash"]
        if wprev is not None:
            dw = abs(w - wprev); turn += dw; ret -= dw * ix.SWITCH_COST
        rets.append(ret); ws.append(w); wprev = w
    return pd.Series(rets, index=m.index), turn, pd.Series(ws, index=m.index)


def _crisis(rets, ws, bh, win, label):
    cm = (rets.index >= win[0]) & (rets.index <= win[1])
    s = ix.equity(rets[cm])[-1] - 1
    b = ix.equity(bh[cm])[-1] - 1
    # 감속 타이밍: 위기 시작 후 비중이 0.5 밑으로 처음 내려간 개월
    wc = ws[ws.index >= win[0]]
    lag = next((j for j, v in enumerate(wc) if v < 0.5), None)
    lagtxt = f"{lag}개월째" if lag is not None else "비중유지"
    return f"{label}: 전략 {s*100:+.0f}% vs B&H {b*100:+.0f}% (비중 0.5↓ 감속 {lagtxt})"


def main() -> None:
    m = ix.monthly("20000101", "20251231")
    months_index = ix._idx_close().resample("ME").last().dropna().index
    bh = ix.bh_returns(m)
    years = len(m) / 12

    print("I3 변동성타겟 그리드", flush=True)
    print(f"{'T/L':10s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} | {'검칼마':>6s} {'연회전':>5s}  PASS")
    print("-" * 52)
    passes, grid = 0, {}
    for T in TS:
        for L in LS:
            rets, turn, ws = strategy(m, months_index, T, L)
            fc, fmd, fca = _win(rets, 2000, 2025)
            _, _, vca = _win(rets, 2013, 2019)
            tr = turn / years
            ok = (fc >= T_CAGR and fmd >= T_MDD and fca >= T_CALMAR
                  and vca >= T_VAL_CALMAR and tr <= T_TRADES)
            passes += ok
            grid[(T, L)] = (rets, ws, fc, fmd, fca, vca, tr)
            print(f"{'T%d/L%d' % (T, L):10s} {fc:6.1f} {fmd:7.1f} {fca:6.2f} | {vca:6.2f} {tr:5.1f}  {'✅' if ok else ''}")
    print("-" * 52)
    print(f"그리드 판정: {passes}/6 → {'✅ 유효(≥4)' if passes >= 4 else ('🔶 부분유효(3)' if passes == 3 else '❌ 기각(≤2)')}")

    # 대표 config = 전체 칼마 최고
    best = max(grid, key=lambda k: grid[k][4])
    rets, ws, fc, fmd, fca, vca, tr = grid[best]
    print(f"\n=== 기여 분해 (I3 최선 T{best[0]}/L{best[1]}) ===")
    print("① 위기 방어 + 감속 타이밍(I3 함정):")
    print("   " + _crisis(rets, ws, bh, C2008, "2008(서서히)"))
    print("   " + _crisis(rets, ws, bh, C2020, "2020(급락)"))
    vc_s, _, _ = _win(rets, 2013, 2019)
    print(f"② 박스피(2013-19): 전략 CAGR {vc_s:.1f}% vs B&H 2.7% → {vc_s-2.7:+.1f}%p")

    # I2 최선(8/±0)과 비교표
    r2, sw2, inv2 = trend_strategy(m, ix._idx_close().resample("ME").last().dropna(), 8, 0.0)
    def crisisret(rr, win): cm=(rr.index>=win[0])&(rr.index<=win[1]); return (ix.equity(rr[cm])[-1]-1)*100
    v2,_,_=_win(r2,2013,2019); f2c,f2md,f2ca=_win(r2,2000,2025)
    print(f"\n=== I3 최선 vs I2 최선(8/±0) 비교 ===")
    print(f"{'축':16s} {'I3(T'+str(best[0])+'/L'+str(best[1])+')':>12s} {'I2(8/±0)':>10s}")
    print(f"{'2008 방어':16s} {crisisret(rets,C2008):11.0f}% {crisisret(r2,C2008):9.0f}%")
    print(f"{'2020 방어':16s} {crisisret(rets,C2020):11.0f}% {crisisret(r2,C2020):9.0f}%")
    print(f"{'박스피 CAGR':16s} {vc_s:11.1f}% {v2:9.1f}%")
    print(f"{'전체 MDD':16s} {fmd:11.0f}% {f2md:9.0f}%")
    print(f"{'전체 칼마':16s} {fca:11.2f} {f2ca:9.2f}")
    print(f"{'연 회전':16s} {tr:11.1f} {sw2/years:9.1f}")


if __name__ == "__main__":
    main()
