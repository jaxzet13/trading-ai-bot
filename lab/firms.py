"""Prop-firm rule engine (numba): evaluation, then the funded phase with payouts.

A firm is a row of numbers (see F_* indices). Rules were collected from firm pages and rule databases in
October-November 2026 and simplified to what a simulator can express. They change often: VERIFY before paying.
Money is tracked relative to the starting balance (0 = start).

Sizing: each trade risks min(f x drawdown, room to the floor, remaining daily allowance). Futures accounts trade whole
micro contracts up to the firm's position cap; CFD accounts trade fractional units up to the leverage cap. So a tight
stop cannot be turned into an oversized position, and an account with too little room to place one micro is stuck.
"""
from __future__ import annotations

import numpy as np
from numba import njit, prange

(F_KIND, F_SIZE, F_T1, F_T2, F_DD, F_DDTYPE, F_LOCK, F_DLL, F_DLLHARD, F_CONS, F_MINDAYS, F_FEE, F_FEEMO, F_ACT, F_REFUND,
 F_FDDTYPE, F_FCONS, F_PWINDAYS, F_PWINMIN, F_PCYCLE, F_PKEEP, F_PCAP, F_PMIN, F_PFRAC, F_SPLIT, F_MAXPAY, F_MAXMICRO, NF) = range(28)

NOLOCK = 1e18


def _firm(**k) -> np.ndarray:
    a = np.zeros(NF)
    d = dict(kind=0, size=50_000, t1=3000, t2=0, dd=2000, ddtype=1, lock=100, dll=0, dllhard=0, cons=0, mindays=0, fee=0, feemo=0,
             act=0, refund=0, fddtype=-1, fcons=0, pwindays=5, pwinmin=150, pcycle=5, pkeep=-1, pcap=2000, pmin=500, pfrac=1.0,
             split=0.9, maxpay=0, maxmicro=50)
    d.update(k)
    if d["fddtype"] < 0:
        d["fddtype"] = d["ddtype"]
    if d["pkeep"] < 0:      # trader policy on locked trailing accounts: leave half a drawdown above the locked floor
        d["pkeep"] = (d["lock"] if d["lock"] < NOLOCK else 0) + 0.5 * d["dd"] if d["kind"] == 0 else 0
    order = ["kind", "size", "t1", "t2", "dd", "ddtype", "lock", "dll", "dllhard", "cons", "mindays", "fee", "feemo", "act", "refund",
             "fddtype", "fcons", "pwindays", "pwinmin", "pcycle", "pkeep", "pcap", "pmin", "pfrac", "split", "maxpay", "maxmicro"]
    for i, name in enumerate(order):
        a[i] = d[name]
    return a


def _cfd(size, t1, t2, fee, refund=1, mindays=4, split=0.8, dll=0.05, dd=0.10, ddtype=0, cons=0.0, lock=NOLOCK):
    return _firm(kind=1, size=size, t1=t1 * size, t2=t2 * size, dd=dd * size, ddtype=ddtype, lock=lock, dll=dll * size, dllhard=1, cons=cons,
                 mindays=mindays, fee=fee, refund=refund, pwindays=0, pwinmin=0, pcycle=10, pkeep=0, pcap=1e12, pmin=0.002 * size, pfrac=1.0,
                 split=split, maxmicro=0)


