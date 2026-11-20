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
    assert len(E.parents(rows)) == E.PER_IDEA


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


def test_parents_fixed_top_and_varied_rest():
    rows = [dict(_parent("fv_drift", f"C{i}", {"x": i}, t=5 - i / 50), id=f"fv_drift:C{i}:1", key=str(i)) for i in range(150)]
    a, b = E.parents(rows, seed=1), E.parents(rows, seed=2)
    assert len(a) == len(b) == E.N_PARENTS
    assert [r["id"] for r in a[:15]] == [r["id"] for r in b[:15]] == [f"fv_drift:C{i}:1" for i in range(15)]
    assert {r["id"] for r in a} != {r["id"] for r in b}


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
