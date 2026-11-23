"""Strategy evolution and rotation: children are valid and new, the rotation policy is scored walk-forward without
looking ahead, and it never acts unless it beat the current live set."""
import json

from kalshi15m import evolve as E
from kalshi15m import lab3
from kalshi15m import rotate as R


def _parent(fam, scope, params, gen=1, t=3.0, filled=40):
    return {"gen": gen, "id": f"{fam}:{scope}:1", "family": fam, "scope": scope, "params": params,
            "filled": filled, "pnl": 5.0, "t": t}


def test_breed_children_are_valid_and_new():
    p1 = _parent("fv_drift", "KXETH15M", {"start": 2, "end": 12, "edge": 0.2, "band": "25-75", "L": 15, "a": -0.25, "vm": 1.0})
    p2 = _parent("fv_drift", "KXNEAR15M", {"start": 4, "end": 10, "edge": 0.14, "band": "05-95", "L": 1, "a": -0.25, "vm": 1.0})
    p3 = _parent("fv_emp", "KXNEAR15M", {"start": 5, "end": 10, "edge": 0.12, "band": "05-95", "lb": 7, "vm": 1.1})
    seen = {E.key(p["family"], p["scope"], p["params"]) for p in (p1, p2, p3)}
    kids = E.breed([p1, p2, p3], seen, lab3.COINS, seed=1)
    assert kids
    keys = [E.key(k["family"], k["scope"], k["params"]) for k in kids]
    assert len(set(keys)) == len(keys) and not set(keys) & seen
    for k in kids:
        grid = lab3.FAMILIES[k["family"]]["grid"]
        assert set(k["params"]) == set(grid)
        assert k["params"]["band"] in lab3.BANDS and k["params"]["start"] + 3 <= k["params"]["end"]
        for kk, v in k["params"].items():           # off-grid only for plain thresholds
            if v not in grid[kk]:
                assert kk in E.CONT or kk in ("start", "end"), (kk, v)
        if k["family"] == "fv_emp":
            assert k["params"]["vm"] in grid["vm"] and k["params"]["lb"] in grid["lb"]


def test_parents_cap_per_idea():
    rows = [dict(_parent("fv_drift", "KXETH15M", {"x": i}, t=3 + i / 10, filled=40 + i), id=f"fv_drift:KXETH15M:{i}", key=str(i)) for i in range(6)]
    assert len(E.parents(rows, explore=0)) == E.PER_IDEA


def _ALL(days):
    """Synthetic batch: rule A wins every day, rule B loses every day, rule C (live) wins small."""
    mk = lambda i, sc: {"id": f"fv_drift:{sc}:{i}", "family": "fv_drift", "scope": sc, "params": {"i": i}}
    a, b, c = mk(1, "KXETH15M"), mk(2, "KXSOL15M"), mk(3, "KXNEAR15M")
    d0 = days[0]
    return [(1, d0 * 86400, a, {d: [1.0, 5, 0.5] for d in days}),
            (1, d0 * 86400, b, {d: [-1.0, 5, 0.5] for d in days}),
            (1, d0 * 86400, c, {d: [0.1, 5, 0.1] for d in days})]


def test_rotation_walk_uses_only_earlier_days():
    days = list(range(20000, 20020))
    ALL = _ALL(days)
    W = R.walk(ALL, ["fv_drift:KXNEAR15M:3"], {"fv_drift"})
    # rules need MIN_DAYS of history first, so the first test day is day 7 of the batch
    assert W["strength"]["days"] == len(days) - 7
    assert W["strength"]["per_day"] > W["current"]["per_day"] > 0
    # B (always losing) is never eligible: eligibility requires a profit on earlier days
    assert all(r["c"]["scope"] != "KXSOL15M" for r in R.eligible(ALL, days[-1], {"fv_drift"}))
    # no look-ahead: on the first test day the stats only cover the 7 days before it
    r = next(r for r in R.eligible(ALL, days[7], {"fv_drift"}) if r["c"]["scope"] == "KXETH15M")
    assert r["filled"] == 35 and abs(r["pnl"] - 7.0) < 1e-9


