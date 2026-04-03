"""
TeamHuddleSkill — Multi-agent team communication at break points.

Generates team messages at strategic timeouts, over changes, and after wickets.
In PERSONA mode: LLM generates messages in character.
In HYBRID mode: Template strings selected from persona data.
In PROBABILISTIC mode: No messages generated.
"""

from __future__ import annotations

from app.services.json_repair import parse_llm_json

import json
import logging
import random
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill
from ..schemas.llm_outputs import TeamHuddle, TEAM_HUDDLE_SCHEMA

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Template messages for HYBRID mode
_ENCOURAGEMENT_TEMPLATES = [
    "Keep going, we've got this!",
    "One ball at a time. Stay focused.",
    "Big moment. Show what you're made of.",
    "Trust your instincts. You've been here before.",
    "Pressure is a privilege. Embrace it.",
]

_STRATEGY_TEMPLATES = {
    "powerplay_batting": "Take the singles, pick the bad balls for boundaries. No rash shots.",
    "death_batting": "Target 15+ this over. Look for the short ball to pull.",
    "middle_overs_batting": "Rotate strike. Keep the scoreboard ticking.",
    "powerplay_bowling": "Hit the top of off stump. Make them play.",
    "death_bowling": "Yorkers. Wide of off. No width on leg side.",
    "wicket_fallen_batting": "Settle in first few balls. Then play your game.",
    "high_pressure": "Stay calm. Back yourself. We've practiced this.",
    "low_pressure": "Play freely. Express yourself.",
}


class TeamHuddleSkill(BaseSkill):
    """Generate team communication at break points."""

    skill_name = "team_huddle"
    skill_type = "communication"
    requires_llm = True

    async def execute(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        """
        Context keys:
            - trigger: str ("timeout", "over_change", "wicket", "boundary_drought")
            - match_situation: dict (score, wickets, overs, target, pressure)
            - team: str
            - participants: list[dict] (agent profiles in the huddle)
        """
        if mode == "probabilistic":
            return {"messages": [], "tactical_shift": None}

        if mode == "persona" and self.requires_llm:
            result = await self._llm_huddle(agent, context)
            if result:
                return result

        # HYBRID: template-based messages
        return self._template_huddle(context)

    async def _llm_huddle(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        persona = agent.get_profile().get("persona", {})
        system = persona.get(
            "system_prompt_template",
            "You are an IPL team leader during a match break."
        )

        situation = context.get("match_situation", {})
        trigger = context.get("trigger", "over_change")

        prompt = (
            f"Team huddle triggered by: {trigger}. "
            f"Score: {situation.get('score', 0)}/{situation.get('wickets', 0)} "
            f"after {situation.get('overs', 0)} overs. "
            f"{'Target: ' + str(situation.get('target', '')) + '. ' if situation.get('target') else ''}"
            f"Pressure: {situation.get('pressure', 0.5):.2f}.\n\n"
            f"Generate 2-3 team messages. Respond with ONLY JSON:\n"
            f"{json.dumps(TEAM_HUDDLE_SCHEMA, indent=2)}"
        )

        try:
            response = await agent.think(prompt=prompt, context=situation, require_llm=True)
            if response:
                parsed = parse_llm_json(response)
                huddle = TeamHuddle(**parsed)
                return huddle.model_dump()
        except Exception as exc:
            logger.warning("Team huddle LLM failed: %s", exc)

        return None

    def _template_huddle(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate template-based team messages for HYBRID mode."""
        trigger = context.get("trigger", "over_change")
        situation = context.get("match_situation", {})
        pressure = situation.get("pressure", 0.5)
        over = situation.get("overs", 10)

        messages = []

        # Pick appropriate strategy template
        if trigger == "timeout":
            if over <= 6:
                strategy = _STRATEGY_TEMPLATES["powerplay_batting"]
            elif over >= 16:
                strategy = _STRATEGY_TEMPLATES["death_batting"]
            else:
                strategy = _STRATEGY_TEMPLATES["middle_overs_batting"]
            messages.append({
                "sender_name": "Coach",
                "sender_role": "coach",
                "recipient": "team",
                "message_type": "strategy",
                "content": strategy,
            })

        if trigger == "wicket":
            messages.append({
                "sender_name": "Captain",
                "sender_role": "captain",
                "recipient": "specific_player",
                "message_type": "instruction",
                "content": _STRATEGY_TEMPLATES["wicket_fallen_batting"],
            })

        # Add encouragement
        if pressure > 0.7:
            messages.append({
                "sender_name": "Teammate",
                "sender_role": "batsman",
                "recipient": "batting_pair",
                "message_type": "encouragement",
                "content": _STRATEGY_TEMPLATES["high_pressure"],
            })
        else:
            messages.append({
                "sender_name": "Teammate",
                "sender_role": "batsman",
                "recipient": "batting_pair",
                "message_type": "encouragement",
                "content": random.choice(_ENCOURAGEMENT_TEMPLATES),
            })

        return {
            "messages": messages,
            "tactical_shift": None,
        }
