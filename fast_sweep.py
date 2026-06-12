"""
Mega strategy sweep — vectorised portfolio sim + vectorised signals.
Runs 15 strategy families × best params on crypto + stocks.
"""
from __future__ import annotations
import sys, itertools
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

FEE_CRYPTO = 0.0025
FEE_STOCKS = 0.0

# ─── data ─────────────────────────────────────────────────────────────────
CRYPTO = ["BTC-USD","ETH-USD","SOL-USD","AVAX-USD","LINK-USD","DOGE-USD","BNB-USD","ADA-USD"]
STOCKS = ["TSLA","NVDA","AMD","MSTR","COIN","SMCI","PLTR","APP","MARA","RIOT"]

def fetch(syms, period="729d", interval="1h"):
    raw = yf.download(syms, period=period, interval=interval,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        cl = raw["Close"].dropna(how="all")
        hi = raw["High"].reindex(cl.index).ffill()
        lo = raw["Low"].reindex(cl.index).ffill()
        vo = raw["Volume"].reindex(cl.index).fillna(1e6)
    else:
        cl = raw[["Close"]].rename(columns={"Close": syms[0]})
        hi = raw[["High"]].rename(columns={"High": syms[0]}).reindex(cl.index).ffill()
        lo = raw[["Low"]].rename(columns={"Low": syms[0]}).reindex(cl.index).ffill()
        vo = pd.DataFrame(1e6, index=cl.index, columns=cl.columns)
    # align all to same index
    idx = cl.index
    hi = hi.reindex(idx).ffill(); lo = lo.reindex(idx).ffill(); vo = vo.reindex(idx).fillna(1e6)
    return cl, hi, lo, vo

print("Fetching crypto hourly…"); cl_c, hi_c, lo_c, vo_c = fetch(CRYPTO)
print(f"  {len(cl_c)} bars, {cl_c.shape[1]} coins")
print("Fetching stock hourly…");  cl_s, hi_s, lo_s, vo_s = fetch(STOCKS)
print(f"  {len(cl_s)} bars, {cl_s.shape[1]} stocks")

# ─── vectorised portfolio sim ─────────────────────────────────────────────
def sim_vec(weights: pd.DataFrame, close: pd.DataFrame,
            fee: float = 0.0, kelly: float = 1.0,
            init: float = 100_000.0) -> pd.Series:
    """
    Fully vectorised equity simulation.
    weights: date × symbol, values 0..1 (target allocation fractions).
    Returns equity series.
    """
    w = weights.reindex(close.index).fillna(0.0).clip(0, 1) * kelly
    prices = close.ffill()
    # daily returns per symbol
    ret = prices.pct_change().fillna(0.0)
    # transaction costs: fee applied to |change in weight|
    w_prev = w.shift(1).fillna(0.0)
    turnover = (w - w_prev).abs()
    cost = (turnover * fee).sum(axis=1)
    # portfolio return each bar
    port_ret = (w_prev * ret).sum(axis=1) - cost
    equity = (1 + port_ret).cumprod() * init
    return equity

# ─── indicators ───────────────────────────────────────────────────────────
def rsi(c, p):
    d = c.diff()
    g = d.clip(lower=0).ewm(alpha=1/p, min_periods=p, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/p, min_periods=p, adjust=False).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))

def ema(c, p): return c.ewm(span=p, adjust=False).mean()

def bb(c, p, k):
    m = c.rolling(p).mean(); s = c.rolling(p).std()
    return m - k*s, m, m + k*s

def atr(c, h, l, p):
    prev = c.shift(1)
    tr = pd.DataFrame(np.maximum(np.maximum((h-l).values,(h-prev).abs().values),(l-prev).abs().values),
                      index=c.index, columns=c.columns)
    return tr.ewm(span=p, adjust=False).mean()

def vwap(c, h, l, v, p):
    tp = (h+l+c)/3
    return (tp*v).rolling(p).sum() / v.rolling(p).sum()