def test_fill_test_scores_only_the_add_on_rules():
    """Empty slots are filled only from coins the live set does not trade, scored on their own, walk-forward."""
    days = list(range(20000, 20020))
    scope = lambda i: i.split(":")[1]
    F = R.walk_fill(_ALL(days), ["fv_drift:KXNEAR15M:3"], {"fv_drift"}, scope)
    assert F["strength"]["days"] == len(days) - 7
    assert abs(F["strength"]["per_day"] - 1.0) < 1e-9          # only rule A (the live NEAR rule is not counted)
    # live set already on ETH: the only other candidate (SOL) always loses, so it is never eligible -> no add-on days
    F = R.walk_fill(_ALL(days), ["fv_drift:KXETH15M:1", "fv_drift:KXNEAR15M:3"], {"fv_drift"}, scope)
    assert F["strength"]["days"] == 0 and F["strength"]["per_day"] is None
    # no empty slot: nothing to test
    full = [f"fv_drift:X{i}:1" for i in range(R.MAX_RULES)]
    assert R.walk_fill(_ALL(days), full, {"fv_drift"}, scope)["strength"]["days"] == 0


def test_parents_follow_the_best_families():
    rows = []
    for i, (sc, per_day) in enumerate([("A", 1.0), ("B", 0.1), ("C", 0.5)]):    # family A best, then C, then B
        for j in range(5):
            r = dict(_parent("fv_drift", sc, {"x": j}, t=3 - j / 10, filled=40 + j), id=f"fv_drift:{sc}:{j}", key=f"{sc}{j}")
            r["pnl"], r["fwd_days"] = per_day * 10 + j / 100, 10
            rows.append(r)
    p = E.parents(rows, k=8, explore=2, seed=1)
    assert [r["scope"] for r in p[:6]] == ["A", "A", "A", "C", "C", "C"]       # 3 best members of the 2 best families
    assert len(p) == 8 and len({r["id"] for r in p}) == 8
    assert E.parents(rows, k=8, explore=2, seed=1)[:6] == p[:6]               # the family part does not depend on luck


def test_real_record_credits_the_rule_that_bet(tmp_path):
    log = tmp_path / "log.jsonl"
    ev = [{"event": "order_intent", "ticker": "A-1", "rule": "r1"}, {"event": "settle", "ticker": "A-1", "pnl": -0.5},
          {"event": "order_intent", "ticker": "B-1", "rule": "r2"}, {"event": "settle", "ticker": "B-1", "pnl": 0.4},
          {"event": "settle", "ticker": "C-1", "pnl": 9.0}]                     # no intent: credited to nobody
    log.write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    rec = R.real_record(log)
    assert rec == {"r1": [1, -0.5], "r2": [1, 0.4]}


def test_removed_rules_never_eligible():
    days = list(range(20000, 20020))
    ALL = _ALL(days)
    assert any(r["rid"] == "fv_drift:KXETH15M:1" for r in R.eligible(ALL, days[-1], {"fv_drift"}, gone=set()))
    assert not any(r["rid"] == "fv_drift:KXETH15M:1" for r in R.eligible(ALL, days[-1], {"fv_drift"}, gone={"fv_drift:KXETH15M:1"}))


def test_parents_skip_exact_duplicates():
    a = dict(_parent("fv_dyn", "KXZEC15M", {"x": 1}, t=3.5, filled=31), id="fv_dyn:KXZEC15M:18", key="a")
    b = dict(a, id="fv_dyn:KXZEC15M:19", params={"x": 2}, key="b")                 # identical forward record
    c = dict(_parent("fv_dyn", "KXZEC15M", {"x": 3}, t=3.0, filled=20), id="fv_dyn:KXZEC15M:8", key="c")
    assert [r["id"] for r in E.parents([a, b, c])] == ["fv_dyn:KXZEC15M:18", "fv_dyn:KXZEC15M:8"]


