"""
PressureResponseSkill — High-pressure override for any agent.

When pressure >= 0.85, this skill overrides the normal decision path
with a pressure-specific LLM call that asks the persona how they respond
to extreme match pressure.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class PressureResponseSkill(BaseSkill):
    """Generate a pressure-specific response from any agent."""

    skill_name = "pressure_response"
    skill_type = "batting"
    requires_llm = True

    async def execute(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        """
        Context keys:
            - pressure_index: float (>= 0.85)
            - match_situation: dict
            - agent_role: str ("batsman", "bowler", "captain")
        """
        if mode == "probabilistic":
            return {"response": "stay_focused", "modifier": 0.0}

        persona = agent.get_profile().get("persona", {})
        comm_style = persona.get("communication_style", {})
        under_pressure = comm_style.get("under_pressure_talk", "focus_inward")

        if mode == "persona":
            result = await self._llm_response(agent, context)
            if result:
                return result

        # Hybrid: personality-based modifier
        resilience = agent.get_profile().get("personality_traits", {}).get("pressure_resilience", 0.5)

        if under_pressure == "rally_teammates":
            response = "channel_aggression"
            modifier = 0.05  # slight confidence boost
        elif under_pressure == "ice_cool":
            response = "stay_calm"
            modifier = 0.08  # significant composure bonus
        else:
            response = "focus_inward"
            modifier = -0.02 if resilience < 0.4 else 0.02

        return {"response": response, "modifier": modifier}

    async def _llm_response(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        situation = context.get("match_situation", {})
        role = context.get("agent_role", "player")

        prompt = (
            f"EXTREME PRESSURE MOMENT. Pressure index: {context.get('pressure_index', 0.9):.2f}. "
            f"You are the {role}. "
            f"Score: {situation.get('score', 0)}/{situation.get('wickets', 0)}, "
            f"over {situation.get('over', 18)}. "
            f"{'Need ' + str(situation.get('runs_needed', 20)) + ' from ' + str(situation.get('balls_left', 12)) + ' balls.' if situation.get('runs_needed') else ''}\n\n"
            f"How do you respond to this pressure? "
            f'Respond JSON: {{"response": "stay_calm"|"channel_aggression"|"focus_inward", "modifier": -0.1 to 0.1, "inner_thought": "..."}}'
        )

        try:
            response = await agent.think(prompt=prompt, context=situation, require_llm=True)
            if response:
                return json.loads(response)
        except Exception as exc:
            logger.warning("Pressure response LLM failed: %s", exc)

        return None
