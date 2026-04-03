# Advanced Implementation Metrics Document

This document captures the implementation status, mathematical definitions, and codebase locations for the advanced institutional metrics and hidden psychological factors in the IPL Oracle engine.

## ✅ Implemented Metrics

### 1. The "Nothing to Lose" vs. "Qualification Squeeze" Anomaly
**Status:** Implemented in `backend/app/data/tournament_state.py`.
- **Elimination Freedom:** If a team is mathematically eliminated, the engine applies an `aggression_modifier` of `1.5x`, simulating the fearless spoiler effect. The CoachAgent's conservative decision-making matrix is dynamically inverted.
- **Qualification Choke:** If a team sits on 14+ points with only 1 match left (needing 1 win), it triggers the `in_qualification_squeeze` state. This returns a `pressure_penalty` (1.2x) that multiplies base error rates, subtly increasing edges and mistimed shots under high psychological tension.

### 2. Dynamic Contextual Pressure Index (CPI)
**Status:** Implemented in `backend/app/simulation/match_engine.py` via `compute_pressure_index()`.
- **Dot-Ball Geometrics:** The engine evaluates pressure non-linearly. Specifically, the base pressure spikes algorithmically according to `consecutive_dots / 3.0` up to a geometric cap.
- **Wicket Cushion:** The formula uses an exponential scale `1.0 - (wickets / total_wickets) ** 2` rather than static linear decay. This accurately reflects that dropping a 2nd wicket at a score of 130 applies vastly different baseline structural pressure than dropping a 6th wicket at 130.

### 3. Boundary Asymmetry vs. Bowling Lines
**Status:** Implemented in `backend/app/agents/stadium_agent.py` and `player_agent.py`.
- **Geometric Sizing:** Stadium boundaries are modeled dimensionally (e.g., M. Chinnaswamy with 68m square and 73m straight).
- **Execution:** `StadiumAgent.get_boundary_asymmetry_factor()` calculates dynamic float multipliers (0.8–1.2) based on shot direction and batsman handedness. Batting agents multiply their boundary rates by this figure, while bowlers dynamically adjust their probabilistic lines to force play toward the longer fence.

### 4. Dew-Induced Spin Degradation (RPM Drop)
**Status:** Implemented in `backend/app/agents/weather_agent.py`.
- **Execution:** `WeatherAgent.model_rpm_degradation()` mathematically limits bowler capability under dew. Wrist spinners (who rely heavily on ball grip for Revolutions Per Minute) lose up to 30% of their effectiveness (multiplier degrades to `0.70`). Finger spinners degrade smoothly to `0.85`, while pace variants remain highly resistant (`0.99`), mirroring empirical data.

### 5. Tournament Context and NRR Pressure
**Status:** Implemented in `backend/app/data/tournament_state.py`.
- **Execution:** Before a match or critical phase, `TournamentState.get_nrr_requirement()` passes the exact target difference back to the coach agent. This statically boosts the `aggression_index` across the batting lineup if the team requires a steep Run Rate to qualify for playoffs.

### 6. Over-by-Over Pitch Aging Model
**Status:** Implemented in `PitchAgent.get_condition()`.
- **Execution:** The pitch behavior naturally ages through the innings without LLM prompting. Overs 1-4 provide seam grip (`early_pace_bonus`), overs 5-12 provide a predictable batting surface (highest `batting_ease`), and Overs 13-20 model wear and tear (decreasing bounce consistency and increasing `spin_growth_rate`), heavily tuned by the specific venue's initial `pitch_type`.

### 7. Crowd Momentum Effect
**Status:** Implemented in `CrowdAgent.get_energy()` and `MatchEngine.compute_pressure_index()`.
- **Execution:** Home crowd momentum is dynamically calculated. The energy shifts based on boundary streaks, wickets fallen, and target parity. This output `crowd_energy` directly amplifies the `pressure_index` penalty experienced by the away team, especially during high-leverage death overs.

### 8. Super Over Readiness & Selection Profiles
**Status:** Implemented in `backend/app/skills/super_over.py`.
- **Execution:** Teams differ greatly in super-over readiness. When a tie occurs, the `SuperOverSkill` parses the squad using unique mathematical weights: `strike_rate` + `aggression_index` + `big_match_temperament` + `experience` for batters; and `economy` + `death_overs_specialization` + `pressure_resilience` for bowlers, fully circumventing standard career averages to select the optimal 3-batter, 1-bowler lineup.

