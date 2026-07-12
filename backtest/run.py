"""백테스트 실행·리포트.

사용법:
  python -m backtest.run                       # 기본(2015~2025, 저PBR+저PER 상위20)
  python -m backtest.run --start 20180101 --end 20241231 --top 30
  python -m backtest.run --cost 0.4 --cap-floor 1000

과최적화 방어를 위해 전체구간과 함께 in/out-of-sample(전/후반 분할)을 같이 출력한다.
"""
from __future__ import annotations

import argparse
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from . import metrics
from .engine import Params, Result, run


def _report(title: str, r: Result) -> None:
    months = len(r.monthly)
    s_cagr = metrics.cagr(r.equity, months)
    b_cagr = metrics.cagr(r.bench_equity, months)
    print(f"\n── {title}  ({r.dates[0]}~{r.dates[-1]}, {months}개월) ──")
    print(f"  {'':10s} {'전략':>12s} {'코스피':>12s}")
    print(f"  {'누적수익':10s} {metrics.total_return(r.equity):>11.1f}% {metrics.total_return(r.bench_equity):>11.1f}%")
    print(f"  {'CAGR':10s} {s_cagr:>11.1f}% {b_cagr:>11.1f}%")
    print(f"  {'MDD':10s} {metrics.mdd(r.equity):>11.1f}% {metrics.mdd(r.bench_equity):>11.1f}%")
    print(f"  {'샤프':10s} {metrics.sharpe(r.monthly):>12.2f} {metrics.sharpe(r.bench_monthly):>12.2f}")
    print(f"  {'월간승률':10s} {metrics.win_rate_vs(r.monthly, r.bench_monthly):>11.1f}%  (코스피 대비)")
    print(f"  {'초과CAGR':10s} {s_cagr - b_cagr:>+11.1f}%p")


def _slice(r: Result, i0: int, i1: int) -> Result:
    """월 인덱스 [i0,i1) 구간으로 잘라 새 Result (누적 1.0 재시작)."""
    dates = r.dates[i0:i1 + 1]
    def renorm(eq):
        base = eq[i0]
        return [v / base for v in eq[i0:i1 + 1]]
    return Result(dates, renorm(r.equity), r.monthly[i0:i1],
                  renorm(r.bench_equity), r.bench_monthly[i0:i1], r.holdings[i0:i1])


def main() -> None:
    ap = argparse.ArgumentParser(description="저PBR+저PER 백테스트")
    ap.add_argument("--start", default="20150101")
    ap.add_argument("--end", default="20251231")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--cap-floor", type=float, default=500)
    ap.add_argument("--vol-floor", type=float, default=5)
    ap.add_argument("--cost", type=float, default=0.25, help="편도 매매비용(%)")
    args = ap.parse_args()

    p = Params(start=args.start, end=args.end, top_n=args.top,
               cap_floor=args.cap_floor, vol_floor=args.vol_floor,
               cost_oneway=args.cost)
    print(f"규칙: 저PBR+저PER 순위합 상위 {p.top_n} · 월리밸런싱 · "
          f"시총≥{p.cap_floor:.0f}억·거래≥{p.vol_floor:.0f}억 · 편도비용 {p.cost_oneway}%")
    print("데이터 수집/캐시 중… (첫 실행은 몇 분, 이후 캐시라 빠름)")

    r = run(p)
    _report("전체구간", r)

    # in/out-of-sample: 전반/후반 반으로 분할 → 과최적화 점검
    mid = len(r.monthly) // 2
    _report("전반(in-sample)", _slice(r, 0, mid))
    _report("후반(out-of-sample)", _slice(r, mid, len(r.monthly)))

    print("\n※ 주의: 등락률은 분할·배당 보정 근사, 상폐 종목은 0수익 처리(보수적).")
    print("  결과가 좋아도 규칙 확정 아님 — 파라미터 민감도·거래비용 가정 재확인 필요.")


if __name__ == "__main__":
    main()
