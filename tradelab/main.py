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
    scheduler.add_job(
        daily_job,
        "cron",
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        day_of_week="mon-fri",
    )
    logger.info(
        "Scheduler started — daily job at %02d:%02d %s on weekdays",
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

    sub.add_parser("run", help="Start the daily scheduler")
    sub.add_parser("dashboard", help="Launch the live terminal dashboard")
    sub.add_parser("web", help="Launch the visual web dashboard (browser)")
    sub.add_parser("resume", help="Clear a risk halt and resume trading")
    sub.add_parser("report", help="Print monthly trade summary")

    args = parser.parse_args()

    dispatch = {
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
