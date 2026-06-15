"""
Head-to-head: HOLD vs TAKE-PROFIT-at-1.5%-and-redeploy.

Tests the actual ATR Impulse Breakout entry on the live trading universe
(high-vol stocks + crypto), 3 years of daily bars. For every trade it
compares two exit rules:

  HOLD : exit after H bars at the close (current system)
  TP   : exit the first day the high touches entry*1.015 (+1.5%),
         otherwise fall back to the H-bar close exit

Key metric is RETURN-PER-BAR (capital efficiency) because the whole premise
of "take profit fast and redeploy" is that you free capital sooner. If TP's
return-per-bar (net of fees) is higher, the idea has merit. If not, it doesn't.
"""
from __future__ import annotations
import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import yfinance as yf

HIGH_VOL = ["TSLA","NVDA","AMD","MSTR","COIN","SMCI","PLTR","RKLB","IONQ",
            "HOOD","SOFI","RIVN","LCID","SOUN","UPST","MARA","RIOT","CLSK","APP","DKNG"]
CRYPTO   = ["BTC-USD","ETH-USD","SOL-USD","DOGE-USD"]

ATR_P, ATR_MULT, HOLD = 14, 2.0, 8
TP = 0.015
FEE_STOCK = 0.0004   # ~0.04% round-trip slippage, $0 commission
FEE_CRYPTO = 0.005   # ~0.5% round-trip (0.25%/side)

def atr(c, h, l, p):
    prev = c.shift(1)
    tr = pd.concat([h-l, (h-prev).abs(), (l-prev).abs()], axis=1).max(axis=1)
    return tr.ewm(span=p, adjust=False).mean()

def analyze(sym, fee):
    df = yf.download(sym, period="3y", interval="1d", auto_adjust=True, progress=False)
    if df.empty or len(df) < 60:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    c, h, l = df["Close"], df["High"], df["Low"]
    a = atr(c, h, l, ATR_P)
    move = c.diff().abs()
    # entry signal at bar i: prior bar was a strong upward impulse
    entry = (move.shift(1) > a.shift(1) * ATR_MULT) & (c.diff().shift(1) > 0)
    idx = np.where(entry.values)[0]
    n = len(c)

    hold_rets, hold_bars = [], []
    tp_rets, tp_bars = [], []
    tp_hits = 0
    for i in idx:
        if i + 1 >= n:
            continue
        ep = c.iloc[i]
        end = min(i + HOLD, n - 1)
        # HOLD exit
        hold_rets.append(c.iloc[end] / ep - 1 - fee)
        hold_bars.append(end - i)
        # TP exit: first bar whose HIGH reaches +1.5%
        hit = None
        for j in range(i + 1, end + 1):
            if h.iloc[j] >= ep * (1 + TP):
                hit = j
                break
        if hit is not None:
            tp_rets.append(TP - fee)
            tp_bars.append(hit - i)
            tp_hits += 1
        else:
            tp_rets.append(c.iloc[end] / ep - 1 - fee)
            tp_bars.append(end - i)
    if not hold_rets:
        return None
    return dict(
        sym=sym, trades=len(hold_rets),
        hold_avg=np.mean(hold_rets), hold_bars=np.mean(hold_bars),
        tp_avg=np.mean(tp_rets), tp_bars=np.mean(tp_bars),
        tp_hit_rate=tp_hits / len(hold_rets),
    )

rows = []
for s in HIGH_VOL:
    r = analyze(s, FEE_STOCK)
    if r: rows.append(r)
for s in CRYPTO:
    r = analyze(s, FEE_CRYPTO)
    if r: rows.append(r)

df = pd.DataFrame(rows)
# return-per-bar = capital efficiency (the redeploy premise)
df["hold_rpb"] = df.hold_avg / df.hold_bars
df["tp_rpb"]   = df.tp_avg / df.tp_bars

print(f"\n{'sym':<9}{'trades':>7}{'HOLD ret':>10}{'HOLD/bar':>10}{'TP ret':>9}{'TP/bar':>9}{'TPhit%':>8}")
print("-" * 62)
for _, r in df.iterrows():
    print(f"{r.sym:<9}{r.trades:>7.0f}{r.hold_avg*100:>9.2f}%{r.hold_rpb*100:>9.3f}%"
          f"{r.tp_avg*100:>8.2f}%{r.tp_rpb*100:>8.3f}%{r.tp_hit_rate*100:>7.0f}%")

print("-" * 62)
# weight each symbol by its trade count
tw = df.trades / df.trades.sum()
hold_rpb = (df.hold_rpb * tw).sum()
tp_rpb   = (df.tp_rpb * tw).sum()
hold_ret = (df.hold_avg * tw).sum()
tp_ret   = (df.tp_avg * tw).sum()
print(f"\nTrade-weighted averages:")
print(f"  HOLD  : {hold_ret*100:+.2f}% per trade over {(df.hold_bars*tw).sum():.1f} bars "
      f"= {hold_rpb*100:+.3f}% per bar")
print(f"  TP    : {tp_ret*100:+.2f}% per trade over {(df.tp_bars*tw).sum():.1f} bars "
      f"= {tp_rpb*100:+.3f}% per bar")

# Annualise return-per-bar (≈252 trading days/yr, assume always redeployed)
print(f"\nIf you could ALWAYS stay deployed (best case for the redeploy idea):")
print(f"  HOLD  annualised: {((1+hold_rpb)**252 - 1)*100:>8.0f}%")
print(f"  TP    annualised: {((1+tp_rpb)**252 - 1)*100:>8.0f}%")
winner = "TP (your idea)" if tp_rpb > hold_rpb else "HOLD (current system)"
print(f"\n  >>> Higher capital efficiency: {winner}")