### 9. Advanced Player Psychology & State Drift (Persona Framework)
**Status:** Implemented in `backend/app/services/context_renderer.py` and actively fed to the `MatchEngine`.
- **Batter Intent State Drift:** The framework actively evaluates recent dot balls against a player's inherent strike rate. Rather than a flat probability drop, it categorizes them into narrative zones: `pressure_release` versus `panic_attack`.
- **Early Dot-Ball Frustration:** Aggressive batters (SR > 140) face explicit narrative triggers forcing them to "hit out" if they endure 4 consecutive dots.
- **Partnership Chemistry Index:** At 50+ runs, the LLM is instructed that strike rotation chemistry has locked in, allowing natural relief of single-side pressure.
- **Chase Narrative Thresholds:** Targets are bucketed psychologically (`<160` safe chase, `160-180` controlled aggression, `180-200` pressure zone, `>200` forced attack early). The persona uses these bounds to select its overriding intent in exactly the manner requested.

---

### 10. The "Price-Tag" Burden (Auction Hangover)
**Status:** Implemented in `backend/app/agents/player_agent.py`.
- **Execution:** The engine injects an `expectation_tax`. Expensive marquee signings (₹15cr+) receive an artificial error rate on their `confidence_metric` depending on the match index. This tax decays exponentially (`decay = math.exp(-match_index / 7.0)`), seamlessly transitioning players to their true form as the season progresses.

### 11. Runs Above Average Replacement (RAAR) Matrix
**Status:** Implemented in `backend/app/data/matchup_processor.py`.
- **Execution:** To prevent LLMs from hallucinating on raw career averages, the preprocessing engine applies Phase-Specific baseline multipliers (e.g. 1.5x for death overs, 1.2x for powerplay). A 12-ball 28 score natively impacts the player's memory arrays distinctly from a 45-ball 55.

### 12. Impact Player State Dependency
**Status:** Implemented in `backend/app/agents/coach_agent.py`.
- **Execution:** Tactical phase optimization. The `should_use_impact_player` method now natively evaluates mathematical arbitrage: seamlessly replacing a bowler exactly after finishing their 4-over quota in the 1st innings for an extra batter, executing a perfect tactical switch before the innings concludes.

### 13. Left-Arm Matchup Dynamics
**Status:** Implemented in `PlayerAgent.bat()` and injected via `BallContext`.
- **Execution:** Geometric handicap evaluation natively coded. RHB facing left-arm pace (incoming angle) or orthodox spin triggers a `left_arm_vulnerability_index` penalty. This actively manipulates edge rates and dot ball probability without requiring manual LLM narrative prompting, fully handling geometric mismatch calculations.

### 14. Ball Condition Phase (White Ball Lacquer)
**Status:** Implemented in `PlayerAgent.bowl()`.
- **Execution:** White-ball phases are now mathematically mapped. New ball (overs 1-4) strongly boosts pace swing/seam and dots. Mid ball (overs 5-13) yields peak batting boundary stats. Old Ball (14+) shifts power strictly to cutters, grip, and spin specialists, naturally shifting MatchEngine progression.

### 15. Death Overs Reputation Factor
**Status:** Implemented in `PlayerAgent.bat()`.
- **Execution:** Mathematical Pre-ball fear indexing. If the bowler acting past over 16 has a `death_overs_specialization` > 0.7, a non-linear `reputation_fear` penalty forces boundaries down and false-shots (wickets/dots) up, simulating the sheer panic of tracking specialists without any LLM prompt hacking.

### 16. Umpire Decision Variance
**Status:** Implemented in `MatchEngine` and `PlayerAgent.bowl()`.
- **Execution:** Stochastic realism. The MatchEngine initializes an `_umpire_strictness` scalar (`0.85` to `1.15`). The strictness permanently alters the probability array of wides and height no-balls for the entire match, ensuring unpredictable umpire rhythms.

