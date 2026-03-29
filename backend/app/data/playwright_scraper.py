"""
ESPNCricinfoScraper — Playwright-based scraper for player career + venue stats.

Rules:
- 800ms delay between page loads
- Max 3 concurrent venue queries (semaphore)
- Realistic User-Agent
- Graceful fallback to empty dict with venue_affinity: 0.5
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.data._playwright_bootstrap import ensure_chromium

logger = logging.getLogger(__name__)

_SEMAPHORE_VENUE = asyncio.Semaphore(3)  # max 3 concurrent venue queries
_REQUEST_DELAY = 0.8  # seconds between requests
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_ESPNCRICINFO_SEARCH_URL = "https://www.espncricinfo.com/ci/content/player/search.html?search={name}"
_ESPNCRICINFO_BASE = "https://www.espncricinfo.com"

# Fallback venue stats when no data found
VENUE_FALLBACK: dict[str, Any] = {
    "venue_affinity": 0.5,
    "innings": 0,
    "runs": 0,
    "avg": None,
    "sr": None,
    "source": "fallback",
}


class ESPNCricinfoScraper:
    """
    Scraper for ESPNcricinfo player career and venue-specific stats.

    Usage:
        async with ESPNCricinfoScraper() as scraper:
            career = await scraper.get_player_career_stats("Virat Kohli")
            venue  = await scraper.get_player_venue_stats("Virat Kohli", "3")  # Chinnaswamy ground_id
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> "ESPNCricinfoScraper":
        ensure_chromium()
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _new_page(self) -> Page:
        """Create a new page in the shared context."""
        if self._context is None:
            raise RuntimeError("Scraper not initialised — use as async context manager")
        return await self._context.new_page()

    async def get_player_career_stats(self, player_name: str) -> dict[str, Any]:
        """
        Search ESPNcricinfo for a player and scrape their T20 career stats.

        Args:
            player_name: Full player name (e.g. "Virat Kohli")

        Returns:
            Dict with batting_avg, strike_rate, bowling_economy, bowling_avg, etc.
            Returns empty dict on failure.
        """
        page = await self._new_page()
        try:
            search_url = (
                f"https://www.espncricinfo.com/ci/content/player/search.html"
                f"?search={player_name.replace(' ', '+')}"
            )
            await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(_REQUEST_DELAY)

            # Try to find the first player result link
            player_links = await page.query_selector_all("a[href*='/cricketers/']")
            if not player_links:
                logger.debug("No player results for '%s' on ESPNcricinfo", player_name)
                return {}

            player_href = await player_links[0].get_attribute("href")
            if not player_href:
                return {}

            # Navigate to player profile
            player_url = _ESPNCRICINFO_BASE + player_href if player_href.startswith("/") else player_href
            await page.goto(player_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(_REQUEST_DELAY)

            return await self._parse_career_stats_page(page, player_name)

        except Exception as exc:
            logger.warning("Career stats scrape failed for '%s': %s", player_name, exc)
            return {}
        finally:
            await page.close()

    async def _parse_career_stats_page(self, page: Page, player_name: str) -> dict[str, Any]:
        """Parse career stats from an ESPNcricinfo player profile page."""
        stats: dict[str, Any] = {"name": player_name, "source": "espncricinfo"}

        try:
            # ESPNcricinfo uses a stats table — look for T20I / T20 rows
            content = await page.content()

            # Extract batting average from visible text (robust fallback parsing)
            bat_avg_match = re.search(r"Batting Average[^\d]*(\d+\.?\d*)", content, re.IGNORECASE)
            if bat_avg_match:
                stats["batting_avg"] = float(bat_avg_match.group(1))

            sr_match = re.search(r"Strike Rate[^\d]*(\d+\.?\d*)", content, re.IGNORECASE)
            if sr_match:
                stats["strike_rate"] = float(sr_match.group(1))

            eco_match = re.search(r"Economy[^\d]*(\d+\.?\d*)", content, re.IGNORECASE)
            if eco_match:
                stats["bowling_economy"] = float(eco_match.group(1))

            bowl_avg_match = re.search(r"Bowling Average[^\d]*(\d+\.?\d*)", content, re.IGNORECASE)
            if bowl_avg_match:
                stats["bowling_avg"] = float(bowl_avg_match.group(1))

        except Exception as exc:
            logger.debug("Stats parse error for '%s': %s", player_name, exc)

        return stats

    async def get_player_venue_stats(
        self, player_name: str, ground_id: str
    ) -> dict[str, Any]:
        """
        Fetch player stats at a specific ESPNcricinfo ground (venue-filtered).

        Uses semaphore to limit to max 3 concurrent venue queries.

        Args:
            player_name: Full player name
            ground_id: ESPNcricinfo ground ID (e.g. "6" for Wankhede)

        Returns:
            Dict with venue_affinity, innings, runs, avg, sr.
            Returns VENUE_FALLBACK on failure or no data.
        """
        async with _SEMAPHORE_VENUE:
            return await self._fetch_venue_stats(player_name, ground_id)

    async def _fetch_venue_stats(
        self, player_name: str, ground_id: str
    ) -> dict[str, Any]:
        """Internal: fetch venue stats after acquiring semaphore."""
        page = await self._new_page()
        try:
            # First find the player ID via search
            search_url = (
                f"https://www.espncricinfo.com/ci/content/player/search.html"
                f"?search={player_name.replace(' ', '+')}"
            )
            await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(_REQUEST_DELAY)

            player_links = await page.query_selector_all("a[href*='/cricketers/']")
            if not player_links:
                logger.debug("Venue stats: no player found for '%s'", player_name)
                return dict(VENUE_FALLBACK)

            player_href = await player_links[0].get_attribute("href")
            if not player_href:
                return dict(VENUE_FALLBACK)

            # Extract numeric player ID from URL like /cricketers/virat-kohli-253802
            pid_match = re.search(r"-(\d+)$", player_href.rstrip("/"))
            if not pid_match:
                return dict(VENUE_FALLBACK)
            player_id = pid_match.group(1)

            # Venue-filtered T20 stats URL
            venue_url = (
                f"https://stats.espncricinfo.com/ci/engine/player/{player_id}.html"
                f"?class=3&ground={ground_id}&template=results&type=batting"
            )
            await page.goto(venue_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(1.5)  # ESPNcricinfo venue endpoint is slower

            return await self._parse_venue_stats_page(page, player_name, ground_id)

        except Exception as exc:
            logger.warning("Venue stats scrape failed for '%s' at ground %s: %s", player_name, ground_id, exc)
            return dict(VENUE_FALLBACK)
        finally:
            await page.close()

    async def _parse_venue_stats_page(
        self, page: Page, player_name: str, ground_id: str
    ) -> dict[str, Any]:
        """Parse the venue-filtered stats results page."""
        result = dict(VENUE_FALLBACK)
        result["source"] = "espncricinfo_venue"

        try:
            content = await page.content()

            # Find innings count
            inns_match = re.search(r"<td[^>]*>(\d+)</td>", content)
            if not inns_match:
                return result

            # Try to extract stats from the stats table rows
            # ESPNcricinfo stats table: Mat | Inns | NO | Runs | HS | Ave | SR | ...
            rows = await page.query_selector_all("table.engineTable tr.data1, table.engineTable tr.data2")

            if not rows:
                # fallback: try text parsing for key stats
                avg_match = re.search(r"<td[^>]*>\s*(\d+\.?\d*)\s*</td>", content)
                if avg_match:
                    result["avg"] = float(avg_match.group(1))
                return result

            for row in rows[:1]:  # take first data row (career total at venue)
                cells = await row.query_selector_all("td")
                cell_texts = []
                for cell in cells:
                    txt = (await cell.inner_text()).strip()
                    cell_texts.append(txt)

                if len(cell_texts) >= 8:
                    try:
                        innings = int(cell_texts[1]) if cell_texts[1].isdigit() else 0
                        runs_str = cell_texts[3].replace(",", "")
                        runs = int(runs_str) if runs_str.isdigit() else 0
                        avg_str = cell_texts[5]
                        avg = float(avg_str) if avg_str not in ("-", "") else None
                        sr_str = cell_texts[6]
                        sr = float(sr_str) if sr_str not in ("-", "") else None

                        result["innings"] = innings
                        result["runs"] = runs
                        result["avg"] = avg
                        result["sr"] = sr

                        # Compute venue_affinity from avg relative to IPL average (28)
                        if avg is not None and innings >= 3:
                            result["venue_affinity"] = min(1.0, max(0.0, avg / 56.0))
                        elif innings > 0:
                            result["venue_affinity"] = 0.55  # some data but sparse
                        # else stays 0.5 (VENUE_FALLBACK default)

                    except (ValueError, IndexError) as e:
                        logger.debug("Cell parse error for %s: %s", player_name, e)

        except Exception as exc:
            logger.debug("Venue page parse error for '%s' at ground %s: %s", player_name, ground_id, exc)

        return result
