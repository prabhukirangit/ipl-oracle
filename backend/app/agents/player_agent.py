"""
PlayerAgent — Autonomous agent for each IPL squad member.

Implements probabilistic bat() and bowl() decision functions.
Probability distributions shaped by 25+ factors including:
  - Career stats, venue affinity, form, fatigue
  - Age & experience (veterans resist pressure; rookies are volatile)
  - Boundary asymmetry, dew, pitch conditions
  - Auction hangover, left-arm matchups, death specialist reputation
  - Core strategy modifiers (collapse contagion, anchor penalty, franchise clutch)
  - Captain field placement interception
"""

from __future__ import annotations

import random
from typing import Any
from dataclasses import dataclass, field

from .base_agent import BaseAgent
from .captain_agent import FieldState


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BallContext:
    """Context passed to bat() and bowl() for each ball."""
    over: int                   # 0-indexed over number (0-19)
    ball: int                   # 0-indexed ball in over (0-5)
    batting_team_score: int     # current innings score
    wickets_fallen: int         # wickets lost so far
    target: int | None          # chase target, None if first innings
    pressure_index: float       # 0-1 pressure float (recomputed each ball)
    pitch_condition: dict       # from PitchAgent.get_condition(over)
    weather_condition: dict     # from WeatherAgent.get_conditions()
    batsman_fatigue: float      # 0-1 (0 = fresh, 1 = exhausted)
    bowler_fatigue: float       # 0-1
    is_batsman_home: bool       # home advantage for batsman
    is_bowler_home: bool        # home advantage for bowler
    balls_faced_this_innings: int  # balls this batsman has faced in this innings
    partnership_runs: int       # runs in current partnership
    required_run_rate: float    # required RR for chasing team (0 if first innings)
    current_run_rate: float     # current run rate
    dew_factor: float = 1.0     # NEW Week 1: dew impact on bowling (0.7-1.0)
    boundary_asymmetry_factor: float = 1.0  # NEW Week 1: directional boundary difficulty
    bowler_economy: float = 8.5   # current bowler's career economy rate
    bowler_bowling_avg: float = 30.0  # current bowler's career bowling average
    match_index: int = 1        # NEW Week 2: Match number in tournament (for decay functions)
    bowler_style: str = "right_arm_pace" # NEW Week 2: Bowling style for left-arm matchups
    umpire_strictness: float = 1.0       # NEW: Umpire decision variance multiplier (0.8 - 1.2)
    bowler_death_spec: float = 0.5       # NEW: Pre-ball fear factor for death specialists
    
    # Core Game & Strategy Architecture Modifiers
    is_post_timeout: bool = False               # Intent shift post strategic timeout
    is_17th_over: bool = False                  # Huge leverage point for death overs
    captain_defensive_tendency: float = 0.5     # Dictates field spreads
    batting_collapse_active: bool = False       # Two wickets in 6 balls triggers contagion
    anchor_penalty_active: bool = False         # Partner batting slow forces this batter to hit
    franchise_clutch_factor: float = 0.5        # Baseline 0.5; high for CSK/MI, low for PBKS
    fielding_conversion_probability: float = 0.5 # Drop catch variance
    lower_order_strike_independence: bool = False # Bowlers hitting freely without intent fear
    over_rate_pressure_active: bool = False     # Fielders brought in due to slow over rate
    field_state: FieldState | None = None       # NEW: On-field fielding positions


@dataclass
class BallOutcome:
    """Result of a single ball."""
    runs: int                   # runs scored (0-6)
    is_wicket: bool             # did a wicket fall?
    is_wide: bool               # wide delivery
    is_no_ball: bool            # no-ball
    is_boundary: bool           # 4 runs
    is_six: bool                # 6 runs
    dismissal_type: str | None  # e.g. 'caught', 'bowled', 'lbw', 'run_out', None
    shot_type: str              # e.g. 'drive', 'pull', 'cut', 'dot', 'defended'
    delivery_type: str          # e.g. 'outswing', 'googly', 'yorker', 'bouncer'
    pressure_index: float       # pressure at moment of this ball
    confidence: float           # how certain the probabilistic model is (0-1)
    notes: str                  # human-readable narrative


# ---------------------------------------------------------------------------
# Player outcome probability constants
# ---------------------------------------------------------------------------

# Base probability weights for batting outcomes (calibrated for T20 cricket).
# Real IPL average: dot ~34%, single ~34%, two ~8%, three ~1.5%, boundary ~13%, six ~4%, wicket ~5.5%
# These are neutral-player weights. All adjustments should be small (±0.03 max per modifier).
BASE_BATTING_WEIGHTS = {
    "dot": 0.34,
    "single": 0.34,
    "two": 0.08,
    "three": 0.015,
    "boundary": 0.13,
    "six": 0.04,
    "wicket": 0.055,
}

SHOT_TYPES_BY_OUTCOME = {
    "dot": ["defended", "left_alone", "blocked", "beaten"],
    "single": ["driven", "flicked", "nudged", "glanced", "tapped"],
    "two": ["driven_hard", "hit_to_gap", "quick_single_repeated"],
    "three": ["hit_to_deep", "misfield"],
    "boundary": ["drive", "pull", "cut", "sweep", "flick_boundary"],
    "six": ["lofted_drive", "pulled_six", "slog", "reverse_sweep_six"],
    "wicket": ["caught", "bowled", "lbw", "run_out", "stumped"],
}

