"""수집기 진입점 — data.json 생성.

사용법:
  python -m collector.build --sample            # 키 없이 스키마 검증용 더미 data.json
  python -m collector.build --limit 30          # DART 실데이터, 앞 30종목만(테스트)
  python -m collector.build                      # DART 실데이터 전체 (하루 1회 운영)
  python -m collector.build --year 2024          # 기준 연도 지정

출력 스키마는 CLAUDE.md 2절 data.json 계약을 따른다. 뷰어(screener_skeleton.html)의
DATA_URL 에 이 파일 주소를 넣으면 그대로 연결된다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta

# Windows 콘솔(cp949)에서도 한글·기호 출력이 깨지지 않게 UTF-8 강제.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from . import config
from . import dart
from . import metrics

KST = timezone(timedelta(hours=9))

# --sample 모드용 더미 (뷰어의 내장 더미와 동일 — 배관 검증용)
_SAMPLE_ITEMS = [
    {"name": "가온테크",   "code": "000001", "sector": "반도체",  "cap": 3200, "vol": 180, "roe": 22, "per": 9,  "pbr": 1.4, "debt": 45,  "risk": False},
    {"name": "세림바이오", "code": "000002", "sector": "바이오",  "cap": 1500, "vol": 90,  "roe": 18, "per": 14, "pbr": 2.6, "debt": 60,  "risk": False},
    {"name": "한빛소재",   "code": "000003", "sector": "2차전지", "cap": 5400, "vol": 260, "roe": 16, "per": 11, "pbr": 1.8, "debt": 110, "risk": False},
    {"name": "대성산업",   "code": "000004", "sector": "산업재",  "cap": 8900, "vol": 140, "roe": 12, "per": 7,  "pbr": 0.8, "debt": 95,  "risk": False},
    {"name": "미래금융지주","code": "000005","sector": "금융",    "cap": 12000,"vol": 300, "roe": 11, "per": 6,  "pbr": 0.5, "debt": 0,   "risk": False},
]


def build_sample() -> dict:
    return {
        "updated": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "SAMPLE",
        "items": _SAMPLE_ITEMS,
    }


def build_real(bsns_year: str, reprt_code: str, limit: int | None,
               throttle: float) -> dict:
    corps = list(dart.iter_listed(limit=limit))
    items: list[dict] = []
    for i, c in enumerate(corps, 1):
        rows = dart.fetch_financials(c.corp_code, bsns_year, reprt_code,
                                     throttle=throttle)
        if not rows:
            continue
        m = metrics.compute(rows)
        if m.roe is None and m.debt is None:      # 재무 파싱 실패 → 스킵
            continue
        items.append({
            "name": c.name,
            "code": c.stock_code,
            "sector": "",                          # 업종 매핑은 이후 보강(DART company.induty)
            "cap": m.cap,                          # KIS 연동 전까지 None
            "vol": m.vol,                          # KIS 연동 전까지 None
            "roe": m.roe,
            "per": m.per,                          # KIS 연동 전까지 None
            "pbr": m.pbr,                          # KIS 연동 전까지 None
            "debt": m.debt,
            "risk": metrics.is_risky(rows, m),
        })
        if i % 100 == 0:
            print(f"  ...{i}/{len(corps)} 처리, 수집 {len(items)}건")

    return {
        "updated": datetime.now(KST).isoformat(timespec="seconds"),
        "source": f"DART({bsns_year}/{reprt_code})",
        "items": items,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="재무 스크리너 수집기")
    p.add_argument("--sample", action="store_true",
                   help="키 없이 스키마 검증용 더미 data.json 생성")
    p.add_argument("--limit", type=int, default=None,
                   help="상장사 앞 N개만 처리(테스트)")
    p.add_argument("--year", default=str(datetime.now(KST).year - 1),
                   help="기준 사업연도(기본: 작년)")
    p.add_argument("--report", default="annual",
                   choices=list(config.REPRT_CODE.keys()),
                   help="보고서 종류(annual/half/q1/q3)")
    p.add_argument("--throttle", type=float, default=0.0,
                   help="종목당 요청 간 대기(초) — 호출 한도 여유용")
    args = p.parse_args()

    if args.sample:
        payload = build_sample()
    else:
        if not config.has_dart_key():
            raise SystemExit(
                "DART_API_KEY 없음. .env 에 키를 채우거나 collector/README.md 발급 안내를 참조,\n"
                "또는 지금은 `python -m collector.build --sample` 로 배관만 확인하세요.")
        payload = build_real(args.year, config.REPRT_CODE[args.report],
                             args.limit, args.throttle)

    config.DATA_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ {config.DATA_JSON}  ({len(payload['items'])}종목, source={payload['source']})")


if __name__ == "__main__":
    main()
