"""
Structured output schemas for LLM persona decisions.

All LLM calls in PERSONA and HYBRID mode must return JSON conforming to these
Pydantic models. The system prompt includes the schema; the response is parsed
and validated before it reaches the outcome resolver.

Design rule: LLM decides INTENT, probability decides OUTCOME.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Batting
# ---------------------------------------------------------------------------

class BattingDecision(BaseModel):
    """What the batsman intends to do on this ball."""

    intent: Literal["attack", "rotate", "defend", "slog"] = Field(
        description="High-level batting intent for this delivery",
    )
    shot_selection: str = Field(
        description=(
            "Specific shot attempted, e.g. 'cover_drive', 'pull', 'sweep', "
            "'reverse_sweep', 'straight_drive', 'flick', 'cut', 'slog_sweep', "
            "'leave', 'block', 'paddle', 'upper_cut', 'lofted_drive'"
        ),
    )
    target_zone: Literal[
        "off_side", "leg_side", "straight", "fine_leg",
        "third_man", "cover", "midwicket", "square_leg",
        "long_on", "long_off",
    ] = Field(
        description="Where the batsman is targeting the ball",
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="How confident the batsman feels about executing this shot (0=unsure, 1=certain)",
    )
    risk_appetite: float = Field(
        ge=0.0, le=1.0,
        description="Willingness to take risk on this ball (0=ultra-safe, 1=all-out attack)",
    )
    reasoning: str = Field(
        max_length=500,
        description="1-2 sentence tactical reasoning in character",
    )
    inner_monologue: str = Field(
        max_length=500,
        description="What the cricketer is thinking — for narrative/commentary use",
    )


# ---------------------------------------------------------------------------
# Bowling
# ---------------------------------------------------------------------------

class BowlingDecision(BaseModel):
    """What the bowler intends to deliver on this ball."""

    delivery_type: str = Field(
        description=(
            "Type of delivery, e.g. 'yorker', 'bouncer', 'slower_ball', "
            "'leg_cutter', 'off_cutter', 'outswinger', 'inswinger', "
            "'googly', 'top_spinner', 'arm_ball', 'carrom_ball', "
            "'stock_delivery', 'knuckle_ball', 'wide_yorker'"
        ),
    )
    line: Literal[
        "off_stump", "middle", "leg_stump",
        "wide_outside_off", "wide_down_leg",
        "fourth_stump",
    ] = Field(
        description="Line of the delivery",
    )
    length: Literal[
        "full", "good_length", "short", "yorker_length",
        "back_of_a_length", "overpitched",
    ] = Field(
        description="Length of the delivery",
    )
    variation: str | None = Field(
        default=None,
        description="Optional variation: 'wobble_seam', 'cross_seam', 'change_of_pace', etc.",
    )
    field_setup_hint: Literal["attacking", "defensive", "spread", "slip_cordon"] = Field(
        default="attacking",
        description="Broad field setup hint for this delivery",
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="How confident the bowler is about executing this delivery",
    )
    reasoning: str = Field(
        max_length=500,
        description="1-2 sentence tactical reasoning in character",
    )
    inner_monologue: str = Field(
        max_length=500,
        description="What the bowler is thinking — for narrative/commentary use",
    )


# ---------------------------------------------------------------------------
# Over-level batch plans (cost optimisation — 1 call for 6 balls)
# ---------------------------------------------------------------------------

class OverBowlingPlan(BaseModel):
    """Bowler's plan for all 6 balls of an over."""

    deliveries: list[BowlingDecision] = Field(
        min_length=1, max_length=6,
        description="Plan for each ball in the over (1-6 balls; fewer after mid-over wickets)",
    )
    over_strategy: str = Field(
        max_length=500,
        description="Overall strategy for this over in 1-2 sentences",
    )


class OverBattingPlan(BaseModel):
    """Batsman's intent for all 6 balls of an over (given the bowling plan context)."""

    responses: list[BattingDecision] = Field(
        min_length=1, max_length=6,
        description="Intended response to each delivery (1-6 balls; fewer after mid-over wickets)",
    )
    over_intent: str = Field(
        max_length=500,
        description="Overall batting intent for this over in 1-2 sentences",
    )


# ---------------------------------------------------------------------------
# Communication
# ---------------------------------------------------------------------------

class CommunicationMessage(BaseModel):
    """A message from one agent to another within a team."""

    sender_name: str = Field(description="Who is speaking")
    sender_role: Literal[
        "captain", "coach", "batsman", "bowler",
        "non_striker", "wicketkeeper", "allrounder",
    ] = Field(description="Role of the sender")
    recipient: Literal[
        "team", "batting_pair", "bowling_unit",
        "specific_player",
    ] = Field(description="Who the message is for")
    recipient_name: str | None = Field(
        default=None,
        description="Specific player name if recipient is 'specific_player'",
    )
    message_type: Literal[
        "strategy", "encouragement", "instruction",
        "field_change", "warning", "celebration",
    ] = Field(description="Nature of the communication")
    content: str = Field(
        max_length=300,
        description="The actual message content, in character",
    )


class TeamHuddle(BaseModel):
    """Multi-message team communication at a break point (timeout, over change, wicket)."""

    messages: list[CommunicationMessage] = Field(
        min_length=1, max_length=5,
        description="Messages exchanged during this huddle",
    )
    tactical_shift: str | None = Field(
        default=None,
        max_length=500,
        description="If the team is changing strategy, describe the shift",
    )


# ---------------------------------------------------------------------------
# JSON schema strings (injected into LLM system prompts)
# ---------------------------------------------------------------------------

BATTING_DECISION_SCHEMA = BattingDecision.model_json_schema()
BOWLING_DECISION_SCHEMA = BowlingDecision.model_json_schema()
OVER_BOWLING_PLAN_SCHEMA = OverBowlingPlan.model_json_schema()
OVER_BATTING_PLAN_SCHEMA = OverBattingPlan.model_json_schema()
COMMUNICATION_MESSAGE_SCHEMA = CommunicationMessage.model_json_schema()
TEAM_HUDDLE_SCHEMA = TeamHuddle.model_json_schema()
