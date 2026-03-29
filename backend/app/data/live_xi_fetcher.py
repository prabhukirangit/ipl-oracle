"""
LiveXIFetcher — Fetch confirmed playing XI before simulation.

On match day (~1hr before toss), teams announce their XI.
This fetcher checks Google News RSS for confirmed XIs and cross-references
against SQUAD_SEED to build the actual roster.

Flow:
  1. Search Google News RSS for "<team> playing XI today IPL 2026"
  2. Parse player names from search results
  3. Cross-reference with SQUAD_SEED to get full profiles
  4. Fall back to SQUAD_SEED top-11 if no confirmed XI found
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Google News RSS endpoint (free, no API key)
_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"


async def fetch_confirmed_xi(
    team_abbrev: str,
    team_full_name: str,
    squad_seed: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """
    Try to fetch confirmed playing XI for a team.

    Returns:
        (roster, is_confirmed): roster is the 11-player list,
        is_confirmed is True if from live data, False if SQUAD_SEED fallback.
    """
    try:
        names = await _search_playing_xi(team_abbrev, team_full_name)
        if names and len(names) >= 11:
            roster = _match_names_to_seed(names[:11], squad_seed, team_full_name)
            if len(roster) >= 11:
                logger.info(
                    "LiveXI: confirmed XI for %s: %s",
                    team_abbrev,
                    [p["name"] for p in roster],
                )
                return roster[:11], True
            else:
                logger.info(
                    "LiveXI: found %d names for %s but only %d matched seed, falling back",
                    len(names), team_abbrev, len(roster),
                )
    except Exception as exc:
        logger.warning("LiveXI: failed to fetch XI for %s: %s", team_abbrev, exc)

    # Fallback to SQUAD_SEED top 11
    logger.info("LiveXI: using SQUAD_SEED fallback for %s", team_abbrev)
    return squad_seed[:11], False


async def _search_playing_xi(team_abbrev: str, team_full_name: str) -> list[str]:
    """Search Google News RSS for confirmed playing XI."""
    query = f"{team_full_name} playing XI today IPL 2026"
    url = _GOOGLE_NEWS_RSS.format(query=query.replace(" ", "+"))

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        resp.raise_for_status()
        return _parse_player_names_from_rss(resp.text, team_abbrev)


def _parse_player_names_from_rss(rss_xml: str, team_abbrev: str) -> list[str]:
    """
    Extract player names from RSS feed titles/descriptions.

    Looks for patterns like "Playing XI: Name1, Name2, ..." or numbered lists.
    """
    names: list[str] = []

    # Extract all <title> and <description> content
    texts = re.findall(r"<title[^>]*>(.*?)</title>", rss_xml, re.DOTALL)
    texts += re.findall(r"<description[^>]*>(.*?)</description>", rss_xml, re.DOTALL)

    for text in texts:
        # Clean HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&#39;", "'").replace("&quot;", '"')

        # Look for comma-separated player lists (common format)
        # Pattern: after "playing XI" or "lineup" or "XI:"
        xi_match = re.search(
            r"(?:playing\s*XI|lineup|XI\s*:)\s*[:–—-]?\s*(.+)",
            text, re.IGNORECASE,
        )
        if xi_match:
            players_text = xi_match.group(1)
            # Split by comma or numbered list
            found = [
                p.strip().rstrip(".")
                for p in re.split(r"[,;]|\d+\.\s*", players_text)
                if p.strip() and len(p.strip()) > 3
            ]
            if len(found) >= 8:  # Looks like a real XI list
                names.extend(found[:15])

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for n in names:
        clean = n.strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            unique.append(clean)

    return unique


def _match_names_to_seed(
    xi_names: list[str],
    squad_seed: list[dict[str, Any]],
    team_name: str,
) -> list[dict[str, Any]]:
    """
    Match parsed player names to SQUAD_SEED entries.

    Uses fuzzy matching: last-name match, first-name match, or substring.
    """
    from ..agents.player_agent import PlayerAgent

    matched: list[dict[str, Any]] = []
    used_seed_indices: set[int] = set()

    for xi_name in xi_names:
        best_match = _find_best_match(xi_name, squad_seed, used_seed_indices)
        if best_match is not None:
            idx, seed_player = best_match
            used_seed_indices.add(idx)
            profile = PlayerAgent.build_profile(
                name=seed_player["name"],
                team=team_name,
                role=seed_player.get("role", "allrounder"),
                batting_style=seed_player.get("batting_style", "right_hand"),
                bowling_style=seed_player.get("bowling_style", "none"),
                is_foreign_player=seed_player.get("is_foreign", False),
                age=2026 - seed_player.get("birth_year", 1998),
                experience_years=2026 - seed_player.get("ipl_debut_year", 2020),
            )
            matched.append(profile)

    return matched


def _find_best_match(
    name: str,
    squad: list[dict[str, Any]],
    used: set[int],
) -> tuple[int, dict] | None:
    """Find the best matching player in squad for a given name."""
    name_lower = name.lower().strip()
    name_parts = name_lower.split()

    for idx, player in enumerate(squad):
        if idx in used:
            continue
        seed_name = player["name"].lower()
        seed_parts = seed_name.split()

        # Exact match
        if name_lower == seed_name:
            return idx, player

        # Last name match (most common in news: "Kohli", "Bumrah")
        if name_parts and seed_parts:
            if name_parts[-1] == seed_parts[-1]:
                return idx, player
            # First name match
            if name_parts[0] == seed_parts[0] and len(name_parts[0]) > 3:
                return idx, player

        # Substring match
        if name_lower in seed_name or seed_name in name_lower:
            return idx, player

    return None
