"""
CricbuzzScraper — Stealth scraper for Cricbuzz (Cloudflare bypass).

Uses playwright-stealth to bypass Cloudflare protection.
Provides playing XI and live score data.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.data._playwright_bootstrap import ensure_chromium

try:
    from playwright_stealth import stealth_async
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False
    stealth_async = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_REQUEST_DELAY = 0.8  # seconds between requests
_CRICBUZZ_BASE = "https://www.cricbuzz.com"

# Default fallback structures
_EMPTY_XI: dict[str, Any] = {
    "team1_xi": [],
    "team2_xi": [],
    "impact_pool": {},
    "source": "cricbuzz",
}

_EMPTY_SCORE: dict[str, Any] = {
    "score": 0,
    "wickets": 0,
    "overs": 0.0,
    "batting_team": "",
    "bowling_team": "",
    "match_status": "unknown",
    "source": "cricbuzz",
}


class CricbuzzScraper:
    """
    Stealth Playwright scraper for Cricbuzz.

    Uses playwright-stealth to bypass Cloudflare JS challenge.

    Usage:
        async with CricbuzzScraper() as scraper:
            xi = await scraper.get_playing_xi("12345")
            score = await scraper.get_live_score("12345")
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

        if not _STEALTH_AVAILABLE:
            logger.warning(
                "playwright-stealth is not installed. "
                "Cricbuzz scraper will run without stealth — Cloudflare may block requests. "
                "Install with: pip install playwright-stealth"
            )

    async def __aenter__(self) -> "CricbuzzScraper":
        ensure_chromium()
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        self._context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _stealth_page(self) -> Page:
        """Create a new page with stealth mode applied."""
        if self._context is None:
            raise RuntimeError("Scraper not initialised — use as async context manager")
        page = await self._context.new_page()
        if _STEALTH_AVAILABLE and stealth_async is not None:
            await stealth_async(page)
        return page

    async def get_playing_xi(self, match_id: str) -> dict[str, Any]:
        """
        Fetch confirmed playing XI for both teams.

        Args:
            match_id: Cricbuzz match ID

        Returns:
            Dict: {team1_xi: [str, ...], team2_xi: [str, ...], impact_pool: {team: [str, ...]}}
        """
        page = await self._stealth_page()
        result = dict(_EMPTY_XI)

        try:
            match_url = f"{_CRICBUZZ_BASE}/live-cricket-scorecard/{match_id}/live"
            await page.goto(match_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(_REQUEST_DELAY)

            # Try to extract squad/playing XI info
            # Cricbuzz shows squads in the Playing XI tab
            playing_xi_tab = await page.query_selector("a[href*='playing-xi'], button:has-text('Playing XI')")
            if playing_xi_tab:
                await playing_xi_tab.click()
                await asyncio.sleep(_REQUEST_DELAY)

            # Extract player names from the playing XI section
            content = await page.content()

            # Look for player name elements (CB uses specific CSS classes)
            player_elements = await page.query_selector_all(
                ".cb-player-name, .cb-col.cb-col-50, [class*='player-name']"
            )

            player_names: list[str] = []
            for el in player_elements:
                name = (await el.inner_text()).strip()
                if name and len(name) > 2 and not name.isdigit():
                    player_names.append(name)

            # Split roughly in half for two teams (simple heuristic)
            if len(player_names) >= 11:
                mid = len(player_names) // 2
                result["team1_xi"] = player_names[:11]
                result["team2_xi"] = player_names[mid:mid + 11] if len(player_names) > mid + 11 else player_names[11:22]

            logger.info("Cricbuzz: fetched %d player names for match %s", len(player_names), match_id)

        except Exception as exc:
            logger.warning("Cricbuzz get_playing_xi failed for match %s: %s", match_id, exc)
        finally:
            await page.close()

        return result

    async def get_live_score(self, match_id: str) -> dict[str, Any]:
        """
        Fetch current live score for an ongoing match.

        Args:
            match_id: Cricbuzz match ID

        Returns:
            Dict: {score, wickets, overs, batting_team, bowling_team, match_status}
        """
        page = await self._stealth_page()
        result = dict(_EMPTY_SCORE)

        try:
            score_url = f"{_CRICBUZZ_BASE}/live-cricket-scores/{match_id}/live"
            await page.goto(score_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(_REQUEST_DELAY)

            # Cricbuzz score selectors
            score_el = await page.query_selector(".cb-lv-scrs-well-live, .cb-mini-scr-itm .cb-ovr-flo")
            if score_el:
                score_text = (await score_el.inner_text()).strip()
                # Typical format: "182/4 (15.3)"
                import re
                score_match = re.search(r"(\d+)/(\d+)\s*\((\d+\.?\d*)\)", score_text)
                if score_match:
                    result["score"] = int(score_match.group(1))
                    result["wickets"] = int(score_match.group(2))
                    result["overs"] = float(score_match.group(3))

            # Match status
            status_el = await page.query_selector(".cb-text-inprogress, .cb-text-complete, .cb-text-stumps")
            if status_el:
                result["match_status"] = (await status_el.inner_text()).strip().lower()

            # Batting/bowling team names
            team_els = await page.query_selector_all(".cb-nav-main.cb-font-18 a, .cb-min-tm-nm")
            if len(team_els) >= 2:
                result["batting_team"] = (await team_els[0].inner_text()).strip()
                result["bowling_team"] = (await team_els[1].inner_text()).strip()

            logger.info(
                "Cricbuzz live score for match %s: %d/%d (%.1f overs)",
                match_id, result["score"], result["wickets"], result["overs"],
            )

        except Exception as exc:
            logger.warning("Cricbuzz get_live_score failed for match %s: %s", match_id, exc)
        finally:
            await page.close()

        return result
