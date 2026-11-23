"""Discord feed: one card per pick, edited green/red when it settles; never re-posted after a restart."""
import json

from kalshi15m import discord_feed as D


def _setup(tmp_path, monkeypatch, events):
    log = tmp_path / "log.jsonl"
    log.write_text("".join(json.dumps(e) + "\n" for e in events))
    (tmp_path / "discord.json").write_text(json.dumps({"trades_channel_id": "123"}))
    monkeypatch.setattr(D, "LOG", log)
    monkeypatch.setattr(D, "CFG", tmp_path / "discord.json")
    monkeypatch.setattr(D, "STATE", tmp_path / "state.json")
    return log


EV = [{"event": "settle", "ticker": "OLD", "series": "KXNEAR15M", "pnl_kalshi": 1.0, "ts": 86400 * 5},
      {"event": "start", "series": "KXNEAR15M", "ts": 86400 * 5 + 10},
      {"event": "order_intent", "ticker": "T1", "series": "KXSOL15M", "rule": "fv_jump:KXSOL15M:2", "minute": 6,
       "close_ts": 86400 * 5 + 900},
      {"event": "fill", "ticker": "T1", "series": "KXSOL15M", "side": "no", "n": 3.0, "avg_price": 0.28, "cost": 0.84,
       "fees": 0.02, "ts": 86400 * 5 + 400},
      {"event": "settle", "ticker": "T1", "series": "KXSOL15M", "result": "yes", "pnl_kalshi": -0.86, "ts": 86400 * 5 + 950}]


class Fake:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, channel, embed, edit_id=None):
        if self.fail:
            return None
        self.calls.append((channel, embed, edit_id))
        return edit_id or f"m{len(self.calls)}"


def test_one_card_per_pick_then_edited_with_the_result(tmp_path, monkeypatch):
    log = _setup(tmp_path, monkeypatch, EV[:1])
    f = Fake()
    D.run(once=True, send=f, log=lambda m: None)
    assert f.calls == []                                # first start: old history is not posted
    with open(log, "a") as fh:
        fh.write("".join(json.dumps(e) + "\n" for e in EV[1:]))
    D.run(once=True, send=f, log=lambda m: None)
    assert len(f.calls) == 2                            # the pick's card, then its edit; no restart message
    ch, card, edit = f.calls[0]
    assert ch == "123" and edit is None and card["title"] == "SOL · NO" and card["color"] == D.BLUE
    vals = {x["name"]: x["value"] for x in card["fields"]}
    assert vals["Entry"] == "29¢" and vals["Contracts"] == "3" and vals["Cost"] == "$0.86" and vals["Pays if right"] == "$3.00"
    assert "Jump strategy" in card["description"]
    ch, card, edit = f.calls[1]
    assert edit == "m1" and card["color"] == D.RED and card["title"] == "SOL · NO · LOST −$0.86"
    f.calls.clear()
    D.run(once=True, send=f, log=lambda m: None)
    assert f.calls == []                                # restart: nothing posted twice


def test_failed_send_is_retried_next_time(tmp_path, monkeypatch):
    log = _setup(tmp_path, monkeypatch, [])
    D.STATE.write_text(json.dumps({"offset": 0}))
    log.write_text("".join(json.dumps(e) + "\n" for e in EV[2:]))
    D.run(once=True, send=Fake(fail=True), log=lambda m: None)
    f = Fake()
    D.run(once=True, send=f, log=lambda m: None)
    assert [c[2] for c in f.calls] == [None, "m1"] and f.calls[1][1]["color"] == D.RED
