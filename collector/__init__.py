"""재무 스크리너 수집기 패키지.

DART OpenAPI에서 국내 상장사 재무제표를 받아 지표를 계산하고,
뷰어(screener_skeleton.html)가 읽는 data.json 을 생성한다.

역할 분리(고정 결정): 수집(파이썬, 키 보유) ↔ 조회(HTML, 키 없음).
자세한 배경은 CLAUDE.md 참조.
"""
