# IPL Oracle Decision Making Modes & Architecture Flow

The IPL Oracle simulation engine employs a hybrid decision-making architecture that balances speed, statistical accuracy, and contextual reasoning. Agents operate across a layered system depending on their role and the match situation.

As the simulation evolves (incorporating the advanced LLM Persona Multi-Agent framework), the interplay between these factors becomes a dynamic mix of deterministic environments, intended LLM tactics, and probabilistic outcomes.

## 1. Deterministic Mode (The Environment)

**How it works:**
Deterministic decisions are strictly rule-based and algorithmic. Given a specific set of inputs, the output will always be identically calculated.

**Flow Integration:**
- **Primary Users:** Environmental agents such as `PitchAgent`, `StadiumAgent`, and `WeatherAgent`.
- **Implementation:** Conditions like pitch wear and tear, dew formation, and boundary sizes are calculated entirely deterministically based on over number, innings, and pitch type.
- **Influence on other modes:** These agents set the baseline constraints. Rather than acting randomly, they modify the environment (e.g., `PitchAgent` specifies spin effectiveness at Over 15, `StadiumAgent` defines square leg asymmetry). Both the internal Math models and the LLM prompts directly consume these factors (e.g., instead of a generic stat, the LLM is told "The ball is wet and slippery due to dew. Spinners are getting no grip.").

## 2. Active Simulation Tiers: PROBABILISTIC, HYBRID, and PERSONA

With the advanced architecture rollout, active participants (`PlayerAgents`, `CoachAgents`) operate in one of three tiers. The simulation can seamlessly auto-downgrade between tiers depending on the volume of matches being simulated (balancing high realism against computing costs).

### Tier A: PROBABILISTIC MODE (The Base Engine)
**How it works:**
This is the default engine for high-speed, bulk ball-by-ball resolution. It uses seeded random number generation paired with specific player/event probabilities.

**Flow Integration:**
- **Execution:** When a bowler bowls to a batsman, their historical base probabilities are fetched. These are adjusted by the underlying **Deterministic** environment modifiers.
- **Resolution:** A random float is generated to resolve the outcome against the adjusted probability.
- **Usage:** This mode is highly efficient, used primarily when simulating large batch volumes (e.g., 100-500 Monte Carlo runs) where invoking LLMs repeatedly would be too slow and expensive.
- **CatBoost Blend:** After all sims complete, the aggregated simulation win probability is blended with the CatBoost historical prior at a fixed 70/30 split: `final_win_pct = 0.70 × sim_win_pct + 0.30 × catboost_prob`.

### Tier B: HYBRID MODE (High-Pressure Transitions)
**How it works:**
The simulation operates largely in Probabilistic Mode but automatically invokes LLM reasoning frameworks during high-leverage "make-or-break" moments.

**Flow Integration:**
- **Trigger:** The Match Engine dynamically calculates a `pressure_index` (factoring in wickets fallen, consecutive dot balls, match phase). LLM fires via **two trigger paths**:

  **Path 1 — Pressure threshold:** `pressure_index >= LLM_PRESSURE_THRESHOLD` (default `0.65`).

  **Path 2 — Explicit high-leverage triggers** (fire regardless of pressure score):
  - **Death overs (18+):** Always LLM — both innings. These overs decide matches.
  - **Wicket cluster:** 3+ wickets fallen AND over >= 10. Collapse territory.
  - **Close chase:** Innings 2, last 5 overs, <= 40 runs needed. Maximum tension.
  - **Post-wicket ball:** First ball to a new batsman after a wicket falls in the same over.
  - **Impact Player decision:** Always an LLM call (high-leverage by definition).

  This targets LLM at ~15-20% of balls while preserving quality at decision points that actually matter.

- **Execution:** The agent packages the Match State, Pitch Condition, and Stats into JSON and asks the LLM for a singular tactical decision (e.g., invoking an Impact Player, shifting the field, passing strategic messages).
- **CatBoost Blend:** After all sims complete, the aggregated simulation win probability is blended with the CatBoost historical prior at a fixed 70/30 split: `final_win_pct = 0.70 × sim_win_pct + 0.30 × catboost_prob`.

### Tier C: PERSONA MODE (Full Multi-Agent Ecosystem)
**How it works:**
At the highest tier (used for 1-10 simulations), every player and coach is backed by a custom LLM persona (e.g., "Virat Kohli: aggressive accumulator"). The agents actively impersonate the cricketers, communicating via a `CommBus` and making tactical choices every single ball.

**The Golden Rule — LLM Decides Intent, Probability Decides Outcome:**
To prevent the LLM from simply generating unrealistic narratives or "cheating" around the player stats, the flow is strictly controlled:
1. **Narrative Injection:** Deterministic environment data is passed to a `ContextRenderer` that describes the pitch/match in natural language for the LLM.
2. **Intent Planning:** The LLM Striker decides on their `intent` (e.g., "attacking off-side", "slog sweep") via structured JSON. The LLM Bowler decides on their delivery tactic (e.g., "yorker", "bouncer"). 
3. **Outcome Resolution Framework:** Their intents are fed into an `OutcomeResolver`. For example, if the batsman chose a "slog" to a "yorker", the Outcome Resolver creates a Matchup Matrix that spikes the standard wicket probability. 
4. **Final Verdict:** The engine finally defers to the **Probabilistic Mode** to resolve the actual outcome of the ball using the modified probabilities.

This ensures that the digital world feels alive with human-like cricketers planning and reacting, but the ultimate simulation remains grounded in cold, hard statistical realism.

- **CatBoost Blend:** After all sims complete, the aggregated simulation win probability is blended with the CatBoost historical prior at a fixed 70/30 split: `final_win_pct = 0.70 × sim_win_pct + 0.30 × catboost_prob`.

## 3. CatBoost ML Ensemble (Cross-Cutting Historical Prior)

**How it works:**
A CatBoost win-probability model trained on 6 seasons of ball-by-ball IPL data (2020-2025) provides a calibrated historical prior that grounds simulation predictions in real outcomes. This layer applies identically across all three simulation tiers.

**Flow Integration:**
- **Training:** Offline pipeline (`scripts/train_catboost.py`) trains on 16 numeric + 8 categorical features with season-based split (train=2020-2023, val=2024, test=2025). No temporal data leakage.
- **Inference:** Singleton `CatBoostPredictor` loads the `.cbm` model once at startup. Prediction completes in <10ms — no I/O, no LLM, pure inference.
- **Blending:** Applied once after all N simulations complete (not per-ball). The formula is identical for all three modes:
  ```
  final_win_pct = 0.70 × simulation_win_pct + 0.30 × catboost_win_prob
  ```
  The simulation engine drives 70% of the final prediction. CatBoost acts as a 30% historical anchor preventing pure-simulation drift.
- **Graceful fallback:** If the `.cbm` model file is missing or test AUC < 0.70, the blend is disabled and simulation runs at 100% weight. A startup warning is logged but no error is raised.
- **Transparency:** The API response includes `catboost_blend` metadata carrying raw simulation and CatBoost probabilities separately, so the blend is fully auditable.
