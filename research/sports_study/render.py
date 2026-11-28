"""Build dashboard/sports_study.html from research/sports_study/results.json (python3 research/sports_study/render.py)."""
import html
import json
import re
import time
from pathlib import Path

RES = Path("research/sports_study/results.json")
OUT = Path("dashboard/sports_study.html")
CSS_FROM = Path("dashboard/index_study.html")
PENDING = ["KXNBAGAME", "KXNFLGAME", "KXNCAAFGAME", "KXNCAAMBGAME", "KXNHLGAME", "KXEPLGAME", "KXUCLGAME", "KXLALIGAGAME",
           "KXCS2GAME", "KXUFCFIGHT", "KXNCAAWBGAME", "KXLIGAMXGAME", "KXMLSGAME", "KXBUNDESLIGAGAME", "KXLOLGAME", "KXDOTA2GAME"]
NAMES = {"KXNBAGAME": "NBA", "KXNFLGAME": "NFL", "KXNCAAFGAME": "College football", "KXNCAAMBGAME": "Men's college basketball",
         "KXNHLGAME": "NHL", "KXEPLGAME": "Premier League", "KXUCLGAME": "Champions League", "KXLALIGAGAME": "La Liga",
         "KXCS2GAME": "Counter-Strike 2", "KXUFCFIGHT": "UFC", "KXNCAAWBGAME": "Women's college basketball",
         "KXLIGAMXGAME": "Liga MX", "KXMLSGAME": "MLS", "KXBUNDESLIGAGAME": "Bundesliga", "KXLOLGAME": "League of Legends",
         "KXDOTA2GAME": "Dota 2"}


def css():
    src = CSS_FROM.read_text()
    style = src[src.index("<style>"):src.index("</style>") + 8]
    extra = """
.pill{display:inline-block;font:600 12px/1 var(--mono);padding:5px 8px;border-radius:999px;border:1px solid var(--line);white-space:nowrap}
.pill.no{color:var(--loss);border-color:color-mix(in srgb,var(--loss) 45%,transparent)}
.pill.maybe{color:var(--gold);border-color:color-mix(in srgb,var(--gold) 45%,transparent)}
.pill.edge{color:var(--flat);border-color:color-mix(in srgb,var(--flat) 55%,transparent)}
.pill.wait{color:var(--mute)}
td.num{font-family:var(--mono);white-space:nowrap;text-align:right}
th.num{text-align:right}
.big{font:700 clamp(22px,4.5vw,30px)/1.2 var(--display);margin:0;text-wrap:balance}
</style>"""
    return style.replace("</style>", extra)


def cell_money(c):
    if c is None:
        return "&ndash;"
    sign = "+" if c > 0 else "&minus;" if c < 0 else ""
    return f"{sign}{abs(c):.1f}&cent;"


