"""
AgentFactory — Spawns all agents for a single match simulation.

Enriches PlayerAgent profiles with:
  - venue stats (via VenueStatsService, cached)
  - home/away modifier
  - news availability check
  - career stats stub (ESPNcricinfo scrape where available)
  - fatigue, foreign flag, auction hangover

Spawns: 2 CoachAgents, 1 StadiumAgent, 1 PitchAgent, 1 WeatherAgent,
        1 CrowdAgent, 2 UmpireAgents, up to 22 PlayerAgents (11 per team).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from app.agents.coach_agent import CoachAgent
from app.agents.crowd_agent import CrowdAgent
from app.agents.pitch_agent import PitchAgent
from app.agents.player_agent import PlayerAgent
from app.agents.stadium_agent import StadiumAgent
from app.agents.umpire_agent import UmpireAgent
from app.agents.weather_agent import WeatherAgent
from app.data.news_service import check_player_availability
from app.data.weather_service import get_weather_for_venue
from app.services.squad_manager import SQUAD_SEED, SquadManager
from app.personas.persona_loader import load_persona
from app.services.venue_stats_service import VenueStatsService

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).resolve().parents[4] / "skills"

# Home/away profiles cache
_home_away_profiles: dict[str, Any] = {}


def _load_home_away_profiles() -> dict[str, Any]:
    global _home_away_profiles
    if _home_away_profiles:
        return _home_away_profiles
    path = _SKILLS_DIR / "home_away_profiles.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _home_away_profiles = data
    except FileNotFoundError:
        logger.warning("home_away_profiles.json not found")
        _home_away_profiles = {}
    return _home_away_profiles


def _get_venue_home_profile(team_abbrev: str, venue_name: str) -> dict[str, Any]:
    """Return home/away profile for a team at a venue."""
    profiles = _load_home_away_profiles()
    team_venue_profiles = profiles.get("team_venue_profiles", {})

    # Try to find matching profile key (format: "{TEAM_SHORT}_{VenueSlug}")
    for key, profile in team_venue_profiles.items():
        if profile.get("team") == team_abbrev and profile.get("venue") == venue_name:
            return profile

    # Return neutral defaults
    return profiles.get("neutral_venue_defaults", {
        "batting_avg_boost": 0.0,
        "bowling_economy_improvement": 0.0,
        "home_win_rate_bat_first": 0.50,
        "home_win_rate_chasing": 0.50,
        "crowd_intensity": 0.50,
        "pitch_familiarity_home": 0.60,
        "pitch_familiarity_away": 0.60,
    })


# Canonical team abbreviation from full name
_TEAM_ABBREV: dict[str, str] = {
    "Mumbai Indians": "MI",
    "Chennai Super Kings": "CSK",
    "Royal Challengers Bengaluru": "RCB",
    "Kolkata Knight Riders": "KKR",
    "Delhi Capitals": "DC",
    "Sunrisers Hyderabad": "SRH",
    "Rajasthan Royals": "RR",
    "Punjab Kings": "PBKS",
    "Gujarat Titans": "GT",
    "Lucknow Super Giants": "LSG",
}

# Home team for each venue
_VENUE_HOME_TEAM: dict[str, str] = {
    "Wankhede Stadium, Mumbai": "MI",
    "Eden Gardens, Kolkata": "KKR",
    "M. Chinnaswamy Stadium, Bengaluru": "RCB",
    "MA Chidambaram Stadium, Chennai": "CSK",
    "Arun Jaitley Stadium, Delhi": "DC",
    "Rajiv Gandhi International Stadium, Hyderabad": "SRH",
    "Sawai Mansingh Stadium, Jaipur": "RR",
    "Punjab Cricket Association Stadium, Mohali": "PBKS",
    "Narendra Modi Stadium, Ahmedabad": "GT",
    "Ekana Cricket Stadium, Lucknow": "LSG",
}

# Stadium boundary configurations (short_boundary_m, long_boundary_m)
_STADIUM_BOUNDARIES: dict[str, tuple[int, int]] = {
    "Wankhede Stadium, Mumbai": (65, 73),
    "Eden Gardens, Kolkata": (68, 75),
    "M. Chinnaswamy Stadium, Bengaluru": (63, 68),
    "MA Chidambaram Stadium, Chennai": (68, 75),
    "Arun Jaitley Stadium, Delhi": (67, 73),
    "Rajiv Gandhi International Stadium, Hyderabad": (70, 78),
    "Sawai Mansingh Stadium, Jaipur": (65, 72),
    "Punjab Cricket Association Stadium, Mohali": (68, 75),
    "Narendra Modi Stadium, Ahmedabad": (72, 80),
    "Ekana Cricket Stadium, Lucknow": (68, 74),
}


class AgentFactory:
    """
    Factory that spawns all agents for a single match simulation.

    All agents for a given run share the same run_id but get isolated memory.
    Player profiles are enriched with real data before agent creation.
    """

    def __init__(self) -> None:
        self._venue_service = VenueStatsService.get_instance()

    async def spawn_all_agents(self, match_info: dict[str, Any]) -> dict[str, Any]:
        """
        Spawn all agents for a match.

        Args:
            match_info: Dict containing:
                - team1: str (full team name)
                - team2: str (full team name)
                - venue: str (full venue name)
                - run_id: str (simulation run ID)
                - match_id: str (optional, for live data)
                - is_night_match: bool (default True for IPL)
                - team1_xi: list[str] (optional confirmed XI)
                - team2_xi: list[str] (optional confirmed XI)

        Returns:
            Dict containing all spawned agents keyed by type:
                {
                    "team1_coach": CoachAgent,
                    "team2_coach": CoachAgent,
                    "stadium": StadiumAgent,
                    "pitch": PitchAgent,
                    "weather": WeatherAgent,
                    "crowd": CrowdAgent,
                    "umpire1": UmpireAgent,
                    "umpire2": UmpireAgent,
                    "team1_players": list[PlayerAgent],
                    "team2_players": list[PlayerAgent],
                }
        """
        team1 = match_info["team1"]
        team2 = match_info["team2"]
        venue = match_info["venue"]
        run_id = match_info["run_id"]
        is_night = match_info.get("is_night_match", True)

        team1_abbrev = _TEAM_ABBREV.get(team1, team1[:3].upper())
        team2_abbrev = _TEAM_ABBREV.get(team2, team2[:3].upper())
        home_team_abbrev = _VENUE_HOME_TEAM.get(venue, "")

        is_team1_home = (team1_abbrev == home_team_abbrev)
        is_team2_home = (team2_abbrev == home_team_abbrev)

        # ------------------------------------------------------------------
        # Weather
        # ------------------------------------------------------------------
        weather_data = await get_weather_for_venue(venue)
        weather_agent = WeatherAgent(
            venue_name=venue,
            weather_data=weather_data,
            run_id=run_id,
        )
        logger.info("AgentFactory: WeatherAgent spawned for %s (dew_risk=%s)", venue, weather_data.get("dew_risk"))

        # ------------------------------------------------------------------
        # Crowd
        # ------------------------------------------------------------------
        home_profile = _get_venue_home_profile(
            team1_abbrev if is_team1_home else team2_abbrev, venue
        )
        crowd_intensity = home_profile.get("crowd_intensity", 0.75)
        home_team_full = team1 if is_team1_home else (team2 if is_team2_home else team1)

        crowd_agent = CrowdAgent(
            home_team=home_team_full,
            venue_name=venue,
            crowd_intensity_base=crowd_intensity,
            run_id=run_id,
        )

        # ------------------------------------------------------------------
        # Stadium
        # ------------------------------------------------------------------
        short_b, long_b = _STADIUM_BOUNDARIES.get(venue, (68, 75))
        stadium_agent = StadiumAgent(
            venue_name=venue,
            short_boundary_m=short_b,
            long_boundary_m=long_b,
            run_id=run_id,
        )

        # ------------------------------------------------------------------
        # Pitch
        # ------------------------------------------------------------------
        pitch_agent = PitchAgent(
            venue_name=venue,
            run_id=run_id,
        )

        # ------------------------------------------------------------------
        # Umpires
        # ------------------------------------------------------------------
        umpire1 = UmpireAgent(
            umpire_name="On-Field Umpire 1",
            lbw_propensity=0.48,
            wide_threshold=0.52,
            no_ball_strictness=0.50,
            run_id=run_id,
        )
        umpire2 = UmpireAgent(
            umpire_name="On-Field Umpire 2",
            lbw_propensity=0.52,
            wide_threshold=0.50,
            no_ball_strictness=0.48,
            run_id=run_id,
        )

        # ------------------------------------------------------------------
        # Coaches
        # ------------------------------------------------------------------
        team1_coach = self._spawn_coach(team1, is_team1_home, run_id)
        team2_coach = self._spawn_coach(team2, is_team2_home, run_id)

        # ------------------------------------------------------------------
        # Players (batch fetch venue stats concurrently)
        # ------------------------------------------------------------------
        team1_players = await self._spawn_team_players(
            team_name=team1,
            team_abbrev=team1_abbrev,
            venue=venue,
            is_home=is_team1_home,
            run_id=run_id,
            confirmed_xi=match_info.get("team1_xi"),
            weather_data=weather_data,
        )
        team2_players = await self._spawn_team_players(
            team_name=team2,
            team_abbrev=team2_abbrev,
            venue=venue,
            is_home=is_team2_home,
            run_id=run_id,
            confirmed_xi=match_info.get("team2_xi"),
            weather_data=weather_data,
        )

        logger.info(
            "AgentFactory: spawn_all_agents complete — %d + %d players, venue=%s, run_id=%s",
            len(team1_players), len(team2_players), venue, run_id[:8],
        )

        return {
            "team1_coach": team1_coach,
            "team2_coach": team2_coach,
            "stadium": stadium_agent,
            "pitch": pitch_agent,
            "weather": weather_agent,
            "crowd": crowd_agent,
            "umpire1": umpire1,
            "umpire2": umpire2,
            "team1_players": team1_players,
            "team2_players": team2_players,
            "meta": {
                "team1": team1,
                "team2": team2,
                "venue": venue,
                "run_id": run_id,
                "is_night_match": is_night,
                "weather": weather_data,
                "home_team": home_team_full,
            },
        }

    def _spawn_coach(self, team: str, is_home: bool, run_id: str) -> CoachAgent:
        """Spawn a CoachAgent with team-specific profile."""
        # Coach profiles based on known IPL coaching tendencies
        COACH_STYLES: dict[str, dict[str, Any]] = {
            "Mumbai Indians": {"style": "data_driven", "ip_strategy": "death", "toss_pref": "field"},
            "Chennai Super Kings": {"style": "conservative", "ip_strategy": "middle_overs", "toss_pref": "venue_based"},
            "Royal Challengers Bengaluru": {"style": "aggressive", "ip_strategy": "powerplay", "toss_pref": "field"},
            "Kolkata Knight Riders": {"style": "data_driven", "ip_strategy": "middle_overs", "toss_pref": "field"},
            "Delhi Capitals": {"style": "aggressive", "ip_strategy": "reactive", "toss_pref": "bat"},
            "Sunrisers Hyderabad": {"style": "aggressive", "ip_strategy": "powerplay", "toss_pref": "field"},
            "Rajasthan Royals": {"style": "data_driven", "ip_strategy": "middle_overs", "toss_pref": "venue_based"},
            "Punjab Kings": {"style": "aggressive", "ip_strategy": "death", "toss_pref": "bat"},
            "Gujarat Titans": {"style": "conservative", "ip_strategy": "middle_overs", "toss_pref": "venue_based"},
            "Lucknow Super Giants": {"style": "balanced", "ip_strategy": "reactive", "toss_pref": "field"},
        }
        defaults = {"style": "balanced", "ip_strategy": "middle_overs", "toss_pref": "venue_based"}
        cfg = COACH_STYLES.get(team, defaults)

        return CoachAgent(
            team=team,
            coach_name=f"{team} Head Coach",
            tactical_style=cfg["style"],
            ip_strategy=cfg["ip_strategy"],
            toss_preference=cfg["toss_pref"],
            captain_defensive_tendency=0.35 if cfg["style"] == "conservative" else 0.25,
            run_id=run_id,
        )

    async def _spawn_team_players(
        self,
        team_name: str,
        team_abbrev: str,
        venue: str,
        is_home: bool,
        run_id: str,
        confirmed_xi: list[str] | None,
        weather_data: dict[str, Any],
    ) -> list[PlayerAgent]:
        """
        Spawn up to 11 PlayerAgents for a team, with full profile enrichment.
        """
        squad_data = SQUAD_SEED.get(team_name, [])
        if not squad_data:
            logger.warning("No squad seed data for team '%s'", team_name)
            return []

        # If confirmed XI provided, filter to those 11
        if confirmed_xi:
            xi_set = set(confirmed_xi)
            squad_data = [p for p in squad_data if p["name"] in xi_set]
            # Fill remaining slots if confirmed XI has names not in seed
            named_set = {p["name"] for p in squad_data}
            for name in confirmed_xi:
                if name not in named_set:
                    squad_data.append({"name": name, "role": "allrounder", "batting_style": "right_hand", "bowling_style": "none", "is_foreign": False})
        else:
            squad_data = squad_data[:11]

        # Fetch venue stats for all players concurrently (respects semaphore internally)
        venue_stats_tasks = [
            self._venue_service.get_player_venue_stats(p["name"], venue)
            for p in squad_data
        ]
        all_venue_stats = await asyncio.gather(*venue_stats_tasks, return_exceptions=True)

        # Fetch availability from news concurrently
        avail_tasks = [check_player_availability(p["name"]) for p in squad_data]
        all_availability = await asyncio.gather(*avail_tasks, return_exceptions=True)

        # Home/away profile for this team at this venue
        ha_profile = _get_venue_home_profile(team_abbrev, venue)
        pitch_familiarity = (
            ha_profile.get("pitch_familiarity_home", 0.75)
            if is_home
            else ha_profile.get("pitch_familiarity_away", 0.50)
        )
        batting_avg_boost = ha_profile.get("batting_avg_boost", 0.0) if is_home else 0.0
        bowling_eco_improv = ha_profile.get("bowling_economy_improvement", 0.0) if is_home else 0.0

        players: list[PlayerAgent] = []

        for i, player_data in enumerate(squad_data):
            venue_stats = all_venue_stats[i] if not isinstance(all_venue_stats[i], Exception) else {}
            availability = all_availability[i] if not isinstance(all_availability[i], Exception) else "available"

            if not isinstance(venue_stats, dict):
                venue_stats = {}

            player = self._build_player_agent(
                player_data=player_data,
                team_name=team_name,
                venue_stats=venue_stats,
                is_home=is_home,
                pitch_familiarity=pitch_familiarity,
                batting_avg_boost=batting_avg_boost,
                bowling_eco_improv=bowling_eco_improv,
                availability=str(availability),
                run_id=run_id,
            )
            players.append(player)

        logger.info("AgentFactory: spawned %d PlayerAgents for %s (home=%s)", len(players), team_name, is_home)
        return players

    def _build_player_agent(
        self,
        player_data: dict[str, Any],
        team_name: str,
        venue_stats: dict[str, Any],
        is_home: bool,
        pitch_familiarity: float,
        batting_avg_boost: float,
        bowling_eco_improv: float,
        availability: str,
        run_id: str,
    ) -> PlayerAgent:
        """
        Build a fully-enriched PlayerAgent from raw player data + venue context.

        Computes age and experience_years from birth_year/ipl_debut_year in seed data.
        Experience steers pressure_resilience, big_match_temperament, and fatigue.
        """
        name = player_data.get("name", "Unknown")
        role = player_data.get("role", "allrounder")
        batting_style = player_data.get("batting_style", "right_hand")
        bowling_style = player_data.get("bowling_style", "none")
        is_foreign = player_data.get("is_foreign", False)

        # Age & experience — steering factors for composure, resilience, decision quality
        current_year = 2026
        birth_year = player_data.get("birth_year")
        ipl_debut_year = player_data.get("ipl_debut_year")
        age = (current_year - birth_year) if birth_year else 28  # default prime age
        experience_years = (current_year - ipl_debut_year) if ipl_debut_year else 5

        # Career stats from seed (Week 2 baseline — scraped stats replace these in Week 3)
        career_stats = player_data.get("career_stats", {})
        batting_avg = float(career_stats.get("batting_avg", 28.0)) + (batting_avg_boost * 0.3 if is_home else 0.0)
        strike_rate = float(career_stats.get("strike_rate", 130.0))
        bowling_eco = max(6.0, float(career_stats.get("bowling_economy", 8.5)) - (bowling_eco_improv * 0.3 if is_home else 0.0))
        bowling_avg = float(career_stats.get("bowling_avg", 30.0))

        # Venue stats enrichment
        venue_affinity = float(venue_stats.get("venue_affinity", 0.5))
        venue_batting_avg = venue_stats.get("avg") or batting_avg
        venue_sr = venue_stats.get("sr") or strike_rate

        # Auction hangover penalty calculation
        auction_price = player_data.get("auction_price", 0)
        matches_played = player_data.get("matches_played_this_season", 0)
        auction_hangover_penalty = 0.0
        if auction_price >= 15_00_00_000:  # 15 crore
            auction_hangover_penalty = 0.15 * max(0.0, (20 - matches_played) / 20.0)

        # Role-based personality defaults, steered by experience
        aggression = _role_aggression(role)
        pressure_resilience = _role_resilience(role)
        death_spec = 0.70 if "death" in role or role == "bowler" else 0.50
        powerplay_spec = 0.70 if role in ("batsman", "wicketkeeper") else 0.50

        # Experience modifiers: veterans gain composure; youngsters are more volatile
        if experience_years >= 10:
            pressure_resilience = min(0.95, pressure_resilience + 0.10)
        elif experience_years >= 6:
            pressure_resilience = min(0.90, pressure_resilience + 0.05)
        elif experience_years <= 2:
            pressure_resilience = max(0.35, pressure_resilience - 0.10)
            aggression = min(0.80, aggression + 0.05)  # rookies tend to overplay

        # Age-based fatigue: older players (35+) tire faster
        age_fatigue_bump = max(0.0, (age - 34) * 0.03) if age > 34 else 0.0

        # Left-arm bowling style flag
        is_left_arm_bowler = "left_arm" in bowling_style.lower()

        profile = PlayerAgent.build_profile(
            name=name,
            team=team_name,
            role=role,
            batting_style=batting_style,
            bowling_style=bowling_style,
            is_foreign_player=is_foreign,
            career_batting_avg=batting_avg,
            career_strike_rate=strike_rate,
            career_bowling_economy=bowling_eco,
            career_bowling_avg=bowling_avg,
            venue_batting_avg=float(venue_batting_avg) if venue_batting_avg else None,
            venue_strike_rate=float(venue_sr) if venue_sr else None,
            aggression_index=aggression,
            pressure_resilience=pressure_resilience,
            venue_affinity=venue_affinity,
            big_match_temperament=min(0.95, 0.60 + experience_years * 0.02 + (0.05 if is_home else 0.0)),
            fatigue_level=min(0.80, player_data.get("fatigue_level", 0.20) + age_fatigue_bump),
            injury_risk=player_data.get("injury_risk", 0.10),
            powerplay_specialization=powerplay_spec,
            death_overs_specialization=death_spec,
            availability_status=availability,
            # Week 2 additions
            is_home_player=is_home,
            home_away_modifier=1.05 if is_home else 0.95,
            pitch_familiarity=pitch_familiarity,
            auction_price=auction_price,
            auction_hangover_penalty=auction_hangover_penalty,
            matches_played_this_season=matches_played,
            is_left_arm_bowler=is_left_arm_bowler,
            age=age,
            experience_years=experience_years,
        )

        # Load LLM persona (for PERSONA and HYBRID modes)
        persona = load_persona(name, profile)
        profile["persona"] = persona

        return PlayerAgent(profile=profile, run_id=run_id)


def _role_aggression(role: str) -> float:
    """Default aggression_index by role."""
    role_map = {
        "batsman": 0.65,
        "wicketkeeper": 0.60,
        "allrounder": 0.62,
        "bowler": 0.45,
    }
    return role_map.get(role, 0.60)


def _role_resilience(role: str) -> float:
    """Default pressure_resilience by role."""
    role_map = {
        "batsman": 0.70,
        "wicketkeeper": 0.72,
        "allrounder": 0.65,
        "bowler": 0.60,
    }
    return role_map.get(role, 0.65)
