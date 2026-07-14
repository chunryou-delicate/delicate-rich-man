"""I5b walk-forward — 통과 후보(N10±1×T15) 견고성 검증.

갈래 (a): 5/5 통과 → walk-forward → (통과 시) 봉인. 봉인 전 견고성 확인:
① 훈련+검증(2000-19)만으로도 §1 통과하나 (전체판정은 테스트 포함이라 오염 가능).
② 롤링 5년 창에서 MDD 감소·수익 유지가 일관되나 (한 시점 요행 배제).
테스트(2020-25)는 여기서 안 봄 — 봉인 전용.

사용법:  python -u -m backtest.i5b_walkforward
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from . import index_data as ix, metrics
from .i2_trend import _win
from .i5b_blend import blend

CONFIG = (10, 0.01, 15, 60)     # N, 버퍼, T, L
T_CAGR, T_MDD, T_CALMAR, T_VAL_CALMAR = 6.6, -29.0, 0.24, 0.13


def _m(rets, y0, y1):
    r = rets[(rets.index.year >= y0) & (rets.index.year <= y1)]
    eq = ix.equity(r)
    n = len(r)
    return metrics.cagr(eq, n, 12), metrics.mdd(eq), metrics.calmar(eq, n, 12)


def main() -> None:
    m = ix.monthly("20000101", "20251231")
    months_index = ix._idx_close().resample("ME").last().dropna().index
    lvl_full = ix._idx_close().resample("ME").last().dropna()
    N, buf, T, L = CONFIG
    rets = blend(m, months_index, lvl_full, N, buf, T, L)[0]
    bh = ix.bh_returns(m)

    print(f"I5b walk-forward — config N{N}±{buf*100:.0f}×T{T}/L{L}", flush=True)

    # ① 훈련+검증(2000-19)만 — 테스트 제외 §1 재확인
    c, md, ca = _m(rets, 2000, 2019)
    _, _, vca = _m(rets, 2013, 2019)
    ok = c >= T_CAGR and md >= T_MDD and ca >= T_CALMAR and vca >= T_VAL_CALMAR
    bc, bmd, _ = _m(bh, 2000, 2019)
    print(f"\n① 훈련+검증(2000-19, 테스트 제외): CAGR {c:.1f}%(관문6.6·B&H{bc:.1f}) · "
          f"MDD {md:.0f}%(관문-29·B&H{bmd:.0f}) · 칼마 {ca:.2f} · 검칼마 {vca:.2f} "
          f"→ {'✅ 통과(테스트 없이도)' if ok else '❌ 테스트가 캐리했음'}")

    # ② 롤링 5년 창 (2000-19 내): MDD 감소·수익 유지 일관성
    print("\n② 롤링 5년 창 (전략 vs B&H):")
    red, maint, wins = 0, 0, 0
    for y in range(2000, 2016):
        sc, smd, _ = _m(rets, y, y + 4)
        bcc, bmdd, _ = _m(bh, y, y + 4)
        r_ok = smd >= bmdd            # MDD 감소(덜 깊음)
        c_ok = sc >= bcc - 2.0        # 수익 유지(B&H-2%p 이내)
        red += r_ok; maint += c_ok; wins += 1
        print(f"   {y}-{y+4}: 전략 CAGR {sc:5.1f}·MDD {smd:5.0f} | B&H {bcc:5.1f}·{bmdd:5.0f} "
              f"{'✅' if (r_ok and c_ok) else ('MDD✅' if r_ok else '')}")
    print(f"\n   {wins}창 중 MDD 감소 {red} · 수익유지 {maint} · 둘다 {sum(1 for y in range(2000,2016) if _m(rets,y,y+4)[1]>=_m(bh,y,y+4)[1] and _m(rets,y,y+4)[0]>=_m(bh,y,y+4)[0]-2.0)}")
    print(f"\n판정: {'✅ 견고(테스트 제외 통과 + 롤링 일관) → 봉인 진행 가능' if ok and red>=wins*0.7 else '⚠️ 견고성 부족 → 박사님 확인'}")
    print("※ 테스트(2020-25)는 여기서 안 봄. 봉인은 박사님 승인 후 1회.")


if __name__ == "__main__":
    main()
