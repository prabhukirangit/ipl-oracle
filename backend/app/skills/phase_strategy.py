"""
PhaseStrategySkill — Tactical phase awareness for powerplay, middle, death, and final over.

Provides phase-specific tactical modifiers that influence batting and bowling
decisions. Each phase has distinct strategic characteristics:
- Powerplay (1-6): field restrictions, aggressive batting, swing bowling
- Middle (7-15): rotation, spin dominance, building platform
- Death (16-19): yorkers, slog, high-risk/high-reward
- Final over (20): maximum pressure, specialist skills needed
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class PhaseStrategySkill(BaseSkill):
    """Compute phase-specific tactical modifiers for batting and bowling."""

    skill_name = "phase_strategy"
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
            - over: int (0-indexed)
            - ball: int (0-indexed)
            - score: int
            - wickets: int
            - target: int | None
            - current_run_rate: float
            - required_run_rate: float
            - batsman_powerplay_spec: float
            - batsman_death_spec: float
            - bowler_death_spec: float
            - batting_team_experience_avg: float (avg experience years of remaining batsmen)
            - is_batting: bool (perspective: batting or bowling team)

        Returns:
            phase: str ("powerplay" | "middle" | "death" | "final_over")
            aggression_modifier: float (-0.1 to 0.2)
            risk_modifier: float (-0.1 to 0.2)
            recommended_intent: str
            field_restriction: bool
            reasoning: str
        """
        over = context.get("over", 10)
        ball = context.get("ball", 0)
        score = context.get("score", 0)
        wickets = context.get("wickets", 0)
        target = context.get("target")
        crr = context.get("current_run_rate", 7.0)
        rrr = context.get("required_run_rate", 0)
        pp_spec = context.get("batsman_powerplay_spec", 0.5)
        death_spec = context.get("batsman_death_spec", 0.5)
        bowler_death = context.get("bowler_death_spec", 0.5)
        team_exp = context.get("batting_team_experience_avg", 5.0)
        is_batting = context.get("is_batting", True)

        # Determine phase
        if over <= 5:
            phase = "powerplay"
        elif over >= 19:
            phase = "final_over"
        elif over >= 16:
            phase = "death"
        else:
            phase = "middle"

        aggression_mod = 0.0
        risk_mod = 0.0
        reasons = []

        if phase == "powerplay":
            # Field restrictions: only 2 fielders outside 30-yard circle
            aggression_mod = 0.05 + (pp_spec - 0.5) * 0.1
            risk_mod = 0.03
            if is_batting:
                if wickets <= 1:
                    intent = "attack"
                    reasons.append("Powerplay with field restrictions — exploit gaps")
                else:
                    intent = "rotate"
                    aggression_mod -= 0.03
                    reasons.append("Lost early wickets — consolidate in powerplay")
            else:
                intent = "attack"
                reasons.append("Powerplay bowling — attack stumps, use swing")

        elif phase == "middle":
            # Build or consolidate
            if target and rrr > 9:
                aggression_mod = 0.04
                risk_mod = 0.03
                intent = "attack"
                reasons.append(f"Required rate {rrr:.1f} — need to accelerate in middle overs")
            elif not target and crr < 7:
                aggression_mod = 0.02
                intent = "rotate"
                reasons.append("Below par run rate — rotate and find boundaries")
            else:
                aggression_mod = 0.0
                intent = "rotate"
                reasons.append("Middle overs — build platform for death overs assault")

            if wickets >= 5:
                aggression_mod -= 0.04
                risk_mod -= 0.04
                intent = "rotate"
                reasons.append("Deep in wickets — play safe through middle overs")

        elif phase == "death":
            # High-intensity scoring phase
            aggression_mod = 0.08 + (death_spec - 0.5) * 0.12
            risk_mod = 0.08

            if is_batting:
                if target and rrr > 12:
                    intent = "slog"
                    risk_mod = 0.15
                    reasons.append(f"RRR {rrr:.1f} in death — must go all out")
                elif not target:
                    intent = "attack"
                    reasons.append("Death overs batting first — maximize total")
                else:
                    intent = "attack"
                    reasons.append("Death overs chase — maintain pressure")
            else:
                # Bowling in death
                aggression_mod = (bowler_death - 0.5) * 0.08
                intent = "defend"
                reasons.append("Death bowling — yorkers, wide lines, limit damage")

            # Experience bonus in death: veterans handle chaos better
            if team_exp >= 8:
                aggression_mod += 0.02
                reasons.append("Experienced batting unit — comfortable in death overs")

        else:  # final_over
            aggression_mod = 0.12
            risk_mod = 0.12

            if is_batting:
                if target:
                    runs_needed = target - score
                    if runs_needed <= 6:
                        intent = "rotate"
                        risk_mod = 0.05
                        reasons.append(f"Only {runs_needed} needed in final over — don't panic")
                    elif runs_needed <= 12:
                        intent = "attack"
                        reasons.append(f"Need {runs_needed} from last over — find boundaries")
                    else:
                        intent = "slog"
                        risk_mod = 0.2
                        reasons.append(f"Need {runs_needed} from last over — swing at everything")
                else:
                    intent = "slog"
                    reasons.append("Last over batting first — go big")
            else:
                intent = "defend"
                reasons.append("Bowling final over — execute plans, stay calm")
                if team_exp >= 10:
                    reasons.append("Experienced bowler closing out — trust the plan")

        # Clamp modifiers
        aggression_mod = max(-0.1, min(0.2, aggression_mod))
        risk_mod = max(-0.1, min(0.2, risk_mod))

        return {
            "phase": phase,
            "aggression_modifier": round(aggression_mod, 4),
            "risk_modifier": round(risk_mod, 4),
            "recommended_intent": intent,
            "field_restriction": phase == "powerplay",
            "reasoning": "; ".join(reasons),
        }
