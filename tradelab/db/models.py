from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from tradelab.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy = Column(String(64), nullable=False)
    symbol = Column(String(16), nullable=False)

    entry_time = Column(DateTime, nullable=False)
    entry_price = Column(Float, nullable=False)
    signal_value = Column(Float, nullable=True)

    exit_time = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)

    position_size = Column(Float, nullable=False)   # shares
    notional = Column(Float, nullable=False)        # entry notional $

    pnl_dollars = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    fees_modeled = Column(Float, nullable=True)

    is_open = Column(Boolean, default=True, nullable=False)
    alpaca_order_id = Column(String(64), nullable=True)

    agent = Column(String(32), nullable=True)   # which persona placed this trade


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)
    equity = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    peak_equity = Column(Float, nullable=False)
    drawdown_pct = Column(Float, nullable=False)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)
    strategy = Column(String(64), nullable=False)
    symbol = Column(String(16), nullable=False)
    signal_value = Column(Float, nullable=False)
    action = Column(String(16), nullable=False)   # BUY / SELL / HOLD


class SystemState(Base):
    __tablename__ = "system_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False)
    value = Column(Text, nullable=False)


class AgentConfig(Base):
    """Live, dashboard-editable per-agent settings. Roster defaults in
    tradelab/agents.py are used until a row exists here, then this row
    wins — lets the user tune agents from the web UI with no code edit."""
    __tablename__ = "agent_configs"

    name = Column(String(32), primary_key=True)
    enabled = Column(Boolean, default=True, nullable=False)

    conviction_min = Column(Float, nullable=False)
    size_multiplier = Column(Float, nullable=False)
    max_positions = Column(Integer, nullable=False)
    allocation_pct = Column(Float, nullable=False)   # share of equity this agent can deploy

    allow_long = Column(Boolean, default=True, nullable=False)
    allow_short = Column(Boolean, default=True, nullable=False)
    trade_stocks = Column(Boolean, default=True, nullable=False)
    trade_crypto = Column(Boolean, default=True, nullable=False)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Engine / session factory
# ---------------------------------------------------------------------------

def get_engine(url: str = DATABASE_URL):
    return create_engine(url, pool_pre_ping=True)


def get_session_factory(engine=None) -> sessionmaker:
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine=None) -> None:
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
