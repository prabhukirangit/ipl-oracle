"""
VenueStatsService — Cached player-venue stat fetcher.

Singleton pattern. Caches per player+venue to avoid re-fetching across 100 sims.
Max 3 concurrent ESPNcricinfo venue queries (semaphore). 1.5s delay per query.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Cache key: f"{player_name}:{venue_name}"
_cache: dict[str, dict[str, Any]] = {}
_semaphore = asyncio.Semaphore(3)

FALLBACK_STATS: dict[str, Any] = {
    "venue_affinity": 0.5,
    "innings": 0,
    "runs": 0,
    "avg": None,
    "sr": None,
    "source": "fallback",
}

# Mapping: venue_name → ESPNcricinfo ground_id
# Loaded lazily from skills/espncricinfo_ground_ids.json
_ground_id_map: dict[str, str] = {}


def _load_ground_ids() -> dict[str, str]:
    global _ground_id_map
    if _ground_id_map:
        return _ground_id_map

    import json
    from pathlib import Path

    skills_dir = Path(__file__).resolve().parents[4] / "skills"
    path = skills_dir / "espncricinfo_ground_ids.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        venues = data.get("venues", {})
        _ground_id_map = {k: str(v["ground_id"]) for k, v in venues.items()}
    except FileNotFoundError:
        logger.warning("espncricinfo_ground_ids.json not found at %s", path)
        _ground_id_map = {}

    return _ground_id_map


class VenueStatsService:
    """
    Singleton service for cached player-venue stats.

    All calls go through this service to prevent duplicate ESPNcricinfo fetches
    across 100 parallel simulations. Cache is session-scoped (in-memory).

    Usage:
        service = VenueStatsService.get_instance()
        stats = await service.get_player_venue_stats("Virat Kohli", "M. Chinnaswamy Stadium, Bengaluru")
    """

    _instance: "VenueStatsService | None" = None

    @classmethod
    def get_instance(cls) -> "VenueStatsService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        # Do not call directly — use get_instance()
        self._cache: dict[str, dict[str, Any]] = _cache

    async def get_player_venue_stats(
        self, player_name: str, venue: str
    ) -> dict[str, Any]:
        """
        Get venue stats for a player, using cache if available.

        Args:
            player_name: Full player name
            venue: Full venue name as in espncricinfo_ground_ids.json

        Returns:
            Dict with venue_affinity, innings, runs, avg, sr.
        """
        cache_key = f"{player_name}:{venue}"

        if cache_key in self._cache:
            logger.debug("VenueStatsService cache hit: %s", cache_key)
            return dict(self._cache[cache_key])

        async with _semaphore:
            # Double-check after acquiring semaphore (another coroutine may have populated)
            if cache_key in self._cache:
                return dict(self._cache[cache_key])

            result = await self._fetch_from_espn(player_name, venue)
            self._cache[cache_key] = result
            return dict(result)

    async def _fetch_from_espn(
        self, player_name: str, venue: str
    ) -> dict[str, Any]:
        """Fetch venue stats from ESPNcricinfo via Playwright scraper."""
        ground_ids = _load_ground_ids()
        ground_id = ground_ids.get(venue)

        if not ground_id:
            logger.debug(
                "No ESPNcricinfo ground_id for venue '%s' — using fallback for %s",
                venue, player_name,
            )
            return dict(FALLBACK_STATS)

        try:
            from app.data.playwright_scraper import ESPNCricinfoScraper

            async with ESPNCricinfoScraper() as scraper:
                # 1.5s delay for venue queries as per spec
                await asyncio.sleep(1.5)
                stats = await scraper.get_player_venue_stats(player_name, ground_id)

            if not stats or stats.get("innings", 0) == 0:
                logger.debug("No venue data found for '%s' at '%s'", player_name, venue)
                return dict(FALLBACK_STATS)

            logger.info(
                "VenueStats fetched: %s @ %s → %s innings, avg=%s",
                player_name, venue, stats.get("innings"), stats.get("avg"),
            )
            return stats

        except Exception as exc:
            logger.warning(
                "VenueStatsService fetch failed for '%s' at '%s': %s",
                player_name, venue, exc,
            )
            return dict(FALLBACK_STATS)

    def get_cached(self, player_name: str, venue: str) -> dict[str, Any] | None:
        """Return cached stats without fetching. Returns None if not cached."""
        key = f"{player_name}:{venue}"
        cached = self._cache.get(key)
        return dict(cached) if cached is not None else None

    def clear_cache(self) -> None:
        """Clear all cached venue stats. Useful for testing."""
        self._cache.clear()
        logger.debug("VenueStatsService cache cleared")

    def cache_size(self) -> int:
        """Return number of cached entries."""
        return len(self._cache)
