"""Quick simulation test — validates the engine runs end-to-end without errors."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.simulation.match_engine import MatchEngine, MatchConfig
from app.agents.player_agent import PlayerAgent
from app.services.squad_manager import SQUAD_SEED


def build_player_profiles(team_name: str) -> list[dict]:
    """Build player profiles from squad seed data."""
    squad = SQUAD_SEED.get(team_name, [])[:11]
    profiles = []
    current_year = 2026

    for p in squad:
        birth_year = p.get("birth_year")
        ipl_debut_year = p.get("ipl_debut_year")
        age = (current_year - birth_year) if birth_year else 28
        experience_years = (current_year - ipl_debut_year) if ipl_debut_year else 5

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
        profiles.append(profile)

    return profiles


async def run_test():
    team1 = "Mumbai Indians"
    team2 = "Chennai Super Kings"
    venue = "Wankhede Stadium, Mumbai"

    print(f"\n{'='*60}")
    print(f"  SIMULATION TEST: {team1} vs {team2}")
    print(f"  Venue: {venue}")
    print(f"  Mode: probabilistic (deterministic, seed=42)")
    print(f"{'='*60}\n")

    team1_profiles = build_player_profiles(team1)
    team2_profiles = build_player_profiles(team2)

    print(f"  {team1}: {len(team1_profiles)} players")
    for p in team1_profiles:
        age = p.get("age", "?")
        exp = p.get("experience_years", "?")
        print(f"    - {p['name']} ({p['role']}) | age={age}, exp={exp}yrs")

    print(f"\n  {team2}: {len(team2_profiles)} players")
    for p in team2_profiles:
        age = p.get("age", "?")
        exp = p.get("experience_years", "?")
        print(f"    - {p['name']} ({p['role']}) | age={age}, exp={exp}yrs")

    config = MatchConfig(
        match_id="test-001",
        team1=team1,
        team2=team2,
        venue=venue,
        match_date="2026-03-28",
        match_time="2026-03-28T19:30:00",
        team1_players=team1_profiles,
        team2_players=team2_profiles,
        simulation_mode="probabilistic",
    )

    engine = MatchEngine(config, seed=42)

    try:
        result = await engine.simulate()
        print(f"\n{'='*60}")
        print(f"  RESULT")
        print(f"{'='*60}")
        print(f"  Toss: {result.toss_winner} chose to {result.toss_decision}")
        print(f"  {result.innings1.team}: {result.innings1.total_score}/{result.innings1.wickets} ({result.innings1.overs_played} ov)")
        print(f"  {result.innings2.team}: {result.innings2.total_score}/{result.innings2.wickets} ({result.innings2.overs_played} ov)")
        print(f"  Winner: {result.winner} by {result.win_margin} {result.win_type}")
        print(f"\n  Innings 1 boundaries: {result.innings1.boundaries} fours, {result.innings1.sixes} sixes")
        print(f"  Innings 2 boundaries: {result.innings2.boundaries} fours, {result.innings2.sixes} sixes")

        if result.key_moments:
            print(f"\n  Key moments:")
            for m in result.key_moments:
                print(f"    - {m}")

        # Bowling figures
        print(f"\n  Innings 1 bowling:")
        for name, card in result.innings1.bowling_figures.items():
            print(f"    {name}: {card.wickets}/{card.runs_conceded} ({card.overs_bowled:.1f} ov, eco: {card.economy})")

        print(f"\n  Innings 2 bowling:")
        for name, card in result.innings2.bowling_figures.items():
            print(f"    {name}: {card.wickets}/{card.runs_conceded} ({card.overs_bowled:.1f} ov, eco: {card.economy})")

        print(f"\n  Fall of wickets (Innings 1):")
        for fow in result.innings1.fall_of_wickets:
            print(f"    {fow['wicket']}-{fow['score']} ({fow['batsman']}, {fow['over']})")

        print(f"\n  {result.disclaimer.encode('ascii', 'replace').decode()}")
        print(f"\n  SIMULATION PASSED SUCCESSFULLY")
        return True

    except Exception as e:
        print(f"\n  SIMULATION FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
