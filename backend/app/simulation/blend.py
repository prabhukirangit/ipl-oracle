"""
CatBoost + Simulation blending function.

All three modes use the same 70/30 split:
  final_win_pct = 0.70 * sim_win_pct + 0.30 * catboost_prob

Called once per simulation run using the aggregated sim win probability
and the CatBoost prediction for the match setup.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CB_WEIGHT = 0.30
SIM_WEIGHT = 0.70


def blend_with_catboost(
    sim_win_prob: float,
    cb_win_prob: float,
    mode: str = "hybrid",
) -> float:
    """
    Blend simulation win probability with CatBoost prediction.

    Args:
        sim_win_prob: Simulation-derived P(team wins) in [0, 1].
        cb_win_prob: CatBoost-derived P(team wins) in [0, 1].
        mode: Simulation mode (for logging only — weights are identical).

    Returns:
        Blended win probability in [0, 1].
    """
    blended = (SIM_WEIGHT * sim_win_prob) + (CB_WEIGHT * cb_win_prob)
    logger.debug(
        "Blend [%s]: sim=%.3f * %.2f + cb=%.3f * %.2f = %.3f",
        mode, sim_win_prob, SIM_WEIGHT, cb_win_prob, CB_WEIGHT, blended,
    )
    return blended
