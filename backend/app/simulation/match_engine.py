"""
MatchEngine — Core single-match simulation engine.

Implements the full T20 match loop:
  Toss → Innings 1 (20 overs, Impact Player windows) → Innings 2 → Result

Ball-by-ball simulation using PlayerAgent bat() / bowl() probabilistic decisions.
Supports three modes: probabilistic, hybrid (LLM at high-pressure), persona (full LLM).
Pressure index recomputed each ball (7 factors). Impact Player rule enforcement is hard law.

Core game factors integrated per ball:
  - Boundary asymmetry, dew, pitch aging, ball condition phase
  - Captain field placement interception, umpire variance
  - Collapse contagion, anchor penalty, franchise clutch
  - Post-timeout intent shift, over-rate pressure, spinner timing
  - Ball replacement 2026 rule, super over tie handling
"""

from __future__ import annotations

import asyncio
import copy
import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..agents.player_agent import PlayerAgent, BallContext, BallOutcome
from ..agents.stadium_agent import StadiumAgent
from ..agents.pitch_agent import PitchAgent
from ..agents.weather_agent import WeatherAgent
from ..agents.crowd_agent import CrowdAgent
from ..agents.umpire_agent import UmpireAgent
from ..agents.coach_agent import CoachAgent
from ..services.context_renderer import ContextRenderer
from ..services.comm_bus import CommBus, AgentMessage
from ..services.llm_batch import batch_bowling_plan, batch_batting_plan_independent
from ..services.llm_client import LLM_PRESSURE_THRESHOLD


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BattingLineup:
    """Ordered batting lineup with player agents."""
    players: list[PlayerAgent]  # batting order
    current_batsman_idx: int = 0
    next_in_idx: int = 2

    def current_batsman(self) -> PlayerAgent:
        return self.players[self.current_batsman_idx]

    def non_striker(self) -> PlayerAgent | None:
        if self.next_in_idx > 1:
            # Find the non-striker from players who have batted but not out
            for i, p in enumerate(self.players):
                if i != self.current_batsman_idx and i < self.next_in_idx:
                    return p
        return None

    def next_batsman(self) -> PlayerAgent | None:
        if self.next_in_idx < len(self.players):
            return self.players[self.next_in_idx]
        return None


@dataclass
class BowlingCard:
    """Track each bowler's figures in an innings."""
    name: str
    overs_bowled: float = 0.0
    balls_bowled: int = 0
    runs_conceded: int = 0
    wickets: int = 0
    wides: int = 0
    no_balls: int = 0

    @property
    def economy(self) -> float:
        if self.overs_bowled == 0:
            return 0.0
        return round(self.runs_conceded / self.overs_bowled, 2)


@dataclass
class BallEvent:
    """Record of a single ball in the match."""
    over: int
    ball: int
    innings: int
    batsman: str
    bowler: str
    runs: int
    extras: int
    is_wicket: bool
    dismissal_type: str | None
    is_wide: bool
    is_no_ball: bool
    is_boundary: bool
    is_six: bool
    pressure_index: float
    score_after: int
    wickets_after: int
    commentary: str


@dataclass
class InningsResult:
    """Result of a single innings."""
    team: str
    batting_order: list[str]
    total_score: int
    wickets: int
    overs_played: float
    balls: list[BallEvent] = field(default_factory=list)
    bowling_figures: dict[str, BowlingCard] = field(default_factory=dict)
    fall_of_wickets: list[dict] = field(default_factory=list)
    extras: int = 0
    boundaries: int = 0
    sixes: int = 0
    impact_player_used: str | None = None
    impact_player_replaced: str | None = None

    @property
    def run_rate(self) -> float:
        if self.overs_played == 0:
            return 0.0
        return round(self.total_score / self.overs_played, 2)


@dataclass
class MatchState:
    """
    Mutable state for a single simulation run.

    This is deepcopied per simulation — profiles are NOT here.
    """
    team1: str
    team2: str
    innings: int = 1
    over: int = 0
    ball: int = 0
    score: int = 0
    wickets: int = 0
    extras: int = 0
    batting_team: str = ""
    bowling_team: str = ""
    target: int | None = None
    current_partnership_runs: int = 0
    balls_since_boundary: int = 0
    batsman_balls_faced: dict[str, int] = field(default_factory=dict)
    bowler_overs_bowled: dict[str, float] = field(default_factory=dict)
    bowler_balls_bowled: dict[str, int] = field(default_factory=dict)
    team_ip_used: dict[str, bool] = field(default_factory=dict)
    ball_replacements_used: dict[str, int] = field(default_factory=lambda: {"team1": 0, "team2": 0})
    current_ball_age_overs: int = 0
    consecutive_dot_balls: int = 0
    ball_replacement_restore_balls: int = 0  # Balls remaining with new-ball grip restoration (dew_factor=1.0)


@dataclass
class MatchConfig:
    """Configuration for a match simulation."""
    match_id: str
    team1: str
    team2: str
    venue: str
    match_date: str
    match_time: str
    team1_players: list[dict]  # player profile dicts
    team2_players: list[dict]  # player profile dicts
    team1_ip_substitutes: list[str] = field(default_factory=list)  # eligible IP names
    team2_ip_substitutes: list[str] = field(default_factory=list)
    pitch_type: str = "balanced"
    weather_data: dict | None = None
    toss_winner: str | None = None
    toss_decision: str | None = None  # 'bat' or 'field'
    max_overs: int = 20
    max_wickets: int = 10
    sim_count: int = 1  # Week 1: always 1
    simulation_mode: str = "hybrid"  # "persona", "hybrid", or "probabilistic"
    persona_llm_trigger: str = "per_over"  # "per_over", "per_ball", "per_wicket" (persona mode only)
    # Live match state — when set, simulation resumes from this point
    # Keys: innings_complete (0|1), batting_team, bowling_team,
    #        score, wickets, overs (float, e.g. 12.3), target (int|None),
    #        innings1_score (int|None — set when innings_complete==1)
    live_state: dict | None = None


@dataclass
class MatchResult:
    """Final result of a simulated match."""
    match_id: str
    simulation_id: str
    team1: str
    team2: str
    venue: str
    winner: str | None
    win_type: str  # 'runs' | 'wickets' | 'super_over' | 'no_result'
    win_margin: int
    team1_score: int
    team1_wickets: int
    team1_overs: float
    team2_score: int
    team2_wickets: int
    team2_overs: float
    toss_winner: str
    toss_decision: str
    innings1: InningsResult
    innings2: InningsResult
    pressure_peaks: list[dict] = field(default_factory=list)
    key_moments: list[str] = field(default_factory=list)
    disclaimer: str = (
        "⚠️ SIMULATION ONLY: Generated by an AI swarm engine for research and entertainment. "
        "Not betting advice. Not a guarantee of outcomes. "
        "Repo owner accepts no responsibility for personal or financial losses. "
        "Full terms: LICENSE.md"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "simulation_id": self.simulation_id,
            "team1": self.team1,
            "team2": self.team2,
            "venue": self.venue,
            "winner": self.winner,
            "win_type": self.win_type,
            "win_margin": self.win_margin,
            "team1_score": self.team1_score,
            "team1_wickets": self.team1_wickets,
            "team1_overs": self.team1_overs,
            "team2_score": self.team2_score,
            "team2_wickets": self.team2_wickets,
            "team2_overs": self.team2_overs,
            "toss_winner": self.toss_winner,
            "toss_decision": self.toss_decision,
            "key_moments": self.key_moments,
            "disclaimer": self.disclaimer,
        }


