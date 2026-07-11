"""설정·경로·API 키 로딩.

키는 코드에 박지 않는다. .env(또는 실제 환경변수)에서만 읽는다.
CLAUDE.md 아키텍처: "API 키는 수집기에만" — 이 파일이 그 경계.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()  # 프로젝트 루트의 .env 를 환경변수로 로드 (있으면)
except ImportError:
    # python-dotenv 미설치여도 실제 환경변수로는 동작하게 둔다.
    pass

# ── 경로 ──────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent      # 프로젝트 루트
CACHE_DIR = ROOT / ".cache"                          # DART 응답 캐시 (gitignore)
DATA_JSON = ROOT / "data.json"                       # 수집기 출력 = 뷰어 입력

# ── API 키 ────────────────────────────────────────────────
DART_API_KEY = os.environ.get("DART_API_KEY", "").strip()
KIS_APP_KEY = os.environ.get("KIS_APP_KEY", "").strip()
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET", "").strip()

# ── DART 리포트 코드 (분기/연간 선택용) ──────────────────
# CLAUDE.md 8-1 '연간 vs 분기'는 실데이터 보며 확정. 기본은 사업보고서(연간).
REPRT_CODE = {
    "annual": "11011",   # 사업보고서(연간)
    "half":   "11012",   # 반기보고서
    "q1":     "11013",   # 1분기보고서
    "q3":     "11014",   # 3분기보고서
}

# 연결(CFS) 우선, 없으면 별도(OFS)로 폴백.
FS_DIV_PRIORITY = ["CFS", "OFS"]


def has_dart_key() -> bool:
    return bool(DART_API_KEY)


def has_kis_key() -> bool:
    return bool(KIS_APP_KEY and KIS_APP_SECRET)