FIRMS: dict[str, dict] = {
    # ---- futures, 50k: target $3,000, $2,000 drawdown --------------------------------------------------------------
    "Lucid Flex 50k": dict(p=_firm(cons=0.5, fee=100, pcap=2000, maxpay=5),
        note="EOD trailing $2k locks at start+$100; 50% consistency in eval; one-time ~$100. Funded: 5 winning days ($150+) per payout, cap $2k, 90%."),
    "Lucid Pro 50k": dict(p=_firm(dll=1200, fee=120, fcons=0.4, pcap=2000, maxpay=5),
        note="EOD trailing $2k; $1.2k daily limit; no eval consistency; ~$120. Funded: 40% consistency per payout cycle, 90%."),
    "Apex 50k EOD": dict(p=_firm(dll=1000, fee=150, fcons=0.5, pkeep=2100, pcap=1500, split=1.0, maxpay=6),
        note="EOD trailing $2k; $1k daily limit; no eval consistency; one-time fee (promo-dependent, ~$150). Funded: must stay above start+$2,100, 50% consistency, max 6 payouts, first caps $1.5k, 100%."),
    "Apex 50k intraday": dict(p=_firm(ddtype=2, fee=130, fcons=0.5, pkeep=2100, pcap=1500, split=1.0, maxpay=6),
        note="Intraday trailing $2k (follows unrealised highs); no daily limit; funded rules as Apex EOD."),
    "Topstep 50k": dict(p=_firm(lock=0, dll=1000, cons=0.5, feemo=49, act=149, pkeep=0, pfrac=0.5, pcap=2000, pmin=125),
        note="EOD trailing $2k to the start balance; $1k daily limit; best day under 50%; $49/month + $149 activation. Funded: 5 winning days of $150+, up to 50% of balance, cap $2k, 90%."),
    "MFFU Rapid 50k": dict(p=_firm(cons=0.5, mindays=2, fee=105, pwindays=0, pwinmin=0, pcycle=1, pkeep=2100, pcap=1500),
        note="EOD $2k; 50% consistency and 2 min days in eval; ~$105. Funded: no consistency, daily payouts above a start+$2,100 buffer, 90%."),
    "Tradeify Select 50k": dict(p=_firm(cons=0.4, mindays=3, fee=165, pcap=2500),
        note="EOD trailing $2k; 40% consistency and 3 min days in eval; $165. Funded Select Flex: payout every 5 winning days, cap $2.5k, 90%."),
    "TakeProfit 50k": dict(p=_firm(mindays=3, feemo=150, act=130, fddtype=2, pwindays=0, pwinmin=0, pcycle=1, pkeep=2000, pcap=1e12, split=0.8),
        note="EOD trailing $2k in the test; 3 min days; ~$150/month + $130 activation. Funded PRO: intraday trailing, withdraw above a $2k buffer, 80%."),
    # ---- CFD ------------------------------------------------------------------------------------------------------
    "FTMO 2-step 100k": dict(p=_cfd(100_000, 0.10, 0.05, 540), note="10% then 5%; 5% daily, 10% static; 4 min days; $540 refunded with first payout; 80%, payouts every 14 days."),
    "FundedNext 2-step 100k": dict(p=_cfd(100_000, 0.08, 0.05, 549, mindays=5), note="8% then 5%; 5% daily, 10% static; 5 min days; $549 refunded; 80%."),
    "FundingPips 2-step 100k": dict(p=_cfd(100_000, 0.08, 0.05, 399, refund=0, mindays=3), note="8% then 5%; 5% daily, 10% static; 3 min days; $399; 80%."),
    "FundingPips 2-step 5k": dict(p=_cfd(5_000, 0.08, 0.05, 32, refund=0, mindays=3), note="Same rules on a $5k account for ~$32."),
    "FTMO 1-step 100k": dict(p=_cfd(100_000, 0.10, 0.0, 540, mindays=0, split=0.9, dll=0.03, ddtype=1, cons=0.5, lock=0.0),
        note="One phase 10%; 3% daily; 10% EOD-trailing max loss; 50% best-day rule; 90%."),
}
FIRM_NAMES = list(FIRMS)
FIRM_MATRIX = np.stack([FIRMS[n]["p"] for n in FIRM_NAMES])


@njit(cache=True)
def _units(P, risk, rpu, npu, upm, levcap):
    if rpu <= 0:
        return 0.0
    if P[F_KIND] == 0:                      # futures: whole micro contracts
        per_micro = rpu * upm
        k = np.floor(risk / per_micro)
        mx = P[F_MAXMICRO] * P[F_SIZE] / 50_000.0
        if k > mx: k = mx
        return k * upm
    u = risk / rpu                          # CFD: fractional units, leverage cap on notional
    mxu = P[F_SIZE] * levcap / npu
    return u if u < mxu else mxu


