"""
IPL Oracle API Routes.

All routes are under /api/ prefix.
Every simulation response includes:
- X-IPL-Oracle-Disclaimer header (via middleware)
- 'disclaimer' field in response body

API Surface:
  GET  /api/schedule/today
  GET  /api/schedule/upcoming
  POST /api/simulation/start
  GET  /api/simulation/{id}/status
  WS   /api/simulation/{id}/stream
  GET  /api/simulation/{id}/result
  GET  /api/agents/{id}
  GET  /api/agents/{id}/{agent_id}
  POST /api/agents/{id}/{agent_id}/interview
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..config.settings import SimulationMode
from ..data.match_state_detector import MatchStateDetector, MatchStatus
from ..data.schedule_manager import ScheduleManager
from ..simulation.match_engine import MatchConfig, MatchEngine
from ..simulation.parallel_runner import ParallelRunner
from ..agents.report_agent import ReportAgent, DISCLAIMER

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SimulationStartRequest(BaseModel):
    """Request body for POST /api/simulation/start"""
    match_id: str = Field(..., description="IPL 2026 match ID from schedule")
    team1: str = Field(..., description="Team 1 name")
    team2: str = Field(..., description="Team 2 name")
    venue: str = Field(..., description="Full venue name")
    match_start_time: str = Field(..., description="Match start time (ISO 8601)")
    pitch_type: str = Field(default="balanced", description="Pitch type")
    sim_count: int = Field(default=100, ge=1, le=500, description="Number of parallel simulations to run")
    team1_players: list[dict] = Field(default_factory=list, description="Team 1 player profiles")
    team2_players: list[dict] = Field(default_factory=list, description="Team 2 player profiles")
    toss_winner: str | None = Field(default=None)
    toss_decision: str | None = Field(default=None, description="'bat' or 'field'")
    simulation_mode: str = Field(
        default="hybrid",
        description="Simulation mode: 'persona' (full LLM, 1-10 sims), 'hybrid' (LLM at key moments), 'probabilistic' (no LLM, fast)",
    )


class InterviewRequest(BaseModel):
    """Request body for POST /api/agents/{id}/{agent_id}/interview"""
    question: str = Field(..., description="Question to ask the agent")
    context: dict = Field(default_factory=dict, description="Optional additional context")


# ---------------------------------------------------------------------------
# In-memory session registry (Week 1 — no persistence)
# ---------------------------------------------------------------------------

class SimulationSession:
    """Represents one active or completed simulation session."""

    def __init__(self, sim_id: str, request: SimulationStartRequest) -> None:
        self.sim_id = sim_id
        self.request = request
        self.status = "pending"  # pending → running → completed | failed
        self.progress_pct = 0
        self.phase = "initializing"
        self.sims_complete = 0
        self.sims_total = request.sim_count
        self.result: dict | None = None
        self.agents: dict[str, Any] = {}
        self.error: str | None = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: str | None = None
        self.match_status: MatchStatus | None = None
        self.state_details: dict | None = None
        # WebSocket listeners for streaming
        self._ws_listeners: list[WebSocket] = []
        self._event_queue: asyncio.Queue = asyncio.Queue()

    def add_ws_listener(self, ws: WebSocket) -> None:
        self._ws_listeners.append(ws)

    def remove_ws_listener(self, ws: WebSocket) -> None:
        self._ws_listeners = [w for w in self._ws_listeners if w != ws]

    async def broadcast_event(self, event: dict) -> None:
        """Broadcast an event to all connected WebSocket clients."""
        event_with_disclaimer = {**event, "disclaimer": DISCLAIMER}
        message = json.dumps(event_with_disclaimer)
        dead_sockets = []
        for ws in self._ws_listeners:
            try:
                await ws.send_text(message)
            except Exception:
                dead_sockets.append(ws)
        for ws in dead_sockets:
            self.remove_ws_listener(ws)


# Global session registry
_sessions: dict[str, SimulationSession] = {}

# ---------------------------------------------------------------------------
# Router setup
# ---------------------------------------------------------------------------

router = APIRouter()
schedule_manager = ScheduleManager()
state_detector = MatchStateDetector()


# ---------------------------------------------------------------------------
# Schedule routes
# ---------------------------------------------------------------------------

@router.get("/schedule/today")
async def get_today_schedule() -> dict:
    """
    Return today's IPL matches.

    Filters: LIVE and FUTURE only — COMPLETED matches are excluded per spec.
    """
    matches = schedule_manager.get_today_matches()
    return {
        "disclaimer": DISCLAIMER,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "matches": matches,
        "total": len(matches),
    }


@router.get("/schedule/upcoming")
async def get_upcoming_schedule(days: int = 7) -> dict:
    """
    Return upcoming IPL matches in the next N days.

    Query params:
        days: Number of days ahead (default 7, max 30)
    """
    days = min(days, 30)
    matches = schedule_manager.get_upcoming_matches(days=days)
    return {
        "disclaimer": DISCLAIMER,
        "days_ahead": days,
        "matches": matches,
        "total": len(matches),
    }


# ---------------------------------------------------------------------------
# Simulation routes
# ---------------------------------------------------------------------------

@router.post("/simulation/start")
async def start_simulation(request: SimulationStartRequest) -> dict:
    """
    Start a match simulation.

    1. Validates match state — COMPLETED → 400 error (hard reject)
    2. Spawns agents from config
    3. Runs simulation (Week 1: single sim)
    4. Returns simulation ID for status polling

    Always includes disclaimer in response.
    """
    # --- Step 1: Match state detection (MUST run before anything else) ---
    match_info = {
        "match_start_time": request.match_start_time,
        "status": "upcoming",
    }
    match_status, state_details = state_detector.detect(match_info)

    if match_status == MatchStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "MATCH_COMPLETED",
                "message": state_detector.get_rejection_message(request.team1, request.team2),
                "upcoming_fixtures_url": "/api/schedule/upcoming",
                "disclaimer": DISCLAIMER,
            },
        )

    if match_status == MatchStatus.UNKNOWN:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "UNKNOWN_MATCH_STATE",
                "message": "Cannot determine match state. Provide a valid match_start_time.",
                "disclaimer": DISCLAIMER,
            },
        )

    # --- Step 2: Build simulation session ---
    sim_id = str(uuid.uuid4())
    session = SimulationSession(sim_id=sim_id, request=request)
    session.match_status = match_status
    session.state_details = state_details
    _sessions[sim_id] = session

    # --- Step 3: Build player rosters ---
    # Cascade: IPLT20 → Cricbuzz → News RSS → SQUAD_SEED (local)
    if request.team1_players and request.team2_players:
        team1_players = request.team1_players
        team2_players = request.team2_players
        team1_confirmed = True
        team2_confirmed = True
    else:
        cascade_result = await _fetch_rosters_cascade(
            request.team1, request.team2, match_status,
        )
        if request.team1_players:
            team1_players = request.team1_players
            team1_confirmed = True
        else:
            team1_players = cascade_result["team1_players"]
            team1_confirmed = cascade_result["team1_confirmed"]
        if request.team2_players:
            team2_players = request.team2_players
            team2_confirmed = True
        else:
            team2_players = cascade_result["team2_players"]
            team2_confirmed = cascade_result["team2_confirmed"]

    # --- Step 4: Resolve simulation mode (auto-downgrade if needed) ---
    requested_mode = request.simulation_mode
    sim_count = request.sim_count
    effective_mode = _resolve_simulation_mode(requested_mode, sim_count)

    # --- Step 5: Build match config ---
    config = MatchConfig(
        match_id=request.match_id,
        team1=request.team1,
        team2=request.team2,
        venue=request.venue,
        match_date=request.match_start_time[:10],
        match_time=request.match_start_time,
        team1_players=team1_players,
        team2_players=team2_players,
        pitch_type=request.pitch_type,
        toss_winner=request.toss_winner,
        toss_decision=request.toss_decision,
        sim_count=sim_count,
        simulation_mode=effective_mode,
    )

    # --- Step 6: Run simulation asynchronously ---
    asyncio.create_task(_run_simulation_task(sim_id, config, sim_count))

    mode_note = ""
    if effective_mode != requested_mode:
        mode_note = f" (auto-downgraded from '{requested_mode}' to '{effective_mode}' for {sim_count} sims)"

    caveats = list(state_details.get("caveats", []))
    if not team1_confirmed:
        caveats.append(f"{request.team1}: using probable XI from squad data (confirmed XI not available)")
    if not team2_confirmed:
        caveats.append(f"{request.team2}: using probable XI from squad data (confirmed XI not available)")

    return {
        "disclaimer": DISCLAIMER,
        "simulation_id": sim_id,
        "status": "started",
        "match_status": match_status,
        "match_state_details": state_details,
        "simulation_mode": effective_mode,
        "message": f"Simulation started{mode_note}. Poll GET /api/simulation/{sim_id}/status for progress.",
        "caveats": caveats,
    }


@router.get("/simulation/{sim_id}/status")
async def get_simulation_status(sim_id: str) -> dict:
    """Return simulation progress and current phase."""
    session = _get_session_or_404(sim_id)

    return {
        "disclaimer": DISCLAIMER,
        "simulation_id": sim_id,
        "status": session.status,
        "progress_pct": session.progress_pct,
        "phase": session.phase,
        "sims_complete": session.sims_complete,
        "sims_total": session.sims_total,
        "match_status": session.match_status,
        "created_at": session.created_at,
        "completed_at": session.completed_at,
        "error": session.error,
    }


@router.websocket("/simulation/{sim_id}/stream")
async def stream_simulation(websocket: WebSocket, sim_id: str) -> None:
    """
    WebSocket endpoint for live ball-by-ball simulation events.

    Connect to receive real-time events as they are generated.
    Each event includes the disclaimer field.
    """
    await websocket.accept()

    session = _sessions.get(sim_id)
    if not session:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"Simulation {sim_id} not found",
            "disclaimer": DISCLAIMER,
        }))
        await websocket.close()
        return

    session.add_ws_listener(websocket)

    # Send current state immediately
    await websocket.send_text(json.dumps({
        "type": "connected",
        "simulation_id": sim_id,
        "status": session.status,
        "disclaimer": DISCLAIMER,
    }))

    try:
        # Keep connection alive until simulation completes or client disconnects
        while session.status not in ("completed", "failed"):
            await asyncio.sleep(0.5)

        # Send final status
        await websocket.send_text(json.dumps({
            "type": "simulation_complete",
            "simulation_id": sim_id,
            "status": session.status,
            "disclaimer": DISCLAIMER,
        }))
    except WebSocketDisconnect:
        pass
    finally:
        session.remove_ws_listener(websocket)


@router.get("/simulation/{sim_id}/result")
async def get_simulation_result(sim_id: str) -> dict:
    """Return the full simulation result with report."""
    session = _get_session_or_404(sim_id)

    if session.status == "running":
        raise HTTPException(
            status_code=202,
            detail={
                "message": "Simulation still running",
                "progress_pct": session.progress_pct,
                "disclaimer": DISCLAIMER,
            },
        )

    if session.status == "failed":
        raise HTTPException(
            status_code=500,
            detail={
                "error": session.error,
                "disclaimer": DISCLAIMER,
            },
        )

    if not session.result:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No result available",
                "disclaimer": DISCLAIMER,
            },
        )

    return {
        "disclaimer": DISCLAIMER,
        "simulation_id": sim_id,
        **session.result,
    }


# ---------------------------------------------------------------------------
# Agent routes
# ---------------------------------------------------------------------------

@router.get("/agents/{sim_id}")
async def get_simulation_agents(sim_id: str) -> dict:
    """Return all agents for a simulation session."""
    session = _get_session_or_404(sim_id)

    return {
        "disclaimer": DISCLAIMER,
        "simulation_id": sim_id,
        "agents": session.agents,
        "total": len(session.agents),
    }


@router.get("/agents/{sim_id}/{agent_id}")
async def get_agent_detail(sim_id: str, agent_id: str) -> dict:
    """Return detailed profile and decision log for a single agent."""
    session = _get_session_or_404(sim_id)

    agent_data = session.agents.get(agent_id)
    if not agent_data:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Agent {agent_id} not found in simulation {sim_id}",
                "disclaimer": DISCLAIMER,
            },
        )

    return {
        "disclaimer": DISCLAIMER,
        "simulation_id": sim_id,
        "agent": agent_data,
    }


@router.post("/agents/{sim_id}/{agent_id}/interview")
async def interview_agent(
    sim_id: str,
    agent_id: str,
    request: InterviewRequest,
) -> dict:
    """
    Ask any agent a question post-simulation.

    Uses LLM when a provider is configured (ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY).
    Falls back to a stub response when no provider is available.
    """
    session = _get_session_or_404(sim_id)

    agent_data = session.agents.get(agent_id)
    if not agent_data:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Agent {agent_id} not found in simulation {sim_id}",
                "disclaimer": DISCLAIMER,
            },
        )

    from ..services.llm_client import llm_client

    agent_type = agent_data.get("agent_type", "unknown")
    profile = agent_data.get("profile", {})
    name = profile.get("name", agent_type)
    decision_log = agent_data.get("decision_log", [])[-10:]  # last 10 decisions

    response_text: str
    if llm_client.is_enabled():
        system_prompt = (
            f"You are {name}, a {agent_type} agent who participated in an IPL cricket simulation. "
            f"Answer the question from your agent's perspective — reference your profile traits "
            f"and decisions you made during the simulation. Be direct and in-character. "
            f"Keep your answer under 150 words."
        )
        llm_response = await llm_client.think(
            system_prompt=system_prompt,
            user_prompt=request.question,
            context={
                "agent_profile": profile,
                "recent_decisions": decision_log,
                **(request.context or {}),
            },
            max_tokens=300,
        )
        response_text = llm_response or (
            f"{name} ({agent_type}): I don't have enough context to answer that right now. "
            f"Check my decision log for what I did during the simulation."
        )
        source = "llm"
    else:
        response_text = (
            f"{name} ({agent_type}) received: '{request.question}'. "
            f"Set ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY to enable "
            f"LLM-powered agent interviews. See this agent's decision_log for simulation data."
        )
        source = "stub"

    return {
        "disclaimer": DISCLAIMER,
        "simulation_id": sim_id,
        "agent_id": agent_id,
        "question": request.question,
        "response": response_text,
        "agent_type": agent_type,
        "source": source,
    }


# ---------------------------------------------------------------------------
# Background simulation task
# ---------------------------------------------------------------------------

async def _run_simulation_task(
    sim_id: str,
    config: MatchConfig,
    sim_count: int,
) -> None:
    """
    Background task that runs simulations via ParallelRunner and aggregates results.

    For sim_count=1: runs a single deterministic simulation.
    For sim_count>1: runs batched parallel simulations (10 per batch, 2s pause between).
    """
    session = _sessions[sim_id]
    session.status = "running"
    session.phase = "spawning_agents"

    try:
        await session.broadcast_event({
            "type": "phase_change",
            "phase": "spawning_agents",
            "message": "Spawning agents...",
        })

        session.phase = "simulating"
        await session.broadcast_event({
            "type": "phase_change",
            "phase": "simulating",
            "message": f"Running {sim_count} simulation(s)...",
        })

        def _on_progress(completed: int, total: int) -> None:
            session.sims_complete = completed
            session.progress_pct = int(completed / total * 80)  # 0–80% during sims

        runner = ParallelRunner(
            config=config,
            sim_count=sim_count,
            on_progress=_on_progress,
        )
        results = await runner.run()

        if not results:
            raise RuntimeError(
                f"All {sim_count} simulations failed. "
                f"Errors: {'; '.join(runner.errors[:3])}"
            )

        session.phase = "generating_report"
        session.progress_pct = 85
        await session.broadcast_event({
            "type": "phase_change",
            "phase": "generating_report",
            "message": f"Generating report from {len(results)} simulations...",
        })

        # Aggregate stats across all sims
        summary = runner.get_summary_stats()

        # Generate statistical report
        report_agent = ReportAgent(simulation_id=sim_id)
        report = report_agent.generate_report(
            team1=config.team1,
            team2=config.team2,
            sim_results=[r.to_dict() for r in results],
            venue=config.venue,
            match_state=str(session.match_status),
        )

        # Build innings summary from most representative sim (median score sim)
        median_result = _pick_median_result(results, config.team1)

        winning_factors = _compute_winning_factors(
            median_result, results, config, summary,
        )

        # Extract hidden factors from median sim for narrative
        hidden_factors = _extract_hidden_factors(median_result, results, config)

        # Always generate LLM narrative (all modes including probabilistic)
        try:
            narrative = await report_agent.generate_llm_narrative(
                report, config.team1, config.team2,
                winning_factors=winning_factors,
                hidden_factors=hidden_factors,
                simulation_mode=config.simulation_mode,
            )
            if narrative and narrative.strip():
                report["llm_narrative"] = narrative
            else:
                logger.warning("LLM narrative returned empty — check API key / provider / credits")
        except Exception as exc:
            logger.error("LLM narrative generation failed: %s", exc, exc_info=True)

        # Store structured analysis data (available even without LLM)
        report["hidden_factors"] = hidden_factors

        # Store agents info (from the first sim as representative)
        first_result = results[0]
        session.agents = {
            sim_id: {
                "agent_id": sim_id,
                "agent_type": "match_engine",
                "profile": {"team1": config.team1, "team2": config.team2},
                "decision_log": [],
            }
        }

        session.result = {
            "summary": summary,
            "simulation_mode": config.simulation_mode,
            "match_result": median_result.to_dict(),
            "report": report,
            "winning_factors": winning_factors,
            "innings": {
                "innings1": _innings_dict(median_result.innings1),
                "innings2": _innings_dict(median_result.innings2),
            },
        }

        session.status = "completed"
        session.progress_pct = 100
        session.sims_complete = len(results)
        session.completed_at = datetime.now(timezone.utc).isoformat()

        await session.broadcast_event({
            "type": "simulation_complete",
            "status": "completed",
            "total_sims": len(results),
            "win_percentages": summary.get("win_percentages", {}),
            "winner": median_result.winner,
            "team1_score": median_result.team1_score,
            "team2_score": median_result.team2_score,
        })

    except Exception as e:
        session.status = "failed"
        session.error = str(e)
        session.completed_at = datetime.now(timezone.utc).isoformat()
        await session.broadcast_event({
            "type": "error",
            "message": str(e),
        })
        raise


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _pick_median_result(results: list, team1: str):
    """Return the simulation result whose team1 score is closest to the median."""
    from ..simulation.match_engine import MatchResult
    scores = sorted(r.team1_score for r in results)
    median_score = scores[len(scores) // 2]
    return min(results, key=lambda r: abs(r.team1_score - median_score))


def _innings_dict(innings) -> dict:
    """Serialise an InningsResult to a plain dict."""
    phase_scoring = _compute_phase_scoring(innings)
    return {
        "team": innings.team,
        "score": innings.total_score,
        "wickets": innings.wickets,
        "overs": innings.overs_played,
        "boundaries": innings.boundaries,
        "sixes": innings.sixes,
        "run_rate": innings.run_rate,
        "fall_of_wickets": innings.fall_of_wickets,
        "phase_scoring": phase_scoring,
        "bowling_figures": {
            name: {
                "overs": round(card.overs_bowled, 1),
                "runs": card.runs_conceded,
                "wickets": card.wickets,
                "economy": card.economy,
            }
            for name, card in innings.bowling_figures.items()
        },
    }


def _compute_phase_scoring(innings) -> dict:
    """Compute phase-wise scoring breakdown (powerplay / middle / death)."""
    phases = {
        "powerplay": {"overs": "1-6", "runs": 0, "wickets": 0, "boundaries": 0, "sixes": 0, "balls": 0},
        "middle": {"overs": "7-15", "runs": 0, "wickets": 0, "boundaries": 0, "sixes": 0, "balls": 0},
        "death": {"overs": "16-20", "runs": 0, "wickets": 0, "boundaries": 0, "sixes": 0, "balls": 0},
    }
    for b in innings.balls:
        over_num = b.over + 1  # 0-indexed → 1-indexed
        if over_num <= 6:
            phase = "powerplay"
        elif over_num <= 15:
            phase = "middle"
        else:
            phase = "death"
        phases[phase]["runs"] += b.runs + b.extras
        phases[phase]["balls"] += 1
        if b.is_wicket:
            phases[phase]["wickets"] += 1
        if b.is_boundary:
            phases[phase]["boundaries"] += 1
        if b.is_six:
            phases[phase]["sixes"] += 1

    # Compute run rates
    for p in phases.values():
        overs = p["balls"] / 6.0 if p["balls"] > 0 else 0
        p["run_rate"] = round(p["runs"] / overs, 2) if overs > 0 else 0.0

    return phases


def _compute_winning_factors(
    median_result, results: list, config, summary: dict
) -> list[dict]:
    """Analyse the simulation results and extract key winning factors."""
    factors = []
    winner = median_result.winner
    if not winner:
        return factors

    loser = config.team2 if winner == config.team1 else config.team1
    win_pct = summary.get("win_percentages", {}).get(winner, 50)

    # 1. Toss advantage
    toss_winners_who_won = sum(
        1 for r in results if r.toss_winner == r.winner and r.winner is not None
    )
    toss_pct = round(toss_winners_who_won / len(results) * 100) if results else 0
    if toss_pct > 60:
        factors.append({
            "factor": "Toss Advantage",
            "impact": "high",
            "detail": f"Toss winners won {toss_pct}% of simulations — toss is decisive at this venue.",
        })

    # 2. Batting superiority
    if winner == config.team1:
        avg_winner_score = summary.get("avg_team1_score", 0)
        avg_loser_score = summary.get("avg_team2_score", 0)
    else:
        avg_winner_score = summary.get("avg_team2_score", 0)
        avg_loser_score = summary.get("avg_team1_score", 0)

    score_gap = avg_winner_score - avg_loser_score
    if score_gap > 15:
        factors.append({
            "factor": "Batting Superiority",
            "impact": "high",
            "detail": f"{winner} outscored {loser} by {score_gap:.0f} runs on average across simulations.",
        })
    elif score_gap > 5:
        factors.append({
            "factor": "Batting Edge",
            "impact": "medium",
            "detail": f"{winner} scored {score_gap:.0f} more runs on average — a slim but consistent edge.",
        })

    # 3. Bowling dominance — aggregate across all simulations
    # Count how many sims the winning side took 3+ wickets with any single bowler
    bowling_dominant_sims = 0
    avg_wickets_best_bowler = 0.0
    for r in results:
        if r.winner != winner:
            continue
        bowling_inn = r.innings1 if r.innings1.team != winner else r.innings2
        if bowling_inn.bowling_figures:
            best_wk = max(card.wickets for card in bowling_inn.bowling_figures.values())
            avg_wickets_best_bowler += best_wk
            if best_wk >= 3:
                bowling_dominant_sims += 1
    winner_sims = sum(1 for r in results if r.winner == winner)
    if winner_sims > 0:
        avg_wickets_best_bowler /= winner_sims
    bowling_pct = round(bowling_dominant_sims / len(results) * 100) if results else 0
    if bowling_pct > 30:
        factors.append({
            "factor": "Bowling Impact",
            "impact": "high",
            "detail": f"In {bowling_pct}% of simulations, the bowling unit delivered 3+ wicket hauls — restricting opposition totals consistently.",
        })
    elif avg_wickets_best_bowler >= 2.0:
        factors.append({
            "factor": "Bowling Pressure",
            "impact": "medium",
            "detail": f"Best bowler averaged {avg_wickets_best_bowler:.1f} wickets per sim — sustained pressure through the attack.",
        })

    # 4. Death overs dominance — aggregate across all simulations
    total_death_winner = 0
    total_death_loser = 0
    death_sim_count = 0
    for r in results:
        if r.winner != winner:
            continue
        w_inn = r.innings1 if r.innings1.team == winner else r.innings2
        l_inn = r.innings1 if r.innings1.team != winner else r.innings2
        total_death_winner += sum(b.runs + b.extras for b in w_inn.balls if b.over >= 15)
        total_death_loser += sum(b.runs + b.extras for b in l_inn.balls if b.over >= 15)
        death_sim_count += 1
    if death_sim_count > 0:
        avg_death_winner = total_death_winner / death_sim_count
        avg_death_loser = total_death_loser / death_sim_count
        death_gap = avg_death_winner - avg_death_loser
        if death_gap > 12:
            factors.append({
                "factor": "Death Overs Surge",
                "impact": "high",
                "detail": f"Winning side averaged {avg_death_winner:.0f} runs in death overs (15–20) vs opposition's {avg_death_loser:.0f} — a {death_gap:.0f}-run phase advantage.",
            })

    # 5. Powerplay control — aggregate across all simulations
    total_pp_winner = 0
    total_pp_loser = 0
    total_pp_wk_winner = 0
    total_pp_wk_loser = 0
    pp_sim_count = 0
    for r in results:
        if r.winner != winner:
            continue
        w_inn = r.innings1 if r.innings1.team == winner else r.innings2
        l_inn = r.innings1 if r.innings1.team != winner else r.innings2
        total_pp_winner += sum(b.runs + b.extras for b in w_inn.balls if b.over < 6)
        total_pp_loser += sum(b.runs + b.extras for b in l_inn.balls if b.over < 6)
        total_pp_wk_winner += sum(1 for b in w_inn.balls if b.over < 6 and b.is_wicket)
        total_pp_wk_loser += sum(1 for b in l_inn.balls if b.over < 6 and b.is_wicket)
        pp_sim_count += 1
    if pp_sim_count > 0:
        avg_pp_winner = total_pp_winner / pp_sim_count
        avg_pp_loser = total_pp_loser / pp_sim_count
        avg_pp_wk_winner = total_pp_wk_winner / pp_sim_count
        avg_pp_wk_loser = total_pp_wk_loser / pp_sim_count
        if avg_pp_winner > avg_pp_loser + 8 and avg_pp_wk_winner < 1.5:
            factors.append({
                "factor": "Powerplay Domination",
                "impact": "medium",
                "detail": f"Winning side averaged {avg_pp_winner:.0f} runs losing {avg_pp_wk_winner:.1f} wickets in the powerplay vs opposition's {avg_pp_loser:.0f}/{avg_pp_wk_loser:.1f}.",
            })

    # 6. Win margin consistency
    if win_pct >= 70:
        factors.append({
            "factor": "Overwhelming Favourites",
            "impact": "high",
            "detail": f"{winner} won {win_pct:.0f}% of {len(results)} simulations — a dominant prediction.",
        })
    elif win_pct >= 55:
        factors.append({
            "factor": "Slight Edge",
            "impact": "low",
            "detail": f"Close contest — {winner} won {win_pct:.0f}% of simulations. Could go either way.",
        })

    # Sort by impact
    impact_order = {"high": 0, "medium": 1, "low": 2}
    factors.sort(key=lambda f: impact_order.get(f["impact"], 3))

    return factors


def _extract_hidden_factors(
    median_result, results: list, config,
) -> dict:
    """Extract hidden institutional factors from simulation results for LLM narrative."""
    factors: dict = {}

    # Toss advantage
    toss_winners_who_won = sum(
        1 for r in results if r.toss_winner == r.winner and r.winner is not None
    )
    toss_pct = round(toss_winners_who_won / len(results) * 100) if results else 50
    if toss_pct > 55:
        factors["toss_advantage"] = f"Toss winners won {toss_pct}% of sims — toss is decisive"
    else:
        factors["toss_advantage"] = f"Toss winners won {toss_pct}% — toss not decisive"

    # Dew factor from the balls (approximation from second innings)
    inn2_balls = median_result.innings2.balls if median_result.innings2 else []
    if inn2_balls:
        late_extras = sum(1 for b in inn2_balls if b.over >= 15 and b.extras > 0)
        factors["dew_factor"] = 0.85 if late_extras > 3 else 0.95

    # Boundary asymmetry (from stadium agent data)
    from ..agents.stadium_agent import StadiumAgent
    stadium = StadiumAgent.for_venue(config.venue, run_id="factors")
    dims = stadium.get_dimensions()
    if dims:
        factors["boundary_asymmetry"] = {
            "straight": dims.get("straight_boundary_m", "N/A"),
            "square": dims.get("square_boundary_m", "N/A"),
        }

    # Pressure peaks from median result
    if median_result.pressure_peaks:
        peak_count = len(median_result.pressure_peaks)
        factors["pressure_peaks"] = f"{peak_count} high-pressure moments detected"

    # Ball replacement usage
    ball_repl = getattr(median_result, "ball_replacements_used", None)
    if ball_repl:
        factors["ball_replacement_used"] = str(ball_repl)

    # Pitch type
    factors["pitch_type"] = config.pitch_type

    # Average margins
    margins = [r.win_margin for r in results if r.win_margin]
    if margins:
        factors["avg_win_margin"] = round(sum(margins) / len(margins), 1)

    return factors


def _get_session_or_404(sim_id: str) -> SimulationSession:
    """Get a simulation session or raise 404."""
    session = _sessions.get(sim_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Simulation {sim_id} not found",
                "disclaimer": DISCLAIMER,
            },
        )
    return session


def _resolve_simulation_mode(requested: str, sim_count: int) -> str:
    """
    Auto-downgrade simulation mode based on sim count to prevent cost explosion.

    Rules:
    - PERSONA mode: max 10 sims. >10 → downgrade to HYBRID.
    - HYBRID mode: max 100 sims. >100 → downgrade to PROBABILISTIC.
    - PROBABILISTIC: no limit.
    """
    from ..config.settings import settings, SimulationMode

    mode = requested.lower()
    if mode not in (SimulationMode.PERSONA, SimulationMode.HYBRID, SimulationMode.PROBABILISTIC):
        mode = SimulationMode.HYBRID

    if mode == SimulationMode.PERSONA and sim_count > settings.persona_max_sims:
        mode = SimulationMode.HYBRID

    if mode == SimulationMode.HYBRID and sim_count > settings.hybrid_max_sims:
        mode = SimulationMode.PROBABILISTIC

    return mode


async def _fetch_rosters_cascade(
    team1: str,
    team2: str,
    match_status: MatchStatus,
) -> dict[str, Any]:
    """
    Fetch playing XI for both teams using the multi-source cascade.

    Priority: IPLT20 → Cricbuzz → Google News RSS → SQUAD_SEED (local).
    Web sources are tried for IMMINENT and LIVE matches.
    FUTURE matches always use SQUAD_SEED.

    Returns:
        {
            "team1_players": list[dict],
            "team2_players": list[dict],
            "team1_confirmed": bool,
            "team2_confirmed": bool,
            "source": str,
        }
    """
    from ..data.xi_cascade import fetch_playing_xi

    team1_full = _ABBREV_TO_FULL.get(team1, team1)
    team2_full = _ABBREV_TO_FULL.get(team2, team2)
    team1_abbrev = next((k for k, v in _ABBREV_TO_FULL.items() if v == team1_full), team1[:3].upper())
    team2_abbrev = next((k for k, v in _ABBREV_TO_FULL.items() if v == team2_full), team2[:3].upper())

    # Only try web sources for IMMINENT or LIVE matches
    if match_status in (MatchStatus.IMMINENT, MatchStatus.LIVE):
        try:
            cascade = await fetch_playing_xi(
                team1_full, team2_full, team1_abbrev, team2_abbrev,
            )
            t1_names = cascade.get("team1_xi", [])
            t2_names = cascade.get("team2_xi", [])
            source = cascade.get("source", "squad_seed")

            logger.info(
                "XI Cascade: source=%s, %s=%d names, %s=%d names",
                source, team1_abbrev, len(t1_names), team2_abbrev, len(t2_names),
            )

            # Build full player profiles from names
            t1_players = _build_roster_from_names(t1_names, team1_full) if t1_names else _build_default_roster(team1)
            t2_players = _build_roster_from_names(t2_names, team2_full) if t2_names else _build_default_roster(team2)

            return {
                "team1_players": t1_players,
                "team2_players": t2_players,
                "team1_confirmed": cascade.get("team1_confirmed", False),
                "team2_confirmed": cascade.get("team2_confirmed", False),
                "source": source,
            }
        except Exception as exc:
            logger.warning("XI Cascade failed, falling back to SQUAD_SEED: %s", exc)

    # FUTURE matches or cascade failure → SQUAD_SEED
    return {
        "team1_players": _build_default_roster(team1),
        "team2_players": _build_default_roster(team2),
        "team1_confirmed": False,
        "team2_confirmed": False,
        "source": "squad_seed",
    }


async def _fetch_or_seed_roster(
    team_name: str,
    match_status: MatchStatus,
) -> tuple[list[dict], bool]:
    """Legacy single-team roster fetch. Kept for backward compatibility."""
    result = await _fetch_rosters_cascade(team_name, team_name, match_status)
    return result["team1_players"], result["team1_confirmed"]


_ABBREV_TO_FULL: dict[str, str] = {
    "MI": "Mumbai Indians", "CSK": "Chennai Super Kings",
    "RCB": "Royal Challengers Bengaluru", "KKR": "Kolkata Knight Riders",
    "DC": "Delhi Capitals", "SRH": "Sunrisers Hyderabad",
    "RR": "Rajasthan Royals", "PBKS": "Punjab Kings",
    "GT": "Gujarat Titans", "LSG": "Lucknow Super Giants",
}

CURRENT_YEAR = 2026


def _build_roster_from_names(names: list[str], team_name: str) -> list[dict]:
    """
    Build player profiles by matching scraped names against SQUAD_SEED.

    Names from web scrapers are matched to seed data using fuzzy matching
    (last name, first name, substring). Players not in SQUAD_SEED get
    a minimal allrounder profile.
    """
    from ..agents.player_agent import PlayerAgent
    from ..services.squad_manager import SQUAD_SEED

    full_name = _ABBREV_TO_FULL.get(team_name, team_name)
    squad = SQUAD_SEED.get(full_name) or SQUAD_SEED.get(team_name, [])
    if not squad:
        for key in SQUAD_SEED:
            if team_name.lower() in key.lower() or key.lower() in team_name.lower():
                squad = SQUAD_SEED[key]
                full_name = key
                break

    players: list[dict] = []
    used_indices: set[int] = set()

    for name in names[:11]:
        # Try to match against seed
        matched = _fuzzy_match_player(name, squad, used_indices)
        if matched is not None:
            idx, seed_player = matched
            used_indices.add(idx)
            birth_year = seed_player.get("birth_year")
            ipl_debut_year = seed_player.get("ipl_debut_year")
            profile = PlayerAgent.build_profile(
                name=seed_player["name"],
                team=full_name,
                role=seed_player.get("role", "allrounder"),
                batting_style=seed_player.get("batting_style", "right_hand"),
                bowling_style=seed_player.get("bowling_style", "none"),
                is_foreign_player=seed_player.get("is_foreign", False),
                age=(CURRENT_YEAR - birth_year) if birth_year else 28,
                experience_years=(CURRENT_YEAR - ipl_debut_year) if ipl_debut_year else 5,
            )
        else:
            # Player not in seed — create minimal profile
            profile = PlayerAgent.build_profile(
                name=name,
                team=full_name,
                role="allrounder",
                batting_style="right_hand",
                bowling_style="none",
                is_foreign_player=False,
                age=28,
                experience_years=5,
            )
        players.append(profile)

    # Pad to 11 if fewer matched
    if len(players) < 11:
        for i, p in enumerate(squad):
            if i not in used_indices and len(players) < 11:
                birth_year = p.get("birth_year")
                ipl_debut_year = p.get("ipl_debut_year")
                profile = PlayerAgent.build_profile(
                    name=p["name"],
                    team=full_name,
                    role=p.get("role", "allrounder"),
                    batting_style=p.get("batting_style", "right_hand"),
                    bowling_style=p.get("bowling_style", "none"),
                    is_foreign_player=p.get("is_foreign", False),
                    age=(CURRENT_YEAR - birth_year) if birth_year else 28,
                    experience_years=(CURRENT_YEAR - ipl_debut_year) if ipl_debut_year else 5,
                )
                players.append(profile)

    return players


def _fuzzy_match_player(
    name: str,
    squad: list[dict],
    used: set[int],
) -> tuple[int, dict] | None:
    """Fuzzy-match a scraped name to a SQUAD_SEED entry."""
    name_lower = name.lower().strip()
    name_parts = name_lower.split()

    for idx, player in enumerate(squad):
        if idx in used:
            continue
        seed_name = player["name"].lower()
        seed_parts = seed_name.split()

        # Exact match
        if name_lower == seed_name:
            return idx, player
        # Last name match
        if name_parts and seed_parts and name_parts[-1] == seed_parts[-1]:
            return idx, player
        # First name match (only if distinctive enough)
        if name_parts and seed_parts and name_parts[0] == seed_parts[0] and len(name_parts[0]) > 3:
            return idx, player
        # Substring match
        if name_lower in seed_name or seed_name in name_lower:
            return idx, player

    return None


def _build_default_roster(team_name: str) -> list[dict]:
    """
    Build an 11-player roster from real SQUAD_SEED data.

    Accepts both abbreviations (RCB) and full names (Royal Challengers Bengaluru).
    Falls back to generic profiles only if team is not found in SQUAD_SEED.
    """
    from ..agents.player_agent import PlayerAgent
    from ..services.squad_manager import SQUAD_SEED

    # Resolve abbreviation to full name
    full_name = _ABBREV_TO_FULL.get(team_name, team_name)
    squad = SQUAD_SEED.get(full_name)

    # Try the original name if abbreviation lookup failed
    if not squad:
        squad = SQUAD_SEED.get(team_name)

    if not squad:
        # Last resort: try matching by substring
        for key in SQUAD_SEED:
            if team_name.lower() in key.lower() or key.lower() in team_name.lower():
                squad = SQUAD_SEED[key]
                full_name = key
                break

    if not squad:
        # Truly unknown team — return minimal generic roster
        return _build_generic_roster(team_name)

    players = []
    for p in squad[:11]:
        birth_year = p.get("birth_year")
        ipl_debut_year = p.get("ipl_debut_year")
        age = (CURRENT_YEAR - birth_year) if birth_year else 28
        experience_years = (CURRENT_YEAR - ipl_debut_year) if ipl_debut_year else 5

        profile = PlayerAgent.build_profile(
            name=p["name"],
            team=full_name,
            role=p.get("role", "allrounder"),
            batting_style=p.get("batting_style", "right_hand"),
            bowling_style=p.get("bowling_style", "none"),
            is_foreign_player=p.get("is_foreign", False),
            age=age,
            experience_years=experience_years,
        )
        players.append(profile)

    return players


def _build_generic_roster(team_name: str) -> list[dict]:
    """Fallback generic roster for unknown teams."""
    from ..agents.player_agent import PlayerAgent

    roles = [
        ("Opener1", "batsman", "right_hand", "none", False),
        ("Opener2", "batsman", "left_hand", "none", True),
        ("No3", "batsman", "right_hand", "none", False),
        ("No4", "batsman", "right_hand", "none", False),
        ("No5", "allrounder", "right_hand", "right_arm_pace", True),
        ("No6", "allrounder", "right_hand", "right_arm_offbreak", False),
        ("WK", "wicketkeeper", "right_hand", "none", False),
        ("Bowler1", "bowler", "right_hand", "right_arm_pace", False),
        ("Bowler2", "bowler", "right_hand", "right_arm_pace", True),
        ("Spinner1", "bowler", "right_hand", "legbreak", False),
        ("Spinner2", "bowler", "left_hand", "left_arm_spin", False),
    ]

    players = []
    for suffix, role, bat_style, bowl_style, is_foreign in roles:
        profile = PlayerAgent.build_profile(
            name=f"{team_name}_{suffix}",
            team=team_name,
            role=role,
            batting_style=bat_style,
            bowling_style=bowl_style,
            is_foreign_player=is_foreign,
        )
        players.append(profile)

    return players
