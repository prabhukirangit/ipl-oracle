"""
predict.py — CLI-only IPL match prediction (no frontend required).

Usage:
    cd ipl-oracle
    uv run python scripts/predict.py --team1 "Mumbai Indians" --team2 "Chennai Super Kings" \
        --venue "Wankhede Stadium, Mumbai" --date "2026-04-05T19:30:00"

    # Quick mode (fewer sims, faster):
    uv run python scripts/predict.py --team1 "MI" --team2 "CSK" --sims 10

    # With LLM narrative:
    uv run python scripts/predict.py --team1 "MI" --team2 "CSK" --llm

Options:
    --team1       Team 1 name (full or abbreviation)
    --team2       Team 2 name (full or abbreviation)
    --venue       Venue name (optional, defaults based on team1 home)
    --date        Match date-time ISO 8601 (optional, defaults to today 19:30)
    --pitch       Pitch type: batting | bowling | spin | balanced (default: balanced)
    --sims        Number of simulations 1-100 (default: 50)
    --llm         Enable LLM hybrid mode for narrative generation
    --json        Output raw JSON instead of formatted text
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))

# Load .env file for API keys
_env_path = _PROJECT_ROOT / ".env"
if _env_path.exists():
    import os as _os2
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _os2.environ.setdefault(_k.strip(), _v.strip())

# Force UTF-8 output on Windows
import io, os as _os
if _os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

from app.agents.player_agent import PlayerAgent
from app.agents.report_agent import ReportAgent, DISCLAIMER


# ---------------------------------------------------------------------------
# Team abbreviation mapping
# ---------------------------------------------------------------------------

TEAM_ABBREVS: dict[str, str] = {
    "MI": "Mumbai Indians",
    "CSK": "Chennai Super Kings",
    "RCB": "Royal Challengers Bengaluru",
    "KKR": "Kolkata Knight Riders",
    "SRH": "Sunrisers Hyderabad",
    "RR": "Rajasthan Royals",
    "DC": "Delhi Capitals",
    "GT": "Gujarat Titans",
    "PBKS": "Punjab Kings",
    "LSG": "Lucknow Super Giants",
}

TEAM_HOME_VENUES: dict[str, str] = {
    "Mumbai Indians": "Wankhede Stadium, Mumbai",
    "Chennai Super Kings": "MA Chidambaram Stadium, Chennai",
    "Royal Challengers Bengaluru": "M. Chinnaswamy Stadium, Bengaluru",
    "Kolkata Knight Riders": "Eden Gardens, Kolkata",
    "Sunrisers Hyderabad": "Rajiv Gandhi International Stadium, Hyderabad",
    "Rajasthan Royals": "Sawai Mansingh Stadium, Jaipur",
    "Delhi Capitals": "Arun Jaitley Stadium, Delhi",
    "Gujarat Titans": "Narendra Modi Stadium, Ahmedabad",
    "Punjab Kings": "Punjab Cricket Association Stadium, Mohali",
    "Lucknow Super Giants": "Ekana Cricket Stadium, Lucknow",
}

# Team strength profiles (same as backtest.py)
TEAM_PROFILES: dict[str, dict] = {
    "Sunrisers Hyderabad": {"bat_q": 1.18, "bowl_econ_scale": 1.04, "agg": 0.85, "pr": 0.72},
    "Royal Challengers Bengaluru": {"bat_q": 1.12, "bowl_econ_scale": 1.02, "agg": 0.80, "pr": 0.70},
    "Mumbai Indians": {"bat_q": 1.02, "bowl_econ_scale": 0.93, "agg": 0.72, "pr": 0.74},
    "Chennai Super Kings": {"bat_q": 0.98, "bowl_econ_scale": 0.96, "agg": 0.68, "pr": 0.80},
    "Gujarat Titans": {"bat_q": 1.00, "bowl_econ_scale": 0.94, "agg": 0.70, "pr": 0.71},
    "Kolkata Knight Riders": {"bat_q": 1.08, "bowl_econ_scale": 0.96, "agg": 0.76, "pr": 0.73},
    "Rajasthan Royals": {"bat_q": 1.04, "bowl_econ_scale": 0.96, "agg": 0.75, "pr": 0.70},
    "Punjab Kings": {"bat_q": 1.00, "bowl_econ_scale": 1.01, "agg": 0.73, "pr": 0.67},
    "Lucknow Super Giants": {"bat_q": 0.94, "bowl_econ_scale": 1.02, "agg": 0.65, "pr": 0.68},
    "Delhi Capitals": {"bat_q": 0.92, "bowl_econ_scale": 1.06, "agg": 0.63, "pr": 0.65},
}

_DEFAULT_TEAM_PROFILE = {"bat_q": 1.0, "bowl_econ_scale": 1.0, "agg": 0.70, "pr": 0.68}


def resolve_team(name: str) -> str:
    """Resolve abbreviation to full name, or return as-is."""
    return TEAM_ABBREVS.get(name.upper().strip(), name.strip())


def build_roster(team_name: str) -> list[dict]:
    """Build an 11-player roster scaled by team quality metrics."""
    tp = TEAM_PROFILES.get(team_name, _DEFAULT_TEAM_PROFILE)
    bq, be, agg, pr = tp["bat_q"], tp["bowl_econ_scale"], tp["agg"], tp["pr"]

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
        is_ar = role == "allrounder"

        profile = PlayerAgent.build_profile(
            name=f"{team_name}_{suffix}",
            team=team_name,
            role=role,
            batting_style=bat_style,
            bowling_style=bowl_style,
            is_foreign_player=is_foreign,
            career_batting_avg=bat_avg * bq if (is_batter or is_ar) else bat_avg,
            career_strike_rate=sr * min(bq, 1.15) if (is_batter or is_ar) else sr,
            career_bowling_economy=economy * be if (is_bowler or is_ar) else economy,
            aggression_index=agg + (0.06 if i <= 1 else -0.03 if is_bowler else 0.0),
            pressure_resilience=pr,
            venue_affinity=0.55,
            powerplay_specialization=0.58 if i <= 1 else 0.44,
            death_overs_specialization=0.58 if i >= 7 else 0.44,
        )
        players.append(profile)
    return players


async def run_prediction(
    team1: str, team2: str, venue: str, match_time: str,
    pitch_type: str, sim_count: int, use_llm: bool, output_json: bool,
) -> None:
    from app.simulation.match_engine import MatchConfig
    from app.simulation.parallel_runner import ParallelRunner

    config = MatchConfig(
        match_id=f"cli_{team1[:3]}_{team2[:3]}",
        team1=team1, team2=team2,
        venue=venue,
        match_date=match_time[:10],
        match_time=match_time,
        team1_players=build_roster(team1),
        team2_players=build_roster(team2),
        pitch_type=pitch_type,
        sim_count=sim_count,
    )

    print(f"\n{'='*60}")
    print(f"  IPL ORACLE — MATCH PREDICTION")
    print(f"{'='*60}")
    print(f"  {team1}  vs  {team2}")
    print(f"  Venue: {venue}")
    print(f"  Pitch: {pitch_type} | Sims: {sim_count}")
    print(f"{'='*60}")
    print(f"  Running {sim_count} simulations...", end="", flush=True)

    runner = ParallelRunner(config=config, sim_count=sim_count)
    results = await runner.run()

    if not results:
        print("\n  ERROR: All simulations failed.")
        return

    print(f" done ({len(results)} completed)")

    # Generate report
    report_agent = ReportAgent(simulation_id=config.match_id)
    report = report_agent.generate_report(
        team1=team1, team2=team2,
        sim_results=[r.to_dict() for r in results],
        venue=venue, match_state="CLI_PREDICTION",
    )

    if output_json:
        print(json.dumps(report, indent=2, default=str))
        return

    # Pretty-print results
    prediction = report.get("prediction", {})
    win_prob = report.get("win_probability", {})
    score_dist = report.get("score_distribution", {})

    winner = prediction.get("winner", "Unknown")
    confidence = prediction.get("confidence_pct", 0)
    conf_label = prediction.get("confidence_label", "")

    t1_wp = win_prob.get(team1, {})
    t2_wp = win_prob.get(team2, {})

    print(f"\n  PREDICTION")
    print(f"  {'-'*56}")

    # Win probability bars
    t1_pct = t1_wp.get("win_pct", 0)
    t2_pct = t2_wp.get("win_pct", 0)
    t1_bar = "#" * int(t1_pct / 2.5) + "." * (40 - int(t1_pct / 2.5))
    t2_bar = "#" * int(t2_pct / 2.5) + "." * (40 - int(t2_pct / 2.5))

    marker1 = " < WINNER" if winner == team1 else ""
    marker2 = " < WINNER" if winner == team2 else ""

    print(f"\n  {team1}")
    print(f"  {t1_bar}  {t1_pct:.1f}%{marker1}")
    t1_ci = t1_wp.get("confidence_interval_95", {})
    if t1_ci:
        print(f"  CI 95%: [{t1_ci.get('lower', 0):.1f}% – {t1_ci.get('upper', 0):.1f}%]")

    print(f"\n  {team2}")
    print(f"  {t2_bar}  {t2_pct:.1f}%{marker2}")
    t2_ci = t2_wp.get("confidence_interval_95", {})
    if t2_ci:
        print(f"  CI 95%: [{t2_ci.get('lower', 0):.1f}% – {t2_ci.get('upper', 0):.1f}%]")

    print(f"\n  Confidence: {conf_label} ({confidence:.0f}%)")

    # Score distribution
    for team_name in [team1, team2]:
        stats = score_dist.get(team_name, {})
        if stats:
            print(f"\n  {team_name} Score Distribution:")
            print(f"    Median: {stats.get('median', 'N/A')} | "
                  f"Mean: {stats.get('mean', 'N/A')} | "
                  f"Min: {stats.get('min', 'N/A')} | "
                  f"Max: {stats.get('max', 'N/A')}")

    # Predicted score
    pred_score = prediction.get("predicted_score")
    if pred_score:
        print(f"\n  Bold Prediction: {winner} to post ~{pred_score}")

    # LLM narrative
    if use_llm:
        print(f"\n  {'-'*56}")
        print(f"  LLM NARRATIVE (generating...)", end="", flush=True)
        narrative = await report_agent.generate_llm_narrative(report, team1, team2)
        if narrative:
            print(f"\r  LLM NARRATIVE                ")
            print(f"  {'-'*56}")
            for line in narrative.split("\n"):
                print(f"  {line}")
        else:
            print(f"\r  LLM narrative unavailable (check API key)")

    print(f"\n  {'-'*56}")
    print(f"  {DISCLAIMER}")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IPL Oracle CLI — Predict IPL match outcomes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python scripts/predict.py --team1 MI --team2 CSK
  uv run python scripts/predict.py --team1 "Mumbai Indians" --team2 "Chennai Super Kings" --sims 100
  uv run python scripts/predict.py --team1 RCB --team2 KKR --pitch batting --llm
  uv run python scripts/predict.py --team1 SRH --team2 RR --json
        """,
    )
    parser.add_argument("--team1", required=True, help="Team 1 (name or abbreviation)")
    parser.add_argument("--team2", required=True, help="Team 2 (name or abbreviation)")
    parser.add_argument("--venue", default=None, help="Venue name (defaults to team1 home)")
    parser.add_argument("--date", default=None, help="Match date-time ISO 8601 (default: today 19:30)")
    parser.add_argument("--pitch", default="balanced", choices=["batting", "bowling", "spin", "balanced"])
    parser.add_argument("--sims", type=int, default=50, help="Simulations to run (1-500, default 50)")
    parser.add_argument("--llm", action="store_true", help="Enable LLM for narrative generation")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    team1 = resolve_team(args.team1)
    team2 = resolve_team(args.team2)

    if team1 == team2:
        print("ERROR: team1 and team2 must be different")
        sys.exit(1)

    venue = args.venue or TEAM_HOME_VENUES.get(team1, "Wankhede Stadium, Mumbai")
    match_time = args.date or datetime.now().strftime("%Y-%m-%dT19:30:00")
    sims = max(1, min(500, args.sims))

    asyncio.run(run_prediction(team1, team2, venue, match_time, args.pitch, sims, args.llm, args.json))


if __name__ == "__main__":
    main()
