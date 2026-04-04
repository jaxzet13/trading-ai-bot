"""
Discord Referral Bot
- Tracks invite counts per member
- DMs "HALFOFF" code when a member hits 8 referrals
- Updates #referral-leaderboard channel on every join
"""

import os
import json
import logging
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
LEADERBOARD_CHANNEL = os.environ.get("LEADERBOARD_CHANNEL", "referral-leaderboard")
REFERRAL_THRESHOLD = int(os.environ.get("REFERRAL_THRESHOLD", "8"))
PROMO_CODE = os.environ.get("PROMO_CODE", "HALFOFF")
DATA_FILE = Path(os.environ.get("DATA_FILE", "referral_data.json"))

# ── Persistent storage ────────────────────────────────────────────────────────

def load_data() -> dict:
    if DATA_FILE.exists():
        with DATA_FILE.open() as f:
            return json.load(f)
    return {"counts": {}, "rewarded": []}


def save_data(data: dict) -> None:
    with DATA_FILE.open("w") as f:
        json.dump(data, f, indent=2)


# ── Bot setup ─────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.members = True
intents.invites = True

bot = commands.Bot(command_prefix="!", intents=intents)

# guild_id -> {invite_code -> uses}
invite_cache: dict[int, dict[str, int]] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def build_invite_cache(guild: discord.Guild) -> dict[str, int]:
    return {inv.code: inv.uses for inv in await guild.invites()}


async def post_leaderboard(guild: discord.Guild, data: dict) -> None:
    channel = discord.utils.get(guild.text_channels, name=LEADERBOARD_CHANNEL)
    if channel is None:
        log.warning("Channel '#%s' not found.", LEADERBOARD_CHANNEL)
        return

    counts: dict[str, int] = data.get("counts", {})
    if not counts:
        await channel.send("No referrals tracked yet.")
        return

    sorted_members = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    lines = []
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for rank, (member_id, count) in enumerate(sorted_members, start=1):
        member = guild.get_member(int(member_id))
        name = member.display_name if member else f"User {member_id}"
        medal = medals.get(rank, f"`#{rank}`")
        rewarded = " ✅" if member_id in data.get("rewarded", []) else ""
        lines.append(f"{medal} **{name}** — {count} referral(s){rewarded}")

    embed = discord.Embed(
        title="Referral Leaderboard",
        description="\n".join(lines),
        color=discord.Color.gold(),
    )
    embed.set_footer(text=f"Reach {REFERRAL_THRESHOLD} referrals to earn a 50% off code!")
    await channel.send(embed=embed)


# ── Events ────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id)
    for guild in bot.guilds:
        invite_cache[guild.id] = await build_invite_cache(guild)
        log.info("Cached %d invites for '%s'", len(invite_cache[guild.id]), guild.name)


@bot.event
async def on_invite_create(invite: discord.Invite):
    if invite.guild:
        invite_cache.setdefault(invite.guild.id, {})[invite.code] = invite.uses or 0


@bot.event
async def on_invite_delete(invite: discord.Invite):
    if invite.guild:
        invite_cache.get(invite.guild.id, {}).pop(invite.code, None)


@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    data = load_data()

    current_invites = await build_invite_cache(guild)
    old_invites = invite_cache.get(guild.id, {})

    inviter: discord.Member | None = None
    for inv in await guild.invites():
        if current_invites.get(inv.code, 0) > old_invites.get(inv.code, 0):
            if inv.inviter:
                inviter = guild.get_member(inv.inviter.id)
            break

    invite_cache[guild.id] = current_invites

    if inviter is None or inviter.bot:
        return

    inviter_id = str(inviter.id)
    counts = data.setdefault("counts", {})
    counts[inviter_id] = counts.get(inviter_id, 0) + 1
    log.info("%s now has %d referral(s).", inviter, counts[inviter_id])

    if (
        counts[inviter_id] >= REFERRAL_THRESHOLD
        and inviter_id not in data.get("rewarded", [])
    ):
        try:
            await inviter.send(
                f"Hey {inviter.display_name}! You've referred **{REFERRAL_THRESHOLD} people** "
                f"to the server — here's your reward:\n\n"
                f"**`{PROMO_CODE}`** is your 50% off code for completing {REFERRAL_THRESHOLD} referrals!"
            )
            data.setdefault("rewarded", []).append(inviter_id)
            log.info("Sent promo code to %s.", inviter)
        except discord.Forbidden:
            log.warning("Could not DM %s — DMs may be disabled.", inviter)

    save_data(data)
    await post_leaderboard(guild, data)


# ── Commands ──────────────────────────────────────────────────────────────────

@bot.command(name="referrals")
async def referrals_cmd(ctx: commands.Context, member: discord.Member | None = None):
    """Check referral count for yourself or another member."""
    target = member or ctx.author
    data = load_data()
    count = data.get("counts", {}).get(str(target.id), 0)
    remaining = max(0, REFERRAL_THRESHOLD - count)
    if remaining > 0:
        msg = f"**{target.display_name}** has **{count}** referral(s). {remaining} more to earn a 50% off code!"
    else:
        msg = f"**{target.display_name}** has **{count}** referral(s). Reward already sent! ✅"
    await ctx.send(msg)


@bot.command(name="leaderboard")
@commands.has_permissions(manage_guild=True)
async def leaderboard_cmd(ctx: commands.Context):
    """Post the referral leaderboard (mods only)."""
    await post_leaderboard(ctx.guild, load_data())


@bot.command(name="reset_referrals")
@commands.has_permissions(administrator=True)
async def reset_cmd(ctx: commands.Context, member: discord.Member):
    """Reset a member's referral count (admins only)."""
    data = load_data()
    mid = str(member.id)
    data.get("counts", {}).pop(mid, None)
    if mid in data.get("rewarded", []):
        data["rewarded"].remove(mid)
    save_data(data)
    await ctx.send(f"Reset referral data for **{member.display_name}**.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
