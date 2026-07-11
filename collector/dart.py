"""DART OpenAPI 클라이언트.

두 가지만 한다:
  1) corp_code 목록 다운로드 (상장사 고유번호 + 종목코드)
  2) 단일회사 전체 재무제표 조회 (fnlttSinglAcntAll)

응답은 .cache/ 에 저장해 하루 안에 재실행 시 재호출을 막는다(분기 지연 있는 데이터라 캐싱 필수 — CLAUDE.md).
"""
from __future__ import annotations

import io
import json
import time
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import requests

from . import config

BASE = "https://opendart.fss.or.kr/api"
_SESSION = requests.Session()


@dataclass(frozen=True)
class Corp:
    """상장사 한 곳의 식별 정보."""
    corp_code: str   # DART 8자리 고유번호
    name: str        # 종목명
    stock_code: str  # 6자리 종목코드 (상장사만 존재)


# ── corp_code 목록 ────────────────────────────────────────
def download_corp_codes(force: bool = False) -> list[Corp]:
    """전체 corp_code 목록을 받아 상장사(종목코드 있는 곳)만 반환.

    DART corpCode.xml 은 ZIP(CORPCODE.xml) 로 온다. 캐시에 XML을 풀어둔다.
    """
    config.CACHE_DIR.mkdir(exist_ok=True)
    xml_path = config.CACHE_DIR / "CORPCODE.xml"

    if force or not xml_path.exists():
        if not config.has_dart_key():
            raise RuntimeError("DART_API_KEY 없음 — .env 에 키를 채우거나 발급 안내를 참조하세요.")
        res = _SESSION.get(f"{BASE}/corpCode.xml",
                           params={"crtfc_key": config.DART_API_KEY}, timeout=30)
        res.raise_for_status()
        # 키 오류 등은 ZIP이 아니라 JSON 에러로 온다.
        if res.headers.get("content-type", "").startswith("application/json"):
            raise RuntimeError(f"DART corpCode 오류: {res.text[:200]}")
        with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
            zf.extractall(config.CACHE_DIR)

    return _parse_corp_codes(xml_path)


def _parse_corp_codes(xml_path: Path) -> list[Corp]:
    root = ET.parse(xml_path).getroot()
    corps: list[Corp] = []
    for el in root.iter("list"):
        stock = (el.findtext("stock_code") or "").strip()
        if not stock:                         # 종목코드 없으면 비상장 → 제외
            continue
        corps.append(Corp(
            corp_code=(el.findtext("corp_code") or "").strip(),
            name=(el.findtext("corp_name") or "").strip(),
            stock_code=stock,
        ))
    return corps


# ── 재무제표 조회 ─────────────────────────────────────────
def fetch_financials(corp_code: str, bsns_year: str, reprt_code: str,
                     force: bool = False, throttle: float = 0.0) -> list[dict]:
    """단일회사 전체 재무제표(fnlttSinglAcntAll) 계정 리스트 반환.

    연결(CFS) 우선, 없으면 별도(OFS). 결과 없으면 빈 리스트.
    """
    for fs_div in config.FS_DIV_PRIORITY:
        rows = _fetch_one(corp_code, bsns_year, reprt_code, fs_div, force, throttle)
        if rows:
            return rows
    return []


def _fetch_one(corp_code, bsns_year, reprt_code, fs_div, force, throttle) -> list[dict]:
    config.CACHE_DIR.mkdir(exist_ok=True)
    cache_key = f"fin_{corp_code}_{bsns_year}_{reprt_code}_{fs_div}.json"
    cache_path = config.CACHE_DIR / cache_key

    if not force and cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        if not config.has_dart_key():
            raise RuntimeError("DART_API_KEY 없음 — .env 에 키를 채우세요.")
        res = _SESSION.get(f"{BASE}/fnlttSinglAcntAll.json", timeout=30, params={
            "crtfc_key": config.DART_API_KEY,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        })
        res.raise_for_status()
        payload = res.json()
        cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        if throttle:
            time.sleep(throttle)

    # status "000" = 정상, "013" = 데이터 없음
    if payload.get("status") != "000":
        return []
    return payload.get("list", [])


def iter_listed(limit: int | None = None) -> Iterator[Corp]:
    """상장사를 순회. limit 지정 시 앞에서 N개만(테스트용)."""
    corps = download_corp_codes()
    for i, c in enumerate(corps):
        if limit is not None and i >= limit:
            return
        yield c
