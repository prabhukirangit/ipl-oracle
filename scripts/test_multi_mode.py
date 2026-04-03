"""
Multi-mode simulation test — runs 3 sims each in PERSONA, HYBRID, and PROBABILISTIC modes.

Tests the full multi-agent ecosystem:
  - LLM persona calls (batting/bowling decisions via Anthropic)
  - Context rendering (narrative generation)
  - Communication bus (team talk)
  - Skill routing (12 skills)
  - Age/experience steering factors
  - Outcome resolver (intent-to-probability mapping)
"""

import asyncio
import sys
import time
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

# Load .env from project root
from dotenv import load_dotenv
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

from app.simulation.match_engine import MatchEngine, MatchConfig
from app.agents.player_agent import PlayerAgent
from app.services.squad_manager import SQUAD_SEED
from app.personas.persona_loader import load_persona


# Match fixtures to simulate
FIXTURES = [
    ("Mumbai Indians", "Chennai Super Kings", "Wankhede Stadium, Mumbai"),
    ("Royal Challengers Bengaluru", "Kolkata Knight Riders", "M. Chinnaswamy Stadium, Bengaluru"),
    ("Rajasthan Royals", "Gujarat Titans", "Sawai Mansingh Stadium, Jaipur"),
]

CURRENT_YEAR = 2026


def build_player_profiles(team_name: str, load_personas: bool = False) -> list[dict]:
    """Build player profiles from squad seed data with age/experience."""
    squad = SQUAD_SEED.get(team_name, [])[:11]
    profiles = []

    for p in squad:
        birth_year = p.get("birth_year")
        ipl_debut_year = p.get("ipl_debut_year")
        age = (CURRENT_YEAR - birth_year) if birth_year else 28
        experience_years = (CURRENT_YEAR - ipl_debut_year) if ipl_debut_year else 5

        profile = PlayerAgent.build_profile(
            name=p["name"],
            team=team_name,
            role=p.get("role", "allrounder"),
            batting_style=p.get("batting_style", "right_hand"),
            bowling_style=p.get("bowling_style", "none"),
            is_foreign_player=p.get("is_foreign", False),
            age=age,
            experience_years=experience_years,
        )

        # Load persona for LLM modes
        if load_personas:
            persona = load_persona(p["name"], profile)
            profile["persona"] = persona

        profiles.append(profile)

    return profiles


async def run_simulation(
    team1: str,
    team2: str,
    venue: str,
    mode: str,
    seed: int,
    sim_number: int,
) -> dict:
    """Run a single simulation and return results summary."""
    load_personas = mode in ("persona", "hybrid")
    team1_profiles = build_player_profiles(team1, load_personas=load_personas)
    team2_profiles = build_player_profiles(team2, load_personas=load_personas)

    config = MatchConfig(
        match_id=f"{mode}-{sim_number:03d}",
        team1=team1,
        team2=team2,
        venue=venue,
        match_date="2026-03-28",
        match_time="2026-03-28T19:30:00",
        team1_players=team1_profiles,
        team2_players=team2_profiles,
        simulation_mode=mode,
    )

    engine = MatchEngine(config, seed=seed)
    start_time = time.time()

    try:
        result = await engine.simulate()
        elapsed = time.time() - start_time

        # Count LLM calls from decision logs
        all_agents = list(engine._team1_agents.values()) + list(engine._team2_agents.values())
        persona_decisions = 0
        heuristic_decisions = 0
        for agent in all_agents:
            for d in agent.get_decision_log():
                if "persona" in d.get("decision_type", ""):
                    persona_decisions += 1
                elif "heuristic" in d.get("decision_type", ""):
                    heuristic_decisions += 1

        return {
            "success": True,
            "mode": mode,
            "fixture": f"{team1} vs {team2}",
            "venue": venue,
            "toss": f"{result.toss_winner} chose to {result.toss_decision}",
            "innings1": f"{result.innings1.team}: {result.innings1.total_score}/{result.innings1.wickets} ({result.innings1.overs_played} ov)",
            "innings2": f"{result.innings2.team}: {result.innings2.total_score}/{result.innings2.wickets} ({result.innings2.overs_played} ov)",
            "winner": result.winner,
            "win_type": result.win_type,
            "win_margin": result.win_margin,
            "key_moments": result.key_moments[:3],
            "elapsed_s": round(elapsed, 2),
            "persona_decisions": persona_decisions,
            "heuristic_decisions": heuristic_decisions,
            "total_balls_i1": len(result.innings1.balls),
            "total_balls_i2": len(result.innings2.balls),
            "comm_messages": len(engine._comm_bus.get_all()) if engine._comm_bus else 0,
        }

    except Exception as e:
        elapsed = time.time() - start_time
        import traceback
        return {
            "success": False,
            "mode": mode,
            "fixture": f"{team1} vs {team2}",
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "elapsed_s": round(elapsed, 2),
        }


