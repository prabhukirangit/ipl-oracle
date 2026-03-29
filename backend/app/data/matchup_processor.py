"""
Runs Above Average Replacement (RAAR) Matrix for IPL Oracle.

Converts raw career averages (which lack phase context) into impactful
situational metrics that better feed the MatchEngine and LLM Personas.
"""

from typing import Any

def compute_raar_score(runs: int, balls: int, phase: str = "middle_overs") -> float:
    """
    Computes to what degree a player's innings over/underperformed an
    Average Replacement Player in a specific phase.
    
    A 12-ball 28 in death overs has a drastically different RAAR than a 45-ball 55.
    """
    if balls == 0:
        return 0.0

    strike_rate = (runs / balls) * 100

    # These are baseline replacement-level expectations for an IPL context
    phase_baselines = {
        "powerplay": {"expected_sr": 135.0, "run_value_modifier": 1.2},
        "middle_overs": {"expected_sr": 125.0, "run_value_modifier": 1.0},
        "death_overs": {"expected_sr": 165.0, "run_value_modifier": 1.5},
    }

    baseline = phase_baselines.get(phase, phase_baselines["middle_overs"])
    expected_sr = baseline["expected_sr"]
    modifier = baseline["run_value_modifier"]

    # Calculate run difference vs replacement level over the same number of balls
    expected_runs = (expected_sr / 100.0) * balls
    runs_above_replacement = runs - expected_runs

    # Multiply by the phase's critical value modifier
    raar_impact = runs_above_replacement * modifier
    
    return round(raar_impact, 2)

def inject_raar_into_profile(player_profile: dict[str, Any]) -> dict[str, Any]:
    """
    Injects pre-calculated True Death-Overs Impact and Powerplay RAAR
    into a player's profile for the MatchEngine / LLM to use.
    """
    stats = player_profile.get("career_stats", {})
    avg = stats.get("batting_avg", 25.0)
    sr = stats.get("strike_rate", 130.0)
    
    # Simulate a generic 20-ball innings logic based on their career SR to derive base RAAR
    # In production, this would query the KuzuDB graph for every historical innings
    simulated_runs = (sr / 100.0) * 20
    
    true_death_impact = compute_raar_score(simulated_runs * 1.5, 20, "death_overs")
    powerplay_raar = compute_raar_score(simulated_runs * 1.1, 20, "powerplay")
    
    if "advanced_metrics" not in player_profile:
        player_profile["advanced_metrics"] = {}
        
    player_profile["advanced_metrics"]["true_death_overs_impact"] = true_death_impact
    player_profile["advanced_metrics"]["powerplay_raar"] = powerplay_raar
    
    return player_profile
