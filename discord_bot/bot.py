"""
Discord Referral Bot
- Tracks invite counts per member
- DMs a unique 50% off Stripe promo code when a member hits 8 referrals
- Updates #referral-leaderboard channel on every join and on demand
"""

import os
import json
import logging
import asyncio
from pathlib import Path

import discord
from discord.ext import commands, tasks
import stripe
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
STRIPE_API_KEY = os.environ["STRIPE_API_KEY"]
STRIPE_COUPON_ID = os.environ["STRIPE_COUPON_ID"]        # pre-created 50% coupon in Stripe
LEADERBOARD_CHANNEL = os.environ.get("LEADERBOARD_CHANNEL", "referral-leaderboard")
REFERRAL_THRESHOLD = int(os.environ.get("REFERRAL_THRESHOLD", "8"))
DATA_FILE = Path(os.environ.get("DATA_FILE", "referral_data.json"))

stripe.api_key = STRIPE_API_KEY

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
    """Return a mapping of invite code -> current use count for a guild."""
    return {inv.code: inv.uses for inv in await guild.invites()}


async def get_leaderboard_channel(guild: discord.Guild) -> discord.TextChannel | None:
    return discord.utils.get(guild.text_channels, name=LEADERBOARD_CHANNEL)


def create_stripe_promo_code(member_id: int) -> str:
    """Create a unique single-use Stripe promo code tied to member_id."""
    promo = stripe.PromotionCode.create(
        coupon=STRIPE_COUPON_ID,
        max_redemptions=1,
        metadata={"discord_member_id": str(member_id)},
    )
    return promo.code


async def post_leaderboard(guild: discord.Guild, data: dict) -> None:
    channel = await get_leaderboard_channel(guild)
    if channel is None:
        log.warning("Leaderboard channel '%s' not found.", LEADERBOARD_CHANNEL)
        return

    counts: dict[str, int] = data.get("counts", {})
    if not counts:
        await channel.send("No referrals tracked yet.")
        return

    sorted_members = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    lines = ["**Referral Leaderboard**\n"]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for rank, (member_id, count) in enumerate(sorted_members, start=1):
        member = guild.get_member(int(member_id))
        name = member.display_name if member else f"User {member_id}"
        medal = medals.get(rank, f"`#{rank}`")
        reward_note = " ✅ rewarded" if member_id in data.get("rewarded", []) else ""
        lines.append(f"{medal} **{name}** — {count} referral(s){reward_note}")

    embed = discord.Embed(
        title="Referral Leaderboard",
        description="\n".join(lines[1:]),
        color=discord.Color.gold(),
    )
    embed.set_footer(text=f"Earn a 50% off code at {REFERRAL_THRESHOLD} referrals!")
    await channel.send(embed=embed)


# ── Events ────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id)
    for guild in bot.guilds:
        invite_cache[guild.id] = await build_invite_cache(guild)
        log.info("Cached %d invites for guild '%s'", len(invite_cache[guild.id]), guild.name)


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

    # Snapshot current invites, then compare with cache to find which code was used
    current_invites = await build_invite_cache(guild)
    old_invites = invite_cache.get(guild.id, {})

    inviter: discord.Member | None = None
    for code, uses in current_invites.items():
        old_uses = old_invites.get(code, 0)
        if uses > old_uses:
            # Find the guild member who owns this invite
            for inv in await guild.invites():
                if inv.code == code and inv.inviter:
                    inviter = guild.get_member(inv.inviter.id)
                    break
            break

    # Refresh cache
    invite_cache[guild.id] = current_invites

    if inviter is None or inviter.bot:
        return

    inviter_id = str(inviter.id)
    counts = data.setdefault("counts", {})
    counts[inviter_id] = counts.get(inviter_id, 0) + 1
    log.info("%s now has %d referral(s).", inviter, counts[inviter_id])

    # Check threshold
    if (
        counts[inviter_id] >= REFERRAL_THRESHOLD
        and inviter_id not in data.get("rewarded", [])
    ):
        await send_reward(inviter, data)

    save_data(data)
    await post_leaderboard(guild, data)


async def send_reward(member: discord.Member, data: dict) -> None:
    try:
        promo_code = create_stripe_promo_code(member.id)
    except stripe.StripeError as exc:
        log.error("Stripe error for %s: %s", member, exc)
        return

    data.setdefault("rewarded", []).append(str(member.id))

    try:
        await member.send(
            f"Hey {member.display_name}! You've hit **{REFERRAL_THRESHOLD} referrals** — "
            f"here's your exclusive **50% off** code:\n\n"
            f"```\n{promo_code}\n```\n"
            f"Thanks for spreading the word! 🎉"
        )
        log.info("Sent promo code to %s.", member)
    except discord.Forbidden:
        log.warning("Could not DM %s — they may have DMs disabled.", member)


# ── Commands ──────────────────────────────────────────────────────────────────

@bot.command(name="referrals")
async def referrals_cmd(ctx: commands.Context, member: discord.Member | None = None):
    """Check referral count for yourself or another member."""
    target = member or ctx.author
    data = load_data()
    count = data.get("counts", {}).get(str(target.id), 0)
    remaining = max(0, REFERRAL_THRESHOLD - count)
    msg = (
        f"**{target.display_name}** has **{count}** referral(s). "
        + (f"**{remaining}** more to earn a 50% off code!" if remaining > 0 else "Reward already earned! ✅")
    )
    await ctx.send(msg)


@bot.command(name="leaderboard")
@commands.has_permissions(manage_guild=True)
async def leaderboard_cmd(ctx: commands.Context):
    """Post the referral leaderboard (admin only)."""
    data = load_data()
    await post_leaderboard(ctx.guild, data)


@bot.command(name="reset_referrals")
@commands.has_permissions(administrator=True)
async def reset_cmd(ctx: commands.Context, member: discord.Member):
    """Reset a member's referral count (admin only)."""
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
