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
from dataclasses import replace

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


def _cagr_of(r: Result, i0: int, i1: int) -> float:
    s = _slice(r, i0, i1)
    return metrics.cagr(s.equity, len(s.monthly))


def _verdict(base: Result, qual: Result) -> None:
    """사전 확정 기준(README): CAGR·MDD·in/out 모두 개선돼야 '품질 필터 유효'."""
    n = len(base.monthly); mid = n // 2
    full_cagr = metrics.cagr(qual.equity, n) > metrics.cagr(base.equity, n)
    full_mdd = metrics.mdd(qual.equity) > metrics.mdd(base.equity)         # 덜 깊음
    in_ok = _cagr_of(qual, 0, mid) > _cagr_of(base, 0, mid)
    out_ok = _cagr_of(qual, mid, n) > _cagr_of(base, mid, n)

    print("\n" + "=" * 46)
    print("판정 (사전 확정 기준 — 모두 충족해야 '유효')")
    print(f"  CAGR 개선(전체)        : {'✅' if full_cagr else '❌'}")
    print(f"  MDD 개선(전체)         : {'✅' if full_mdd else '❌'}")
    print(f"  in-sample CAGR 개선    : {'✅' if in_ok else '❌'}")
    print(f"  out-of-sample CAGR 개선: {'✅' if out_ok else '❌'}")
    ok = full_cagr and full_mdd and in_ok and out_ok
    print("  " + "-" * 42)
    print(f"  → {'✅ 품질 필터 유효' if ok else '❌ 채택 보류 (한쪽만 개선 = 과최적화 의심)'}")
    print("=" * 46)


def _run_and_report(title: str, p: Params) -> Result:
    r = run(p)
    _report(f"{title} 전체", r)
    mid = len(r.monthly) // 2
    _report(f"{title} 전반(in)", _slice(r, 0, mid))
    _report(f"{title} 후반(out)", _slice(r, mid, len(r.monthly)))
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description="저PBR+저PER (+품질) 백테스트")
    ap.add_argument("--start", default="20150101")
    ap.add_argument("--end", default="20251231")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--cap-floor", type=float, default=500)
    ap.add_argument("--vol-floor", type=float, default=5)
    ap.add_argument("--cost", type=float, default=0.25, help="편도 매매비용(%)")
    ap.add_argument("--fscore", action="store_true", help="F-Score 품질 필터 켜기")
    ap.add_argument("--value-pool", type=int, default=100, help="F-Score 계산할 가치 상위 풀")
    ap.add_argument("--fscore-min", type=int, default=6, help="F-Score 통과 컷(8점 만점)")
    ap.add_argument("--compare", action="store_true",
                    help="가치only vs 가치+품질 비교 + 사전기준 판정")
    args = ap.parse_args()

    base = Params(start=args.start, end=args.end, top_n=args.top,
                  cap_floor=args.cap_floor, vol_floor=args.vol_floor,
                  cost_oneway=args.cost)
    print("데이터 수집/캐시 중… (첫 실행은 몇 분, 이후 캐시라 빠름)")

    if args.compare:
        qual = replace(base, use_fscore=True, value_pool=args.value_pool,
                       fscore_min=args.fscore_min)
        rb = _run_and_report("[가치only]", base)
        rq = _run_and_report("[가치+품질]", qual)
        _verdict(rb, rq)
    else:
        p = replace(base, use_fscore=args.fscore, value_pool=args.value_pool,
                    fscore_min=args.fscore_min)
        _run_and_report("전략", p)

    print("\n※ 등락률은 분할·배당 보정 근사, 상폐 종목은 0수익 처리(보수적).")


if __name__ == "__main__":
    main()
