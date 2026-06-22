"""
TradeLab web dashboard — launch with `python -m tradelab.main web`
(or directly: `streamlit run tradelab/webapp.py`).

Reads the same database the trading loop writes to. If the database is
empty (no trading has happened yet), demo data is shown so the layout
is visible.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from tradelab.agents import ROSTER, ensure_agent_configs
from tradelab.db.models import (
    AgentConfig,
    EquitySnapshot,
    SystemState,
    Trade,
    get_engine,
    get_session_factory,
    init_db,
)

st.set_page_config(
    page_title="TradeLab",
    page_icon="📈",
    layout="wide",
)

ACCENT_GREEN = "#00c980"
ACCENT_RED = "#ff4b6e"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_resource
def _session_factory():
    engine = get_engine()
    init_db(engine)
    return get_session_factory(engine)


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, bool, bool]:
    """Returns (equity_df, open_df, closed_df, halted, is_demo)."""
    Session = _session_factory()
    with Session() as s:
        snaps = s.query(EquitySnapshot).order_by(EquitySnapshot.ts).all()
        open_trades = s.query(Trade).filter_by(is_open=True).all()
        closed = (
            s.query(Trade)
            .filter_by(is_open=False)
            .order_by(Trade.exit_time.desc())
            .all()
        )
        halted_row = s.query(SystemState).filter_by(key="halted").first()
        halted = halted_row is not None and halted_row.value == "true"

    if not snaps and not closed:
        return *_demo_data(), halted, True

    equity_df = pd.DataFrame(
        [
            {"ts": x.ts, "equity": x.equity, "cash": x.cash,
             "drawdown_pct": x.drawdown_pct * 100}
            for x in snaps
        ]
    )
    open_df = pd.DataFrame(
        [
            {"Symbol": t.symbol, "Strategy": t.strategy,
             "Entry $": t.entry_price,
             "Current $": t.exit_price or t.entry_price,
             "Unrealized P&L $": t.pnl_dollars or 0.0,
             "Entered": t.entry_time}
            for t in open_trades
        ]
    )
    closed_df = pd.DataFrame(
        [
            {"Symbol": t.symbol, "Strategy": t.strategy,
             "Entry $": t.entry_price, "Exit $": t.exit_price,
             "P&L $": t.pnl_dollars or 0.0, "P&L %": t.pnl_pct or 0.0,
             "Exited": t.exit_time}
            for t in closed
        ]
    )
    return equity_df, open_df, closed_df, halted, False


def load_leaderboard() -> tuple[list[dict], bool]:
    """Returns (rows, is_demo). Talks to the live Alpaca paper account for
    current equity/positions — falls back to demo rows if that's not
    reachable (no keys configured, or no agents have traded yet)."""
    Session = _session_factory()
    try:
        from tradelab.execution.broker import PaperBroker
        from tradelab.intraday_runner import compute_leaderboard
        broker = PaperBroker()
        with Session() as s:
            ensure_agent_configs(s)
            rows = compute_leaderboard(s, broker)
        if rows:
            return rows, False
    except Exception:
        pass
    return _demo_leaderboard(), True


def _demo_leaderboard() -> list[dict]:
    import random
    random.seed(13)
    rows = []
    for a in ROSTER:
        ret = random.gauss(2.0, 4.0)
        baseline = round(80_000 * a.allocation_pct, 2)
        rows.append({
            "agent": a.name, "label": a.label, "personality": a.personality,
            "baseline": baseline,
            "bankroll_now": round(baseline * (1 + ret / 100), 2),
            "realized_pnl": round(baseline * ret / 100 * 0.7, 2),
            "unrealized_pnl": round(baseline * ret / 100 * 0.3, 2),
            "return_pct": round(ret, 2),
            "trades": random.randint(5, 40),
            "wins": 0,
            "win_rate": round(random.uniform(40, 65), 1),
            "open_positions": random.randint(0, 3),
        })
    rows.sort(key=lambda r: r["return_pct"], reverse=True)
    return rows


def _demo_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    import random

    random.seed(7)
    now = datetime.utcnow()
    rows, eq = [], 100_000.0
    for d in range(30, 0, -1):
        eq *= 1 + random.gauss(0.004, 0.012)
        rows.append({"ts": now - timedelta(days=d), "equity": eq,
                     "cash": eq * 0.1, "drawdown_pct": 0.0})
    equity_df = pd.DataFrame(rows)
    peak = equity_df["equity"].cummax()
    equity_df["drawdown_pct"] = (equity_df["equity"] - peak) / peak * 100

    open_df = pd.DataFrame([
        {"Symbol": "NVDA", "Strategy": "mean_reversion", "Entry $": 500.0,
         "Current $": 512.0, "Unrealized P&L $": 720.0,
         "Entered": now - timedelta(hours=30)},
        {"Symbol": "META", "Strategy": "momentum", "Entry $": 610.0,
         "Current $": 605.5, "Unrealized P&L $": -270.0,
         "Entered": now - timedelta(hours=6)},
    ])

    syms = ["AAPL", "NVDA", "TSLA", "META", "MSFT", "AMZN", "JPM", "XOM", "COST", "HD"]
    closed_rows = []
    for i, sym in enumerate(syms):
        pnl_pct = random.gauss(1.2, 2.5)
        closed_rows.append({
            "Symbol": sym,
            "Strategy": "mean_reversion" if i % 2 else "momentum",
            "Entry $": 150 + i * 10,
            "Exit $": (150 + i * 10) * (1 + pnl_pct / 100),
            "P&L $": 30_000 * pnl_pct / 100,
            "P&L %": pnl_pct,
            "Exited": now - timedelta(days=18 - i),
        })
    return equity_df, open_df, pd.DataFrame(closed_rows)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

@st.fragment(run_every="30s")
def render():
    equity_df, open_df, closed_df, halted, is_demo = load_data()

    for df, col in ((open_df, "Entered"), (closed_df, "Exited")):
        if len(df) and col in df.columns:
            df[col] = pd.to_datetime(df[col]).dt.strftime("%b %d, %H:%M")

    st.title("📈 TradeLab")
    if is_demo:
        st.info(
            "No live trading data yet — showing **demo data** so you can see the layout. "
            "Run `python -m tradelab.main run` with your Alpaca paper keys to go live.",
            icon="🧪",
        )
    if halted:
        st.error("⛔ TRADING HALTED — drawdown limit hit. Run `python -m tradelab.main resume` after review.")

    # ---- metric cards ----
    equity = equity_df["equity"].iloc[-1] if len(equity_df) else 0.0
    cash = equity_df["cash"].iloc[-1] if len(equity_df) else 0.0
    start_eq = equity_df["equity"].iloc[0] if len(equity_df) else equity
    day_delta = (
        equity - equity_df["equity"].iloc[-2]
        if len(equity_df) > 1 else 0.0
    )
    total_pnl_pct = (equity / start_eq - 1) * 100 if start_eq else 0.0
    dd = equity_df["drawdown_pct"].iloc[-1] if len(equity_df) else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Equity", f"${equity:,.0f}", f"{day_delta:+,.0f} today")
    c2.metric("Cash", f"${cash:,.0f}")
    c3.metric("Total P&L", f"{total_pnl_pct:+.2f}%")
    c4.metric("Drawdown", f"{dd:.2f}%", delta_color="inverse")
    c5.metric("Open positions", len(open_df))

    # ---- equity + drawdown charts ----
    col_eq, col_dd = st.columns([2, 1])
    with col_eq:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=equity_df["ts"], y=equity_df["equity"],
            fill="tozeroy", mode="lines",
            line=dict(color=ACCENT_GREEN, width=2),
            fillcolor="rgba(0,201,128,0.12)",
            name="Equity",
        ))
        fig.update_layout(
            title="Account Equity", height=320,
            margin=dict(l=10, r=10, t=40, b=10),
            yaxis=dict(rangemode="tozero" if len(equity_df) < 3 else "normal"),
        )
        fig.update_yaxes(tickprefix="$", separatethousands=True)
        st.plotly_chart(fig, width='stretch')
    with col_dd:
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=equity_df["ts"], y=equity_df["drawdown_pct"],
            fill="tozeroy", mode="lines",
            line=dict(color=ACCENT_RED, width=2),
            fillcolor="rgba(255,75,110,0.15)",
            name="Drawdown",
        ))
        fig_dd.add_hline(y=-10, line_dash="dash", line_color=ACCENT_RED,
                         annotation_text="halt level")
        fig_dd.update_layout(
            title="Drawdown from Peak (%)", height=320,
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig_dd, width='stretch')

    # ---- positions and trades ----
    col_pos, col_tr = st.columns(2)
    with col_pos:
        st.subheader("Open Positions")
        if len(open_df):
            st.dataframe(
                open_df.style.map(
                    lambda v: f"color: {ACCENT_GREEN}" if isinstance(v, (int, float)) and v >= 0
                    else f"color: {ACCENT_RED}",
                    subset=["Unrealized P&L $"],
                ).format({"Entry $": "${:.2f}", "Current $": "${:.2f}",
                          "Unrealized P&L $": "${:+,.2f}"}),
                width='stretch', hide_index=True,
            )
        else:
            st.caption("No open positions.")

    with col_tr:
        st.subheader("Recent Trades")
        if len(closed_df):
            st.dataframe(
                closed_df.head(10).style.map(
                    lambda v: f"color: {ACCENT_GREEN}" if isinstance(v, (int, float)) and v >= 0
                    else f"color: {ACCENT_RED}",
                    subset=["P&L $", "P&L %"],
                ).format({"Entry $": "${:.2f}", "Exit $": "${:.2f}",
                          "P&L $": "${:+,.2f}", "P&L %": "{:+.2f}%"}),
                width='stretch', hide_index=True,
            )
        else:
            st.caption("No closed trades yet.")

    # ---- strategy scoreboard ----
    if len(closed_df):
        st.subheader("Strategy Scoreboard")
        col_score, col_bar = st.columns([1, 1])
        score = (
            closed_df.groupby("Strategy")
            .agg(
                Trades=("P&L $", "size"),
                Wins=("P&L $", lambda x: (x > 0).sum()),
                Total_PnL=("P&L $", "sum"),
                Avg_PnL_pct=("P&L %", "mean"),
            )
            .reset_index()
        )
        score["Win rate"] = (score["Wins"] / score["Trades"] * 100).round(1).astype(str) + "%"
        with col_score:
            st.dataframe(
                score[["Strategy", "Trades", "Win rate", "Total_PnL", "Avg_PnL_pct"]]
                .rename(columns={"Total_PnL": "Total P&L $", "Avg_PnL_pct": "Avg P&L %"})
                .style.format({"Total P&L $": "${:+,.2f}", "Avg P&L %": "{:+.2f}%"}),
                width='stretch', hide_index=True,
            )
        with col_bar:
            pnl_by_trade = closed_df.head(20).iloc[::-1]
            fig_bar = px.bar(
                pnl_by_trade, x="Symbol", y="P&L $", color="P&L $",
                color_continuous_scale=[ACCENT_RED, "#888888", ACCENT_GREEN],
                title="P&L by Trade (last 20)",
            )
            fig_bar.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10),
                                  coloraxis_showscale=False)
            st.plotly_chart(fig_bar, width='stretch')

    # ---- agent leaderboard ----
    st.subheader("🏆 Agent Leaderboard")
    lb_rows, lb_demo = load_leaderboard()
    if lb_demo:
        st.caption(
            "Demo leaderboard — connect Alpaca paper keys and let `tradelab run` "
            "place a few trades to see agents compete for real."
        )
    if lb_rows:
        lb_df = pd.DataFrame(lb_rows)
        col_lb, col_lb_bar = st.columns([1, 1])
        with col_lb:
            st.dataframe(
                lb_df[["label", "return_pct", "bankroll_now", "baseline",
                       "trades", "win_rate", "open_positions"]]
                .rename(columns={
                    "label": "Agent", "return_pct": "Return %",
                    "bankroll_now": "Bankroll $", "baseline": "Start $",
                    "trades": "Trades", "win_rate": "Win %", "open_positions": "Open",
                })
                .style.map(
                    lambda v: f"color: {ACCENT_GREEN}" if isinstance(v, (int, float)) and v >= 0
                    else f"color: {ACCENT_RED}",
                    subset=["Return %"],
                ).format({"Return %": "{:+.2f}%", "Bankroll $": "${:,.0f}",
                          "Start $": "${:,.0f}", "Win %": "{:.1f}%"}),
                width='stretch', hide_index=True,
            )
        with col_lb_bar:
            fig_lb = px.bar(
                lb_df.sort_values("return_pct"), x="return_pct", y="label", orientation="h",
                color="return_pct", color_continuous_scale=[ACCENT_RED, "#888888", ACCENT_GREEN],
                title="Return % by Agent",
            )
            fig_lb.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10),
                                  coloraxis_showscale=False, xaxis_title="", yaxis_title="")
            st.plotly_chart(fig_lb, width='stretch')

    # ---- agent controls ----
    with st.expander("⚙️ Agent Controls — tune each persona live, no code needed"):
        Session = _session_factory()
        with Session() as s:
            ensure_agent_configs(s)
            configs = {c.name: c for c in s.query(AgentConfig).all()}

        for a in ROSTER:
            cfg = configs.get(a.name)
            if cfg is None:
                continue
            with st.form(key=f"agent_form_{a.name}"):
                st.markdown(f"**{a.label}** — {a.personality}")
                c1, c2, c3, c4 = st.columns(4)
                enabled = c1.toggle("Enabled", value=cfg.enabled, key=f"en_{a.name}")
                conviction_min = c2.slider("Min conviction", 0.5, 2.5, float(cfg.conviction_min), 0.05, key=f"cv_{a.name}")
                size_multiplier = c3.slider("Size multiplier", 0.3, 2.0, float(cfg.size_multiplier), 0.05, key=f"sz_{a.name}")
                max_positions = c4.slider("Max positions", 1, 10, int(cfg.max_positions), 1, key=f"mp_{a.name}")
                c5, c6, c7, c8 = st.columns(4)
                allocation_pct = c5.slider("Allocation %", 0.0, 0.5, float(cfg.allocation_pct), 0.01, key=f"al_{a.name}")
                allow_long = c6.toggle("Long", value=cfg.allow_long, key=f"lo_{a.name}")
                allow_short = c7.toggle("Short", value=cfg.allow_short, key=f"sh_{a.name}")
                trade_stocks = c8.toggle("Stocks", value=cfg.trade_stocks, key=f"st_{a.name}")
                trade_crypto = st.toggle("Crypto", value=cfg.trade_crypto, key=f"cr_{a.name}")
                if st.form_submit_button(f"Save {a.name}"):
                    with Session() as s2:
                        row = s2.query(AgentConfig).filter_by(name=a.name).first()
                        row.enabled = enabled
                        row.conviction_min = conviction_min
                        row.size_multiplier = size_multiplier
                        row.max_positions = max_positions
                        row.allocation_pct = allocation_pct
                        row.allow_long = allow_long
                        row.allow_short = allow_short
                        row.trade_stocks = trade_stocks
                        row.trade_crypto = trade_crypto
                        s2.commit()
                    st.success(f"Saved {a.name}.")
                    st.rerun()

    st.caption(
        f"Auto-refreshes every 30s · last update {datetime.now().strftime('%H:%M:%S')}"
        + (" · demo mode" if is_demo else "")
    )


render()
