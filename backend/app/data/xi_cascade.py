"""
XI Cascade — Live playing XI fetcher with multi-source fallback.

Priority order:
  1. IPLT20.com (Playwright) — official source, primary
  2. Cricbuzz (Playwright + stealth) — fast fallback, Cloudflare-protected
  3. Google News RSS — lightweight text-mining fallback
  4. SQUAD_SEED (local hardcoded) — last resort, always available

Each source is tried in order. First source to return >= 11 players wins.
Falls back to local SQUAD_SEED only when ALL web sources fail.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.squad_manager import SQUAD_SEED

logger = logging.getLogger(__name__)


async def fetch_playing_xi(
    team1: str,
    team2: str,
    team1_abbrev: str,
    team2_abbrev: str,
) -> dict[str, Any]:
    """
    Cascade through all XI sources for both teams.

    Returns:
        {
            "team1_xi": [str, ...],  # 11 player names
            "team2_xi": [str, ...],
            "team1_confirmed": bool,
            "team2_confirmed": bool,
            "impact_pool": {...},
            "source": str,  # which source provided the data
        }
    """
    result: dict[str, Any] = {
        "team1_xi": [],
        "team2_xi": [],
        "team1_confirmed": False,
        "team2_confirmed": False,
        "impact_pool": {},
        "source": "squad_seed",
    }

    # --- Source 1: IPLT20.com (primary) ---
    iplt20_result = await _try_iplt20(team1, team2)
    if iplt20_result:
        t1_xi = iplt20_result.get("team1_xi", [])
        t2_xi = iplt20_result.get("team2_xi", [])
        if len(t1_xi) >= 11 and len(t2_xi) >= 11:
            result["team1_xi"] = t1_xi[:11]
            result["team2_xi"] = t2_xi[:11]
            result["team1_confirmed"] = True
            result["team2_confirmed"] = True
            result["impact_pool"] = iplt20_result.get("impact_pool", {})
            result["source"] = "iplt20"
            logger.info("XI Cascade: IPLT20 returned confirmed XI for both teams")
            return result
        # Partial result — keep what we got, try other sources for missing team
        if len(t1_xi) >= 11:
            result["team1_xi"] = t1_xi[:11]
            result["team1_confirmed"] = True
        if len(t2_xi) >= 11:
            result["team2_xi"] = t2_xi[:11]
            result["team2_confirmed"] = True
        if result["team1_confirmed"] or result["team2_confirmed"]:
            result["source"] = "iplt20_partial"

    # --- Source 2: Cricbuzz (stealth fallback) ---
    if not result["team1_confirmed"] or not result["team2_confirmed"]:
        cricbuzz_result = await _try_cricbuzz(team1, team2)
        if cricbuzz_result:
            t1_xi = cricbuzz_result.get("team1_xi", [])
            t2_xi = cricbuzz_result.get("team2_xi", [])
            if not result["team1_confirmed"] and len(t1_xi) >= 11:
                result["team1_xi"] = t1_xi[:11]
                result["team1_confirmed"] = True
                result["source"] = "cricbuzz" if not result["team2_confirmed"] else result["source"]
            if not result["team2_confirmed"] and len(t2_xi) >= 11:
                result["team2_xi"] = t2_xi[:11]
                result["team2_confirmed"] = True
                if result["source"] == "squad_seed":
                    result["source"] = "cricbuzz"

    # --- Source 3: Google News RSS ---
    if not result["team1_confirmed"] or not result["team2_confirmed"]:
        news_result = await _try_news_rss(
            team1, team2, team1_abbrev, team2_abbrev,
        )
        if not result["team1_confirmed"] and news_result.get("team1_xi"):
            result["team1_xi"] = news_result["team1_xi"][:11]
            result["team1_confirmed"] = news_result.get("team1_confirmed", False)
            if result["source"] == "squad_seed":
                result["source"] = "news_rss"
        if not result["team2_confirmed"] and news_result.get("team2_xi"):
            result["team2_xi"] = news_result["team2_xi"][:11]
            result["team2_confirmed"] = news_result.get("team2_confirmed", False)
            if result["source"] == "squad_seed":
                result["source"] = "news_rss"

    # --- Source 4: SQUAD_SEED (local fallback) ---
    if not result["team1_xi"] or len(result["team1_xi"]) < 11:
        seed = _get_seed_names(team1)
        result["team1_xi"] = seed
        result["team1_confirmed"] = False
        logger.info("XI Cascade: using SQUAD_SEED fallback for %s", team1)

    if not result["team2_xi"] or len(result["team2_xi"]) < 11:
        seed = _get_seed_names(team2)
        result["team2_xi"] = seed
        result["team2_confirmed"] = False
        logger.info("XI Cascade: using SQUAD_SEED fallback for %s", team2)

    if not result["team1_confirmed"] and not result["team2_confirmed"]:
        result["source"] = "squad_seed"

    logger.info(
        "XI Cascade: final source=%s, t1_confirmed=%s, t2_confirmed=%s",
        result["source"], result["team1_confirmed"], result["team2_confirmed"],
    )
    return result


# ---------------------------------------------------------------------------
# Source implementations
# ---------------------------------------------------------------------------

async def _iplt20_session(team1: str, team2: str) -> dict[str, Any] | None:
    """Full IPLT20 Playwright session (runs inside ProactorEventLoop on Windows)."""
    from app.data.iplt20_scraper import IPLT20Scraper
    async with IPLT20Scraper() as scraper:
        return await scraper.get_playing_xi(team1, team2)


async def _try_iplt20(team1: str, team2: str) -> dict[str, Any] | None:
    """Try fetching playing XI from iplt20.com."""
    try:
        from app.data._playwright_windows import run_playwright
        return await run_playwright(_iplt20_session, team1, team2)
    except Exception as exc:
        logger.warning("XI Cascade: IPLT20 failed — %s", exc)
        return None


async def _cricbuzz_session(team1: str, team2: str) -> dict[str, Any] | None:
    """Full Cricbuzz Playwright session (runs inside ProactorEventLoop on Windows)."""
    import re
    from app.data.cricbuzz_scraper import CricbuzzScraper

    async with CricbuzzScraper() as scraper:
        # Find match ID from schedule page
        match_id = await _find_cricbuzz_match_id(scraper, team1, team2)
        if match_id:
            return await scraper.get_playing_xi(match_id)
        logger.info("XI Cascade: Cricbuzz — could not find match_id for %s vs %s", team1, team2)
        return None


async def _try_cricbuzz(team1: str, team2: str) -> dict[str, Any] | None:
    """Try fetching playing XI from Cricbuzz."""
    try:
        from app.data._playwright_windows import run_playwright
        return await run_playwright(_cricbuzz_session, team1, team2)
    except Exception as exc:
        logger.warning("XI Cascade: Cricbuzz failed — %s", exc)
    return None


async def _find_cricbuzz_match_id(
    scraper: Any, team1: str, team2: str,
) -> str | None:
    """
    Search Cricbuzz homepage/schedule for today's match between team1 and team2.
    Returns the numeric Cricbuzz match ID.
    """
    import re
    from playwright.async_api import Page

    if scraper._context is None:
        return None

    page: Page = await scraper._context.new_page()
    try:
        await page.goto(
            "https://www.cricbuzz.com/cricket-schedule/upcoming-series/ipl",
            wait_until="domcontentloaded", timeout=30000,
        )
        import asyncio
        await asyncio.sleep(0.8)

        content = await page.content()
        t1_short = team1.lower().split()[-1]  # "bengaluru", "hyderabad"
        t2_short = team2.lower().split()[-1]

        # Look for match links containing both team references
        links = re.findall(r'href="(/live-cricket-scores?/(\d+)/[^"]*)"', content)
        for href, mid in links:
            href_lower = href.lower()
            if t1_short in href_lower and t2_short in href_lower:
                return mid

        # Broader search: match cards with team names in text
        link_elements = await page.query_selector_all("a[href*='/live-cricket-scores/']")
        for link_el in link_elements:
            href = await link_el.get_attribute("href") or ""
            text = (await link_el.inner_text()).lower()
            if (t1_short in text or t1_short in href.lower()) and \
               (t2_short in text or t2_short in href.lower()):
                mid_match = re.search(r'/live-cricket-scores?/(\d+)/', href)
                if mid_match:
                    return mid_match.group(1)

    except Exception as exc:
        logger.debug("Cricbuzz match ID search failed: %s", exc)
    finally:
        await page.close()

    return None


async def _try_news_rss(
    team1: str, team2: str,
    team1_abbrev: str, team2_abbrev: str,
) -> dict[str, Any]:
    """Try fetching playing XI from Google News RSS."""
    result: dict[str, Any] = {
        "team1_xi": [],
        "team2_xi": [],
        "team1_confirmed": False,
        "team2_confirmed": False,
    }
    try:
        from app.data.live_xi_fetcher import fetch_confirmed_xi

        squad1 = SQUAD_SEED.get(team1, [])
        squad2 = SQUAD_SEED.get(team2, [])

        if squad1:
            roster1, confirmed1 = await fetch_confirmed_xi(team1_abbrev, team1, squad1)
            if confirmed1 and roster1:
                result["team1_xi"] = [p.get("name", p) if isinstance(p, dict) else p for p in roster1]
                result["team1_confirmed"] = True

        if squad2:
            roster2, confirmed2 = await fetch_confirmed_xi(team2_abbrev, team2, squad2)
            if confirmed2 and roster2:
                result["team2_xi"] = [p.get("name", p) if isinstance(p, dict) else p for p in roster2]
                result["team2_confirmed"] = True

    except Exception as exc:
        logger.warning("XI Cascade: News RSS failed — %s", exc)

    return result


def _get_seed_names(team_name: str) -> list[str]:
    """Get first 11 player names from SQUAD_SEED for a team."""
    squad = SQUAD_SEED.get(team_name, [])
    if not squad:
        # Try fuzzy match
        for key in SQUAD_SEED:
            if team_name.lower() in key.lower() or key.lower() in team_name.lower():
                squad = SQUAD_SEED[key]
                break
    return [p["name"] for p in squad[:11]]
