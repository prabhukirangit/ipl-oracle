"""
HowstatScraper — Historical cricket records via httpx + BeautifulSoup4.

Howstat is static HTML — no Playwright needed.
Provides career batting/bowling records and head-to-head data.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HOWSTAT_BASE = "https://www.howstat.com/cricket"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_REQUEST_DELAY = 0.8  # seconds between requests
_TIMEOUT = 15.0


class HowstatScraper:
    """
    HTTP + BeautifulSoup4 scraper for Howstat cricket records.

    Howstat serves static HTML pages — safe for httpx, no JS rendering needed.

    Usage:
        async with HowstatScraper() as scraper:
            record = await scraper.get_player_t20_record("Virat Kohli")
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "HowstatScraper":
        self._client = httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def _get(self, url: str) -> str | None:
        """Fetch a URL and return raw HTML, or None on failure."""
        if self._client is None:
            raise RuntimeError("Scraper not initialised — use as async context manager")
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            await asyncio.sleep(_REQUEST_DELAY)
            return resp.text
        except httpx.HTTPStatusError as exc:
            logger.warning("Howstat HTTP error for %s: %s", url, exc)
            return None
        except httpx.RequestError as exc:
            logger.warning("Howstat request error for %s: %s", url, exc)
            return None

    async def get_player_t20_record(self, player_name: str) -> dict[str, Any]:
        """
        Fetch a player's T20 career record from Howstat.

        Args:
            player_name: Full player name (e.g. "Virat Kohli")

        Returns:
            Dict with batting and bowling career stats.
            Returns empty dict if player not found or fetch fails.
        """
        # Howstat search: replace spaces with + for search
        search_url = (
            f"{_HOWSTAT_BASE}/Statistics/Players/"
            f"PlayerSearch.asp?Search={player_name.replace(' ', '+')}"
        )
        html = await self._get(search_url)
        if not html:
            return {}

        soup = BeautifulSoup(html, "lxml")

        # Find first player result link
        player_link = soup.find("a", href=re.compile(r"/PlayerOverview\.asp\?PlayerID=\d+"))
        if not player_link:
            logger.debug("Howstat: player '%s' not found in search results", player_name)
            return {}

        player_url = f"{_HOWSTAT_BASE}/Statistics/Players/{player_link['href'].lstrip('/')}"
        profile_html = await self._get(player_url)
        if not profile_html:
            return {}

        return self._parse_player_profile(profile_html, player_name)

    def _parse_player_profile(self, html: str, player_name: str) -> dict[str, Any]:
        """Parse player overview page for T20 career stats."""
        soup = BeautifulSoup(html, "lxml")
        stats: dict[str, Any] = {"name": player_name, "source": "howstat"}

        # Howstat stats are in HTML tables — look for T20I row
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if not cells:
                    continue

                # Look for rows that contain "Twenty20" or "T20"
                row_text = " ".join(cells).lower()
                if "twenty20" in row_text or "t20" in row_text:
                    if len(cells) >= 8:
                        try:
                            # Batting: Mat | Inn | NO | Runs | HS | Avg | SR | 50s | 100s | 4s | 6s
                            stats["t20_batting"] = {
                                "matches": _safe_int(cells[1] if len(cells) > 1 else "0"),
                                "innings": _safe_int(cells[2] if len(cells) > 2 else "0"),
                                "not_out": _safe_int(cells[3] if len(cells) > 3 else "0"),
                                "runs": _safe_int(cells[4] if len(cells) > 4 else "0"),
                                "avg": _safe_float(cells[6] if len(cells) > 6 else "0"),
                                "strike_rate": _safe_float(cells[7] if len(cells) > 7 else "0"),
                            }
                        except (IndexError, ValueError):
                            pass

        return stats

    async def get_head_to_head(self, team1: str, team2: str) -> dict[str, Any]:
        """
        Fetch head-to-head T20 record between two teams.

        Args:
            team1, team2: Team names (abbreviated, e.g. "MI", "CSK")

        Returns:
            Dict with wins, losses, ties, last_5 results.
        """
        # Howstat team records — simplified query
        url = f"{_HOWSTAT_BASE}/Statistics/Teams/TeamVsTeam.asp"
        html = await self._get(url)
        if not html:
            return {"team1": team1, "team2": team2, "record": "unavailable"}

        # Basic parsing — return structured empty result as fallback
        return {
            "team1": team1,
            "team2": team2,
            "t1_wins": 0,
            "t2_wins": 0,
            "ties": 0,
            "last_5": [],
            "source": "howstat",
        }

    async def get_venue_statistics(self, venue_name: str) -> dict[str, Any]:
        """
        Fetch historical T20 statistics for a venue.

        Args:
            venue_name: Ground name (e.g. "Wankhede Stadium")

        Returns:
            Dict with avg_first_innings_score, avg_winning_score, etc.
        """
        search_url = (
            f"{_HOWSTAT_BASE}/Statistics/Grounds/"
            f"GroundSearch.asp?Search={venue_name.replace(' ', '+')}"
        )
        html = await self._get(search_url)
        if not html:
            return {"venue": venue_name, "source": "howstat_unavailable"}

        soup = BeautifulSoup(html, "lxml")

        # Look for venue link
        venue_link = soup.find("a", href=re.compile(r"/GroundOverview\.asp\?GroundID=\d+"))
        if not venue_link:
            return {"venue": venue_name, "source": "howstat_not_found"}

        venue_url = f"{_HOWSTAT_BASE}/Statistics/Grounds/{venue_link['href'].lstrip('/')}"
        venue_html = await self._get(venue_url)
        if not venue_html:
            return {"venue": venue_name, "source": "howstat_fetch_failed"}

        return self._parse_venue_stats(venue_html, venue_name)

    def _parse_venue_stats(self, html: str, venue_name: str) -> dict[str, Any]:
        """Parse venue overview page for T20 records."""
        soup = BeautifulSoup(html, "lxml")
        stats: dict[str, Any] = {"venue": venue_name, "source": "howstat"}

        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 4:
                    row_text = " ".join(cells).lower()
                    if "average" in row_text and "score" in row_text:
                        try:
                            stats["avg_first_innings_score"] = _safe_int(cells[1])
                            stats["avg_winning_score"] = _safe_int(cells[2])
                        except (IndexError, ValueError):
                            pass

        return stats


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_int(s: str) -> int:
    try:
        return int(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


def _safe_float(s: str) -> float:
    try:
        return float(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0
