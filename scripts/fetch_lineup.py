"""
fetch_lineup.py — One-off script to fetch the announced playing XI after toss.

Run this once after the toss is announced (~30 min before match start).
Saves the confirmed XI + Impact Player pool to data/lineup_{match_id}.json.
The AgentFactory reads this file at spawn time to use confirmed XI over probable XI.

Usage:
    cd ipl-oracle
    uv run python scripts/fetch_lineup.py --match-id 12345 --team1 "Mumbai Indians" --team2 "Chennai Super Kings"

Output:
    backend/data/lineup_12345.json

If Cricbuzz scraping fails (Cloudflare), falls back to IPLT20.com.
If both fail, prints a warning and writes an empty lineup so you can fill it manually.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure the backend/app package is importable when run from the project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_DATA_DIR = _PROJECT_ROOT / "backend" / "data"


async def fetch_via_cricbuzz(match_id: str) -> dict | None:
    """Try to get the playing XI from Cricbuzz stealth scraper."""
    try:
        from app.data.cricbuzz_scraper import CricbuzzScraper

        async with CricbuzzScraper() as scraper:
            xi = await scraper.get_playing_xi(match_id)

        # If both XIs are non-empty, treat as success
        if xi.get("team1_xi") or xi.get("team2_xi"):
            logger.info("Cricbuzz: fetched playing XI for match %s", match_id)
            return xi
        logger.warning("Cricbuzz: returned empty XI for match %s", match_id)
    except Exception as exc:
        logger.warning("Cricbuzz scrape failed: %s", exc)
    return None


async def fetch_via_iplt20(match_id: str, team1: str, team2: str) -> dict | None:
    """
    Fallback: scrape IPLT20.com match centre for the playing XI.

    Uses Playwright (no stealth needed — not Cloudflare protected).
    """
    try:
        from playwright.async_api import async_playwright

        url = f"https://www.iplt20.com/match/2026/{match_id}"
        logger.info("Fetching lineup from IPLT20: %s", url)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            await page.goto(url, wait_until="networkidle", timeout=30_000)

            # Look for playing XI section — IPLT20 uses a table with player names
            # Selector may change season to season; adjust if needed.
            team_sections = await page.query_selector_all(".cb-player-name-highlight, .playing-xi-player")
            players = [await el.inner_text() for el in team_sections]

            await browser.close()

        if not players:
            logger.warning("IPLT20: no players found on page %s", url)
            return None

        # Split players roughly 50/50 between teams (best effort without team labels)
        mid = len(players) // 2
        return {
            "team1_xi": [p.strip() for p in players[:mid]],
            "team2_xi": [p.strip() for p in players[mid:]],
            "impact_pool": {},
            "source": "iplt20_fallback",
        }

    except Exception as exc:
        logger.warning("IPLT20 scrape failed: %s", exc)
    return None


def _empty_lineup(team1: str, team2: str) -> dict:
    """Return a skeleton lineup dict for manual filling."""
    return {
        "team1": team1,
        "team1_xi": [],
        "team2": team2,
        "team2_xi": [],
        "impact_pool": {team1: [], team2: []},
        "toss_winner": None,
        "toss_decision": None,
        "source": "manual",
        "note": "Both scrapers failed — fill this file manually before running simulation.",
    }


async def main(match_id: str, team1: str, team2: str) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _DATA_DIR / f"lineup_{match_id}.json"

    # Try Cricbuzz first, fall back to IPLT20
    lineup = await fetch_via_cricbuzz(match_id)
    if not lineup:
        lineup = await fetch_via_iplt20(match_id, team1, team2)
    if not lineup:
        logger.error(
            "Both scrapers failed. Writing empty lineup to %s — fill manually.", output_path
        )
        lineup = _empty_lineup(team1, team2)
    else:
        # Enrich with team names and metadata
        lineup["team1"] = team1
        lineup["team2"] = team2
        lineup.setdefault("toss_winner", None)
        lineup.setdefault("toss_decision", None)

    lineup["fetched_at"] = datetime.utcnow().isoformat() + "Z"
    lineup["match_id"] = match_id

    output_path.write_text(json.dumps(lineup, indent=2, ensure_ascii=False))
    logger.info("Lineup saved to %s", output_path)

    # Print summary
    t1_count = len(lineup.get("team1_xi", []))
    t2_count = len(lineup.get("team2_xi", []))
    print(f"\n{team1}: {t1_count} players")
    print(f"{team2}: {t2_count} players")
    if t1_count < 11 or t2_count < 11:
        print(
            "\n⚠️  Lineup is incomplete. Edit the file manually or re-run after the toss is announced."
        )
    else:
        print("\n✓ Full playing XI captured. Ready for simulation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch IPL playing XI after toss")
    parser.add_argument("--match-id", required=True, help="IPL match ID (from schedule)")
    parser.add_argument("--team1", required=True, help="Team 1 full name")
    parser.add_argument("--team2", required=True, help="Team 2 full name")
    args = parser.parse_args()

    asyncio.run(main(args.match_id, args.team1, args.team2))
