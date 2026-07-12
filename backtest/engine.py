"""백테스트 엔진 — 월별 리밸런싱 루프.

규칙(기본): 매 리밸런싱일에 PER·PBR 각각 순위를 매겨 합산(마법공식식),
합산순위 낮은(=싸고) 상위 N종목을 동일비중 보유, 다음 리밸런싱까지.

방어 장치:
- look-ahead: 지표는 리밸런싱일 '당일' 단면만 사용, 수익은 그 이후 기간만.
- 생존편향: 각 시점의 실제 상장 종목(pykrx 단면)으로 유니버스 구성.
- 거래비용: 회전율에 비례해 매매비용 차감(수수료+세금+슬리피지 근사).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import data


@dataclass
class Params:
    start: str = "20150101"
    end: str = "20251231"
    top_n: int = 20               # 보유 종목 수
    cap_floor: float = 500        # 시가총액 하한(억) — 극소형 제외(체결 가능성)
    vol_floor: float = 5          # 거래대금 하한(억) — 유동성
    cost_oneway: float = 0.25     # 편도 매매비용(%) — 수수료+세금+슬리피지 근사


@dataclass
class Result:
    dates: list[str]
    equity: list[float]           # 전략 누적(1.0 시작)
    monthly: list[float]          # 전략 월수익률
    bench_equity: list[float]     # 코스피 누적
    bench_monthly: list[float]
    holdings: list[list[str]] = field(default_factory=list)


def _select(date: str, p: Params) -> list[str]:
    """해당일 유니버스에서 PER·PBR 순위합 상위 N종목 선정."""
    fund = data.fundamental(date)
    cap = data.market_cap(date)

    df = fund[(fund["PER"] > 0) & (fund["PBR"] > 0)].copy()
    # 규모·유동성 필터 (억 단위 환산)
    df = df.join(cap[["시가총액", "거래대금"]])
    df = df[(df["시가총액"] / 1e8 >= p.cap_floor) & (df["거래대금"] / 1e8 >= p.vol_floor)]
    if df.empty:
        return []
    # 마법공식식: 각 지표 오름차순 순위(작을수록 좋음) 합산
    df["rank"] = df["PER"].rank() + df["PBR"].rank()
    return df.nsmallest(p.top_n, "rank").index.tolist()


def run(p: Params = Params()) -> Result:
    dates = data.rebalance_dates(p.start, p.end)
    kospi = data.kospi(p.start, p.end)

    equity, monthly, holdings = [1.0], [], []
    bench_equity, bench_monthly = [1.0], []
    prev: set[str] = set()

    for d0, d1 in zip(dates[:-1], dates[1:]):
        picks = _select(d0, p)
        pc = data.price_change(d0, d1)

        # 보유 종목 수익률(동일비중). 기간 중 상폐/정지로 표에서 빠지면 0 처리(보수적).
        rets = [pc.loc[t, "등락률"] / 100 if t in pc.index else 0.0 for t in picks]
        port = sum(rets) / len(rets) if rets else 0.0

        # 거래비용: 신규 편입/이탈 비율 × 편도비용 × 양방향
        cur = set(picks)
        turnover = len(cur - prev) / max(len(cur), 1)
        cost = 2 * (p.cost_oneway / 100) * turnover
        net = port - cost

        equity.append(equity[-1] * (1 + net))
        monthly.append(net)
        holdings.append(picks)
        prev = cur

        # 벤치마크: 같은 기간 코스피 등락
        b = _bench_ret(kospi, d0, d1)
        bench_equity.append(bench_equity[-1] * (1 + b))
        bench_monthly.append(b)

    return Result(dates, equity, monthly, bench_equity, bench_monthly, holdings)


def _bench_ret(kospi, d0: str, d1: str) -> float:
    """코스피 [d0,d1] 수익률. 인덱스는 Timestamp라 근접 조회."""
    import pandas as pd
    s = kospi.loc[pd.Timestamp(d0):pd.Timestamp(d1)]
    if len(s) < 2:
        return 0.0
    return s.iloc[-1] / s.iloc[0] - 1
