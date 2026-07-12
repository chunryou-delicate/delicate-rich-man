"""과거 데이터 접근 계층 (pykrx) + 디스크 캐싱.

같은 날짜의 pykrx 응답을 .cache/bt/ 에 pickle로 저장 → 규칙을 바꿔가며
재실행할 때 재호출이 없어 즉시 돈다. (규칙 튜닝 반복이 핵심이라 캐싱 필수)
"""
from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd
from pykrx import stock

from collector import config  # KRX 로그인(.env) 트리거 겸 경로 재사용

CACHE = config.ROOT / ".cache" / "bt"


def _cached(key: str, fn):
    """key 로 pickle 캐시. 없으면 fn() 호출해 저장."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{key}.pkl"
    if path.exists():
        with open(path, "rb") as f:
            return pickle.load(f)
    obj = fn()
    with open(path, "wb") as f:
        pickle.dump(obj, f)
    return obj


def trading_calendar(start: str, end: str) -> list[str]:
    """[start,end] 거래일 목록(YYYYMMDD). 삼성전자 일봉 인덱스로 확보."""
    def fetch():
        df = stock.get_market_ohlcv_by_date(start, end, "005930")
        return [d.strftime("%Y%m%d") for d in df.index]
    return _cached(f"cal_{start}_{end}", fetch)


def rebalance_dates(start: str, end: str) -> list[str]:
    """월별 리밸런싱일 = 각 달의 마지막 거래일."""
    cal = trading_calendar(start, end)
    by_month: dict[str, str] = {}
    for d in cal:
        by_month[d[:6]] = d          # 같은 달이면 뒤 날짜가 덮음 → 월 마지막 거래일
    return [by_month[m] for m in sorted(by_month)]


def fundamental(date: str) -> pd.DataFrame:
    """해당일 전종목 PER·PBR·DIV 등 (point-in-time 단면)."""
    return _cached(f"fund_{date}", lambda: stock.get_market_fundamental_by_ticker(date, market="ALL"))


def market_cap(date: str) -> pd.DataFrame:
    """해당일 전종목 시가총액·거래대금 (규모·유동성 필터용)."""
    return _cached(f"cap_{date}", lambda: stock.get_market_cap_by_ticker(date, market="ALL"))


def price_change(d0: str, d1: str) -> pd.DataFrame:
    """[d0,d1] 기간 전종목 등락률(%). 한 번에 받아 보유수익 계산에 사용."""
    return _cached(f"pc_{d0}_{d1}", lambda: stock.get_market_price_change(d0, d1, market="ALL"))


def kospi(start: str, end: str) -> pd.Series:
    """코스피 지수(1001) 종가 시계열 — 벤치마크."""
    def fetch():
        return stock.get_index_ohlcv_by_date(start, end, "1001")["종가"]
    return _cached(f"kospi_{start}_{end}", fetch)


def daily_close(ticker: str, start: str, end: str) -> pd.Series:
    """종목 일별 종가(수정주가) — 손절·트레일링 시뮬용. 인덱스=Timestamp."""
    def fetch():
        df = stock.get_market_ohlcv_by_date(start, end, ticker, adjusted=True)
        return df["종가"] if len(df) else pd.Series(dtype=float)
    return _cached(f"close_{ticker}_{start}_{end}", fetch)
