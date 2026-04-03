"""
OutcomeResolver — Maps LLM intent decisions to probabilistic ball outcomes.

Core principle: LLM decides INTENT, probability decides OUTCOME.

The batsman's BattingDecision (intent, shot, risk) and the bowler's
BowlingDecision (delivery, line, length) interact through a matchup matrix
that adjusts the base probability weights. The outcome is then sampled.

Examples:
  - Batsman "slog" vs bowler "yorker" → high wicket probability
  - Batsman "defend" vs "bouncer" → mostly dot ball
  - Batsman "attack off_side" vs "wide_outside_off" → higher boundary probability
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from ..agents.player_agent import BallOutcome


# ---------------------------------------------------------------------------
# Matchup matrices: how batting intent vs bowling delivery affect outcomes
# ---------------------------------------------------------------------------

# Modifiers to base weights: (dot, single, two, three, boundary, six, wicket)
# Positive = increases probability; negative = decreases

_INTENT_MODIFIERS: dict[str, dict[str, float]] = {
    "attack": {
        "dot": -0.05, "single": -0.03, "two": 0.01, "three": 0.005,
        "boundary": 0.04, "six": 0.02, "wicket": 0.015,
    },
    "rotate": {
        "dot": -0.03, "single": 0.05, "two": 0.02, "three": 0.01,
        "boundary": -0.02, "six": -0.02, "wicket": -0.01,
    },
    "defend": {
        "dot": 0.08, "single": 0.02, "two": -0.02, "three": -0.01,
        "boundary": -0.04, "six": -0.03, "wicket": -0.02,
    },
    "slog": {
        "dot": -0.06, "single": -0.06, "two": -0.02, "three": 0.0,
        "boundary": 0.05, "six": 0.06, "wicket": 0.04,
    },
}

# How delivery type modifies outcome when matched with batting intent
_DELIVERY_MODIFIERS: dict[str, dict[str, float]] = {
    "yorker": {
        "dot": 0.05, "single": 0.01, "boundary": -0.02, "six": -0.03, "wicket": 0.02,
    },
    "bouncer": {
        "dot": 0.03, "boundary": 0.01, "six": -0.01, "wicket": 0.02,
    },
    "slower_ball": {
        "dot": 0.02, "six": -0.02, "wicket": 0.015, "boundary": -0.01,
    },
    "knuckle_ball": {
        "dot": 0.03, "six": -0.02, "wicket": 0.02,
    },
    "wide_yorker": {
        "dot": 0.04, "wicket": 0.015, "boundary": -0.02, "six": -0.03,
    },
    "googly": {
        "dot": 0.02, "wicket": 0.025, "six": -0.02, "boundary": -0.01,
    },
    "carrom_ball": {
        "dot": 0.02, "wicket": 0.02, "six": -0.015,
    },
    "outswinger": {
        "dot": 0.02, "wicket": 0.015, "boundary": -0.01,
    },
    "inswinger": {
        "dot": 0.01, "wicket": 0.02, "boundary": -0.01,
    },
    # Default for all other deliveries: no extra modifier
}

# Intent vs delivery INTERACTION modifiers (specific matchups)
_MATCHUP_INTERACTIONS: dict[tuple[str, str], dict[str, float]] = {
    # Slog against yorker = very risky
    ("slog", "yorker"): {"wicket": 0.06, "six": -0.04, "dot": 0.03},
    ("slog", "wide_yorker"): {"wicket": 0.05, "six": -0.03, "dot": 0.02},
    # Slog against bouncer = top-edge or six
    ("slog", "bouncer"): {"wicket": 0.03, "six": 0.03, "boundary": 0.01},
    # Defend against bouncer = safe
    ("defend", "bouncer"): {"dot": 0.06, "wicket": -0.02},
    # Attack against full delivery = rewarding
    ("attack", "stock_delivery"): {"boundary": 0.02, "six": 0.01},
    ("attack", "overpitched"): {"boundary": 0.04, "six": 0.02},
    # Rotate against tight bowling = difficult
    ("rotate", "yorker"): {"dot": 0.04, "single": -0.02},
    # Slog against slower ball = deception
    ("slog", "slower_ball"): {"wicket": 0.04, "six": -0.02, "boundary": -0.01},
    # Attack against googly = risky
    ("attack", "googly"): {"wicket": 0.03, "boundary": -0.01},
}


# Base weights (same as PlayerAgent.BASE_BATTING_WEIGHTS)
BASE_WEIGHTS = {
    "dot": 0.34,
    "single": 0.34,
    "two": 0.08,
    "three": 0.015,
    "boundary": 0.13,
    "six": 0.04,
    "wicket": 0.055,
}


# ---------------------------------------------------------------------------
# Confidence and risk modifiers
# ---------------------------------------------------------------------------

def _apply_confidence_modifier(weights: dict[str, float], batting_conf: float, bowling_conf: float) -> None:
    """High batting confidence reduces wicket chance; high bowling confidence increases it."""
    conf_diff = batting_conf - bowling_conf  # positive = batsman dominant

    # Batsman confident → fewer dots/wickets, more scoring
    weights["wicket"] += (-0.02 * conf_diff)
    weights["dot"] += (-0.03 * conf_diff)
    weights["boundary"] += (0.02 * conf_diff)
    weights["single"] += (0.01 * conf_diff)


def _apply_risk_modifier(weights: dict[str, float], risk_appetite: float) -> None:
    """Higher risk → more extremes (more sixes AND more wickets)."""
    risk_shift = risk_appetite - 0.5  # centered around 0.5
    weights["six"] += 0.04 * risk_shift
    weights["boundary"] += 0.03 * risk_shift
    weights["wicket"] += 0.025 * risk_shift
    weights["dot"] -= 0.04 * risk_shift
    weights["single"] -= 0.03 * risk_shift


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def resolve_persona_outcome(
    batting_decision: dict[str, Any],
    bowling_decision: dict[str, Any],
    ball_context: dict[str, Any],
    rng: random.Random | None = None,
) -> BallOutcome:
    """
    Resolve a ball outcome from LLM intent decisions.

    Takes the batting and bowling decisions (from LLM or heuristic) and
    produces a probabilistic BallOutcome through the matchup matrix.

    Applies 7 modifier layers:
      1. Batting intent (attack/rotate/defend/slog)
      2. Delivery type (yorker/bouncer/googly/etc.)
      3. Intent x delivery interaction matchups
      4. Confidence differential (batsman vs bowler)
      5. Risk appetite scaling
      6. Ball context (pressure, dew, boundary asymmetry)
      7. Experience modifier (veterans more clinical)

    Args:
        batting_decision: BattingDecision as dict
        bowling_decision: BowlingDecision as dict
        ball_context: Match state dict (may include batsman_experience_years)
        rng: Random instance for reproducibility

    Returns:
        BallOutcome with runs, wicket status, and narrative.
    """
    rng = rng or random.Random()

    # Start with base weights
    weights = dict(BASE_WEIGHTS)

    # 1. Apply batting intent modifier
    intent = batting_decision.get("intent", "rotate")
    intent_mods = _INTENT_MODIFIERS.get(intent, {})
    for key, mod in intent_mods.items():
        weights[key] = weights.get(key, 0) + mod

    # 2. Apply delivery type modifier
    delivery = bowling_decision.get("delivery_type", "stock_delivery")
    delivery_mods = _DELIVERY_MODIFIERS.get(delivery, {})
    for key, mod in delivery_mods.items():
        weights[key] = weights.get(key, 0) + mod

    # 3. Apply intent × delivery interaction
    interaction_mods = _MATCHUP_INTERACTIONS.get((intent, delivery), {})
    for key, mod in interaction_mods.items():
        weights[key] = weights.get(key, 0) + mod

    # 4. Apply confidence and risk modifiers
    batting_conf = batting_decision.get("confidence", 0.5)
    bowling_conf = bowling_decision.get("confidence", 0.5)
    risk = batting_decision.get("risk_appetite", 0.5)

    _apply_confidence_modifier(weights, batting_conf, bowling_conf)
    _apply_risk_modifier(weights, risk)

    # 5. Apply ball context modifiers (pressure, dew, boundary asymmetry)
    pressure = ball_context.get("pressure_index", 0.3)
    if pressure > 0.7:
        weights["wicket"] += 0.015 * (pressure - 0.7)
        weights["dot"] += 0.02 * (pressure - 0.7)

    dew = ball_context.get("dew_factor", 1.0)
    if dew < 0.85:
        # Dew helps batsman against spin
        weights["boundary"] += 0.02 * (1.0 - dew)
        weights["dot"] -= 0.01 * (1.0 - dew)

    asymmetry = ball_context.get("boundary_asymmetry_factor", 1.0)
    weights["boundary"] *= asymmetry
    weights["six"] *= asymmetry

    # 6. Experience modifier: veterans are more clinical in persona mode
    #    This uses ball_context which may carry experience info from the batsman
    exp_years = ball_context.get("batsman_experience_years", 5)
    if exp_years >= 10:
        weights["wicket"] -= 0.01
        weights["single"] += 0.005
    elif exp_years <= 2:
        weights["wicket"] += 0.008

    # 7. Apply field placement interception — matches probabilistic path logic
    #    CaptainAgent sets fielders; boundaries hit toward occupied positions
    #    get intercepted (caught/dot/single instead of 4).
    field = ball_context.get("field_state")
    if field and isinstance(field, dict):
        # Count deep fielders — more fielders = harder to find gaps
        deep_count = sum(1 for k in [
            "deep_third_man", "deep_fine_leg", "deep_point", "deep_cover",
            "long_off", "long_on", "deep_midwicket", "deep_square_leg",
        ] if field.get(k))
        # Each deep fielder reduces boundary probability slightly
        if deep_count >= 4:
            boundary_suppress = 0.015 * deep_count  # 0.06–0.12 penalty
            weights["boundary"] -= boundary_suppress
            weights["dot"] += boundary_suppress * 0.4
            weights["single"] += boundary_suppress * 0.4
            weights["wicket"] += boundary_suppress * 0.2  # caught in the deep

    # 8. Clamp and normalize
    for key in weights:
        weights[key] = max(0.001, weights[key])

    outcomes = list(weights.keys())
    probs = [weights[k] for k in outcomes]
    total = sum(probs)
    normalized = [p / total for p in probs]

    # 9. Sample outcome
    outcome_key = rng.choices(outcomes, weights=normalized, k=1)[0]

    # 10. Resolve to BallOutcome
    runs = 0
    is_wicket = False
    is_boundary = False
    is_six = False
    dismissal_type = None

    if outcome_key == "dot":
        runs = 0
    elif outcome_key == "single":
        runs = 1
    elif outcome_key == "two":
        runs = 2
    elif outcome_key == "three":
        runs = 3
    elif outcome_key == "boundary":
        runs = 4
        is_boundary = True
    elif outcome_key == "six":
        runs = 6
        is_six = True
    elif outcome_key == "wicket":
        is_wicket = True
        dismissal_type = rng.choice(["caught", "bowled", "lbw", "stumped", "run_out"])

    # 11. Post-sample field interception — specific shot-to-fielder matchups
    #     (mirrors PlayerAgent.bat() interception logic)
    shot = batting_decision.get("shot_selection", "shot")
    target = batting_decision.get("target_zone", "")

    if field and isinstance(field, dict) and outcome_key in ("boundary", "three", "two"):
        intercepted = False
        if shot in ("drive", "lofted_drive", "cover_drive", "straight_drive") and (field.get("long_off") or field.get("deep_cover")):
            intercepted = True
        elif shot in ("pull", "slog", "slog_sweep", "hook") and field.get("deep_square_leg"):
            intercepted = True
        elif shot in ("cut", "upper_cut", "late_cut") and field.get("deep_point"):
            intercepted = True
        elif shot in ("flick", "glance", "paddle") and field.get("deep_fine_leg"):
            intercepted = True
        elif shot in ("sweep", "reverse_sweep") and (field.get("deep_square_leg") or field.get("deep_fine_leg")):
            intercepted = True

        if intercepted:
            roll = rng.random()
            if roll < 0.2:
                # Caught in the deep
                outcome_key = "wicket"
                is_wicket = True
                is_boundary = False
                runs = 0
                dismissal_type = "caught"
                shot = f"{shot} (caught in the deep)"
            elif roll < 0.5:
                # Fielder cuts it off — dot ball
                outcome_key = "dot"
                is_boundary = False
                runs = 0
                shot = f"{shot} (intercepted)"
            else:
                # Single — fielder's throw keeps it to one
                outcome_key = "single"
                is_boundary = False
                runs = 1
                shot = f"{shot} (cut off)"

    if is_wicket:
        notes = (
            f"OUT! {dismissal_type}. Tried a {shot} to {target} "
            f"against the {delivery} — didn't come off."
        )
    elif is_six:
        notes = f"SIX! {shot} to {target} — sent the {delivery} into the stands!"
    elif is_boundary:
        notes = f"FOUR! {shot} to {target} — perfectly placed against the {delivery}."
    elif runs == 0:
        notes = f"Dot ball. {delivery} beats the {shot} — no run."
    else:
        notes = f"{runs} run{'s' if runs > 1 else ''}. {shot} to {target} off the {delivery}."

    inner = batting_decision.get("inner_monologue", "")
    if inner:
        notes = f"{notes} [{inner}]"

    return BallOutcome(
        runs=runs,
        is_wicket=is_wicket,
        is_wide=False,
        is_no_ball=False,
        is_boundary=is_boundary,
        is_six=is_six,
        dismissal_type=dismissal_type,
        shot_type=shot,
        delivery_type=delivery,
        pressure_index=ball_context.get("pressure_index", 0),
        confidence=batting_conf,
        notes=notes,
    )
