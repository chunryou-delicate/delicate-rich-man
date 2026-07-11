"""KRX 시세 스냅샷 (pykrx 경유).

DART엔 없는 시가총액·거래대금·PER·PBR을 KRX Data Marketplace에서 받아온다.
로그인은 pykrx가 KRX_ID/KRX_PW(.env) 로 자동 처리. EOD(전일 종가) 기준 — 스크리너엔 충분.
지표는 억 단위로 맞춰 data.json 스키마(cap·vol)와 일치시킨다.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from pykrx import stock

KST = timezone(timedelta(hours=9))


def _clean_ratio(v) -> float | None:
    """PER·PBR 정리: NaN·0·음수(적자 등)는 의미 없으므로 None."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or v <= 0:
        return None
    return round(v, 2)


def latest_trading_date(max_back: int = 10):
    """오늘부터 거슬러 올라가며 시총·펀더멘탈이 모두 있는 최근 영업일을 찾는다.

    주말/휴장일엔 시총·펀더멘탈 endpoint가 행은 주지만 PER·PBR이 전부 0으로 온다.
    따라서 PER>0 종목이 실제로 있는 날(=진짜 영업일)이어야 한다.
    반환: (YYYYMMDD, 시총 df, 펀더멘탈 df) 또는 (None, None, None).
    """
    d = datetime.now(KST)
    for _ in range(max_back):
        ymd = d.strftime("%Y%m%d")
        try:
            fund_df = stock.get_market_fundamental_by_ticker(ymd, market="ALL")
            if len(fund_df) and (fund_df["PER"] > 0).sum() > 100:   # 진짜 영업일
                cap_df = stock.get_market_cap_by_ticker(ymd, market="ALL")
                if len(cap_df):
                    return ymd, cap_df, fund_df
        except Exception:
            pass
        d -= timedelta(days=1)
    return None, None, None


def get_price_snapshot() -> tuple[dict[str, dict], str | None]:
    """{종목코드: {cap, vol, per, pbr}} 스냅샷과 기준일(YYYYMMDD) 반환. 억 단위."""
    ymd, cap_df, fund_df = latest_trading_date()
    if not ymd:
        return {}, None

    snap: dict[str, dict] = {}
    for ticker, row in cap_df.iterrows():
        per = pbr = None
        if fund_df is not None and ticker in fund_df.index:
            f = fund_df.loc[ticker]
            per = _clean_ratio(f.get("PER"))
            pbr = _clean_ratio(f.get("PBR"))
        snap[ticker] = {
            "cap": round(row["시가총액"] / 1e8),        # 원 → 억
            "vol": round(row["거래대금"] / 1e8, 1),     # 원 → 억
            "per": per,
            "pbr": pbr,
        }
    return snap, ymd
