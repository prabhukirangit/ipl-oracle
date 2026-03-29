"""
LLMBatch — Over-level batching for LLM calls.

Instead of making 12 LLM calls per over (6 bowling + 6 batting),
batch into 2 calls: one bowling plan and one batting plan for the full over.

This cuts LLM calls by ~80% in PERSONA mode.

Supports partial-over re-plans after mid-over wickets (remaining_balls < 6).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..schemas.llm_outputs import (
    OverBowlingPlan,
    OverBattingPlan,
    OVER_BOWLING_PLAN_SCHEMA,
    OVER_BATTING_PLAN_SCHEMA,
)

logger = logging.getLogger(__name__)


async def batch_bowling_plan(
    bowler_agent: Any,
    over_number: int,
    match_situation: dict[str, Any],
    batsman_profile: dict[str, Any],
    narrative: str,
    remaining_balls: int = 6,
) -> list[dict[str, Any]] | None:
    """
    Ask the bowler for a multi-ball over plan in a single LLM call.

    Args:
        remaining_balls: How many balls to plan (< 6 for re-plans after wickets).

    Returns a list of BowlingDecision dicts, or None on failure.
    """
    persona = bowler_agent.get_profile().get("persona", {})

    balls_text = f"{remaining_balls} ball{'s' if remaining_balls > 1 else ''}"
    replan_note = " (re-planning after wicket — new batsman at the crease)" if remaining_balls < 6 else ""

    prompt = (
        f"{narrative}\n\n"
        f"Plan your next {balls_text}{replan_note} against "
        f"{batsman_profile.get('name', 'the batsman')} "
        f"({batsman_profile.get('batting_style', 'right-hand')}). "
        f"Over {over_number + 1} of 20.\n\n"
        f"Respond with ONLY valid JSON. Include exactly {remaining_balls} deliveries.\n"
        f"Schema:\n{json.dumps(OVER_BOWLING_PLAN_SCHEMA, indent=2)}\n"
        f"No markdown — just the JSON."
    )

    try:
        response = await bowler_agent.think(
            prompt=prompt,
            context=match_situation,
            require_llm=True,
            max_tokens=1024,
        )
        if response:
            parsed = json.loads(response)
            plan = OverBowlingPlan(**parsed)
            return [d.model_dump() for d in plan.deliveries[:remaining_balls]]
    except Exception as exc:
        logger.warning("Batch bowling plan failed for over %d: %s", over_number, exc)

    return None


async def batch_batting_plan(
    batsman_agent: Any,
    over_number: int,
    match_situation: dict[str, Any],
    bowling_plan: list[dict[str, Any]],
    narrative: str,
    remaining_balls: int = 6,
) -> list[dict[str, Any]] | None:
    """
    Ask the batsman for responses to deliveries in a single LLM call.

    Args:
        remaining_balls: How many balls to plan (< 6 for re-plans after wickets).

    Returns a list of BattingDecision dicts, or None on failure.
    """
    deliveries_desc = "\n".join(
        f"  Ball {i+1}: {d.get('delivery_type', '?')} on {d.get('line', '?')}, {d.get('length', '?')}"
        for i, d in enumerate(bowling_plan[:remaining_balls])
    )

    balls_text = f"{remaining_balls} ball{'s' if remaining_balls > 1 else ''}"

    prompt = (
        f"{narrative}\n\n"
        f"You're facing {balls_text} this over. The bowler's plan:\n{deliveries_desc}\n\n"
        f"How do you respond to each delivery?\n\n"
        f"Respond with ONLY valid JSON. Include exactly {remaining_balls} responses.\n"
        f"Schema:\n{json.dumps(OVER_BATTING_PLAN_SCHEMA, indent=2)}\n"
        f"No markdown — just the JSON."
    )

    try:
        response = await batsman_agent.think(
            prompt=prompt,
            context=match_situation,
            require_llm=True,
            max_tokens=1024,
        )
        if response:
            parsed = json.loads(response)
            plan = OverBattingPlan(**parsed)
            return [r.model_dump() for r in plan.responses[:remaining_balls]]
    except Exception as exc:
        logger.warning("Batch batting plan failed for over %d: %s", over_number, exc)

    return None


async def batch_batting_plan_independent(
    batsman_agent: Any,
    over_number: int,
    match_situation: dict[str, Any],
    narrative: str,
    remaining_balls: int = 6,
) -> list[dict[str, Any]] | None:
    """
    Ask the batsman for their over plan WITHOUT knowing the bowling plan.

    This allows concurrent bowler + batsman LLM calls (real batsmen
    walk in with intent before seeing the delivery).

    Returns a list of BattingDecision dicts, or None on failure.
    """
    balls_text = f"{remaining_balls} ball{'s' if remaining_balls > 1 else ''}"

    prompt = (
        f"{narrative}\n\n"
        f"You're facing {balls_text} this over. Plan your approach for each ball — "
        f"what intent, shot selection, and risk level will you bring?\n\n"
        f"Respond with ONLY valid JSON. Include exactly {remaining_balls} responses.\n"
        f"Schema:\n{json.dumps(OVER_BATTING_PLAN_SCHEMA, indent=2)}\n"
        f"No markdown — just the JSON."
    )

    try:
        response = await batsman_agent.think(
            prompt=prompt,
            context=match_situation,
            require_llm=True,
            max_tokens=1024,
        )
        if response:
            parsed = json.loads(response)
            plan = OverBattingPlan(**parsed)
            return [r.model_dump() for r in plan.responses[:remaining_balls]]
    except Exception as exc:
        logger.warning("Batch independent batting plan failed for over %d: %s", over_number, exc)

    return None
