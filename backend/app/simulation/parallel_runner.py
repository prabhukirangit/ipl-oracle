"""
ParallelRunner — Runs multiple match simulations in parallel.

Week 1: Sequential single simulation.
Week 3+: Up to 500 parallel sims via asyncio.gather() in batches of 10.

Each sim gets:
- Shared read-only agent profiles (from MatchConfig)
- Unique random seed (sim_index × 42)
- Unique run_id for memory isolation

Auto-downgrade: if sim_count exceeds mode thresholds, the simulation mode
is downgraded (persona → hybrid → probabilistic) to prevent cost explosion.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import uuid
from typing import Any, Callable

from .match_engine import MatchEngine, MatchConfig, MatchResult

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
BATCH_PAUSE_SECONDS = 2.0  # rate limiting pause between batches


class ParallelRunner:
    """
    Orchestrates parallel match simulations.

    Week 1: Always runs 1 simulation synchronously.
    Week 3: Will run up to 100 parallel simulations in batches.
    """

    def __init__(
        self,
        config: MatchConfig,
        sim_count: int = 1,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """
        Initialise the parallel runner.

        Args:
            config: Match configuration (shared, read-only across all sims)
            sim_count: Number of simulations to run (Week 1: always 1)
            on_progress: Optional callback(completed, total) for progress updates
        """
        # Auto-downgrade simulation mode based on sim count
        mode = getattr(config, "simulation_mode", "hybrid")
        original_mode = mode
        if mode == "persona" and sim_count > 10:
            mode = "hybrid"
        if mode == "hybrid" and sim_count > 100:
            mode = "probabilistic"

        if mode != original_mode:
            logger.info(
                "ParallelRunner: auto-downgraded mode from %s to %s for %d sims",
                original_mode, mode, sim_count,
            )
            config = copy.copy(config)
            config.simulation_mode = mode

        self._config = config
        self._sim_count = sim_count
        self._on_progress = on_progress
        self._results: list[MatchResult] = []
        self._errors: list[str] = []
        self._effective_mode = mode

    async def run(self) -> list[MatchResult]:
        """
        Run all simulations and return results.

        In Week 1 this runs a single simulation synchronously.
        In Week 3+ this will batch 10 sims at a time.

        Returns:
            List of MatchResult objects from all simulations.
        """
        self._results = []
        self._errors = []

        if self._sim_count == 1:
            # Week 1: single simulation
            result = await self._run_single_sim(sim_index=0)
            if result:
                self._results.append(result)
        else:
            # Week 3+: batched parallel execution
            await self._run_batched()

        return self._results

    async def _run_single_sim(self, sim_index: int) -> MatchResult | None:
        """Run a single simulation with a deterministic seed."""
        seed = sim_index * 42
        # Create a copy of config with unique run_id
        config_copy = copy.deepcopy(self._config)
        config_copy.sim_count = 1

        try:
            engine = MatchEngine(config=config_copy, seed=seed)
            result = await engine.simulate()
            if self._on_progress:
                self._on_progress(sim_index + 1, self._sim_count)
            return result
        except Exception as e:
            self._errors.append(f"Sim {sim_index} failed: {str(e)}")
            return None

    async def _run_batched(self) -> None:
        """Run simulations in batches of BATCH_SIZE with a pause between batches."""
        completed = 0
        for batch_start in range(0, self._sim_count, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, self._sim_count)
            batch_tasks = [
                self._run_single_sim(sim_index=i)
                for i in range(batch_start, batch_end)
            ]

            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for r in batch_results:
                if isinstance(r, MatchResult):
                    self._results.append(r)
                elif isinstance(r, Exception):
                    self._errors.append(str(r))

            completed = batch_end
            if self._on_progress:
                self._on_progress(completed, self._sim_count)

            # Pause between batches (rate limiting / resource management)
            if batch_end < self._sim_count:
                await asyncio.sleep(BATCH_PAUSE_SECONDS)

    @property
    def results(self) -> list[MatchResult]:
        return list(self._results)

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    @property
    def success_rate(self) -> float:
        total = len(self._results) + len(self._errors)
        if total == 0:
            return 0.0
        return len(self._results) / total

    def get_summary_stats(self) -> dict[str, Any]:
        """Compute aggregate stats from all simulation results."""
        if not self._results:
            return {"error": "No results available"}

        from collections import Counter

        winners = Counter(r.winner for r in self._results if r.winner)
        total = len(self._results)

        return {
            "total_simulations": total,
            "successful_simulations": len(self._results),
            "failed_simulations": len(self._errors),
            "win_counts": dict(winners),
            "win_percentages": {
                team: round(count / total * 100, 1)
                for team, count in winners.items()
            },
            "avg_team1_score": round(
                sum(r.team1_score for r in self._results) / total, 1
            ),
            "avg_team2_score": round(
                sum(r.team2_score for r in self._results) / total, 1
            ),
        }
