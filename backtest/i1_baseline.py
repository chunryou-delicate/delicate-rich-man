"""I1 — 베이스라인 측정 (전략 아님, 잣대 세우기).

코스피 Buy&Hold(배당·현금·비용 반영)를 3구간별로 실측 → §1 성공 정의를 구체 수치로 확정.
INDEX_PLAN §1: 성공은 B&H 대비 CAGR 유지(≤1%p 드로다운) + MDD ≤ B&H의 60% + 칼마 ≥ 1.5×B&H.

사용법:  python -u -m backtest.i1_baseline
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from . import index_data as ix, metrics

WINDOWS = [("전체 2000-25", 2000, 2025), ("훈련 2000-12", 2000, 2012),
           ("검증 2013-19", 2013, 2019), ("테스트 2020-25", 2020, 2025)]


def _win(rets, y0, y1):
    r = rets[(rets.index.year >= y0) & (rets.index.year <= y1)]
    eq = ix.equity(r)
    n = len(r)
    return (metrics.cagr(eq, n, 12), metrics.mdd(eq),
            metrics.calmar(eq, n, 12), metrics.sharpe(list(r), 12))


def main() -> None:
    m = ix.monthly("20000101", "20251231")
    bh = ix.bh_returns(m)

    print("I1 베이스라인 — 코스피 B&H(가격+배당-비용) 구간분해", flush=True)
    print(f"{'구간':14s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} {'샤프':>6s}")
    print("-" * 44)
    res = {}
    for nm, y0, y1 in WINDOWS:
        c, md, ca, sh = _win(bh, y0, y1)
        res[nm] = (c, md, ca, sh)
        print(f"{nm:14s} {c:6.1f} {md:7.1f} {ca:6.2f} {sh:6.2f}")

    # DCA(정액적립) 참고: 매월 1단위 투입, 최종가치/총투입
    r = bh
    units, value = 0.0, 0.0
    for x in r:
        value = value * (1 + x) + 1.0     # 매월 1 투입 후 성장
        units += 1.0
    print(f"\nDCA(정액적립) 참고: 총투입 {units:.0f} → 최종가치 {value:.0f} (배수 {value/units:.2f})")

    # §1 성공선 확정 (B&H 기준)
    fc, fmd, fca, _ = res["전체 2000-25"]
    print("\n§1 성공선 (사전등록 — B&H 실측 기준):")
    print(f"  ① CAGR ≥ {fc-1.0:.1f}%  (B&H {fc:.1f}% − 1.0%p 이내 '유지')")
    print(f"  ② MDD ≤ {abs(fmd)*0.6:.0f}% (낙폭)  (B&H {abs(fmd):.0f}%의 60%)")
    print(f"  ③ 칼마 ≥ {fca*1.5:.2f}  (B&H {fca:.2f} × 1.5)")
    print(f"  ④ 연 매매 ≤ 4회, ⑤ 훈련·검증 모두 충족")


if __name__ == "__main__":
    main()
