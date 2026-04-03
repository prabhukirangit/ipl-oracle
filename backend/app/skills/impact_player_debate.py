"""
ImpactPlayerDebateSkill — Coach reasons about Impact Player substitution timing.

Impact Player decisions are always high-leverage (per CLAUDE.md rules),
so this skill always uses LLM when available.
"""

from __future__ import annotations

from app.services.json_repair import parse_llm_json

import json
import logging
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ImpactPlayerDebateSkill(BaseSkill):
    """Reason about Impact Player substitution timing."""

    skill_name = "impact_player_debate"
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
            - over: int
            - score: int, wickets: int
            - target: int | None
            - pressure_index: float
            - ip_pool: list[dict] (available substitutes)
            - current_xi_overseas_count: int
            - ip_already_used: bool
        """
        if context.get("ip_already_used", False):
            return {"should_substitute": False, "reasoning": "Already used Impact Player."}

        if mode != "probabilistic":
            result = await self._llm_decision(agent, context)
            if result:
                return result

        return self._rule_based(agent, context)

    async def _llm_decision(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        persona = agent.get_profile().get("persona", {})
        system = persona.get(
            "system_prompt_template",
            "You are an IPL coach deciding on Impact Player substitution."
        )

        pool_desc = ", ".join(
            p.get("name", "Player") for p in context.get("ip_pool", [])
        )

        prompt = (
            f"Score: {context.get('score', 0)}/{context.get('wickets', 0)}, "
            f"over {context.get('over', 0)}. "
            f"{'Target: ' + str(context.get('target')) + '. ' if context.get('target') else ''}"
            f"Pressure: {context.get('pressure_index', 0):.2f}. "
            f"Available substitutes: {pool_desc or 'None'}. "
            f"Overseas in XI: {context.get('current_xi_overseas_count', 3)}/4.\n\n"
            f"Should you use the Impact Player now? If yes, who? "
            f'Respond JSON: {{"should_substitute": true/false, "player_name": "...", "reasoning": "..."}}'
        )

        try:
            response = await agent.think(prompt=prompt, context=context, require_llm=True)
            if response:
                return parse_llm_json(response)
        except Exception as exc:
            logger.warning("Impact Player debate LLM failed: %s", exc)

        return None

    def _rule_based(self, agent: BaseAgent, context: dict[str, Any]) -> dict[str, Any]:
        """Existing CoachAgent-style rule-based IP decision."""
        over = context.get("over", 0)
        pressure = context.get("pressure_index", 0)
        target = context.get("target")

        # Phase optimization: bowler after 4-over quota if chasing 200+
        if target and target >= 200 and over >= 15:
            return {
                "should_substitute": True,
                "reasoning": "Chasing 200+, need fresh bowling or batting resource in death.",
                "player_name": None,  # Let CoachAgent pick
            }

        # Reactive: high pressure
        if pressure > 0.75:
            return {
                "should_substitute": True,
                "reasoning": "High pressure moment — bring in Impact Player for tactical edge.",
                "player_name": None,
            }

        return {"should_substitute": False, "reasoning": "Not the right moment yet."}
