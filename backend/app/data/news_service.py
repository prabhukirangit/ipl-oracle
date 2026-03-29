"""
NewsService — Google News RSS parser for player/team availability news.

Free, no API key needed. Uses feedparser for RSS parsing.
Async interface via asyncio.to_thread() since feedparser is synchronous.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import feedparser

logger = logging.getLogger(__name__)

# Google News RSS endpoint
_GNEWS_URL = "https://news.google.com/rss/search?q={query}+cricket&hl=en-IN&gl=IN&ceid=IN:en"

# Keywords that indicate unavailability
_RULED_OUT_KEYWORDS = {"ruled out", "injured", "injury", "ruled-out", "unavailable", "out of"}
_DOUBTFUL_KEYWORDS = {"doubtful", "fitness test", "fitness concern", "uncertain", "in doubt", "not certain"}
_AVAILABLE_KEYWORDS = {"confirmed", "fit", "available", "playing", "included", "fit to play"}


def _parse_feed_sync(query: str) -> list[dict[str, str]]:
    """
    Synchronous feedparser call. Run via asyncio.to_thread.

    Returns list of article dicts with title, link, published, summary.
    """
    url = _GNEWS_URL.format(query=query.replace(" ", "+"))
    try:
        feed = feedparser.parse(url)
        entries = []
        for entry in feed.entries[:20]:  # cap at 20 articles
            entries.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "summary": entry.get("summary", ""),
            })
        return entries
    except Exception as exc:
        logger.error("feedparser error for query '%s': %s", query, exc)
        return []


async def fetch_news(query: str) -> list[dict[str, str]]:
    """
    Fetch Google News RSS articles for a query.

    Args:
        query: Search query (player name, team name, etc.)

    Returns:
        List of article dicts: {title, link, published, summary}
    """
    return await asyncio.to_thread(_parse_feed_sync, query)


def _check_availability_in_text(text: str) -> str:
    """
    Classify player availability from article text.

    Returns: 'ruled_out' | 'doubtful' | 'available'
    """
    lower = text.lower()

    # Check ruled out first (highest severity)
    for kw in _RULED_OUT_KEYWORDS:
        if kw in lower:
            return "ruled_out"

    # Check doubtful
    for kw in _DOUBTFUL_KEYWORDS:
        if kw in lower:
            return "doubtful"

    # Check confirmed available
    for kw in _AVAILABLE_KEYWORDS:
        if kw in lower:
            return "available"

    return "unknown"


async def check_player_availability(player_name: str) -> str:
    """
    Check a player's availability status from recent news.

    Args:
        player_name: Full player name (e.g. "Virat Kohli")

    Returns:
        'available' | 'doubtful' | 'ruled_out'
    """
    articles = await fetch_news(player_name)

    if not articles:
        logger.debug("No news found for '%s' — defaulting to available", player_name)
        return "available"

    # Aggregate signal across the most recent 5 articles
    signals: list[str] = []
    for article in articles[:5]:
        combined_text = article.get("title", "") + " " + article.get("summary", "")
        signal = _check_availability_in_text(combined_text)
        if signal != "unknown":
            signals.append(signal)

    if not signals:
        return "available"

    # Severity precedence: ruled_out > doubtful > available
    if "ruled_out" in signals:
        logger.info("Player '%s' flagged as ruled_out from news", player_name)
        return "ruled_out"
    if "doubtful" in signals:
        logger.info("Player '%s' flagged as doubtful from news", player_name)
        return "doubtful"
    return "available"


async def get_team_news(team_name: str) -> list[dict[str, str]]:
    """
    Fetch recent news articles for a team.

    Args:
        team_name: Full team name (e.g. "Mumbai Indians")

    Returns:
        List of article dicts
    """
    return await fetch_news(team_name + " IPL 2026")
