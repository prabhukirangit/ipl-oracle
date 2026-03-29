"""
BowlingChangeSkill — Captain/coach pick next bowler with persona reasoning.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class BowlingChangeSkill(BaseSkill):
    """Decide which bowler to bring on next."""

    skill_name = "bowling_change"
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
            - available_bowlers: list[dict] (name, overs_bowled, economy, style)
            - over: int
            - match_situation: dict
            - on_strike_batsman: dict
        """
        pressure = context.get("match_situation", {}).get("pressure", 0)

        if self.should_use_llm(mode, pressure):
            result = await self._llm_decision(agent, context)
            if result:
                return result

        # Fallback: pick bowler with fewest overs
        bowlers = context.get("available_bowlers", [])
        if not bowlers:
            return {"bowler_name": None, "reasoning": "No bowlers available."}

        pick = min(bowlers, key=lambda b: b.get("overs_bowled", 0))
        return {
            "bowler_name": pick.get("name"),
            "reasoning": f"Rotation — {pick.get('name')} has bowled fewest overs.",
        }

    async def _llm_decision(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        bowlers_desc = "\n".join(
            f"  - {b.get('name')}: {b.get('overs_bowled', 0)} overs, eco {b.get('economy', 0):.1f}, {b.get('style', 'pace')}"
            for b in context.get("available_bowlers", [])
        )
        batsman = context.get("on_strike_batsman", {})
        situation = context.get("match_situation", {})

        prompt = (
            f"Over {situation.get('over', 0)}. Score: {situation.get('score', 0)}/{situation.get('wickets', 0)}. "
            f"On strike: {batsman.get('name', 'Unknown')} ({batsman.get('batting_style', 'right-hand')}).\n"
            f"Available bowlers:\n{bowlers_desc}\n\n"
            f"Who should bowl next? "
            f'Respond JSON: {{"bowler_name": "...", "reasoning": "..."}}'
        )

        try:
            response = await agent.think(prompt=prompt, context=situation, require_llm=True)
            if response:
                return json.loads(response)
        except Exception as exc:
            logger.warning("Bowling change LLM failed: %s", exc)

        return None
