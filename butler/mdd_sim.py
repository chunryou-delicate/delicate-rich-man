"""v0.5 낙폭 시뮬 — 프리셋 실측 MDD·회복기간.

3프리셋(방어 50/35/15 · 균형 70/20/10 · 성장 85/10/5, 주식 국내:글로벌 50:50)의
실제 과거 낙폭을 표로. 발주낸 추정(-30%)을 실측으로 대체.

데이터 제약(정직):
- 4자산 실데이터는 2011~ (글로벌·채권 ETF 시작). **2020·2022는 실측**, 2008은 못 봄.
- 2008은 코스피만으로 근사(글로벌≈국내, 채권≈현금 보수적 가정) — 한계 명시.
- 글로벌은 헤지형(143850)뿐 → 시뮬은 헤지. 실투자는 언헤지(위기 때 덜 빠짐) →
  **시뮬 낙폭은 보수적(약간 나쁘게 나온) 추정.** 방향: 실제는 시뮬보다 덜 빠짐.

사용법:  python -u -m butler.mdd_sim
"""
from __future__ import annotations

import sys

import pandas as pd
from pykrx import stock

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from backtest import index_data as ix, metrics, data

GLOBAL_ETF = "143850"      # TIGER S&P500선물(H) — 2011~
BOND_ETF = "148070"        # KOSEF 국고채10년 — 2011~
PRESETS = {"방어 50/35/15": (0.50, 0.35, 0.15),
           "균형 70/20/10": (0.70, 0.20, 0.10),
           "성장 85/10/5": (0.85, 0.10, 0.05)}
CRISES = {"2020 코로나": (2020, 2020), "2022 금리쇼크": (2022, 2022)}


def _etf_month(tk):
    def fetch():
        return stock.get_etf_ohlcv_by_date("20100101", "20251231", tk)["종가"]
    return data._cached(f"etf_{tk}", fetch).resample("ME").last().dropna()


def _mdd_recovery(eq):
    """MDD(%)와 회복 개월수. 미회복이면 None."""
    peak, peak_i, mdd, tro_i, mdd_peak_i = eq[0], 0, 0.0, 0, 0
    for i, v in enumerate(eq):
        if v > peak:
            peak, peak_i = v, i
        if v / peak - 1 < mdd:
            mdd, tro_i, mdd_peak_i = v / peak - 1, i, peak_i
    peak_val = eq[mdd_peak_i]
    rec = next((i - tro_i for i in range(tro_i, len(eq)) if eq[i] >= peak_val), None)
    return mdd * 100, rec


def _eq(rets):
    e = [1.0]
    for r in rets:
        e.append(e[-1] * (1 + r))
    return e


def _preset_rets(dom_r, glob_r, bond_r, cash_r, ws, wb, wc):
    return ws * (0.5 * dom_r + 0.5 * glob_r) + wb * bond_r + wc * cash_r


def main() -> None:
    dom = ix._idx_close().resample("ME").last().dropna()          # 코스피
    glob = _etf_month(GLOBAL_ETF)
    bond = _etf_month(BOND_ETF)
    dom_r, glob_r, bond_r = dom.pct_change(), glob.pct_change(), bond.pct_change()
    idx = dom_r.index.intersection(glob_r.index).intersection(bond_r.index)
    idx = idx[idx >= pd.Timestamp("2011-12-31")]
    dom_r, glob_r, bond_r = dom_r[idx], glob_r[idx], bond_r[idx]
    cash_r = pd.Series([ix._BASE_RATE.get(d.year, 3.0) / 100 / 12 for d in idx], index=idx)

    print(f"낙폭 시뮬 실측구간: {idx[0].date()} ~ {idx[-1].date()} ({len(idx)}개월)", flush=True)
    print("(글로벌=헤지형 143850 → 실투자 언헤지는 위기 때 덜 빠짐 → 시뮬은 보수적 추정)\n")
    print(f"{'프리셋':16s} {'CAGR':>6s} {'전체MDD':>7s} {'회복(월)':>7s} | "
          f"{'2020 MDD':>8s} {'2022 MDD':>8s}")
    print("-" * 62)
    for nm, (ws, wb, wc) in PRESETS.items():
        r = _preset_rets(dom_r, glob_r, bond_r, cash_r, ws, wb, wc)
        eq = _eq(r)
        mdd, rec = _mdd_recovery(eq)
        cr = metrics.cagr(eq, len(r), 12)
        crmdd = {}
        for cn, (y0, y1) in CRISES.items():
            rr = r[(r.index.year >= y0) & (r.index.year <= y1)]
            crmdd[cn] = _mdd_recovery(_eq(rr))[0]
        print(f"{nm:16s} {cr:6.1f} {mdd:7.1f} {str(rec)+'월' if rec else '미회복':>7s} | "
              f"{crmdd['2020 코로나']:7.1f}% {crmdd['2022 금리쇼크']:7.1f}%")

    # 2008 근사 (코스피만, 글로벌≈국내·채권≈현금 보수적)
    print("\n=== 2008 근사 (실데이터 없음 — 코스피 기반, 보수적) ===")
    m00 = ix.monthly("20000101", "20251231")
    d08 = m00[m00.index.year.isin([2007, 2008, 2009])]
    for nm, (ws, wb, wc) in PRESETS.items():
        # 글로벌≈국내(코스피), 채권≈현금(보수적: 채권의 08 안전자산 상승 미반영)
        r = ws * d08["price"] + (wb + wc) * d08["cash"]
        mdd, rec = _mdd_recovery(_eq(r))
        print(f"  {nm:16s} 2008 근사 MDD {mdd:6.1f}% (실제는 채권 완충으로 이보다 덜 빠졌을 것)")
    print("\n※ 핵심 산출: 균형형 2020·2022 실측 MDD → policy _expected(-30%) 대체.")


if __name__ == "__main__":
    main()
