"""Backtest: Kalshi's price against DraftKings' moneyline, on every game in the downloaded history (Nov 28 2026).

ESPN's public API keeps DraftKings' (closing) moneyline for finished games. For each downloaded Kalshi game-winner
market this takes the no-vig DraftKings win chance and, at M minutes before the start, buys YES (or NO) when the book
says Kalshi is mispriced by more than the fee plus a bar. Fills are the honest ones used everywhere else here: decided
on one minute's quote, filled the next minute at the worst price, Kalshi's fee paid.

Caveat, stated up front: the line is the CLOSING line, which already contains news that arrived after the decision
minute, so the result flatters the rule. If it still shows nothing, there is nothing here. If it shows something, the
forward recorder (record.py) is the real test.

    python3 research/sports_odds/backtest.py [series ...]   -> research/sports_odds/backtest_results.json
"""
import collections
import datetime as dt
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, "research/sports_odds")
from record import LEAGUES, norm, prob                          # noqa: E402

DATA = Path("data/sports")
HIST = Path("data/sports_odds/hist")
OUT = Path("research/sports_odds/backtest_results.json")
CORE = "https://sports.core.api.espn.com/v2/sports"
SITE = "https://site.api.espn.com/apis/site/v2/sports"
MINUTES = (15, 60, 120)
BARS = (0.0, 0.02, 0.04, 0.06, 0.08)
SERIES_PATH = {v: k for k, v in LEAGUES.items()}
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:5.0f}s]", *a, flush=True)


def fee(p):
    return 0.07 * p * (1 - p)


def get(url, params=None):
    for i in range(3):
        try:
            r = requests.get(url, params=params, timeout=25)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(1 + i)
    return None


def scoreboard(path, day):
    f = HIST / f"sb_{path.replace('/', '_')}_{day}.json"
    if f.exists():
        return json.load(open(f))
    groups = "80" if path == "football/college-football" else "50" if path == "basketball/mens-college-basketball" else None
    d = get(f"{SITE}/{path}/scoreboard", {"dates": day, "limit": 400, **({"groups": groups} if groups else {})}) or {}
    out = []
    for e in d.get("events", []):
        try:
            c = e["competitions"][0]
            teams = {t["homeAway"]: t["team"] for t in c["competitors"]}
            out.append({"id": e["id"], "start": dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00")).timestamp(),
                        "names": {s: sorted({norm(teams[s].get(x)) for x in ("location", "shortDisplayName", "displayName", "name", "abbreviation")} - {""})
                                  for s in ("home", "away")}})
        except Exception:
            continue
    f.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(f, "w"))
    return out


def book(path, eid):
    f = HIST / f"odds_{path.replace('/', '_')}_{eid}.json"
    if f.exists():
        return json.load(open(f))
    sport, league = path.split("/")
    d = get(f"{CORE}/{sport}/leagues/{league}/events/{eid}/competitions/{eid}/odds")
    res = None
    for it in (d or {}).get("items", []):
        ph, pa = prob((it.get("homeTeamOdds") or {}).get("moneyLine")), prob((it.get("awayTeamOdds") or {}).get("moneyLine"))
        if ph is None or pa is None:
            continue
        pd_ = prob((it.get("drawOdds") or {}).get("moneyLine")) or 0.0
        z = ph + pa + pd_
        res = {"home": ph / z, "away": pa / z, "draw": pd_ / z, "provider": (it.get("provider") or {}).get("name")}
        if (it.get("provider") or {}).get("name") == "DraftKings":
            break
    f.parent.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(f, "w"))
    return res


def load_events(series):
    ev = collections.defaultdict(list)
    for ln in open(DATA / f"{series}.jsonl"):
        m = json.loads(ln)
        if m.get("result") in ("yes", "no") and m.get("bars"):
            ev[m["event"]].append(m)
    return ev


def match(series, ev):
    path = SERIES_PATH[series]
    days = set()
    for ms in ev.values():
        s = ms[0]["start"]
        for k in (-1, 0, 1):
            days.add(dt.datetime.fromtimestamp(s + k * 86400, dt.timezone.utc).strftime("%Y%m%d"))
    with ThreadPoolExecutor(6) as ex:
        sbs = dict(zip(sorted(days), ex.map(lambda d: scoreboard(path, d), sorted(days))))
    games = {}
    for lst in sbs.values():
        for g in lst:
            games[g["id"]] = g
    pairs = {}
    for e, ms in ev.items():
        s = ms[0]["start"] - 3 * 3600                 # Kalshi's occurrence time is ~3 h after kickoff for team sports
        for g in games.values():
            if abs(g["start"] - s) > 4 * 3600:
                continue
            side = {}
            for m in ms:
                n = norm(m.get("player"))
                if n in ("tie", "draw"):
                    side[m["ticker"]] = "draw"
                for sd in ("home", "away"):
                    if n and n in g["names"][sd]:
                        side[m["ticker"]] = sd
            if {"home", "away"} <= set(side.values()):
                pairs[e] = (g["id"], side, g["start"])
                break
    return path, pairs