# ---------------------------------------------------------------------------
# Pressure Index Calculator
# ---------------------------------------------------------------------------

def compute_pressure_index(
    innings: int,
    over: int,
    wickets: int,
    score: int,
    target: int | None,
    crowd_energy: float = 0.5,
    player_fatigue: float = 0.2,
    consecutive_dots: int = 0,
    total_wickets: int = 10,
) -> float:
    """
    Compute pressure index (0-1) for the current ball.

    7 Factors (enhanced — higher weights for death overs and wicket clusters):
    - Wickets remaining (EXPONENTIAL cushion, not linear)
    - Over number (death overs = strong pressure in BOTH innings)
    - Required run rate vs target (chasing innings only)
    - Innings 1 scoring pressure (setting a total also has pressure)
    - Dot-ball contagion (3+ consecutive dots trigger non-linear spike)
    - Crowd energy (±0.05 modifier)
    - Player fatigue (additive penalty)

    Returns:
        Float 0-1 where 1.0 = maximum pressure
    """
    pressure = 0.0

    # 1. Wicket-based pressure: EXPONENTIAL not linear
    # 10 wickets remaining = low, fewer wickets = escalating pressure
    wickets_remaining = total_wickets - wickets
    wickets_pressure = 1.0 - (wickets_remaining / total_wickets) ** 2
    pressure += wickets_pressure * 0.25

    # Wicket cluster bonus: 3+ wickets fallen AND in middle/death = spike
    if wickets >= 3 and over >= 10:
        pressure += 0.10
    if wickets >= 5:
        pressure += 0.10  # collapse territory

    # 2. Over-based pressure: death overs are HIGH pressure in BOTH innings
    if over >= 18:
        # Last 2 overs — always high leverage
        pressure += 0.30
    elif over >= 16:
        # Death overs (17-18)
        pressure += 0.20
    elif over >= 14:
        # Pre-death overs
        pressure += 0.10
    elif over >= 11:
        over_pressure = (over - 10) / 10.0
        pressure += over_pressure * 0.08

    # 3. Run rate pressure (chasing only)
    if target and innings == 2:
        balls_remaining = max(1, (20 - over) * 6)
        runs_needed = target - score
        if runs_needed > 0:
            required_rr = (runs_needed * 6) / balls_remaining
            # Required RR > 10 is high pressure, > 14 is extreme
            rr_pressure = min(1.0, max(0.0, (required_rr - 6.0) / 8.0))
            pressure += rr_pressure * 0.30

            # Close chase bonus: within 30 runs in last 5 overs = tense
            if over >= 15 and runs_needed <= 40:
                pressure += 0.10
        elif runs_needed <= 0:
            pressure = max(0.0, pressure - 0.3)
    elif innings == 1 and over >= 16:
        # Innings 1 death overs: setting a total is also pressure
        # Especially if scoring rate is below par (< 8 rpo at death)
        current_rr = (score * 6) / max(1, over * 6) if over > 0 else 0.0
        if current_rr < 8.0:
            pressure += 0.10  # Below-par scoring pressure

    # 4. Dot-ball contagion: 3+ consecutive dots trigger pressure spike (non-linear)
    if consecutive_dots >= 3:
        dot_spike = min(consecutive_dots / 3.0, 1.5) * 0.15
        pressure += dot_spike

    # 5. Crowd energy amplifies pressure on away team
    crowd_pressure = (crowd_energy - 0.5) * 0.10
    pressure += crowd_pressure

    # 6. Fatigue adds pressure (tired players feel more pressure)
    pressure += player_fatigue * 0.08

    return round(min(1.0, max(0.0, pressure)), 4)


# ---------------------------------------------------------------------------
# Match Engine
# ---------------------------------------------------------------------------

MAX_BOWLER_OVERS = 4  # T20 rule: max 4 overs per bowler
MAX_FOREIGN_PLAYERS = 4  # IPL rule: max 4 overseas players in playing XI


