"""Tennis app: arb math is exact after Kalshi fees, the scanner counts an open arb once, sizes are respected."""
import json

from tennis import api, arb


def _row(t, ev, ya, yas, yb, ybs, ts=1.0):
    return {"ticker": t, "event": ev, "series": "KXATPMATCH", "yes_ask": ya, "yes_ask_size": yas,
            "yes_bid": yb, "yes_bid_size": ybs, "ts": ts}


def test_fee_matches_kalshi_formula():
    assert api.fee(0.5, 1) == 0.02 and api.fee(0.5, 100) == 1.75 and api.fee(0.9, 10) == 0.07


def test_yes_yes_arb_profit_after_fees():
    a, b = _row("A", "E", 0.40, 50, 0.38, 50), _row("B", "E", 0.55, 20, 0.53, 20)
    found = arb.check(a, b)
    y = [x for x in found if x["kind"] == "yes+yes"][0]
    n = y["n"]
    assert n <= 20                                              # limited by the thinner side
    assert abs(y["profit"] - (n * 0.05 - api.fee(0.40, n) - api.fee(0.55, n))) < 1e-9 and y["profit"] > 0


def test_no_arb_when_fees_eat_the_gap():
    a, b = _row("A", "E", 0.50, 100, 0.40, 100), _row("B", "E", 0.495, 100, 0.40, 100)   # 0.5% gap < fees
    assert arb.check(a, b) == []


def test_no_no_arb_uses_bids():
    a, b = _row("A", "E", 0.70, 10, 0.62, 30), _row("B", "E", 0.45, 10, 0.42, 30)          # NO costs 0.38 + 0.58
    x = [x for x in arb.check(a, b) if x["kind"] == "no+no"][0]
    assert abs(x["cost"] - 0.96) < 1e-9 and x["profit"] > 0


def test_scan_counts_an_open_arb_once(tmp_path):
    rows = [_row("A", "E", 0.40, 50, 0.3, 5, 1), _row("B", "E", 0.70, 50, 0.5, 5, 1),     # no arb
            _row("B", "E", 0.55, 50, 0.5, 5, 2),                                         # arb opens
            _row("A", "E", 0.41, 50, 0.3, 5, 3),                                         # still open
            _row("B", "E", 0.70, 50, 0.5, 5, 4),                                         # closes
            _row("B", "E", 0.50, 50, 0.5, 5, 5)]                                         # opens again
    p = tmp_path / "d.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    found = arb.scan([p], log=lambda m: None)
    assert [x["ts"] for x in found] == [2, 5]


def test_scan_never_pairs_a_new_price_with_an_old_one(tmp_path):
    """Both players move in the same snapshot: judging after each row would invent an arb (new A + old B)."""
    rows = [_row("A", "E", 0.83, 50, 0.82, 50, 1), _row("B", "E", 0.18, 50, 0.17, 50, 1),
            _row("A", "E", 0.79, 50, 0.78, 50, 2), _row("B", "E", 0.22, 50, 0.21, 50, 2)]   # A down, B up
    p = tmp_path / "d.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert arb.scan([p], log=lambda m: None) == []


def _mkt(rel, mid, askhi=None, bidlo=None, value=1.0, day=1):
    import numpy as np
    rel = np.array(rel, float); mid = np.array(mid, float)
    return {"ticker": "T", "event": "E", "series": "KXATPMATCH", "day": day, "start": 0, "value": value, "rel": rel, "mid": mid,
            "askhi": np.array(askhi if askhi is not None else mid + 0.01, float),
            "bidlo": np.array(bidlo if bidlo is not None else mid - 0.01, float)}


def test_band_bet_fills_next_minute_at_worst_ask_and_pays_settlement():
    from tennis import lab
    m = _mkt([-2, -1, 0, 1], [0.60, 0.62, 0.65, 0.70], askhi=[0.61, 0.63, 0.66, 0.74], value=1.0)
    s = {"fam": "band", "M": 0, "lo": 0.60, "hi": 0.70, "id": "x"}
    side, p, pnl, at = lab.bet(m, s)
    assert side == "yes" and p == 0.74                      # decided at minute 0, filled at minute 1's ask high
    assert abs(pnl - (1 - 0.74 - api.fee(0.74, 1))) < 1e-9


def test_no_bet_when_price_outside_band_or_no_next_minute():
    from tennis import lab
    s = {"fam": "band", "M": 0, "lo": 0.60, "hi": 0.70, "id": "x"}
    assert lab.bet(_mkt([-1, 0, 1], [0.5, 0.75, 0.8]), s) is None
    assert lab.bet(_mkt([-1, 0, 9], [0.5, 0.65, 0.8]), s) is None    # next bar 9 minutes later: no fill


