"""
WeatherAgent — Deterministic weather conditions agent.

Week 1: Returns static/default weather conditions.
Week 2+: Will fetch from OpenWeatherMap API using venue coordinates.

Weather affects:
- Dew factor (helps batting team in second innings)
- Wind speed (boundary carry)
- Humidity (swing bowling)
- Cloud cover (overcast conditions help swing)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .base_agent import BaseAgent


# Default weather for IPL conditions (March-May in India)
DEFAULT_WEATHER = {
    "temperature_c": 28.0,
    "humidity_pct": 60.0,
    "wind_speed_kmh": 12.0,
    "wind_direction": "SW",
    "cloud_cover_pct": 20.0,
    "dew_point_c": 18.0,
    "is_raining": False,
    "rain_probability_pct": 10.0,
    "visibility_km": 8.0,
    "pressure_hpa": 1010.0,
    "conditions_summary": "Clear skies, light breeze",
    "dew_onset_expected_over": None,  # which over dew expected (None = no dew expected)
}


class WeatherAgent(BaseAgent):
    """
    Agent providing weather conditions for the match venue.

    In Week 1, returns static conditions. In Week 2+, calls OpenWeatherMap.
    All conditions are read-only during simulation.
    """

    def __init__(
        self,
        venue_name: str,
        match_time: datetime | None = None,
        weather_data: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> None:
        """
        Initialise WeatherAgent.

        Args:
            venue_name: Venue name (used for coordinate lookup in Week 2+)
            match_time: Match start time (IST)
            weather_data: Pre-fetched weather data dict (Week 2+). Uses defaults if None.
            run_id: Simulation run ID
        """
        weather = weather_data or DEFAULT_WEATHER.copy()
        weather["venue_name"] = venue_name
        weather["match_time"] = match_time.isoformat() if match_time else None
        weather["data_source"] = "default" if weather_data is None else "api"

        # Compute derived factors
        weather["swing_factor"] = self._compute_swing_factor(weather)
        weather["dew_factor"] = self._compute_dew_factor(weather, match_time)

        super().__init__(agent_type="weather", profile=weather, run_id=run_id)
        self._venue_name = venue_name
        self._match_time = match_time

    @staticmethod
    def _compute_swing_factor(weather: dict) -> float:
        """
        Compute swing bowling factor from weather conditions.

        Overcast + humidity = more swing. Clear and dry = less swing.
        Returns 0-1 float.
        """
        cloud_factor = weather.get("cloud_cover_pct", 20) / 100.0
        humidity_factor = (weather.get("humidity_pct", 60) - 40) / 60.0
        humidity_factor = max(0, min(1, humidity_factor))
        return round(0.4 * cloud_factor + 0.6 * humidity_factor, 3)

    @staticmethod
    def _compute_dew_factor(weather: dict, match_time: datetime | None) -> float:
        """
        Compute dew factor: how much dew will affect the ball in second innings.

        Evening matches (after 19:00 IST) in humid venues get heavy dew.
        Returns 0-1 float (higher = more dew = helps batting second innings).
        """
        humidity = weather.get("humidity_pct", 60)
        is_evening = False
        if match_time and match_time.hour >= 19:
            is_evening = True
        elif match_time and match_time.hour >= 15:
            is_evening = True  # afternoon games also get some dew after sunset

        if not is_evening:
            return 0.15

        # Dew increases with humidity
        base_dew = (humidity - 40) / 60.0
        base_dew = max(0.1, min(0.9, base_dew))
        return round(base_dew * 0.85, 3)  # scale to realistic range

    def get_conditions(self) -> dict[str, Any]:
        """Return the full weather conditions dict."""
        return self.get_profile()

    def get_swing_factor(self) -> float:
        """Return swing bowling factor (0-1). Higher = more swing available."""
        return self._profile.get("swing_factor", 0.35)

    def get_dew_factor(self) -> float:
        """
        Return dew factor (0-1).

        Higher values mean more dew — easier for batting team in second innings.
        """
        return self._profile.get("dew_factor", 0.30)

    def is_overcast(self) -> bool:
        """Return True if cloud cover is heavy enough to affect play."""
        return self._profile.get("cloud_cover_pct", 20) > 60

    def is_humid(self) -> bool:
        """Return True if humidity is high (>70%)."""
        return self._profile.get("humidity_pct", 60) > 70

    def get_dew_onset_over(self) -> int | None:
        """
        Return the over number when dew is expected to onset, or None.

        If dew factor > 0.6 and match is evening, estimate onset around over 12-14.
        """
        dew = self.get_dew_factor()
        if dew > 0.60:
            # Heavy dew expected around over 12-14 of second innings
            return 12
        elif dew > 0.40:
            return 15
        return None

    def compute_dew_factor(self, over_number: int, is_night_match: bool) -> float:
        """
        Per-over RPM grip factor (0.7–1.0).

        IMPORTANT: Different scale from get_dew_factor()!
        - This method: 1.0 = no grip loss, 0.7 = full grip loss (for RPM/effectiveness)
        - get_dew_factor(): 0.0–0.9 where higher = more dew (match-level indicator)

        Use this method for: RPM degradation, ball replacement decisions, spin effectiveness.
        Use get_dew_factor() for: toss decisions, venue dew presence check.

        Dew typically arrives 12–14 overs into night matches.
        Peaks at overs 16–18, gradually saturates.
        Day matches: always 1.0 (no dew).

        Args:
            over_number: Current over (0–20)
            is_night_match: Is this a night match?

        Returns:
            float RPM grip factor (1.0 = no dew grip loss, 0.7 = full dew)
        """
        if not is_night_match:
            return 1.0  # No dew in day matches

        if over_number < 12:
            return 1.0  # Too early, dew hasn't arrived

        dew_onset_over = 13
        dew_saturation_over = 17

        if over_number >= dew_saturation_over:
            return 0.70  # Full dew effect

        # Linear ramp from over 13 to 17
        progress = (over_number - dew_onset_over) / (dew_saturation_over - dew_onset_over)
        return 1.0 - (0.30 * progress)  # Ramps from 1.0 → 0.70

    def model_rpm_degradation(
        self, bowler_type: str, dew_factor: float, over_number: int
    ) -> float:
        """
        RPM multiplier based on dew and bowler type.

        - Wrist spinners (leggie, chinaman): lose 20–30% RPM (most affected)
        - Finger spinners (off-spinner, left-arm orthodox): lose 10–15%
        - Pacers: negligible loss (~1%)

        After ball replacement (10+ overs in night matches), RPM is temporarily restored.

        Args:
            bowler_type: 'wrist_spinner', 'finger_spinner', 'pacer'
            dew_factor: From compute_dew_factor()
            over_number: For tracking post-ball-replacement window

        Returns:
            RPM multiplier (0.7–1.0)
        """
        if bowler_type == "wrist_spinner":
            # Worst affected: 0.70 at full dew, 1.0 at no dew
            return 0.70 + (0.30 * dew_factor)
        elif bowler_type == "finger_spinner":
            # Moderate: 0.85 at full dew, 1.0 at no dew
            return 0.85 + (0.15 * dew_factor)
        else:  # Pacer
            # Negligible: 0.99 even at full dew
            return 0.99

    def is_ball_replacement_window(
        self, over_number: int, innings_number: int, is_night_match: bool
    ) -> bool:
        """
        Check if fielding captain can request ball replacement.

        2026 Rule: After 10th over, first or second innings, night matches only.

        Args:
            over_number: Current over (0–20)
            innings_number: 1 or 2
            is_night_match: Night match?

        Returns:
            bool True if in replacement window
        """
        return (
            over_number >= 10
            and is_night_match
            and innings_number in [1, 2]
        )

    def apply_ball_replacement_effect(self) -> float:
        """
        After ball replacement, dew_factor temporarily resets to 1.0 for 1–2 overs.

        Returns:
            Dew factor reset value (1.0) for use in MatchEngine
        """
        return 1.0  # New ball = dry grip restored

    def get_conditions_at_over(self, over: int, innings: int = 1) -> dict[str, Any]:
        """
        Return weather conditions modified for a specific over.

        Dew increases as the game progresses into the evening.
        """
        base = dict(self._profile)
        if innings == 2 and over >= (self.get_dew_onset_over() or 20):
            dew_mult = min(1.5, 1.0 + (over - 12) * 0.05)
            base["active_dew"] = True
            base["effective_dew_factor"] = min(0.95, base.get("dew_factor", 0.30) * dew_mult)
        else:
            base["active_dew"] = False
            base["effective_dew_factor"] = 0.0
        base["over"] = over
        base["innings"] = innings
        return base

    def __repr__(self) -> str:
        return f"WeatherAgent(venue={self._venue_name!r}, run_id={self._run_id[:8]!r})"
