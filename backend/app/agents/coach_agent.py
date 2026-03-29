"""
CoachAgent — Tactical decision-making agent for team management.

Makes decisions on:
- Batting order management
- Bowling changes and overs allocation
- Impact Player substitution timing and target
- Toss decision recommendation

Week 1: Deterministic rule-based decisions.
Week 3+: LLM for high-leverage Impact Player decisions.
"""

from __future__ import annotations

from typing import Any

from .base_agent import BaseAgent


class CoachAgent(BaseAgent):
    """
    Agent representing a team's coaching staff in the simulation.

    Decisions are made deterministically in Week 1 based on:
    - Coach's tactical style (data-driven / aggressive / conservative)
    - Match situation (score, wickets, overs)
    - Player fatigue and form
    - Impact Player timing strategy
    """

    def __init__(
        self,
        team: str,
        coach_name: str = "Team Coach",
        tactical_style: str = "balanced",
        ip_strategy: str = "middle_overs",
        toss_preference: str = "bat",
        run_id: str | None = None,
    ) -> None:
        """
        Initialise CoachAgent.

        Args:
            team: Team name
            coach_name: Coach's name
            tactical_style: 'aggressive' | 'conservative' | 'balanced' | 'data_driven'
            ip_strategy: When to use Impact Player — 'powerplay' | 'middle_overs' | 'death' | 'reactive'
            toss_preference: 'bat' | 'field' | 'venue_based'
            run_id: Simulation run ID
        """
        profile = {
            "team": team,
            "name": coach_name,
            "tactical_style": tactical_style,
            "ip_strategy": ip_strategy,
            "toss_preference": toss_preference,
            "ip_used": False,
            "bowling_changes_made": 0,
        }
        super().__init__(agent_type="coach", profile=profile, run_id=run_id)
        self._team = team
        self._tactical_style = tactical_style
        self._ip_strategy = ip_strategy
        self._ip_used = False

    def decide_toss(self, venue_recommendation: str, weather_dew: float) -> str:
        """
        Decide what to do at toss.

        Args:
            venue_recommendation: Venue's historical recommendation ('bat' or 'field')
            weather_dew: Dew factor (0-1) — high dew favours fielding first

        Returns:
            'bat' or 'field'
        """
        pref = self._profile.get("toss_preference", "bat")

        if pref == "venue_based":
            decision = venue_recommendation
        elif weather_dew > 0.65:
            # High dew — override preference to field (batting second easier)
            decision = "field"
        else:
            decision = pref

        self.log_decision(
            "toss_decision",
            decision,
            reasoning=f"Style: {self._tactical_style}, dew: {weather_dew:.2f}, venue rec: {venue_recommendation}",
            context={"venue_recommendation": venue_recommendation, "dew_factor": weather_dew},
        )
        return decision

    def should_use_impact_player(
        self,
        over: int,
        score: int,
        wickets: int,
        target: int | None,
        pressure_index: float,
        bowler_overs_bowled: int = 0,
    ) -> bool:
        """
        Decide whether to use the Impact Player substitution now.

        Args:
            over: Current over (0-19)
            score: Current innings score
            wickets: Wickets fallen
            target: Chase target (None = first innings)
            pressure_index: Current pressure (0-1)
            bowler_overs_bowled: Overs bowled by the outgoing bowler today
            
        Returns:
            True if Impact Player should be used now
        """
        if self._ip_used:
            return False

        # IMPACT PLAYER STATE DEPENDENCY / PHASE OPTIMIZATION
        # Tactical Arbitrage: If in the 1st innings and a bowler has completed their
        # 4-over quota (>= 4), substitute them immediately for an extra batter.
        is_first_innings = target is None
        if is_first_innings and bowler_overs_bowled >= 4:
            self.log_decision(
                "impact_player_decision",
                True,
                reasoning="Phase optimization: Executing mathematical arbitrage (trading bowled-out bowler for an extra batter)",
                context={"over": over, "bowler_overs_bowled": bowler_overs_bowled, "strategy": "phase_optimization"},
            )
            return True

        # Standard strategy fallback
        strategy = self._ip_strategy

        if strategy == "powerplay":
            trigger = over == 6 and wickets <= 2
        elif strategy == "death":
            trigger = over == 15 and wickets <= 6
        elif strategy == "middle_overs":
            trigger = 8 <= over <= 12 and wickets <= 4
        elif strategy == "reactive":
            # Use when under pressure or have a big advantage
            trigger = pressure_index > 0.75 or (target and score > target * 0.9 and over >= 15)
        else:
            trigger = over == 10  # default: use at half-time

        if trigger:
            self.log_decision(
                "impact_player_decision",
                True,
                reasoning=f"IP strategy '{strategy}' triggered at over {over}",
                context={"over": over, "score": score, "wickets": wickets, "pressure": pressure_index},
            )
        return trigger

    def mark_impact_player_used(self) -> None:
        """Record that the Impact Player substitution has been made."""
        self._ip_used = True
        self.add_memory({
            "type": "impact_player_used",
            "description": f"Team {self._team} used their Impact Player substitution",
        })

    def choose_next_bowler(
        self,
        available_bowlers: list[str],
        over: int,
        current_bowling_figures: dict[str, dict],
    ) -> str:
        """
        Choose the next bowler based on tactical style and situation.

        Week 1: Simple rotation logic.

        Args:
            available_bowlers: List of player names who can still bowl
            over: Current over
            current_bowling_figures: Dict of player_name -> {overs_bowled, runs, wickets}

        Returns:
            Player name of chosen bowler
        """
        if not available_bowlers:
            raise ValueError("No bowlers available")

        # Death overs (16+): prefer specialist death bowlers (simple heuristic)
        # For now, pick bowler with fewest overs bowled
        # Sort by overs bowled (ascending) to spread the load
        def overs_key(p: str) -> int:
            return current_bowling_figures.get(p, {}).get("overs_bowled", 0)
        chosen = min(available_bowlers, key=overs_key)

        self.log_decision(
            "bowling_change",
            chosen,
            reasoning=f"Rotation policy at over {over}",
            context={"over": over, "available": available_bowlers},
        )
        return chosen

    @property
    def team(self) -> str:
        return self._team

    @property
    def ip_used(self) -> bool:
        return self._ip_used

    def __repr__(self) -> str:
        return (
            f"CoachAgent(team={self._team!r}, style={self._tactical_style!r}, "
            f"run_id={self._run_id[:8]!r})"
        )