class MatchEngine:
    """
    Core simulation engine for a single T20 match.

    Usage (Week 1):
        engine = MatchEngine(config)
        result = await engine.simulate()
    """

    def __init__(self, config: MatchConfig, seed: int | None = None) -> None:
        """
        Initialise the match engine.

        Args:
            config: Match configuration (teams, players, venue, etc.)
            seed: Random seed for reproducibility. None = random.
        """
        self._config = config
        self._rng = random.Random(seed)
        self._simulation_id = str(uuid.uuid4())

        # Parse match time for dew/night-match calculations
        self._match_time: Any = None
        if config.match_time:
            try:
                from datetime import datetime as _dt
                self._match_time = _dt.fromisoformat(config.match_time)
            except (ValueError, TypeError):
                self._match_time = None

        # Initialize mutable match state (reset per simulation run)
        self._match_state = MatchState(
            team1=config.team1,
            team2=config.team2,
        )

        # Build agents from config
        self._stadium_agent = StadiumAgent.for_venue(config.venue, run_id=self._simulation_id)
        self._pitch_agent = PitchAgent.from_venue(
            config.venue, config.pitch_type, run_id=self._simulation_id
        )
        self._weather_agent = WeatherAgent(
            venue_name=config.venue,
            weather_data=config.weather_data,
            run_id=self._simulation_id,
        )
        home_team = self._stadium_agent.home_team or config.team1
        self._crowd_agent = CrowdAgent(
            home_team=home_team,
            venue_name=config.venue,
            run_id=self._simulation_id,
        )
        self._umpire1 = UmpireAgent(umpire_name="Umpire 1", run_id=self._simulation_id)
        self._umpire2 = UmpireAgent(umpire_name="Umpire 2", run_id=self._simulation_id)

        self._coach_team1 = CoachAgent(team=config.team1, run_id=self._simulation_id)
        self._coach_team2 = CoachAgent(team=config.team2, run_id=self._simulation_id)

        # Build player agents
        self._team1_agents: dict[str, PlayerAgent] = {
            p["name"]: PlayerAgent(profile=p, run_id=self._simulation_id)
            for p in config.team1_players
        }
        self._team2_agents: dict[str, PlayerAgent] = {
            p["name"]: PlayerAgent(profile=p, run_id=self._simulation_id)
            for p in config.team2_players
        }

        # Persona mode infrastructure
        is_persona_mode = config.simulation_mode in ("persona", "hybrid")
        self._context_renderer = ContextRenderer() if is_persona_mode else None
        self._comm_bus = CommBus(
            run_id=self._simulation_id,
            enabled=config.simulation_mode == "persona",
        ) if is_persona_mode else None

    # ------------------------------------------------------------------
    # Main simulation entry point
    # ------------------------------------------------------------------

    async def simulate(self) -> MatchResult:
        """
        Run a full match simulation, or resume from live state if available.

        When ``self._config.live_state`` is set the engine skips already-
        completed play and simulates only the remaining balls.

        Returns:
            MatchResult with all match data and the disclaimer.
        """
        # Umpire Decision Variance initialized per match
        self._umpire_strictness = self._rng.uniform(0.85, 1.15)

        live = self._config.live_state

        if live:
            # --- LIVE match: resume from current state ---
            innings1, innings2, toss_winner, toss_decision, batting_first, target = (
                await self._simulate_live(live)
            )
        else:
            # --- Normal full-match simulation ---
            toss_winner, toss_decision = self._resolve_toss()
            if toss_decision == "bat":
                batting_first = toss_winner
                fielding_first = self._config.team2 if toss_winner == self._config.team1 else self._config.team1
            else:
                fielding_first = toss_winner
                batting_first = self._config.team2 if toss_winner == self._config.team1 else self._config.team1

            innings1 = await self._simulate_innings(
                batting_team=batting_first,
                bowling_team=fielding_first,
                innings_number=1,
                target=None,
            )

            target = innings1.total_score + 1

            innings2 = await self._simulate_innings(
                batting_team=fielding_first,
                bowling_team=batting_first,
                innings_number=2,
                target=target,
            )

        # Determine winner
        winner, win_type, win_margin = self._determine_winner(innings1, innings2, target)

        result = MatchResult(
            match_id=self._config.match_id,
            simulation_id=self._simulation_id,
            team1=self._config.team1,
            team2=self._config.team2,
            venue=self._config.venue,
            winner=winner,
            win_type=win_type,
            win_margin=win_margin,
            team1_score=innings1.total_score if batting_first == self._config.team1 else innings2.total_score,
            team1_wickets=innings1.wickets if batting_first == self._config.team1 else innings2.wickets,
            team1_overs=innings1.overs_played if batting_first == self._config.team1 else innings2.overs_played,
            team2_score=innings2.total_score if batting_first == self._config.team1 else innings1.total_score,
            team2_wickets=innings2.wickets if batting_first == self._config.team1 else innings1.wickets,
            team2_overs=innings2.overs_played if batting_first == self._config.team1 else innings1.overs_played,
            toss_winner=toss_winner,
            toss_decision=toss_decision,
            innings1=innings1,
            innings2=innings2,
            key_moments=self._collect_key_moments(innings1, innings2),
        )

        return result

    # ------------------------------------------------------------------
    # LIVE match resumption
    # ------------------------------------------------------------------

    async def _simulate_live(
        self, live: dict,
    ) -> tuple[InningsResult, InningsResult, str, str, str, int]:
        """
        Resume simulation from a live match state.

        Returns (innings1, innings2, toss_winner, toss_decision, batting_first, target).
        """
        innings_complete = live.get("innings_complete", 0)
        batting_team = live.get("batting_team", "")
        bowling_team = live.get("bowling_team", "")
        live_score = live.get("score", 0)
        live_wickets = live.get("wickets", 0)
        live_overs = float(live.get("overs", 0))

        # Toss already happened in a live match — use config or infer
        toss_winner = self._config.toss_winner or batting_team
        toss_decision = self._config.toss_decision or "bat"

        # Determine who batted first from live context
        if innings_complete >= 1:
            # Innings 1 done — current batting team is batting second
            batting_first = bowling_team
            fielding_first = batting_team
        else:
            # Still in innings 1 — current batting team is batting first
            batting_first = batting_team
            fielding_first = bowling_team

        if innings_complete == 0:
            # --- Mid innings 1: simulate remainder of innings 1, then full innings 2 ---
            start_over = int(live_overs)
            start_ball = round((live_overs - start_over) * 10)  # e.g. 12.3 → ball 3

            innings1 = await self._simulate_innings(
                batting_team=batting_first,
                bowling_team=fielding_first,
                innings_number=1,
                target=None,
                start_score=live_score,
                start_wickets=live_wickets,
                start_over=start_over,
                start_ball=start_ball,
            )

            target = innings1.total_score + 1

            innings2 = await self._simulate_innings(
                batting_team=fielding_first,
                bowling_team=batting_first,
                innings_number=2,
                target=target,
            )

        else:
            # --- Innings 1 complete, mid innings 2: use actual innings 1 score ---
            innings1_score = live.get("innings1_score", 0)

            innings1 = InningsResult(
                team=batting_first,
                batting_order=[],
                total_score=innings1_score,
                wickets=0,  # not known, not needed for remaining sim
                overs_played=20.0,
            )

            target = innings1_score + 1

            start_over = int(live_overs)
            start_ball = round((live_overs - start_over) * 10)

            innings2 = await self._simulate_innings(
                batting_team=fielding_first,
                bowling_team=batting_first,
                innings_number=2,
                target=target,
                start_score=live_score,
                start_wickets=live_wickets,
                start_over=start_over,
                start_ball=start_ball,
            )

        return innings1, innings2, toss_winner, toss_decision, batting_first, target

    # ------------------------------------------------------------------
    # Over-level batch planning
    # ------------------------------------------------------------------

    async def _get_over_plans(
        self,
        bowler: PlayerAgent,
        batsman: PlayerAgent,
        over: int,
        score: int,
        wickets: int,
        target: int | None,
        innings_number: int,
        batting_team: str,
        bowling_team: str,
        home_team: str,
        consecutive_dots: int,
        remaining_balls: int = 6,
    ) -> tuple[list[dict] | None, list[dict] | None]:
        """
        Get over-level batch plans for bowling and batting via concurrent LLM calls.

        Returns (bowling_plan, batting_plan) — either may be None on failure.
        Fires both calls concurrently since batsman plans independently of bowler.
        """
        import asyncio

        pitch_condition = self._pitch_agent.get_condition(over, innings_number)
        weather_condition = self._weather_agent.get_conditions_at_over(over, innings_number)
        crowd_energy = self._crowd_agent.get_energy(
            over=over, batting_team=batting_team,
            wickets_fallen=wickets, score=score, target=target,
        )

        situation = {
            "over": over, "score": score, "wickets": wickets,
            "target": target, "innings": innings_number,
            "pitch": pitch_condition, "weather": weather_condition,
            "crowd_energy": crowd_energy,
        }

        # Build a brief narrative for LLM context
        narrative_parts = [
            f"Over {over + 1}/20. {batting_team}: {score}/{wickets}.",
        ]
        if target:
            needed = target - score
            balls_left = max(1, (20 - over) * 6)
            narrative_parts.append(f"Need {needed} from {balls_left} balls (RRR: {needed * 6 / balls_left:.1f}).")
        narrative_parts.append(f"Conditions: {pitch_condition.get('condition', 'standard')}, crowd energy: {crowd_energy:.0%}.")
        narrative = " ".join(narrative_parts)

        try:
            bowling_task = batch_bowling_plan(
                bowler, over, situation, batsman.get_profile(),
                narrative, remaining_balls=remaining_balls,
            )
            batting_task = batch_batting_plan_independent(
                batsman, over, situation, narrative,
                remaining_balls=remaining_balls,
            )
            # Fire both concurrently
            bowling_plan, batting_plan = await asyncio.gather(
                bowling_task, batting_task,
            )
            return bowling_plan, batting_plan
        except Exception:
            return None, None

    # ------------------------------------------------------------------
    # Innings simulation
    # ------------------------------------------------------------------

    async def _simulate_innings(
        self,
        batting_team: str,
        bowling_team: str,
        innings_number: int,
        target: int | None,
        start_score: int = 0,
        start_wickets: int = 0,
        start_over: int = 0,
        start_ball: int = 0,
    ) -> InningsResult:
        """
        Simulate one innings (up to 20 overs or 10 wickets).

        For LIVE matches, ``start_*`` params resume from mid-innings.

        Args:
            batting_team: Name of the batting team
            bowling_team: Name of the bowling team
            innings_number: 1 or 2
            target: Target to chase (None for first innings)
            start_score: Starting score (for live match resumption)
            start_wickets: Starting wickets fallen (for live match resumption)
            start_over: Starting over number, 0-indexed (for live match resumption)
            start_ball: Starting ball within the over (for live match resumption)

        Returns:
            InningsResult with full innings data
        """
        # Select batting and bowling rosters
        batting_agents = (
            self._team1_agents if batting_team == self._config.team1 else self._team2_agents
        )
        bowling_agents = (
            self._team1_agents if bowling_team == self._config.team1 else self._team2_agents
        )

        batting_order = list(batting_agents.values())
        self._rng.shuffle(batting_order)  # Week 1: random order, Week 2: use actual order

        # Bowler pool: only players who can bowl
        bowlers = [p for p in bowling_agents.values() if p.can_bowl()]
        if not bowlers:
            # Fallback: use all players as bowlers
            bowlers = list(bowling_agents.values())

        # Innings state — initialise from live state when resuming
        score = start_score
        wickets = start_wickets
        extras = 0
        boundaries = 0
        sixes = 0
        balls_list: list[BallEvent] = []
        bowling_cards: dict[str, BowlingCard] = {}
        fall_of_wickets: list[dict] = []
        bowler_overs: dict[str, int] = {}  # balls bowled per bowler
        consecutive_dots = 0  # Track consecutive dot balls for pressure contagion

        # Batting state — advance past dismissed batsmen
        current_batsman_idx = 0
        non_striker_idx = 1
        # Ensure we have at least 2 batsmen
        if len(batting_order) < 2:
            batting_order = batting_order + batting_order  # duplicate if needed

        # When resuming mid-innings, skip past already-dismissed batsmen
        next_in_idx = 2 + start_wickets
        if start_wickets > 0:
            current_batsman_idx = start_wickets
            non_striker_idx = start_wickets + 1
            if current_batsman_idx >= len(batting_order):
                current_batsman_idx = len(batting_order) - 1
            if non_striker_idx >= len(batting_order):
                non_striker_idx = current_batsman_idx

        current_batsman = batting_order[current_batsman_idx]
        non_striker = batting_order[non_striker_idx] if len(batting_order) > 1 else current_batsman
        batsman_balls_faced: dict[str, int] = {}
        batsman_runs: dict[str, int] = {}

        # Bowling rotation
        current_bowler: PlayerAgent | None = None
        prev_bowler_name: str | None = None

        home_team = self._stadium_agent.home_team or batting_team

        # Over-level batching: pre-plan bowling + batting for the full over
        sim_mode = self._config.simulation_mode
        use_over_batching = sim_mode in ("persona", "hybrid")

        # Persona trigger granularity (only matters for persona mode)
        persona_trigger = getattr(self._config, "persona_llm_trigger", "per_over")
        if not persona_trigger:
            persona_trigger = "per_over"

        for over in range(start_over, self._config.max_overs):
            # Choose bowler for this over (can't bowl two consecutive overs)
            available_bowlers = [
                b for b in bowlers
                if bowler_overs.get(b.name, 0) < MAX_BOWLER_OVERS * 6
                and b.name != prev_bowler_name
            ]
            if not available_bowlers:
                # Fallback: allow previous bowler if no one else
                available_bowlers = [
                    b for b in bowlers
                    if bowler_overs.get(b.name, 0) < MAX_BOWLER_OVERS * 6
                ]
            if not available_bowlers:
                available_bowlers = bowlers  # last resort

            # Pick bowler with fewest balls bowled
            current_bowler = min(available_bowlers, key=lambda b: bowler_overs.get(b.name, 0))
            prev_bowler_name = current_bowler.name

            if current_bowler.name not in bowling_cards:
                bowling_cards[current_bowler.name] = BowlingCard(name=current_bowler.name)

            # Check for ball replacement (2026 rule: night matches, after 10th over, once per innings)
            is_night_match = self._match_time is not None and (self._match_time.hour >= 15)  # approximate
            if over >= 10 and is_night_match:
                should_replace = self.check_ball_replacement_request(
                    over_number=over,
                    fielding_team=bowling_team,
                    is_night_match=is_night_match,
                    current_bowler=current_bowler
                )
                if should_replace:
                    self.apply_ball_replacement(bowling_team)

            # --- Over-level batch plan (Persona mode, or Hybrid when pressure is high) ---
            bowling_plan: list[dict] | None = None
            batting_plan: list[dict] | None = None
            plan_ball_idx = 0  # tracks which plan entry to use

            if use_over_batching and sim_mode == "persona":
                # Persona: batch plan based on trigger granularity
                # per_over  → batch every over (default)
                # per_ball  → no batch, per-ball LLM calls handled below
                # per_wicket → batch only on first over (over 0); wicket re-plans handled below
                if persona_trigger == "per_over" or (persona_trigger == "per_wicket" and over == 0):
                    bowling_plan, batting_plan = await self._get_over_plans(
                        current_bowler, current_batsman, over, score, wickets,
                        target, innings_number, batting_team, bowling_team,
                        home_team, consecutive_dots,
                    )
            elif use_over_batching and sim_mode == "hybrid":
                # Hybrid: batch plan when high-leverage over is expected
                est_pressure = compute_pressure_index(
                    innings=innings_number, over=over, wickets=wickets,
                    score=score, target=target, crowd_energy=0.5,
                    player_fatigue=0.3, consecutive_dots=consecutive_dots,
                    total_wickets=self._config.max_wickets,
                )
                # Force LLM batch for: pressure threshold, death overs,
                # wicket clusters, or close chases
                is_high_leverage_over = (
                    est_pressure >= LLM_PRESSURE_THRESHOLD
                    or over >= 18  # death overs always
                    or (wickets >= 3 and over >= 10)  # wicket cluster
                    or (innings_number == 2 and target is not None
                        and over >= 15 and 0 < (target - score) <= 40)
                )
                if is_high_leverage_over:
                    bowling_plan, batting_plan = await self._get_over_plans(
                        current_bowler, current_batsman, over, score, wickets,
                        target, innings_number, batting_team, bowling_team,
                        home_team, consecutive_dots,
                    )

            # Cache pitch + weather per over (they don't change ball-to-ball)
            pitch_condition = self._pitch_agent.get_condition(over, innings_number)
            weather_condition = self._weather_agent.get_conditions_at_over(over, innings_number)

            # Simulate 6 balls in this over
            # When resuming mid-over, skip already-bowled balls
            legal_balls = start_ball if over == start_over and start_ball > 0 else 0
            while legal_balls < 6:

                # Compute fatigue
                batsman_fatigue = min(0.8, batsman_balls_faced.get(current_batsman.name, 0) / 120.0)
                bowler_fatigue = min(0.8, bowler_overs.get(current_bowler.name, 0) / 24.0)

                # Crowd energy
                crowd_energy = self._crowd_agent.get_energy(
                    over=over,
                    batting_team=batting_team,
                    wickets_fallen=wickets,
                    score=score,
                    target=target,
                )

                # Pressure index (7 factors: RRR + wickets_exp + over + dot_contagion + crowd + fatigue + wicket_cushion)
                pressure = compute_pressure_index(
                    innings=innings_number,
                    over=over,
                    wickets=wickets,
                    score=score,
                    target=target,
                    crowd_energy=crowd_energy,
                    player_fatigue=batsman_fatigue,
                    consecutive_dots=consecutive_dots,
                    total_wickets=self._config.max_wickets,
                )

                # Required run rate
                balls_remaining = max(1, (self._config.max_overs - over) * 6 - legal_balls)
                runs_needed = (target - score) if target else 0
                required_rr = (runs_needed * 6) / balls_remaining if target and runs_needed > 0 else 0.0
                current_rr = (score * 6) / max(1, over * 6 + legal_balls) if (over * 6 + legal_balls) > 0 else 0.0

                # Compute dew factor for this over
                is_night_match = self._match_time is not None and (self._match_time.hour >= 15)
                if self._match_state.ball_replacement_restore_balls > 0:
                    # New ball in play — grip restored, dew effect suppressed for this ball
                    dew_factor = 1.0
                    self._match_state.ball_replacement_restore_balls -= 1
                else:
                    dew_factor = self._weather_agent.compute_dew_factor(over, is_night_match)

                # Compute boundary asymmetry factor (use random direction for this ball)
                shot_directions = ["off_side", "square_leg", "extra_cover", "mid_wicket", "third_man", "fine_leg"]
                shot_direction = self._rng.choice(shot_directions)
                batsman_handedness = current_batsman.get_profile().get("batting_style", "right_hand").upper()[:3]  # RHB or LHB
                boundary_asymmetry = self._stadium_agent.get_boundary_asymmetry_factor(
                    shot_direction=shot_direction,
                    batsman_handedness=batsman_handedness
                )

                # Get current bowler's career stats for bat() modifiers
                bowler_career = current_bowler.get_profile().get("career_stats", {})
                
                # --- Core Strategy Analytics for BallContext ---
                is_post_timeout = over in [9, 14] and legal_balls == 0
                is_17th_over = over == 16
                cap_defensive = 0.5 # Default to balanced; hook for CoachAgent evaluation later
                
                # Heuristic for collapse contagion: lost 2+ wickets within the first 6 overs, or general high-speed collapse
                collapse_active = wickets >= 2 and (over * 6 + legal_balls) <= 36
                
                # Anchor penalty: Check if non-striker is slowing down the innings (balls > 15, SR < 115)
                anchor_active = False
                if non_striker:
                    ns_balls = batsman_balls_faced.get(non_striker.name, 0)
                    ns_runs = batsman_runs.get(non_striker.name, 0)
                    if ns_balls > 15 and ns_balls > 0 and (ns_runs / ns_balls) < 1.15:
                        anchor_active = True
                        
                # Clutch factor by franchise tier
                team_upper = batting_team.upper()
                if any(t in team_upper for t in ["CSK", "CHENNAI", "MI", "MUMBAI"]):
                    clutch_factor = 0.8
                elif any(t in team_upper for t in ["PBKS", "PUNJAB", "RCB", "ROYAL"]):
                    clutch_factor = 0.3
                else:
                    clutch_factor = 0.5
                    
                # Lower order independence: Is this batter a bowler?
                role = current_batsman.get_profile().get("role", "").lower()
                batsman_position = next_in_idx - 1  # approximate batting position
                is_lower_order = "bowler" in role or batsman_position >= 7
                
                # --- Captain & Field State Integration ---
                from ..agents.captain_agent import CaptainAgent
                # Retrieve or initialize CaptainAgent for fielding team
                captain = getattr(self, f"_captain_{bowling_team}", None)
                if not captain:
                    captain = CaptainAgent(
                        name=f"{bowling_team} Captain", 
                        team=bowling_team, 
                        defensive_tendency=self._rng.uniform(0.3, 0.7)
                    )
                    setattr(self, f"_captain_{bowling_team}", captain)
                
                b_style = current_bowler.get_profile().get("bowling_style", "right_arm_pace")
                c_aggro = current_batsman.get_profile().get("personality_traits", {}).get("aggression_index", 0.5) > 0.6
                field_state = captain.set_field(
                    over=over,
                    bowler_style=b_style,
                    pressure_index=pressure,
                    is_batter_aggressive=c_aggro
                )

                ball_ctx = BallContext(
                    over=over,
                    ball=legal_balls,
                    batting_team_score=score,
                    wickets_fallen=wickets,
                    target=target,
                    pressure_index=pressure,
                    pitch_condition=pitch_condition,
                    weather_condition=weather_condition,
                    batsman_fatigue=batsman_fatigue,
                    bowler_fatigue=bowler_fatigue,
                    is_batsman_home=batting_team == home_team,
                    is_bowler_home=bowling_team == home_team,
                    balls_faced_this_innings=batsman_balls_faced.get(current_batsman.name, 0),
                    partnership_runs=0,  # simplified Week 1
                    required_run_rate=required_rr,
                    current_run_rate=current_rr,
                    dew_factor=dew_factor,
                    boundary_asymmetry_factor=boundary_asymmetry,
                    bowler_economy=bowler_career.get("bowling_economy", 8.5),
                    bowler_bowling_avg=bowler_career.get("bowling_avg", 30.0),
                    match_index=getattr(self._match_state, "match_index", 1),
                    bowler_style=current_bowler.get_profile().get("bowling_style", "right_arm_pace"),
                    umpire_strictness=getattr(self, "_umpire_strictness", 1.0),
                    bowler_death_spec=current_bowler.get_profile().get("personality_traits", {}).get("death_overs_specialization", 0.5),
                    is_post_timeout=is_post_timeout,
                    is_17th_over=is_17th_over,
                    captain_defensive_tendency=cap_defensive,
                    batting_collapse_active=collapse_active,
                    anchor_penalty_active=anchor_active,
                    franchise_clutch_factor=clutch_factor,
                    fielding_conversion_probability=0.85, # Drop catch scalar
                    lower_order_strike_independence=is_lower_order,
                    over_rate_pressure_active=over >= 18, # 23: In real matches, an over rate penalty brings an extra fielder inside the circle.
                    field_state=field_state,
                )

                # Simulate the ball — mode-aware
                if use_over_batching and hasattr(current_batsman, "bat_with_persona"):
                    # Check if we should use LLM for this ball
                    # Hybrid mode triggers LLM on:
                    #   1. Pressure index >= threshold (0.65)
                    #   2. Death overs (18+) — always high-leverage
                    #   3. Wicket cluster (3+ down AND over >= 10)
                    #   4. Close chase: innings 2, last 5 overs, <= 40 runs needed
                    #   5. First ball after a wicket (new batsman pressure)
                    is_death_over = over >= 18
                    is_wicket_cluster = wickets >= 3 and over >= 10
                    is_close_chase = (
                        innings_number == 2 and target is not None
                        and over >= 15 and 0 < (target - score) <= 40
                    )
                    is_post_wicket_ball = (
                        len(fall_of_wickets) > 0
                        and fall_of_wickets[-1].get("over", "").startswith(f"{over}.")
                        and legal_balls <= 1
                    )

                    if sim_mode == "persona":
                        if persona_trigger == "per_ball":
                            # Per-ball: always use LLM (no batch, individual calls)
                            use_llm_this_ball = True
                        elif persona_trigger == "per_wicket":
                            # Per-wicket: only use LLM if we have a batch plan from
                            # a wicket re-plan or first over; otherwise probabilistic
                            use_llm_this_ball = bool(bowling_plan and batting_plan)
                        else:
                            # Per-over (default): use batch plan or per-ball fallback
                            use_llm_this_ball = True
                    elif sim_mode == "hybrid":
                        use_llm_this_ball = (
                            pressure >= LLM_PRESSURE_THRESHOLD
                            or is_death_over
                            or is_wicket_cluster
                            or is_close_chase
                            or is_post_wicket_ball
                        )
                    else:
                        use_llm_this_ball = False

                    if use_llm_this_ball:
                        try:
                            # Use batched plan if available, otherwise fall back to per-ball
                            if bowling_plan and batting_plan and plan_ball_idx < len(bowling_plan) and plan_ball_idx < len(batting_plan):
                                # Use pre-planned decisions from batch
                                bowling_decision = bowling_plan[plan_ball_idx]
                                batting_decision = batting_plan[plan_ball_idx]
                                # Resolve outcome from intent matchup — only
                                # here do both plans meet
                                from .outcome_resolver import resolve_persona_outcome as _resolve
                                outcome = _resolve(
                                    batting_decision=batting_decision,
                                    bowling_decision=bowling_decision,
                                    ball_context=current_batsman._ball_context_to_dict(ball_ctx),
                                    rng=self._rng,
                                )
                            else:
                                # Fallback: per-ball LLM calls (batch failed or exhausted)
                                # Pre-render BOTH contexts upfront (they're independent)
                                ball_ctx_dict = current_batsman._ball_context_to_dict(ball_ctx)
                                stadium_dims = self._stadium_agent.get_dimensions()
                                bowl_comm = self._comm_bus.get_recent_for_agent(current_bowler.agent_id, bowling_team) if self._comm_bus else None
                                bat_comm = self._comm_bus.get_recent_for_agent(current_batsman.agent_id, batting_team) if self._comm_bus else None
                                bowl_narrative = self._context_renderer.render_bowling_context(
                                    ball_context=ball_ctx_dict,
                                    pitch_condition=pitch_condition,
                                    weather_condition=weather_condition,
                                    crowd_state={"energy": crowd_energy},
                                    stadium_info=stadium_dims,
                                    comm_messages=bowl_comm,
                                    recent_memory=current_bowler.recall_memory(limit=6),
                                    batsman_profile=current_batsman.get_profile(),
                                )
                                bat_narrative = self._context_renderer.render_batting_context(
                                    ball_context=ball_ctx_dict,
                                    pitch_condition=pitch_condition,
                                    weather_condition=weather_condition,
                                    crowd_state={"energy": crowd_energy},
                                    stadium_info=stadium_dims,
                                    comm_messages=bat_comm,
                                    recent_memory=current_batsman.recall_memory(limit=6),
                                    bowler_profile=current_bowler.get_profile(),
                                    batsman_profile=current_batsman.get_profile(),
                                )
                                # Fire bowler and batsman concurrently — neither
                                # sees the other's plan (real cricket: batsman
                                # commits to intent before seeing the delivery).
                                bowling_task = current_bowler.bowl_with_persona(
                                    ball_ctx, current_batsman.get_profile(), bowl_narrative,
                                    comm_messages=bowl_comm, rng=self._rng,
                                )
                                batting_task = current_batsman.get_batting_decision(
                                    ball_ctx, bat_narrative,
                                    comm_messages=bat_comm,
                                )
                                bowling_decision, batting_decision = await asyncio.gather(
                                    bowling_task, batting_task,
                                )
                                # Resolve outcome through matchup matrix —
                                # only HERE do both plans meet (slog vs yorker = wicket, etc.)
                                from .outcome_resolver import resolve_persona_outcome
                                outcome = resolve_persona_outcome(
                                    batting_decision=batting_decision,
                                    bowling_decision=bowling_decision,
                                    ball_context=current_batsman._ball_context_to_dict(ball_ctx),
                                    rng=self._rng,
                                )
                                # Record batting memory
                                current_batsman.add_memory({
                                    "type": "ball_faced",
                                    "over": ball_ctx.over,
                                    "ball": ball_ctx.ball,
                                    "outcome": "wicket" if outcome.is_wicket else f"{outcome.runs}_runs",
                                    "runs": outcome.runs,
                                    "is_wicket": outcome.is_wicket,
                                    "intent": batting_decision.get("intent", "unknown"),
                                    "shot": batting_decision.get("shot_selection", "unknown"),
                                    "pressure_index": ball_ctx.pressure_index,
                                })
                        except Exception:
                            # Fall back to probabilistic on any persona failure
                            outcome = current_batsman.bat(ball_ctx, rng=self._rng)
                    else:
                        # Hybrid mode below pressure threshold — skip LLM entirely
                        outcome = current_batsman.bat(ball_ctx, rng=self._rng)
                else:
                    # Probabilistic path (original behavior)
                    outcome = current_batsman.bat(ball_ctx, rng=self._rng)

                plan_ball_idx += 1

                # Update counts
                is_legal_ball = not outcome.is_wide and not outcome.is_no_ball

                # Update scores
                score += outcome.runs
                batsman_runs[current_batsman.name] = (
                    batsman_runs.get(current_batsman.name, 0) + outcome.runs
                )
                if outcome.is_wide or outcome.is_no_ball:
                    extras += 1
                    score += 1  # wide/no-ball penalty run

                if is_legal_ball:
                    legal_balls += 1
                    batsman_balls_faced[current_batsman.name] = (
                        batsman_balls_faced.get(current_batsman.name, 0) + 1
                    )
                    bowler_overs[current_bowler.name] = (
                        bowler_overs.get(current_bowler.name, 0) + 1
                    )

                # Update bowling card
                card = bowling_cards[current_bowler.name]
                card.balls_bowled += 1
                card.runs_conceded += outcome.runs + (1 if outcome.is_wide or outcome.is_no_ball else 0)
                card.overs_bowled = card.balls_bowled / 6.0
                if outcome.is_wide:
                    card.wides += 1
                if outcome.is_no_ball:
                    card.no_balls += 1

                if outcome.is_boundary:
                    boundaries += 1
                    consecutive_dots = 0  # Reset dot counter on boundary
                if outcome.is_six:
                    sixes += 1
                    consecutive_dots = 0  # Reset dot counter on six

                # Track consecutive dots for pressure contagion
                if is_legal_ball and outcome.runs == 0 and not outcome.is_wicket:
                    consecutive_dots += 1
                else:
                    consecutive_dots = 0  # Reset on any runs or wicket

                # Record ball event
                balls_list.append(BallEvent(
                    over=over,
                    ball=legal_balls,
                    innings=innings_number,
                    batsman=current_batsman.name,
                    bowler=current_bowler.name,
                    runs=outcome.runs,
                    extras=1 if (outcome.is_wide or outcome.is_no_ball) else 0,
                    is_wicket=outcome.is_wicket,
                    dismissal_type=outcome.dismissal_type,
                    is_wide=outcome.is_wide,
                    is_no_ball=outcome.is_no_ball,
                    is_boundary=outcome.is_boundary,
                    is_six=outcome.is_six,
                    pressure_index=pressure,
                    score_after=score,
                    wickets_after=wickets + (1 if outcome.is_wicket else 0),
                    commentary=outcome.notes,
                ))

                # Handle wicket
                if outcome.is_wicket:
                    card.wickets += 1
                    wickets += 1
                    fall_of_wickets.append({
                        "wicket": wickets,
                        "score": score,
                        "over": f"{over}.{legal_balls}",
                        "batsman": current_batsman.name,
                        "dismissal": outcome.dismissal_type,
                        "bowler": current_bowler.name,
                    })

                    if wickets >= self._config.max_wickets:
                        # All out
                        overs_played = over + legal_balls / 6.0
                        return InningsResult(
                            team=batting_team,
                            batting_order=[p.name for p in batting_order],
                            total_score=score,
                            wickets=wickets,
                            overs_played=round(overs_played, 1),
                            balls=balls_list,
                            bowling_figures=bowling_cards,
                            fall_of_wickets=fall_of_wickets,
                            extras=extras,
                            boundaries=boundaries,
                            sixes=sixes,
                        )

                    # Bring in next batsman
                    if next_in_idx < len(batting_order):
                        current_batsman = batting_order[next_in_idx]
                        next_in_idx += 1

                        # Re-plan remaining balls with new batsman (over-level batching)
                        # In hybrid mode, a wicket fall is always high-leverage — re-plan
                        # In persona per_ball mode, skip batch (per-ball LLM handles it)
                        remaining_in_over = 6 - legal_balls
                        should_replan = (
                            use_over_batching
                            and sim_mode in ("persona", "hybrid")
                            and remaining_in_over > 0
                            and not (sim_mode == "persona" and persona_trigger == "per_ball")
                        )
                        if should_replan:
                            bowling_plan, batting_plan = await self._get_over_plans(
                                current_bowler, current_batsman, over, score, wickets,
                                target, innings_number, batting_team, bowling_team,
                                home_team, consecutive_dots,
                                remaining_balls=remaining_in_over,
                            )
                            plan_ball_idx = 0  # reset index for new plans

                        # Communication trigger: captain → new batsman after wicket
                        if self._comm_bus and self._comm_bus.enabled:
                            captain = batting_order[0]  # first in order is captain (simplified)
                            runs_needed = (target - score) if target else 0
                            msg_content = (
                                f"Take your time settling in. "
                                f"{'Need ' + str(runs_needed) + ' more.' if target else 'Build from here.'}"
                            )
                            self._comm_bus.post(AgentMessage(
                                sender_id=captain.agent_id,
                                sender_name=captain.name,
                                sender_role="captain",
                                team=batting_team,
                                recipient=current_batsman.agent_id,
                                message_type="instruction",
                                content=msg_content,
                                over=over, ball=legal_balls, innings=innings_number,
                            ))
                    else:
                        # Should not reach here with 10-wicket limit
                        break

                # Rotate strike on odd runs
                if outcome.runs % 2 == 1 and is_legal_ball:
                    current_batsman, non_striker = non_striker, current_batsman

                # Check if target achieved (second innings)
                if target and score >= target:
                    overs_played = over + legal_balls / 6.0
                    return InningsResult(
                        team=batting_team,
                        batting_order=[p.name for p in batting_order],
                        total_score=score,
                        wickets=wickets,
                        overs_played=round(overs_played, 1),
                        balls=balls_list,
                        bowling_figures=bowling_cards,
                        fall_of_wickets=fall_of_wickets,
                        extras=extras,
                        boundaries=boundaries,
                        sixes=sixes,
                    )

            # End of over — communication triggers
            if self._comm_bus and self._comm_bus.enabled:
                # Strategic timeout communication (after over 6 and 13)
                if over in (6, 13):
                    coach = self._coach_team1 if batting_team == self._config.team1 else self._coach_team2
                    timeout_msg = (
                        f"Strategic timeout. Score: {score}/{wickets} after {over + 1} overs. "
                        f"{'Target: ' + str(target) + '. Need ' + str(target - score) + ' from ' + str((20 - over - 1) * 6) + ' balls.' if target else 'Set a big total.'}"
                    )
                    self._comm_bus.post(AgentMessage(
                        sender_id=coach.agent_id,
                        sender_name=coach.get_profile().get("name", "Coach"),
                        sender_role="coach",
                        team=batting_team,
                        recipient="team",
                        message_type="strategy",
                        content=timeout_msg,
                        over=over, ball=6, innings=innings_number,
                    ))

                # Coach → next bowler instruction at over change
                bowling_coach = self._coach_team1 if bowling_team == self._config.team1 else self._coach_team2
                self._comm_bus.post(AgentMessage(
                    sender_id=bowling_coach.agent_id,
                    sender_name=bowling_coach.get_profile().get("name", "Coach"),
                    sender_role="coach",
                    team=bowling_team,
                    recipient="bowling_unit",
                    message_type="instruction",
                    content=f"Over {over + 1} done. {score}/{wickets}. Keep the pressure on.",
                    over=over, ball=6, innings=innings_number,
                ))

            # End of over — rotate strike
            current_batsman, non_striker = non_striker, current_batsman

        # End of 20 overs
        return InningsResult(
            team=batting_team,
            batting_order=[p.name for p in batting_order],
            total_score=score,
            wickets=wickets,
            overs_played=self._config.max_overs,
            balls=balls_list,
            bowling_figures=bowling_cards,
            fall_of_wickets=fall_of_wickets,
            extras=extras,
            boundaries=boundaries,
            sixes=sixes,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def check_ball_replacement_request(
        self, over_number: int, fielding_team: str, is_night_match: bool, current_bowler: PlayerAgent | None = None
    ) -> bool:
        """
        CoachAgent decides: should we request ball replacement?

        Logic: If dew significant (dew_factor < 0.85) AND spinner in attack,
        request new ball.

        Args:
            over_number: Current over
            fielding_team: 'team1' or 'team2' (team name)
            is_night_match: Is night match?
            current_bowler: The bowler currently bowling

        Returns:
            bool True if captain should request replacement
        """
        # Check eligibility
        if not is_night_match:
            return False
        if over_number < 10:
            return False

        # Check if already used replacement this innings
        team_key = "team1" if fielding_team == self._config.team1 else "team2"
        if self._match_state.ball_replacements_used.get(team_key, 0) > 0:
            return False  # Already used once per innings

        # Check conditions: dew + spinner
        dew_factor = self._weather_agent.compute_dew_factor(over_number, is_night_match)

        # Check if spinner in attack
        is_spinner_bowling = False
        if current_bowler:
            bowling_type = current_bowler.get_profile().get("bowling_style", "pace")
            is_spinner_bowling = "spin" in bowling_type.lower()

        # Decision: if significant dew + spinner, request new ball
        if dew_factor < 0.85 and is_spinner_bowling:
            return True

        return False

    def apply_ball_replacement(self, fielding_team: str) -> None:
        """
        Apply ball replacement effect.

        - Increment usage counter
        - Reset ball_age_overs to 0
        - Temporarily boost spin effectiveness (dew_factor → 1.0 for 1 over)
        - Log decision
        """
        team_key = "team1" if fielding_team == self._config.team1 else "team2"
        self._match_state.ball_replacements_used[team_key] += 1
        self._match_state.current_ball_age_overs = 0
        # New ball restores grip — dew_factor=1.0 for 6 balls (one over)
        self._match_state.ball_replacement_restore_balls = 6

    def _resolve_toss(self) -> tuple[str, str]:
        """
        Determine toss winner and decision.

        Uses config if already set, otherwise simulates the toss.
        """
        if self._config.toss_winner and self._config.toss_decision:
            return self._config.toss_winner, self._config.toss_decision

        # Simulate toss
        toss_winner = self._rng.choice([self._config.team1, self._config.team2])

        # Coach decides based on venue and weather
        stadium_rec = self._stadium_agent.get_toss_recommendation()
        dew_factor = self._weather_agent.get_dew_factor()

        coach = self._coach_team1 if toss_winner == self._config.team1 else self._coach_team2
        toss_decision = coach.decide_toss(stadium_rec, dew_factor)

        return toss_winner, toss_decision

    def _determine_winner(
        self,
        innings1: InningsResult,
        innings2: InningsResult,
        target: int,
    ) -> tuple[str | None, str, int]:
        """
        Determine match winner from innings results.

        Returns:
            (winner_name_or_None, win_type, win_margin)
        """
        if innings2.total_score >= target:
            # Team batting second wins
            winner = innings2.team
            wickets_remaining = self._config.max_wickets - innings2.wickets
            return winner, "wickets", wickets_remaining
        elif innings2.total_score == innings1.total_score:
            # Tie — in a real match this would go to super over
            # For simulation, pick random winner to represent super over outcome
            winner = self._rng.choice([innings1.team, innings2.team])
            return winner, "super_over", 0
        else:
            # Team batting first wins
            winner = innings1.team
            run_difference = innings1.total_score - innings2.total_score
            return winner, "runs", run_difference

    def _collect_key_moments(
        self,
        innings1: InningsResult,
        innings2: InningsResult,
    ) -> list[str]:
        """Extract key moments from both innings for the report."""
        moments = []
        innings2_target = innings1.total_score + 1  # target for innings 2

        # First innings milestones
        if innings1.sixes >= 5:
            moments.append(f"{innings1.team} hit {innings1.sixes} sixes in first innings")
        if innings1.total_score >= 200:
            moments.append(f"Massive total: {innings1.team} posted {innings1.total_score}")
        elif innings1.total_score <= 130:
            moments.append(f"Below-par total: {innings1.team} restricted to {innings1.total_score}")

        # Bowling performances (no player names — aggregate simulation)
        three_wicket_hauls = sum(1 for card in innings1.bowling_figures.values() if card.wickets >= 3)
        if three_wicket_hauls > 0:
            moments.append(
                f"Bowling unit delivered {three_wicket_hauls} three-wicket-haul(s) in the innings"
            )

        # Second innings drama
        if innings2.total_score >= innings2_target - 5 and innings2.total_score < innings2_target:
            moments.append(
                f"Nail-biting finish: {innings2.team} fell short by "
                f"{innings2_target - 1 - innings2.total_score} run(s)"
            )

        if innings2.wickets >= 8 and innings2.total_score >= innings2_target:
            moments.append(f"Remarkable chase: {innings2.team} won with only 2 wickets to spare!")

        return moments[:5]  # top 5 key moments

    @property
    def simulation_id(self) -> str:
        return self._simulation_id
