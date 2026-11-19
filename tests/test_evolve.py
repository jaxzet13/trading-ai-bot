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
    rows = [dict(_parent("fv_drift", "KXETH15M", {"x": i}, t=3 + i / 10), id=f"fv_drift:KXETH15M:{i}", key=str(i)) for i in range(6)]
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
