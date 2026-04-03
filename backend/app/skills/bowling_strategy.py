"""
BowlingStrategySkill — LLM-as-bowler: delivery plan and execution.

In PERSONA mode: Full LLM call with bowler persona. Returns structured BowlingDecision.
In HYBRID mode: LLM only at high pressure. Falls back to heuristic.
In PROBABILISTIC mode: Returns a heuristic decision (no LLM).
"""

from __future__ import annotations

from app.services.json_repair import parse_llm_json

import json
import logging
import random
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill
from ..schemas.llm_outputs import BowlingDecision, BOWLING_DECISION_SCHEMA

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Delivery pools by bowling type
_PACE_DELIVERIES = ["outswinger", "inswinger", "bouncer", "yorker", "slower_ball", "knuckle_ball", "leg_cutter", "off_cutter"]
_SPIN_DELIVERIES = ["stock_delivery", "arm_ball", "googly", "top_spinner", "carrom_ball", "slider"]
_DEATH_PACE = ["yorker", "wide_yorker", "slower_ball", "bouncer", "knuckle_ball"]
_POWERPLAY_PACE = ["outswinger", "inswinger", "bouncer", "good_length_seam"]


class BowlingStrategySkill(BaseSkill):
    """Decide bowling delivery type, line, and length for a single ball."""

    skill_name = "bowling_strategy"
    skill_type = "bowling"
    requires_llm = True

    async def execute(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        """
        Execute bowling decision.

        Context expected keys:
            - ball_context: dict with over, ball, score, wickets, target, pressure, etc.
            - narrative: str, natural language situation from ContextRenderer
            - batsman_profile: dict (optional), the batsman's profile
            - persona: dict (optional), the bowler's persona

        Returns:
            BowlingDecision as a dict.
        """
        pressure = context.get("ball_context", {}).get("pressure_index", 0)

        if self.should_use_llm(mode, pressure):
            result = await self._llm_decision(agent, context)
            if result:
                return result

        return self._heuristic_decision(agent, context)

    async def _llm_decision(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Make an LLM-powered bowling decision using the bowler's persona."""
        persona = context.get("persona") or agent.get_profile().get("persona", {})
        narrative = context.get("narrative", "")
        ball_ctx = context.get("ball_context", {})
        batsman = context.get("batsman_profile", {})

        system_prompt = persona.get(
            "system_prompt_template",
            "You are a professional IPL bowler. Plan your delivery."
        )

        schema_instruction = (
            "\n\nRespond with ONLY valid JSON matching this schema:\n"
            f"{json.dumps(BOWLING_DECISION_SCHEMA, indent=2)}\n\n"
            "No markdown, no explanation — just the JSON object."
        )

        batsman_info = ""
        if batsman:
            batsman_info = (
                f"\nYou're bowling to {batsman.get('name', 'the batsman')} "
                f"({batsman.get('batting_style', 'right-hand')})."
            )

        user_prompt = f"{narrative}{batsman_info}\n\nWhat delivery are you bowling?"

        try:
            response = await agent.think(
                prompt=user_prompt + schema_instruction,
                context=ball_ctx,
                require_llm=True,
                max_tokens=768,
            )

            if response:
                parsed = parse_llm_json(response)
                decision = BowlingDecision(**parsed)
                agent.log_decision(
                    decision_type="persona_bowling",
                    decision=decision.model_dump(),
                    reasoning=decision.reasoning,
                    confidence=decision.confidence,
                    context=ball_ctx,
                )
                return decision.model_dump()

        except json.JSONDecodeError as exc:
            logger.warning("LLM bowling response not valid JSON: %s", exc)
        except Exception as exc:
            logger.warning("LLM bowling decision failed: %s", exc)

        return None

    def _heuristic_decision(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Stat-based heuristic bowling decision (no LLM)."""
        ball_ctx = context.get("ball_context", {})
        profile = agent.get_profile()
        persona = context.get("persona") or profile.get("persona", {})
        bowling_p = persona.get("bowling_personality", {})

        over = ball_ctx.get("over", 10)
        pressure = ball_ctx.get("pressure_index", 0.3)
        dew = ball_ctx.get("dew_factor", 1.0)
        bowling_style = profile.get("bowling_style", "pace")

        is_spinner = bowling_style in ("off_break", "legbreak", "chinaman", "left_arm_spin")
        is_pacer = not is_spinner

        # Phase-based delivery selection
        if over <= 6:  # Powerplay
            if is_pacer:
                delivery = random.choice(_POWERPLAY_PACE)
                line = random.choice(["off_stump", "fourth_stump"])
                length = random.choice(["good_length", "full", "back_of_a_length"])
            else:
                delivery = random.choice(["stock_delivery", "arm_ball"])
                line = "off_stump"
                length = "good_length"
        elif over >= 16:  # Death
            if is_pacer:
                delivery = random.choice(_DEATH_PACE)
                line = random.choice(["off_stump", "leg_stump", "wide_outside_off"])
                length = "yorker_length" if random.random() < 0.5 else "back_of_a_length"
            else:
                # Spinners in death with dew are risky
                if dew < 0.85:
                    delivery = random.choice(["stock_delivery", "slider"])
                    line = "off_stump"
                    length = "full"
                else:
                    delivery = random.choice(_SPIN_DELIVERIES)
                    line = "off_stump"
                    length = "good_length"
        else:  # Middle overs
            if is_spinner:
                delivery = random.choice(_SPIN_DELIVERIES)
                line = random.choice(["off_stump", "middle", "leg_stump"])
                length = random.choice(["good_length", "full"])
            else:
                delivery = random.choice(_PACE_DELIVERIES[:5])
                line = random.choice(["off_stump", "fourth_stump"])
                length = random.choice(["good_length", "back_of_a_length", "short"])

        # Use signature deliveries from persona if available
        sig = bowling_p.get("signature_deliveries", [])
        if sig and random.random() < 0.3:
            delivery = random.choice(sig)

        confidence = max(0.3, min(0.9, 0.6 - pressure * 0.2 + (1.0 - ball_ctx.get("bowler_fatigue", 0)) * 0.2))

        field = "attacking" if pressure < 0.5 or over <= 6 else "defensive" if pressure > 0.7 else "spread"

        decision = BowlingDecision(
            delivery_type=delivery,
            line=line,
            length=length,
            variation=None,
            field_setup_hint=field,
            confidence=confidence,
            reasoning=f"Over {over}, {'death' if over >= 16 else 'powerplay' if over <= 6 else 'middle'} phase. "
                      f"{'Dew affecting grip.' if dew < 0.85 and is_spinner else 'Good conditions.'}",
            inner_monologue=f"Going with the {delivery}. {line} line.",
        )

        agent.log_decision(
            decision_type="heuristic_bowling",
            decision=decision.model_dump(),
            reasoning=decision.reasoning,
            confidence=decision.confidence,
            context=ball_ctx,
        )

        return decision.model_dump()
