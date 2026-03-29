"""
ContextRenderer — Converts hidden factors + match state into natural language.

Instead of passing dew_factor=0.73 to an LLM, we render:
"Ball is wet and slippery. Spinners getting almost no grip off the surface."

The LLM persona then weighs this naturally, the way a real cricketer would.

Renders 8 narrative sections:
  match situation, conditions (pitch/weather/dew), crowd, stadium/boundaries,
  bowler/batsman threat, personal state (incl. age/experience, dot-ball drift,
  partnership chemistry), and team communication.
"""

from __future__ import annotations

from typing import Any


class ContextRenderer:
    """Renders match situation as natural language for LLM persona prompts."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_batting_context(
        self,
        ball_context: dict[str, Any],
        pitch_condition: dict[str, Any],
        weather_condition: dict[str, Any],
        crowd_state: dict[str, Any],
        stadium_info: dict[str, Any],
        comm_messages: list[dict[str, Any]] | None = None,
        recent_memory: list[dict[str, Any]] | None = None,
        bowler_profile: dict[str, Any] | None = None,
        batsman_profile: dict[str, Any] | None = None,
    ) -> str:
        """
        Build a full situation narrative for a batsman's LLM persona.

        Returns a multi-paragraph natural language briefing covering:
        match situation, conditions, bowler threat, personal state, and team talk.
        """
        sections = [
            self._render_match_situation(ball_context),
            self._render_conditions(pitch_condition, weather_condition, ball_context),
            self._render_crowd(crowd_state, ball_context),
            self._render_stadium(stadium_info),
            self._render_bowler_threat(bowler_profile, ball_context),
            self._render_personal_state(ball_context, recent_memory, batsman_profile),
            self._render_team_communication(comm_messages),
        ]
        return "\n\n".join(s for s in sections if s)

    def render_bowling_context(
        self,
        ball_context: dict[str, Any],
        pitch_condition: dict[str, Any],
        weather_condition: dict[str, Any],
        crowd_state: dict[str, Any],
        stadium_info: dict[str, Any],
        comm_messages: list[dict[str, Any]] | None = None,
        recent_memory: list[dict[str, Any]] | None = None,
        batsman_profile: dict[str, Any] | None = None,
    ) -> str:
        """Build a full situation narrative for a bowler's LLM persona."""
        sections = [
            self._render_match_situation(ball_context),
            self._render_conditions(pitch_condition, weather_condition, ball_context),
            self._render_crowd(crowd_state, ball_context),
            self._render_stadium(stadium_info),
            self._render_batsman_threat(batsman_profile, ball_context),
            self._render_bowling_state(ball_context, recent_memory),
            self._render_team_communication(comm_messages),
        ]
        return "\n\n".join(s for s in sections if s)

    # ------------------------------------------------------------------
    # Match situation
    # ------------------------------------------------------------------

    def _render_match_situation(self, ctx: dict[str, Any]) -> str:
        over = ctx.get("over", 0)
        ball = ctx.get("ball", 0)
        score = ctx.get("batting_team_score", 0)
        wickets = ctx.get("wickets_fallen", 0)
        target = ctx.get("target")

        over_display = f"{over}.{ball}"
        score_display = f"{score}/{wickets}"

        parts = [f"MATCH SITUATION: {score_display} after {over_display} overs."]

        if target:
            remaining = target - score
            balls_left = (20 - over) * 6 - ball
            if balls_left > 0:
                rrr = (remaining * 6) / balls_left
                parts.append(f"Chasing {target}. Need {remaining} from {balls_left} balls (RRR: {rrr:.1f}).")
                
                # Chase Narrative Thresholds Integration
                if target < 160:
                    parts.append("Target psychology: <160 Safe chase. Look to build partnerships without undue risk.")
                elif target <= 180:
                    parts.append("Target psychology: 160-180 Controlled aggression needed. Keep the run rate in check.")
                elif target <= 200:
                    parts.append("Target psychology: 180-200 Pressure zone. Boundary hitting is essential in the middle overs.")
                else:
                    parts.append("Target psychology: >200 chase. Forced attack early, leverage the powerplay completely or risk falling behind.")

                if rrr > 12:
                    parts.append("Required rate is very steep — extreme big hitting needed.")
        else:
            crr = ctx.get("current_run_rate", 0)
            if crr:
                parts.append(f"Batting first. Current run rate: {crr:.1f}.")
                if over >= 15 and crr < 8:
                    parts.append("Need to push hard in the death overs to post a competitive total.")
                elif over >= 15 and crr > 10:
                    parts.append("Scoring well. Keep the momentum going in the death overs.")

        pressure = ctx.get("pressure_index", 0)
        if pressure >= 0.85:
            parts.append("EXTREME PRESSURE. This is a high-stakes moment.")
        elif pressure >= 0.7:
            parts.append("Pressure is building. Need to stay composed.")
        elif pressure >= 0.5:
            parts.append("Moderate pressure. Steady approach needed.")
        elif pressure < 0.3:
            parts.append("Low pressure. Freedom to play natural game.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Conditions (pitch, weather, dew)
    # ------------------------------------------------------------------

    def _render_conditions(
        self,
        pitch: dict[str, Any],
        weather: dict[str, Any],
        ctx: dict[str, Any],
    ) -> str:
        parts = ["CONDITIONS:"]

        # Pitch
        batting_ease = pitch.get("batting_ease", 0.5)
        spin_eff = pitch.get("spin_effectiveness", 0.5)
        pace_eff = pitch.get("pace_effectiveness", 0.5)
        pitch_type = pitch.get("pitch_type", "balanced")

        if batting_ease > 0.7:
            parts.append("True batting surface — ball coming on nicely to the bat.")
        elif batting_ease < 0.4:
            parts.append("Tricky wicket — uneven bounce and movement off the surface.")
        else:
            parts.append("Decent batting surface with something in it for both sides.")

        if spin_eff > 0.65:
            parts.append("Pitch offering turn and grip for spinners.")
        if pace_eff > 0.65:
            parts.append("Good carry and pace off the surface for seamers.")

        if pitch.get("turn_available"):
            parts.append("Visible turn available off the deck.")
        if pitch.get("swing_available"):
            parts.append("Conditions offering swing.")

        # Dew
        dew_factor = ctx.get("dew_factor", 1.0)
        if dew_factor < 0.75:
            parts.append(
                "Heavy dew on the ground. Ball is wet and slippery. "
                "Spinners getting almost no grip — the ball is skidding through."
            )
        elif dew_factor < 0.85:
            parts.append(
                "Dew setting in. Ball getting slightly wet. "
                "Spin is becoming less effective."
            )
        elif dew_factor < 0.95:
            parts.append("Light dew. Outfield is slick — boundaries running fast.")

        # Weather
        temp = weather.get("temperature_c")
        humidity = weather.get("humidity_pct")
        wind = weather.get("wind_speed_kmh")

        weather_parts = []
        if temp:
            weather_parts.append(f"{temp}°C")
        if humidity and humidity > 70:
            weather_parts.append(f"humid ({humidity}%)")
        if wind and wind > 20:
            weather_parts.append(f"windy ({wind} km/h)")

        if weather_parts:
            parts.append(f"Weather: {', '.join(weather_parts)}.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Crowd
    # ------------------------------------------------------------------

    def _render_crowd(self, crowd: dict[str, Any], ctx: dict[str, Any]) -> str:
        energy = crowd.get("energy", 0.5)
        is_home = ctx.get("is_batsman_home", False)
        is_derby = crowd.get("is_derby", False)

        if energy > 0.8:
            crowd_desc = "The crowd is absolutely electric — deafening noise."
            if is_derby:
                crowd_desc += " Derby match atmosphere — passionate and hostile."
        elif energy > 0.6:
            crowd_desc = "Lively crowd, plenty of noise and energy in the stands."
        elif energy > 0.4:
            crowd_desc = "Decent crowd atmosphere."
        else:
            crowd_desc = "Subdued crowd. Quiet in the stands."

        if is_home:
            crowd_desc += " Home crowd backing you — every run cheered."
        else:
            crowd_desc += " Hostile away crowd — every dot ball celebrated against you."

        return f"CROWD: {crowd_desc}"

    # ------------------------------------------------------------------
    # Stadium / boundaries
    # ------------------------------------------------------------------

    def _render_stadium(self, stadium: dict[str, Any]) -> str:
        dims = stadium.get("dimensions", {})
        if not dims:
            return ""

        straight = dims.get("straight_boundary_m", 70)
        square = dims.get("square_boundary_m", 65)

        parts = ["GROUND:"]
        parts.append(f"Straight boundary: {straight}m. Square boundary: {square}m.")

        if straight > 72:
            parts.append("Long straight boundary — harder to clear over the top.")
        elif straight < 65:
            parts.append("Short straight boundary — lofted drives rewarded.")

        if square < 62:
            parts.append("Short square boundaries — pulls and cuts can find the fence easily.")
        elif square > 70:
            parts.append("Big square boundaries — need timing to beat the field.")

        asymmetry = stadium.get("boundary_asymmetry_factor")
        if asymmetry and asymmetry > 1.1:
            parts.append("Significant boundary asymmetry — one side much shorter than the other.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Bowler threat (for batting context)
    # ------------------------------------------------------------------

    def _render_bowler_threat(
        self, bowler: dict[str, Any] | None, ctx: dict[str, Any]
    ) -> str:
        if not bowler:
            return ""

        name = bowler.get("name", "The bowler")
        style = bowler.get("bowling_style", "")
        economy = ctx.get("bowler_economy", 0)
        avg = ctx.get("bowler_bowling_avg", 0)

        parts = [f"BOWLING THREAT: {name}"]

        if "pace" in style.lower():
            parts.append("is a seam/pace bowler.")
        elif "spin" in style.lower() or "break" in style.lower() or "chinaman" in style.lower():
            parts.append("is a spin bowler.")
        else:
            parts.append(f"bowls {style}.")

        if economy and economy < 7:
            parts.append(f"Very economical today (eco: {economy:.1f}).")
        elif economy and economy > 10:
            parts.append(f"Has been expensive (eco: {economy:.1f}). Opportunities to score.")

        fatigue = ctx.get("bowler_fatigue", 0)
        if fatigue > 0.6:
            parts.append("Looks tired — may lose some pace or accuracy.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Batsman threat (for bowling context)
    # ------------------------------------------------------------------

    def _render_batsman_threat(
        self, batsman: dict[str, Any] | None, ctx: dict[str, Any]
    ) -> str:
        if not batsman:
            return ""

        name = batsman.get("name", "The batsman")
        style = batsman.get("batting_style", "")
        sr = batsman.get("career_stats", {}).get("strike_rate", 0)

        parts = [f"BATSMAN: {name}"]

        if "left" in style.lower():
            parts.append("(left-handed)")
        else:
            parts.append("(right-handed)")

        balls_faced = ctx.get("balls_faced_this_innings", 0)
        if balls_faced < 5:
            parts.append("— just arrived at the crease, still settling in.")
        elif balls_faced > 30:
            parts.append(f"— well set, has faced {balls_faced} balls.")
        else:
            parts.append(f"— has faced {balls_faced} balls.")

        if sr and sr > 150:
            parts.append("Aggressive striker — can take the game away quickly.")
        elif sr and sr < 120:
            parts.append("Steady accumulator — rotate strike well.")

        partnership = ctx.get("partnership_runs", 0)
        if partnership > 50:
            parts.append(f"In a partnership of {partnership} runs — well set.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Personal state (batting)
    # ------------------------------------------------------------------

    def _render_personal_state(
        self,
        ctx: dict[str, Any],
        memory: list[dict[str, Any]] | None,
        batsman_profile: dict[str, Any] | None = None,
    ) -> str:
        parts = ["YOUR STATE:"]

        balls_faced = ctx.get("balls_faced_this_innings", 0)
        fatigue = ctx.get("batsman_fatigue", 0)
        partnership = ctx.get("partnership_runs", 0)

        if balls_faced == 0:
            parts.append("Fresh to the crease. First ball to face.")
        elif balls_faced < 10:
            parts.append(f"Still settling in — {balls_faced} balls faced.")
        elif balls_faced < 30:
            parts.append(f"Getting your eye in — {balls_faced} balls faced.")
        else:
            parts.append(f"Well set — {balls_faced} balls faced.")

        if partnership > 0:
            parts.append(f"Partnership: {partnership} runs.")
            if partnership >= 50:
                parts.append("Partnership Chemistry is flowing well. Strike rotation should be easier.")

        if fatigue > 0.6:
            parts.append("Feeling tired. Legs getting heavy.")
        elif fatigue > 0.3:
            parts.append("Slight fatigue setting in.")

        # Render recent ball history from memory
        if memory:
            recent = memory[-6:]  # last 6 balls
            recent_outcomes = []
            for m in recent:
                outcome = m.get("outcome", "")
                runs = m.get("runs", 0)
                if m.get("is_wicket"):
                    recent_outcomes.append("W")
                elif runs == 0:
                    recent_outcomes.append(".")
                elif runs == 4:
                    recent_outcomes.append("4")
                elif runs == 6:
                    recent_outcomes.append("6")
                else:
                    recent_outcomes.append(str(runs))
            if recent_outcomes:
                parts.append(f"Last {len(recent_outcomes)} balls: {' '.join(recent_outcomes)}")

        # Experience & age narrative
        if batsman_profile:
            exp_years = batsman_profile.get("experience_years", 5)
            player_age = batsman_profile.get("age", 28)
            if exp_years >= 12:
                parts.append(f"Veteran of {exp_years} IPL seasons. You've been here before — trust your process, stay composed.")
            elif exp_years >= 8:
                parts.append(f"Experienced campaigner ({exp_years} seasons). You know how to handle these situations.")
            elif exp_years <= 2:
                parts.append(f"Only {exp_years} season(s) in the IPL. Big stage nerves are natural — back yourself.")
            if player_age >= 37:
                parts.append(f"At {player_age}, you know your body. Pick your moments wisely — don't over-exert.")
            elif player_age <= 21:
                parts.append(f"Young and fearless at {player_age}. Play your natural game.")

        # Batter Intent State Drift & Early Dot-Ball Frustration Integration
        consecutive_dots = ctx.get("consecutive_dot_balls", 0)
        batsman_sr = batsman_profile.get("career_stats", {}).get("strike_rate", 120) if batsman_profile else 120
        
        if consecutive_dots >= 4:
            if batsman_sr > 140:
                parts.append(f"ALERT: {consecutive_dots} dot balls in a row. As an aggressive striker, you are feeling significant early dot-ball frustration and entering 'panic_attack' intent drift. You feel an overwhelming urge to hit out.")
            else:
                parts.append(f"ALERT: {consecutive_dots} dot balls in a row. Pressure mounting. Entering 'pressure_release' intent. Need to break the shackles.")
        elif consecutive_dots >= 3:
            parts.append(f"{consecutive_dots} dots in a row. Approaching 'pressure_release' state. Look to rotate strike actively.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Bowling personal state
    # ------------------------------------------------------------------

    def _render_bowling_state(
        self,
        ctx: dict[str, Any],
        memory: list[dict[str, Any]] | None,
    ) -> str:
        parts = ["YOUR BOWLING STATE:"]

        overs_bowled = ctx.get("bowler_overs_bowled", 0)
        fatigue = ctx.get("bowler_fatigue", 0)

        parts.append(f"Overs bowled: {overs_bowled:.1f}/4.")

        if fatigue > 0.6:
            parts.append("Feeling the workload. Need to be smart with energy.")
        elif fatigue > 0.3:
            parts.append("Slight fatigue but still in good rhythm.")
        else:
            parts.append("Fresh legs. Plenty of energy.")

        if memory:
            recent = memory[-6:]
            recent_outcomes = []
            for m in recent:
                runs = m.get("runs_conceded", 0)
                if m.get("is_wicket"):
                    recent_outcomes.append("W")
                elif runs == 0:
                    recent_outcomes.append(".")
                elif runs == 4:
                    recent_outcomes.append("4")
                elif runs == 6:
                    recent_outcomes.append("6")
                else:
                    recent_outcomes.append(str(runs))
            if recent_outcomes:
                parts.append(f"Last {len(recent_outcomes)} balls: {' '.join(recent_outcomes)}")

        consecutive_dots = ctx.get("consecutive_dot_balls", 0)
        if consecutive_dots >= 3:
            parts.append(f"Building pressure — {consecutive_dots} dots in a row. Keep squeezing.")

        balls_since_boundary = ctx.get("balls_since_boundary", 0)
        if balls_since_boundary > 12:
            parts.append(f"No boundary for {balls_since_boundary} balls. Batsmen are struggling.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Team communication
    # ------------------------------------------------------------------

    def _render_team_communication(
        self, messages: list[dict[str, Any]] | None
    ) -> str:
        if not messages:
            return ""

        parts = ["TEAM COMMUNICATION:"]
        for msg in messages[-5:]:  # last 5 messages
            sender = msg.get("sender_name", "Teammate")
            role = msg.get("sender_role", "")
            content = msg.get("content", "")
            if content:
                parts.append(f'  {sender} ({role}): "{content}"')

        return "\n".join(parts) if len(parts) > 1 else ""
