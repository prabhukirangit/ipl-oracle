"""
GraphLoader — Seeds KuzuDB with IPL 2026 entities from JSON skill files.

Sources:
  - skills/ipl2026_venue_coords.json → Venue nodes
  - skills/home_away_profiles.json → Team nodes
  - services/squad_manager.py → Player nodes (seed squads)
  - Head-to-head seed data for top rivalry matchups
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).resolve().parents[4] / "skills"

# Team ID → full name mapping (for canonical IDs)
TEAM_ID_MAP: dict[str, str] = {
    "MI": "Mumbai Indians",
    "CSK": "Chennai Super Kings",
    "RCB": "Royal Challengers Bengaluru",
    "KKR": "Kolkata Knight Riders",
    "DC": "Delhi Capitals",
    "SRH": "Sunrisers Hyderabad",
    "RR": "Rajasthan Royals",
    "PBKS": "Punjab Kings",
    "GT": "Gujarat Titans",
    "LSG": "Lucknow Super Giants",
}

# Reverse: full name → short ID
TEAM_SHORT_MAP = {v: k for k, v in TEAM_ID_MAP.items()}

# Venue → avg first innings T20 score (historical IPL average)
VENUE_AVG_SCORES: dict[str, int] = {
    "Wankhede Stadium, Mumbai": 175,
    "Eden Gardens, Kolkata": 163,
    "M. Chinnaswamy Stadium, Bengaluru": 185,
    "MA Chidambaram Stadium, Chennai": 155,
    "Arun Jaitley Stadium, Delhi": 168,
    "Rajiv Gandhi International Stadium, Hyderabad": 172,
    "Sawai Mansingh Stadium, Jaipur": 162,
    "Punjab Cricket Association Stadium, Mohali": 165,
    "Maharashtra Cricket Association Stadium, Pune": 170,
    "JSCA International Stadium, Ranchi": 158,
    "Barsapara Cricket Stadium, Guwahati": 155,
    "Dr. YS Rajasekhara Reddy ACA-VDCA Cricket Stadium, Visakhapatnam": 160,
    "Narendra Modi Stadium, Ahmedabad": 170,
    "Ekana Cricket Stadium, Lucknow": 162,
}

# Seed head-to-head rivalry matchup data (batter → bowler)
RIVALRY_H2H_SEED: list[dict[str, Any]] = [
    # Virat Kohli vs Mohammed Siraj (RCB training partner insight)
    {"batter": "Virat Kohli", "bowler": "Mohammed Siraj", "balls": 48, "runs": 52, "wickets": 2, "dots": 18},
    # Rohit Sharma vs Jasprit Bumrah (MI partnership)
    {"batter": "Rohit Sharma", "bowler": "Jasprit Bumrah", "balls": 36, "runs": 41, "wickets": 1, "dots": 15},
    # MS Dhoni vs Rashid Khan (classic matchup)
    {"batter": "MS Dhoni", "bowler": "Rashid Khan", "balls": 24, "runs": 35, "wickets": 3, "dots": 6},
    # Suryakumar Yadav vs Yuzvendra Chahal
    {"batter": "Suryakumar Yadav", "bowler": "Yuzvendra Chahal", "balls": 52, "runs": 68, "wickets": 4, "dots": 14},
    # Hardik Pandya vs Trent Boult (MI teammates)
    {"batter": "Hardik Pandya", "bowler": "Trent Boult", "balls": 28, "runs": 42, "wickets": 2, "dots": 8},
    # KL Rahul vs Rashid Khan
    {"batter": "KL Rahul", "bowler": "Rashid Khan", "balls": 44, "runs": 38, "wickets": 5, "dots": 22},
    # Shubman Gill vs Mohammed Shami
    {"batter": "Shubman Gill", "bowler": "Mohammed Shami", "balls": 30, "runs": 28, "wickets": 1, "dots": 14},
    # Travis Head vs Bhuvneshwar Kumar
    {"batter": "Travis Head", "bowler": "Bhuvneshwar Kumar", "balls": 22, "runs": 38, "wickets": 1, "dots": 4},
]


def _slugify(name: str) -> str:
    """Convert name to a slug for use as ID."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _load_json(filename: str) -> dict:
    path = _SKILLS_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def seed_all(graph: Any) -> None:
    """
    Seed the KnowledgeGraph with all IPL 2026 entities.

    Args:
        graph: KnowledgeGraph instance (already schema-setup)
    """
    await _seed_venues(graph)
    await _seed_teams(graph)
    await _seed_players(graph)
    await _seed_head_to_head(graph)
    logger.info("GraphLoader: seed_all complete")