def sim(series):
    ev = load_events(series)
    path, pairs = match(series, ev)
    ids = sorted({v[0] for v in pairs.values()})
    with ThreadPoolExecutor(6) as ex:
        bk = dict(zip(ids, ex.map(lambda i: book(path, i), ids)))
    rows = collections.defaultdict(list)       # (minutes) -> dicts
    used = 0
    for e, (gid, side, real_start) in pairs.items():      # real_start = ESPN's kickoff (Kalshi's own start field is 3 h late)
        b = bk.get(gid)
        if not b:
            continue
        used += 1
        for m in ev[e]:
            sd = side.get(m["ticker"])
            if not sd or b.get(sd) is None:
                continue
            bars = m["bars"]
            bt = np.array([x[0] for x in bars])
            y = float(m["result"] == "yes")
            for mins in MINUTES:
                t = real_start - 60 * mins
                i = int(np.searchsorted(bt, t, "right") - 1)
                if i < 0 or i + 1 >= len(bars) or t - bt[i] > 600:
                    continue
                bid, ask = bars[i][1], bars[i][3]
                fa, fb = bars[i + 1][4], bars[i + 1][2]          # next minute: worst ask (YES), lowest bid (NO)
                if None in (bid, ask, fa, fb):
                    continue
                rows[mins].append({"day": int(real_start // 86400), "book": b[sd], "bid": bid, "ask": ask, "fa": fa, "fb": fb, "y": y})
    log(f"{series}: {len(ev)} Kalshi games, {len(pairs)} matched to ESPN, {used} with a book line")
    return rows, len(ev), len(pairs), used


def score(rows, bar):
    p, d = [], []
    for r in rows:
        ey = r["book"] - r["ask"] - fee(r["ask"])
        na = 1 - r["bid"]
        en = (1 - r["book"]) - na - fee(na)
        if ey >= bar and 0.05 <= r["fa"] <= 0.95:
            p.append(r["y"] - r["fa"] - fee(r["fa"])); d.append(r["day"])
        elif en >= bar and 0.05 <= 1 - r["fb"] <= 0.95:
            fn = 1 - r["fb"]
            p.append((1 - r["y"]) - fn - fee(fn)); d.append(r["day"])
    if len(p) < 5:
        return {"bets": len(p)}
    p, d = np.array(p), np.array(d)
    days = np.unique(d)
    dd = np.array([p[d == x].sum() for x in days])
    t = dd.mean() / dd.std(ddof=1) * math.sqrt(len(dd)) if len(dd) > 2 and dd.std(ddof=1) > 0 else 0
    h = len(days) // 2
    half = lambda m: round(100 * float(p[m].mean()), 2) if m.sum() else None
    return {"bets": len(p), "cents_per_bet": round(100 * float(p.mean()), 2), "t": round(float(t), 2), "days": len(days),
            "halves": [half(d < days[h]), half(d >= days[h])], "win_rate": round(float((p > -0.5).mean()), 3)}


def main():
    series = sys.argv[1:] or [s for s in SERIES_PATH if (DATA / f"{s}.jsonl").exists()]
    res, allrows = {}, collections.defaultdict(list)
    for s in series:
        try:
            rows, n, mt, used = sim(s)
        except Exception as e:
            log(f"{s}: {e!r}")
            continue
        res[s] = {"games": n, "matched": mt, "with_book": used}
        for mins, rr in rows.items():
            allrows[mins] += rr
            res[s][f"m{mins}"] = {f"bar{b}": score(rr, b) for b in BARS}
            ll = lambda f: round(float(-np.mean([x["y"] * math.log(max(f(x), 1e-3)) + (1 - x["y"]) * math.log(max(1 - f(x), 1e-3)) for x in rr])), 4)
            res[s][f"m{mins}"]["logloss"] = {"book": ll(lambda x: x["book"]), "kalshi_mid": ll(lambda x: (x["bid"] + x["ask"]) / 2)}
            log(s, f"{mins} min before:", {k: (v if k == "logloss" else (v.get("bets"), v.get("cents_per_bet"), v.get("t"))) for k, v in res[s][f"m{mins}"].items()})
    res["ALL"] = {}
    for mins, rr in allrows.items():
        res["ALL"][f"m{mins}"] = {f"bar{b}": score(rr, b) for b in BARS}
        log("ALL", f"{mins} min before:", {k: (v.get("bets"), v.get("cents_per_bet"), v.get("t"), v.get("halves")) for k, v in res["ALL"][f"m{mins}"].items()})
    json.dump(res, open(OUT, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
