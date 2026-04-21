"""Thin client for The Odds API (https://the-odds-api.com).

Only the endpoints we need:
  - GET /v4/sports                                  list in-season sports
  - GET /v4/sports/{sport}/odds                     book odds for game markets
  - GET /v4/sports/{sport}/events                   event ids (for props)
  - GET /v4/sports/{sport}/events/{id}/odds         per-event markets (props)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

BASE = "https://api.the-odds-api.com/v4"

GAME_MARKETS = "h2h,spreads,totals"

# Common player-prop markets. Availability varies by sport/book; the API returns
# only what exists so listing them all is safe.
PROP_MARKETS_BY_SPORT: Dict[str, str] = {
    "basketball_nba": ",".join([
        "player_points", "player_rebounds", "player_assists",
        "player_threes", "player_points_rebounds_assists",
    ]),
    "basketball_wnba": "player_points,player_rebounds,player_assists",
    "icehockey_nhl": "player_points,player_goals,player_assists,player_shots_on_goal",
    "baseball_mlb": ",".join([
        "batter_hits", "batter_home_runs", "batter_total_bases",
        "batter_rbis", "pitcher_strikeouts",
    ]),
    "americanfootball_nfl": ",".join([
        "player_pass_yds", "player_rush_yds", "player_reception_yds",
        "player_receptions", "player_pass_tds", "player_anytime_td",
    ]),
}


class OddsAPIError(RuntimeError):
    pass


@dataclass
class OddsAPI:
    api_key: Optional[str] = None
    regions: str = "us"
    odds_format: str = "american"
    timeout: int = 15

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv("ODDS_API_KEY")
        if not self.api_key:
            raise OddsAPIError(
                "Missing ODDS_API_KEY. Get a free key at https://the-odds-api.com "
                "and export ODDS_API_KEY=... before running."
            )

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = dict(params or {})
        params["apiKey"] = self.api_key
        url = f"{BASE}{path}"
        r = requests.get(url, params=params, timeout=self.timeout)
        if r.status_code != 200:
            raise OddsAPIError(f"{r.status_code} {r.reason} on {path}: {r.text[:200]}")
        return r.json()

    def sports(self, all_sports: bool = False) -> List[Dict[str, Any]]:
        params = {"all": "true"} if all_sports else None
        return self._get("/sports", params)

    def odds(self, sport_key: str, markets: str = GAME_MARKETS) -> List[Dict[str, Any]]:
        return self._get(
            f"/sports/{sport_key}/odds",
            {"regions": self.regions, "markets": markets, "oddsFormat": self.odds_format},
        )

    def events(self, sport_key: str) -> List[Dict[str, Any]]:
        return self._get(f"/sports/{sport_key}/events", {})

    def event_odds(
        self, sport_key: str, event_id: str, markets: str
    ) -> Dict[str, Any]:
        return self._get(
            f"/sports/{sport_key}/events/{event_id}/odds",
            {"regions": self.regions, "markets": markets, "oddsFormat": self.odds_format},
        )

    def prop_markets_for(self, sport_key: str) -> Optional[str]:
        return PROP_MARKETS_BY_SPORT.get(sport_key)
