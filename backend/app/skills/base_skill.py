"""
BaseSkill — Abstract base class for all agent skills.

Skills are composable decision modules that agents invoke. Each skill:
- Has a standard execute() interface
- Knows its own LLM requirements
- Can operate in all three simulation modes (persona/hybrid/probabilistic)
- Returns a structured dict matching the skill's output schema
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent


class BaseSkill(ABC):
    """Abstract base class for all simulation skills."""

    skill_name: str = "base"
    skill_type: str = "generic"       # "batting", "bowling", "tactical", "communication"
    requires_llm: bool = False        # Whether this skill needs an LLM call

    @abstractmethod
    async def execute(
        self,
        agent: BaseAgent,
        context: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        """
        Execute the skill.

        Args:
            agent: The agent invoking the skill
            context: Skill-specific context dict
            mode: "persona", "hybrid", or "probabilistic"

        Returns:
            Structured result dict matching the skill's output schema.
        """
        ...

    def should_use_llm(self, mode: str, pressure: float = 0.0) -> bool:
        """Determine whether this skill invocation should use LLM."""
        if mode == "probabilistic":
            return False
        if mode == "persona":
            return self.requires_llm
        # hybrid: only at high pressure
        if mode == "hybrid":
            return self.requires_llm and pressure >= 0.85
        return False
