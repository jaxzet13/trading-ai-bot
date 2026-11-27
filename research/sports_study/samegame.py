"""Same-game parlays: are the legs of one game linked, while Kalshi's combo market makers price them as unrelated?

Live check, Nov 27 2026 (8 NBA combos quoted): favourite covers + over, and underdog wins + over, were quoted within
~0.5c of the two leg asks multiplied. Kalshi refuses combos where one leg guarantees the other (win + cover).

So a combo is worth buying when P(both legs) is clearly above P(leg 1) x P(leg 2). This measures that from settled
games: for each game the main spread and main total line (the most-traded strike of each, roughly the 50% line), the
pre-game favourite (from the game-winner candles 60 minutes before the start, data/sports/<series>.jsonl), and the
outcomes. For each combo type: how often both legs won vs the product of how often each leg won (lift), and the
profit of buying the combo at the product price (legs priced at their win rates, + Kalshi's fee on the combo).

    python3 research/sports_study/samegame.py NBA NFL ...
"""
import collections
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from tennis import api, lab                                   # noqa: E402
from tennis import history as H                               # noqa: E402

LEAGUES = {"NBA": ("KXNBAGAME", "KXNBASPREAD", "KXNBATOTAL"), "NFL": ("KXNFLGAME", "KXNFLSPREAD", "KXNFLTOTAL"),
           "NCAAMB": ("KXNCAAMBGAME", "KXNCAAMBSPREAD", "KXNCAAMBTOTAL"), "NCAAF": ("KXNCAAFGAME", "KXNCAAFSPREAD", "KXNCAAFTOTAL"),
           "NHL": ("KXNHLGAME", "KXNHLSPREAD", "KXNHLTOTAL")}
CACHE = Path("data/sports/settled_lists")


def settled_list(series, days=60):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{series}.json"
    if p.exists():
        return json.loads(p.read_text())
    import time
    ms = H.settled(series, int(time.time()) - days * 86400)
    p.write_text(json.dumps(ms))
    return ms


def game_key(event_ticker):
    return event_ticker.split("-", 1)[1]                       # e.g. 26NOV27MIANYK


def fee(p):
    return 0.07 * p * (1 - p)


def study(league):
    g, s, t = LEAGUES[league]
    gpath = Path("data/sports") / f"{g}.jsonl"
    if not gpath.exists():
        return {"league": league, "note": "no game history yet"}
    ms = lab.load(gpath)
    ok, mid, _, _ = lab._band_arrays(ms, -60)
    fav = {}
    for i, m in enumerate(ms):
        if ok[i] and mid[i] > 0.5:
            fav[game_key(m["event"])] = (m["ticker"].rsplit("-", 1)[1], float(mid[i]), m["value"])
    spreads, totals = collections.defaultdict(list), collections.defaultdict(list)
    for m in settled_list(s):
        spreads[game_key(m["event_ticker"])].append(m)
    for m in settled_list(t):
        totals[game_key(m["event_ticker"])].append(m)
    rows = []
    for gk, (team, pfav, won) in fav.items():
        if gk not in spreads or gk not in totals:
            continue
        sp = [m for m in spreads[gk] if m["ticker"].split("-")[-1].rstrip("0123456789") == team]
        if not sp or not totals[gk]:
            continue
        msp = max(sp, key=lambda m: float(m.get("volume_fp") or 0))
        mto = max(totals[gk], key=lambda m: float(m.get("volume_fp") or 0))
        if msp.get("result") not in ("yes", "no") or mto.get("result") not in ("yes", "no"):
            continue
        rows.append({"pfav": pfav, "fav_win": float(won >= 0.5), "cover": float(msp["result"] == "yes"),
                     "over": float(mto["result"] == "yes")})
    n = len(rows)
    if n < 30:
        return {"league": league, "games": n, "note": "too few games with all three markets"}
    a = {k: np.array([r[k] for r in rows]) for k in rows[0]}
    dog = 1 - a["fav_win"]
    under = 1 - a["over"]
    combos = {"favourite wins + over": (a["fav_win"], a["over"], a["pfav"]),
              "favourite wins + under": (a["fav_win"], under, a["pfav"]),
              "underdog wins + over": (dog, a["over"], 1 - a["pfav"]),
              "underdog wins + under": (dog, under, 1 - a["pfav"]),
              "favourite covers + over": (a["cover"], a["over"], None),
              "favourite covers + under": (a["cover"], under, None),
              "underdog covers + over": (1 - a["cover"], a["over"], None),
              "underdog covers + under": (1 - a["cover"], under, None)}
    out = {"league": league, "games": n, "base_rates": {"favourite won": round(float(a["fav_win"].mean()), 3),
                                                        "favourite covered": round(float(a["cover"].mean()), 3),
                                                        "over": round(float(a["over"].mean()), 3)}, "combos": {}}
    for name, (x, y, px) in combos.items():
        both = x * y
        # price each leg at its market price: winner leg from the game candles, line legs at 0.50 (main line)
        leg1 = px if px is not None else np.full(n, 0.5)
        price = leg1 * 0.5
        pnl = both - price - fee(price)
        se = pnl.std(ddof=1) / math.sqrt(n)
        out["combos"][name] = {"both_rate": round(float(both.mean()), 3),
                               "product_rate": round(float(x.mean() * y.mean()), 3),
                               "lift": round(float(both.mean() / max(x.mean() * y.mean(), 1e-9)), 3),
                               "profit_per_1": round(float(pnl.mean()), 3), "t": round(float(pnl.mean() / se), 2) if se > 0 else 0.0}
    return out


def main():
    res = {}
    for lg in (sys.argv[1:] or ["NBA", "NFL"]):
        r = study(lg)
        res[lg] = r
        print(json.dumps(r, indent=1))
    p = Path("research/sports_study/samegame_results.json")
    old = json.loads(p.read_text()) if p.exists() else {}
    old.update(res)
    p.write_text(json.dumps(old, indent=1))


if __name__ == "__main__":
    main()