def test_swing_momentum_buys_no_at_one_minus_bid_low():
    from tennis import lab
    m = _mkt([10, 15, 20, 21], [0.60, 0.58, 0.45, 0.44], bidlo=[0.59, 0.57, 0.44, 0.40], value=0.0)
    s = {"fam": "swing", "phase": "early", "w": 10, "d": 0.10, "dir": "down", "act": "mom", "id": "y"}
    side, p, pnl, at = lab.bet(m, s)
    assert side == "no" and abs(p - 0.60) < 1e-9 and at == 20     # 1 - next bar's bid low (0.40)
    assert abs(pnl - (1 - 0.60 - api.fee(0.60, 1))) < 1e-9


def test_walk_forward_never_ranks_on_the_judged_day():
    from tennis import lab
    # strategy A wins every day but loses big on the last; B loses early, wins the last day
    daily = {"A": {d: [1.0, 10, 1.0] for d in range(10)}, "B": {d: [-1.0, 10, 1.0] for d in range(10)}}
    daily["A"][9] = [-5.0, 10, 5.0]; daily["B"][9] = [5.0, 10, 5.0]
    w = lab.walk(daily, warmup=3, ks=(1,))
    # on day 9 the top-1 must still be A (ranked on days 0-8 only), so its day-9 loss is counted
    assert w["top"][1][0] < 0.1 and w["test_days"] == 7


def test_practice_runner_runs_the_frozen_batch_before_anything_passes(tmp_path, monkeypatch):
    """Before any strategy passes, the practice runner must still run the newest frozen batch (it ran none before)."""
    from tennis import paper
    (tmp_path / "forward").mkdir(); (tmp_path / "report").mkdir()
    batch = [{"id": f"band:m0:0.{i}0-0.{i}5", "fam": "band", "M": 0, "lo": i / 10, "hi": i / 10 + 0.05} for i in range(1, 9)]
    (tmp_path / "forward" / "batch_1.json").write_text(json.dumps({"frozen_at": 1, "strategies": batch}))
    (tmp_path / "report" / "forward.json").write_text(json.dumps([{"code": s["id"], "t": None, "bets": 0, "passed": False} for s in batch]))
    monkeypatch.setattr(paper, "DATA", tmp_path)
    s, passed = paper._strategies()
    assert not passed and [x["id"] for x in s] == [x["id"] for x in batch][:paper.FALLBACK_N]


def test_live_minute_close_is_the_price_at_the_boundary(tmp_path, monkeypatch):
    """A drop in the last seconds of a minute belongs to that minute's close, as in Kalshi's official bar."""
    import time as _t
    from tennis import paper
    books = tmp_path / "books"; books.mkdir()
    base = 1_000_000_020 - (1_000_000_020 % 60)          # a minute boundary
    snaps = [(base + 5, 0.24, 0.25), (base + 35, 0.19, 0.20),            # inside minute 0: last sample 0.195 mid
             (base + 62, 0.11, 0.12),                                    # 2 s after the boundary: the real close
             (base + 125, 0.11, 0.12), (base + 185, 0.11, 0.12)]
    (books / "d.jsonl").write_text("".join(json.dumps({"ticker": "T", "event": "E", "series": "S", "ts": ts,
                                                        "yes_bid": b, "yes_ask": a}) + "\n" for ts, b, a in snaps))
    monkeypatch.setattr(paper, "BOOKS", books)
    ms = paper.live_markets({"T": base}, base + 240)
    m = ms[0]
    assert abs(m["mid"][0] - 0.115) < 1e-9 and m["rel"][0] == 1.0     # minute 0 closes at the boundary price


def test_fast_scorer_matches_bet_exactly():
    """score_matrix (used to rank thousands of strategies) must give exactly the bets bet() gives (used live)."""
    import numpy as np
    from tennis import lab
    rng = np.random.default_rng(3)
    ms = []
    for k in range(40):
        rel = np.arange(-200, 200, 1.0)
        rel = rel[rng.random(len(rel)) > 0.1]                                  # gaps, like real bars
        mid = np.clip(0.5 + np.cumsum(rng.normal(0, 0.02, len(rel))), 0.03, 0.97)
        mid[rng.random(len(rel)) < 0.03] = np.nan
        ms.append({"ticker": f"T{k}", "event": f"E{k}", "series": ["KXATPMATCH", "KXWTAMATCH", "KXITFMATCH"][k % 3],
                   "day": 20000 + k % 5, "start": 0, "value": float(rng.random() < 0.5), "rel": rel, "mid": mid,
                   "askhi": mid + 0.01, "bidlo": mid - 0.01})
    strats = [s for s in lab.strategies() if s["fam"] == "swing" or s["M"] in (-60, 0, 30)]
    days, P, N, Q = lab.score_matrix(ms, strats, log=lambda m: None)
    for r, s in enumerate(strats):
        pnl, n = 0.0, 0
        for m in ms:
            b = lab.bet(m, s)
            if b:
                pnl += b[2]; n += 1
        assert n == N[r].sum() and abs(pnl - P[r].sum()) < 1e-9, s["id"]
