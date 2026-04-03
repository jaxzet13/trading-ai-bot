"""
Sports pick engine for BetLab AI Discord bot.

Currently uses seeded mock data so picks are consistent within a calendar day.
Swap _generate_mock_pick() internals when real AI/odds API is ready —
the public interface (get_pick_for_sport, get_todays_picks, SportsPick) stays the same.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

SUPPORTED_SPORTS = ["NFL", "NBA", "MLB", "NHL", "NCAAF", "NCAAB"]

SPORT_EMOJIS = {
    "NFL":   "🏈",
    "NBA":   "🏀",
    "MLB":   "⚾",
    "NHL":   "🏒",
    "NCAAF": "🏈",
    "NCAAB": "🏀",
}

_TEAMS = {
    "NFL": [
        "Chiefs", "Bills", "Eagles", "49ers", "Cowboys", "Ravens",
        "Dolphins", "Lions", "Bengals", "Packers", "Rams", "Chargers",
        "Steelers", "Browns", "Bears", "Giants",
    ],
    "NBA": [
        "Lakers", "Celtics", "Nuggets", "Heat", "Bucks", "Warriors",
        "Suns", "Clippers", "Mavericks", "76ers", "Nets", "Raptors",
        "Thunder", "Pelicans", "Timberwolves", "Kings",
    ],
    "MLB": [
        "Yankees", "Dodgers", "Braves", "Astros", "Mets", "Cubs",
        "Red Sox", "Cardinals", "Padres", "Blue Jays", "Giants", "Brewers",
        "Phillies", "Rays", "Guardians", "Tigers",
    ],
    "NHL": [
        "Oilers", "Bruins", "Avalanche", "Lightning", "Rangers", "Stars",
        "Panthers", "Maple Leafs", "Flames", "Canucks", "Capitals", "Kings",
        "Penguins", "Hurricanes", "Wild", "Jets",
    ],
    "NCAAF": [
        "Alabama", "Georgia", "Ohio State", "Michigan", "Texas", "Oklahoma",
        "Notre Dame", "Penn State", "Clemson", "LSU", "Florida State", "USC",
        "Oregon", "Tennessee", "Utah", "TCU",
    ],
    "NCAAB": [
        "Duke", "Kentucky", "Kansas", "UNC", "Gonzaga", "Houston",
        "Purdue", "Tennessee", "Arizona", "Baylor", "Villanova", "Indiana",
        "Michigan State", "UCLA", "Connecticut", "Florida",
    ],
}

_PICK_TYPES = ["SPREAD", "TOTAL", "MONEYLINE"]

_ANALYSIS_TEMPLATES = [
    "{team} has covered {pct}% of {pick_type} bets in their last {n} games.",
    "Model heavily favors {recommendation} — strong edge in {factor}.",
    "{team} is {advantage} in this matchup based on {n}-game trend data.",
    "Public money is on the other side, but our model disagrees — sharp value on {recommendation}.",
    "{team} trends {advantage} against the {line_type} when {condition}.",
    "Line movement and injury reports both point toward {recommendation} as the right side.",
    "AI model identifies a {pct}% historical edge on {pick_type} in this spot.",
]

_FACTORS = [
    "defensive efficiency", "pace of play", "recent form",
    "home/away splits", "weather conditions", "rest advantage",
    "matchup history", "turnover differential",
]

_CONDITIONS = [
    "playing at home", "coming off a rest day", "facing a divisional opponent",
    "as a road underdog", "in primetime games", "after a blowout loss",
]

_ADVANTAGES = ["strong", "favored", "well-positioned", "statistically ahead"]
_LINE_TYPES = ["spread", "total", "moneyline"]


@dataclass
class SportsPick:
    sport: str
    home_team: str
    away_team: str
    pick_type: str
    recommendation: str
    confidence: int
    odds: str
    game_time: datetime
    analysis_text: str
    sport_emoji: str


def _generate_mock_pick(sport: str) -> SportsPick:
    """
    Generates a deterministic mock pick for the given sport.
    Seeded by sport + calendar date so the same pick is returned all day.
    """
    seed = f"{sport}-{datetime.now(tz=timezone.utc).date().isoformat()}"
    rng = random.Random(seed)

    teams = _TEAMS[sport]
    home_team = rng.choice(teams)
    away_team = rng.choice([t for t in teams if t != home_team])

    pick_type = rng.choice(_PICK_TYPES)

    if pick_type == "SPREAD":
        favored = rng.choice([home_team, away_team])
        line = rng.choice([1.5, 2.5, 3.0, 3.5, 4.5, 5.5, 6.5, 7.0, 7.5, 10.5])
        recommendation = f"{favored} -{line}"
        odds = rng.choice(["-110", "-105", "-115"])
    elif pick_type == "TOTAL":
        if sport in ("NBA", "NCAAB"):
            total = rng.choice([210.5, 215.5, 218.5, 221.5, 224.5, 227.5, 230.5])
        elif sport in ("NFL", "NCAAF"):
            total = rng.choice([40.5, 43.5, 45.5, 47.5, 50.5, 52.5, 55.5])
        elif sport == "MLB":
            total = rng.choice([7.5, 8.0, 8.5, 9.0, 9.5])
        else:  # NHL
            total = rng.choice([5.5, 6.0, 6.5])
        direction = rng.choice(["OVER", "UNDER"])
        recommendation = f"{direction} {total}"
        odds = rng.choice(["-110", "-105", "-115"])
    else:  # MONEYLINE
        pick_team = rng.choice([home_team, away_team])
        recommendation = f"{pick_team} ML"
        odds = rng.choice(["-130", "-145", "-160", "+115", "+130", "+145"])

    confidence = rng.randint(56, 89)

    # Game time: random hour today between 1pm and 10pm ET
    today = datetime.now(tz=timezone.utc).replace(
        hour=rng.randint(17, 23), minute=rng.choice([0, 30]), second=0, microsecond=0
    )
    # Push to next day if it's already past
    if today < datetime.now(tz=timezone.utc):
        today = today + timedelta(days=1)

    template = rng.choice(_ANALYSIS_TEMPLATES)
    analysis = template.format(
        team=rng.choice([home_team, away_team]),
        recommendation=recommendation,
        pick_type=pick_type.lower(),
        line_type=rng.choice(_LINE_TYPES),
        factor=rng.choice(_FACTORS),
        condition=rng.choice(_CONDITIONS),
        advantage=rng.choice(_ADVANTAGES),
        pct=rng.randint(58, 74),
        n=rng.choice([5, 7, 8, 10]),
    )

    return SportsPick(
        sport=sport,
        home_team=home_team,
        away_team=away_team,
        pick_type=pick_type,
        recommendation=recommendation,
        confidence=confidence,
        odds=odds,
        game_time=today,
        analysis_text=analysis,
        sport_emoji=SPORT_EMOJIS[sport],
    )


def get_pick_for_sport(sport: str) -> Optional[SportsPick]:
    """
    Return the AI pick for the given sport.
    Raises ValueError if sport is not supported.
    """
    sport = sport.upper()
    if sport not in SUPPORTED_SPORTS:
        raise ValueError(f"Unsupported sport '{sport}'. Choose from: {', '.join(SUPPORTED_SPORTS)}")
    return _generate_mock_pick(sport)


def get_todays_picks(sports: list = None) -> list:
    """
    Return one pick per sport for all (or specified) supported sports.
    Used by the morning auto-post scheduler.
    """
    target = [s.upper() for s in sports] if sports else SUPPORTED_SPORTS
    return [_generate_mock_pick(s) for s in target if s in SUPPORTED_SPORTS]
