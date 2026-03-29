"""
MatchStateDetector — Classifies match state before agent spawn.

Four states:
  FUTURE    : > ~1hr before toss → simulate with probable XI
  IMMINENT  : Toss window to match start → use confirmed XI if toss done
  LIVE      : Match in progress → fetch live state, simulate remainder
  COMPLETED : Match over → Hard reject, return 400 error

This MUST run before spawning any agents. COMPLETED = hard reject.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any

# IST is UTC+5:30
IST_OFFSET = timedelta(hours=5, minutes=30)


class MatchStatus(str, Enum):
    FUTURE = "FUTURE"
    IMMINENT = "IMMINENT"
    LIVE = "LIVE"
    COMPLETED = "COMPLETED"
    UNKNOWN = "UNKNOWN"


# Time thresholds
TOSS_WINDOW_MINUTES = 60        # toss happens ~60 min before match
MATCH_START_BUFFER_MINUTES = 5  # 5 min buffer for match start
T20_DURATION_HOURS = 4          # T20 match typically completes in ~3.5-4 hours


class MatchStateDetector:
    """
    Classifies the current state of a cricket match.

    Must be called before spawning agents. If state is COMPLETED,
    the caller must return HTTP 400 and must NOT run simulation.

    Usage:
        detector = MatchStateDetector()
        status, details = detector.detect(match_info)
        if status == MatchStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Match already completed")
    """

    def detect(
        self,
        match_info: dict[str, Any],
        current_time: datetime | None = None,
    ) -> tuple[MatchStatus, dict[str, Any]]:
        """
        Detect the current state of a match.

        Args:
            match_info: Dict with at minimum:
                - match_start_time: ISO datetime string (UTC or with timezone)
                - status: Optional status string ('upcoming', 'live', 'completed', 'cancelled')
                - toss_done: Optional bool
                - innings_complete: Optional int (0, 1, or 2)
            current_time: Current time for comparison. Defaults to UTC now.

        Returns:
            Tuple of (MatchStatus, details_dict)
            Details include: state, time_to_toss_minutes, xi_source, caveats
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # If we have an explicit status, use it
        explicit_status = match_info.get("status", "").lower()
        if explicit_status in ("completed", "finished", "result"):
            return MatchStatus.COMPLETED, {
                "state": MatchStatus.COMPLETED,
                "reason": "Match completed (explicit status)",
                "xi_source": None,
                "caveats": ["Match is over — simulation not allowed"],
            }

        if explicit_status == "live":
            return MatchStatus.LIVE, self._live_details(match_info)

        if explicit_status == "cancelled":
            return MatchStatus.COMPLETED, {
                "state": MatchStatus.COMPLETED,
                "reason": "Match cancelled",
                "xi_source": None,
                "caveats": ["Match was cancelled"],
            }

        # Use time-based detection
        match_start_str = match_info.get("match_start_time") or match_info.get("start_time")
        if not match_start_str:
            return MatchStatus.UNKNOWN, {"state": MatchStatus.UNKNOWN, "reason": "No start time provided"}

        try:
            match_start = self._parse_datetime(match_start_str)
        except ValueError as e:
            return MatchStatus.UNKNOWN, {"state": MatchStatus.UNKNOWN, "reason": f"Invalid datetime: {e}"}

        # Ensure both are timezone-aware
        if match_start.tzinfo is None:
            # Assume IST if no timezone
            match_start = match_start.replace(tzinfo=timezone(IST_OFFSET))
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        # Convert to UTC for comparison
        match_start_utc = match_start.astimezone(timezone.utc)
        current_utc = current_time.astimezone(timezone.utc)

        minutes_to_start = (match_start_utc - current_utc).total_seconds() / 60
        hours_since_start = (current_utc - match_start_utc).total_seconds() / 3600

        # Classify
        if minutes_to_start > TOSS_WINDOW_MINUTES:
            # More than 1hr before toss
            return MatchStatus.FUTURE, {
                "state": MatchStatus.FUTURE,
                "reason": f"Match starts in {minutes_to_start:.0f} minutes",
                "time_to_start_minutes": round(minutes_to_start),
                "xi_source": "probable_xi",
                "caveats": [
                    f"CAUTION: Playing XI not confirmed. Using probable XI.",
                    f"Match starts at {match_start.strftime('%H:%M %Z')}",
                ],
            }

        elif minutes_to_start > -MATCH_START_BUFFER_MINUTES:
            # In toss window (last 60 min before start)
            toss_done = match_info.get("toss_done", False)
            xi_source = "confirmed_xi" if toss_done else "probable_xi"
            return MatchStatus.IMMINENT, {
                "state": MatchStatus.IMMINENT,
                "reason": f"Match imminent — {abs(minutes_to_start):.0f} min to start",
                "time_to_start_minutes": round(minutes_to_start),
                "toss_done": toss_done,
                "xi_source": xi_source,
                "caveats": [
                    "Toss confirmed XI available" if toss_done else "Toss pending — using probable XI",
                ],
            }

        elif hours_since_start <= T20_DURATION_HOURS:
            # Match has started, within T20 duration window
            innings_complete = match_info.get("innings_complete", 0)
            if innings_complete >= 2:
                # Two innings complete = match over
                return MatchStatus.COMPLETED, {
                    "state": MatchStatus.COMPLETED,
                    "reason": "Both innings complete",
                    "xi_source": None,
                    "caveats": ["Match is over — simulation not allowed"],
                }
            return MatchStatus.LIVE, self._live_details(match_info)

        else:
            # Match should be over (well past T20 duration)
            return MatchStatus.COMPLETED, {
                "state": MatchStatus.COMPLETED,
                "reason": f"Match started {hours_since_start:.1f}h ago — likely completed",
                "xi_source": None,
                "caveats": ["Match duration exceeded — assumed completed"],
            }

    def _live_details(self, match_info: dict[str, Any]) -> dict[str, Any]:
        """Build details dict for a LIVE match."""
        return {
            "state": MatchStatus.LIVE,
            "reason": "Match in progress",
            "xi_source": "confirmed_xi",
            "innings_complete": match_info.get("innings_complete", 0),
            "current_score": match_info.get("current_score"),
            "current_over": match_info.get("current_over"),
            "ip_used": match_info.get("ip_used", {}),
            "caveats": [
                "Simulating from current live state.",
                "Result covers only remaining play — not already completed overs.",
            ],
        }

    @staticmethod
    def _parse_datetime(dt_str: str) -> datetime:
        """Parse an ISO datetime string with flexible format support."""
        # Try ISO format variants
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(dt_str, fmt)
            except ValueError:
                continue

        # Try Python 3.11+ fromisoformat (handles more variants)
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            raise ValueError(f"Cannot parse datetime: {dt_str!r}")

    def is_simulatable(self, status: MatchStatus) -> bool:
        """Return True if the match state allows simulation."""
        return status in (MatchStatus.FUTURE, MatchStatus.IMMINENT, MatchStatus.LIVE)

    def get_rejection_message(self, team1: str, team2: str) -> str:
        """Return a user-facing rejection message for COMPLETED matches."""
        return (
            f"The {team1} vs {team2} match has already been completed. "
            "IPL Oracle does not simulate completed matches. "
            "Please check /api/schedule/upcoming for upcoming fixtures."
        )
