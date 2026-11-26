"""The parlay runner's money path with a fake Kalshi client: price check, accepted side, refusing dear quotes."""
import math

import pytest

from tennis import parlay


class FakeClient:
    def __init__(self, no_bid):
        self.no_bid, self.sent, self.pos = no_bid, [], 0.0

    def _send(self, method, path, body=None, params=None):
        self.sent.append((method, path, body))
        if path.startswith("/multivariate_event_collections/"):
            return {"market_ticker": "COMBO-1", "event_ticker": "COMBO"}
        if path == "/communications/rfqs":
            return {"id": "rfq-1"}
        if path.endswith("/accept"):
            self.pos = 1.0
            return {}
        return {}

    def get(self, path, params=None):
        assert path == "/communications/quotes" and params["rfq_user_filter"] == "self"
        return {"quotes": [{"id": "q1", "status": "open", "yes_bid_dollars": "0.70", "no_bid_dollars": str(self.no_bid)}]}

    def positions(self, ticker):
        return [{"ticker": ticker, "position_fp": str(self.pos)}] if self.pos else []

    def fills(self, ticker):
        return [{"fee_cost": "0.01"}]


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    monkeypatch.setattr(parlay, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(parlay.notify, "post", lambda *a, **k: None)
    monkeypatch.setattr(parlay.time, "sleep", lambda s: None)
    monkeypatch.setattr(parlay.tapi, "orderbook_top", lambda tk: {"yes_ask": 0.93})


LEGS = [{"ticker": f"KXATPCHALLENGERMATCH-X{i}-A", "event": f"KXATPCHALLENGERMATCH-X{i}", "start": 0, "player": f"P{i}"}
        for i in range(3)]


def test_buys_yes_by_accepting_the_no_side_when_no_worse_than_the_legs():
    fair = math.prod(0.93 + parlay.fee(0.93) for _ in range(3))
    c = FakeClient(no_bid=round(1 - fair + 0.02, 4))                 # YES at 1 - no_bid, comfortably under the legs
    rec = parlay.buy_combo(c, [dict(x) for x in LEGS], log=lambda *a: None)
    assert rec and rec["contracts"] == 1.0
    acc = [s for s in c.sent if s[1].endswith("/accept")]
    assert acc and acc[0][2] == {"accepted_side": "no"}
    rfq = [s for s in c.sent if s[1] == "/communications/rfqs"][0][2]
    assert float(rfq["contracts_fp"]) * fair <= parlay.STAKE + 1e-9    # sized to the stake
    assert ("DELETE", "/communications/rfqs/rfq-1", None) in c.sent


def test_refuses_a_quote_dearer_than_the_legs():
    fair = math.prod(0.93 + parlay.fee(0.93) for _ in range(3))
    c = FakeClient(no_bid=round(1 - fair - 0.01, 4))
    assert parlay.buy_combo(c, [dict(x) for x in LEGS], log=lambda *a: None) is None
    assert not [s for s in c.sent if s[1].endswith("/accept")]


def test_drops_a_leg_whose_live_price_left_the_band(monkeypatch):
    monkeypatch.setattr(parlay.tapi, "orderbook_top", lambda tk: {"yes_ask": 0.80})
    legs = [dict(x) for x in LEGS]
    c = FakeClient(no_bid=0.3)
    assert parlay.buy_combo(c, legs, log=lambda *a: None) is None
    assert legs[0].get("dead") and not c.sent
