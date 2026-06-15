from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tradelab")


def _get_strategy(name: str):
    from tradelab.strategies.momentum import MomentumStrategy
    from tradelab.strategies.mean_reversion import MeanReversionStrategy
    from tradelab.strategies.top_intraday import ATRImpulseBreakoutStrategy, CascadeEMAStrategy, CombinedIntradayStrategy

    strategies = {
        "momentum": MomentumStrategy(),
        "mean_reversion": MeanReversionStrategy(),
        "atr_breakout": ATRImpulseBreakoutStrategy(),       # CAGR +48%, Sharpe 1.51
        "cascade_ema": CascadeEMAStrategy(),
        "combined": CombinedIntradayStrategy(),
    }
    if name not in strategies:
        print(f"Unknown strategy '{name}'. Choose from: {list(strategies)}")
        sys.exit(1)
    return strategies[name]


def cmd_backtest(args) -> None:
    from tradelab.backtest.runner import run_backtest, run_benchmark, compare_with_benchmark

    output_dir = Path("backtest_output")
    strategies = (
        [_get_strategy(args.strategy)]
        if args.strategy != "all"
        else [
            _get_strategy("atr_breakout"),
            _get_strategy("mean_reversion"),
            _get_strategy("momentum"),
        ]
    )

    results = []
    for strat in strategies:
        print(f"\nRunning backtest for: {strat.name} ...")
        result = run_backtest(strat, output_dir=output_dir)
        result.print_report()
        results.append(result)

    compare_with_benchmark(results)


def cmd_now(args) -> None:
    """Run one trading cycle immediately — useful for testing or a manual trigger."""
    from tradelab.db.models import init_db, get_engine, get_session_factory
    from tradelab.runner import run_daily_cycle

    engine = get_engine()
    init_db(engine)
    SessionFactory = get_session_factory(engine)

    print("Running one trading cycle NOW...")
    with SessionFactory() as session:
        run_daily_cycle(session)
    print("Done.")


def cmd_run(args) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from tradelab.config import MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, TIMEZONE
    from tradelab.db.models import init_db, get_engine, get_session_factory

    engine = get_engine()
    init_db(engine)
    SessionFactory = get_session_factory(engine)

    def daily_job():
        from tradelab.runner import run_daily_cycle
        with SessionFactory() as session:
            run_daily_cycle(session)

    scheduler = BlockingScheduler(timezone=TIMEZONE)
    # Morning run: signals fresh at market open
    scheduler.add_job(
        daily_job,
        "cron",
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        day_of_week="mon-fri",
        id="morning",
    )
    # Midday run: rebalance / catch new entries that emerged since open
    scheduler.add_job(
        daily_job,
        "cron",
        hour=13,
        minute=0,
        day_of_week="mon-fri",
        id="midday",
    )
    logger.info(
        "Scheduler started — runs at %02d:%02d and 13:00 %s on weekdays",
        MARKET_OPEN_HOUR,
        MARKET_OPEN_MINUTE,
        TIMEZONE,
    )
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")


def cmd_dashboard(args) -> None:
    from tradelab.db.models import init_db, get_engine, get_session_factory
    from tradelab.dashboard import run_dashboard

    engine = get_engine()
    init_db(engine)
    SessionFactory = get_session_factory(engine)

    with SessionFactory() as session:
        run_dashboard(session)


def cmd_web(args) -> None:
    import subprocess
    from pathlib import Path

    app_path = Path(__file__).resolve().parent / "webapp.py"
    print("Starting TradeLab web dashboard — it will open in your browser...")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path),
         "--theme.base", "dark"],
        check=False,
    )


def cmd_brief(args) -> None:
    """Daily analyst briefing: price action + news + flags on your holdings."""
    from tradelab.db.models import init_db, get_engine, get_session_factory
    from tradelab.execution.broker import PaperBroker
    from tradelab.data.fetcher import fetch_bars
    from tradelab.analyst import build_briefing, print_briefing

    engine = get_engine()
    init_db(engine)

    broker = PaperBroker()
    positions = broker.get_positions()
    if not positions:
        print("No open positions to brief on. Run `tradelab now` first.")
        return
    symbols = [p["symbol"] for p in positions]
    print(f"Gathering briefing for {len(symbols)} holdings...")
    bars = fetch_bars(symbols, years=1)
    brief = build_briefing(broker, bars)
    print_briefing(brief)


