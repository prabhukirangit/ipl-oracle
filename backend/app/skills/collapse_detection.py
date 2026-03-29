"""
CollapseDetectionSkill — Detects and amplifies batting collapse tendency.

After 3+ wickets fall in quick succession (within 15 balls), the batting
team enters a "collapse zone" where incoming batsmen face amplified pressure,
reduced confidence, and higher dismissal probability. Experienced players
resist this contagion better.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Collapse thresholds
COLLAPSE_WICKETS_THRESHOLD = 3  # wickets in quick succession
COLLAPSE_BALLS_WINDOW = 15       # within this many balls
COLLAPSE_MAX_MODIFIER = 0.15     # maximum collapse amplification


class CollapseDetectionSkill(BaseSkill):
    """Detect batting collapse tendency and compute pressure amplification."""

    skill_name = "collapse_detection"
    skill_type = "behavioral"
    requires_llm = False

    async def execute(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        """
        Context keys:
            - fall_of_wickets: list of dicts with "score", "over" (e.g. "12.3"), "ball_number" (total balls)
            - current_ball_number: int, total balls bowled in innings
            - batsman_experience_years: int
            - batsman_pressure_resilience: float (0-1)

        Returns:
            is_collapse: bool
            collapse_severity: float (0-1)
            pressure_amplifier: float (1.0 = no effect, up to 1.15)
            confidence_penalty: float (0 to -0.15)
            reasoning: str
        """
        fow = context.get("fall_of_wickets", [])
        current_ball = context.get("current_ball_number", 0)
        experience = context.get("batsman_experience_years", 5)
        resilience = context.get("batsman_pressure_resilience", 0.5)

        if len(fow) < COLLAPSE_WICKETS_THRESHOLD:
            return {
                "is_collapse": False,
                "collapse_severity": 0.0,
                "pressure_amplifier": 1.0,
                "confidence_penalty": 0.0,
                "reasoning": "Not enough wickets for collapse detection",
            }

        # Count wickets fallen within the last COLLAPSE_BALLS_WINDOW balls
        recent_wickets = 0
        for w in reversed(fow):
            # Parse over string like "12.3" to ball number
            over_str = str(w.get("over", "0.0"))
            parts = over_str.split(".")
            over_num = int(parts[0])
            ball_in_over = int(parts[1]) if len(parts) > 1 else 0
            wicket_ball = over_num * 6 + ball_in_over

            if current_ball - wicket_ball <= COLLAPSE_BALLS_WINDOW:
                recent_wickets += 1
            else:
                break  # wickets are in order, so once we pass window, stop

        is_collapse = recent_wickets >= COLLAPSE_WICKETS_THRESHOLD

        if not is_collapse:
            return {
                "is_collapse": False,
                "collapse_severity": 0.0,
                "pressure_amplifier": 1.0,
                "confidence_penalty": 0.0,
                "reasoning": f"Only {recent_wickets} wickets in last {COLLAPSE_BALLS_WINDOW} balls",
            }

        # Compute collapse severity (3 wickets = 0.5, 4 = 0.75, 5+ = 1.0)
        severity = min(1.0, (recent_wickets - 2) / 4.0)

        # Experience reduces collapse impact
        # Veterans (10+ years) resist collapse contagion
        experience_resistance = min(1.0, experience / 15.0) * 0.4
        resilience_resistance = resilience * 0.3

        effective_severity = severity * (1.0 - experience_resistance - resilience_resistance)
        effective_severity = max(0.0, effective_severity)

        pressure_amplifier = 1.0 + effective_severity * COLLAPSE_MAX_MODIFIER
        confidence_penalty = -effective_severity * 0.15

        reasons = [f"{recent_wickets} wickets in last {COLLAPSE_BALLS_WINDOW} balls — collapse zone"]
        if experience >= 10:
            reasons.append(f"Veteran ({experience} yrs) resisting collapse pressure")
        if resilience >= 0.7:
            reasons.append("High pressure resilience reducing collapse impact")

        return {
            "is_collapse": True,
            "collapse_severity": round(effective_severity, 3),
            "pressure_amplifier": round(pressure_amplifier, 4),
            "confidence_penalty": round(confidence_penalty, 4),
            "reasoning": "; ".join(reasons),
        }