DELIVERY_TYPES = [
    "outswinger", "inswinger", "off_cutter", "leg_cutter",
    "offbreak", "legbreak", "googly", "doosra",
    "yorker", "bouncer", "slower_ball", "full_toss"
]

DISMISSAL_TYPES_BY_BOWLER_TYPE = {
    "pace": ["caught", "bowled", "lbw", "caught_behind", "run_out"],
    "spin": ["caught", "stumped", "lbw", "bowled", "run_out"],
}


# ---------------------------------------------------------------------------
# PlayerAgent
# ---------------------------------------------------------------------------

class PlayerAgent(BaseAgent):
    """
    Autonomous agent representing one IPL squad player.

    Profile is set at factory spawn and is READ-ONLY during simulation.
    Mutable state (fatigue, form, balls_faced) is in the simulation MatchState.
    """

    def __init__(
        self,
        profile: dict[str, Any],
        run_id: str | None = None,
    ) -> None:
        """
        Initialise PlayerAgent.

        Args:
            profile: Player data dict (see build_profile() for schema)
            run_id: Simulation run ID for memory isolation
        """
        super().__init__(agent_type="player", profile=profile, run_id=run_id)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def build_profile(
        cls,
        name: str,
        team: str,
        role: str,
        batting_style: str = "right_hand",
        bowling_style: str = "none",
        is_foreign_player: bool = False,
        career_batting_avg: float = 25.0,
        career_strike_rate: float = 130.0,
        career_bowling_economy: float = 8.5,
        career_bowling_avg: float = 30.0,
        last_5_scores: list[int] | None = None,
        last_5_bowling_figs: list[str] | None = None,
        venue_batting_avg: float | None = None,
        venue_strike_rate: float | None = None,
        aggression_index: float = 0.60,
        pressure_resilience: float = 0.65,
        form_confidence: float = 0.65,
        venue_affinity: float = 0.50,
        big_match_temperament: float = 0.65,
        fatigue_level: float = 0.20,
        injury_risk: float = 0.10,
        spin_vulnerability: float = 0.40,
        pace_vulnerability: float = 0.35,
        powerplay_specialization: float = 0.50,
        death_overs_specialization: float = 0.50,
        is_impact_player_eligible: bool = False,
        availability_status: str = "confirmed",
        **extra_fields: Any,
    ) -> dict[str, Any]:
        """
        Build a standardised player profile dict.

        This is used by AgentFactory (Week 2) or test harnesses (Week 1).
        """
        return {
            "name": name,
            "team": team,
            "role": role,
            "batting_style": batting_style,
            "bowling_style": bowling_style,
            "is_foreign_player": is_foreign_player,
            "career_stats": {
                "batting_avg": career_batting_avg,
                "strike_rate": career_strike_rate,
                "bowling_economy": career_bowling_economy,
                "bowling_avg": career_bowling_avg,
            },
            "recent_form": {
                "last_5_scores": last_5_scores or [],
                "last_5_bowling_figs": last_5_bowling_figs or [],
            },
            "venue_stats": {
                "batting_avg": venue_batting_avg or career_batting_avg,
                "strike_rate": venue_strike_rate or career_strike_rate,
                "has_venue_data": venue_batting_avg is not None,
            },
            "personality_traits": {
                "aggression_index": aggression_index,
                "pressure_resilience": pressure_resilience,
                "form_confidence": form_confidence,
                "venue_affinity": venue_affinity,
                "big_match_temperament": big_match_temperament,
                "fatigue_level": fatigue_level,
                "injury_risk": injury_risk,
                "spin_vulnerability": spin_vulnerability,
                "pace_vulnerability": pace_vulnerability,
                "powerplay_specialization": powerplay_specialization,
                "death_overs_specialization": death_overs_specialization,
            },
            "impact_player": {
                "is_eligible": is_impact_player_eligible,
                "has_been_used": False,
            },
            "availability_status": availability_status,
            "auction_price_cr": extra_fields.pop("auction_price_cr", 0.0),
            "age": extra_fields.pop("age", 28),
            "experience_years": extra_fields.pop("experience_years", 5),
            **extra_fields,
        }

    # ------------------------------------------------------------------
    # Mathematical Decay Handlers
    # ------------------------------------------------------------------

    def get_expectation_tax(self, match_index: int) -> float:
        """
        Price-Tag Burden (Auction Hangover):
        Expensive marquee signings (e.g., ₹15cr+) receive an artificial error rate on
        their confidence during the first 3-4 matches. Decays exponentially.
        """
        auction_price = self._profile.get("auction_price_cr", 0.0)
        if auction_price < 15.0:
            return 1.0  # Normal, no tax
            
        import math
        base_tax = 0.15 * (auction_price / 15.0)  # +15% error rate for a 15cr player
        decay = math.exp(-match_index / 7.0)
        return 1.0 + (base_tax * decay)

    # ------------------------------------------------------------------
    # Batting decision function
    # ------------------------------------------------------------------

    def bat(self, ball_context: BallContext, rng: random.Random | None = None) -> BallOutcome:
        """
        Simulate this player's response to a delivery as batsman.

        Probability distributions shaped by 25+ factors including:
        - aggression_index, pressure_resilience, venue_affinity, fatigue
        - experience_years: veterans (10+) fewer wickets; rookies (<=2) more volatile
        - age: 37+ lose boundary hitting ability gradually
        - home advantage, form_confidence, auction hangover
        - boundary_asymmetry_factor, dew_factor, left-arm matchups
        - death specialist reputation, collapse contagion, anchor penalty
        - captain field placement interception

        Args:
            ball_context: All situational context for this delivery
            rng: Optional seeded Random instance for reproducibility

        Returns:
            BallOutcome describing what happened on this ball
        """
        if rng is None:
            rng = random.Random()

        traits = self._profile["personality_traits"]
        career = self._profile["career_stats"]
        venue = self._profile["venue_stats"]

        # -- Build adjusted probability weights --
        weights = dict(BASE_BATTING_WEIGHTS)

        # Aggression modifier: high aggression shifts probability to boundaries/sixes
        # Capped to ±0.03 per modifier to keep distribution realistic
        aggression = traits["aggression_index"]
        weights["boundary"] += (aggression - 0.5) * 0.06
        weights["six"] += (aggression - 0.5) * 0.03
        weights["dot"] -= (aggression - 0.5) * 0.05
        weights["single"] -= (aggression - 0.5) * 0.02

        # Strike rate modifier: normalise around typical IPL SR of 140
        sr_norm = (career["strike_rate"] - 140.0) / 100.0  # range roughly -0.4 to +0.6
        weights["boundary"] += sr_norm * 0.04
        weights["six"] += sr_norm * 0.02
        weights["dot"] -= sr_norm * 0.03

        # Venue affinity modifier
        venue_mod = (traits["venue_affinity"] - 0.5) * 0.04
        weights["boundary"] += venue_mod
        weights["dot"] -= venue_mod

        # Form confidence modifier combined with Price-Tag Burden (Auction Hangover)
        expectation_tax = self.get_expectation_tax(ball_context.match_index)
        effective_form = traits["form_confidence"] / expectation_tax
        form_mod = (effective_form - 0.5) * 0.03
        weights["boundary"] += form_mod
        weights["wicket"] -= form_mod
        
        # If under high expectation tax, increase dot balls and edges slightly
        if expectation_tax > 1.0:
            tax_penalty = (expectation_tax - 1.0) * 0.1
            weights["dot"] += tax_penalty
            weights["wicket"] += tax_penalty * 0.5

        # Home advantage for batsman
        if ball_context.is_batsman_home:
            weights["boundary"] += 0.025
            weights["six"] += 0.012
            weights["dot"] -= 0.020
            weights["wicket"] -= 0.012

        # Bowler quality modifier: good bowlers create more dots/wickets, fewer boundaries
        eco_mod = (8.5 - ball_context.bowler_economy) / 8.5  # positive = good bowler
        weights["dot"] += eco_mod * 0.05
        weights["boundary"] -= eco_mod * 0.04
        weights["six"] -= eco_mod * 0.02
        weights["wicket"] += eco_mod * 0.025

        bavg_mod = (30.0 - ball_context.bowler_bowling_avg) / 30.0
        weights["wicket"] += bavg_mod * 0.02

        # Pressure index: increases dots and wicket probability
        pressure = ball_context.pressure_index
        if pressure > 0.5:
            pressure_factor = (pressure - 0.5) * 0.12
            resilience = traits["pressure_resilience"]
            # More resilient players are less affected by pressure
            effective_pressure = pressure_factor * (1.0 - resilience * 0.7)
            weights["dot"] += effective_pressure
            weights["wicket"] += effective_pressure * 0.6
            weights["boundary"] -= effective_pressure * 0.4
            weights["single"] -= effective_pressure * 0.2

        # Fatigue modifier: tired batsmen play more defensively / riskier
        fatigue = ball_context.batsman_fatigue + traits["fatigue_level"]
        fatigue = min(fatigue, 1.0)
        if fatigue > 0.3:
            fatigue_factor = (fatigue - 0.3) * 0.06
            weights["wicket"] += fatigue_factor
            weights["dot"] += fatigue_factor * 0.4
            weights["boundary"] -= fatigue_factor * 0.2

        # Experience modifier: veterans make better decisions under pressure
        exp_years = self._profile.get("experience_years", 5)
        player_age = self._profile.get("age", 28)
        if exp_years >= 10:
            # Veterans: fewer rash shots, lower wicket probability
            weights["wicket"] -= 0.015
            weights["dot"] += 0.005  # more patient
            weights["single"] += 0.005
        elif exp_years <= 2:
            # Rookies: more volatile — higher boundary AND wicket rates
            weights["wicket"] += 0.01
            weights["boundary"] += 0.01
        # Age-related decline: players 37+ lose some boundary hitting ability
        if player_age >= 37:
            age_decline = min(0.03, (player_age - 36) * 0.008)
            weights["boundary"] -= age_decline
            weights["six"] -= age_decline * 0.5

        # Powerplay boost (overs 0-5)
        if ball_context.over < 6:
            pp_spec = traits["powerplay_specialization"]
            weights["boundary"] += (pp_spec - 0.5) * 0.04
            weights["six"] += (pp_spec - 0.5) * 0.02

        # Death overs boost (overs 16-19)
        if ball_context.over >= 16:
            death_spec = traits["death_overs_specialization"]
            weights["six"] += (death_spec - 0.5) * 0.05
            weights["boundary"] += (death_spec - 0.5) * 0.03

        # Pitch condition modifier
        pitch = ball_context.pitch_condition
        pitch_batting_ease = pitch.get("batting_ease", 0.5)
        weights["boundary"] += (pitch_batting_ease - 0.5) * 0.04
        weights["dot"] -= (pitch_batting_ease - 0.5) * 0.03
        weights["wicket"] -= (pitch_batting_ease - 0.5) * 0.03
        
        # Death Overs Reputation Factor
        # Known death specialists create pre-ball fear, driving up false-shots
        if ball_context.over >= 16 and ball_context.bowler_death_spec > 0.7:
            reputation_fear = (ball_context.bowler_death_spec - 0.7) * 0.15
            weights["dot"] += reputation_fear
            weights["wicket"] += reputation_fear * 0.5
            weights["boundary"] -= reputation_fear

        # Boundary asymmetry modifier (Week 1): shorter boundaries increase six/boundary probability
        asymmetry = ball_context.boundary_asymmetry_factor
        weights["boundary"] *= asymmetry  # direct multiplicative adjustment
        weights["six"] *= asymmetry

        # Dew factor modifier (Week 1): affects spin effectiveness against batsman
        # High dew (0.7) makes spin less effective, benefiting batsman
        dew = ball_context.dew_factor
        dew_spin_boost = (1.0 - dew)  # 0.3 at full dew means 30% spin resistance boost
        weights["boundary"] += dew_spin_boost * 0.02
        weights["six"] += dew_spin_boost * 0.01

        # Left-Arm Matchup Dynamics (Geometric Handicap)
        # Right-Hand Batter vs Left-Arm Pace/Spin creates challenging incoming angles
        b_style = ball_context.bowler_style.lower()
        if "left" in b_style and "right" in self._profile.get("batting_style", "").lower():
            la_vulnerability = traits.get("left_arm_vulnerability_index", 0.6)
            # Increase edges (wickets) and dots based on vulnerability index
            la_penalty = (la_vulnerability - 0.5) * 0.05
            weights["wicket"] += la_penalty
            weights["dot"] += la_penalty * 0.6
            weights["boundary"] -= la_penalty * 0.4

        # --- Core Strategy & Game Architecture Modifiers ---
        
        # 16. Post-timeout intent shift (Over 9 and Over 14)
        # Batters are given instructions to attack immediately after timeouts
        if ball_context.is_post_timeout:
            weights["boundary"] += 0.05
            weights["six"] += 0.04
            weights["wicket"] += 0.04  # High risk, high reward
            weights["dot"] -= 0.05

        # 9. 17th over leverage factor
        # Sets the platform for the rest of the death overs. Huge pressure applied to the bowler.
        if ball_context.is_17th_over:
            weights["boundary"] += 0.03
            weights["dot"] -= 0.02
            weights["single"] += 0.02

        # 15. Batting collapse contagion tendency
        # If the team lost 2 quick wickets, the new batter inherits the panic.
        if ball_context.batting_collapse_active and ball_context.balls_faced_this_innings < 6:
            weights["dot"] += 0.08
            weights["wicket"] += 0.05
            weights["boundary"] -= 0.06

        # 19. Anchor penalty
        # If the non-striker is slowing down the innings, this batter is forced into risk.
        if ball_context.anchor_penalty_active:
            weights["boundary"] += 0.06
            weights["six"] += 0.04
            weights["wicket"] += 0.06
            weights["single"] -= 0.04
            
        # 25. Franchise clutch factor (Emotional rivalry volatility)
        # High-clutch franchises execute under pressure, limiting edges.
        clutch_mod = (ball_context.franchise_clutch_factor - 0.5) * 0.05
        weights["boundary"] += clutch_mod
        weights["wicket"] -= clutch_mod

        # 17. Lower-order strike independence
        # Bowlers batting at 8-11 do not care about building an innings. Hit or get out.
        if ball_context.lower_order_strike_independence:
            weights["six"] += 0.06
            weights["wicket"] += 0.08
            weights["dot"] += 0.05
            weights["single"] -= 0.06

        # 7. Captain defensive tendency
        # A conservative captain spreads the field, conceding singles to prevent boundaries.
        cap_def = (ball_context.captain_defensive_tendency - 0.5) * 0.06
        weights["single"] += cap_def
        weights["boundary"] -= cap_def
        
        # 2. Opening 12-ball intent profile
        if ball_context.balls_faced_this_innings < 12:
            intent_mod = (traits["aggression_index"] - 0.5) * 0.08
            weights["boundary"] += intent_mod
            weights["wicket"] += abs(intent_mod) * 0.6
            
        # 13. Spinner entry timing distortion
        # Spinners entering the powerplay are hit for boundaries but pick up edges.
        b_style = ball_context.bowler_style.lower()
        is_spinner = "spin" in b_style or b_style in ["off_break", "leg_break", "left_arm_spin"]
        if is_spinner and ball_context.over < 6:
            weights["boundary"] += 0.05
            weights["six"] += 0.03
            weights["wicket"] += 0.04
            weights["dot"] -= 0.06
            
        # 23. Over-rate pressure
        # Field restrictions in the final 2 overs. Boundaries naturally spike.
        if ball_context.over_rate_pressure_active:
            weights["boundary"] += 0.05
            weights["six"] += 0.03
            weights["single"] += 0.02
            weights["dot"] -= 0.05

        # --- Clamp all weights to non-negative ---
        for key in weights:
            weights[key] = max(0.001, weights[key])

        # --- Sample the outcome ---
        outcomes = list(weights.keys())
        probs = [weights[k] for k in outcomes]
        total = sum(probs)
        normalised = [p / total for p in probs]

        outcome_key = rng.choices(outcomes, weights=normalised, k=1)[0]

        # Map outcome key to BallOutcome fields
        runs = 0
        is_wicket = False
        is_boundary = False
        is_six = False
        dismissal_type = None

        if outcome_key == "dot":
            runs = 0
        elif outcome_key == "single":
            runs = 1
        elif outcome_key == "two":
            runs = 2
        elif outcome_key == "three":
            runs = 3
        elif outcome_key == "boundary":
            runs = 4
            is_boundary = True
        elif outcome_key == "six":
            runs = 6
            is_six = True
        elif outcome_key == "wicket":
            runs = 0
            is_wicket = True
            dismissal_pool = DISMISSAL_TYPES_BY_BOWLER_TYPE.get("pace", ["caught", "bowled", "lbw"])
            dismissal_type = rng.choice(dismissal_pool)
            
            # 10. Fielding conversion probability
            # The catch might be dropped down based on team fielding efficiency
            if dismissal_type == "caught":
                if rng.random() > ball_context.fielding_conversion_probability:
                    # Catch DROPPED! Convert the wicket into 1 or 2 runs
                    is_wicket = False
                    runs = rng.choice([1, 2])
                    outcome_key = "single" if runs == 1 else "two"
                    dismissal_type = None
                    shot_type = "dropped_catch"

        # Pick shot type narrative BEFORE confirming outcome
        shot_type = rng.choice(SHOT_TYPES_BY_OUTCOME.get(outcome_key, ["played"]))
        delivery_type = rng.choice(DELIVERY_TYPES)

        # Apply Field Placement Interception (Captain Agent Integration)
        # Driven shot can be a dot if a fielder is perfectly placed in the deep or inside the ring.
        field = ball_context.field_state
        if field:
            intersected = False
            if outcome_key in ["boundary", "three", "two"]:
                if shot_type in ["drive", "lofted_drive"] and (field.long_off or field.deep_cover):
                    intersected = True
                elif shot_type in ["pull", "slog"] and field.deep_square_leg:
                    intersected = True
                elif shot_type in ["cut"] and field.deep_point:
                    intersected = True
                elif shot_type in ["flick_boundary"] and field.deep_fine_leg:
                    intersected = True
                    
            if intersected:
                # Shot was heading for a boundary but hit straight to a fielder
                if rng.random() < 0.2:
                    outcome_key = "wicket"
                    is_wicket = True
                    is_boundary = False
                    runs = 0
                    dismissal_type = "caught"
                    shot_type = f"{shot_type} (caught in the deep)"
                elif rng.random() < 0.5:
                    outcome_key = "dot"
                    is_boundary = False
                    runs = 0
                    shot_type = f"{shot_type} (intercepted)"
                else:
                    outcome_key = "single"
                    is_boundary = False
                    runs = 1
                    shot_type = f"{shot_type} (cut off)"

        # Set final fields after field interception
        if outcome_key == "dot":
            runs = 0
        elif outcome_key == "single":
            runs = 1
        elif outcome_key == "two":
            runs = 2
        elif outcome_key == "three":
            runs = 3
        elif outcome_key == "boundary":
            runs = 4
            is_boundary = True
        elif outcome_key == "six":
            runs = 6
            is_six = True

        # Build notes
        player_name = self._profile.get("name", "Batsman")
        if is_wicket:
            notes = f"{player_name} is OUT! {dismissal_type}"
        elif is_six:
            notes = f"{player_name} hits a massive SIX via {shot_type}!"
        elif is_boundary:
            notes = f"{player_name} finds the boundary with a {shot_type}"
        elif runs == 0:
            notes = f"{player_name} plays a {shot_type} — dot ball"
        else:
            notes = f"{player_name} takes {runs} via {shot_type}"

        outcome = BallOutcome(
            runs=runs,
            is_wicket=is_wicket,
            is_wide=False,
            is_no_ball=False,
            is_boundary=is_boundary,
            is_six=is_six,
            dismissal_type=dismissal_type,
            shot_type=shot_type,
            delivery_type=delivery_type,
            pressure_index=ball_context.pressure_index,
            confidence=0.85,  # probabilistic model confidence
            notes=notes,
        )

        # Log decision to agent memory
        self.add_memory({
            "type": "ball_faced",
            "over": ball_context.over,
            "ball": ball_context.ball,
            "outcome": outcome_key,
            "runs": runs,
            "is_wicket": is_wicket,
            "pressure_index": ball_context.pressure_index,
            "description": notes,
        })

        return outcome

    # ------------------------------------------------------------------
    # Bowling decision function
    # ------------------------------------------------------------------

    def bowl(self, ball_context: BallContext, rng: random.Random | None = None) -> BallOutcome:
        """
        Simulate this player bowling a delivery.

        Probability distributions shaped by:
        - bowling economy (lower economy = more dots/wickets)
        - bowling_avg (lower avg = more wickets)
        - fatigue: tired bowler → more wides/no-balls, worse economy
        - home advantage for bowler: better economy, higher wicket probability
        - pitch conditions (spin effectiveness, pace effectiveness)
        - pressure index: bowler under pressure may bowl wider
        - dew_factor: spin RPM degradation (0.7-1.0), wrist spinners hit hardest

        Args:
            ball_context: All situational context
            rng: Optional seeded Random for reproducibility

        Returns:
            BallOutcome from the bowler's perspective
        """
        if rng is None:
            rng = random.Random()

        traits = self._profile["personality_traits"]
        career = self._profile["career_stats"]

        # Determine bowling style from profile
        bowling_style = self._profile.get("bowling_style", "pace")
        is_spinner = "spin" in bowling_style.lower() or bowling_style in ["off_break", "leg_break", "left_arm_spin"]

        # -- Build adjusted weights (from bowler's perspective — inverse of batting) --
        weights = dict(BASE_BATTING_WEIGHTS)

        # Economy modifier: normalise around typical IPL economy of 8.5
        eco_norm = (8.5 - career["bowling_economy"]) / 8.5
        weights["dot"] += eco_norm * 0.04
        weights["boundary"] -= eco_norm * 0.03
        weights["six"] -= eco_norm * 0.02

        # Bowling average modifier: lower avg = more wickets
        bowl_avg_norm = (30.0 - career.get("bowling_avg", 28.0)) / 30.0
        weights["wicket"] += bowl_avg_norm * 0.02

        # Home advantage for bowler
        if ball_context.is_bowler_home:
            weights["dot"] += 0.012
            weights["wicket"] += 0.010
            weights["boundary"] -= 0.010

        # Fatigue: tired bowler bowls worse
        bowler_fatigue = ball_context.bowler_fatigue + traits["fatigue_level"]
        bowler_fatigue = min(bowler_fatigue, 1.0)
        
        # Apply Price-Tag Burden (Auction Hangover) to bowling confidence/fatigue
        expectation_tax = self.get_expectation_tax(ball_context.match_index)
        if expectation_tax > 1.0:
            bowler_fatigue = min(bowler_fatigue + (expectation_tax - 1.0), 1.0)
        
        if bowler_fatigue > 0.3:
            fatigue_penalty = (bowler_fatigue - 0.3) * 0.04
            weights["boundary"] += fatigue_penalty
            weights["six"] += fatigue_penalty * 0.3
            weights["dot"] -= fatigue_penalty * 0.3
            weights["wicket"] -= fatigue_penalty * 0.15

        # Pitch condition: spin / pace effectiveness
        pitch = ball_context.pitch_condition
        if is_spinner:
            spin_eff = pitch.get("spin_effectiveness", 0.5)
            weights["wicket"] += (spin_eff - 0.5) * 0.04
            weights["dot"] += (spin_eff - 0.5) * 0.03
            weights["boundary"] -= (spin_eff - 0.5) * 0.02
        else:
            pace_eff = pitch.get("pace_effectiveness", 0.5)
            weights["wicket"] += (pace_eff - 0.5) * 0.04
            weights["dot"] += (pace_eff - 0.5) * 0.03
            weights["boundary"] -= (pace_eff - 0.5) * 0.02

        # Death overs: good death bowler keeps runs down
        if ball_context.over >= 16:
            death_spec = traits["death_overs_specialization"]
            weights["dot"] += (death_spec - 0.5) * 0.03
            weights["six"] -= (death_spec - 0.5) * 0.02
            
        # Experience modifier for bowling: veterans bowl tighter lines
        exp_years = self._profile.get("experience_years", 5)
        if exp_years >= 10:
            weights["dot"] += 0.015
            weights["wicket"] += 0.01
            weights["boundary"] -= 0.01
        elif exp_years <= 2:
            weights["boundary"] += 0.01
            weights["dot"] -= 0.01

        # Ball Condition Phase Modifiers (White Ball Lacquer Lifecycle)
        if ball_context.over <= 3:
            # New ball phase: Peak swing and seam. Lacquer intact.
            if not is_spinner:
                weights["wicket"] += 0.03
                weights["dot"] += 0.04
        elif 4 <= ball_context.over <= 12:
            # Mid ball phase: Lacquer wears off, best batting phase.
            weights["boundary"] += 0.03
            weights["dot"] -= 0.03
        else:
            # Old ball phase: Cutters, grip, and reverse swing dominate.
            if is_spinner or traits.get("death_overs_specialization", 0.5) > 0.65:
                weights["dot"] += 0.03
                weights["wicket"] += 0.02

        # Dew factor modifier (Week 1): RPM degradation for spinners
        # Wrist spinners lose 20-30% RPM, finger spinners lose 10-15%, pacers negligible
        bowling_style = self._profile.get("bowling_style", "pace")
        is_wrist_spinner = bowling_style in ["legbreak", "leggie", "chinaman", "googly"]
        is_finger_spinner = bowling_style in ["offbreak", "off_break", "left_arm_spin", "orthodox"]

        dew = ball_context.dew_factor  # 1.0 = full grip, 0.7 = worst grip (RPM factor)
        if is_wrist_spinner:
            # Wrist spinners hit hardest: dew IS the grip factor directly
            weights["dot"] *= dew
            weights["wicket"] *= dew
        elif is_finger_spinner:
            # Finger spinners moderately affected: dampen the grip loss
            finger_grip = 0.5 + 0.5 * dew  # 0.85 at worst, 1.0 at best
            weights["dot"] *= finger_grip
            weights["wicket"] *= finger_grip
        # Pacers negligible impact (~0.99), so we skip adjustment

        # Umpire Decision Variance (Stochastic Realism)
        # Strict umpires call more wides/no-balls, heavily impacting death overs.
        umpire_modifier = ball_context.umpire_strictness
        wide_prob = (0.025 + bowler_fatigue * 0.02) * umpire_modifier
        if rng.random() < wide_prob:
            # Wide delivery
            return BallOutcome(
                runs=1,  # wide concedes 1 run
                is_wicket=False,
                is_wide=True,
                is_no_ball=False,
                is_boundary=False,
                is_six=False,
                dismissal_type=None,
                shot_type="none",
                delivery_type="wide",
                pressure_index=ball_context.pressure_index,
                confidence=0.95,
                notes=f"{self._profile.get('name', 'Bowler')} bowls a wide",
            )

        # Clamp weights
        for key in weights:
            weights[key] = max(0.001, weights[key])

        outcomes = list(weights.keys())
        probs = [weights[k] for k in outcomes]
        total = sum(probs)
        normalised = [p / total for p in probs]

        outcome_key = rng.choices(outcomes, weights=normalised, k=1)[0]

        # Resolve outcome
        runs = 0
        is_wicket = False
        is_boundary = False
        is_six = False
        dismissal_type = None

        if outcome_key == "dot":
            runs = 0
        elif outcome_key == "single":
            runs = 1
        elif outcome_key == "two":
            runs = 2
        elif outcome_key == "three":
            runs = 3
        elif outcome_key == "boundary":
            runs = 4
            is_boundary = True
        elif outcome_key == "six":
            runs = 6
            is_six = True
        elif outcome_key == "wicket":
            is_wicket = True
            dismissal_pool = DISMISSAL_TYPES_BY_BOWLER_TYPE.get(
                "spin" if is_spinner else "pace", ["caught", "bowled"]
            )
            dismissal_type = rng.choice(dismissal_pool)

        delivery_type = rng.choice(DELIVERY_TYPES)
        bowler_name = self._profile.get("name", "Bowler")

        if is_wicket:
            notes = f"{bowler_name} takes a wicket! {dismissal_type}"
        elif is_six:
            notes = f"{bowler_name} goes for a SIX — {delivery_type}"
        elif is_boundary:
            notes = f"{bowler_name} goes for a boundary — {delivery_type}"
        else:
            notes = f"{bowler_name}: {runs} runs off {delivery_type}"

        outcome = BallOutcome(
            runs=runs,
            is_wicket=is_wicket,
            is_wide=False,
            is_no_ball=False,
            is_boundary=is_boundary,
            is_six=is_six,
            dismissal_type=dismissal_type,
            shot_type="batsman_response",
            delivery_type=delivery_type,
            pressure_index=ball_context.pressure_index,
            confidence=0.82,
            notes=notes,
        )

        self.add_memory({
            "type": "ball_bowled",
            "over": ball_context.over,
            "ball": ball_context.ball,
            "outcome": outcome_key,
            "runs_conceded": runs,
            "is_wicket": is_wicket,
            "description": notes,
        })

        return outcome

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._profile.get("name", "Unknown Player")

    @property
    def team(self) -> str:
        return self._profile.get("team", "Unknown Team")

    @property
    def role(self) -> str:
        return self._profile.get("role", "allrounder")

    @property
    def is_foreign_player(self) -> bool:
        return self._profile.get("is_foreign_player", False)

    @property
    def is_impact_player_eligible(self) -> bool:
        return self._profile.get("impact_player", {}).get("is_eligible", False)

    def can_bowl(self) -> bool:
        """Check if this player can bowl."""
        bowling_style = self._profile.get("bowling_style", "none")
        return bowling_style not in ("none", "")

    # ------------------------------------------------------------------
    # Persona-mode batting and bowling (Phase 2)
    # ------------------------------------------------------------------

    async def bat_with_persona(
        self,
        ball_context: BallContext,
        bowling_decision: dict[str, Any] | None,
        narrative: str,
        comm_messages: list[dict[str, Any]] | None = None,
        rng: random.Random | None = None,
    ) -> BallOutcome:
        """
        Persona-mode batting: LLM decides intent, probability resolves outcome.

        Uses the skills system (BattingDecisionSkill) to get a structured
        BattingDecision from the LLM, then feeds it to the OutcomeResolver
        to get a probabilistic BallOutcome.

        Falls back to regular bat() if LLM call fails.
        """
        from ..skills.batting_decision import BattingDecisionSkill
        from ..simulation.outcome_resolver import resolve_persona_outcome

        rng = rng or random.Random()
        skill = BattingDecisionSkill()

        context = {
            "ball_context": self._ball_context_to_dict(ball_context),
            "narrative": narrative,
            "bowling_decision": bowling_decision,
            "persona": self.persona,
            "comm_messages": comm_messages,
        }

        try:
            batting_decision = await skill.execute(self, context, "persona")
            outcome = resolve_persona_outcome(
                batting_decision=batting_decision,
                bowling_decision=bowling_decision or {},
                ball_context=self._ball_context_to_dict(ball_context),
                rng=rng,
            )

            # Record memory
            self.add_memory({
                "type": "ball_faced",
                "over": ball_context.over,
                "ball": ball_context.ball,
                "outcome": "wicket" if outcome.is_wicket else f"{outcome.runs}_runs",
                "runs": outcome.runs,
                "is_wicket": outcome.is_wicket,
                "intent": batting_decision.get("intent", "unknown"),
                "shot": batting_decision.get("shot_selection", "unknown"),
                "pressure_index": ball_context.pressure_index,
                "description": outcome.notes,
                "inner_monologue": batting_decision.get("inner_monologue", ""),
            })

            return outcome

        except Exception:
            # Fall back to probabilistic
            return self.bat(ball_context, rng=rng)

    async def bowl_with_persona(
        self,
        ball_context: BallContext,
        batsman_profile: dict[str, Any] | None,
        narrative: str,
        comm_messages: list[dict[str, Any]] | None = None,
        rng: random.Random | None = None,
    ) -> dict[str, Any]:
        """
        Persona-mode bowling: LLM decides delivery plan.

        Returns the bowling decision dict (to be passed to batsman's
        bat_with_persona as context). Does NOT resolve the ball outcome —
        that's done on the batting side.
        """
        from ..skills.bowling_strategy import BowlingStrategySkill

        skill = BowlingStrategySkill()

        context = {
            "ball_context": self._ball_context_to_dict(ball_context),
            "narrative": narrative,
            "batsman_profile": batsman_profile,
            "persona": self.persona,
            "comm_messages": comm_messages,
        }

        try:
            bowling_decision = await skill.execute(self, context, "persona")

            self.add_memory({
                "type": "ball_bowled_plan",
                "over": ball_context.over,
                "ball": ball_context.ball,
                "delivery": bowling_decision.get("delivery_type", "unknown"),
                "line": bowling_decision.get("line", "unknown"),
                "pressure_index": ball_context.pressure_index,
                "inner_monologue": bowling_decision.get("inner_monologue", ""),
            })

            return bowling_decision

        except Exception:
            # Return a minimal heuristic decision
            return {
                "delivery_type": "stock_delivery",
                "line": "off_stump",
                "length": "good_length",
                "confidence": 0.5,
                "reasoning": "Fallback delivery",
                "inner_monologue": "",
            }

    @staticmethod
    def _ball_context_to_dict(ctx: BallContext) -> dict[str, Any]:
        """Convert BallContext dataclass to dict for skill context."""
        return {
            "over": ctx.over,
            "ball": ctx.ball,
            "batting_team_score": ctx.batting_team_score,
            "wickets_fallen": ctx.wickets_fallen,
            "target": ctx.target,
            "pressure_index": ctx.pressure_index,
            "batsman_fatigue": ctx.batsman_fatigue,
            "bowler_fatigue": ctx.bowler_fatigue,
            "is_batsman_home": ctx.is_batsman_home,
            "is_bowler_home": ctx.is_bowler_home,
            "balls_faced_this_innings": ctx.balls_faced_this_innings,
            "partnership_runs": ctx.partnership_runs,
            "required_run_rate": ctx.required_run_rate,
            "current_run_rate": ctx.current_run_rate,
            "dew_factor": ctx.dew_factor,
            "boundary_asymmetry_factor": ctx.boundary_asymmetry_factor,
            "bowler_economy": ctx.bowler_economy,
            "bowler_bowling_avg": ctx.bowler_bowling_avg,
        }

    def __repr__(self) -> str:
        return (
            f"PlayerAgent(name={self.name!r}, team={self.team!r}, "
            f"role={self.role!r}, run_id={self._run_id[:8]!r})"
        )
