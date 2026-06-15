from __future__ import annotations

"""
Trade journal + memory — the agent's persistent diary and self-review.

The "hidden lesson" from the routines video: files are the system's memory and
discipline. Every cycle appends a human-readable entry to journal/journal.md so
you (and the system) have a readable history of what it did and why. A weekly
review grades performance against the S&P.

    python -m tradelab.main journal     # show recent entries
    python -m tradelab.main review      # run + print this week's self-review
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

JOURNAL_DIR = Path("journal")
JOURNAL_FILE = JOURNAL_DIR / "journal.md"
REVIEW_FILE = JOURNAL_DIR / "weekly_review.md"


def _ensure_dir() -> None:
    JOURNAL_DIR.mkdir(exist_ok=True)


def log_cycle(actions: dict) -> None:
    """Append one cycle's activity to the journal as readable markdown."""
    _ensure_dir()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"\n## {ts}"]
    lines.append(
        f"- Equity ${actions.get('equity', 0):,.2f}  "
        f"(daily {actions.get('daily_pct', 0):+.2f}%, "
        f"challenge {actions.get('challenge_pct', 0):+.2f}%, "
        f"drawdown {actions.get('drawdown_pct', 0):+.2f}%)"
    )
    lines.append(
        f"- {actions.get('n_positions', 0)} positions, "
        f"{actions.get('deployed_pct', 0):.0f}% deployed"
    )
    if actions.get("bought"):
        lines.append(f"- 🟢 Bought: {', '.join(actions['bought'])}")
    if actions.get("closed"):
        lines.append(f"- 🔴 Closed: {', '.join(actions['closed'])}")
    if actions.get("trimmed"):
        lines.append(f"- ✂️  Trimmed: {', '.join(actions['trimmed'])}")
    if actions.get("partial_tp"):
        lines.append(f"- 🎯 Partial take-profit: {', '.join(actions['partial_tp'])}")
    if actions.get("trail_stop"):
        lines.append(f"- 🛑 Trailing stop closed: {', '.join(actions['trail_stop'])}")
    if actions.get("riding"):
        lines.append(f"- 🏇 Riding (banked, trailing): {', '.join(sorted(actions['riding']))}")
    if actions.get("note"):
        lines.append(f"- 📝 {actions['note']}")

    with JOURNAL_FILE.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def show_journal(n: int = 20) -> None:
    if not JOURNAL_FILE.exists():
        print("No journal yet. Run `tradelab now` to start logging.")
        return
    text = JOURNAL_FILE.read_text(encoding="utf-8")
    # show the last N '##' entries
    entries = text.split("\n## ")
    tail = entries[-n:] if len(entries) > n else entries
    print("\n# TradeLab Journal (recent)\n")
    print("\n## ".join(tail) if not tail[0].startswith("#") else tail[0] + "\n## ".join(tail[1:]))


def weekly_review(session, broker) -> str:
    """Compute this week's performance vs the S&P, grade it, persist + return."""
    from tradelab.db.models import EquitySnapshot, Trade
    from tradelab.config import BENCHMARK

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    week_ago = now - timedelta(days=7)

    snaps = (
        session.query(EquitySnapshot)
        .filter(EquitySnapshot.ts >= week_ago)
        .order_by(EquitySnapshot.ts)
        .all()
    )
    acct = broker.get_account()
    cur_equity = acct["equity"]
    start_equity = float(snaps[0].equity) if snaps else cur_equity
    week_ret = (cur_equity - start_equity) / start_equity * 100 if start_equity else 0.0

    # Benchmark return over the same window
    spy_ret = float("nan")
    try:
        import yfinance as yf
        spy = yf.download(BENCHMARK, period="7d", interval="1d",
                          auto_adjust=True, progress=False)["Close"].dropna()
        if len(spy) >= 2:
            spy_ret = (float(spy.iloc[-1]) / float(spy.iloc[0]) - 1) * 100
    except Exception:
        pass

    # Closed-trade stats this week
    closed = (
        session.query(Trade)
        .filter(Trade.is_open == False, Trade.exit_time >= week_ago)  # noqa: E712
        .all()
    )
    wins = [t for t in closed if (t.pnl_dollars or 0) > 0]
    win_rate = len(wins) / len(closed) * 100 if closed else 0.0
    best = max(closed, key=lambda t: t.pnl_dollars or 0, default=None)
    worst = min(closed, key=lambda t: t.pnl_dollars or 0, default=None)

    # Self-grade: beating the benchmark is the bar
    edge = week_ret - spy_ret if spy_ret == spy_ret else week_ret
    if edge >= 3:
        grade = "A"
    elif edge >= 1:
        grade = "B"
    elif edge >= -1:
        grade = "C"
    elif edge >= -3:
        grade = "D"
    else:
        grade = "F"

    ts = now.strftime("%Y-%m-%d")
    lines = [
        f"\n## Weekly Review — {ts}",
        f"- Grade: **{grade}**",
        f"- Account this week: {week_ret:+.2f}%",
        f"- {BENCHMARK} this week: {spy_ret:+.2f}%" if spy_ret == spy_ret else f"- {BENCHMARK}: n/a",
        f"- Edge vs benchmark: {edge:+.2f}%",
        f"- Closed trades: {len(closed)}  |  win rate {win_rate:.0f}%",
    ]
    if best:
        lines.append(f"- Best: {best.symbol} ${best.pnl_dollars or 0:+,.0f}")
    if worst:
        lines.append(f"- Worst: {worst.symbol} ${worst.pnl_dollars or 0:+,.0f}")

    text = "\n".join(lines)
    _ensure_dir()
    with REVIEW_FILE.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    return text
