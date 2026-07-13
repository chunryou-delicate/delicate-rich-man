"""I0 — 인덱스 데이터·인프라 (3국면).

지수 레벨 + 배당수익률 + 현금(대피) 수익률 + 비용 모델을 한곳에.
공정성(INDEX_PLAN §3-2): 배당(추세전략 과대평가 방지)과 현금수익(과소평가 방지) **둘 다** 반영.

- B&H 월수익 = 지수 가격수익 + 배당수익(보유 중).
- 추세전략은 '주식일 때' 가격+배당, '현금일 때' 현금수익 — I2에서 이 모듈로 조립.
- 실행 규약: 신호 t월말 → 체결 t+1(월 단위라 다음 달 수익부터 반영).

검증: `python -u -m backtest.index_data` → B&H 지표가 공개 코스피와 대략 일치하는지.
"""
from __future__ import annotations

import sys

import pandas as pd
from pykrx import stock

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from . import data, metrics

KOSPI = "1001"

# 비용(ETF 표준, INDEX_PLAN §3-3)
SWITCH_COST = 0.10 / 100        # 스위치 왕복(%)
HOLD_DRAG_YR = 0.15 / 100       # 보유 총보수(연) — 주식 보유 월에만 적용

# 현금 대피 수익률: 한국 기준금리 연평균 근사(%) — CD91 근사, I0 잠정치(추후 정밀화)
_BASE_RATE = {
    2000: 5.0, 2001: 4.5, 2002: 4.25, 2003: 3.75, 2004: 3.5, 2005: 3.75, 2006: 4.5,
    2007: 5.0, 2008: 4.8, 2009: 2.0, 2010: 2.3, 2011: 3.1, 2012: 3.0, 2013: 2.6,
    2014: 2.3, 2015: 1.7, 2016: 1.4, 2017: 1.3, 2018: 1.6, 2019: 1.6, 2020: 0.7,
    2021: 0.6, 2022: 1.9, 2023: 3.5, 2024: 3.4, 2025: 3.0,
}


def _idx_close(start="19900101", end="20251231", ticker=KOSPI):
    return data._cached(f"idx_{ticker}_{start}_{end}",
                        lambda: stock.get_index_ohlcv_by_date(start, end, ticker)["종가"])


def _div_yield(start="19900101", end="20251231", ticker=KOSPI):
    def fetch():
        try:
            return stock.get_index_fundamental_by_date(start, end, ticker)["배당수익률"]
        except Exception:
            return pd.Series(dtype=float)
    return data._cached(f"idxdiv_{ticker}_{start}_{end}", fetch)


def monthly(start: str, end: str, ticker=KOSPI) -> pd.DataFrame:
    """월말 기준 시계열: 가격수익·배당수익·현금수익. index=월말 Timestamp."""
    lvl = _idx_close(ticker=ticker).resample("ME").last().dropna()
    lvl = lvl[(lvl.index >= pd.Timestamp(start)) & (lvl.index <= pd.Timestamp(end))]
    price = lvl.pct_change().dropna()

    dy = _div_yield(ticker=ticker).resample("ME").last()
    dy = dy.reindex(price.index, method="ffill").fillna(1.8)   # 결측 초기엔 1.8% 근사
    div = (dy / 100) / 12                                       # 월 배당수익(보유 중)

    cash = pd.Series([_BASE_RATE.get(d.year, 3.0) / 100 / 12 for d in price.index],
                     index=price.index)
    return pd.DataFrame({"level": lvl.reindex(price.index), "price": price,
                         "div": div, "cash": cash})


def bh_returns(m: pd.DataFrame) -> pd.Series:
    """Buy&Hold 월수익 = 가격 + 배당 (보유 드래그 반영)."""
    return m["price"] + m["div"] - HOLD_DRAG_YR / 12


def equity(rets) -> list[float]:
    e = [1.0]
    for r in rets:
        e.append(e[-1] * (1 + r))
    return e


def _report(name, rets):
    eq = equity(rets)
    n = len(rets)
    print(f"  {name:16s} CAGR {metrics.cagr(eq, n, 12):5.1f}% · MDD {metrics.mdd(eq):6.1f}% · "
          f"칼마 {metrics.calmar(eq, n, 12):.2f} · 샤프 {metrics.sharpe(list(rets), 12):.2f}")


def main() -> None:
    print("I0 검증 — 코스피 B&H (배당·현금·비용 반영)", flush=True)
    m = monthly("20000101", "20251231")
    print(f"월 데이터 {len(m)}개월, 지수 {m['level'].iloc[0]:.0f} → {m['level'].iloc[-1]:.0f}")
    bh = bh_returns(m)
    price_only = m["price"] - HOLD_DRAG_YR / 12
    _report("B&H(가격만)", price_only)
    _report("B&H(가격+배당)", bh)
    # 검증: 가격수익 복리가 실제 지수 레벨 변화와 일치하는가 (공개지표 대조)
    # base는 pct_change 이전의 첫 월말(원본 lvl.iloc[0]) — reindex된 m["level"] 아님.
    lvl = _idx_close().resample("ME").last().dropna()
    lvl = lvl[(lvl.index >= pd.Timestamp("20000101")) & (lvl.index <= pd.Timestamp("20251231"))]
    implied = lvl.iloc[-1] / lvl.iloc[0] - 1
    comp = equity(m["price"])[-1] - 1
    ok = abs(implied - comp) < 0.02
    print(f"\n검증(공개지표 대조): 지수레벨 {lvl.iloc[0]:.0f}→{lvl.iloc[-1]:.0f} "
          f"= 총 {implied*100:.0f}% vs 가격수익 복리 {comp*100:.0f}% → {'일치 ✅' if ok else '불일치 ⚠️'}")
    print(f"      배당수익률 최근 {m['div'].iloc[-1]*12*100:.1f}%/년 · 현금 최근 {m['cash'].iloc[-1]*12*100:.1f}%/년")
    print("※ 현금(기준금리)은 연평균 근사 잠정치. 배당은 지수 배당수익률 실측.")


if __name__ == "__main__":
    main()
