"""Piotroski F-Score (v1: 8항목 — '신주발행 없음' 제외).

밸류 트랩 방어용 품질 점수. 연속 2개년 연간재무를 비교해 9개(여기선 8개) 회계신호를
0/1로 채점, 합산(0~8). 높을수록 재무 품질/개선이 좋음.

⚠️ 컷오프·만점은 상수로 명시 — 나중 9항목(신주발행) 확장 대비.
   9번째(발행주식수, KRX 상장주식수 필요)를 얹으면 MAX_SCORE=9, PASS_THRESHOLD=7 로.
은행·보험·증권·리츠는 계정 구조가 달라 핵심 계정이 비어 자연히 None(제외) 처리됨.
판정 기준·설계 배경: README.md, pit-verification.md
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── 확장 대비 상수 ──────────────────────────────────────
MAX_SCORE = 8          # 현재 항목 수 (신주발행 제외). 9항목 확장 시 9.
PASS_THRESHOLD = 6     # 통과 컷 (8점 만점). 9항목 확장 시 7.

# 채점에 반드시 필요한 계정 (없으면 scoreable=False → 유니버스에서 제외)
_CORE = ["net_income", "assets", "revenue", "cfo", "cur_assets", "cur_liab", "liab", "cogs"]


@dataclass
class FScore:
    total: int | None                 # 0~8, 계산 불가면 None
    detail: dict = field(default_factory=dict)  # 항목명 → 0/1 (투명성·뷰어용)

    @property
    def scoreable(self) -> bool:
        return self.total is not None


def _bad(fin: dict | None) -> bool:
    """핵심 계정 결측 또는 분모 0 → 채점 불가."""
    if not fin:
        return True
    if any(fin.get(k) is None for k in _CORE):
        return True
    # 분모로 쓰는 값이 0이면 비율 계산 불가
    return fin["assets"] == 0 or fin["revenue"] == 0 or fin["cur_liab"] == 0


def compute(cur: dict | None, prev: dict | None) -> FScore:
    """(current, prev) 연간재무 dict → F-Score. 계산 불가면 total=None."""
    if _bad(cur) or _bad(prev):
        return FScore(total=None)

    d: dict[str, int] = {}
    # ── 수익성 (4) ──
    d["ROA>0"]     = int(cur["net_income"] > 0)
    d["CFO>0"]     = int(cur["cfo"] > 0)
    roa_c = cur["net_income"] / cur["assets"]
    roa_p = prev["net_income"] / prev["assets"]
    d["ΔROA>0"]    = int(roa_c > roa_p)
    d["CFO>순이익"] = int(cur["cfo"] > cur["net_income"])   # 이익의 현금 뒷받침
    # ── 재무건전성/유동성 (2) — 신주발행 항목은 v1 제외 ──
    d["부채비율↓"]  = int(cur["liab"] / cur["assets"] < prev["liab"] / prev["assets"])
    d["유동비율↑"]  = int(cur["cur_assets"] / cur["cur_liab"] > prev["cur_assets"] / prev["cur_liab"])
    # ── 운영효율 (2) ──
    gm_c = (cur["revenue"] - cur["cogs"]) / cur["revenue"]
    gm_p = (prev["revenue"] - prev["cogs"]) / prev["revenue"]
    d["매출총이익률↑"] = int(gm_c > gm_p)
    d["자산회전율↑"]   = int(cur["revenue"] / cur["assets"] > prev["revenue"] / prev["assets"])

    return FScore(total=sum(d.values()), detail=d)


def passes(fs: FScore, threshold: int = PASS_THRESHOLD) -> bool:
    return fs.total is not None and fs.total >= threshold
