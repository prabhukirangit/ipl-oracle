"""
PitchAgent — Deterministic over-by-over pitch evolution agent.

Models how pitch conditions change through a T20 innings:
- Early overs: pace-friendly, some grass
- Middle overs: pitch flattens, becomes batting-friendly
- Later overs: spinners may get grip; pitch wear affects bounce

No randomness — all outputs are deterministic functions of over number
and pitch type. Pitch type is set at match start from venue data.
"""

from __future__ import annotations

from typing import Any

from .base_agent import BaseAgent


# ---------------------------------------------------------------------------
# Pitch type evolution tables
# ---------------------------------------------------------------------------

# Over-indexed condition tables. Key: over number (0-19), Value: condition modifiers.
# Each table defines how a pitch type evolves ball by ball.

PITCH_EVOLUTIONS: dict[str, dict] = {
    "batting_friendly": {
        "base_batting_ease": 0.72,
        "early_pace_bonus": 0.10,   # overs 0-3
        "middle_batting_boost": 0.12,  # overs 7-14
        "late_wear_factor": 0.05,   # overs 15-19 (minimal degradation)
        "spin_growth_rate": 0.008,  # spin effectiveness growth per over
        "pace_decay_rate": 0.015,   # pace effectiveness decay per over
    },
    "batting_paradise": {
        "base_batting_ease": 0.85,
        "early_pace_bonus": 0.05,
        "middle_batting_boost": 0.15,
        "late_wear_factor": 0.03,
        "spin_growth_rate": 0.005,
        "pace_decay_rate": 0.010,
    },
    "spin_friendly": {
        "base_batting_ease": 0.52,
        "early_pace_bonus": 0.15,   # some early pace movement
        "middle_batting_boost": 0.05,
        "late_wear_factor": 0.15,   # significant wear helps spinners
        "spin_growth_rate": 0.020,
        "pace_decay_rate": 0.018,
    },
    "pace_friendly": {
        "base_batting_ease": 0.48,
        "early_pace_bonus": 0.25,   # strong early pace movement
        "middle_batting_boost": 0.08,
        "late_wear_factor": 0.10,
        "spin_growth_rate": 0.012,
        "pace_decay_rate": 0.008,   # pace stays effective longer
    },
    "balanced": {
        "base_batting_ease": 0.60,
        "early_pace_bonus": 0.15,
        "middle_batting_boost": 0.10,
        "late_wear_factor": 0.08,
        "spin_growth_rate": 0.015,
        "pace_decay_rate": 0.012,
    },
}


