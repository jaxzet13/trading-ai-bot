from __future__ import annotations

"""
Agent roster — multiple trading "personas" sharing one real Alpaca paper
account, each running a different slice of the signal engine and competing
on a profit leaderboard.

There is only ONE real brokerage account. Each agent gets a notional
"bankroll" (a slice of total equity, set at rollout time) and every trade
it places is tagged with its name on the Trade row. The leaderboard ranks
agents by return % against their bankroll — see compute_leaderboard() in
intraday_runner.py.

Strategy keys match the `strategy` field returned by generate_5m_signals()
in strategies/intraday_5m.py: ema_cross, vwap_cross, momentum_3bar, engulfing.
"""

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from tradelab.db.models import AgentConfig

ALL_STRATEGIES = ("ema_cross", "vwap_cross", "momentum_3bar", "engulfing")


@dataclass(frozen=True)
class Agent:
    name: str
    emoji: str
    personality: str

    strategies: tuple[str, ...] = ALL_STRATEGIES
    trade_stocks: bool = True
    trade_crypto: bool = True
    allow_long: bool = True
    allow_short: bool = True

    conviction_min: float = 1.0
    size_multiplier: float = 1.0
    max_positions: int = 4
    allocation_pct: float = 0.18   # share of account equity this agent can deploy

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.name}"


ROSTER: list[Agent] = [
    Agent(
        name="Maverick",
        emoji="🔥",
        personality="Aggressive momentum chaser — takes every signal with decent volume, "
                     "fires fast and often, biggest size on the desk.",
        strategies=ALL_STRATEGIES,
        trade_stocks=True,
        trade_crypto=True,
        allow_long=True,
        allow_short=True,
        conviction_min=1.0,
        size_multiplier=1.3,
        max_positions=5,
        allocation_pct=0.22,
    ),
    Agent(
        name="The Professor",
        emoji="🎓",
        personality="Trend-following purist — only trusts EMA cross and VWAP cross "
                     "(the two trend/level patterns), skips the reversal plays, waits "
                     "for high conviction before committing.",
        strategies=("ema_cross", "vwap_cross"),
        trade_stocks=True,
        trade_crypto=True,
        allow_long=True,
        allow_short=True,
        conviction_min=1.4,
        size_multiplier=1.0,
        max_positions=3,
        allocation_pct=0.18,
    ),
    Agent(
        name="Ghost",
        emoji="🥷",
        personality="Crypto-only night owl — markets are closed half the day for stocks, "
                     "BTC never sleeps, so neither does Ghost. Long-only since Alpaca "
                     "paper can't short crypto anyway.",
        strategies=ALL_STRATEGIES,
        trade_stocks=False,
        trade_crypto=True,
        allow_long=True,
        allow_short=False,
        conviction_min=1.0,
        size_multiplier=1.1,
        max_positions=4,
        allocation_pct=0.18,
    ),
    Agent(
        name="The Shark",
        emoji="🦈",
        personality="Short specialist — stocks only, hunts death crosses and bearish "
                     "engulfing candles at overbought extremes. Doesn't bother going long.",
        strategies=("ema_cross", "engulfing", "momentum_3bar"),
        trade_stocks=True,
        trade_crypto=False,
        allow_long=False,
        allow_short=True,
        conviction_min=1.1,
        size_multiplier=1.1,
        max_positions=3,
        allocation_pct=0.16,
    ),
    Agent(
        name="Steady Eddie",
        emoji="🐢",
        personality="Conservative grinder — smallest size, highest conviction bar, "
                     "fewer trades, but rarely the one chasing a bad fill.",
        strategies=ALL_STRATEGIES,
        trade_stocks=True,
        trade_crypto=True,
        allow_long=True,
        allow_short=True,
        conviction_min=1.6,
        size_multiplier=0.7,
        max_positions=3,
        allocation_pct=0.14,
    ),
]

ROSTER_BY_NAME: dict[str, Agent] = {a.name: a for a in ROSTER}


def load_agents(session: Session) -> list[Agent]:
    """Roster defaults merged with any live overrides saved in AgentConfig
    (written by the dashboard). Disabled agents are dropped entirely."""
    overrides = {c.name: c for c in session.query(AgentConfig).all()}

    out: list[Agent] = []
    for base in ROSTER:
        cfg = overrides.get(base.name)
        if cfg is None:
            out.append(base)
            continue
        if not cfg.enabled:
            continue
        out.append(Agent(
            name=base.name,
            emoji=base.emoji,
            personality=base.personality,
            strategies=base.strategies,
            trade_stocks=cfg.trade_stocks,
            trade_crypto=cfg.trade_crypto,
            allow_long=cfg.allow_long,
            allow_short=cfg.allow_short,
            conviction_min=cfg.conviction_min,
            size_multiplier=cfg.size_multiplier,
            max_positions=cfg.max_positions,
            allocation_pct=cfg.allocation_pct,
        ))
    return out


def ensure_agent_configs(session: Session) -> None:
    """Seed AgentConfig with roster defaults for any agent missing a row,
    so the dashboard always has something to render/edit."""
    existing = {c.name for c in session.query(AgentConfig).all()}
    for a in ROSTER:
        if a.name in existing:
            continue
        session.add(AgentConfig(
            name=a.name,
            enabled=True,
            conviction_min=a.conviction_min,
            size_multiplier=a.size_multiplier,
            max_positions=a.max_positions,
            allocation_pct=a.allocation_pct,
            allow_long=a.allow_long,
            allow_short=a.allow_short,
            trade_stocks=a.trade_stocks,
            trade_crypto=a.trade_crypto,
        ))
    session.commit()
