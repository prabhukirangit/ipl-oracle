"""
FieldPlacementSkill — Captain sets field for this bowler/batsman matchup.

PERSONA mode only — generates a descriptive field setup.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_DEFAULT_FIELDS = {
    "powerplay_pace": "2 slips, gully, mid-off, mid-on, fine leg, third man. Attacking.",
    "powerplay_spin": "Slip, short leg, mid-off, mid-on, cover, midwicket. Tight.",
    "middle_overs_spin": "No slip. Sweeper cover, deep midwicket, long-on, long-off. Contain.",
    "death_pace": "Yorker field. Long-on, long-off, fine leg, deep square. No width.",
    "default": "Standard T20 field. 4 fielders in the ring, 5 on the boundary.",
}


class FieldPlacementSkill(BaseSkill):
    """Generate field placement description."""

    skill_name = "field_placement"
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
            - bowler_style: str
            - batsman_style: str
            - match_situation: dict
        """
        if mode == "persona":
            result = await self._llm_field(agent, context)
            if result:
                return result

        # Template field
        over = context.get("over", 10)
        style = context.get("bowler_style", "pace")

        if over <= 6:
            key = f"powerplay_{'spin' if 'spin' in style or 'break' in style else 'pace'}"
        elif over >= 16:
            key = "death_pace"
        else:
            key = "middle_overs_spin" if "spin" in style or "break" in style else "default"

        return {
            "field_description": _DEFAULT_FIELDS.get(key, _DEFAULT_FIELDS["default"]),
            "is_attacking": over <= 6 or over >= 16,
        }

    async def _llm_field(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        situation = context.get("match_situation", {})
        prompt = (
            f"You're setting the field. Over {context.get('over', 10)}. "
            f"Bowler: {context.get('bowler_style', 'pace')}. "
            f"Batsman: {context.get('batsman_style', 'right-hand')}. "
            f"Score: {situation.get('score', 0)}/{situation.get('wickets', 0)}.\n"
            f'Respond JSON: {{"field_description": "...", "is_attacking": true/false}}'
        )

        try:
            response = await agent.think(prompt=prompt, context=situation, require_llm=True)
            if response:
                return json.loads(response)
        except Exception as exc:
            logger.warning("Field placement LLM failed: %s", exc)

        return None