class PitchAgent(BaseAgent):
    """
    Deterministic agent modelling over-by-over pitch evolution.

    Pitch condition is computed from:
    - Pitch type (from venue profile)
    - Over number (wear and tear accumulates)
    - Innings number (second innings pitch is more worn)

    All outputs are deterministic — given the same inputs, the same
    condition dict is always returned.
    """

    def __init__(
        self,
        pitch_type: str = "balanced",
        venue_name: str = "Unknown Venue",
        run_id: str | None = None,
    ) -> None:
        """
        Initialise PitchAgent.

        Args:
            pitch_type: One of the PITCH_EVOLUTIONS keys
            venue_name: Venue name for logging
            run_id: Simulation run ID
        """
        # Validate pitch type, fall back to balanced
        if pitch_type not in PITCH_EVOLUTIONS:
            pitch_type = "balanced"

        profile = {
            "pitch_type": pitch_type,
            "venue_name": venue_name,
            "evolution_params": PITCH_EVOLUTIONS[pitch_type],
        }
        super().__init__(agent_type="pitch", profile=profile, run_id=run_id)
        self._pitch_type = pitch_type
        self._evolution = PITCH_EVOLUTIONS[pitch_type]

    @classmethod
    def from_venue(cls, venue_name: str, pitch_type: str, run_id: str | None = None) -> "PitchAgent":
        """Create a PitchAgent for a specific venue."""
        return cls(pitch_type=pitch_type, venue_name=venue_name, run_id=run_id)

    # ------------------------------------------------------------------
    # Core condition methods
    # ------------------------------------------------------------------

    def get_condition(self, over_number: int, innings: int = 1) -> dict[str, float]:
        """
        Return the pitch condition dict for a given over and innings.

        Pitch evolves as:
        1. Early overs (0-5): pace-friendly, some grass/moisture
        2. Middle overs (6-14): pitch flattens, batting gets easier
        3. Death overs (15-19): wear and tear, spinners may help; pitch can get inconsistent

        Args:
            over_number: Current over (0-19)
            innings: Innings number (1 or 2). Second innings pitch is more worn.

        Returns:
            Dict with: batting_ease, pace_effectiveness, spin_effectiveness,
                       bounce_consistency, swing_availability, turn_available
        """
        evo = self._evolution
        base_ease = evo["base_batting_ease"]

        # Phase-based adjustments
        if over_number <= 3:
            # Early: pace helps, batting harder
            phase_batting_mod = -0.10
            pace_eff = 0.70 + evo["early_pace_bonus"]
            spin_eff = 0.25
            swing_available = True
            bounce_consistency = 0.85
        elif over_number <= 6:
            # Powerplay end: transitioning
            phase_batting_mod = -0.05
            pace_eff = 0.65 + evo["early_pace_bonus"] * 0.5
            spin_eff = 0.30
            swing_available = True
            bounce_consistency = 0.82
        elif over_number <= 10:
            # Middle: pitch flattens
            phase_batting_mod = 0.05
            pace_eff = 0.55 - (over_number - 6) * evo["pace_decay_rate"]
            spin_eff = 0.40 + (over_number - 6) * evo["spin_growth_rate"]
            swing_available = False
            bounce_consistency = 0.80
        elif over_number <= 14:
            # Late middle: batting paradise
            phase_batting_mod = evo["middle_batting_boost"]
            pace_eff = max(0.35, 0.55 - (over_number - 4) * evo["pace_decay_rate"])
            spin_eff = min(0.75, 0.40 + over_number * evo["spin_growth_rate"])
            swing_available = False
            bounce_consistency = 0.78
        else:
            # Death overs: wear + variable conditions
            wear_factor = (over_number - 14) * evo["late_wear_factor"]
            phase_batting_mod = evo["middle_batting_boost"] - wear_factor
            pace_eff = max(0.30, 0.45 - (over_number - 10) * evo["pace_decay_rate"])
            spin_eff = min(0.85, 0.55 + over_number * evo["spin_growth_rate"])
            swing_available = False
            bounce_consistency = max(0.65, 0.78 - wear_factor)

        # Second innings pitch is more worn
        innings_wear = 0.0
        if innings == 2:
            innings_wear = 0.08  # additional wear from first innings

        batting_ease = base_ease + phase_batting_mod - innings_wear
        batting_ease = max(0.20, min(0.95, batting_ease))  # clamp

        # Adjust pace and spin for second innings
        pace_eff = max(0.20, pace_eff - innings_wear * 0.5)
        spin_eff = min(0.90, spin_eff + innings_wear * 0.5)

        condition = {
            "over": over_number,
            "innings": innings,
            "pitch_type": self._pitch_type,
            "batting_ease": round(batting_ease, 3),
            "pace_effectiveness": round(pace_eff, 3),
            "spin_effectiveness": round(spin_eff, 3),
            "bounce_consistency": round(bounce_consistency, 3),
            "swing_available": swing_available,
            "turn_available": spin_eff > 0.55,
            "description": self._describe_condition(batting_ease, spin_eff, pace_eff, over_number),
        }

        return condition

    def get_spin_effectiveness(self, over: int, innings: int = 1) -> float:
        """Return spin bowling effectiveness for this over (0-1)."""
        return self.get_condition(over, innings)["spin_effectiveness"]

    def get_pace_effectiveness(self, over: int, innings: int = 1) -> float:
        """Return pace bowling effectiveness for this over (0-1)."""
        return self.get_condition(over, innings)["pace_effectiveness"]

    def get_batting_ease(self, over: int, innings: int = 1) -> float:
        """Return how easy it is to bat at this stage of the innings (0-1)."""
        return self.get_condition(over, innings)["batting_ease"]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _describe_condition(batting_ease: float, spin_eff: float, pace_eff: float, over: int) -> str:
        """Generate a human-readable pitch condition description."""
        if over <= 5:
            if pace_eff > 0.75:
                return "Lively pitch with pace and movement — bowlers in control"
            return "Pitch offering some assistance to pacers early"
        elif over <= 12:
            if batting_ease > 0.70:
                return "Pitch has flattened out — excellent for batting"
            elif spin_eff > 0.50:
                return "Pitch showing some turn — spinners becoming effective"
            return "Good batting pitch with slight assistance to bowlers"
        else:
            if spin_eff > 0.70:
                return "Significant turn available — experienced spinners dangerous"
            elif batting_ease > 0.68:
                return "Pitch still good for batting despite some wear"
            return "Pitch showing wear — variable bounce and some turn"

    @property
    def pitch_type(self) -> str:
        return self._pitch_type

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["pitch_type"] = self._pitch_type
        return base

    def __repr__(self) -> str:
        return f"PitchAgent(type={self._pitch_type!r}, run_id={self._run_id[:8]!r})"
