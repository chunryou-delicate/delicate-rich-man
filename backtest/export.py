"""백테스트 결과 → backtest.json (뷰어 입력).

스크리너와 동일 골격: 엔진이 JSON을 뱉고 HTML 뷰어가 그린다.
담는 것: 자산곡선(가치only·가치+품질·코스피), 성과지표, 월별 보유종목(드릴다운용),
거시 이벤트(전쟁·금리·폭락) 마커.  모두 캐시에서 계산 — DART 안 씀.

사용법:  python -m backtest.export
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector import config
from . import data, metrics
from .engine import Params, run

KST = timezone(timedelta(hours=9))

# 거시 이벤트 (국면 오버레이) — 날짜는 YYYYMM
EVENTS = [
    ("201506", "메르스"),
    ("201611", "트럼프 당선"),
    ("201801", "미중 무역전쟁"),
    ("202003", "코로나 폭락"),
    ("202011", "유동성 랠리"),
    ("202202", "러·우 전쟁"),
    ("202207", "금리 급등"),
    ("202310", "고금리 장기화"),
]


def _iso(ymd: str) -> str:
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"


def _metrics(equity, monthly):
    n = len(monthly)
    return {
        "cagr": round(metrics.cagr(equity, n), 1),
        "mdd": round(metrics.mdd(equity), 1),
        "sharpe": round(metrics.sharpe(monthly), 2),
        "total": round(metrics.total_return(equity), 1),
    }


def _holdings_detail(dates, holdings):
    """월별 보유종목 + 종목명 + 그달 수익률 (드릴다운용). price_change 캐시 사용."""
    out = []
    for i, picks in enumerate(holdings):
        d0, d1 = dates[i], dates[i + 1]
        pc = data.price_change(d0, d1)
        rows = []
        for t in picks:
            nm = pc.loc[t, "종목명"] if t in pc.index else t
            ret = round(float(pc.loc[t, "등락률"]), 1) if t in pc.index else 0.0
            rows.append({"code": t, "name": str(nm), "ret": ret})
        out.append({"date": _iso(d0), "stocks": rows})
    return out


def main() -> None:
    p_base = Params(start="20150101", end="20251231", top_n=20)
    p_qual = replace(p_base, use_fscore=True)

    print("백테스트 실행(캐시)…", flush=True)
    rb = run(p_base)
    rq = run(p_qual)

    dates = [_iso(d) for d in rq.dates]
    payload = {
        "generated": datetime.now(KST).isoformat(timespec="seconds"),
        "rule": "저PBR+저PER 순위합 상위20 + F-Score≥6 (월 리밸런싱)",
        "period": {"start": dates[0], "end": dates[-1], "months": len(rq.monthly)},
        "dates": dates,
        "series": {
            "quality": [round(v, 4) for v in rq.equity],       # 가치+품질
            "value": [round(v, 4) for v in rb.equity],          # 가치only
            "kospi": [round(v, 4) for v in rq.bench_equity],
        },
        "monthly": {
            "quality": [round(v, 4) for v in rq.monthly],
            "kospi": [round(v, 4) for v in rq.bench_monthly],
        },
        "metrics": {
            "quality": _metrics(rq.equity, rq.monthly),
            "value": _metrics(rb.equity, rb.monthly),
            "kospi": _metrics(rq.bench_equity, rq.bench_monthly),
        },
        "holdings": _holdings_detail(rq.dates, rq.holdings),
        "events": [{"date": _iso(ym + "01"), "label": lb} for ym, lb in EVENTS],
    }

    out = config.ROOT / "backtest.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    kb = out.stat().st_size // 1024
    print(f"✓ {out}  ({len(dates)}개월, {kb}KB)")
    print(f"  가치only CAGR {payload['metrics']['value']['cagr']}% · "
          f"가치+품질 CAGR {payload['metrics']['quality']['cagr']}% · "
          f"코스피 CAGR {payload['metrics']['kospi']['cagr']}%")


if __name__ == "__main__":
    main()
