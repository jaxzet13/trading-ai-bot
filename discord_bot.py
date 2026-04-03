"""
BetLab AI — Discord Bot
=======================
Auto-posts AI sports picks to a #picks channel every morning and
supports slash commands for members to query picks on demand.

Setup:
  1. Copy .env.example to .env and fill in your values
  2. pip install -r requirements.txt
  3. python discord_bot.py

Discord Developer Portal requirements:
  - Server Members Intent must be enabled (Privileged Gateway Intents)
  - Bot permissions: Send Messages, Embed Links, Use Application Commands
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DISCORD_TOKEN    = os.environ["DISCORD_TOKEN"]
GUILD_ID         = int(os.environ["DISCORD_GUILD_ID"])
PICKS_CHANNEL_ID = int(os.environ["PICKS_CHANNEL_ID"])
PREMIUM_ROLE_ID  = int(os.environ["PREMIUM_ROLE_ID"])
SCHEDULE_HOUR    = int(os.environ.get("PICKS_SCHEDULE_HOUR",   "9"))
SCHEDULE_MINUTE  = int(os.environ.get("PICKS_SCHEDULE_MINUTE", "0"))
SCHEDULE_TZ      = os.environ.get("PICKS_TIMEZONE", "America/New_York")
FREE_LIMIT       = int(os.environ.get("FREE_DAILY_PICK_LIMIT", "1"))
DRY_RUN          = os.environ.get("BOT_DRY_RUN", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Local imports (after dotenv so DB_PATH env var is loaded)
# ---------------------------------------------------------------------------

from src.sports_picks import get_todays_picks, get_pick_for_sport, SUPPORTED_SPORTS
from src.picks_db import (
    init_db,
    save_pick,
    get_todays_picks as db_get_todays_picks,
    get_todays_record,
    get_weekly_record,
    mark_pick_posted,
    count_user_requests_today,
    log_user_request,
)
from src.embeds import (
    build_pick_embed,
    build_record_embed,
    build_schedule_embed,
    build_locked_embed,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("betlab-bot")

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.guilds  = True   # resolve channels / roles
intents.members = True   # inspect member roles for premium check

bot = commands.Bot(command_prefix="!", intents=intents)
guild_obj = discord.Object(id=GUILD_ID)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_has_premium(member: discord.Member) -> bool:
    """True if the member holds the premium role."""
    return any(role.id == PREMIUM_ROLE_ID for role in member.roles)


# ---------------------------------------------------------------------------
# Scheduled: morning picks drop
# ---------------------------------------------------------------------------

async def post_daily_picks() -> None:
    """
    Fires every morning at SCHEDULE_HOUR:SCHEDULE_MINUTE in SCHEDULE_TZ.
    Generates picks for all supported sports, saves to DB, posts to #picks.
    """
    log.info("Running daily picks job...")

    channel = bot.get_channel(PICKS_CHANNEL_ID)
    if channel is None:
        log.error("Cannot find picks channel id=%s — skipping daily post", PICKS_CHANNEL_ID)
        return

    picks = await asyncio.to_thread(get_todays_picks)
    log.info("Generated %d picks", len(picks))

    # Header announcement
    header = discord.Embed(
        title="🔔 BetLab AI — Morning Picks Drop",
        description=(
            f"Good morning! Here are today's AI picks across **{len(picks)} games**.\n\n"
            "Premium members see everything. Free members get **1 pick/day** via `/pick [sport]`."
        ),
        color=0x5865F2,
        timestamp=datetime.now(tz=timezone.utc),
    ).set_footer(text="betlabai.app — AI-powered sports intelligence")

    if DRY_RUN:
        log.info("[DRY RUN] Would post header embed to channel %s", PICKS_CHANNEL_ID)
    else:
        await channel.send(embed=header)

    for pick in picks:
        pick_id = await asyncio.to_thread(
            save_pick,
            pick.sport, pick.home_team, pick.away_team, pick.pick_type,
            pick.recommendation, pick.confidence, pick.odds,
            pick.game_time.isoformat(), pick.analysis_text,
        )
        embed = build_pick_embed(pick, is_premium=True)

        if DRY_RUN:
            log.info(
                "[DRY RUN] Would post %s pick: %s (id=%s)",
                pick.sport, pick.recommendation, pick_id,
            )
        else:
            msg = await channel.send(embed=embed)
            await asyncio.to_thread(mark_pick_posted, pick_id, str(msg.id))
            log.info("Posted %s pick id=%s msg=%s", pick.sport, pick_id, msg.id)


# ---------------------------------------------------------------------------
# Bot events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready() -> None:
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id)

    # Sync slash commands to the guild (instant, unlike global sync which takes ~1hr)
    await bot.tree.sync(guild=guild_obj)
    log.info("Slash commands synced to guild %s", GUILD_ID)

    # Init DB
    await asyncio.to_thread(init_db)
    log.info("Database ready")

    # Start scheduler
    scheduler = AsyncIOScheduler(timezone=SCHEDULE_TZ)
    scheduler.add_job(
        post_daily_picks,
        CronTrigger(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE, timezone=SCHEDULE_TZ),
        id="daily_picks",
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        "Scheduler started — daily picks at %02d:%02d %s",
        SCHEDULE_HOUR, SCHEDULE_MINUTE, SCHEDULE_TZ,
    )


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

@bot.tree.command(
    name="pick",
    description="Get the latest AI pick for a sport",
    guild=guild_obj,
)
@app_commands.describe(sport="Sport to get a pick for")
@app_commands.choices(sport=[
    app_commands.Choice(name=s, value=s) for s in SUPPORTED_SPORTS
])
async def slash_pick(interaction: discord.Interaction, sport: str) -> None:
    await interaction.response.defer()

    member = interaction.guild.get_member(interaction.user.id)
    if member is None:
        await interaction.followup.send("Could not resolve your server membership. Please try again.", ephemeral=True)
        return

    is_premium = _user_has_premium(member)

    # Rate-limit free users
    if not is_premium:
        request_count = await asyncio.to_thread(count_user_requests_today, str(interaction.user.id))
        if request_count >= FREE_LIMIT:
            await interaction.followup.send(
                embed=build_locked_embed(sport, FREE_LIMIT), ephemeral=True
            )
            return

    try:
        pick = await asyncio.to_thread(get_pick_for_sport, sport)
    except ValueError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return

    pick_id = await asyncio.to_thread(
        save_pick,
        pick.sport, pick.home_team, pick.away_team, pick.pick_type,
        pick.recommendation, pick.confidence, pick.odds,
        pick.game_time.isoformat(), pick.analysis_text,
    )

    if not is_premium:
        await asyncio.to_thread(log_user_request, str(interaction.user.id), pick_id)

    embed = build_pick_embed(pick, is_premium=is_premium)
    await interaction.followup.send(embed=embed)


@bot.tree.command(
    name="record",
    description="Show today's and this week's win-loss record",
    guild=guild_obj,
)
async def slash_record(interaction: discord.Interaction) -> None:
    await interaction.response.defer()

    today  = await asyncio.to_thread(get_todays_record)
    weekly = await asyncio.to_thread(get_weekly_record)

    await interaction.followup.send(
        embeds=[
            build_record_embed(today,  "Today's"),
            build_record_embed(weekly, "This Week's"),
        ]
    )


@bot.tree.command(
    name="schedule",
    description="Show today's picks and game times",
    guild=guild_obj,
)
async def slash_schedule(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    picks = await asyncio.to_thread(db_get_todays_picks)
    await interaction.followup.send(embed=build_schedule_embed(picks))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if DRY_RUN:
        log.info("DRY RUN mode enabled — picks will be logged but not posted to Discord")
    bot.run(DISCORD_TOKEN, log_handler=None)