def persist(entry: pd.DataFrame, exit_: pd.DataFrame) -> pd.DataFrame:
    sig = pd.DataFrame(np.nan, index=entry.index, columns=entry.columns)
    sig[entry.astype(bool)] = 1.0
    sig[exit_.astype(bool)] = 0.0
    return sig.ffill().fillna(0.0)

def norm(w: pd.DataFrame) -> pd.DataFrame:
    s = w.sum(axis=1).replace(0, np.nan)
    return w.div(s, axis=0).fillna(0.0)

# ─── evaluation ───────────────────────────────────────────────────────────
results = []

def evaluate(label, targets, close, fee, kelly=1.0):
    try:
        eq = sim_vec(targets, close, fee, kelly)
        eq = eq.dropna()
        if len(eq) < 200: return
        deq = eq.resample("D").last().dropna()
        if len(deq) < 60: return
        dr  = deq.pct_change().dropna()
        n   = len(dr)
        yrs = n/365
        tot = eq.iloc[-1]/eq.iloc[0]-1
        cagr = (1+tot)**(1/yrs)-1 if yrs>0 else 0
        dd  = ((eq/eq.cummax())-1).min()
        sh  = dr.mean()/dr.std()*np.sqrt(365) if dr.std()>0 else 0
        results.append(dict(
            name=label, kelly=kelly,
            avg_day=dr.mean()*100,
            days_3pct=int((dr>=0.03).sum()),
            pct_3pct=(dr>=0.03).mean()*100,
            days_neg3=int((dr<=-0.03).sum()),
            best_day=dr.max()*100, worst_day=dr.min()*100,
            cagr=cagr*100, total=tot*100, final=eq.iloc[-1],
            sharpe=sh, maxdd=dd*100,
            n_days=n,
        ))
    except Exception as e:
        print(f"  SKIP {label}: {e}")

def R(label, tgts, close, fee):
    for k in [0.5, 1.0]:
        evaluate(f"{label}_k{k}", tgts, close, fee, k)

