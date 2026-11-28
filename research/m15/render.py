"""Build the 15-minute markets artifact page (dashboard/m15_markets.html) from research/m15/results.json (Nov 28 2026)."""
import json
import re
import time
from pathlib import Path

R = json.load(open("research/m15/results.json"))
res = R["results"]
glob = res["_best_of_everything"]
try:
    vol = {r[0]: r for r in json.load(open("research/other_markets/fifteen_min.json"))}
except Exception:
    vol = {}
NAMES = {"KXBTC15M": "Bitcoin", "KXETH15M": "Ethereum", "KXSOL15M": "Solana", "KXXRP15M": "XRP", "KXDOGE15M": "Dogecoin",
         "KXNEAR15M": "NEAR", "KXHYPE15M": "HYPE", "KXZEC15M": "Zcash", "KXBNB15M": "BNB", "KXGOLD15M": "Gold", "KXWTI15M": "WTI oil",
         "KXSILVER15M": "Silver", "KXNATGAS15M": "Natural gas", "KXCOPPER15M": "Copper", "KXBRENT15M": "Brent oil",
         "KXPLATINUM15M": "Platinum", "KXPALLADIUM15M": "Palladium", "KXUSDJPY15M": "USD/JPY", "KXEURUSD15M": "EUR/USD",
         "KXAUDUSD15M": "AUD/USD", "KXGBPUSD15M": "GBP/USD", "KXUSDCAD15M": "USD/CAD", "KXUSDMXN15M": "USD/MXN",
         "KXINX15M": "S&P 500", "KX2YRRATE15M": "2-year yield", "KX5YRRATE15M": "5-year yield", "KX10YRRATE15M": "10-year yield",
         "KX30YRRATE15M": "30-year yield", "METALS": "All metals", "ENERGY": "All energy", "FX": "All currencies",
         "RATES": "All Treasury yields", "CRYPTO": "All crypto coins", "ALL": "Everything pooled"}
MODEL = {"KXBNB15M": (2.3, 1.0), "KXBTC15M": (-0.4, -0.1), "KXDOGE15M": (4.1, 2.3), "KXETH15M": (0.8, 0.3), "KXHYPE15M": (-3.4, -1.5),
         "KXNEAR15M": (5.4, 3.4), "KXSOL15M": (4.7, 2.3), "KXXRP15M": (5.9, 3.6), "KXZEC15M": (6.3, 4.7)}


def c(x):
    return f"{x:+.1f}".replace("-", "&minus;") + "&cent;"


def verdict(w):
    if w["t"] >= 2.5 and w["cents_per_bet"] > 1 and min(w["halves"]) > 0:
        return ("edge", "Edge")
    if w["t"] >= 1.5 and w["cents_per_bet"] > 0:
        return ("maybe", "Maybe, unproven")
    return ("no", "No edge")


rows = []
for k, v in res.items():
    if k.startswith("_") or "walk_top5" not in v:
        continue
    w = v["walk_top5"]
    cls, lab = verdict(w)
    kind = 0 if k in NAMES and k.endswith("15M") else 1
    rows.append((kind, k, v, w, cls, lab))
rows.sort(key=lambda r: (r[0], -(vol.get(r[1], [0, 0, 0, 0, 0])[4] if r[1] in vol else 0)))
body = []
for kind, k, v, w, cls, lab in rows:
    mt = MODEL.get(k)
    body.append(f"<tr><td>{NAMES.get(k, k)}</td><td class='num'>{v['strategies_scored']:,}</td>"
                f"<td class='num'>{c(w['cents_per_bet'])}</td><td class='num'>{w['t']:+.2f}</td><td class='num'>{w['bets']}</td>"
                f"<td class='num'>{'' if not mt else c(mt[0])}</td><td><span class='pill {cls}'>{lab}</span></td></tr>")
g = glob
gw = {K: g[f"walk_top{K}"] for K in (1, 5, 20)}
best = sorted((r for r in rows if r[0] == 0 or r[1] in ("ALL",)), key=lambda r: -r[3]["t"])[:3]
n_edge = sum(1 for r in rows if r[4] == "edge")
n_maybe = sum(1 for r in rows if r[4] == "maybe")
headline = ("No proven edge in the 15-minute markets (yet)." if n_edge == 0 else f"{n_edge} market group(s) pass the test.")
lead = (f"I tested {g['total_strategies_generated']:,} strategies on {len(rows)} groups of Kalshi 15-minute markets. "
        f"Strategies picked only from earlier days were bet on later days, and none held up after Kalshi's fee.")
