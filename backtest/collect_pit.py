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
    """이 규칙(가치풀)이 건드릴 (corp_code, year) 집합. KRX·CORPCODE 캐시만 사용."""
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


def needed_pairs_full(p: Params) -> set[tuple[str, int]]:
    """전 종목 아카이브: 기간 중 한 번이라도 상장됐던 모든 종목 × 필요한 모든 연도.

    이걸 다 받아두면 '어떤 규칙이든' DART 없이 오프라인 실험 가능(생존편향도 완비).
    유니버스 = 각 리밸런싱일 KRX 단면의 합집합(그때 상장된 종목). 연도 = start-3 ~ end-1.
    """
    dates = data.rebalance_dates(p.start, p.end)
    cmap = pit_data.corp_map()
    years = range(int(p.start[:4]) - 3, int(p.end[:4]))
    corps: set[str] = set()
    for d0 in dates[:-1]:
        for t in data.fundamental(d0).index:       # 그 시점 상장 전 종목
            c = cmap.get(t)
            if c:
                corps.add(c)
    return {(c, y) for c in corps for y in years}


def _cached_pairs() -> set[tuple[str, int]]:
    out = set()
    for f in glob.glob(str(config.CACHE_DIR / "fin_*_11011_*.json")):
        parts = os.path.basename(f).split("_")     # fin_<corp>_<year>_11011_<fs>.json
        out.add((parts[1], int(parts[2])))
    return out


def _dart_up() -> bool:
    """빠른 단건 프로브(재시도 없음). 차단 중이면 즉시 False → 패스 스킵(헛돌기 방지)."""
    import requests
    try:
        r = requests.get("https://opendart.fss.or.kr/api/list.json", timeout=10,
                         params={"crtfc_key": config.DART_API_KEY, "corp_code": "00126380",
                                 "bgn_de": "20240101", "end_de": "20240201"})
        return r.status_code == 200
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="F-Score 과거재무 사전수집(재개형)")
    ap.add_argument("--start", default="20150101")
    ap.add_argument("--end", default="20251231")
    ap.add_argument("--value-pool", type=int, default=100)
    ap.add_argument("--throttle", type=float, default=0.3, help="호출 간 대기(초)")
    ap.add_argument("--full", action="store_true",
                    help="전 종목 10년 아카이브(어떤 규칙이든 오프라인). 대량 — 며칠 소요")
    args = ap.parse_args()

    p = Params(start=args.start, end=args.end, value_pool=args.value_pool)
    pit_data._THROTTLE = args.throttle          # 수집 속도 조절

    need = needed_pairs_full(p) if args.full else needed_pairs(p)
    todo = sorted(need - _cached_pairs())
    print(f"필요 {len(need):,} · 캐시됨 {len(need)-len(todo):,} · 받을 것 {len(todo):,} "
          f"(throttle {args.throttle}s)", flush=True)
    if not todo:
        print("전량 수집 완료 → `python -m backtest.run --compare` 즉시 실행 가능.")
        sys.exit(0)

    if not _dart_up():
        print("DART 아직 차단 중 — 이번 패스 스킵. 나중에 재시도.")
        sys.exit(2)

    ok = fail = streak = 0
    for i, (corp, year) in enumerate(todo, 1):
        try:
            pit_data.annual(corp, year)         # 캐시에 저장됨(값 무관)
            ok += 1
            streak = 0
        except Exception as e:                  # 실패내성: 로그 후 계속
            fail += 1
            streak += 1
            if fail <= 20:
                print(f"  skip {corp}/{year}: {type(e).__name__}", flush=True)
            if streak >= 12:                    # DART 재차단 추정 → 패스 중단(헛돌기 방지)
                print("  연속 실패 12회 — DART 재차단 추정, 이번 패스 중단.", flush=True)
                break
        if i % 100 == 0:
            print(f"  {i}/{len(todo)}  (성공 {ok}, 실패 {fail})", flush=True)

    remain = len(need - _cached_pairs())
    print(f"\n패스 종료: 성공 {ok} · 실패 {fail} · 남음 {remain}", flush=True)
    if remain == 0:
        print("전량 수집 완료 → run --compare 즉시 실행 가능.")
    sys.exit(0 if remain == 0 else 2)


if __name__ == "__main__":
    main()
