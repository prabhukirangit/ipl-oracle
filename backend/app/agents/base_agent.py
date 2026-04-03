"""
BaseAgent — Abstract base class for all IPL Oracle agents.

Every agent in the system MUST extend this class. No exceptions.
Provides: unique agent_id, read-only profile, per-agent memory, think() stub, decision log.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class BaseAgent(ABC):
    """
    Abstract base for all IPL Oracle agents.

    Key design rules:
    - Profile is READ-ONLY during simulation (set once at factory spawn)
    - Memory is mutable but isolated per run_id
    - think() is a stub in Week 1 — returns None (no LLM calls)
    - Decision log captures all key decisions for post-sim review
    """

    def __init__(
        self,
        agent_type: str,
        profile: dict[str, Any],
        run_id: str | None = None,
    ) -> None:
        """
        Initialise a BaseAgent.

        Args:
            agent_type: Human-readable type identifier (e.g. 'player', 'stadium')
            profile: Read-only dict of agent characteristics. Set once, never modified.
            run_id: Unique simulation run identifier for memory isolation.
                    Defaults to a new UUID if not provided.
        """
        self._agent_id: str = str(uuid.uuid4())
        self._agent_type: str = agent_type
        self._profile: dict[str, Any] = dict(profile)  # defensive copy — do not mutate
        self._run_id: str = run_id or str(uuid.uuid4())

        # Per-agent memory: list of event dicts, isolated by run_id
        self._memory: list[dict[str, Any]] = []

        # Decision log: structured record of every decision this agent made
        self._decision_log: list[dict[str, Any]] = []

        # Agent creation timestamp
        self._created_at: datetime = datetime.utcnow()

    # ------------------------------------------------------------------
    # Identity properties (read-only)
    # ------------------------------------------------------------------

    @property
    def agent_id(self) -> str:
        """Unique identifier for this agent instance."""
        return self._agent_id

    @property
    def agent_type(self) -> str:
        """Type label for this agent (e.g. 'player', 'pitcher', 'stadium')."""
        return self._agent_type

    @property
    def run_id(self) -> str:
        """Simulation run ID — used to isolate memory across parallel sims."""
        return self._run_id

    # ------------------------------------------------------------------
    # Profile access (read-only)
    # ------------------------------------------------------------------

    def get_profile(self) -> dict[str, Any]:
        """
        Return a copy of the agent's read-only profile.

        Callers MUST NOT modify the returned dict. The profile is set once at
        AgentFactory spawn time and is shared (read-only) across all simulations.
        """
        return dict(self._profile)

    # ------------------------------------------------------------------
    # Memory interface
    # ------------------------------------------------------------------

    def add_memory(self, event: dict[str, Any]) -> None:
        """
        Record an event in this agent's memory.

        Each event should have at minimum:
        - 'type': str — event category (e.g. 'ball_faced', 'wicket', 'over_change')
        - 'description': str — human-readable summary
        - Any additional domain-specific fields

        Args:
            event: Dictionary describing the event to remember.
        """
        memory_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "run_id": self._run_id,
            "agent_id": self._agent_id,
            **event,
        }
        self._memory.append(memory_entry)

    def recall_memory(self, event_type: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """
        Retrieve recent memories, optionally filtered by event type.

        Args:
            event_type: If provided, only return events of this type.
            limit: Maximum number of memories to return (most recent first).

        Returns:
            List of memory event dicts, most recent first.
        """
        memories = self._memory
        if event_type:
            memories = [m for m in memories if m.get("type") == event_type]
        return list(reversed(memories[-limit:]))

    def clear_memory(self) -> None:
        """Clear all memories for this agent. Used between simulation runs."""
        self._memory.clear()

    # ------------------------------------------------------------------
    # Decision log
    # ------------------------------------------------------------------

    def log_decision(
        self,
        decision_type: str,
        decision: Any,
        reasoning: str = "",
        confidence: float = 1.0,
        context: dict[str, Any] | None = None,
    ) -> None:
        """
        Record a decision made by this agent for post-sim audit.

        Args:
            decision_type: Category of decision (e.g. 'shot_selection', 'bowling_change')
            decision: The actual decision value
            reasoning: Human-readable explanation of why this decision was made
            confidence: Confidence score (0-1). 1.0 = deterministic, <1 = probabilistic
            context: Optional additional context (over, ball, score, etc.)
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "run_id": self._run_id,
            "agent_id": self._agent_id,
            "agent_type": self._agent_type,
            "decision_type": decision_type,
            "decision": decision,
            "reasoning": reasoning,
            "confidence": confidence,
            "context": context or {},
        }
        self._decision_log.append(entry)

    def get_decision_log(self) -> list[dict[str, Any]]:
        """Return the full decision log for this agent."""
        return list(self._decision_log)

    # ------------------------------------------------------------------
    # LLM interface (hybrid mode — Week 3+)
    # ------------------------------------------------------------------

    async def think(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        *,
        require_llm: bool = False,
        max_tokens: int = 2048,
    ) -> str | None:
        """
        Invoke the LLM for high-leverage decisions (hybrid mode).

        Calls claude-sonnet-4-6 when:
        - ANTHROPIC_API_KEY is set, AND
        - pressure_index in context >= LLM_PRESSURE_THRESHOLD (0.65), OR require_llm=True

        Falls back to None (probabilistic path) when not enabled or below threshold.

        Args:
            prompt: The reasoning prompt to send to the LLM
            context: Structured context dict. If context["pressure_index"] >= threshold,
                     LLM is called automatically.
            require_llm: If True, always attempt LLM call regardless of pressure index.
                         Raises NotImplementedError if LLM is not configured.

        Returns:
            LLM response string, or None (probabilistic fallback).
        """
        # Import here to avoid circular imports at module load time
        from ..services.llm_client import llm_client

        pressure = (context or {}).get("pressure_index", 0.0)
        use_llm = require_llm or llm_client.should_use_llm(pressure)

        if not use_llm:
            return None

        if require_llm and not llm_client.is_enabled():
            raise NotImplementedError(
                "LLM calls require ANTHROPIC_API_KEY to be set. "
                "Set require_llm=False to use probabilistic fallback."
            )

        system_prompt = (
            f"You are a {self._agent_type} agent in an IPL cricket simulation. "
            f"Agent ID: {self._agent_id[:8]}. "
            f"Make a decisive, concise tactical decision. "
            f"Output only your decision and brief reasoning (2-3 sentences max)."
        )
        return await llm_client.think(
            system_prompt=system_prompt,
            user_prompt=prompt,
            context=context,
            max_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # Persona support
    # ------------------------------------------------------------------

    @property
    def persona(self) -> dict[str, Any]:
        """Return the agent's LLM persona dict (empty if none loaded)."""
        return self._profile.get("persona", {})

    @property
    def has_persona(self) -> bool:
        """Whether this agent has a loaded persona."""
        return bool(self._profile.get("persona"))

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise agent to a dict for API responses."""
        return {
            "agent_id": self._agent_id,
            "agent_type": self._agent_type,
            "run_id": self._run_id,
            "created_at": self._created_at.isoformat(),
            "profile": self.get_profile(),
            "memory_count": len(self._memory),
            "decision_count": len(self._decision_log),
        }

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"agent_id={self._agent_id[:8]!r}, "
            f"type={self._agent_type!r}, "
            f"run_id={self._run_id[:8]!r})"
        )
