"""v0.5 가변 적립 배분 엔진 (실전 트랙 §2) — 6:2:2 고배당 확대판.

입력: 이번에 넣을 금액(가변) + 자산별 현재 잔고(수동).
출력: policy 비율로 이번 입력액을 어디에 얼마씩 배분하는 지시 — 목표미달 자산 우선.

자산(전체 대비 목표):
  국내코어 21% · 글로벌코어 21%  (= 코어인덱스 42%, 국내:글로벌 50:50)
  고배당ETF 14% · 개별주(위성) 14%  (= 주식 6:2:2의 2:2)
  채권 20% · 현금 10%
위성은 상한 14% — 초과분엔 신규 적립 안 함, 초과 시 코어/고배당ETF로 재배분 권고.
계좌: 현금→유동성버퍼(CMA), ETF→연금(한도)→ISA→일반, 개별주→ISA→일반(연금 불가).
100% 결정론. **주문 없음.**  사용법:  python -u -m butler.allocate
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent
POLICY = json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))

# 자산 키 순서(표시 순). is_sat=위성(연금 불가·상한), is_etf=연금/ISA 담기 가능
ASSETS = ["국내코어", "글로벌코어", "고배당ETF", "개별주(위성)", "채권", "현금"]
IS_SAT = {"개별주(위성)": True}
IS_ETF = {"국내코어": True, "글로벌코어": True, "고배당ETF": True, "채권": True}


def asset_weights() -> dict:
    """policy → 자산별 목표비중(전체 기준)."""
    ta = POLICY["preset"]["target_allocation"]
    sp = POLICY["preset"]["stock_split"]
    stock = ta["stock"]
    core = stock * sp["core_index"]
    geo = sp["core_geo_split"]
    return {
        "국내코어": core * geo["domestic"],
        "글로벌코어": core * geo["global"],
        "고배당ETF": stock * sp["high_dividend_etf"],
        "개별주(위성)": stock * sp["individual_satellite"],
        "채권": ta["bond"],
        "현금": ta["cash"],
    }


def sat_cap() -> float:
    return POLICY["preset"]["satellite_cap"]["max_pct_of_total"]


def allocate(new_amount: float, balances: dict) -> dict:
    """이번 입력액을 목표미달 자산 우선으로 배분. 결정론. 위성은 상한까지만 목표로."""
    w = asset_weights()
    cap = sat_cap()
    bal = {a: float(balances.get(a, 0)) for a in ASSETS}
    total_now = sum(bal.values())
    total_new = total_now + new_amount
    # 위성 목표는 min(목표비중, 상한) — 어차피 목표=상한(14%)이라 동일하나 명시적 보호
    target_amt = {a: total_new * (min(w[a], cap) if IS_SAT.get(a) else w[a]) for a in ASSETS}
    deficit = {a: max(0.0, target_amt[a] - bal[a]) for a in ASSETS}
    total_def = sum(deficit.values())

    alloc = {a: 0.0 for a in ASSETS}
    if new_amount <= 0:
        pass
    elif total_def <= 0:                       # 전부 목표 이상 → 목표비중대로(위성 제외)
        # 목표 이상이면 위성엔 추가 안 함, 나머지에 비중 비례
        base = {a: w[a] for a in ASSETS if not IS_SAT.get(a)}
        s = sum(base.values())
        for a in base:
            alloc[a] = new_amount * base[a] / s
    elif new_amount <= total_def:              # 미달분에 비례(목표미달 우선)
        for a in ASSETS:
            alloc[a] = new_amount * deficit[a] / total_def
    else:                                      # 미달 다 채우고 나머지는 위성 뺀 비중대로
        rem = new_amount - total_def
        base = {a: w[a] for a in ASSETS if not IS_SAT.get(a)}
        s = sum(base.values())
        for a in ASSETS:
            alloc[a] = deficit[a] + (rem * base[a] / s if a in base else 0.0)

    after = {a: bal[a] + alloc[a] for a in ASSETS}
    after_pct = {a: (after[a] / total_new if total_new else 0) for a in ASSETS}
    band = POLICY["rebalance"]["band_pct"] / 100
    reb = [a for a in ASSETS if total_new > 0 and abs(after_pct[a] - w[a]) > band]
    sat_over = total_new > 0 and after_pct["개별주(위성)"] > cap + 1e-9
    return {
        "new_amount": new_amount, "weights": w, "cap": cap, "target_amt": target_amt,
        "balances": bal, "alloc": alloc, "after": after, "total_after": total_new,
        "after_pct": after_pct, "rebalance_flag": reb, "sat_over": sat_over,
    }


def place_accounts(alloc: dict, room: dict | None) -> list:
    """자산 배분액을 계좌 우선순위로 배치.

    현금→유동성버퍼(CMA). ETF(코어·고배당·채권)→연금(한도)→ISA→일반.
    개별주(위성)→ISA→일반(연금 불가). room={"연금":.., "ISA":..} 없으면 생략.
    """
    if room is None:
        return []
    plan = []
    if alloc["현금"] > 0:
        plan.append(("일반/CMA(유동성버퍼)", "현금", alloc["현금"]))
    etf_pool = sum(alloc[a] for a in ASSETS if IS_ETF.get(a))
    sat_pool = alloc["개별주(위성)"]

    # 연금: ETF만
    pen = min(float(room.get("연금", 0)), etf_pool)
    if pen > 0:
        plan.append(("연금저축", "ETF(코어·고배당·채권 비율대로)", pen)); etf_pool -= pen
    # ISA: 위성 우선(연금 못 담으니) → 남으면 ETF
    isa_left = float(room.get("ISA", 0))
    isa_sat = min(isa_left, sat_pool)
    if isa_sat > 0:
        plan.append(("ISA", "개별주(위성)", isa_sat)); sat_pool -= isa_sat; isa_left -= isa_sat
    isa_etf = min(isa_left, etf_pool)
    if isa_etf > 0:
        plan.append(("ISA", "ETF(코어·고배당·채권 비율대로)", isa_etf)); etf_pool -= isa_etf
    # 일반: 나머지
    if etf_pool > 0:
        plan.append(("일반계좌", "ETF(코어·고배당·채권 비율대로)", etf_pool))
    if sat_pool > 0:
        plan.append(("일반계좌", "개별주(위성)", sat_pool))
    return plan


def _won(x): return f"{round(x):,}원"


def main() -> None:
    # 예시: 이번 1,200만원, 잔고 0(첫 적립) → 6:2:2로 쪼개지는지 확인
    new_amount = 12_000_000
    balances = {a: 0 for a in ASSETS}
    room = {"연금": 6_000_000, "ISA": 4_000_000}

    r = allocate(new_amount, balances)
    print(f"=== 이번 입력 {_won(new_amount)} 배분 지시 (균형형 고배당확대판 6:2:2) ===")
    print(f"{'자산':16s} {'목표%':>6s} {'현재':>10s} {'→ 이번배분':>13s} {'→ 후잔고(%)':>16s}")
    for a in ASSETS:
        add = r["alloc"][a]
        print(f"{a:16s} {r['weights'][a]*100:5.1f}% {_won(r['balances'][a]):>10s} "
              f"{('+'+_won(add)) if add>0.5 else '—':>13s} "
              f"{_won(r['after'][a]):>12s}({r['after_pct'][a]*100:4.1f}%)")
    # 6:2:2 검산
    core = r["alloc"]["국내코어"] + r["alloc"]["글로벌코어"]
    hi, sat = r["alloc"]["고배당ETF"], r["alloc"]["개별주(위성)"]
    stock_add = core + hi + sat
    if stock_add > 0:
        print(f"\n주식 내부 분할: 코어 {core/stock_add*100:.0f} : 고배당 {hi/stock_add*100:.0f} : "
              f"위성 {sat/stock_add*100:.0f}  (목표 60:20:20)")
    print(f"\n계좌 배치(우선순위):")
    for acct, what, amt in place_accounts(r["alloc"], room):
        print(f"  {acct:16s} ← {what}: {_won(amt)}")
    msg = "불필요"
    if r["rebalance_flag"]:
        msg = "필요(밴드 초과: " + ", ".join(r["rebalance_flag"]) + ")"
        if r["sat_over"]:
            msg += " · ⚠위성 상한(14%) 초과 → 초과분 코어/고배당ETF로 재배분(위성 추가매수 금지)"
    print(f"\n리밸런싱: {msg}")
    print("주문 버튼 없음 — 이 지시 보고 증권사에서 손으로 실행. (v0.5, 100% 결정론)")

    out = {**{k: r[k] for k in ["new_amount", "weights", "cap", "balances", "alloc",
                                "after", "after_pct", "total_after", "rebalance_flag", "sat_over"]},
           "accounts": [{"acct": a, "what": w, "amount": m}
                        for a, w, m in place_accounts(r["alloc"], room)],
           "preset": POLICY["preset"]["name"]}
    (ROOT / "지시서.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ 지시서.json 생성")


if __name__ == "__main__":
    main()
