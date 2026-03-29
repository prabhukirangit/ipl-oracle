"""
StadiumAgent — Deterministic agent for IPL venue characteristics.

Provides ground dimensions, historical scoring patterns, chase win rates,
and powerplay averages. No randomness — all outputs are deterministic.
"""

from __future__ import annotations

from typing import Any

from .base_agent import BaseAgent


# ---------------------------------------------------------------------------
# Stadium profiles for all IPL 2026 venues
# ---------------------------------------------------------------------------

STADIUM_PROFILES: dict[str, dict[str, Any]] = {
    "Wankhede Stadium, Mumbai": {
        "venue_key": "wankhede_mumbai",
        "team": "MI",
        "city": "Mumbai",
        "capacity": 33108,
        "dimensions": {
            "straight_boundary_m": 68,
            "square_boundary_m": 62,
            "long_on_boundary_m": 72,
            "long_off_boundary_m": 70,
        },
        "pitch_type": "batting_friendly",
        "surface": "red_soil",
        "historical_scoring": {
            "avg_first_innings": 172,
            "avg_second_innings": 158,
            "highest_score": 235,
            "lowest_defended": 128,
            "typical_range": (145, 210),
        },
        "chase_stats": {
            "chase_win_rate": 0.48,
            "bat_first_win_rate": 0.52,
            "avg_winning_chase": 163,
        },
        "powerplay_stats": {
            "avg_powerplay_score": 52,
            "avg_powerplay_wickets": 1.8,
        },
        "dew_factor": 0.65,  # high dew influence in evening
        "spin_friendly": False,
        "pace_friendly": True,
        "notes": "Sea breeze from west in evening helps swing bowlers early. Shorter square boundaries.",
    },
    "Eden Gardens, Kolkata": {
        "venue_key": "eden_gardens_kolkata",
        "team": "KKR",
        "city": "Kolkata",
        "capacity": 66349,
        "dimensions": {
            "straight_boundary_m": 71,
            "square_boundary_m": 65,
            "long_on_boundary_m": 74,
            "long_off_boundary_m": 73,
        },
        "pitch_type": "balanced",
        "surface": "red_soil",
        "historical_scoring": {
            "avg_first_innings": 168,
            "avg_second_innings": 155,
            "highest_score": 222,
            "lowest_defended": 130,
            "typical_range": (140, 205),
        },
        "chase_stats": {
            "chase_win_rate": 0.52,
            "bat_first_win_rate": 0.48,
            "avg_winning_chase": 161,
        },
        "powerplay_stats": {
            "avg_powerplay_score": 49,
            "avg_powerplay_wickets": 1.6,
        },
        "dew_factor": 0.70,
        "spin_friendly": True,
        "pace_friendly": True,
        "notes": "Largest IPL crowd; spin assist in second half of innings. Dew factor significant.",
    },
    "M. Chinnaswamy Stadium, Bengaluru": {
        "venue_key": "chinnaswamy_bengaluru",
        "team": "RCB",
        "city": "Bengaluru",
        "capacity": 40000,
        "dimensions": {
            "straight_boundary_m": 63,
            "square_boundary_m": 58,
            "long_on_boundary_m": 66,
            "long_off_boundary_m": 65,
        },
        "pitch_type": "batting_paradise",
        "surface": "black_soil",
        "historical_scoring": {
            "avg_first_innings": 185,
            "avg_second_innings": 172,
            "highest_score": 263,
            "lowest_defended": 112,
            "typical_range": (160, 235),
        },
        "chase_stats": {
            "chase_win_rate": 0.55,
            "bat_first_win_rate": 0.45,
            "avg_winning_chase": 176,
        },
        "powerplay_stats": {
            "avg_powerplay_score": 58,
            "avg_powerplay_wickets": 1.4,
        },
        "dew_factor": 0.40,
        "spin_friendly": False,
        "pace_friendly": False,
        "notes": "High-altitude ground at 920m; ball carries well; shortest boundaries in IPL.",
    },
    "MA Chidambaram Stadium, Chennai": {
        "venue_key": "chepauk_chennai",
        "team": "CSK",
        "city": "Chennai",
        "capacity": 50000,
        "dimensions": {
            "straight_boundary_m": 70,
            "square_boundary_m": 64,
            "long_on_boundary_m": 72,
            "long_off_boundary_m": 71,
        },
        "pitch_type": "spin_friendly",
        "surface": "black_soil",
        "historical_scoring": {
            "avg_first_innings": 162,
            "avg_second_innings": 148,
            "highest_score": 211,
            "lowest_defended": 117,
            "typical_range": (135, 195),
        },
        "chase_stats": {
            "chase_win_rate": 0.44,
            "bat_first_win_rate": 0.56,
            "avg_winning_chase": 153,
        },
        "powerplay_stats": {
            "avg_powerplay_score": 46,
            "avg_powerplay_wickets": 2.0,
        },
        "dew_factor": 0.55,
        "spin_friendly": True,
        "pace_friendly": False,
        "notes": "Heavy Chennai wicket; massive home advantage for CSK; bat first recommended.",
    },
    "Arun Jaitley Stadium, Delhi": {
        "venue_key": "arun_jaitley_delhi",
        "team": "DC",
        "city": "Delhi",
        "capacity": 41842,
        "dimensions": {
            "straight_boundary_m": 69,
            "square_boundary_m": 62,
            "long_on_boundary_m": 71,
            "long_off_boundary_m": 70,
        },
        "pitch_type": "batting_friendly",
        "surface": "red_soil",
        "historical_scoring": {
            "avg_first_innings": 175,
            "avg_second_innings": 160,
            "highest_score": 231,
            "lowest_defended": 125,
            "typical_range": (150, 215),
        },
        "chase_stats": {
            "chase_win_rate": 0.50,
            "bat_first_win_rate": 0.50,
            "avg_winning_chase": 165,
        },
        "powerplay_stats": {
            "avg_powerplay_score": 53,
            "avg_powerplay_wickets": 1.7,
        },
        "dew_factor": 0.50,
        "spin_friendly": False,
        "pace_friendly": True,
        "notes": "Good batting wicket; Delhi smog can affect visibility; true surface.",
    },
    "Rajiv Gandhi International Stadium, Hyderabad": {
        "venue_key": "rajiv_gandhi_hyderabad",
        "team": "SRH",
        "city": "Hyderabad",
        "capacity": 55000,
        "dimensions": {
            "straight_boundary_m": 68,
            "square_boundary_m": 61,
            "long_on_boundary_m": 70,
            "long_off_boundary_m": 69,
        },
        "pitch_type": "batting_friendly",
        "surface": "red_soil",
        "historical_scoring": {
            "avg_first_innings": 170,
            "avg_second_innings": 158,
            "highest_score": 228,
            "lowest_defended": 121,
            "typical_range": (145, 210),
        },
        "chase_stats": {
            "chase_win_rate": 0.53,
            "bat_first_win_rate": 0.47,
            "avg_winning_chase": 162,
        },
        "powerplay_stats": {
            "avg_powerplay_score": 51,
            "avg_powerplay_wickets": 1.5,
        },
        "dew_factor": 0.72,
        "spin_friendly": False,
        "pace_friendly": True,
        "notes": "Heavy dew in evening games; second innings batting becomes very easy.",
    },
    "Narendra Modi Stadium, Ahmedabad": {
        "venue_key": "narendra_modi_ahmedabad",
        "team": "GT",
        "city": "Ahmedabad",
        "capacity": 132000,
        "dimensions": {
            "straight_boundary_m": 73,
            "square_boundary_m": 67,
            "long_on_boundary_m": 76,
            "long_off_boundary_m": 75,
        },
        "pitch_type": "balanced",
        "surface": "red_soil",
        "historical_scoring": {
            "avg_first_innings": 165,
            "avg_second_innings": 152,
            "highest_score": 215,
            "lowest_defended": 129,
            "typical_range": (140, 205),
        },
        "chase_stats": {
            "chase_win_rate": 0.49,
            "bat_first_win_rate": 0.51,
            "avg_winning_chase": 157,
        },
        "powerplay_stats": {
            "avg_powerplay_score": 48,
            "avg_powerplay_wickets": 1.9,
        },
        "dew_factor": 0.45,
        "spin_friendly": True,
        "pace_friendly": True,
        "notes": "World's largest cricket stadium; big outfield; good for bowlers.",
    },
    "Ekana Cricket Stadium, Lucknow": {
        "venue_key": "ekana_lucknow",
        "team": "LSG",
        "city": "Lucknow",
        "capacity": 50000,
        "dimensions": {
            "straight_boundary_m": 72,
            "square_boundary_m": 66,
            "long_on_boundary_m": 74,
            "long_off_boundary_m": 73,
        },
        "pitch_type": "batting_friendly",
        "surface": "red_soil",
        "historical_scoring": {
            "avg_first_innings": 173,
            "avg_second_innings": 160,
            "highest_score": 227,
            "lowest_defended": 128,
            "typical_range": (148, 210),
        },
        "chase_stats": {
            "chase_win_rate": 0.51,
            "bat_first_win_rate": 0.49,
            "avg_winning_chase": 164,
        },
        "powerplay_stats": {
            "avg_powerplay_score": 52,
            "avg_powerplay_wickets": 1.6,
        },
        "dew_factor": 0.68,
        "spin_friendly": False,
        "pace_friendly": True,
        "notes": "Flat North Indian track; dew plays huge role in evening games.",
    },
    "Sawai Mansingh Stadium, Jaipur": {
        "venue_key": "sawai_mansingh_jaipur",
        "team": "RR",
        "city": "Jaipur",
        "capacity": 30000,
        "dimensions": {
            "straight_boundary_m": 67,
            "square_boundary_m": 60,
            "long_on_boundary_m": 70,
            "long_off_boundary_m": 68,
        },
        "pitch_type": "spin_friendly",
        "surface": "red_soil",
        "historical_scoring": {
            "avg_first_innings": 168,
            "avg_second_innings": 155,
            "highest_score": 218,
            "lowest_defended": 123,
            "typical_range": (142, 205),
        },
        "chase_stats": {
            "chase_win_rate": 0.50,
            "bat_first_win_rate": 0.50,
            "avg_winning_chase": 159,
        },
        "powerplay_stats": {
            "avg_powerplay_score": 50,
            "avg_powerplay_wickets": 1.7,
        },
        "dew_factor": 0.35,
        "spin_friendly": True,
        "pace_friendly": False,
        "notes": "Spin turns from ball one; dry Rajasthan conditions; low dew.",
    },
    "Punjab Cricket Association Stadium, Mohali": {
        "venue_key": "pca_mohali",
        "team": "PBKS",
        "city": "Mohali",
        "capacity": 26000,
        "dimensions": {
            "straight_boundary_m": 70,
            "square_boundary_m": 64,
            "long_on_boundary_m": 72,
            "long_off_boundary_m": 71,
        },
        "pitch_type": "pace_friendly",
        "surface": "red_soil",
        "historical_scoring": {
            "avg_first_innings": 167,
            "avg_second_innings": 153,
            "highest_score": 221,
            "lowest_defended": 120,
            "typical_range": (140, 205),
        },
        "chase_stats": {
            "chase_win_rate": 0.51,
            "bat_first_win_rate": 0.49,
            "avg_winning_chase": 158,
        },
        "powerplay_stats": {
            "avg_powerplay_score": 50,
            "avg_powerplay_wickets": 2.1,
        },
        "dew_factor": 0.42,
        "spin_friendly": False,
        "pace_friendly": True,
        "notes": "Outswing in powerplay; good for pace bowlers; smaller ground.",
    },
}

