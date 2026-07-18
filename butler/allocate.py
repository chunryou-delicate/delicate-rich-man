"""v0.5 가변 적립 배분 엔진 (실전 트랙 §2).

입력: 이번에 넣을 금액(가변) + 자산별 현재 잔고(수동).
출력: policy 비율로 이번 입력액을 어디에 얼마씩 배분하는 지시 — 목표미달 자산 우선.
계좌 순서: 유동성버퍼 → 연금 → ISA → 일반. 100% 결정론. **주문 없음.**

정책은 policy.json(유일). 이 엔진은 policy + 입력값만으로 계산(예측·전략 로직 없음).
사용법:  python -u -m butler.allocate            # 예시 입력으로 지시 생성(+지시서.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent
POLICY = json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))

ASSETS = ["국내주식", "글로벌주식", "채권", "현금"]


def asset_weights() -> dict:
    """policy → 자산별 목표비중(전체 기준)."""
    ta = POLICY["preset"]["target_allocation"]
    sp = POLICY["preset"]["stock_split"]
    return {
        "국내주식": ta["stock"] * sp["domestic"],
        "글로벌주식": ta["stock"] * sp["global"],
        "채권": ta["bond"],
        "현금": ta["cash"],
    }


def allocate(new_amount: float, balances: dict) -> dict:
    """이번 입력액을 목표미달 자산 우선으로 배분. 결정론."""
    w = asset_weights()
    bal = {a: float(balances.get(a, 0)) for a in ASSETS}
    total_now = sum(bal.values())
    total_new = total_now + new_amount
    target_amt = {a: total_new * w[a] for a in ASSETS}
    deficit = {a: max(0.0, target_amt[a] - bal[a]) for a in ASSETS}
    total_def = sum(deficit.values())

    alloc = {a: 0.0 for a in ASSETS}
    if new_amount <= 0:
        pass
    elif total_def <= 0:                       # 전부 목표 이상 → 목표비중대로
        for a in ASSETS:
            alloc[a] = new_amount * w[a]
    elif new_amount <= total_def:              # 미달분에 비례(목표미달 우선)
        for a in ASSETS:
            alloc[a] = new_amount * deficit[a] / total_def
    else:                                      # 미달 다 채우고 나머지는 목표비중대로
        rem = new_amount - total_def
        for a in ASSETS:
            alloc[a] = deficit[a] + rem * w[a]

    after = {a: bal[a] + alloc[a] for a in ASSETS}
    # 리밸런싱 체크(±band). new money로 미달을 채우므로 대개 완화됨. 초과분만 플래그.
    band = POLICY["rebalance"]["band_pct"] / 100
    reb = [a for a in ASSETS if total_new > 0 and abs(after[a] / total_new - w[a]) > band]
    return {
        "new_amount": new_amount, "weights": w, "target_amt": target_amt,
        "balances": bal, "alloc": alloc, "after": after, "total_after": total_new,
        "after_pct": {a: (after[a] / total_new if total_new else 0) for a in ASSETS},
        "rebalance_flag": reb,
    }


def place_accounts(alloc: dict, room: dict | None) -> list:
    """자산 배분액을 계좌 우선순위로 배치. 현금=CMA(버퍼), ETF=연금→ISA→일반.

    room = {"연금": 남은한도, "ISA": 남은한도} (없으면 계좌배치 생략, 자산만 지시).
    """
    if room is None:
        return []
    plan = []
    # 현금은 유동성 버퍼(일반/CMA)로
    if alloc["현금"] > 0:
        plan.append(("일반/CMA(유동성버퍼)", "현금", alloc["현금"]))
    etf_pool = alloc["국내주식"] + alloc["글로벌주식"] + alloc["채권"]
    # ETF 배분액을 연금→ISA→일반 순으로 한도 내 채움(자산 구성은 비율 유지)
    for acct in ["연금", "ISA"]:
        if etf_pool <= 0:
            break
        cap = float(room.get(acct, 0))
        put = min(cap, etf_pool)
        if put > 0:
            plan.append((acct, "ETF(국내/글로벌/채권 비율대로)", put))
            etf_pool -= put
    if etf_pool > 0:
        plan.append(("일반", "ETF(국내/글로벌/채권 비율대로)", etf_pool))
    return plan


def _won(x): return f"{round(x):,}원"


def main() -> None:
    # 예시 입력 — 실제로 '이번에 얼마' 넣으면 지시가 나오는 걸 확인
    new_amount = 3_000_000
    balances = {"국내주식": 4_000_000, "글로벌주식": 2_000_000, "채권": 3_000_000, "현금": 1_000_000}
    room = {"연금": 1_500_000, "ISA": 5_000_000}   # 남은 납입한도(예시)

    r = allocate(new_amount, balances)
    print(f"=== 이번 입력 {_won(new_amount)} 배분 지시 (균형형) ===")
    print(f"{'자산':10s} {'목표%':>6s} {'현재':>12s} {'→ 이번배분':>12s} {'→ 후잔고(%)':>16s}")
    for a in ASSETS:
        print(f"{a:10s} {r['weights'][a]*100:5.0f}% {_won(r['balances'][a]):>12s} "
              f"{_won(r['alloc'][a]):>12s} {_won(r['after'][a]):>12s}({r['after_pct'][a]*100:4.1f}%)")
    print(f"\n계좌 배치(우선순위):")
    for acct, what, amt in place_accounts(r["alloc"], room):
        print(f"  {acct:20s} ← {what}: {_won(amt)}")
    print(f"\n리밸런싱: {'필요(밴드 초과: '+', '.join(r['rebalance_flag'])+')' if r['rebalance_flag'] else '불필요'}")
    print("주문 버튼 없음 — 이 지시 보고 증권사에서 손으로 실행. (v0.5, 100% 결정론)")

    # 지시서 HTML용 JSON 산출
    out = {**{k: r[k] for k in ["new_amount", "weights", "balances", "alloc", "after",
                                "after_pct", "total_after", "rebalance_flag"]},
           "accounts": [{"acct": a, "what": w, "amount": m}
                        for a, w, m in place_accounts(r["alloc"], room)],
           "preset": POLICY["preset"]["name"]}
    (ROOT / "지시서.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ 지시서.json 생성 (HTML 뷰어 입력)")


if __name__ == "__main__":
    main()