def cmd_journal(args) -> None:
    """Show the recent trade journal — what the system did and why."""
    from tradelab.journal import show_journal
    show_journal()


def cmd_review(args) -> None:
    """Run this week's self-review: performance vs S&P, win rate, grade."""
    from tradelab.db.models import init_db, get_engine, get_session_factory
    from tradelab.execution.broker import PaperBroker
    from tradelab.journal import weekly_review

    engine = get_engine()
    init_db(engine)
    SessionFactory = get_session_factory(engine)
    broker = PaperBroker()
    with SessionFactory() as session:
        print(weekly_review(session, broker))


def cmd_leaps(args) -> None:
    """LEAPS options screener — analysis only, separate from the challenge."""
    from tradelab.options_lab import screen_leaps, print_leaps
    print("Screening long-dated calls (LEAPS) on high-conviction names...")
    rows = screen_leaps()
    print_leaps(rows)


def cmd_options(args) -> None:
    """Run the LIVE options/LEAPS cycle on Alpaca paper (separate experiment)."""
    from tradelab.execution.broker import PaperBroker
    from tradelab.options_lab import run_options_cycle, print_options_run
    print("Running LIVE options/LEAPS cycle on Alpaca paper...")
    broker = PaperBroker()
    summary = run_options_cycle(broker)
    print_options_run(summary)


def cmd_challenge(args) -> None:
    """Print prop-firm challenge progress vs all limits."""
    from tradelab.db.models import init_db, get_engine, get_session_factory, EquitySnapshot
    from tradelab.execution.broker import PaperBroker
    from tradelab.config import (
        PROFIT_TARGET_PCT, DRAWDOWN_HALT_PCT,
        DAILY_LOSS_LIMIT_PCT, SYMBOL_LOSS_LIMIT_PCT,
    )
    from datetime import datetime, timezone

    engine = get_engine()
    init_db(engine)
    SessionFactory = get_session_factory(engine)

    broker = PaperBroker()
    acct = broker.get_account()
    equity = acct["equity"]

    with SessionFactory() as session:
        first = session.query(EquitySnapshot).order_by(EquitySnapshot.ts).first()
        start_eq = float(first.equity) if first else equity

        today = datetime.now(timezone.utc).date()
        today_start_dt = datetime(today.year, today.month, today.day)
        today_row = (
            session.query(EquitySnapshot)
            .filter(EquitySnapshot.ts >= today_start_dt)
            .order_by(EquitySnapshot.ts)
            .first()
        )
        daily_start = float(today_row.equity) if today_row else equity

    challenge_pct = (equity - start_eq) / start_eq * 100
    daily_pct = (equity - daily_start) / daily_start * 100
    target_pct = PROFIT_TARGET_PCT * 100
    max_loss_pct = DRAWDOWN_HALT_PCT * 100
    daily_limit_pct = DAILY_LOSS_LIMIT_PCT * 100

    print(f"\n{'='*52}")
    print("  PROP FIRM CHALLENGE TRACKER")
    print(f"{'='*52}")
    print(f"  Starting equity : ${start_eq:>12,.2f}")
    print(f"  Current equity  : ${equity:>12,.2f}")
    print(f"{'─'*52}")
    pbar = min(challenge_pct / target_pct, 1.0)
    filled = int(pbar * 30)
    bar = "█" * filled + "░" * (30 - filled)
    status = "✓ TARGET HIT!" if challenge_pct >= target_pct else f"need +{target_pct - challenge_pct:.2f}% more"
    print(f"  Profit target   : [{bar}] {challenge_pct:+.2f}% / +{target_pct:.0f}%  {status}")
    print(f"  Daily P&L today : {daily_pct:+.2f}%  (limit: -{daily_limit_pct:.0f}%)")
    print(f"  Max loss used   : {(equity-start_eq)/start_eq*100:.2f}%  (limit: -{max_loss_pct:.1f}%)")
    print(f"{'='*52}\n")


