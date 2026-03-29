"""
SkillRouter — Dispatches skill calls and respects simulation mode.

Central registry for all skills. The MatchEngine calls skills through here
rather than directly, ensuring mode-aware routing and consistent error handling.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from .base_skill import BaseSkill

if TYPE_CHECKING:
    from ..agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class SkillRouter:
    """
    Routes skill invocations based on simulation mode.

    Usage:
        router = SkillRouter(mode="persona")
        router.register(BattingDecisionSkill())
        result = await router.invoke("batting_decision", agent, context)
    """

    def __init__(self, mode: str = "hybrid") -> None:
        self._mode = mode
        self._skills: dict[str, BaseSkill] = {}

    @property
    def mode(self) -> str:
        return self._mode

    def register(self, skill: BaseSkill) -> None:
        """Register a skill instance."""
        self._skills[skill.skill_name] = skill

    def register_all(self, skills: list[BaseSkill]) -> None:
        """Register multiple skills at once."""
        for skill in skills:
            self.register(skill)

    def has_skill(self, skill_name: str) -> bool:
        return skill_name in self._skills

    async def invoke(
        self,
        skill_name: str,
        agent: BaseAgent,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Invoke a skill by name.

        Args:
            skill_name: Registered skill name
            agent: The agent making the decision
            context: Skill-specific context

        Returns:
            Skill result dict

        Raises:
            KeyError: If skill is not registered
        """
        skill = self._skills.get(skill_name)
        if skill is None:
            raise KeyError(f"Skill '{skill_name}' not registered. Available: {list(self._skills.keys())}")

        try:
            result = await skill.execute(agent, context, self._mode)
            return result
        except Exception as exc:
            logger.warning(
                "Skill '%s' failed for agent %s (mode=%s): %s. Falling back to probabilistic.",
                skill_name, agent.agent_id[:8], self._mode, exc,
            )
            # Fall back to probabilistic mode on any skill failure
            return await skill.execute(agent, context, "probabilistic")

    def get_registered_skills(self) -> list[str]:
        """List all registered skill names."""
        return list(self._skills.keys())


def create_skill_router(mode: str = "hybrid") -> SkillRouter:
    """
    Factory: create a SkillRouter with all standard skills registered.

    Registers 12 skills:
      LLM skills: batting_decision, bowling_strategy, toss_analysis,
                  impact_player_debate, team_huddle, bowling_change,
                  field_placement, pressure_response
      Non-LLM skills: matchup_analysis, collapse_detection,
                      super_over, phase_strategy

    Called once per simulation session.
    """
    from .batting_decision import BattingDecisionSkill
    from .bowling_strategy import BowlingStrategySkill
    from .toss_analysis import TossAnalysisSkill
    from .impact_player_debate import ImpactPlayerDebateSkill
    from .team_huddle import TeamHuddleSkill
    from .bowling_change import BowlingChangeSkill
    from .field_placement import FieldPlacementSkill
    from .pressure_response import PressureResponseSkill
    from .matchup_analysis import MatchupAnalysisSkill
    from .collapse_detection import CollapseDetectionSkill
    from .super_over import SuperOverSkill
    from .phase_strategy import PhaseStrategySkill

    router = SkillRouter(mode=mode)
    router.register_all([
        BattingDecisionSkill(),
        BowlingStrategySkill(),
        TossAnalysisSkill(),
        ImpactPlayerDebateSkill(),
        TeamHuddleSkill(),
        BowlingChangeSkill(),
        FieldPlacementSkill(),
        PressureResponseSkill(),
        MatchupAnalysisSkill(),
        CollapseDetectionSkill(),
        SuperOverSkill(),
        PhaseStrategySkill(),
    ])

    logger.info("SkillRouter created (mode=%s) with %d skills", mode, len(router.get_registered_skills()))
    return router
