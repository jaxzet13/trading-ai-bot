from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def _sparkline(values: list[float], width: int = 30) -> str:
    if not values:
        return ""
    bars = "▁▂▃▄▅▆▇█"
    mn, mx = min(values), max(values)
    span = mx - mn if mx != mn else 1
    chars = [bars[int((v - mn) / span * (len(bars) - 1))] for v in values[-width:]]
    return "".join(chars)


def _color_pnl(val: float) -> Text:
    s = f"{val:+.2f}%"
    return Text(s, style="bold green" if val >= 0 else "bold red")


def build_dashboard(db_session, broker=None) -> Layout:
    from tradelab.db.models import EquitySnapshot, Trade, SystemState

    # --- pull data from DB ---
    snapshots = (
        db_session.query(EquitySnapshot)
        .order_by(EquitySnapshot.ts.desc())
        .limit(30)
        .all()
    )
    snapshots.reverse()

    latest = snapshots[-1] if snapshots else None
    equity = latest.equity if latest else 0.0
    cash = latest.cash if latest else 0.0
    peak = latest.peak_equity if latest else equity
    drawdown_pct = latest.drawdown_pct * 100 if latest else 0.0

    halted_row = (
        db_session.query(SystemState).filter_by(key="halted").first()
    )
    halted = halted_row is not None and halted_row.value == "true"

    first_snap = snapshots[0] if snapshots else None
    start_equity = first_snap.equity if first_snap else equity
    total_pnl_pct = ((equity - start_equity) / start_equity * 100) if start_equity else 0.0

    open_trades = (
        db_session.query(Trade).filter_by(is_open=True).all()
    )
    closed_trades = (
        db_session.query(Trade)
        .filter_by(is_open=False)
        .order_by(Trade.exit_time.desc())
        .limit(10)
        .all()
    )

    # ---- Panel 1: Account ----
    account_text = Text()
    if halted:
        account_text.append("  ⛔ HALTED — manual resume required  \n", style="bold white on red")
    account_text.append(f"Equity      : ${equity:,.2f}\n")
    account_text.append(f"Cash        : ${cash:,.2f}\n")
    account_text.append(f"Total P&L   : ")
    account_text.append(f"{total_pnl_pct:+.2f}%\n", style="green" if total_pnl_pct >= 0 else "red")
    account_text.append(f"Drawdown    : ")
    account_text.append(
        f"{drawdown_pct:.2f}%\n",
        style="red bold" if drawdown_pct <= -5 else "yellow" if drawdown_pct < 0 else "green",
    )
    account_panel = Panel(account_text, title="[bold cyan]Account[/]", border_style="cyan")

    # ---- Panel 2: Open Positions ----
    pos_table = Table(show_header=True, header_style="bold magenta", expand=True)
    pos_table.add_column("Symbol")
    pos_table.add_column("Strategy")
    pos_table.add_column("Entry $", justify="right")
    pos_table.add_column("Current $", justify="right")
    pos_table.add_column("Unreal P&L", justify="right")
    pos_table.add_column("Hold")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for t in open_trades:
        hold_hours = int((now - t.entry_time).total_seconds() / 3600) if t.entry_time else 0
        hold_str = f"{hold_hours}h" if hold_hours < 48 else f"{hold_hours//24}d"
        pnl = t.pnl_dollars or 0.0
        pnl_style = "green" if pnl >= 0 else "red"
        pos_table.add_row(
            t.symbol,
            t.strategy,
            f"${t.entry_price:.2f}",
            f"${t.exit_price or t.entry_price:.2f}",
            Text(f"${pnl:+.2f}", style=pnl_style),
            hold_str,
        )

    pos_panel = Panel(pos_table, title="[bold cyan]Open Positions[/]", border_style="cyan")

    # ---- Panel 3: Recent Trades ----
    trades_table = Table(show_header=True, header_style="bold magenta", expand=True)
    trades_table.add_column("Symbol")
    trades_table.add_column("Strategy")
    trades_table.add_column("P&L %", justify="right")
    trades_table.add_column("Result")

    for t in closed_trades:
        pnl_pct = t.pnl_pct or 0.0
        result_style = "green" if pnl_pct >= 0 else "red"
        result_text = "WIN" if pnl_pct >= 0 else "LOSS"
        trades_table.add_row(
            t.symbol,
            t.strategy,
            Text(f"{pnl_pct:+.2f}%", style=result_style),
            Text(result_text, style=f"bold {result_style}"),
        )

    trades_panel = Panel(trades_table, title="[bold cyan]Recent Trades (last 10)[/]", border_style="cyan")

    # ---- Panel 4: Strategy Scoreboard ----
    from sqlalchemy import func
    score_table = Table(show_header=True, header_style="bold magenta", expand=True)
    score_table.add_column("Strategy")
    score_table.add_column("Trades", justify="right")
    score_table.add_column("Win%", justify="right")
    score_table.add_column("Avg Win", justify="right")
    score_table.add_column("Avg Loss", justify="right")
    score_table.add_column("Prof.Factor", justify="right")

    strategies = db_session.query(Trade.strategy).distinct().all()
    for (strat,) in strategies:
        strat_trades = (
            db_session.query(Trade)
            .filter(Trade.strategy == strat, Trade.is_open == False)
            .all()
        )
        if not strat_trades:
            continue
        pnls = [t.pnl_pct or 0.0 for t in strat_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / len(pnls) * 100
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        pf = sum(wins) / abs(sum(losses)) if losses else float("inf")
        score_table.add_row(
            strat,
            str(len(pnls)),
            f"{win_rate:.1f}%",
            Text(f"{avg_win:+.2f}%", style="green"),
            Text(f"{avg_loss:+.2f}%", style="red"),
            f"{pf:.2f}",
        )

    score_panel = Panel(score_table, title="[bold cyan]Strategy Scoreboard[/]", border_style="cyan")

    # ---- Panel 5: Equity Sparkline ----
    eq_values = [s.equity for s in snapshots]
    spark = _sparkline(eq_values)
    spark_text = Text(f"\n  {spark}\n", style="bold yellow")
    spark_panel = Panel(spark_text, title="[bold cyan]Equity (last 30 snapshots)[/]", border_style="cyan")

    # ---- Panel 6: Paper vs Backtest ----
    # Load latest backtest results from DB if stored, else placeholder
    pb_text = Text()
    pb_text.append("  (Run `python main.py backtest <strategy>` to populate)\n", style="dim")
    pb_panel = Panel(pb_text, title="[bold cyan]Paper vs Backtest[/]", border_style="cyan")

    layout = Layout()
    layout.split_column(
        Layout(Columns([account_panel, spark_panel], equal=True), name="top", size=8),
        Layout(pos_panel, name="positions", size=10),
        Layout(Columns([trades_panel, score_panel], equal=True), name="middle"),
        Layout(pb_panel, name="bottom", size=5),
    )

    return layout


def run_dashboard(db_session, refresh_seconds: int = 30) -> None:
    console.print("[bold green]TradeLab Dashboard[/] — press Ctrl+C to exit\n")
    with Live(console=console, refresh_per_second=1, screen=True) as live:
        while True:
            try:
                live.update(build_dashboard(db_session))
                time.sleep(refresh_seconds)
            except KeyboardInterrupt:
                break
