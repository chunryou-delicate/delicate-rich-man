# 수집기 (Collector)

DART(재무) + KRX(시세)에서 국내 상장사 데이터를 받아 지표를 계산하고,
뷰어([../screener_skeleton.html](../screener_skeleton.html))가 읽는 `data.json`을 만든다.

> 아키텍처 배경: [../CLAUDE.md](../CLAUDE.md) 2절. 수집(파이썬, 키 보유) ↔ 조회(HTML, 키 없음) 분리.

## 구조

```
collector/
  config.py    설정·경로·키 로딩 (.env 에서만 읽음)
  dart.py      DART 클라이언트 — corp_code 목록 + 재무제표 조회 + 캐싱
  krx.py       KRX 시세(pykrx) — 시총·거래대금·PER·PBR 스냅샷 (KRX 로그인)
  metrics.py   재무 계정 → ROE·부채비율 계산 (자본잠식이면 null)
  build.py     진입점 — DART 재무 + KRX 시세 병합 → data.json 생성
```

## 설치

```bash
pip install -r ../requirements.txt
```

## 실행

```bash
# 키 없이 배관 확인 — 스키마대로 더미 data.json 생성
python -m collector.build --sample

# 소량 테스트 (앞 30종목만)
python -m collector.build --limit 30

# 전체 (하루 1회 운영). 재무는 캐시라 이후 재실행은 빠름
python -m collector.build

# 시세 없이 재무 지표만
python -m collector.build --no-price

# 기준 연도/보고서 지정 (기본: 작년 · 사업보고서)
python -m collector.build --year 2024 --report half   # annual/half/q1/q3
```

## 필요한 키 (둘 다 무료)

`.env.example` 을 `.env` 로 복사하고 채운다. `.env` 는 `.gitignore` 됨.

### 1) DART OpenAPI 인증키 — 재무제표
1. https://opendart.fss.or.kr → **인증키 신청/관리 → 인증키 신청**
2. 메일로 인증키(40자 hex) 즉시 발급 → `.env` 에 `DART_API_KEY=...`
3. 상장사 ~2,700개는 하루 1회면 충분. 응답은 `.cache/` 에 저장돼 재실행 시 재호출 안 함.

### 2) KRX Data Marketplace 로그인 — 시세
> 2025-12-27부터 KRX 정보데이터시스템이 회원제로 개편됨(봇 수집 차단 목적). 조회는 **무료**.
1. https://data.krx.co.kr 에서 **회원가입** (자체 아이디/비밀번호 — 네이버·카카오 SSO 아님)
2. `.env` 에 `KRX_ID=...`, `KRX_PW=...`
3. pykrx 가 이 값으로 자동 로그인해 시세를 받아온다. EOD(전일 종가) 기준.

> KIS(한국투자증권)는 **실제 주문 실행(실전 매매)** 단계에서만 필요. 지금은 비워둠.

## data.json 필드별 소스

| 필드 | 소스 | 상태 |
|------|------|------|
| roe, debt | DART 재무 | ✅ (자본잠식이면 null) |
| cap, vol, per, pbr | KRX(pykrx) | ✅ EOD 시세 |
| risk | DART(적자·자본잠식) | 🔶 재무 기준만 (관리종목 플래그는 이후) |
| sector | DART 업종코드 | ⬜ `""` (한글 섹터 매핑 이후) |

현재 커버리지: 2,701종목 · roe 2,584 · debt 2,690 · cap/vol 2,571 · pbr 2,452 · per 1,503
(per는 적자 종목이 0→null 처리되어 상대적으로 적음)

## 주의점

- **날짜**: `krx.py` 는 PER>0 실값이 있는 최근 영업일을 자동 선택(주말/휴장일 0값 회피).
- **자본잠식**: 자기자본 ≤ 0 이면 ROE·부채비율이 무의미하므로 null. 위험 플래그는 유지.
- **KRX 미매칭 ~130종목**: DART엔 있으나 KRX에 없는 종목(코넥스·신규/폐지 등)은 cap 등이 null.
  뷰어의 자격 필터가 값 없으면 탈락시켜 걸러냄.

## 다음 작업 (예정)

- DART `company.json` 업종코드 → 한글 섹터 매핑 (분야 필터용)
- 관리종목/거래정지 플래그 소스 연결
- (백테스트 단계) pykrx 과거 시세·PER·PBR 일자별 수집
