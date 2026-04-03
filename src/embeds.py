"""
Discord embed builder for BetLab AI bot.
No bot or scheduler dependency — takes data, returns discord.Embed objects.
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord

from src.sports_picks import SportsPick

# Confidence range → embed color
_CONFIDENCE_COLORS = [
    (85, 100, 0x00FF88),  # bright green — Elite
    (70,  84, 0x2ECC71),  # green — Strong
    (60,  69, 0xF39C12),  # amber — Moderate
    (51,  59, 0xE67E22),  # orange — Lean
]


def _confidence_color(confidence: int) -> int:
    for low, high, color in _CONFIDENCE_COLORS:
        if low <= confidence <= high:
            return color
    return 0x95A5A6  # gray fallback


def _confidence_bar(confidence: int) -> str:
    """12-block progress bar, e.g. `██████████░░` 83%"""
    filled = round(confidence / 100 * 12)
    bar = "█" * filled + "░" * (12 - filled)
    return f"`{bar}` {confidence}%"


def build_pick_embed(pick: SportsPick, is_premium: bool = True) -> discord.Embed:
    """
    Rich pick embed. If is_premium=False the recommendation field is redacted
    and a soft upgrade prompt replaces it.
    """
    embed = discord.Embed(
        title=f"{pick.sport_emoji}  BetLab AI — {pick.sport} Pick",
        color=_confidence_color(pick.confidence),
        timestamp=datetime.now(tz=timezone.utc),
    )

    embed.add_field(
        name="📋 Matchup",
        value=f"**{pick.away_team}** @ **{pick.home_team}**",
        inline=True,
    )

    if is_premium:
        embed.add_field(
            name="🎯 Our Pick",
            value=f"**{pick.recommendation}**",
            inline=True,
        )
    else:
        embed.add_field(
            name="🎯 Our Pick",
            value="🔒 *Premium members only*\nUpgrade at [betlabai.app](https://betlabai.app)",
            inline=True,
        )

    embed.add_field(name="\u200b", value="\u200b", inline=False)  # spacer

    embed.add_field(
        name="📊 Confidence",
        value=_confidence_bar(pick.confidence),
        inline=True,
    )
    embed.add_field(
        name="💰 Odds",
        value=pick.odds,
        inline=True,
    )

    game_ts = int(pick.game_time.timestamp())
    embed.add_field(
        name="🕐 Game Time",
        value=f"<t:{game_ts}:F>",
        inline=True,
    )

    embed.add_field(
        name="Analysis",
        value=pick.analysis_text,
        inline=False,
    )

    embed.set_footer(
        text="betlabai.app  •  /record to see today's results  •  Gamble responsibly"
    )
    return embed


def build_record_embed(record: dict, period: str = "Today's") -> discord.Embed:
    """W/L record embed. record keys: wins, losses, pushes, pending."""
    wins    = record.get("wins",    0)
    losses  = record.get("losses",  0)
    pushes  = record.get("pushes",  0)
    pending = record.get("pending", 0)

    graded = wins + losses + pushes
    win_pct = f"{wins / graded * 100:.1f}%" if graded else "—"

    embed = discord.Embed(
        title=f"📈 BetLab AI — {period} Record",
        color=0x5865F2,
        timestamp=datetime.now(tz=timezone.utc),
    )
    embed.add_field(name="✅ Wins",    value=str(wins),    inline=True)
    embed.add_field(name="❌ Losses",  value=str(losses),  inline=True)
    embed.add_field(name="↩️ Pushes", value=str(pushes),  inline=True)
    embed.add_field(name="📊 Win %",   value=win_pct,      inline=True)
    embed.add_field(name="⏳ Pending", value=str(pending), inline=True)
    embed.set_footer(text="betlabai.app  •  Results updated as games complete")
    return embed


def build_schedule_embed(picks: list) -> discord.Embed:
    """Today's picks schedule. picks = list of dicts from picks_db.get_todays_picks()."""
    embed = discord.Embed(
        title="📅 BetLab AI — Today's Pick Schedule",
        color=0x5865F2,
        timestamp=datetime.now(tz=timezone.utc),
    )

    if not picks:
        embed.description = "No picks posted yet today. Check back at 9 AM ET!"
        embed.set_footer(text="betlabai.app")
        return embed

    for p in picks:
        outcome = p.get("outcome")
        if outcome == "WIN":
            status = "✅"
        elif outcome == "LOSS":
            status = "❌"
        elif outcome == "PUSH":
            status = "↩️"
        else:
            status = "⏳"

        try:
            game_ts = int(datetime.fromisoformat(p["game_time"]).timestamp())
            time_str = f"<t:{game_ts}:t>"
        except Exception:
            time_str = p.get("game_time", "TBD")

        posted = "✔" if p.get("posted_at") else "Pending"

        embed.add_field(
            name=f"{status} {p['sport']} — {p['away_team']} @ {p['home_team']}",
            value=f"Game: {time_str}  •  Posted: {posted}  •  Pick: **{p['recommendation']}**",
            inline=False,
        )

    embed.set_footer(text="betlabai.app")
    return embed


def build_locked_embed(sport: str, free_limit: int) -> discord.Embed:
    """Shown to free users who have exhausted their daily pick limit."""
    embed = discord.Embed(
        title="🔒 Daily Limit Reached",
        description=(
            f"Free members get **{free_limit} pick{'s' if free_limit != 1 else ''}/day**.\n\n"
            f"Upgrade to **BetLab Premium** to unlock:\n"
            f"• All daily picks across every sport\n"
            f"• Full AI confidence breakdowns\n"
            f"• Historical record & analytics\n\n"
            f"👉 [betlabai.app](https://betlabai.app)"
        ),
        color=0xED4245,
    )
    embed.set_footer(text="betlabai.app  •  Gamble responsibly")
    return embed
