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
