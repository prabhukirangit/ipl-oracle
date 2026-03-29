"""
TournamentState — Track IPL standings, elimination status, NRR requirements.

Computes psychological factors:
- Elimination Freedom: mathematically eliminated teams → 1.5× aggression
- Qualification Squeeze: 14+ points, 1 match left → pressure penalty 1.2×
- Safe: 2+ wins buffer → normal 1.0×
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TeamStanding:
    """Represents a team's position in the IPL standings."""
    team_name: str
    matches_played: int
    wins: int
    losses: int
    points: int = field(init=False)  # 2 per win, 1 per super-over loss, 0 per loss
    nrr: float = 0.0

    def __post_init__(self):
        """Calculate points (2 per win, 1 per super-over loss)."""
        super_over_losses = max(0, self.matches_played - self.wins - self.losses)
        self.points = (self.wins * 2) + super_over_losses


class TournamentState:
    """
    IPL tournament state tracker.

    Computes:
    - Elimination status (alive / eliminated / in_qualification_squeeze)
    - NRR requirements for qualification
    - Psychological modifiers for CoachAgent and PlayerAgent
    """

    def __init__(
        self,
        match_schedule: list[dict],
        current_match_index: int,
        standings: dict[str, TeamStanding],
        total_teams: int = 10,
        playoff_spots: int = 4,
    ):
        """
        Initialize tournament state.

        Args:
            match_schedule: List of match dicts with 'team1', 'team2', 'date', etc.
            current_match_index: Index of current match (0-based) in schedule
            standings: Dict[team_name] -> TeamStanding
            total_teams: Usually 10 for IPL
            playoff_spots: Usually 4 for IPL (top 4 qualify)
        """
        self.schedule = match_schedule
        self.current_index = current_match_index
        self.standings = standings
        self.total_teams = total_teams
        self.playoff_spots = playoff_spots

    def get_elimination_status(self, team: str) -> Literal["alive", "eliminated", "in_qualification_squeeze"]:
        """
        Determine if a team is mathematically eliminated, in qualification squeeze, or alive.

        Returns:
            - "eliminated": Max possible points < 8th place current points (no playoff chance)
            - "in_qualification_squeeze": 14+ points but only 1 match left (high psychological tension)
            - "alive": Everything else
        """
        if team not in self.standings:
            return "alive"

        team_standing = self.standings[team]
        matches_remaining = len(self.schedule) - self.current_index

        # Max possible points: current + (remaining matches × 2 points per win)
        max_possible_points = team_standing.points + (matches_remaining * 2)

        # Get 8th place team's current points (threshold for playoff)
        sorted_standings = sorted(
            self.standings.values(),
            key=lambda x: x.points,
            reverse=True
        )
        if len(sorted_standings) >= self.total_teams:
            eighth_place_points = sorted_standings[self.total_teams - 1].points
        else:
            eighth_place_points = 0

        # Mathematically eliminated: even if you win all remaining, you can't reach 8th place
        if max_possible_points < eighth_place_points:
            return "eliminated"

        # Qualification squeeze: secured 14+ points (7 wins) but only 1 match left
        # This creates peak psychological tension: one loss ends playoff hopes
        if team_standing.points >= 14 and matches_remaining == 1:
            return "in_qualification_squeeze"

        return "alive"

    def get_nrr_requirement(self, team: str) -> float:
        """
        Compute NRR margin needed to qualify if in squeeze.

        Simplified: if team is in squeeze, return their current NRR.
        In production, this would compute exact target based on competitors' NRR.

        Args:
            team: Team name

        Returns:
            NRR value (float). Positive if team is ahead, negative if behind.
        """
        if team not in self.standings:
            return 0.0

        return self.standings[team].nrr

    def get_aggression_modifier(self, team: str) -> float:
        """
        Psychological aggression multiplier based on elimination status.

        Used in:
        - CoachAgent.decide_batting_approach()
        - PlayerAgent.get_aggression_modifier()

        Returns:
            - 1.5 if eliminated (nothing to lose → fearless cricket)
            - 0.85 if in qualification squeeze (peak pressure → increased error rate)
            - 1.0 if alive and safe
        """
        status = self.get_elimination_status(team)

        if status == "eliminated":
            return 1.5  # Elimination freedom: play fearless
        elif status == "in_qualification_squeeze":
            return 0.85  # Qualification choke: elevated pressure → errors
        else:
            return 1.0  # Normal

    def get_pressure_penalty(self, team: str) -> float:
        """
        Pressure penalty multiplier (applied to error rates, edge probability, etc.).

        - in_qualification_squeeze: 1.2× (20% more likely to error under peak pressure)
        - eliminated: 0.9× (actually more relaxed, play loose)
        - alive: 1.0× (normal)
        """
        status = self.get_elimination_status(team)

        if status == "in_qualification_squeeze":
            return 1.2  # Peak pressure increases error margin
        elif status == "eliminated":
            return 0.9  # Less pressure, play looser
        else:
            return 1.0  # Normal

    def get_team_standing(self, team: str) -> TeamStanding | None:
        """Retrieve full standing for a team."""
        return self.standings.get(team)

    def to_dict(self) -> dict:
        """Serialize tournament state for API responses."""
        return {
            "current_match_index": self.current_index,
            "matches_remaining": len(self.schedule) - self.current_index,
            "total_teams": self.total_teams,
            "playoff_spots": self.playoff_spots,
            "standings": {
                name: {
                    "matches_played": standing.matches_played,
                    "wins": standing.wins,
                    "losses": standing.losses,
                    "points": standing.points,
                    "nrr": standing.nrr,
                }
                for name, standing in self.standings.items()
            }
        }
