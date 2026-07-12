"""Point-in-time 재무 수집·조회 (F-Score용).

핵심: look-ahead 방어. 리밸런싱일 D에서 "그때 실제로 공시돼 있던 재무"만 쓴다.
공시일은 DART 재무응답 rcept_no 앞 8자리(=접수일). 연간보고서는 다음 해 3~4월 공시.

F-Score는 연속 2개년 비교라 as_of(D) 는 (current, prev) 두 해치를 함께 준다.
재무 조회는 collector.dart.fetch_financials 재사용(연도별 캐시됨).
검증 기록: pit-verification.md
"""
from __future__ import annotations

from collector import dart

# F-Score 입력 계정 별칭 (옛 공시 표기차 대응 — pit-verification.md '부분' 사례 방어)
_FIELDS = {
    "net_income": ["당기순이익", "당기순이익(손실)", "연결당기순이익"],
    "cfo":        ["영업활동현금흐름", "영업활동으로인한현금흐름",
                   "영업활동으로 인한 현금흐름", "영업활동 현금흐름"],
    "assets":     ["자산총계"],
    "cur_assets": ["유동자산"],
    "cur_liab":   ["유동부채"],
    "liab":       ["부채총계"],
    "revenue":    ["매출액", "수익(매출액)", "영업수익"],
    "cogs":       ["매출원가"],
}


def _amount(rows: list[dict], keys: list[str]) -> float | None:
    for r in rows:
        if (r.get("account_nm") or "").strip() in keys:
            raw = (r.get("thstrm_amount") or "").replace(",", "").strip()
            if raw in ("", "-"):
                return None
            try:
                return float(raw)
            except ValueError:
                return None
    return None


# 대량 수집 시 DART 부하 완화(캐시 미스에만 적용). 재시도는 dart._get 이 담당.
# rate-limit 차단을 피하려 완만하게(캐시된 뒤 재실행은 이 대기 없음).
_THROTTLE = 0.2


def annual(corp_code: str, year: int) -> dict | None:
    """연간(사업보고서) 재무 → F-Score 계정 dict + 공시일(filing_date). 없으면 None."""
    rows = dart.fetch_financials(corp_code, str(year), "11011", throttle=_THROTTLE)
    if not rows:
        return None
    d = {k: _amount(rows, keys) for k, keys in _FIELDS.items()}
    d["filing_date"] = (rows[0].get("rcept_no") or "")[:8]   # YYYYMMDD
    d["year"] = year
    return d


def as_of(corp_code: str, date: str) -> tuple[dict | None, dict | None]:
    """date(YYYYMMDD) 기준 '이미 공시된' 최신 연간(current)과 직전(prev) 반환.

    look-ahead 방어: 공시일 ≤ date 인 보고서만 유효.
    보통 date 해의 전년도(FY=Yd-1) 보고서가 그 해 3~4월 공시 → 그게 최신.
    아직 공시 전(3월 이전 등)이면 FY=Yd-2 로 내려감.
    F-Score 계산 불가(둘 중 하나라도 없음)면 그대로 None 포함해 반환 — 호출측이 판단.
    """
    yd = int(date[:4])
    for cur_y in (yd - 1, yd - 2):
        cur = annual(corp_code, cur_y)
        if cur and cur["filing_date"] and cur["filing_date"] <= date:
            return cur, annual(corp_code, cur_y - 1)
    return None, None


_CORP_MAP: dict[str, str] | None = None


def corp_map() -> dict[str, str]:
    """종목코드(6자리) → corp_code(DART) 매핑. CORPCODE 기반, 1회 로드 후 메모리 캐시."""
    global _CORP_MAP
    if _CORP_MAP is None:
        _CORP_MAP = {c.stock_code: c.corp_code for c in dart.download_corp_codes()}
    return _CORP_MAP