# ─── strategy sweep ───────────────────────────────────────────────────────
def sweep(cl, hi, lo, vo, fee, tag):
    print(f"\n── {tag} ──")
    n0 = len(results)

    # 1  BB reversion
    for p,k in [(14,1.5),(20,2.0),(20,2.5)]:
        lo_b,mid_b,_ = bb(cl,p,k)
        R(f"BB_Rev_{p}_{k}_{tag}", norm(persist(cl<lo_b, cl>=mid_b)), cl, fee)

    # 2  BB + RSI
    for (bp,k),(rp,rt) in itertools.product([(14,1.5),(20,2.0)],[(5,25),(7,30)]):
        lo_b,mid_b,_ = bb(cl,bp,k); rs = rsi(cl,rp)
        R(f"BB_RSI_{bp}_{rp}<{rt}_{tag}",
          norm(persist((cl<lo_b)&(rs<rt), cl>=mid_b)), cl, fee)

    # 3  VWAP reversion
    for p,pb in [(24,0.015),(24,0.020),(48,0.015)]:
        vw = vwap(cl,hi,lo,vo,p)
        R(f"VWAP_{p}_{int(pb*1000)}_{tag}",
          norm(persist(cl<vw*(1-pb), cl>=vw*(1+0.005))), cl, fee)

    # 4  MACD cross
    for f,s,sg in [(6,13,4),(8,21,5)]:
        line = ema(cl,f)-ema(cl,s); sig2 = ema(line,sg); hist = line-sig2
        R(f"MACD_{f}_{s}_{tag}",
          norm(persist((hist>0)&(hist.shift(1)<=0),(hist<0)&(hist.shift(1)>=0))), cl, fee)

    # 5  Donchian breakout
    for p in [12,24]:
        hin = cl.rolling(p).max().shift(1); lon = cl.rolling(p//2).min().shift(1)
        R(f"Donchian_{p}_{tag}", norm(persist(cl>hin, cl<=lon)), cl, fee)

    # 6  Keltner reversion
    for ep,ap,m in [(20,10,2.0),(14,10,1.5)]:
        em = ema(cl,ep); at = atr(cl,hi,lo,ap)
        R(f"Kelt_{ep}_{m}_{tag}", norm(persist(cl<em-m*at, cl>=em)), cl, fee)

    # 7  Supertrend
    for ap,m in [(10,3.0),(7,2.0)]:
        at = atr(cl,hi,lo,ap); lb = ((hi+lo)/2)-m*at
        R(f"ST_{ap}_{m}_{tag}", norm(persist(cl>lb.shift(1), cl<lb)), cl, fee)

    # 8  StochRSI
    for rp,sp in [(7,7),(14,14)]:
        rs = rsi(cl,rp); lr=rs.rolling(sp).min(); hr=rs.rolling(sp).max()
        srsi = (rs-lr)/(hr-lr+1e-9)*100
        R(f"StochRSI_{rp}_{sp}_{tag}",
          norm(persist(srsi<15, srsi>75)), cl, fee)

    # 9  Gap fade [ORIGINAL]
    for gp,h in [(0.020,4),(0.025,6),(0.015,3)]:
        ret1 = cl.pct_change()
        entry = ret1.shift(1) <= -gp
        hm = sum(entry.shift(i).fillna(False).astype(float) for i in range(h))
        R(f"GapFade_{int(gp*1000)}h{h}_{tag}", norm((hm>0).astype(float)), cl, fee)

    # 10 Vol-gated MR [ORIGINAL]
    for rp,et,vm in [(5,25,1.2),(5,20,1.5),(3,20,1.3)]:
        rs = rsi(cl,rp); at = atr(cl,hi,lo,14)
        avg_at = at.rolling(24*5,min_periods=48).mean()
        R(f"VolGMR_r{rp}<{et}_v{vm}_{tag}",
          norm(persist((at>avg_at*vm)&(rs.shift(1)<et), rs>60)), cl, fee)

    # 11 Cascade EMA [ORIGINAL]
    for (f,m,s),pull in itertools.product([(8,21,55),(13,34,89)],[40,45]):
        ef=ema(cl,f); em2=ema(cl,m); es=ema(cl,s); rs=rsi(cl,5)
        R(f"Cascade_{f}_{m}_{s}_p{pull}_{tag}",
          norm(persist((ef>em2)&(em2>es)&(rs<pull), ef<em2)), cl, fee)

    # 12 Triple Confluence [ORIGINAL]
    for rp,rt,rx in [(5,25,60),(7,30,65)]:
        rs=rsi(cl,rp); lo_b,_,_ = bb(cl,20,2.0); vw=vwap(cl,hi,lo,vo,24)
        R(f"Triple_{rp}<{rt}_{tag}",
          norm(persist((rs.shift(1)<rt)&(cl<lo_b)&(cl<vw*0.99), rs>rx)), cl, fee)

    # 13 ATR impulse breakout [ORIGINAL]
    for ap,m,h in [(14,1.5,6),(14,2.0,8)]:
        at=atr(cl,hi,lo,ap); mv=cl.diff().abs()
        entry = (mv.shift(1)>at.shift(1)*m)&(cl.diff().shift(1)>0)
        hm = sum(entry.shift(i).fillna(False).astype(float) for i in range(h))
        R(f"ATRBreak_{ap}_{m}h{h}_{tag}", norm((hm>0).astype(float)), cl, fee)

    # 14 Regime switcher [ORIGINAL]
    for rp,mr_e,mr_x in [(5,30,60),(5,25,55)]:
        up=(hi-hi.shift(1)).clip(lower=0); dn=(lo.shift(1)-lo).clip(lower=0)
        at=atr(cl,hi,lo,14)
        dip=up.ewm(span=14,adjust=False).mean()/(at+1e-9)*100
        dim=dn.ewm(span=14,adjust=False).mean()/(at+1e-9)*100
        dx=((dip-dim).abs()/(dip+dim+1e-9)*100)
        adx=dx.ewm(span=14,adjust=False).mean()
        rs=rsi(cl,rp); mom=cl.pct_change(12)
        mr_en = (adx<20)&(rs.shift(1)<mr_e)
        mo_en = (adx>25)&(mom>0)&(mom.shift(1)<=0)
        mr_ex = rs>mr_x; mo_ex = mom<0
        R(f"Regime_r{rp}_{tag}",
          norm(persist(mr_en|mo_en, mr_ex|mo_ex)), cl, fee)

    # 15 Pairs spread [ORIGINAL]
    cols = list(cl.columns)
    if len(cols) >= 2:
        sa,sb = cols[0], cols[1]
        for p,ze in [(48,2.0),(24,1.5)]:
            spread=np.log(cl[sa]/cl[sb]); mn=spread.rolling(p).mean(); st=spread.rolling(p).std()
            z=(spread-mn)/(st+1e-9)
            tw = pd.DataFrame(0.0, index=cl.index, columns=cl.columns)
            tw[sa] = persist((z<-ze).to_frame(sa).rename(columns={sa:sa}),
                              (z.abs()<0.5).to_frame(sa).rename(columns={sa:sa}))[sa]
            tw[sb] = persist((z>ze).to_frame(sb).rename(columns={sb:sb}),
                              (z.abs()<0.5).to_frame(sb).rename(columns={sb:sb}))[sb]
            R(f"Pairs_{sa[:3]}_{sb[:3]}_p{p}_{tag}", norm(tw), cl, fee)

    print(f"  {len(results)-n0} result rows")

sweep(cl_c, hi_c, lo_c, vo_c, FEE_CRYPTO, "crypto")
sweep(cl_s, hi_s, lo_s, vo_s, FEE_STOCKS, "stocks")

# ─── report ───────────────────────────────────────────────────────────────
df = pd.DataFrame(results)
if df.empty:
    print("No results."); sys.exit(1)

df = df.sort_values("days_3pct", ascending=False)
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 30)
N = int(df.n_days.median())
C = ["name","avg_day","days_3pct","pct_3pct","days_neg3","cagr","sharpe","maxdd","final"]

