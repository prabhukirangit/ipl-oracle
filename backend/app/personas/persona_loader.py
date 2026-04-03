"""
PersonaLoader — Load or generate LLM personas for cricket players.

Lookup order:
1. Exact match: app/personas/{snake_case_name}.json
2. Fuzzy match: try common variations (initials, short names)
3. Fallback: auto-generate a generic persona from the player's profile stats

The persona dict is attached to the player's profile at spawn time and used
to construct system prompts for LLM calls in PERSONA and HYBRID modes.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PERSONA_DIR = Path(__file__).parent
_BASE_PERSONA_PATH = _PERSONA_DIR / "_base_persona.json"
_persona_cache: dict[str, dict[str, Any]] = {}


def _to_snake_case(name: str) -> str:
    """Convert 'Virat Kohli' → 'virat_kohli'."""
    name = re.sub(r"[^a-zA-Z0-9\s]", "", name)
    return "_".join(name.lower().split())


def load_persona(player_name: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Load a persona for the given player name.

    Args:
        player_name: Full player name (e.g. "Virat Kohli")
        profile: Player profile dict (used for fallback generation)

    Returns:
        Persona dict with system_prompt_template, batting/bowling personality, etc.
    """
    # Check cache first
    cache_key = _to_snake_case(player_name)
    if cache_key in _persona_cache:
        return _persona_cache[cache_key]

    # Try loading from file
    persona_path = _PERSONA_DIR / f"{cache_key}.json"
    if persona_path.exists():
        try:
            persona = json.loads(persona_path.read_text(encoding="utf-8"))
            _persona_cache[cache_key] = persona
            logger.info("Loaded persona for %s from %s", player_name, persona_path.name)
            return persona
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load persona %s: %s", persona_path, exc)

    # Fallback: generate from profile + base template
    persona = _generate_persona(player_name, profile or {})
    _persona_cache[cache_key] = persona
    logger.info("Generated generic persona for %s", player_name)
    return persona


def _generate_persona(player_name: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Generate a generic persona from a player's profile stats."""

    # Load base template
    try:
        base = json.loads(_BASE_PERSONA_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        base = {}

    role = profile.get("role", "allrounder")
    batting_style = profile.get("batting_style", "right_hand")
    bowling_style = profile.get("bowling_style", "none")
    team = profile.get("team", "Unknown Team")
    career = profile.get("career_stats", {})
    traits = profile.get("personality_traits", {})

    # Build batting personality from stats
    sr = career.get("strike_rate", 130)
    avg = career.get("batting_avg", 25)
    aggression = traits.get("aggression_index", 0.5)

    if sr > 150 and aggression > 0.7:
        approach = "explosive_striker"
        mental = f"Fearless approach. Looks to dominate from ball one. SR of {sr:.0f} shows intent to attack."
    elif sr > 140:
        approach = "aggressive_accumulator"
        mental = f"Strong striker (SR: {sr:.0f}) who builds before accelerating. Balances risk and reward."
    elif avg > 35:
        approach = "anchor"
        mental = f"Reliable anchor (avg: {avg:.0f}). Bats deep and takes responsibility for the innings."
    else:
        approach = "situational"
        mental = f"Adapts to the situation. Can attack or defend as needed."

    # Build bowling personality
    bowling_personality = None
    if role in ("bowler", "allrounder") and bowling_style != "none":
        eco = career.get("bowling_economy", 8.0)
        bowl_avg = career.get("bowling_avg", 30)
        if eco < 7:
            bowl_approach = f"Miserly {bowling_style} bowler (eco: {eco:.1f}). Builds pressure through dot balls."
        elif eco < 8.5:
            bowl_approach = f"Reliable {bowling_style} bowler (eco: {eco:.1f}). Good control with wicket-taking ability."
        else:
            bowl_approach = f"Attacking {bowling_style} bowler. Looks for wickets, can be expensive."

        bowling_personality = {
            "style": bowling_style,
            "approach": bowl_approach,
            "death_bowling": traits.get("death_overs_specialization", 0.5) > 0.6,
            "powerplay_specialist": traits.get("powerplay_specialization", 0.5) > 0.6,
        }

    hand = "left" if "left" in batting_style.lower() else "right"

    # Inject personality adjectives from SQUAD_SEED if available
    personality = profile.get("personality", "")
    personality_line = ""
    if personality:
        personality_line = f"Your playing character: {personality}. "

    system_prompt = (
        f"You are {player_name}, a professional IPL cricketer playing for {team}. "
        f"You bat {hand}-handed. {personality_line}{mental} "
        f"You make every decision as {player_name} would — with your specific strengths, "
        f"weaknesses, instincts, and competitive nature. "
        f"Stay in character. Think like a real T20 cricketer under match pressure."
    )

    persona = {
        "player_name": player_name,
        "player_key": _to_snake_case(player_name),
        "system_prompt_template": system_prompt,
        "batting_personality": {
            "approach": approach,
            "signature_shots": base.get("batting_personality", {}).get("signature_shots", []),
            "weakness_zones": [],
            "mental_model": mental,
            "powerplay_intent": "aggressive" if aggression > 0.6 else "steady",
            "death_overs_intent": "calculated_aggression",
            "chase_mentality": "calm_under_pressure" if traits.get("pressure_resilience", 0.5) > 0.6 else "can_feel_pressure",
        },
        "bowling_personality": bowling_personality,
        "communication_style": {
            "tone": "intense" if aggression > 0.7 else "calm" if aggression < 0.3 else "focused",
            "encouragement_pattern": "aggressive_pump_up" if aggression > 0.7 else "quiet_support",
            "under_pressure_talk": "rally_teammates" if traits.get("big_match_temperament", 0.5) > 0.6 else "focus_inward",
        },
        "is_generated": True,
    }

    return persona


def get_all_persona_names() -> list[str]:
    """Return names of all available custom persona files."""
    return [
        p.stem
        for p in _PERSONA_DIR.glob("*.json")
        if not p.name.startswith("_")
    ]


def clear_cache() -> None:
    """Clear the persona cache."""
    _persona_cache.clear()
