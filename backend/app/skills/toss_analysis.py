"""
TossAnalysisSkill — Coach analyzes toss decision using persona reasoning.

In PERSONA mode: LLM reasons about venue, dew, team strengths.
In HYBRID/PROBABILISTIC: Rule-based (existing CoachAgent logic).
"""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class TossAnalysisSkill(BaseSkill):
    """Analyze toss decision with persona reasoning."""

    skill_name = "toss_analysis"
    skill_type = "tactical"
    requires_llm = True

    async def execute(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        """
        Context keys:
            - venue: str
            - dew_factor: float
            - chase_win_rate: float
            - team_strengths: dict
        """
        if self.should_use_llm(mode, pressure=1.0):  # toss is always high-leverage
            result = await self._llm_decision(agent, context)
            if result:
                return result

        # Fallback: rule-based
        dew = context.get("dew_factor", 0.5)
        chase_wr = context.get("chase_win_rate", 0.5)

        if dew > 0.65 or chase_wr > 0.55:
            decision = "field"
            reasoning = "Dew expected — batting second is easier."
        else:
            decision = "bat"
            reasoning = "Good batting conditions — set a total."

        return {
            "decision": decision,
            "reasoning": reasoning,
            "confidence": 0.7,
        }

    async def _llm_decision(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        persona = agent.get_profile().get("persona", {})
        system = persona.get(
            "system_prompt_template",
            "You are an IPL team coach making the toss decision."
        )

        prompt = (
            f"You won the toss at {context.get('venue', 'the venue')}. "
            f"Dew factor: {context.get('dew_factor', 0.5):.2f}. "
            f"Historical chase win rate here: {context.get('chase_win_rate', 0.5):.0%}. "
            f"\nDecide: bat or field? Respond with JSON: "
            f'{{"decision": "bat"|"field", "reasoning": "...", "confidence": 0.0-1.0}}'
        )

        try:
            response = await agent.think(prompt=prompt, context=context, require_llm=True)
            if response:
                return json.loads(response)
        except Exception as exc:
            logger.warning("Toss analysis LLM failed: %s", exc)

        return None
