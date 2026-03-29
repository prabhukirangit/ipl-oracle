"""
SuperOverSkill — Strategy for super over selection and decision-making.

When scores are tied after 20 overs each, a super over is played.
Each team picks 3 batsmen and 1 bowler. The skill decides:
- Which batsmen to send (aggressive + experienced)
- Which bowler to use (death specialist with composure)
- Batting approach (all-out attack)
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class SuperOverSkill(BaseSkill):
    """Pick super over batting trio and bowler, set strategy."""

    skill_name = "super_over"
    skill_type = "tactical"
    requires_llm = False

    async def execute(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        """
        Context keys:
            - available_batsmen: list of player profile dicts (not yet dismissed or eligible)
            - available_bowlers: list of player profile dicts (overs remaining)
            - team_name: str

        Returns:
            batsmen: list of 3 player names (in batting order)
            bowler: str (player name)
            strategy: str ("all_out_attack" | "calculated_aggression")
            reasoning: str
        """
        batsmen_pool = context.get("available_batsmen", [])
        bowlers_pool = context.get("available_bowlers", [])
        team = context.get("team_name", "")

        # Score each batsman: aggression + strike_rate + experience + big_match_temperament
        def bat_score(p: dict) -> float:
            traits = p.get("personality_traits", {})
            career = p.get("career_stats", {})
            sr = career.get("strike_rate", 130)
            aggression = traits.get("aggression_index", 0.5)
            temperament = traits.get("big_match_temperament", 0.5)
            experience = p.get("experience_years", 5)
            exp_bonus = min(0.3, experience / 30.0)
            return (sr / 200.0) * 0.3 + aggression * 0.25 + temperament * 0.25 + exp_bonus * 0.2

        # Score each bowler: death specialization + experience + composure
        def bowl_score(p: dict) -> float:
            traits = p.get("personality_traits", {})
            career = p.get("career_stats", {})
            economy = career.get("bowling_economy", 8.5)
            death_spec = traits.get("death_overs_specialization", 0.5)
            resilience = traits.get("pressure_resilience", 0.5)
            experience = p.get("experience_years", 5)
            exp_bonus = min(0.3, experience / 30.0)
            eco_score = max(0, (10 - economy) / 10.0)
            return death_spec * 0.3 + resilience * 0.25 + eco_score * 0.25 + exp_bonus * 0.2

        # Pick top 3 batsmen
        sorted_batsmen = sorted(batsmen_pool, key=bat_score, reverse=True)
        chosen_batsmen = [p["name"] for p in sorted_batsmen[:3]]

        # Pick best bowler
        sorted_bowlers = sorted(bowlers_pool, key=bowl_score, reverse=True)
        chosen_bowler = sorted_bowlers[0]["name"] if sorted_bowlers else "Unknown"

        # Strategy: always aggressive in super over
        strategy = "all_out_attack"

        reasons = []
        if chosen_batsmen:
            reasons.append(f"Selected {', '.join(chosen_batsmen)} for maximum firepower")
        reasons.append(f"{chosen_bowler} to bowl — best death/pressure combo")
        reasons.append("Super over demands all-out attack from ball one")

        return {
            "batsmen": chosen_batsmen,
            "bowler": chosen_bowler,
            "strategy": strategy,
            "reasoning": "; ".join(reasons),
        }