def test_near_copies_of_removed_rules_are_blocked():
    days = list(range(20000, 20020))
    ALL = _ALL(days)
    twin = {"id": "fv_drift:KXETH15M:7", "family": "fv_drift", "scope": "KXETH15M", "params": {"i": 7}}
    ALL.append((1, days[0] * 86400, twin, {d: [1.0 + (d % 3) * 0.01, 5, 0.5] for d in days}))
    for g, s, c, daily in ALL:                    # give the removed rule some day-to-day variation to correlate with
        if c["id"] == "fv_drift:KXETH15M:1":
            daily.update({d: [1.0 + (d % 3) * 0.01, 5, 0.5] for d in days})
    ids = {r["rid"] for r in R.eligible(ALL, days[-1], {"fv_drift"}, gone={"fv_drift:KXETH15M:1"})}
    assert "fv_drift:KXETH15M:7" not in ids and "fv_drift:KXNEAR15M:3" in ids


def test_guards_report_pause_and_brake(tmp_path, monkeypatch):
    """rotate guards reads the runner's log the way the runner applies its brakes."""
    log, cfg = tmp_path / "real_log.jsonl", tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"limits": {"rule_pause_last_n": 5, "rule_pause_loss_usd": 2.0, "drawdown_brake_usd": 7.0},
                               "golden_rules": [{"id": "A"}, {"id": "B"}]}))
    ev = []
    for i in range(5):                                  # A: 5 losing bets of $0.50 -> -2.50, paused
        ev += [{"event": "order_intent", "ticker": f"a{i}", "rule": "A", "balance_crypto": 30.0},
               {"event": "settle", "ticker": f"a{i}", "pnl": -0.5, "ts": 1}]
    ev += [{"event": "order_intent", "ticker": "b0", "rule": "B", "balance_crypto": 30.0},
           {"event": "settle", "ticker": "b0", "pnl": 1.0, "ts": 1}]
    log.write_text("\n".join(json.dumps(e) for e in ev))
    (tmp_path / "real_log_peak.json").write_text(json.dumps({"peak": 40.0}))
    monkeypatch.setattr(R, "REAL_LOG", log)
    monkeypatch.setattr(R, "CFG", cfg)
    g = R.guards(log=lambda m: None)
    assert g["rules"]["A"]["state"] == "PAUSED" and g["rules"]["B"]["state"] == "ok"
    assert g["brake"]["halving"] is True                # 30 < 40 - 7


def test_lab_sizing_buys_more_contracts_when_cheap(tmp_path, monkeypatch):
    """The runner stakes dollars: a $1 stake buys 4 contracts at 25c and 1 at 80c; the lab bets 1 contract each."""
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"limits": {"stake_usd": 1.0}, "golden_rules": [{"id": "A"}]}))
    lab = tmp_path / "lab"
    lab.mkdir()
    (lab / "fwd_live_bets.json").write_text(json.dumps({"rules": {"A": [
        {"filled": True, "limit": 0.25, "pnl": 0.75},      # cheap win: 4 contracts sized
        {"filled": True, "limit": 0.80, "pnl": -0.80},     # dear loss: 1 contract either way
        {"filled": False, "limit": 0.30, "pnl": 0.0}]}}))
    monkeypatch.setattr(R, "CFG", cfg)
    monkeypatch.setattr(R, "LABDIR", lab)
    monkeypatch.setattr(R, "REAL_LOG", tmp_path / "none.jsonl")
    out = R.lab_sizing(log=lambda m: None)["A"]
    assert out["bets"] == 2 and abs(out["pnl_1c"] - (-0.05)) < 1e-9 and abs(out["pnl_sized"] - 2.2) < 1e-9
