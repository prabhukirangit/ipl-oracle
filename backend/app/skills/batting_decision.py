"""
BattingDecisionSkill — LLM-as-batsman: shot selection and intent.

In PERSONA mode: Full LLM call with persona prompt. Returns structured BattingDecision.
In HYBRID mode: LLM only at high pressure. Falls back to heuristic.
In PROBABILISTIC mode: Returns a heuristic decision based on stats (no LLM).
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill
from ..schemas.llm_outputs import BattingDecision, BATTING_DECISION_SCHEMA

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Shot selection heuristics for probabilistic fallback
_AGGRESSIVE_SHOTS = ["pull", "slog_sweep", "lofted_drive", "upper_cut", "slog"]
_ROTATING_SHOTS = ["flick", "nudge", "push", "dab", "glance"]
_DEFENSIVE_SHOTS = ["block", "leave", "dead_bat"]
_SIGNATURE_SHOTS = ["cover_drive", "straight_drive", "cut", "sweep", "reverse_sweep", "paddle"]


class BattingDecisionSkill(BaseSkill):
    """Decide batting intent and shot selection for a single delivery."""

    skill_name = "batting_decision"
    skill_type = "batting"
    requires_llm = True

    async def execute(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        """
        Execute batting decision.

        Context expected keys:
            - ball_context: dict with over, ball, score, wickets, target, pressure, etc.
            - narrative: str, natural language situation from ContextRenderer
            - bowling_decision: dict (optional), the bowler's intent if known
            - persona: dict (optional), the player's persona

        Returns:
            BattingDecision as a dict.
        """
        pressure = context.get("ball_context", {}).get("pressure_index", 0)

        if self.should_use_llm(mode, pressure):
            result = await self._llm_decision(agent, context)
            if result:
                return result

        # Fallback: heuristic decision
        return self._heuristic_decision(agent, context)

    async def _llm_decision(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Make an LLM-powered batting decision using the player's persona."""
        persona = context.get("persona") or agent.get_profile().get("persona", {})
        narrative = context.get("narrative", "")
        ball_ctx = context.get("ball_context", {})
        bowling = context.get("bowling_decision", {})

        system_prompt = persona.get(
            "system_prompt_template",
            "You are a professional IPL cricketer. Make your batting decision."
        )

        schema_instruction = (
            "\n\nRespond with ONLY valid JSON matching this schema:\n"
            f"{json.dumps(BATTING_DECISION_SCHEMA, indent=2)}\n\n"
            "No markdown, no explanation — just the JSON object."
        )

        bowling_info = ""
        if bowling:
            bowling_info = (
                f"\nThe bowler is planning: {bowling.get('delivery_type', 'unknown')} "
                f"on {bowling.get('line', 'unknown')} line, {bowling.get('length', 'unknown')} length."
            )

        user_prompt = f"{narrative}{bowling_info}\n\nWhat is your batting decision for this ball?"

        try:
            response = await agent.think(
                prompt=user_prompt + schema_instruction,
                context=ball_ctx,
                require_llm=True,
                max_tokens=768,
            )

            if response:
                # Parse structured output
                parsed = json.loads(response)
                decision = BattingDecision(**parsed)
                agent.log_decision(
                    decision_type="persona_batting",
                    decision=decision.model_dump(),
                    reasoning=decision.reasoning,
                    confidence=decision.confidence,
                    context=ball_ctx,
                )
                return decision.model_dump()

        except json.JSONDecodeError as exc:
            logger.warning("LLM batting response not valid JSON: %s", exc)
        except Exception as exc:
            logger.warning("LLM batting decision failed: %s", exc)

        return None

    def _heuristic_decision(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Stat-based heuristic batting decision (no LLM)."""
        ball_ctx = context.get("ball_context", {})
        profile = agent.get_profile()
        traits = profile.get("personality_traits", {})
        persona = context.get("persona") or profile.get("persona", {})

        pressure = ball_ctx.get("pressure_index", 0.3)
        over = ball_ctx.get("over", 10)
        target = ball_ctx.get("target")
        aggression = traits.get("aggression_index", 0.5)
        balls_faced = ball_ctx.get("balls_faced_this_innings", 0)

        # Determine intent
        if target and ball_ctx.get("required_run_rate", 0) > 12:
            intent = "slog"
            risk = min(0.9, 0.6 + pressure * 0.3)
        elif over >= 16 and aggression > 0.5:
            intent = "attack"
            risk = 0.7 + aggression * 0.2
        elif over <= 6 and aggression > 0.6:
            intent = "attack"
            risk = 0.5 + aggression * 0.3
        elif balls_faced < 5:
            intent = "rotate" if pressure > 0.5 else "defend"
            risk = 0.2
        elif pressure > 0.7:
            intent = "rotate"
            risk = 0.3
        else:
            intent = "attack" if aggression > 0.6 else "rotate"
            risk = 0.3 + aggression * 0.3

        # Select shot based on intent
        batting_p = persona.get("batting_personality", {})
        sig_shots = batting_p.get("signature_shots", _SIGNATURE_SHOTS)

        if intent == "slog":
            shot = random.choice(_AGGRESSIVE_SHOTS)
            zone = random.choice(["leg_side", "long_on", "midwicket"])
        elif intent == "attack":
            shot = random.choice(sig_shots) if sig_shots else random.choice(_SIGNATURE_SHOTS)
            zone = random.choice(["off_side", "cover", "straight", "midwicket"])
        elif intent == "defend":
            shot = random.choice(_DEFENSIVE_SHOTS)
            zone = "straight"
        else:  # rotate
            shot = random.choice(_ROTATING_SHOTS)
            zone = random.choice(["leg_side", "off_side", "fine_leg", "third_man"])

        confidence = max(0.3, min(0.9, 0.6 + traits.get("form_confidence", 0.5) * 0.3 - pressure * 0.2))

        decision = BattingDecision(
            intent=intent,
            shot_selection=shot,
            target_zone=zone,
            confidence=confidence,
            risk_appetite=risk,
            reasoning=f"{'High pressure' if pressure > 0.7 else 'Match situation'} dictates {intent} approach.",
            inner_monologue=f"Need to {intent}. Go with the {shot}.",
        )

        agent.log_decision(
            decision_type="heuristic_batting",
            decision=decision.model_dump(),
            reasoning=decision.reasoning,
            confidence=decision.confidence,
            context=ball_ctx,
        )

        return decision.model_dump()