def main():
    res = json.loads(RES.read_text()) if RES.exists() else {}
    def tested(r):                                     # a walk-forward that placed no bets (too few days) is not a test
        w = r.get("walk_forward") or {}
        w = w.get("5") or w.get(5) or {}
        return bool(w.get("bets"))

    done = [res[s] for s in PENDING if s in res and "walk_forward" in res[s] and tested(res[s])]
    edge = [r for r in done if r["verdict"] == "edge"]
    maybe = [r for r in done if r["verdict"] == "maybe"]
    rows = []
    for s in PENDING:
        r = res.get(s)
        name = NAMES.get(s, s)
        if not r:
            rows.append(f"<tr><td>{name}</td><td class='num'>&ndash;</td><td class='num'>&ndash;</td><td class='num'>&ndash;</td>"
                        f"<td><span class='pill wait'>downloading</span></td></tr>")
            continue
        if "walk_forward" not in r or not tested(r):
            rows.append(f"<tr><td>{name}</td><td class='num'>{r.get('games', r.get('markets', 0))}</td><td class='num'>&ndash;</td><td class='num'>&ndash;</td>"
                        f"<td><span class='pill wait'>too few days</span></td></tr>")
            continue
        w = r["walk_forward"]["5"] if "5" in r["walk_forward"] else r["walk_forward"][5]
        cls = {"edge": "edge", "maybe": "maybe"}.get(r["verdict"], "no")
        label = {"edge": "Edge", "maybe": "Maybe, unproven"}.get(r["verdict"], "No edge")
        rows.append(f"<tr><td>{name}</td><td class='num'>{r['games']}</td><td class='num'>{cell_money(w['cents_per_bet'])}</td>"
                    f"<td class='num'>{w['days_up']}/{w['days']}</td><td><span class='pill {cls}'>{label}</span></td></tr>")
    n_done = len(done)
    if not n_done:
        headline, lead = "Downloading game history.", "Results appear here sport by sport as each download finishes."
    elif edge:
        headline = f"{len(edge)} of {n_done} sports show an edge so far."
        lead = "An edge here means the strategies picked only from earlier days kept winning on later games. Next step for those: a forward test on new games before any real money."
    elif maybe:
        headline = f"No proven edge yet. {len(maybe)} of {n_done} sports look possible."
        lead = "“Maybe” means positive results that could still be luck. They get watched on new games before any real money goes in."
    else:
        headline = f"No edge in {n_done} of {n_done} sports tested so far."
        lead = "Strategies picked only from earlier days lost money on the later games, the same as the stock-index test."
    calib = []
    for r in done:
        bands = r.get("calibration_60min", [])
        best = max(bands, key=lambda b: b["cents_per_bet"]) if bands else None
        if best:
            calib.append(f"<tr><td>{NAMES.get(r['series'], r['series'])}</td><td class='num'>{best['band']}</td>"
                         f"<td class='num'>{cell_money(best['cents_per_bet'])}</td><td class='num'>{best['t']:+.1f}</td><td class='num'>{best['n']}</td></tr>")
    real = ("Not yet. Nothing has passed. Real money only goes in after a sport shows an edge here <em>and</em> keeps it on new games in a no-money forward test."
            if not edge else
            "Not yet for any sport. The ones marked Edge go into a no-money forward test on new games first; if they hold up there, they start small with real money.")
    page = f"""<title>Sports Backtests</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;600&family=Unbounded:wght@500;700&display=swap">
{css()}
<main>
  <section>
    <div class="eyebrow">Per-sport backtests &middot; Kalshi game-winner markets &middot; updated {time.strftime('%b %d %H:%M UTC', time.gmtime())}</div>
    <h1>{html.escape(headline)}</h1>
    <p class="lead">{lead}</p>
    <div class="facts">
      <div><b>{n_done}/{len(PENDING)}</b><span>sports tested</span></div>
      <div><b>{sum(r['games'] for r in done):,}</b><span>games scored</span></div>
      <div><b>~3,000</b><span>strategies tried per sport</span></div>
      <div><b>{len(edge)}</b><span>with an edge</span></div>
    </div>
  </section>

  <section>
    <h2>Each sport, tested on its own</h2>
    <p>Each day, the bot picked the 5 strategies that had done best on <em>earlier</em> days only, and bet them on that day's games. The money column is the average result per $1 contract after Kalshi's fee. This is the same honest test the crypto bot passed.</p>
    <div class="tw"><table>
      <thead><tr><th>Sport</th><th class="num">Games</th><th class="num">Per $1 bet</th><th class="num">Days up</th><th>Verdict</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
  </section>

  <section>
    <h2>Should we use real money?</h2>
    <div class="note"><p>{real}</p></div>
  </section>

  <section>
    <h2>Best price band an hour before the game</h2>
    <p>A simpler check: buy every team in one price band an hour before the start. This shows the best band per sport. It was picked after the fact, so treat it as a clue, not a result.</p>
    <div class="tw"><table>
      <thead><tr><th>Sport</th><th class="num">Band</th><th class="num">Per $1</th><th class="num">t</th><th class="num">Bets</th></tr></thead>
      <tbody>{''.join(calib) or "<tr><td colspan='5' class='mute'>Waiting for the first sport.</td></tr>"}</tbody>
    </table></div>
  </section>

  <section>
    <h2>How it works</h2>
    <p>For every settled game in the last 60 days the bot replays Kalshi's minute-by-minute prices. It decides on one minute's price and buys the next minute at the worst ask, so there are no lucky fills, then pays Kalshi's fee. Next up after this: same-game parlays, where the winner, spread and total of one game are linked and might be mispriced as a combo.</p>
    <p class="mute">Full numbers: research/sports_study in the repository.</p>
  </section>
</main>
"""
    OUT.write_text(page)
    print(f"wrote {OUT} ({n_done} sports done)")


if __name__ == "__main__":
    main()
