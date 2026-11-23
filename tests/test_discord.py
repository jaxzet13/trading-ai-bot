"""Discord feed: reads the runner's log only, posts bets and results once each, never re-posts after a restart."""
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
       "close_ts": 86400 * 5 + 900, "balance_crypto": 30.0},
      {"event": "fill", "ticker": "T1", "series": "KXSOL15M", "side": "no", "n": 3.0, "avg_price": 0.28, "cost": 0.84, "fees": 0.02},
      {"event": "settle", "ticker": "T1", "series": "KXSOL15M", "pnl_kalshi": -0.86, "ts": 86400 * 5 + 950}]


def test_first_run_starts_at_the_end_and_posts_only_new_trades(tmp_path, monkeypatch):
    log = _setup(tmp_path, monkeypatch, EV[:1])
    sent = []
    D.run(once=True, post=lambda ch, t: sent.append((ch, t)) or True, log=lambda m: None)
    assert sent == []                                   # the old settle is history: no flood on first start
    with open(log, "a") as f:
        f.write("".join(json.dumps(e) + "\n" for e in EV[1:]))
    feed = D.run(once=True, post=lambda ch, t: sent.append((ch, t)) or True, log=lambda m: None)
    texts = [t for _, t in sent]
    assert len(texts) == 3 and all(ch == "123" for ch, _ in sent)
    assert "started" in texts[0]
    assert "BET** SOL **NO** 3 @ 0.28 = $0.86" in texts[1] and "fv_jump:KXSOL15M:2" in texts[1]
    assert "LOSS** SOL -0.86" in texts[2] and "all 2 bets +0.14" in texts[2]   # totals include the old bet
    assert abs(feed.total - 0.14) < 1e-9
    sent.clear()
    D.run(once=True, post=lambda ch, t: sent.append((ch, t)) or True, log=lambda m: None)
    assert sent == []                                   # restart: nothing posted twice


def test_failed_post_is_retried_next_time(tmp_path, monkeypatch):
    log = _setup(tmp_path, monkeypatch, [])
    D.STATE.write_text(json.dumps({"offset": 0}))
    log.write_text("".join(json.dumps(e) + "\n" for e in EV[2:]))
    D.run(once=True, post=lambda ch, t: False, log=lambda m: None)
    sent = []
    D.run(once=True, post=lambda ch, t: sent.append(t) or True, log=lambda m: None)
    assert len(sent) == 2 and "BET" in sent[0] and "LOSS" in sent[1]
