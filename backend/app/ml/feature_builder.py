"""
Feature builder for CatBoost win-probability model.

Single source of truth: used identically in training AND inference.
Never derive features in two places.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Column lists — kept in one place so trainer + predictor stay in sync
# ---------------------------------------------------------------------------

NUMERIC_FEATURES = [
    "over", "ball_no", "innings",
    "team_runs", "team_balls", "team_wicket",
    "balls_remaining", "wickets_in_hand",
    "current_run_rate", "required_run_rate",
    "run_rate_diff", "pressure_index",
    "phase", "is_innings_2", "balls_into_innings", "runs_target",
]

CAT_FEATURES = [
    "batting_team", "bowling_team",
    "venue",
    "toss_winner", "toss_decision",
    "month",
    "batter", "bowler",
]

ALL_FEATURES = NUMERIC_FEATURES + CAT_FEATURES

# Columns that leak future ball-level outcome info — must never be features
_LEAKY_COLS = {
    "runs_batter", "runs_extras", "runs_total",
    "wicket_kind", "player_out", "fielders",
    "match_id", "date", "match_won_by",
}

ALLOWED_SEASONS = {"2020/21", "2021", "2022", "2023", "2024", "2025"}


# ---------------------------------------------------------------------------
# Training: build features from the full DataFrame
# ---------------------------------------------------------------------------

def build(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Build feature matrix + label from raw ball-by-ball DataFrame.

    Returns:
        (X, y) where X has ALL_FEATURES columns and y is binary (1 = batting team won).
    """
    df = df.copy()

    # Derived numeric features
    df["balls_remaining"] = (120 - df["ball_no"]).clip(lower=0)
    df["wickets_in_hand"] = 10 - df["team_wicket"]
    df["current_run_rate"] = df["team_runs"] / df["team_balls"].clip(lower=1) * 6
    df["runs_target"] = df["runs_target"].fillna(0).astype(float)
    df["balls_remaining"] = df["balls_remaining"].astype(float)

    # Required run rate — only meaningful in innings 2
    df["required_run_rate"] = 0.0
    inn2 = df["innings"] == 2
    df.loc[inn2, "required_run_rate"] = (
        (df.loc[inn2, "runs_target"] - df.loc[inn2, "team_runs"])
        / df.loc[inn2, "balls_remaining"].clip(lower=1) * 6
    )

    df["run_rate_diff"] = df["current_run_rate"] - df["required_run_rate"]

    # Pressure index — ratio of required to current RR (innings 2), 1.0 for innings 1
    df["pressure_index"] = 1.0
    df.loc[inn2, "pressure_index"] = (
        df.loc[inn2, "required_run_rate"] / df.loc[inn2, "current_run_rate"].clip(lower=0.1)
    )

    # Phase: 1=powerplay, 2=middle, 3=death
    df["phase"] = 2
    df.loc[df["over"] <= 5, "phase"] = 1
    df.loc[df["over"] >= 16, "phase"] = 3

    df["is_innings_2"] = (df["innings"] == 2).astype(int)
    df["balls_into_innings"] = df["ball_no"].astype(float)

    # Categorical: month as string
    df["month"] = df["month"].astype(str)

    # Fill any NaN categoricals
    for col in CAT_FEATURES:
        df[col] = df[col].fillna("Unknown").astype(str)

    # Label: 1 if batting_team == match_won_by
    y = (df["batting_team"] == df["match_won_by"]).astype(int)

    X = df[ALL_FEATURES].copy()

    # Ensure numeric columns are float
    for col in NUMERIC_FEATURES:
        X[col] = X[col].astype(float)

    return X, y


# ---------------------------------------------------------------------------
# Inference: build a single feature vector from live match state
# ---------------------------------------------------------------------------

def build_single(match_state: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a live match state dict to the feature dict CatBoost expects.

    Expected keys in match_state:
        current_over, ball_no, innings,
        team_runs, team_balls, team_wicket,
        runs_target (None for innings 1),
        batting_team, bowling_team, venue,
        toss_winner, toss_decision (None if unknown),
        match_month (int: 3, 4, or 5),
        current_batter, current_bowler (None if unset)
    """
    over = match_state.get("current_over", 0)
    ball_no = match_state.get("ball_no", 0)
    innings = match_state.get("innings", 1)
    team_runs = match_state.get("team_runs", 0)
    team_balls = match_state.get("team_balls", 0)
    team_wicket = match_state.get("team_wicket", 0)
    runs_target = match_state.get("runs_target") or 0

    balls_remaining = max(0, 120 - ball_no)
    wickets_in_hand = 10 - team_wicket
    current_run_rate = (team_runs / max(team_balls, 1)) * 6

    if innings == 2 and balls_remaining > 0:
        required_run_rate = ((runs_target - team_runs) / max(balls_remaining, 1)) * 6
    else:
        required_run_rate = 0.0

    run_rate_diff = current_run_rate - required_run_rate

    if innings == 2 and current_run_rate > 0.1:
        pressure_index = required_run_rate / current_run_rate
    else:
        pressure_index = 1.0

    phase = 1 if over <= 5 else (3 if over >= 16 else 2)
    is_innings_2 = 1 if innings == 2 else 0

    features = {
        # Numeric
        "over": float(over),
        "ball_no": float(ball_no),
        "innings": float(innings),
        "team_runs": float(team_runs),
        "team_balls": float(team_balls),
        "team_wicket": float(team_wicket),
        "balls_remaining": float(balls_remaining),
        "wickets_in_hand": float(wickets_in_hand),
        "current_run_rate": float(current_run_rate),
        "required_run_rate": float(required_run_rate),
        "run_rate_diff": float(run_rate_diff),
        "pressure_index": float(pressure_index),
        "phase": float(phase),
        "is_innings_2": float(is_innings_2),
        "balls_into_innings": float(ball_no),
        "runs_target": float(runs_target),
        # Categorical
        "batting_team": str(match_state.get("batting_team") or "Unknown"),
        "bowling_team": str(match_state.get("bowling_team") or "Unknown"),
        "venue": str(match_state.get("venue") or "Unknown"),
        "toss_winner": str(match_state.get("toss_winner") or "Unknown"),
        "toss_decision": str(match_state.get("toss_decision") or "Unknown"),
        "month": str(match_state.get("match_month") or "Unknown"),
        "batter": str(match_state.get("current_batter") or "Unknown"),
        "bowler": str(match_state.get("current_bowler") or "Unknown"),
    }

    return features
