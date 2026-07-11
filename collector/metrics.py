"""재무제표 계정 리스트 → 스크리너 지표 계산.

DART만으로 구할 수 있는 것: ROE, 부채비율, 매출/이익 (그리고 순이익·자기자본 원값).
시세가 필요한 것(시가총액·거래대금·PER·PBR): KIS 연동 전까지 None.
지표 정의는 CLAUDE.md 3절을 따른다.
"""
from __future__ import annotations

from dataclasses import dataclass

# DART 계정명은 회사마다 표기가 조금씩 다르다. 후보군을 두고 매칭한다.
# (sj_div: BS=재무상태표, IS=손익, CIS=포괄손익)
_ACCOUNT_ALIASES = {
    "equity":     ["자본총계"],                       # 자기자본
    "liabilities":["부채총계"],                       # 부채
    "net_income": ["당기순이익", "당기순이익(손실)",
                   "연결당기순이익"],                  # 순이익
    "revenue":    ["매출액", "수익(매출액)", "영업수익"],
    "op_income":  ["영업이익", "영업이익(손실)"],
}


@dataclass
class Metrics:
    roe: float | None = None      # %  = 순이익 / 자기자본 × 100
    debt: float | None = None     # %  = 부채총계 / 자기자본 × 100
    per: float | None = None      # 배 (KIS 시세 필요)
    pbr: float | None = None      # 배 (KIS 시세 필요)
    cap: float | None = None      # 억 (KIS 시세 필요)
    vol: float | None = None      # 억 (KIS 시세 필요)
    # 원값 (KIS로 PER/PBR 계산할 때 재사용)
    net_income: float | None = None
    equity: float | None = None


def _amount(rows: list[dict], keys: list[str]) -> float | None:
    """계정 리스트에서 이름이 일치하는 첫 계정의 당기금액을 숫자로."""
    for row in rows:
        name = (row.get("account_nm") or "").strip()
        if name in keys:
            raw = (row.get("thstrm_amount") or "").replace(",", "").strip()
            if raw in ("", "-"):
                return None
            try:
                return float(raw)
            except ValueError:
                return None
    return None


def compute(rows: list[dict]) -> Metrics:
    equity = _amount(rows, _ACCOUNT_ALIASES["equity"])
    liab = _amount(rows, _ACCOUNT_ALIASES["liabilities"])
    net = _amount(rows, _ACCOUNT_ALIASES["net_income"])

    m = Metrics(net_income=net, equity=equity)
    if equity and equity != 0:
        if net is not None:
            m.roe = round(net / equity * 100, 1)
        if liab is not None:
            m.debt = round(liab / equity * 100, 1)
    return m


def is_risky(rows: list[dict], m: Metrics) -> bool:
    """구조적 위험 신호 플래그 (자격 필터 ③용).

    지금은 DART 재무만으로 판단 가능한 것: 적자(순이익<0), 자본잠식(자본<0).
    관리종목·거래정지 여부는 별도 소스(KRX/KIS) 필요 → 이후 보강.
    """
    if m.equity is not None and m.equity <= 0:
        return True                      # 자본잠식
    if m.net_income is not None and m.net_income < 0:
        return True                      # 적자
    return False
