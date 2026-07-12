"""포트폴리오 레벨 방어 시뮬 — 차단기·정적 현금비중 (로드맵 [5]).

개별종목 손절이 장중 갭에 취약해 실패(exit_sim) → 전체 포트폴리오 레벨로.
월 단위·전체 신호라 갭에 덜 취약하다는 가설을 검증한다.

목표(재정의): 시장 이기기 ❌ → **시장 수익 유지하며 MDD 줄이기.**
판정(사전 확정, README): 칼마·샤프 개선 + 차단기가 정적현금(null)보다 나음 + 민감도 유지.

입력 = 가치+품질 전략의 월수익(캐시). DART/시세 추가 조회 없음 — 순수 과거 시뮬.
차단기 신호는 look-ahead 없음: shadow(항상 풀투자 가정) 누적으로 t까지 정보만 써 t+1 결정.

사용법:  python -m backtest.defense_sim
한계(v1): 현금수익 0 가정(금리 무시), 상태전환 비용 0.25% 근사.
"""
from __future__ import annotations

import sys
from dataclasses import replace

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from . import metrics
from .engine import Params, run

COST = 0.25 / 100   # 상태 전환(전량 매도/매수) 편도비용 근사


def _stat(equity, monthly):
    n = len(monthly)
    return (metrics.cagr(equity, n), metrics.mdd(equity),
            metrics.calmar(equity, n), metrics.sharpe(monthly))


def base(r):
    eq = [1.0]
    for x in r:
        eq.append(eq[-1] * (1 + x))
    return eq, list(r)


def static_cash(r, c):
    """상시 c 현금 + (1-c) 전략."""
    eq, mo = [1.0], []
    for x in r:
        ret = (1 - c) * x
        eq.append(eq[-1] * (1 + ret))
        mo.append(ret)
    return eq, mo


def circuit(r, exit_dd, reenter_dd):
    """shadow(풀투자) 드로다운 -exit_dd 도달→현금, -reenter_dd 위로 회복→재진입."""
    eq, mo = [1.0], []
    shadow, peak, invested = 1.0, 1.0, True
    for x in r:
        ret = x if invested else 0.0
        prev = invested
        # 상태 갱신(이번 달 실현치 x 로 t+1 결정 — look-ahead 없음)
        shadow *= (1 + x)
        peak = max(peak, shadow)
        dd = shadow / peak - 1
        if invested and dd <= -exit_dd / 100:
            invested = False
        elif not invested and dd >= -reenter_dd / 100:
            invested = True
        if invested != prev:                 # 전환 비용
            ret -= COST
        eq.append(eq[-1] * (1 + ret))
        mo.append(ret)
    return eq, mo


def main() -> None:
    print("가치+품질 전략 월수익 로드(캐시)…", flush=True)
    p = replace(Params(start="20150101", end="20251231", top_n=20), use_fscore=True)
    r = run(p)
    rm = r.monthly
    kospi_m = r.bench_monthly

    rows = []
    eqb, mob = base(rm)
    rows.append(("base(무방어)", *_stat(eqb, mob)))
    for c in (0.2, 0.4):
        rows.append((f"정적현금 {int(c*100)}%", *_stat(*static_cash(rm, c))))
    for n in (15, 20, 25):
        rows.append((f"차단기 -{n}%", *_stat(*circuit(rm, n, n / 2))))
    # 코스피
    eqk = [1.0]
    for x in kospi_m:
        eqk.append(eqk[-1] * (1 + x))
    kospi_row = ("[코스피]", *_stat(eqk, kospi_m))

    b = rows[0]
    print(f"\n{'설정':13s} {'CAGR':>6s} {'MDD':>7s} {'칼마':>6s} {'샤프':>6s}  판정")
    print("-" * 50)
    print(f"{kospi_row[0]:13s} {kospi_row[1]:6.1f} {kospi_row[2]:7.1f} {kospi_row[3]:6.2f} {kospi_row[4]:6.2f}")
    cb_ok = 0
    static_best_calmar = max(rows[1][3], rows[2][3])
    for x in rows:
        mark = ""
        if x[0].startswith("차단기"):
            improve = x[3] > b[3] and x[4] > b[4]          # 칼마·샤프 개선
            beats_null = x[3] > static_best_calmar          # 정적현금보다 나음
            cb_ok += improve and beats_null
            mark = "✅" if (improve and beats_null) else ("△(정적현금 이하)" if improve else "❌")
        print(f"{x[0]:13s} {x[1]:6.1f} {x[2]:7.1f} {x[3]:6.2f} {x[4]:6.2f}  {mark}")
    print("-" * 50)
    print(f"판정: 차단기 {cb_ok}/3 이 칼마·샤프 개선 + 정적현금(null) 초과", flush=True)
    if cb_ok >= 2:
        print("→ ✅ 포트폴리오 차단기가 방어로 유효 (개별 손절과 달리 갭 무관하게 작동)")
    elif cb_ok >= 1:
        print("→ △ 일부만 — 박사님 확인 필요(과최적화 경계)")
    else:
        print("→ ❌ 차단기도 무효(정적현금과 다를 바 없거나 더 나쁨). 방어 재설계 필요")
    print("\n※ 현금수익 0(금리무시)·전환비용 0.25% 근사. 월 단위 신호라 갭 영향 없음.")


if __name__ == "__main__":
    main()
