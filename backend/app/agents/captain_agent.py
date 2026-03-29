"""
CaptainAgent — Tactical leadership agent managing on-field operations.

Handles field placements, bowling changes (partnering with CoachAgent),
and micro-tactics based on match state.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .base_agent import BaseAgent

@dataclass
class FieldState:
    """Represents the on-field fielding positions for a delivery."""
    slips: int = 0
    deep_third_man: bool = False
    deep_fine_leg: bool = False
    deep_point: bool = False
    deep_cover: bool = False
    long_off: bool = False
    long_on: bool = False
    deep_midwicket: bool = False
    deep_square_leg: bool = False
    sweepers: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class CaptainAgent(BaseAgent):
    """
    On-field Captain who dictates field placements dynamically 
    based on the match phase, bowler style, and pressure.
    """
    
    def __init__(
        self,
        name: str,
        team: str,
        defensive_tendency: float = 0.5,
        run_id: str | None = None,
    ) -> None:
        profile = {
            "name": name,
            "team": team,
            "defensive_tendency": defensive_tendency,
        }
        super().__init__(agent_type="captain", profile=profile, run_id=run_id)
        self.defensive_tendency = defensive_tendency
        
    def set_field(
        self, 
        over: int, 
        bowler_style: str, 
        pressure_index: float,
        is_batter_aggressive: bool = False
    ) -> FieldState:
        """
        Dynamically positions fielders based on constraints.
        Powerplay (Overs 0-5): Max 2 fielders outside 30 yards.
        Middle/Death: Max 5 fielders outside 30 yards.
        """
        field = FieldState()
        is_powerplay = over < 6
        is_spin = "spin" in bowler_style.lower() or bowler_style in ["off_break", "leg_break", "left_arm_spin"]
        
        if is_powerplay:
            # 2 deep fielders allowed
            if is_spin:
                field.long_on = True
                field.deep_midwicket = True
                field.slips = 1
            else:
                if pressure_index > 0.6 or self.defensive_tendency > 0.6:
                    field.deep_third_man = True
                    field.deep_fine_leg = True
                else:
                    field.deep_square_leg = True
                    field.long_off = True
                    field.slips = 2 if over < 3 else 1
        else:
            # Up to 5 deep fielders allowed
            if over >= 16:
                # Death overs: Protect boundaries entirely
                field.long_off = True
                field.long_on = True
                field.deep_midwicket = True
                field.deep_square_leg = True
                field.deep_cover = True
                field.deep_point = False
                field.deep_fine_leg = True if "pace" in bowler_style else False
            elif is_spin:
                field.long_off = True
                field.long_on = True
                field.deep_midwicket = True
                field.deep_square_leg = True
                field.deep_cover = True
            else:
                # Middle overs pace
                field.deep_third_man = True
                field.deep_fine_leg = True
                field.deep_square_leg = True
                field.long_off = True
                if is_batter_aggressive:
                    field.deep_midwicket = True
                    field.long_on = True
        
        self.log_decision(
            "field_change",
            field.to_dict(),
            reasoning=f"Setting field for over {over} vs {'spin' if is_spin else 'pace'}",
        )
        return field