async def _seed_venues(graph: Any) -> None:
    """Create Venue nodes from ipl2026_venue_coords.json."""
    try:
        data = _load_json("ipl2026_venue_coords.json")
    except FileNotFoundError:
        logger.warning("ipl2026_venue_coords.json not found — skipping venue seed")
        return

    venues = data.get("venues", {})
    count = 0
    for venue_name, coords in venues.items():
        venue_id = _slugify(venue_name)
        capacity_data = _load_capacity(venue_name)
        avg_score = VENUE_AVG_SCORES.get(venue_name, 165)

        graph.upsert_venue(
            venue_id=venue_id,
            name=venue_name,
            city=coords.get("city", ""),
            capacity=capacity_data,
            avg_first_innings_score=avg_score,
        )
        count += 1

    logger.info("GraphLoader: seeded %d venues", count)


def _load_capacity(venue_name: str) -> int:
    """Load venue capacity from espncricinfo_ground_ids.json."""
    try:
        data = _load_json("espncricinfo_ground_ids.json")
        info = data.get("venues", {}).get(venue_name, {})
        return int(info.get("capacity", 40000))
    except Exception:
        return 40000


async def _seed_teams(graph: Any) -> None:
    """Create Team nodes from home_away_profiles.json."""
    try:
        data = _load_json("home_away_profiles.json")
    except FileNotFoundError:
        logger.warning("home_away_profiles.json not found — using hardcoded team list")
        data = {"team_venue_profiles": {}}

    profiles = data.get("team_venue_profiles", {})
    seeded_teams: set[str] = set()
    count = 0

    for profile_key, profile in profiles.items():
        team_short = profile.get("team", "")
        if not team_short or team_short in seeded_teams:
            continue

        full_name = TEAM_ID_MAP.get(team_short, team_short)
        venue_name = profile.get("venue", "")

        graph.upsert_team(
            team_id=team_short.lower(),
            name=full_name,
            home_venue=venue_name,
            home_city=_extract_city(venue_name),
        )
        seeded_teams.add(team_short)
        count += 1

    # Ensure all 10 teams exist even if not in profiles
    for short, full in TEAM_ID_MAP.items():
        if short not in seeded_teams:
            graph.upsert_team(
                team_id=short.lower(),
                name=full,
                home_venue="",
                home_city="",
            )
            count += 1

    logger.info("GraphLoader: seeded %d teams", count)


async def _seed_players(graph: Any) -> None:
    """Create Player nodes from SQUAD_SEED and add PlaysFor edges."""
    from app.services.squad_manager import SQUAD_SEED

    count = 0
    for team_name, players in SQUAD_SEED.items():
        team_short = TEAM_SHORT_MAP.get(team_name, _slugify(team_name))
        team_id = team_short.lower()

        for player in players:
            player_name = player.get("name", "")
            if not player_name:
                continue

            player_id = _slugify(player_name)

            graph.upsert_player(
                player_id=player_id,
                name=player_name,
                team=team_name,
                role=player.get("role", "allrounder"),
                is_foreign=player.get("is_foreign", False),
                batting_style=player.get("batting_style", "right_hand"),
                bowling_style=player.get("bowling_style", "none"),
            )

            # PlaysFor edge
            graph.add_plays_for(player_id=player_id, team_id=team_id)
            count += 1

    logger.info("GraphLoader: seeded %d players", count)


async def _seed_head_to_head(graph: Any) -> None:
    """Add Matchup edges from RIVALRY_H2H_SEED."""
    count = 0
    for h2h in RIVALRY_H2H_SEED:
        batter_id = _slugify(h2h["batter"])
        bowler_id = _slugify(h2h["bowler"])

        graph.add_matchup(
            batter_id=batter_id,
            bowler_id=bowler_id,
            balls=h2h["balls"],
            runs=h2h["runs"],
            wickets=h2h["wickets"],
            dots=h2h["dots"],
        )
        count += 1

    logger.info("GraphLoader: seeded %d head-to-head matchups", count)


def _extract_city(venue_name: str) -> str:
    """Extract city name from venue string (last comma-separated part)."""
    if "," in venue_name:
        return venue_name.split(",")[-1].strip()
    return ""
