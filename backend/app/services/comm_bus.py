"""
CommBus — Per-simulation inter-agent communication bus.

Agents post messages (strategy, encouragement, instructions); messages are
injected into LLM persona context at decision time. The bus itself never
makes LLM calls — it is a data structure.

In PERSONA mode: messages are LLM-generated.
In HYBRID mode: messages are template strings from persona JSON.
In PROBABILISTIC mode: the bus is disabled (no messages posted or read).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentMessage:
    """A single message from one agent to another."""

    sender_id: str
    sender_name: str
    sender_role: str            # "captain", "coach", "bowler", "batsman", etc.
    team: str                   # Which team this message belongs to
    recipient: str              # "team", "batting_pair", "bowling_unit", or agent_id
    message_type: str           # "strategy", "encouragement", "instruction", "field_change", "warning", "celebration"
    content: str                # The actual message text
    over: int = 0
    ball: int = 0
    innings: int = 1
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "sender_role": self.sender_role,
            "team": self.team,
            "recipient": self.recipient,
            "message_type": self.message_type,
            "content": self.content,
            "over": self.over,
            "ball": self.ball,
            "innings": self.innings,
            "timestamp": self.timestamp,
        }


class CommBus:
    """
    Per-simulation message queue for inter-agent communication.

    Usage:
        bus = CommBus(run_id="sim_001")
        bus.post(AgentMessage(sender_id="...", sender_name="Rohit Sharma", ...))
        recent = bus.get_recent_for_agent(agent_id="...", limit=5)
    """

    def __init__(self, run_id: str, enabled: bool = True) -> None:
        self._run_id = run_id
        self._enabled = enabled
        self._messages: list[AgentMessage] = []

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def post(self, message: AgentMessage) -> None:
        """Post a message to the bus. No-op if bus is disabled."""
        if not self._enabled:
            return
        self._messages.append(message)

    def get_recent_for_agent(
        self,
        agent_id: str,
        team: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Get recent messages relevant to a specific agent.

        Returns messages where:
        - recipient is "team" and same team, OR
        - recipient is the agent's ID, OR
        - recipient is "batting_pair" or "bowling_unit" (broad match)

        Most recent first.
        """
        if not self._enabled:
            return []

        relevant = []
        for msg in reversed(self._messages):
            if team and msg.team != team:
                continue
            if msg.recipient in ("team", "batting_pair", "bowling_unit") or msg.recipient == agent_id:
                relevant.append(msg.to_dict())
            if len(relevant) >= limit:
                break

        return relevant

    def get_team_messages(
        self,
        team: str,
        since_over: int = 0,
        since_innings: int = 1,
    ) -> list[dict[str, Any]]:
        """Get all team messages since a given over in a given innings."""
        if not self._enabled:
            return []

        return [
            msg.to_dict()
            for msg in self._messages
            if msg.team == team
            and msg.innings >= since_innings
            and msg.over >= since_over
        ]

    def get_messages_by_type(
        self,
        message_type: str,
        team: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get messages filtered by type (e.g., 'strategy', 'encouragement')."""
        if not self._enabled:
            return []

        results = []
        for msg in reversed(self._messages):
            if msg.message_type == message_type:
                if team and msg.team != team:
                    continue
                results.append(msg.to_dict())
                if len(results) >= limit:
                    break
        return results

    def clear(self) -> None:
        """Clear all messages. Used between simulation runs."""
        self._messages.clear()

    def get_all_messages(self) -> list[dict[str, Any]]:
        """Return all messages for post-sim audit."""
        return [msg.to_dict() for msg in self._messages]