def print_result(r: dict, idx: int):
    """Print a simulation result."""
    status = "PASS" if r["success"] else "FAIL"
    mode_tag = r["mode"].upper()
    print(f"\n  [{mode_tag}] Sim #{idx+1}: {r['fixture']} [{status}] ({r['elapsed_s']}s)")

    if not r["success"]:
        print(f"    ERROR: {r['error']}")
        print(f"    {r.get('traceback', '')[:500]}")
        return

    print(f"    Venue: {r['venue']}")
    print(f"    Toss: {r['toss']}")
    print(f"    {r['innings1']}")
    print(f"    {r['innings2']}")
    print(f"    Winner: {r['winner']} by {r['win_margin']} {r['win_type']}")
    print(f"    Balls: {r['total_balls_i1']} + {r['total_balls_i2']}")
    print(f"    Decisions: {r['persona_decisions']} persona, {r['heuristic_decisions']} heuristic")
    if r.get("comm_messages"):
        print(f"    Comm messages: {r['comm_messages']}")
    if r.get("key_moments"):
        for m in r["key_moments"]:
            print(f"      - {m}")


async def main():
    # Check LLM availability
    from app.services.llm_client import llm_client
    llm_ok = llm_client.is_enabled()

    print(f"\n{'='*70}")
    print(f"  IPL ORACLE — MULTI-MODE SIMULATION TEST")
    print(f"  LLM: {'ENABLED' if llm_ok else 'DISABLED'} (provider={llm_client.provider}, model={llm_client.model})")
    print(f"  Fixtures: {len(FIXTURES)}")
    print(f"{'='*70}")

    if not llm_ok:
        print("\n  WARNING: LLM is not enabled. PERSONA and HYBRID modes will fall back to heuristic.")
        print("  Set ANTHROPIC_API_KEY in .env to enable LLM calls.\n")

    all_results = []

    # ---- TIER C: PERSONA MODE (Full Multi-Agent Ecosystem) ----
    print(f"\n{'='*70}")
    print(f"  TIER C: PERSONA MODE (Full LLM per ball)")
    print(f"{'='*70}")

    for i, (t1, t2, venue) in enumerate(FIXTURES):
        r = await run_simulation(t1, t2, venue, mode="persona", seed=42 + i, sim_number=i + 1)
        all_results.append(r)
        print_result(r, i)

    # ---- TIER B: HYBRID MODE (LLM at high pressure only) ----
    print(f"\n{'='*70}")
    print(f"  TIER B: HYBRID MODE (LLM at pressure >= 0.85 only)")
    print(f"{'='*70}")

    for i, (t1, t2, venue) in enumerate(FIXTURES):
        r = await run_simulation(t1, t2, venue, mode="hybrid", seed=100 + i, sim_number=i + 1)
        all_results.append(r)
        print_result(r, i)

    # ---- Summary ----
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")

    passed = sum(1 for r in all_results if r["success"])
    failed = len(all_results) - passed
    total_persona = sum(r.get("persona_decisions", 0) for r in all_results)
    total_heuristic = sum(r.get("heuristic_decisions", 0) for r in all_results)
    total_comm = sum(r.get("comm_messages", 0) for r in all_results)
    total_time = sum(r.get("elapsed_s", 0) for r in all_results)

    print(f"  Total sims: {len(all_results)} ({passed} passed, {failed} failed)")
    print(f"  Total LLM persona decisions: {total_persona}")
    print(f"  Total heuristic decisions: {total_heuristic}")
    print(f"  Total comm messages: {total_comm}")
    print(f"  Total time: {total_time:.1f}s")

    persona_results = [r for r in all_results if r["mode"] == "persona"]
    hybrid_results = [r for r in all_results if r["mode"] == "hybrid"]

    if persona_results:
        avg_persona_time = sum(r["elapsed_s"] for r in persona_results) / len(persona_results)
        avg_persona_llm = sum(r.get("persona_decisions", 0) for r in persona_results) / len(persona_results)
        print(f"\n  PERSONA mode avg: {avg_persona_time:.1f}s/sim, {avg_persona_llm:.0f} LLM calls/sim")

    if hybrid_results:
        avg_hybrid_time = sum(r["elapsed_s"] for r in hybrid_results) / len(hybrid_results)
        avg_hybrid_llm = sum(r.get("persona_decisions", 0) for r in hybrid_results) / len(hybrid_results)
        print(f"  HYBRID mode avg: {avg_hybrid_time:.1f}s/sim, {avg_hybrid_llm:.0f} LLM calls/sim")

    if failed > 0:
        print(f"\n  FAILURES:")
        for r in all_results:
            if not r["success"]:
                print(f"    - [{r['mode'].upper()}] {r['fixture']}: {r['error']}")

    print(f"\n  {'ALL TESTS PASSED' if failed == 0 else f'{failed} TESTS FAILED'}")
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
