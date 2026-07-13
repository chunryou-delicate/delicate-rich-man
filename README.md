# delicate-rich-man

> 국내 주식 재무 스크리닝 → 백테스트 → (먼 훗날) 무인 자동매매로 가는 **단계형** 프로젝트.
> 원칙: **한 번에 다 하지 않는다. 검증 전엔 돈 안 넣는다. 무인 운용은 최종 목표지 시작점이 아니다.**

## 이게 뭔가

수천 개 상장사를 재무 조건으로 걸러 후보를 뽑고(스크리너), 그 규칙이 과거에 통했는지
검증하고(백테스트), 단계적으로 검증을 쌓아 최종적으로 무인 운용까지 가는 것이 목표다.
지금은 **1단계 완료, 2단계(백테스트) 진행 중**. 아직 실제 매매·주문은 없다(돈 0원).

전체 지도는 [ROADMAP.md](ROADMAP.md), 1단계 구현 명세는 [CLAUDE.md](CLAUDE.md) 참조.

## 로드맵 (6단계)

```
[1] 스크리닝 ✅ → [2] 백테스트 ★ → [3] 진입 → [4] 청산
 후보 추리기        과거 검증          언제·얼마 사나  언제 파나
     └──────── [5] 리스크·자금관리 (전 단계 관통) ────┘
                        └── [6] 실행·운영 (무인 인프라)
```

- **[1] 스크리닝 ✅** — DART(재무) + KRX(시세)로 2,700여 종목 실데이터, 3층 필터 뷰어.
- **[2] 백테스트 ★현재** — 규칙을 과거로 시뮬레이션. 저PBR+저PER은 실패 → **F-Score 품질 필터 = ✅유효**(CAGR 1.7→8.0%, MDD -54→-38%, 코스피 상회). "싸다"는 졌고 "싸고+좋다"는 통함.
- [3]~[6] — 진입·청산·자금관리·무인운영. 앞 단계 검증 후 진행.

## 저장소 구조

```
delicate-rich-man/
├─ README.md               이 문서 (프로젝트 홈)
├─ ROADMAP.md              전체 6단계 지도
├─ CLAUDE.md               1단계 구현 명세 + 결정 기록
├─ EXPERIMENT_PLAN.md      2단계 실험 헌법 (목표·규율·판정원칙)
├─ LESSONS.md              2단계에서 배운 것 (반증 경로·방법론·재사용 자산)
├─ INDEX_PLAN.md           3국면 실험계획 (인덱스+자금관리, 헌법 승계)
├─ screener_skeleton.html  스크리너 뷰어 (data.json 을 fetch, 폰/PC 반응형)
├─ data.json               수집 결과 = 뷰어 입력 (6지표 실데이터, 공개 데이터라 커밋함)
├─ requirements.txt        파이썬 의존성
├─ .env.example            API 키 템플릿 (.env 는 gitignore)
│
├─ collector/              수집기 — DART 재무 + KRX 시세 → data.json
│   ├─ dart.py   krx.py    소스별 클라이언트 (+캐싱)
│   ├─ metrics.py          재무 계정 → ROE·부채비율
│   └─ build.py            진입점
│
└─ backtest/               2단계 백테스트 엔진
    ├─ data.py             과거 시세(pykrx) + 캐싱
    ├─ pit_data.py         과거 재무 point-in-time 조회 (공시일 기준 look-ahead 방어)
    ├─ fscore.py           Piotroski F-Score (품질 필터)
    ├─ engine.py           월 리밸런싱 루프 (가치 → 품질 2단)
    ├─ metrics.py          CAGR·MDD·샤프
    ├─ run.py              실행·리포트 (--compare 판정)
    └─ collect_pit.py      과거재무 사전수집 (재개형, --full 아카이브)
```

**아키텍처 핵심**: 무거운 **수집(파이썬, 키 보유)** ↔ 가벼운 **조회(HTML, 키 없음)** 분리.
수집기가 `data.json`을 만들고, 뷰어는 그걸 읽기만 한다(브라우저는 DART/KRX를 직접 안 부름 — CORS·키유출 방지).

## 빠른 시작

```bash
# 1) 의존성
pip install -r requirements.txt

# 2) 키 설정 (둘 다 무료) — 자세히는 collector/README.md
cp .env.example .env        # 그리고 DART_API_KEY, KRX_ID/KRX_PW 채우기

# 3) 데이터 수집 → data.json
python -m collector.build

# 4) 뷰어 (로컬 서버 필요 — file:// 는 fetch 막힘)
python -m http.server 8000  # → http://127.0.0.1:8000/screener_skeleton.html

# 5) 백테스트
python -m backtest.run
```

## 데이터 소스 (둘 다 무료)

| 데이터 | 소스 | 키 |
|--------|------|----|
| 재무제표 (ROE·부채) | DART OpenAPI | `DART_API_KEY` (opendart.fss.or.kr) |
| 시세 (시총·거래대금·PER·PBR) | KRX Data Marketplace / pykrx | `KRX_ID` / `KRX_PW` (data.krx.co.kr 무료 회원) |

> KIS(한국투자증권)는 실제 **주문 실행** 단계에서만 필요 → 지금은 안 씀.

## 🔐 보안 (중요)

- **API 키는 `.env` 에만.** `.env` 는 `.gitignore` 되어 **깃에 안 올라간다**(키 유출 방지).
- 코드·문서·커밋에 키를 절대 박지 않는다. 공유용 템플릿은 값 없는 `.env.example`.
- `data.json` 은 공개 재무·시세라 커밋해도 안전(비밀 아님, 뷰어 호스팅용).

## ⚠️ 안전 원칙

- 현재 단계는 **돈 1원도 안 들어감.** 매수 버튼·주문 없음.
- **백테스트 → 모의투자 → 소액 실전 → 증액** 순서 고정. 무인 운용은 맨 마지막.
- "재무제표는 과거, 주가는 미래" — 지표 조건만으로 매수 확정 금지.
- 백테스트가 좋아도 **과최적화** 경계 — 과거에 맞춘 규칙이 미래를 보장하지 않는다.