# Default profile for venues not in the list
DEFAULT_STADIUM_PROFILE: dict[str, Any] = {
    "venue_key": "generic",
    "team": None,
    "city": "Unknown",
    "capacity": 35000,
    "dimensions": {
        "straight_boundary_m": 70,
        "square_boundary_m": 64,
        "long_on_boundary_m": 72,
        "long_off_boundary_m": 71,
    },
    "pitch_type": "balanced",
    "surface": "red_soil",
    "historical_scoring": {
        "avg_first_innings": 168,
        "avg_second_innings": 155,
        "highest_score": 218,
        "lowest_defended": 122,
        "typical_range": (142, 205),
    },
    "chase_stats": {
        "chase_win_rate": 0.50,
        "bat_first_win_rate": 0.50,
        "avg_winning_chase": 160,
    },
    "powerplay_stats": {
        "avg_powerplay_score": 50,
        "avg_powerplay_wickets": 1.8,
    },
    "dew_factor": 0.50,
    "spin_friendly": False,
    "pace_friendly": True,
    "notes": "Generic venue profile.",
}


class StadiumAgent(BaseAgent):
    """
    Deterministic agent for IPL venue characteristics.

    All methods return deterministic values — no randomness.
    Profile is set once and read-only during simulation.
    """

    # Map team abbreviations used in STADIUM_PROFILES to full IPL team names
    _TEAM_ABBREV_TO_FULL: dict[str, str] = {
        "MI": "Mumbai Indians",
        "CSK": "Chennai Super Kings",
        "RCB": "Royal Challengers Bengaluru",
        "KKR": "Kolkata Knight Riders",
        "SRH": "Sunrisers Hyderabad",
        "RR": "Rajasthan Royals",
        "DC": "Delhi Capitals",
        "GT": "Gujarat Titans",
        "PBKS": "Punjab Kings",
        "LSG": "Lucknow Super Giants",
        "LSG2": "Lucknow Super Giants",
    }

    def __init__(
        self,
        venue_name: str,
        run_id: str | None = None,
    ) -> None:
        """
        Initialise StadiumAgent for a named venue.

        Args:
            venue_name: Full venue name. Exact key match attempted first, then
                        fuzzy substring match against STADIUM_PROFILES keys.
            run_id: Simulation run ID
        """
        # Try exact match first
        profile = STADIUM_PROFILES.get(venue_name)
        if profile is None:
            # Fuzzy match: venue_name is substring of a key or vice-versa
            vl = venue_name.lower()
            for key, val in STADIUM_PROFILES.items():
                kl = key.lower()
                if vl in kl or kl in vl or vl.split(",")[0].strip() in kl:
                    profile = val
                    break
        if profile is None:
            profile = DEFAULT_STADIUM_PROFILE
        profile = profile.copy()
        profile["venue_name"] = venue_name
        super().__init__(agent_type="stadium", profile=profile, run_id=run_id)
        self._venue_name = venue_name

    @classmethod
    def for_venue(cls, venue_name: str, run_id: str | None = None) -> "StadiumAgent":
        """Factory method to create a StadiumAgent for a named venue."""
        return cls(venue_name=venue_name, run_id=run_id)

    # ------------------------------------------------------------------
    # Deterministic data access methods
    # ------------------------------------------------------------------

    def get_dimensions(self) -> dict[str, int]:
        """Return ground boundary dimensions in metres."""
        dims = self._profile.get("dimensions", {})
        self.log_decision("get_dimensions", dims, reasoning="Returning static venue dimensions")
        return dict(dims)

    def get_historical_scores(self) -> dict[str, Any]:
        """Return historical scoring data at this venue."""
        scores = self._profile.get("historical_scoring", {})
        return dict(scores)

    def get_chase_win_rate(self) -> float:
        """
        Return the historical chase win rate at this venue.

        Returns:
            Float 0-1 where 1.0 = teams always win chasing at this ground.
        """
        return self._profile.get("chase_stats", {}).get("chase_win_rate", 0.50)

    def get_bat_first_win_rate(self) -> float:
        """Return the historical bat-first win rate at this venue."""
        return self._profile.get("chase_stats", {}).get("bat_first_win_rate", 0.50)

    def get_powerplay_avg(self) -> dict[str, float]:
        """Return average powerplay stats (score and wickets)."""
        pp = self._profile.get("powerplay_stats", {})
        return {
            "avg_score": pp.get("avg_powerplay_score", 50),
            "avg_wickets": pp.get("avg_powerplay_wickets", 1.8),
        }

    def get_avg_first_innings_score(self) -> int:
        """Return average first innings score at this venue."""
        return self._profile.get("historical_scoring", {}).get("avg_first_innings", 168)

    def get_avg_second_innings_score(self) -> int:
        """Return average second innings score at this venue."""
        return self._profile.get("historical_scoring", {}).get("avg_second_innings", 155)

    def get_dew_factor(self) -> float:
        """
        Return the dew factor (0-1) for this venue.

        Higher values = more dew influence in evening games (helps batting team).
        """
        return self._profile.get("dew_factor", 0.50)

    def is_spin_friendly(self) -> bool:
        """Return True if this venue traditionally favours spinners."""
        return self._profile.get("spin_friendly", False)

    def is_pace_friendly(self) -> bool:
        """Return True if this venue traditionally favours pace bowlers."""
        return self._profile.get("pace_friendly", True)

    def get_typical_score_range(self) -> tuple[int, int]:
        """Return (low, high) typical first innings score range."""
        return tuple(self._profile.get("historical_scoring", {}).get("typical_range", (142, 205)))

    def get_toss_recommendation(self) -> str:
        """
        Deterministic toss recommendation based on venue stats and dew factor.

        Returns:
            'bat' or 'field'
        """
        dew = self.get_dew_factor()
        bat_first_wr = self.get_bat_first_win_rate()
        chase_wr = self.get_chase_win_rate()

        # High dew factor → field first (bat second is easier with no dew)
        if dew > 0.65:
            rec = "field"
            reason = f"High dew factor ({dew:.2f}) makes second innings batting easier"
        elif bat_first_wr > 0.52:
            rec = "bat"
            reason = f"Bat-first win rate ({bat_first_wr:.0%}) historically favours batting first"
        elif chase_wr > 0.52:
            rec = "field"
            reason = f"Chase win rate ({chase_wr:.0%}) historically favours fielding first"
        else:
            rec = "bat"
            reason = "Neutral venue — defaulting to bat first"

        self.log_decision(
            "toss_recommendation",
            rec,
            reasoning=reason,
        )
        return rec

    @property
    def venue_name(self) -> str:
        return self._venue_name

    @property
    def home_team(self) -> str | None:
        abbrev = self._profile.get("team")
        if abbrev is None:
            return None
        return self._TEAM_ABBREV_TO_FULL.get(abbrev, abbrev)

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["venue_name"] = self._venue_name
        return base

    def get_boundary_asymmetry_factor(
        self, shot_direction: str, batsman_handedness: str
    ) -> float:
        """
        Return boundary probability multiplier based on asymmetry.

        E.g., RHB hitting square-leg at Chinnaswamy: 1.15× (longer boundary)
        LHB hitting off-side: 0.90× (shorter boundary)

        Args:
            shot_direction: 'off_side', 'square_leg', 'extra_cover', 'mid_wicket', 'third_man', 'fine_leg'
            batsman_handedness: 'RHB' or 'LHB'

        Returns:
            float (0.8–1.2) representing boundary probability adjustment
        """
        if not hasattr(self, "_boundaries"):
            # Load from skills/stadium_boundaries.json
            import json
            import os

            # Try multiple path options for flexibility
            possible_paths = [
                "skills/stadium_boundaries.json",
                "../../../skills/stadium_boundaries.json",
                "/c/Users/prabh/OneDrive/Desktop/gitpk/ipl-panda/ipl-oracle/skills/stadium_boundaries.json",
            ]

            boundaries_data = {}
            for path in possible_paths:
                if os.path.exists(path):
                    try:
                        with open(path) as f:
                            data = json.load(f)
                            boundaries_data = data.get("stadiums", {})
                            break
                    except (IOError, json.JSONDecodeError):
                        continue

            # Extract stadium profile — match venue name to keys in the JSON
            stadium_key = None
            venue_name = self._venue_name
            for key in boundaries_data.keys():
                if key.lower() in venue_name.lower() or venue_name.lower() in key.lower():
                    stadium_key = key
                    break

            self._boundaries = boundaries_data.get(stadium_key, {}) if stadium_key else {}

        boundaries = self._boundaries
        if not boundaries:
            return 1.0  # Fallback: no asymmetry

        # Map shot directions to boundary fields
        direction_map = {
            "off_side": "east_boundary_m",
            "square_leg": "north_boundary_m",
            "extra_cover": "east_boundary_m",
            "mid_wicket": "north_boundary_m",
            "third_man": "south_boundary_m",
            "fine_leg": "west_boundary_m",
        }

        boundary_field = direction_map.get(shot_direction, "east_boundary_m")
        boundary_dist = boundaries.get(boundary_field, 72)

        # Average boundary across stadium
        all_boundaries = [
            boundaries.get("north_boundary_m", 72),
            boundaries.get("east_boundary_m", 72),
            boundaries.get("south_boundary_m", 72),
            boundaries.get("west_boundary_m", 72),
        ]
        avg_boundary = sum(all_boundaries) / len(all_boundaries)

        # Compute asymmetry factor (shorter boundary = easier sixes = 1.1-1.2)
        asymmetry_factor = avg_boundary / boundary_dist  # invert: shorter boundary = higher multiplier

        # Apply handedness adjustment if bias exists
        bias = boundaries.get("square_leg_bias", "neutral")
        if batsman_handedness == "RHB" and bias == "long" and shot_direction in ["square_leg", "mid_wicket"]:
            # RHB hitting toward longer square-leg boundary: penalty
            asymmetry_factor *= 0.95
        elif batsman_handedness == "RHB" and bias == "short" and shot_direction in ["off_side", "extra_cover"]:
            # RHB hitting toward shorter off-side boundary: boost
            asymmetry_factor *= 1.05
        elif batsman_handedness == "LHB" and bias == "short" and shot_direction in ["square_leg", "mid_wicket"]:
            # LHB hitting toward shorter square-leg: boost
            asymmetry_factor *= 1.05
        elif batsman_handedness == "LHB" and bias == "long" and shot_direction in ["off_side", "extra_cover"]:
            # LHB hitting toward longer off-side: penalty
            asymmetry_factor *= 0.95

        return max(0.8, min(1.2, asymmetry_factor))  # Clamp to realistic range

    def __repr__(self) -> str:
        return f"StadiumAgent(venue={self._venue_name!r}, run_id={self._run_id[:8]!r})"
