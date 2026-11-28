"""La Liga and Premier League: what the walk-forward strategy search makes on games played AFTER the Nov 28 freeze.

Account holder, Nov 28: "Do way more backtesting on La Liga and Premier League to find crazy good strategies ... since they
were the most profitable in the backtests". Kalshi only lists soccer winners since Oct 9, so each league has ~60 games and
the "profit" rests on 26 (La Liga) and 8 (EPL) bets: no amount of re-testing the same games can separate skill from luck.
research/soccer_focus/search_frozen_nov28.json is the baseline. This re-downloads new games, re-runs the same search
(same grid, same walk-forward, same corrected clock) and prints the extra bets and money since the freeze, which is the only
honest test left. It reports top-5 walk-forward results (the same view as the baseline).

    python3 research/soccer_focus/forward_soccer.py
"""
import json
import os
import subprocess
import sys

SER = ["KXLALIGAGAME", "KXEPLGAME", "KXUCLGAME", "KXBUNDESLIGAGAME", "KXMLSGAME", "KXLIGAMXGAME"]
BASE = "research/soccer_focus/search_frozen_nov28.json"
NOW = "research/soccer_focus/search_latest.json"

env = dict(os.environ, MIN_MARKETS="100", SEARCH_OUT=NOW)
subprocess.run([sys.executable, "research/sports_study/download.py", "200"] + SER, check=False, capture_output=True)
subprocess.run([sys.executable, "research/sports_study/fix_clock.py"] + SER, check=False, capture_output=True)
subprocess.run([sys.executable, "research/sports_study/search.py"] + SER, env=env, check=False, capture_output=True)
a, b = json.load(open(BASE)), json.load(open(NOW))
out = {}
for s in SER[:2] + ["POOLED"]:
    x, y = a.get(s) or {}, b.get(s) or {}
    wa, wb = x.get("walk_top5") or {}, y.get("walk_top5") or {}
    na, nb = wa.get("bets", 0), wb.get("bets", 0)
    pa = na * wa.get("cents_per_bet", 0) / 100
    pb = nb * wb.get("cents_per_bet", 0) / 100
    out[s] = {"frozen_bets": na, "now_bets": nb, "new_bets": nb - na, "new_pnl_per_contract": round(pb - pa, 2),
              "new_cents_per_bet": round(100 * (pb - pa) / (nb - na), 2) if nb > na else None}
print(json.dumps(out))
json.dump(out, open("research/soccer_focus/forward_results.json", "w"), indent=1)