src = Path("dashboard/sports_study.html").read_text()
style = re.search(r"<style>.*?</style>", src, re.S).group(0)
page = f"""<title>15-Minute Markets Test</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;600&family=Unbounded:wght@500;700&display=swap">
{style}
<main>
  <section>
    <div class="eyebrow">Kalshi 15-minute markets &middot; gold, oil, metals, currencies, S&amp;P, yields and crypto &middot; updated {R['updated']}</div>
    <h1>{headline}</h1>
    <p class="lead">{lead}</p>
    <div class="facts">
      <div><b>{g['total_strategies_generated'] / 1e6:.1f}M</b><span>strategies generated</span></div>
      <div><b>{g['total_strategies_scored'] / 1e6:.1f}M</b><span>with 30+ bets, scored</span></div>
      <div><b>{len(rows)}</b><span>market groups</span></div>
      <div><b>{n_edge}</b><span>pass the test</span></div>
    </div>
  </section>

  <section>
    <h2>The best of everything</h2>
    <p>Each day, take the best strategies across <em>all</em> {g['total_strategies_scored']:,} on earlier days only, and bet them on that day. This is the fairest "pick the winner" test.</p>
    <div class="tw"><table>
      <thead><tr><th>Bet the top</th><th class="num">Bets</th><th class="num">Per $1 bet</th><th class="num">t</th><th class="num">Days</th></tr></thead>
      <tbody>
        <tr><td>1 strategy</td><td class="num">{gw[1]['bets']}</td><td class="num">{c(gw[1]['cents_per_bet'])}</td><td class="num">{gw[1]['t']:+.2f}</td><td class="num">{gw[1]['days']}</td></tr>
        <tr><td>5 strategies</td><td class="num">{gw[5]['bets']}</td><td class="num">{c(gw[5]['cents_per_bet'])}</td><td class="num">{gw[5]['t']:+.2f}</td><td class="num">{gw[5]['days']}</td></tr>
        <tr><td>20 strategies</td><td class="num">{gw[20]['bets']}</td><td class="num">{c(gw[20]['cents_per_bet'])}</td><td class="num">{gw[20]['t']:+.2f}</td><td class="num">{gw[20]['days']}</td></tr>
      </tbody>
    </table></div>
    <p class="mute">A real edge needs a t of about 2.5 or more and gains in both halves of the period. By luck alone, the best of {g['total_strategies_scored']:,} strategies would look like t &asymp; {g['luck_best_t']} on the data it was picked from, which is why only days the strategy never saw count.</p>
  </section>

  <section>
    <h2>Each market, tested on its own</h2>
    <p>The money column is the average result per $1 bet after Kalshi's fee, for strategies picked from earlier days. The last column is the live crypto bot's own price-based model (it also watches the coin's real price, which gold, oil and the others don't have a free feed for).</p>
    <div class="tw"><table>
      <thead><tr><th>Market</th><th class="num">Strategies</th><th class="num">Per $1 bet</th><th class="num">t</th><th class="num">Bets</th><th class="num">Live model</th><th>Verdict</th></tr></thead>
      <tbody>{''.join(body)}</tbody>
    </table></div>
  </section>

  <section>
    <h2>Should we use real money?</h2>
    <div class="note"><p>Not on these. Nothing here passes. The crypto coins the live bot trades only make money with its model, which also watches the coin's real price. Gold, oil, metals and currencies have no free price feed from here yet, so the next step is a proper price source.</p></div>
    <p class="mute">A first run on only six of these markets looked exciting (t = 3.6). With all the data (76 days, 32 market groups) it was 0.0&cent; at t = 0.0: too few days, so it was luck. That is why nothing here is promoted without a forward test on new days.</p>
  </section>

  <section>
    <h2>How it works</h2>
    <p>For every settled 15-minute window the test replays Kalshi's minute-by-minute bid and ask. Each strategy looks at the market's own quotes (price, spread, recent moves, drift since the window opened, how stretched it is) in two or three buckets at once, decides at one minute, and buys the next minute at the ask, then pays the fee.</p>
    <p class="mute">Full numbers: research/m15 in the repository.</p>
  </section>
</main>
"""
Path("dashboard/m15_markets.html").write_text(page)
print("wrote dashboard/m15_markets.html", len(rows), "groups")
