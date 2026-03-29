"""
CrowdAgent — Models crowd energy and its effect on home/away players.

The crowd acts as the "12th man" — boosting home players' probability outcomes
and applying passive pressure to away players.

Week 1: Deterministic model based on match situation and venue.
Week 2: Added rivalry volatility boost (derby matches), get_volatility_factor().
"""

from __future__ import annotations

from typing import Any

from .base_agent import BaseAgent


# ---------------------------------------------------------------------------
# Rivalry pair definitions (Week 2)
# ---------------------------------------------------------------------------

RIVALRY_PAIRS: set[frozenset] = {
    frozenset({"Chennai Super Kings", "Mumbai Indians"}),
    frozenset({"Royal Challengers Bengaluru", "Chennai Super Kings"}),
    frozenset({"Mumbai Indians", "Royal Challengers Bengaluru"}),
    frozenset({"Kolkata Knight Riders", "Mumbai Indians"}),
    frozenset({"Sunrisers Hyderabad", "Royal Challengers Bengaluru"}),
}

# Rivalry boost: 20% uplift on crowd energy for derby matches
_RIVALRY_BOOST = 0.20


class CrowdAgent(BaseAgent):
    """
    Agent modelling crowd dynamics and the 12th-man home advantage effect.

    Crowd energy is a float (0-1) that changes based on:
    - Match situation (wickets, scoring rate vs target)
    - Over number (crowds louder at tense moments)
    - Venue capacity and historical crowd intensity
    - Whether home team is batting or fielding
    - Derby/rivalry match status (Week 2)

    Energy feeds into PlayerAgent probability adjustments via BallContext.
    """

    def __init__(
        self,
        home_team: str,
        venue_name: str,
        venue_capacity: int = 40000,
        crowd_intensity_base: float = 0.75,  # from home_away_profiles.json
        away_team: str = "",
        run_id: str | None = None,
    ) -> None:
        profile = {
            "home_team": home_team,
            "away_team": away_team,
            "venue_name": venue_name,
            "venue_capacity": venue_capacity,
            "crowd_intensity_base": crowd_intensity_base,
        }
        super().__init__(agent_type="crowd", profile=profile, run_id=run_id)
        self._home_team = home_team
        self._away_team = away_team
        self._base_intensity = crowd_intensity_base
        self._is_rivalry = self._check_rivalry(home_team, away_team)

    # ------------------------------------------------------------------
    # Rivalry detection (Week 2)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_rivalry(team1: str, team2: str) -> bool:
        """Return True if this matchup is a recognised rivalry derby."""
        if not team1 or not team2:
            return False
        return frozenset({team1, team2}) in RIVALRY_PAIRS

    @staticmethod
    def get_rivalry_boost(team1: str, team2: str) -> float:
        """
        Return the crowd energy boost for a rivalry match.

        Args:
            team1, team2: Full team names

        Returns:
            0.20 if this is a recognised derby match, 0.0 otherwise.
        """
        if frozenset({team1, team2}) in RIVALRY_PAIRS:
            return _RIVALRY_BOOST
        return 0.0

    def get_volatility_factor(self) -> float:
        """
        Return crowd energy variance factor for close/rivalry matches.

        Higher volatility means crowd energy swings more dramatically
        with each wicket/boundary. Used in pressure index calculation.

        Returns:
            Float (1.0–1.30). 1.0 = normal, 1.30 = maximum volatility (derby + tight game).
        """
        if self._is_rivalry:
            return 1.25
        return 1.05

    # ------------------------------------------------------------------
    # Core energy model
    # ------------------------------------------------------------------

    def get_energy(
        self,
        over: int,
        batting_team: str,
        wickets_fallen: int,
        score: int,
        target: int | None,
    ) -> float:
        """
        Compute current crowd energy level (0-1).

        Energy spikes when:
        - Home team takes wickets
        - Home team scores boundaries / sixes
        - Match is close (last 5 overs, small run difference)
        - Rivalry match (20% base boost, Week 2)

        Args:
            over: Current over (0-19)
            batting_team: Which team is currently batting
            wickets_fallen: Wickets lost in current innings
            score: Current score
            target: Chase target (None = first innings)

        Returns:
            Float 0-1 crowd energy level
        """
        energy = self._base_intensity
        home_batting = batting_team == self._home_team

        # Rivalry boost: base intensity is higher for derby matches
        rivalry_boost = _RIVALRY_BOOST if self._is_rivalry else 0.0
        energy = min(1.0, energy + rivalry_boost)

        # Powerplay excitement
        if over <= 5:
            energy += 0.05

        # Death overs excitement
        if over >= 16:
            energy += 0.10

        # Wicket excitement for home fielding team
        if not home_batting and wickets_fallen >= 3:
            energy += min(0.20, wickets_fallen * 0.04)

        # Chase tension
        if target and over >= 10:
            runs_needed = target - score
            balls_remaining = (20 - over) * 6
            if balls_remaining > 0:
                required_rr = (runs_needed * 6) / balls_remaining
                if required_rr > 10:
                    # Very hard chase — crowd either tense or celebrating
                    energy += 0.15 if not home_batting else 0.05
                elif 8 <= required_rr <= 10:
                    energy += 0.10  # tight game

        # Home team near win (close target, last 5 overs)
        if home_batting and target and over >= 15:
            runs_needed = target - score
            if 0 < runs_needed <= 30:
                energy = min(1.0, energy + 0.20)

        return round(min(1.0, max(0.0, energy)), 3)

    def get_home_pressure_modifier(
        self,
        crowd_energy: float,
        is_player_home: bool,
    ) -> float:
        """
        Return a pressure modifier based on crowd energy and player origin.

        Home players: positive modifier (crowd supports them, reduces pressure)
        Away players: negative modifier (crowd intimidates them, increases pressure)

        In rivalry matches the modifier is amplified by the volatility factor.

        Args:
            crowd_energy: Current crowd energy (0-1)
            is_player_home: True if this player's team is the home team

        Returns:
            Float: positive (reduces pressure) for home players,
                   negative (increases pressure) for away players
        """
        volatility = self.get_volatility_factor()
        crowd_effect = (crowd_energy - 0.5) * 0.20 * volatility  # max ±0.10–0.13
        if is_player_home:
            return crowd_effect  # positive: crowd helps
        else:
            return -crowd_effect  # negative: crowd intimidates

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def home_team(self) -> str:
        return self._home_team

    @property
    def is_rivalry_match(self) -> bool:
        return self._is_rivalry

    def __repr__(self) -> str:
        rivalry_tag = " [DERBY]" if self._is_rivalry else ""
        return f"CrowdAgent(home={self._home_team!r}{rivalry_tag}, run_id={self._run_id[:8]!r})"
