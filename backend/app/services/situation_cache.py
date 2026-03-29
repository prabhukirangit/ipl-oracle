"""
SituationCache — Cache LLM decisions for similar match situations.

Keyed on (player_name, match_phase, pressure_bucket, over_bucket, score_bucket).
When a similar situation arises within the same simulation session, the cached
decision is returned with slight random perturbation instead of making a new
LLM call. Expected hit rate: 30-40% for routine balls.
"""

from __future__ import annotations

import copy
import random
from typing import Any


def _bucket(value: float, step: float) -> float:
    """Round to nearest bucket for cache key."""
    return round(value / step) * step


def _make_key(
    player_name: str,
    over: int,
    pressure: float,
    score: int,
    wickets: int,
) -> tuple:
    """Create a hashable cache key from match situation."""
    phase = "powerplay" if over <= 6 else "death" if over >= 16 else "middle"
    pressure_bucket = _bucket(pressure, 0.1)
    score_bucket = _bucket(score, 20)
    return (player_name, phase, pressure_bucket, score_bucket, wickets)


class SituationCache:
    """
    In-memory cache for LLM decisions within a simulation session.

    Usage:
        cache = SituationCache()
        key_args = {"player_name": "Virat Kohli", "over": 12, ...}

        cached = cache.get(**key_args)
        if cached:
            # Use cached decision with perturbation
            decision = cached
        else:
            decision = await skill.execute(...)
            cache.put(decision=decision, **key_args)
    """

    def __init__(self, max_size: int = 500) -> None:
        self._cache: dict[tuple, dict[str, Any]] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(
        self,
        player_name: str,
        over: int,
        pressure: float,
        score: int,
        wickets: int,
        rng: random.Random | None = None,
    ) -> dict[str, Any] | None:
        """
        Look up a cached decision for this situation.

        Returns a perturbation of the cached decision, or None on miss.
        """
        key = _make_key(player_name, over, pressure, score, wickets)
        cached = self._cache.get(key)

        if cached is None:
            self._misses += 1
            return None

        self._hits += 1
        # Return a slightly perturbed copy
        return self._perturb(cached, rng or random.Random())

    def put(
        self,
        decision: dict[str, Any],
        player_name: str,
        over: int,
        pressure: float,
        score: int,
        wickets: int,
    ) -> None:
        """Store a decision in the cache."""
        if len(self._cache) >= self._max_size:
            # Evict oldest entry (simple FIFO)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        key = _make_key(player_name, over, pressure, score, wickets)
        self._cache[key] = copy.deepcopy(decision)

    def _perturb(self, decision: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        """Apply slight random perturbation to a cached decision."""
        perturbed = copy.deepcopy(decision)

        # Perturb confidence by ±0.05
        if "confidence" in perturbed:
            perturbed["confidence"] = max(0.0, min(1.0,
                perturbed["confidence"] + rng.uniform(-0.05, 0.05)
            ))

        # Perturb risk_appetite by ±0.05
        if "risk_appetite" in perturbed:
            perturbed["risk_appetite"] = max(0.0, min(1.0,
                perturbed["risk_appetite"] + rng.uniform(-0.05, 0.05)
            ))

        return perturbed

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self.hit_rate:.1%}",
        }

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0
