# 수집기 (Collector)

DART OpenAPI에서 국내 상장사 재무제표를 받아 지표를 계산하고,
뷰어([../screener_skeleton.html](../screener_skeleton.html))가 읽는 `data.json`을 만든다.

> 아키텍처 배경: [../CLAUDE.md](../CLAUDE.md) 2절. 수집(파이썬, 키 보유) ↔ 조회(HTML, 키 없음) 분리.

## 구조

```
collector/
  config.py    설정·경로·API 키 로딩 (.env 에서만 읽음)
  dart.py      DART 클라이언트 — corp_code 목록 + 재무제표 조회 + 캐싱
  metrics.py   계정 리스트 → ROE·부채비율 계산 (시세 지표는 KIS 연동 후)
  build.py     진입점 — data.json 생성
```

## 설치

```bash
pip install -r ../requirements.txt
```

## 실행

```bash
# 1) 키 없이 배관 확인 — 스키마대로 더미 data.json 생성
python -m collector.build --sample

# 2) DART 키 넣은 뒤 실데이터 (앞 30종목만 테스트)
python -m collector.build --limit 30

# 3) 전체 (하루 1회 운영). 호출 한도 여유 두려면 --throttle 0.1
python -m collector.build --throttle 0.1
```

## DART API 키 발급 (무료, 즉시)

1. https://opendart.fss.or.kr 접속 → 상단 **인증키 신청/관리 → 인증키 신청**
2. 이메일·이름 등 입력 후 신청 → **메일로 인증키(40자 hex) 즉시 발급**
3. 프로젝트 루트에서 `.env.example` 을 `.env` 로 복사하고 키를 채움:
   ```bash
   cp .env.example .env
   # .env 안에서  DART_API_KEY=발급받은키  로 수정
   ```
4. `.env` 는 `.gitignore` 되어 깃에 안 올라감 (키 유출 방지).

- 무료 한도: 분당/일일 호출 제한 있음(대량). 상장사 ~2,500개는 하루 1회면 충분.
- 재무제표는 분기 지연 있음 → 응답은 `.cache/` 에 저장해 재실행 시 재호출 안 함.

## 지금 채워지는 값 / 나중 채워지는 값

| 필드 | 소스 | 현재 |
|------|------|------|
| roe, debt | DART 재무 | ✅ 실데이터 |
| net_income, equity(원값) | DART 재무 | ✅ (PER/PBR 계산 재료) |
| cap, vol, per, pbr | KIS 시세 | ⬜ `null` (KIS 연동 후) |
| sector | DART 업종코드 | ⬜ `""` (매핑 이후 보강) |
| risk | DART(적자·자본잠식) + KRX(관리종목) | 🔶 일부 (재무 기준만) |

## 다음 작업 (예정)

- KIS 시세 연동 → cap·vol·per·pbr 채우기 (`kis.py` 추가 예정)
- DART `company.json` 업종코드 → 한글 섹터 매핑
- 관리종목/거래정지 플래그 소스 연결
