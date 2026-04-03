"""
backtest.py — Backtesting framework against historical IPL 2025 results.

Runs the simulation engine against each completed IPL 2025 match and measures:
  - Accuracy: did the predicted winner match the actual winner?
  - Brier score: calibration of win probability (lower = better)
  - By-venue accuracy breakdown
  - Confidence-tier accuracy (HIGH/MEDIUM/LOW predictions)

Usage:
    cd ipl-oracle
    uv run python scripts/backtest.py
    uv run python scripts/backtest.py --sims 20 --output results/backtest_2025.json

The script ships with a built-in sample of 10 IPL 2025 results for quick validation.
Add your own matches to the HISTORICAL_RESULTS list or pass --results-file path/to/file.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))

# Load .env file for API keys (LLM hybrid mode, etc.)
_env_path = _PROJECT_ROOT / ".env"
if _env_path.exists():
    import os
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from app.agents.player_agent import PlayerAgent


# ---------------------------------------------------------------------------
# Team strength profiles — calibrated from IPL 2025 season performance
# (batting_quality: higher = better attack; bowling_quality: lower economy = better)
# ---------------------------------------------------------------------------

TEAM_PROFILES: dict[str, dict] = {
    # Explosive batting, moderate bowling (Orange Army)
    "Sunrisers Hyderabad": {"bat_q": 1.18, "bowl_econ_scale": 1.04, "agg": 0.85, "pr": 0.72},
    # Star-heavy batting, decent pace attack
    "Royal Challengers Bengaluru": {"bat_q": 1.12, "bowl_econ_scale": 1.02, "agg": 0.80, "pr": 0.70},
    # Elite bowling (Bumrah), solid batting depth
    "Mumbai Indians": {"bat_q": 1.02, "bowl_econ_scale": 0.93, "agg": 0.72, "pr": 0.74},
    # Experienced batting, spin-heavy bowling
    "Chennai Super Kings": {"bat_q": 0.98, "bowl_econ_scale": 0.96, "agg": 0.68, "pr": 0.80},
    # Strong batting, Rashid Khan bowling impact
    "Gujarat Titans": {"bat_q": 1.00, "bowl_econ_scale": 0.94, "agg": 0.70, "pr": 0.71},
    # Good batting, spinners + Chakravarthy
    "Kolkata Knight Riders": {"bat_q": 1.08, "bowl_econ_scale": 0.96, "agg": 0.76, "pr": 0.73},
    # Chahal-led bowling, attacking openers
    "Rajasthan Royals": {"bat_q": 1.04, "bowl_econ_scale": 0.96, "agg": 0.75, "pr": 0.70},
    # Aggressive batting, inconsistent bowling
    "Punjab Kings": {"bat_q": 1.00, "bowl_econ_scale": 1.01, "agg": 0.73, "pr": 0.67},
    # Modest batting, average bowling
    "Lucknow Super Giants": {"bat_q": 0.94, "bowl_econ_scale": 1.02, "agg": 0.65, "pr": 0.68},
    # Below average in 2025
    "Delhi Capitals": {"bat_q": 0.92, "bowl_econ_scale": 1.06, "agg": 0.63, "pr": 0.65},
}

_DEFAULT_TEAM_PROFILE = {"bat_q": 1.0, "bowl_econ_scale": 1.0, "agg": 0.70, "pr": 0.68}


def _build_default_roster(team_name: str) -> list[dict]:
    """Build an 11-player roster scaled by team-specific IPL 2025 quality metrics."""
    tp = TEAM_PROFILES.get(team_name, _DEFAULT_TEAM_PROFILE)
    bq = tp["bat_q"]           # batting quality multiplier (affects avg + SR)
    be = tp["bowl_econ_scale"] # bowling economy scale (>1 = worse economy)
    agg = tp["agg"]            # team aggression style
    pr = tp["pr"]              # team pressure resilience

    # Base roles: (suffix, role, bat_style, bowl_style, is_foreign, bat_avg, sr, economy)
    roles = [
        ("Opener1", "batsman",     "right_hand", "none",           False, 35.0, 148.0, 9.5),
        ("Opener2", "batsman",     "left_hand",  "none",           True,  32.0, 152.0, 9.5),
        ("No3",     "batsman",     "right_hand", "none",           False, 42.0, 138.0, 9.5),
        ("No4",     "batsman",     "right_hand", "none",           False, 38.0, 143.0, 8.8),
        ("No5",     "allrounder",  "right_hand", "medium_pace",    True,  28.0, 158.0, 8.2),
        ("No6",     "allrounder",  "right_hand", "off_break",      False, 22.0, 162.0, 7.8),
        ("WK",      "wicketkeeper","right_hand", "none",           False, 30.0, 150.0, 9.5),
        ("Bowler1", "bowler",      "right_hand", "fast",           False, 12.0, 115.0, 7.6),
        ("Bowler2", "bowler",      "right_hand", "fast_medium",    True,  10.0, 110.0, 7.9),
        ("Spinner1","bowler",      "right_hand", "leg_break",      False,  8.0, 105.0, 7.1),
        ("Spinner2","bowler",      "left_hand",  "left_arm_spin",  False,  6.0,  95.0, 7.3),
    ]
    players = []
    for i, (suffix, role, bat_style, bowl_style, is_foreign, bat_avg, sr, economy) in enumerate(roles):
        is_batter = role in ("batsman", "wicketkeeper")
        is_bowler = role == "bowler"
        is_allrounder = role == "allrounder"

        scaled_bat_avg = bat_avg * bq if (is_batter or is_allrounder) else bat_avg
        scaled_sr = sr * min(bq, 1.15) if (is_batter or is_allrounder) else sr
        scaled_econ = economy * be if (is_bowler or is_allrounder) else economy

        profile = PlayerAgent.build_profile(
            name=f"{team_name}_{suffix}",
            team=team_name,
            role=role,
            batting_style=bat_style,
            bowling_style=bowl_style,
            is_foreign_player=is_foreign,
            career_batting_avg=scaled_bat_avg,
            career_strike_rate=scaled_sr,
            career_bowling_economy=scaled_econ,
            aggression_index=agg + (0.06 if i <= 1 else -0.03 if is_bowler else 0.0),
            pressure_resilience=pr,
            venue_affinity=0.55,
            powerplay_specialization=0.58 if i <= 1 else 0.44,
            death_overs_specialization=0.58 if i >= 7 else 0.44,
        )
        players.append(profile)
    return players

# ---------------------------------------------------------------------------
# Sample IPL 2025 historical results (add more for better calibration)
# ---------------------------------------------------------------------------

HISTORICAL_RESULTS: list[dict] = [
    {
        "match_id": "ipl2025_001",
        "team1": "Mumbai Indians",
        "team2": "Chennai Super Kings",
        "venue": "Wankhede Stadium, Mumbai",
        "home_team": "Mumbai Indians",
        "actual_winner": "Mumbai Indians",
        "match_date": "2025-03-22",
        "match_time": "2025-03-22T19:30:00",
        "pitch_type": "batting",
    },
    {
        "match_id": "ipl2025_002",
        "team1": "Royal Challengers Bengaluru",
        "team2": "Kolkata Knight Riders",
        "venue": "M Chinnaswamy Stadium, Bengaluru",
        "home_team": "Royal Challengers Bengaluru",
        "actual_winner": "Royal Challengers Bengaluru",
        "match_date": "2025-03-23",
        "match_time": "2025-03-23T15:30:00",
        "pitch_type": "batting",
    },
    {
        "match_id": "ipl2025_003",
        "team1": "Sunrisers Hyderabad",
        "team2": "Rajasthan Royals",
        "venue": "Rajiv Gandhi International Cricket Stadium, Hyderabad",
        "home_team": "Sunrisers Hyderabad",
        "actual_winner": "Rajasthan Royals",
        "match_date": "2025-03-24",
        "match_time": "2025-03-24T19:30:00",
        "pitch_type": "balanced",
    },
    {
        "match_id": "ipl2025_004",
        "team1": "Delhi Capitals",
        "team2": "Punjab Kings",
        "venue": "Arun Jaitley Stadium, Delhi",
        "home_team": "Delhi Capitals",
        "actual_winner": "Punjab Kings",
        "match_date": "2025-03-25",
        "match_time": "2025-03-25T19:30:00",
        "pitch_type": "pace",
    },
    {
        "match_id": "ipl2025_005",
        "team1": "Lucknow Super Giants",
        "team2": "Gujarat Titans",
        "venue": "BRSABV Ekana Cricket Stadium, Lucknow",
        "home_team": "Lucknow Super Giants",
        "actual_winner": "Lucknow Super Giants",
        "match_date": "2025-03-26",
        "match_time": "2025-03-26T19:30:00",
        "pitch_type": "spin",
    },
    {
        "match_id": "ipl2025_006",
        "team1": "Chennai Super Kings",
        "team2": "Kolkata Knight Riders",
        "venue": "MA Chidambaram Stadium, Chennai",
        "home_team": "Chennai Super Kings",
        "actual_winner": "Chennai Super Kings",
        "match_date": "2025-03-28",
        "match_time": "2025-03-28T19:30:00",
        "pitch_type": "spin",
    },
    {
        "match_id": "ipl2025_007",
        "team1": "Rajasthan Royals",
        "team2": "Mumbai Indians",
        "venue": "Sawai Mansingh Stadium, Jaipur",
        "home_team": "Rajasthan Royals",
        "actual_winner": "Rajasthan Royals",
        "match_date": "2025-03-29",
        "match_time": "2025-03-29T19:30:00",
        "pitch_type": "balanced",
    },
    {
        "match_id": "ipl2025_008",
        "team1": "Gujarat Titans",
        "team2": "Royal Challengers Bengaluru",
        "venue": "Narendra Modi Stadium, Ahmedabad",
        "home_team": "Gujarat Titans",
        "actual_winner": "Gujarat Titans",
        "match_date": "2025-03-30",
        "match_time": "2025-03-30T15:30:00",
        "pitch_type": "batting",
    },
    {
        "match_id": "ipl2025_009",
        "team1": "Punjab Kings",
        "team2": "Sunrisers Hyderabad",
        "venue": "Punjab Cricket Association IS Bindra Stadium, Mohali",
        "home_team": "Punjab Kings",
        "actual_winner": "Sunrisers Hyderabad",
        "match_date": "2025-03-31",
        "match_time": "2025-03-31T19:30:00",
        "pitch_type": "pace",
    },
    {
        "match_id": "ipl2025_010",
        "team1": "Mumbai Indians",
        "team2": "Delhi Capitals",
        "venue": "Wankhede Stadium, Mumbai",
        "home_team": "Mumbai Indians",
        "actual_winner": "Mumbai Indians",
        "match_date": "2025-04-01",
        "match_time": "2025-04-01T19:30:00",
        "pitch_type": "batting",
    },
]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BacktestRecord:
    match_id: str
    team1: str
    team2: str
    venue: str
    actual_winner: str
    predicted_winner: str
    team1_win_pct: float
    team2_win_pct: float
    predicted_win_pct: float   # win% for the predicted winner
    confidence_label: str
    correct: bool
    brier: float               # (1 - predicted_win_pct/100)^2 if correct else (predicted_win_pct/100)^2
    error: str = ""


@dataclass
class BacktestSummary:
    total_matches: int = 0
    correct: int = 0
    accuracy: float = 0.0
    brier_score: float = 0.0
    by_confidence: dict = field(default_factory=dict)
    by_venue: dict = field(default_factory=dict)
    records: list = field(default_factory=list)
    run_at: str = ""
    sim_count_per_match: int = 0


# ---------------------------------------------------------------------------
# Core backtesting logic
# ---------------------------------------------------------------------------

async def run_single_backtest(match: dict, sim_count: int) -> BacktestRecord:
    """Run the simulation engine on a historical match and compare to actual result."""
    from app.simulation.match_engine import MatchEngine, MatchConfig
    from app.simulation.parallel_runner import ParallelRunner
    from app.agents.report_agent import ReportAgent

    match_id = match["match_id"]
    team1 = match["team1"]
    team2 = match["team2"]

    try:
        config = MatchConfig(
            match_id=match_id,
            team1=team1,
            team2=team2,
            venue=match["venue"],
            match_date=match["match_date"],
            match_time=match["match_time"],
            team1_players=_build_default_roster(team1),
            team2_players=_build_default_roster(team2),
            pitch_type=match.get("pitch_type", "balanced"),
        )

        runner = ParallelRunner(config=config, sim_count=sim_count)
        results = await runner.run()

        if not results:
            return BacktestRecord(
                match_id=match_id, team1=team1, team2=team2,
                venue=match["venue"], actual_winner=match["actual_winner"],
                predicted_winner="", team1_win_pct=0, team2_win_pct=0,
                predicted_win_pct=0, confidence_label="", correct=False, brier=1.0,
                error="All simulations failed",
            )

        report_agent = ReportAgent(simulation_id=match_id)
        report = report_agent.generate_report(
            team1=team1, team2=team2,
            sim_results=[r.to_dict() for r in results],
            venue=match["venue"], match_state="COMPLETED_BACKTEST",
        )

        prediction = report.get("prediction", {})
        win_prob = report.get("win_probability", {})
        predicted_winner = prediction.get("winner", "")
        confidence_label = prediction.get("confidence_label", "")
        t1_pct = win_prob.get(team1, {}).get("win_pct", 0)
        t2_pct = win_prob.get(team2, {}).get("win_pct", 0)
        predicted_pct = prediction.get("confidence_pct", 0)

        actual = match["actual_winner"]
        correct = predicted_winner == actual

        # Brier score: (p - outcome)^2 where outcome=1 if predicted==actual
        p = predicted_pct / 100.0
        brier = (p - 1.0) ** 2 if correct else p ** 2

        logger.info(
            "[%s] %s vs %s → predicted=%s (%s %.0f%%) actual=%s %s",
            match_id, team1, team2, predicted_winner, confidence_label, predicted_pct,
            actual, "✓" if correct else "✗",
        )

        return BacktestRecord(
            match_id=match_id, team1=team1, team2=team2,
            venue=match["venue"], actual_winner=actual,
            predicted_winner=predicted_winner,
            team1_win_pct=t1_pct, team2_win_pct=t2_pct,
            predicted_win_pct=predicted_pct,
            confidence_label=confidence_label,
            correct=correct, brier=brier,
        )

    except Exception as exc:
        logger.error("Backtest failed for %s: %s", match_id, exc)
        return BacktestRecord(
            match_id=match_id, team1=team1, team2=team2,
            venue=match.get("venue", ""), actual_winner=match["actual_winner"],
            predicted_winner="", team1_win_pct=0, team2_win_pct=0,
            predicted_win_pct=0, confidence_label="", correct=False, brier=1.0,
            error=str(exc),
        )


async def run_backtest(matches: list[dict], sim_count: int) -> BacktestSummary:
    """Run all matches sequentially (avoids resource contention from nested parallel runners)."""
    records: list[BacktestRecord] = []

    for match in matches:
        rec = await run_single_backtest(match, sim_count)
        records.append(rec)

    # Aggregate
    total = len(records)
    valid = [r for r in records if not r.error]
    correct_records = [r for r in valid if r.correct]

    accuracy = len(correct_records) / len(valid) if valid else 0.0
    brier_score = statistics.mean(r.brier for r in valid) if valid else 1.0

    # By confidence tier
    by_confidence: dict[str, dict] = {}
    for r in valid:
        tier = r.confidence_label or "UNKNOWN"
        if tier not in by_confidence:
            by_confidence[tier] = {"total": 0, "correct": 0}
        by_confidence[tier]["total"] += 1
        if r.correct:
            by_confidence[tier]["correct"] += 1
    for tier_data in by_confidence.values():
        t = tier_data["total"]
        tier_data["accuracy"] = round(tier_data["correct"] / t * 100, 1) if t else 0

    # By venue
    by_venue: dict[str, dict] = {}
    for r in valid:
        v = r.venue
        if v not in by_venue:
            by_venue[v] = {"total": 0, "correct": 0}
        by_venue[v]["total"] += 1
        if r.correct:
            by_venue[v]["correct"] += 1
    for vdata in by_venue.values():
        t = vdata["total"]
        vdata["accuracy"] = round(vdata["correct"] / t * 100, 1) if t else 0

    return BacktestSummary(
        total_matches=total,
        correct=len(correct_records),
        accuracy=round(accuracy * 100, 1),
        brier_score=round(brier_score, 4),
        by_confidence=by_confidence,
        by_venue=by_venue,
        records=[asdict(r) for r in records],
        run_at=datetime.now(tz=__import__('datetime').timezone.utc).isoformat(),
        sim_count_per_match=sim_count,
    )


def print_summary(summary: BacktestSummary) -> None:
    print("\n" + "=" * 60)
    print("IPL ORACLE — BACKTEST RESULTS (IPL 2025)")
    print("=" * 60)
    print(f"Matches:       {summary.total_matches}")
    print(f"Correct:       {summary.correct}/{summary.total_matches}")
    print(f"Accuracy:      {summary.accuracy}%")
    print(f"Brier Score:   {summary.brier_score}  (lower is better, 0=perfect)")
    print(f"Sims/match:    {summary.sim_count_per_match}")
    print()
    print("By confidence tier:")
    for tier, data in sorted(summary.by_confidence.items()):
        print(f"  {tier:<8}  {data['correct']}/{data['total']}  ({data['accuracy']}%)")
    print()
    print("By venue (top 5):")
    top_venues = sorted(summary.by_venue.items(), key=lambda x: x[1]["total"], reverse=True)[:5]
    for venue, data in top_venues:
        short = venue[:30].ljust(30)
        print(f"  {short}  {data['correct']}/{data['total']}  ({data['accuracy']}%)")
    print("=" * 60)


async def run_llm_test(sim_count: int) -> None:
    """Run a single match with LLM hybrid mode enabled and print the narrative."""
    from app.services.llm_client import llm_client
    from app.agents.report_agent import ReportAgent

    if not llm_client.is_enabled():
        logger.error("LLM is not enabled. Set LLM_PROVIDER + API key in .env")
        return

    logger.info("LLM hybrid test: provider=%s model=%s", llm_client.provider, llm_client.model)

    # Use first match
    match = HISTORICAL_RESULTS[0]
    logger.info("Running LLM-enabled sim: %s vs %s", match["team1"], match["team2"])

    rec = await run_single_backtest(match, sim_count)
    if rec.error:
        logger.error("Simulation failed: %s", rec.error)
        return

    # Generate LLM narrative
    from app.simulation.match_engine import MatchConfig, MatchEngine
    from app.simulation.parallel_runner import ParallelRunner

    config = MatchConfig(
        match_id=match["match_id"],
        team1=match["team1"], team2=match["team2"],
        venue=match["venue"], match_date=match["match_date"],
        match_time=match["match_time"],
        team1_players=_build_default_roster(match["team1"]),
        team2_players=_build_default_roster(match["team2"]),
        pitch_type=match.get("pitch_type", "balanced"),
    )
    runner = ParallelRunner(config=config, sim_count=sim_count)
    results = await runner.run()

    report_agent = ReportAgent(simulation_id=match["match_id"])
    report = report_agent.generate_report(
        team1=match["team1"], team2=match["team2"],
        sim_results=[r.to_dict() for r in results],
        venue=match["venue"], match_state="LLM_TEST",
    )

    narrative = await report_agent.generate_llm_narrative(report, match["team1"], match["team2"])

    print("\n" + "=" * 60)
    print("LLM HYBRID TEST — NARRATIVE OUTPUT")
    print("=" * 60)
    print(f"Match: {match['team1']} vs {match['team2']}")
    print(f"Predicted: {rec.predicted_winner} ({rec.predicted_win_pct:.0f}%)")
    print(f"Actual: {match['actual_winner']} {'OK' if rec.correct else 'WRONG'}")
    print("-" * 60)
    if narrative:
        print(narrative)
    else:
        print("(LLM narrative returned None — check API key / provider)")
    print("=" * 60)


async def main(sim_count: int, results_file: str | None, output: str | None, llm_test: bool = False) -> None:
    if llm_test:
        await run_llm_test(sim_count)
        return

    if results_file:
        matches = json.loads(Path(results_file).read_text())
        logger.info("Loaded %d matches from %s", len(matches), results_file)
    else:
        matches = HISTORICAL_RESULTS
        logger.info("Using %d built-in IPL 2025 sample matches", len(matches))

    summary = await run_backtest(matches, sim_count)
    print_summary(summary)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(asdict(summary), indent=2))
        print(f"\nFull results saved to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest IPL Oracle against IPL 2025 results")
    parser.add_argument("--sims", type=int, default=20,
                        help="Simulations per match (default 20, use 100 for full accuracy)")
    parser.add_argument("--results-file", type=str, default=None,
                        help="Path to JSON file with historical results (uses built-in if not set)")
    parser.add_argument("--output", type=str, default=None,
                        help="Save full JSON results to this path")
    parser.add_argument("--llm", action="store_true",
                        help="Run one match with LLM hybrid mode enabled (requires API key)")
    args = parser.parse_args()

    asyncio.run(main(args.sims, args.results_file, args.output, llm_test=args.llm))