def cmd_resume(args) -> None:
    from tradelab.db.models import init_db, get_engine, get_session_factory, SystemState

    engine = get_engine()
    init_db(engine)
    SessionFactory = get_session_factory(engine)

    with SessionFactory() as session:
        row = session.query(SystemState).filter_by(key="halted").first()
        if row:
            row.value = "false"
            session.commit()
            print("Trading resumed. Halt flag cleared.")
        else:
            print("System is not halted.")


def cmd_report(args) -> None:
    from tradelab.db.models import init_db, get_engine, get_session_factory, Trade
    from collections import defaultdict
    from datetime import datetime

    engine = get_engine()
    init_db(engine)
    SessionFactory = get_session_factory(engine)

    with SessionFactory() as session:
        trades = (
            session.query(Trade)
            .filter(Trade.is_open == False)
            .order_by(Trade.exit_time)
            .all()
        )

        if not trades:
            print("No closed trades found.")
            return

        monthly: dict[str, list] = defaultdict(list)
        for t in trades:
            key = t.exit_time.strftime("%Y-%m") if t.exit_time else "unknown"
            monthly[key].append(t)

        print(f"\n{'='*60}")
        print("  Monthly Trade Report")
        print(f"{'='*60}")
        for month, month_trades in sorted(monthly.items()):
            pnls = [t.pnl_dollars or 0.0 for t in month_trades]
            wins = sum(1 for p in pnls if p > 0)
            total = sum(pnls)
            print(
                f"\n  {month}  |  {len(month_trades)} trades  |  "
                f"{wins}/{len(month_trades)} wins  |  P&L: ${total:+,.2f}"
            )
            for t in month_trades:
                pnl_pct = t.pnl_pct or 0.0
                marker = "+" if pnl_pct >= 0 else "-"
                print(
                    f"    [{marker}] {t.symbol:<6} {t.strategy:<16} "
                    f"${t.pnl_dollars or 0:+8.2f}  ({pnl_pct:+.2f}%)"
                )
        print(f"\n{'='*60}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tradelab",
        description="TradeLab — paper trading system",
    )
    sub = parser.add_subparsers(dest="command")

    p_bt = sub.add_parser("backtest", help="Run backtest for a strategy")
    p_bt.add_argument(
        "strategy",
        nargs="?",
        default="all",
        choices=["momentum", "mean_reversion", "atr_breakout", "cascade_ema", "combined", "all"],
        help="Strategy to backtest (default: all)",
    )

    sub.add_parser("now", help="Run one trading cycle immediately (for testing / manual trigger)")
    sub.add_parser("brief", help="Daily analyst briefing: price action + news + flags on holdings")
    sub.add_parser("journal", help="Show the recent trade journal (what the system did)")
    sub.add_parser("review", help="Run this week's self-review vs the S&P, with a grade")
    sub.add_parser("leaps", help="LEAPS options screener (analysis only)")
    sub.add_parser("options", help="Run the LIVE options/LEAPS cycle on Alpaca paper")
    sub.add_parser("challenge", help="Show prop-firm challenge progress vs all limits")
    sub.add_parser("run", help="Start the daily scheduler (9:31 AM + 1:00 PM ET, weekdays)")
    sub.add_parser("dashboard", help="Launch the live terminal dashboard")
    sub.add_parser("web", help="Launch the visual web dashboard (browser)")
    sub.add_parser("resume", help="Clear a risk halt and resume trading")
    sub.add_parser("report", help="Print monthly trade summary")

    args = parser.parse_args()

    dispatch = {
        "now": cmd_now,
        "brief": cmd_brief,
        "journal": cmd_journal,
        "review": cmd_review,
        "leaps": cmd_leaps,
        "options": cmd_options,
        "challenge": cmd_challenge,
        "backtest": cmd_backtest,
        "run": cmd_run,
        "dashboard": cmd_dashboard,
        "web": cmd_web,
        "resume": cmd_resume,
        "report": cmd_report,
    }

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
