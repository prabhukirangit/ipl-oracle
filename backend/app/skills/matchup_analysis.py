"""
MatchupAnalysisSkill — Head-to-head batter vs bowler matchup awareness.

Evaluates the specific matchup between the current batsman and bowler,
considering style matchups (LHB vs right-arm pace, etc.), historical
tendencies from persona data, and weakness zones.
"""

from __future__ import annotations

import logging
import random
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Style matchup advantages: (batting_style, bowling_style) → modifier
# Positive = advantage to bowler, negative = advantage to batsman
_STYLE_MATCHUPS: dict[tuple[str, str], float] = {
    # Left-handers vs right-arm pace: natural angle creates edges
    ("left_hand", "right_arm_pace"): 0.02,
    # Right-handers vs left-arm pace: awkward angle
    ("right_hand", "left_arm_pace"): 0.025,
    # Left-handers vs left-arm spin: turning away = harder
    ("left_hand", "left_arm_spin"): 0.015,
    # Right-handers vs legbreak: googly threat
    ("right_hand", "legbreak"): 0.02,
    # Left-handers vs offbreak: turning in, easier to score
    ("left_hand", "right_arm_offbreak"): -0.02,
    # Right-handers vs left-arm spin: turning away
    ("right_hand", "left_arm_spin"): 0.015,
}


class MatchupAnalysisSkill(BaseSkill):
    """Analyze batter-bowler matchup to modify decision confidence and risk."""

    skill_name = "matchup_analysis"
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
            - batsman_profile: dict with batting_style, persona, weakness_zones
            - bowler_profile: dict with bowling_style, persona, signature_deliveries
            - ball_context: dict with over, pressure, etc.

        Returns:
            matchup_modifier: float (-0.1 to 0.1), positive = bowler advantage
            advantage: str ("batsman" | "bowler" | "neutral")
            weakness_targeted: bool
            reasoning: str
        """
        batsman = context.get("batsman_profile", {})
        bowler = context.get("bowler_profile", {})
        ball_ctx = context.get("ball_context", {})

        batting_style = batsman.get("batting_style", "right_hand")
        bowling_style = bowler.get("bowling_style", "right_arm_pace")

        modifier = 0.0
        reasons = []

        # 1. Style matchup
        style_mod = _STYLE_MATCHUPS.get((batting_style, bowling_style), 0.0)
        if style_mod != 0:
            modifier += style_mod
            if style_mod > 0:
                reasons.append(f"{batting_style} vs {bowling_style}: angle advantage to bowler")
            else:
                reasons.append(f"{batting_style} vs {bowling_style}: natural scoring angle for batsman")

        # 2. Weakness zone targeting
        batsman_persona = batsman.get("persona", {})
        batting_p = batsman_persona.get("batting_personality", {})
        weakness_zones = batting_p.get("weakness_zones", [])
        bowler_persona = bowler.get("persona", {})
        bowling_p = bowler_persona.get("bowling_personality", {})
        signature_deliveries = bowling_p.get("signature_deliveries", [])

        weakness_targeted = False
        # Check if bowler's strengths match batsman's weaknesses
        weakness_keywords = {
            "wide_outside_off": ["outswinger", "wide_yorker", "off_cutter"],
            "short_pitch": ["bouncer", "back_of_a_length"],
            "yorker": ["yorker", "wide_yorker"],
            "spin": ["googly", "carrom_ball", "arm_ball"],
            "pace": ["bouncer", "yorker"],
        }

        for wz in weakness_zones:
            for keyword, deliveries in weakness_keywords.items():
                if keyword in wz.lower():
                    if any(d in signature_deliveries for d in deliveries):
                        weakness_targeted = True
                        modifier += 0.03
                        reasons.append(f"Bowler's {signature_deliveries} targets batsman's weakness: {wz}")
                        break

        # 3. Experience differential
        batsman_exp = batsman.get("experience_years", 5)
        bowler_exp = bowler.get("experience_years", 5)
        exp_diff = (bowler_exp - batsman_exp) / 20.0  # normalized
        modifier += exp_diff * 0.02
        if abs(exp_diff) > 0.2:
            more_exp = "bowler" if exp_diff > 0 else "batsman"
            reasons.append(f"Experience advantage to {more_exp}")

        # 4. Pace vulnerability check
        traits = batsman.get("personality_traits", {})
        is_pacer = "pace" in bowling_style.lower()
        is_spinner = not is_pacer

        if is_pacer and traits.get("pace_vulnerability", 0.35) > 0.5:
            modifier += 0.02
            reasons.append("Batsman vulnerable to pace")
        elif is_spinner and traits.get("spin_vulnerability", 0.4) > 0.5:
            modifier += 0.02
            reasons.append("Batsman vulnerable to spin")

        # Clamp modifier
        modifier = max(-0.1, min(0.1, modifier))

        if modifier > 0.02:
            advantage = "bowler"
        elif modifier < -0.02:
            advantage = "batsman"
        else:
            advantage = "neutral"

        return {
            "matchup_modifier": round(modifier, 4),
            "advantage": advantage,
            "weakness_targeted": weakness_targeted,
            "reasoning": "; ".join(reasons) if reasons else "Neutral matchup",
        }