print(f"\n{'='*80}")
print(f"  TOP 25 — DAYS ≥ +3%  (of ~{N} total days)")
print(f"{'='*80}")
print(df[C].head(25).to_string(index=False, float_format=lambda x: f"{x:.2f}"))

pos = df[df.avg_day > 0].sort_values("avg_day", ascending=False)
print(f"\n{'='*80}")
print("  TOP 10 — HIGHEST AVERAGE DAILY RETURN (positive only)")
print(f"{'='*80}")
print(pos[C].head(10).to_string(index=False, float_format=lambda x: f"{x:.2f}") if len(pos) else "  none positive")

print(f"\n{'='*80}")
print("  TOP 10 — SHARPE")
print(f"{'='*80}")
print(df.sort_values("sharpe",ascending=False)[C].head(10).to_string(index=False, float_format=lambda x: f"{x:.2f}"))

b = df.iloc[0]
print(f"\n{'='*80}")
print(f"  ★  WINNER: {b['name']}")
print(f"     Days ≥ +3%:  {b['days_3pct']} / {b['n_days']}  ({b['pct_3pct']:.1f}% of days)")
print(f"     Avg day:     {b['avg_day']:+.3f}%")
print(f"     CAGR:        {b['cagr']:+.1f}%   |   $100k → ${b['final']:,.0f}")
print(f"     Sharpe:      {b['sharpe']:.2f}   |   Max DD: {b['maxdd']:.1f}%")
print(f"{'='*80}")

Path("backtest_output").mkdir(exist_ok=True)
df.to_csv("backtest_output/mega_sweep.csv", index=False)
print(f"\nFull results: backtest_output/mega_sweep.csv ({len(df)} rows)")