@njit(cache=True)
def _phase(P, target, ddtype, f, i, n, day, R, MAE, MFE, RPU, NPU, UPM, LEV, funded, horizon):
    """One phase. Eval: returns (status 0 fail / 1 pass / 2 data ended, next index, payouts, first-payout flag).
    Funded: runs until breach, payout limit, or `horizon` trading days; status 1 = still alive at the end."""
    dd = P[F_DD]; lock = P[F_LOCK]; dll = P[F_DLL]
    bal = 0.0; peak = 0.0; ipk = 0.0
    best_day = 0.0; day_pnl = 0.0; cur = -1; ndays = 0; skips = 0
    stopped = False; traded = False
    paid = 0.0; npay = 0; win_days = 0; since = 0; cyc_best = 0.0; cyc_start = 0.0
    while i < n:
        if day[i] != cur:
            if cur >= 0:
                if day_pnl > best_day: best_day = day_pnl
                if bal > peak: peak = bal
                if funded and traded:
                    since += 1
                    if day_pnl >= P[F_PWINMIN] and day_pnl > 0: win_days += 1
                    if day_pnl > cyc_best: cyc_best = day_pnl
                    if win_days >= P[F_PWINDAYS] and since >= P[F_PCYCLE]:
                        avail = (bal - P[F_PKEEP]) * P[F_PFRAC]
                        prof = bal - cyc_start
                        okc = P[F_FCONS] == 0 or (prof > 0 and cyc_best <= P[F_FCONS] * prof)
                        amt = avail if avail < P[F_PCAP] else P[F_PCAP]
                        if okc and amt >= P[F_PMIN]:
                            bal -= amt; paid += amt * P[F_SPLIT]; npay += 1
                            win_days = 0; since = 0; cyc_best = 0.0; cyc_start = bal
                            if P[F_MAXPAY] > 0 and npay >= P[F_MAXPAY]:
                                return 1, i, paid, npay
                    if ndays >= horizon:
                        return 1, i, paid, npay
            cur = day[i]; day_pnl = 0.0; stopped = False; traded = False
        if ddtype == 0:
            floor = -dd
        else:
            pk = peak if ddtype == 1 else ipk
            floor = pk - dd
            if floor > lock: floor = lock
        room = bal - floor
        if room <= 0:
            return 0, i, paid, npay
        if stopped:
            i += 1; continue
        risk = f * dd
        cap = room * (0.5 if funded else 1.0)
        if risk > cap: risk = cap
        if dll > 0:
            left = 0.9 * (dll + day_pnl)
            if left <= 0:
                stopped = True; i += 1; continue
            if risk > left: risk = left
        u = _units(P, risk, RPU[i], NPU[i], UPM[i], LEV[i])
        if u <= 0:
            skips += 1
            if skips > 30:
                return 0, i, paid, npay          # stuck: not enough room to place the smallest position
            i += 1; continue
        skips = 0
        if not traded:
            traded = True; ndays += 1
        ru = u * RPU[i]
        if bal - ru * MAE[i] <= floor:
            return 0, i + 1, paid, npay
        hi = bal + ru * MFE[i]
        if hi > ipk: ipk = hi
        pnl = ru * R[i]
        bal += pnl; day_pnl += pnl
        if bal > ipk: ipk = bal
        if dll > 0 and day_pnl <= -dll:
            if P[F_DLLHARD] == 1:
                return 0, i + 1, paid, npay
            stopped = True
        if bal <= floor:
            return 0, i + 1, paid, npay
        if not funded:
            bd = best_day if best_day > day_pnl else day_pnl
            if bal >= target and ndays >= P[F_MINDAYS] and (P[F_CONS] == 0 or bd <= P[F_CONS] * bal):
                return 1, i + 1, paid, npay
        i += 1
    return 2, i, paid, npay


@njit(cache=True)
def _attempt(P, fe, ff, i0, n, day, R, MAE, MFE, RPU, NPU, UPM, LEV, horizon):
    st, i, _, _ = _phase(P, P[F_T1], P[F_DDTYPE], fe, i0, n, day, R, MAE, MFE, RPU, NPU, UPM, LEV, False, 0)
    if st == 1 and P[F_T2] > 0:
        st, i, _, _ = _phase(P, P[F_T2], P[F_DDTYPE], fe, i, n, day, R, MAE, MFE, RPU, NPU, UPM, LEV, False, 0)
    if st != 1:
        return st, 0, 0.0, 0, 0
    cal = day[i - 1] - day[i0] + 1
    fs, j, paid, npay = _phase(P, 0.0, P[F_FDDTYPE], ff, i, n, day, R, MAE, MFE, RPU, NPU, UPM, LEV, True, horizon)
    return 1, cal, paid, npay, fs


@njit(parallel=True, cache=True)
def evaluate(FM, FE, FF, starts, day, R, MAE, MFE, RPU, NPU, UPM, LEV, horizon):
    """All firms x eval sizings x funded sizings. Output [firm, fe, ff, 8]:
    resolved, pass rate, mean calendar days to pass, median days, mean payouts if funded, P(>=1 payout | funded),
    funded alive at horizon, EV per attempt."""
    nF = FM.shape[0]; nE = len(FE); nG = len(FF); nS = len(starts); n = len(R)
    out = np.zeros((nF, nE, nG, 8))
    for a in prange(nF):
        P = FM[a]
        for b in range(nE):
            for c in range(nG):
                res = 0; npass = 0; sum_paid = 0.0; got = 0; alive = 0
                days = np.empty(nS)
                for s in range(nS):
                    st, cal, paid, npay, fs = _attempt(P, FE[b], FF[c], starts[s], n, day, R, MAE, MFE, RPU, NPU, UPM, LEV, horizon)
                    if st == 2:
                        continue
                    res += 1
                    if st == 1:
                        days[npass] = cal; npass += 1
                        sum_paid += paid
                        if npay > 0: got += 1
                        if fs == 1: alive += 1
                if res == 0:
                    continue
                pr = npass / res
                md = np.mean(days[:npass]) if npass > 0 else 0.0
                med = np.median(days[:npass]) if npass > 0 else 0.0
                mp = sum_paid / npass if npass > 0 else 0.0
                pg = got / npass if npass > 0 else 0.0
                # fees: one-time + monthly while in evaluation (failed attempts assumed to last as long as passed ones)
                months = max(1.0, md / 30.0) if P[F_FEEMO] > 0 else 0.0
                ev = pr * (mp - P[F_ACT]) + pr * pg * P[F_REFUND] * P[F_FEE] - P[F_FEE] - P[F_FEEMO] * months
                o = out[a, b, c]
                o[0] = res; o[1] = pr; o[2] = md; o[3] = med; o[4] = mp; o[5] = pg
                o[6] = alive / npass if npass > 0 else 0.0
                o[7] = ev
    return out
