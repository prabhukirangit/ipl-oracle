"""
IPLT20Scraper — Playwright scraper for iplt20.com playing XI.

Primary source for confirmed playing XI and Impact Player pool.
IPLT20 uses Next.js (JS-rendered) — requires Playwright.

Polite: 800ms delay between page loads, max 5 concurrent instances,
realistic User-Agent.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.data._playwright_bootstrap import ensure_chromium

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_REQUEST_DELAY = 0.8  # seconds between requests
_IPLT20_BASE = "https://www.iplt20.com"

# Team name → IPLT20 URL slug
_TEAM_SLUGS: dict[str, str] = {
    "Mumbai Indians": "mumbai-indians",
    "Chennai Super Kings": "chennai-super-kings",
    "Royal Challengers Bengaluru": "royal-challengers-bengaluru",
    "Kolkata Knight Riders": "kolkata-knight-riders",
    "Delhi Capitals": "delhi-capitals",
    "Sunrisers Hyderabad": "sunrisers-hyderabad",
    "Rajasthan Royals": "rajasthan-royals",
    "Punjab Kings": "punjab-kings",
    "Gujarat Titans": "gujarat-titans",
    "Lucknow Super Giants": "lucknow-super-giants",
}


class IPLT20Scraper:
    """
    Playwright scraper for iplt20.com — playing XI and Impact Player pool.

    Usage:
        async with IPLT20Scraper() as scraper:
            result = await scraper.get_playing_xi(team1, team2)
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> "IPLT20Scraper":
        ensure_chromium()
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
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

    async def get_playing_xi(
        self, team1: str, team2: str,
    ) -> dict[str, Any]:
        """
        Fetch confirmed playing XI for both teams from iplt20.com match page.

        Searches the fixtures/results page for the specific match, then
        navigates to the match detail page to extract the playing XI.

        Returns:
            {
                "team1_xi": [str, ...],   # 11 player names
                "team2_xi": [str, ...],   # 11 player names
                "impact_pool": {"team1": [...], "team2": [...]},
                "source": "iplt20",
                "confirmed": True/False,
            }
        """
        if self._context is None:
            raise RuntimeError("Scraper not initialised — use as async context manager")

        result: dict[str, Any] = {
            "team1_xi": [],
            "team2_xi": [],
            "impact_pool": {},
            "source": "iplt20",
            "confirmed": False,
        }

        page = await self._context.new_page()
        try:
            # Strategy 1: Go to fixtures page and find today's match
            match_url = await self._find_match_url(page, team1, team2)
            if not match_url:
                logger.info("IPLT20: could not find match URL for %s vs %s", team1, team2)
                return result

            # Navigate to the match page
            await page.goto(match_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(_REQUEST_DELAY)

            # Try to find and click "Playing XI" or "Squads" tab
            xi_tab = await page.query_selector(
                "a:has-text('Playing XI'), "
                "a:has-text('playing xi'), "
                "button:has-text('Playing XI'), "
                "[data-tab='playing-xi'], "
                "a:has-text('Squads')"
            )
            if xi_tab:
                await xi_tab.click()
                await asyncio.sleep(_REQUEST_DELAY)

            # Extract playing XI from page content
            content = await page.content()
            team1_xi, team2_xi = self._parse_playing_xi(content, team1, team2)

            if team1_xi and len(team1_xi) >= 11:
                result["team1_xi"] = team1_xi[:11]
                result["confirmed"] = True
            if team2_xi and len(team2_xi) >= 11:
                result["team2_xi"] = team2_xi[:11]
                result["confirmed"] = result["confirmed"] and True

            # Try to extract impact pool
            impact_pool = self._parse_impact_pool(content, team1, team2)
            if impact_pool:
                result["impact_pool"] = impact_pool

            logger.info(
                "IPLT20: fetched XI for %s vs %s — t1=%d, t2=%d, confirmed=%s",
                team1, team2, len(result["team1_xi"]),
                len(result["team2_xi"]), result["confirmed"],
            )

        except Exception as exc:
            logger.warning("IPLT20 get_playing_xi failed: %s", exc)
        finally:
            await page.close()

        return result

    async def _find_match_url(self, page: Page, team1: str, team2: str) -> str | None:
        """Find the match detail URL from the IPLT20 fixtures page."""
        fixtures_url = f"{_IPLT20_BASE}/matches/fixtures"
        try:
            await page.goto(fixtures_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(_REQUEST_DELAY)

            # IPLT20 match cards contain team names — find the one matching
            # our teams (look for links containing both team slugs)
            slug1 = _TEAM_SLUGS.get(team1, team1.lower().replace(" ", "-"))
            slug2 = _TEAM_SLUGS.get(team2, team2.lower().replace(" ", "-"))

            # Look for match card links
            links = await page.query_selector_all("a[href*='/match/']")
            for link in links:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).lower()

                # Check if this link's text or href references both teams
                has_team1 = slug1 in href.lower() or _short_name(team1) in text
                has_team2 = slug2 in href.lower() or _short_name(team2) in text
                if has_team1 and has_team2:
                    if href.startswith("/"):
                        return f"{_IPLT20_BASE}{href}"
                    return href

            # Fallback: search all visible text for match cards
            content = await page.content()
            match_pattern = re.search(
                rf'href="(/match/\d+[^"]*)"[^>]*>.*?'
                rf'(?:{re.escape(_short_name(team1))}.*?{re.escape(_short_name(team2))}'
                rf'|{re.escape(_short_name(team2))}.*?{re.escape(_short_name(team1))})',
                content, re.IGNORECASE | re.DOTALL,
            )
            if match_pattern:
                return f"{_IPLT20_BASE}{match_pattern.group(1)}"

        except Exception as exc:
            logger.warning("IPLT20: failed to find match URL: %s", exc)

        return None

    def _parse_playing_xi(
        self, html: str, team1: str, team2: str,
    ) -> tuple[list[str], list[str]]:
        """Parse playing XI names from IPLT20 match page HTML."""
        team1_xi: list[str] = []
        team2_xi: list[str] = []

        # IPLT20 typically shows playing XI in structured divs with player names
        # Pattern: player name spans/divs within team sections
        # Try multiple CSS-like patterns from the raw HTML

        # Extract all player-name-like elements
        # Common IPLT20 patterns:
        #   <span class="player-name">Player Name</span>
        #   <div class="...playerName...">Player Name</div>
        name_patterns = [
            re.findall(r'class="[^"]*player[_-]?name[^"]*"[^>]*>([^<]{3,40})<', html, re.IGNORECASE),
            re.findall(r'class="[^"]*squad[^"]*player[^"]*"[^>]*>([^<]{3,40})<', html, re.IGNORECASE),
            re.findall(r'<span[^>]*>([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)</span>', html),
        ]

        all_names: list[str] = []
        for group in name_patterns:
            all_names.extend(n.strip() for n in group if n.strip())

        if not all_names:
            return team1_xi, team2_xi

        # Deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for n in all_names:
            nl = n.lower()
            if nl not in seen and len(n) > 3:
                seen.add(nl)
                unique.append(n)

        # Split into two teams — look for team name markers in HTML
        # to determine the split point
        t1_short = _short_name(team1).lower()
        t2_short = _short_name(team2).lower()
        html_lower = html.lower()

        t1_pos = html_lower.find(t1_short)
        t2_pos = html_lower.find(t2_short, t1_pos + 1 if t1_pos >= 0 else 0)

        if len(unique) >= 22:
            team1_xi = unique[:11]
            team2_xi = unique[11:22]
        elif len(unique) >= 11:
            team1_xi = unique[:11]
            team2_xi = unique[11:]

        return team1_xi, team2_xi

    def _parse_impact_pool(
        self, html: str, team1: str, team2: str,
    ) -> dict[str, list[str]]:
        """Parse Impact Player pool (5 named subs per team) from match page."""
        pool: dict[str, list[str]] = {}

        # IPLT20 shows impact pool in a separate section after playing XI
        # Look for "Impact Player" or "Substitute" sections
        impact_match = re.search(
            r'(?:impact\s*player|substitute|sub)[^<]*</[^>]+>(.*?)(?:<h|</section)',
            html, re.IGNORECASE | re.DOTALL,
        )
        if impact_match:
            section = impact_match.group(1)
            names = re.findall(r'>([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)<', section)
            if names:
                mid = len(names) // 2
                pool[team1] = names[:mid] if mid <= 5 else names[:5]
                pool[team2] = names[mid:mid + 5] if mid + 5 <= len(names) else names[mid:]

        return pool


def _short_name(team: str) -> str:
    """Extract short team identifier for text matching."""
    # "Royal Challengers Bengaluru" → "bengaluru"
    # "Sunrisers Hyderabad" → "hyderabad"
    # "Mumbai Indians" → "mumbai"
    parts = team.lower().split()
    # Use last word (city name) which is typically unique
    return parts[-1] if parts else team.lower()
