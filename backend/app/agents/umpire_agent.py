"""
UmpireAgent — Models umpire decision tendencies.

Affects:
- LBW decisions (propensity to raise finger)
- Wide threshold (how strict on wide calls)
- No-ball detection (how often no-balls are called)
- DRS overturns (Week 3+)

Week 1: Simple deterministic modifiers.
Week 2: Added rhythm effect (consistent decisions build confidence_boost).
        Added LBW+DRS awareness stub for Week 3.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from .base_agent import BaseAgent


class UmpireAgent(BaseAgent):
    """
    Agent representing a match umpire and their decision tendencies.

    In T20s, umpire decisions on borderline LBWs, wides, and no-balls
    have a measurable effect on match outcomes.

    Week 2 additions:
    - Decision rhythm tracking (last 5 decisions in deque)
    - confidence_boost: increases 0.05 per consistent decision, caps at 0.20
    - get_rhythm_factor(): 1.0 + confidence_boost
    - LBW+DRS awareness stub for Week 3
    """

    # Maximum confidence boost from rhythm
    _MAX_CONFIDENCE_BOOST = 0.20
    # Boost per consistent same-type decision
    _RHYTHM_STEP = 0.05
    # Number of recent decisions tracked
    _RHYTHM_WINDOW = 5

    def __init__(
        self,
        umpire_name: str = "Generic Umpire",
        lbw_propensity: float = 0.5,
        wide_threshold: float = 0.5,
        no_ball_strictness: float = 0.5,
        run_id: str | None = None,
    ) -> None:
        """
        Initialise UmpireAgent.

        Args:
            umpire_name: Umpire's name
            lbw_propensity: How likely to give LBW decisions (0-1, higher = more LBW decisions)
            wide_threshold: How strict on wides (0-1, higher = more wides called)
            no_ball_strictness: How strict on no-balls (0-1, higher = more no-balls called)
            run_id: Simulation run ID
        """
        profile = {
            "name": umpire_name,
            "lbw_propensity": lbw_propensity,
            "wide_threshold": wide_threshold,
            "no_ball_strictness": no_ball_strictness,
        }
        super().__init__(agent_type="umpire", profile=profile, run_id=run_id)

        # Week 2: rhythm tracking
        self._decision_history: deque[dict[str, Any]] = deque(maxlen=self._RHYTHM_WINDOW)
        self._confidence_boost: float = 0.0

    # ------------------------------------------------------------------
    # Core decision access
    # ------------------------------------------------------------------

    def get_lbw_propensity(self) -> float:
        """Return effective LBW decision tendency including rhythm factor."""
        base = self._profile.get("lbw_propensity", 0.5)
        return min(1.0, base + self._confidence_boost * 0.1)

    def get_wide_threshold(self) -> float:
        """Return wide call strictness (0-1)."""
        return self._profile.get("wide_threshold", 0.5)

    def get_no_ball_strictness(self) -> float:
        """Return no-ball detection strictness (0-1)."""
        return self._profile.get("no_ball_strictness", 0.5)

    # ------------------------------------------------------------------
    # Rhythm effect (Week 2)
    # ------------------------------------------------------------------

    def update_decision_rhythm(self, decision_type: str, was_correct: bool) -> None:
        """
        Record a decision and update the confidence boost.

        Consistent decisions of the same type build confidence (rhythm effect).
        An incorrect or different-type decision breaks the rhythm and resets.

        Args:
            decision_type: Type of decision made (e.g. 'lbw_out', 'wide', 'not_out', 'no_ball')
            was_correct: Whether the decision was upheld (not overturned by DRS/review)
        """
        # Record the decision
        entry = {"type": decision_type, "correct": was_correct}
        self._decision_history.append(entry)

        # Recompute confidence_boost from the last N decisions
        self._recompute_confidence_boost()

        self.log_decision(
            "rhythm_update",
            decision_type,
            reasoning=f"was_correct={was_correct}, boost={self._confidence_boost:.2f}",
            context={"decision_type": decision_type, "was_correct": was_correct, "boost": self._confidence_boost},
        )

    def _recompute_confidence_boost(self) -> None:
        """
        Recompute confidence_boost from recent decision history.

        Logic:
        - Count consecutive same-type correct decisions in the history
        - Each such streak decision adds _RHYTHM_STEP to boost
        - Capped at _MAX_CONFIDENCE_BOOST
        - Incorrect decisions or type-changes reduce the streak
        """
        if not self._decision_history:
            self._confidence_boost = 0.0
            return

        # Find longest consistent streak at the end of the deque
        history = list(self._decision_history)
        streak = 0
        last_type = history[-1]["type"]

        for entry in reversed(history):
            if entry["type"] == last_type and entry["correct"]:
                streak += 1
            else:
                break

        # Minimum 3 consecutive to start building boost
        if streak >= 3:
            self._confidence_boost = min(
                self._MAX_CONFIDENCE_BOOST,
                (streak - 2) * self._RHYTHM_STEP,
            )
        else:
            self._confidence_boost = 0.0

    def get_rhythm_factor(self) -> float:
        """
        Return the rhythm-based decision confidence multiplier.

        1.0 = no rhythm / baseline
        1.05–1.20 = increasingly consistent umpire (after 3+ consistent decisions)

        Returns:
            Float: 1.0 + confidence_boost (range 1.0–1.20)
        """
        return 1.0 + self._confidence_boost

    def get_decision_rhythm_info(self) -> dict[str, Any]:
        """Return current rhythm state for debugging/audit."""
        history = list(self._decision_history)
        return {
            "recent_decisions": history,
            "confidence_boost": self._confidence_boost,
            "rhythm_factor": self.get_rhythm_factor(),
            "decision_count": len(history),
        }

    # ------------------------------------------------------------------
    # LBW + DRS awareness stub (Week 3)
    # ------------------------------------------------------------------

    def evaluate_lbw_decision(
        self,
        ball_pitching: str,
        impact_zone: str,
        projected_path: str,
        umpire_out_call: bool,
    ) -> dict[str, Any]:
        """
        Stub: Evaluate an LBW decision considering DRS ball-tracking.

        Week 3 will implement full ball-tracking logic.
        Currently returns the on-field decision with a review probability.

        Args:
            ball_pitching: 'in_line', 'outside_off', 'outside_leg'
            impact_zone: 'in_line', 'outside_off', 'outside_leg'
            projected_path: 'hitting_stumps', 'missing_leg', 'missing_off'
            umpire_out_call: Whether the umpire originally gave it out

        Returns:
            Dict with: decision (bool), drs_overturn_probability (float), notes (str)
        """
        # Basic eligibility check: DRS cannot overturn if pitched outside leg
        drs_eligible = ball_pitching != "outside_leg"

        # Rough overturn probability based on impact and projection
        overturn_prob = 0.0
        if drs_eligible and projected_path == "hitting_stumps" and impact_zone == "in_line":
            overturn_prob = 0.05  # very low — umpire probably right
        elif drs_eligible and projected_path == "missing_leg":
            overturn_prob = 0.35 if umpire_out_call else 0.10
        elif drs_eligible and impact_zone == "outside_off":
            overturn_prob = 0.45 if umpire_out_call else 0.08

        return {
            "on_field_decision": umpire_out_call,
            "final_decision": umpire_out_call,  # Week 3: apply DRS simulation
            "drs_overturn_probability": overturn_prob,
            "drs_eligible": drs_eligible,
            "notes": "Week 3: full DRS ball-tracking simulation not yet enabled",
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def umpire_name(self) -> str:
        return self._profile.get("name", "Unknown Umpire")

    @property
    def confidence_boost(self) -> float:
        return self._confidence_boost

    def __repr__(self) -> str:
        return (
            f"UmpireAgent(name={self.umpire_name!r}, "
            f"rhythm={self.get_rhythm_factor():.2f}, "
            f"run_id={self._run_id[:8]!r})"
        )
