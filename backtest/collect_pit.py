"""F-Score용 과거 재무 사전수집기 (느리게·재개형·실패내성).

백테스트 루프 중 대량 DART 호출이 rate-limit를 유발 → 수집을 분리한다.
필요한 (corp, year) 집합을 KRX 가치풀에서 계산하고, 미캐시분만 천천히 받는다.
- 캐시된 건 건너뜀(재개형). 실패는 로그 후 계속 → 재실행으로 메움.
- 캐시가 다 차면 `python -m backtest.run --compare` 는 DART 없이 즉시 돈다.

사용법:
  python -m backtest.collect_pit                 # 기본(2015~2025, pool100)
  python -m backtest.collect_pit --throttle 0.4  # 더 느리게(차단 회피)
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector import config
from . import data, pit_data
from .engine import Params


def needed_pairs(p: Params) -> set[tuple[str, int]]:
    """백테스트가 건드릴 (corp_code, year) 집합. KRX·CORPCODE 캐시만 사용(DART 안 씀)."""
    dates = data.rebalance_dates(p.start, p.end)
    cmap = pit_data.corp_map()
    need: set[tuple[str, int]] = set()
    for d0 in dates[:-1]:
        fund = data.fundamental(d0)
        cap = data.market_cap(d0)
        df = fund[(fund["PER"] > 0) & (fund["PBR"] > 0)].copy()
        df = df.join(cap[["시가총액", "거래대금"]])
        df = df[(df["시가총액"] / 1e8 >= p.cap_floor) & (df["거래대금"] / 1e8 >= p.vol_floor)]
        df["rank"] = df["PER"].rank() + df["PBR"].rank()
        yd = int(d0[:4])
        for t in df.nsmallest(p.value_pool, "rank").index:
            corp = cmap.get(t)
            if corp:
                for y in (yd - 1, yd - 2, yd - 3):   # as_of가 볼 수 있는 연도
                    need.add((corp, y))
    return need


def _cached_pairs() -> set[tuple[str, int]]:
    out = set()
    for f in glob.glob(str(config.CACHE_DIR / "fin_*_11011_*.json")):
        parts = os.path.basename(f).split("_")     # fin_<corp>_<year>_11011_<fs>.json
        out.add((parts[1], int(parts[2])))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="F-Score 과거재무 사전수집(재개형)")
    ap.add_argument("--start", default="20150101")
    ap.add_argument("--end", default="20251231")
    ap.add_argument("--value-pool", type=int, default=100)
    ap.add_argument("--throttle", type=float, default=0.3, help="호출 간 대기(초)")
    args = ap.parse_args()

    p = Params(start=args.start, end=args.end, value_pool=args.value_pool)
    pit_data._THROTTLE = args.throttle          # 수집 속도 조절

    need = needed_pairs(p)
    todo = sorted(need - _cached_pairs())
    print(f"필요 {len(need):,} · 캐시됨 {len(need)-len(todo):,} · 받을 것 {len(todo):,} "
          f"(throttle {args.throttle}s)", flush=True)

    ok = fail = 0
    for i, (corp, year) in enumerate(todo, 1):
        try:
            pit_data.annual(corp, year)         # 캐시에 저장됨(값 무관)
            ok += 1
        except Exception as e:                  # 실패내성: 로그 후 계속
            fail += 1
            if fail <= 20:
                print(f"  skip {corp}/{year}: {type(e).__name__}", flush=True)
        if i % 100 == 0:
            print(f"  {i}/{len(todo)}  (성공 {ok}, 실패 {fail})", flush=True)

    remain = len(sorted(need - _cached_pairs()))
    print(f"\n완료: 성공 {ok} · 실패 {fail} · 남음 {remain}")
    if remain:
        print("남은 게 있으면 잠시 후 다시 실행하면 이어받습니다(캐시 재개형).")
    else:
        print("전량 수집 완료 → `python -m backtest.run --compare` 즉시 실행 가능.")


if __name__ == "__main__":
    main()
