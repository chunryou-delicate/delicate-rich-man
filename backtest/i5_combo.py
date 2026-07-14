"""I5 — I2(추세) + I3(변동성) 조합.

곱 구조: 비중 = 추세신호(0/1) × 변동성비중(0~1). 추세 이탈=즉시 0(빠른 방어),
추세 안=변동성 스케일(횡보 완화). 신호 t월말 → t+1 체결.

파라미터 폭발 금지: I2·I3 검증된 대표값만 조합(새 탐색 없음). 결합방식 검증이지 재튜닝 아님.
이중 관문(사전): §1 전부 + 훈련MDD≥-30%(I2 근접) + 검증CAGR≥1.3%(I3 근접). 부모보다 퇴보=실패.
재입장 비용 분해: 추세 0→1 복귀 점프가 I3 부드러움 무력화하나.
사용법:  python -u -m backtest.i5_combo
"""
from __future__ import annotations

import sys

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from . import index_data as ix, metrics
from .i2_trend import _states, _win
from .i3_vol import _rvol_monthly

# 검증된 대표값만 (새 파라미터 탐색 없음)
TREND = [(8, 0.0), (10, 0.01)]      # (N, 버퍼)
VOL = [(12, 60), (15, 60)]          # (T, L)
# 판정 관문
T_CAGR, T_MDD, T_CALMAR, T_VAL_CALMAR, T_TRADES = 6.6, -29.0, 0.24, 0.13, 4.0
G_TRAIN_MDD, G_VAL_CAGR = -30.0, 1.3   # 이중관문(I2/I3 근접)
C2008 = (pd.Timestamp("2008-05-31"), pd.Timestamp("2009-02-28"))
C2020 = (pd.Timestamp("2020-01-31"), pd.Timestamp("2020-04-30"))


def combo(m, months_index, lvl_full, N, buf, T, L):
    st = _states(lvl_full, N, buf)
    volw = ((T / 100) / _rvol_monthly(months_index, L)).clip(0, 1)
    pos = {d: i for i, d in enumerate(months_index)}
    rets, ws, turn, reentry, wprev, tprev = [], [], 0.0, 0, None, None
    for r in m.index:
        i = pos[r] - 1
        tsig = st[months_index[i]]                       # 0/1 (직전 월말)
        w = (1.0 if tsig else 0.0) * volw.iloc[i]        # 곱
        stock = m.loc[r, "price"] + m.loc[r, "div"] - ix.HOLD_DRAG_YR / 12
        ret = w * stock + (1 - w) * m.loc[r, "cash"]
        if wprev is not None:
            dw = abs(w - wprev); turn += dw; ret -= dw * ix.SWITCH_COST
        if tprev is not None and tsig and not tprev:     # 추세 0→1 재입장
            reentry += 1
        rets.append(ret); ws.append(w); wprev = w; tprev = tsig
    return pd.Series(rets, index=m.index), turn, reentry, pd.Series(ws, index=m.index)


def _cret(rr, win):
    cm = (rr.index >= win[0]) & (rr.index <= win[1])
    return (ix.equity(rr[cm])[-1] - 1) * 100


def main() -> None:
    m = ix.monthly("20000101", "20251231")
    months_index = ix._idx_close().resample("ME").last().dropna().index
    lvl_full = ix._idx_close().resample("ME").last().dropna()
    years = len(m) / 12

    print("I5 조합 그리드 (곱: 추세 × 변동성)", flush=True)
    print(f"{'추세×변동성':16s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} | {'훈MDD':>6s} {'검CAGR':>6s} "
          f"{'검칼마':>6s} {'연회전':>5s} {'재입장':>5s}  PASS")
    print("-" * 82)
    passes, grid = 0, {}
    for N, buf in TREND:
        for T, L in VOL:
            rets, turn, reentry, ws = combo(m, months_index, lvl_full, N, buf, T, L)
            fc, fmd, fca = _win(rets, 2000, 2025)
            _, tmd, _ = _win(rets, 2000, 2012)
            vc, _, vca = _win(rets, 2013, 2019)
            tr = turn / years
            s1 = (fc >= T_CAGR and fmd >= T_MDD and fca >= T_CALMAR
                  and vca >= T_VAL_CALMAR and tr <= T_TRADES)
            gate = (tmd >= G_TRAIN_MDD and vc >= G_VAL_CAGR)   # 이중관문
            ok = s1 and gate
            passes += ok
            grid[(N, buf, T, L)] = (rets, ws, fc, fmd, fca, vc, vca, tr, reentry, tmd)
            tag = 'N%d±%.0f×T%d' % (N, buf * 100, T)
            print(f"{tag:16s} {fc:6.1f} {fmd:7.1f} {fca:6.2f} | {tmd:6.1f} {vc:6.1f} {vca:6.2f} "
                  f"{tr:5.1f} {reentry:5d}  {'✅' if ok else ('§1×' if not s1 else '관문×')}")
    print("-" * 82)
    print(f"그리드 판정: {passes}/4 → "
          f"{'✅ 유효(≥3)' if passes >= 3 else ('🔶 부분유효(2)' if passes == 2 else '❌ 기각(≤1)')}")

    best = max(grid, key=lambda k: grid[k][4])
    rets, ws, fc, fmd, fca, vc, vca, tr, reentry, tmd = grid[best]
    print(f"\n=== 최선 조합 {best} 기여 분해 (부모와 비교) ===")
    print(f"위기 방어: 2008 {_cret(rets,C2008):+.0f}% (I2 -7·I3 -20) · 2020 {_cret(rets,C2020):+.0f}% (I2 -9·I3 -12)")
    print(f"박스피 CAGR: {vc:.1f}% (I2 -0.1·I3 +1.8) · 훈련MDD: {tmd:.0f}% (I2 ~-27·I3 ~-27)")
    print(f"전체: CAGR {fc:.1f}·MDD {fmd:.0f}·칼마 {fca:.2f} · 연회전 {tr:.1f}(I3 0.7) · 재입장 {reentry}회")
    print("② 재입장 비용: 곱 구조 0→1 점프 {}회 → 연 {:.1f}회, I3(부드러움) 대비 회전 {:.1f}배".format(
        reentry, reentry / years, tr / 0.7))


if __name__ == "__main__":
    main()