### 17. Core Game & Strategy Architecture (11 New Factors)
**Status:** Multi-variable injection completed directly into `PlayerAgent` and `MatchEngine` probabilistic arrays.
- **Execution:** To achieve immediate high-value scaling without API overhead, the following factors have been mathematically modeled and permanently integrated as `BallContext` variables:
  - **Opening 12-ball intent profile:** Freshly entered batters undergo forced `aggression_index` amplification for their first 12 balls, spiking both boundaries and wickets simultaneously.
  - **Captain defensive tendency:** Default scalar (0.5) that natively shifts singleton probability vs boundaries, mimicking field spreads.
  - **17th over leverage factor:** Directly identifies `over == 16` as a critical momentum point, universally applying pressure to the bowler to restrict boundaries.
  - **Fielding conversion probability (Dropping catches):** If the resolution engine rolls a `caught` dismissal, it makes a secondary probabilistic roll against a team fielding scalar (`0.85`). If failed, the wicket is completely wiped and substituted for 1/2 runs to simulate drops.
  - **Spinner entry timing distortion:** Spinners operating inside the Powerplay (`over < 6`) natively concede higher boundaries but collect a significant wicket boost (mimicking edge vulnerability behind the wicket against hard balls).
  - **Batting collapse contagion:** If `MatchEngine` identifies 2+ wickets falling inside 36 deliveries, the incoming batsman's confidence is instantly drained, increasing dots.
  - **Post-timeout intent shift:** `MatchEngine` tracks the typical TV-timeout periods (e.g. following over 9 and 14). For exactly `legal_balls == 0` on the following over, boundary probabilities skyrocket simulating strict coach instructions.
  - **Lower-order strike independence:** #8-11 batting roles ("bowler") no longer build innings. Dots and Singles drop drastically, Sixes and Wickets maximize.
  - **Anchor penalty:** A passive sweep determines if the non-striker is anchoring tightly (>15 balls @ <115 SR). If so, a heavy pressure penalty falls entirely on the facing batsman forcing them to find the boundary or fall trying.
  - **Over-rate pressure:** If an innings drags to over 18, fielders must enter the circle. This permanently buffs boundary probability for overs 18 & 19.
  - **Emotional rivalry (Franchise Clutch):** Built-in string arrays detect if heavyweights (CSK, MI) are batting vs standard franchises (PBKS, RCB). Big match temperaments mathematically shield against edges depending on the team jersey.

### 18. Captain Field Intelligence & Placement (CaptainAgent)
**Status:** Implemented in `backend/app/agents/captain_agent.py` and `player_agent.py` (Batting logic loop).
- **Execution:** We architected a dedicated `CaptainAgent` that explicitly handles field layouts! It dynamically generates a `FieldState` variable per ball reflecting powerplay restrictions, phase-specific depth, and spin-vs-pace geometric adjustments. 
  - Inside `PlayerAgent.bat()`, boundaries and runs are NO LONGER guaranteed by random number generation. If the `outcome_key` returns a boundary "drive", but the Captain deployed a `long_off` fielder, the simulation algorithm mathematically intercepts the shot—yielding either a Caught-in-the-deep wicket, a cutoff-single, or a complete dot ball!

---

## ⏳ Pending / Upcoming Implementations

### Core Game / Strategy Architecture
- 1. Toss conditional value
- 3. Matchup suppression memory (KuzuDB integration)
- 4. Travel fatigue sequence (circadian biological constraints)
- 6. Death overs specialist availability
- 12. Powerplay wicket timing vs raw count
- 14. Silent injury behavior (physical degradation limits)
- 24. Bench role familiarity / selection insecurity
- 26. Matchup Memory Recency 

### Pitch Micro-Signals
- 26. Fresh grass deception
- 27. Roller effect memory
- 28. Pitch edge hardness (square boundary speeds)
- 29. Footmark emergence timing
- 30. Surface night cooling rate

### Captaincy Hidden Signals
- 31. Slip retention duration
- 32. Third-man movement frequency
- 33. Bowler trust sequencing
- 34. Delayed timeout request

### Player Psychology Indicators
- 36. Recent dismissal repetition
- 37. Milestone hesitation (Nervous Nineties/Fifties)
- 38. Comeback anxiety / Rehabilitation tentativeness
- 39. Opposition-specific pressure (Nemesis logic)
- 14. DRS Survival Momentum

### Live Odds Anomalies (Data Pipeline Required)
- 41. Unexpected short drift
- 42. Boundary underreaction gap
- 43. Wicket overreaction reversal
- 44. Spinner mismatch drift
- 45. Hidden weather adjustment

### Super Over Specific Micro-Logic
- 46. First-ball six probability / opening dominance
- 47. Yorker reliability index under exact 6-ball stress
- 48. Left-right combo necessity 
- 49. Extreme boundary preference under sudden death stress
- 50. Captain super-over batting order panic bias
- 19. Bowler Nerve Compression
- 20. Perfect pair capability 
- 21. Repeat super-over physical fatigue penalty
- 22. Keeper super-over absolute edge
- 23. Psychological Carryover from exactly previous innings
