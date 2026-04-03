# CATBOOST_PLAN.md — IPL Oracle ML Layer
### Offline task plan for Claude Code CLI

> **STATUS: FULLY IMPLEMENTED (Week 2.7)**
> All components below have been built and integrated. Minor deviations from this plan:
> - `learning_rate` tuned to `0.01` (plan said `0.05`) for better generalization
> - `early_stopping_rounds` set to `100` (plan said `50`) with `l2_leaf_reg=5` added
> - `blend.py` lives at `backend/app/simulation/blend.py` (not root `simulation/`)
> - See `backend/app/ml/` for implementation and `scripts/train_catboost.py` for CLI

This plan is self-contained. Read it fully before writing any code.
All context needed to build the CatBoost layer is here.

---

## WHAT THIS TASK IS

Add a CatBoost win-probability model as a 30% weighted signal into all three
simulation modes of IPL Oracle. The model trains on ball-by-ball IPL data
(2020–2025 seasons only) and produces a calibrated P(batting team wins) at
any point in a match. That probability is blended with the simulation result
at the weights below.

**Blending formula per mode:**
```
probabilistic mode  →  0.70 × prob_sim_result   + 0.30 × catboost_win_prob
hybrid mode         →  0.70 × hybrid_sim_result  + 0.30 × catboost_win_prob
persona mode        →  0.70 × persona_sim_result + 0.30 × catboost_win_prob
```

CatBoost is always 30%. The simulation engine drives 70%. CatBoost acts as
the historical prior grounding predictions in 6 seasons of real outcomes.

---

## FILES TO CREATE

```
backend/app/ml/
├── __init__.py
├── catboost_trainer.py       ← training pipeline (run once offline)
├── catboost_predictor.py     ← inference wrapper (called during simulation)
├── feature_builder.py        ← MatchState → feature vector
└── models/                   ← git-ignored, populated after training
    ├── win_prob.cbm           ← trained model artifact
    └── win_prob_meta.json     ← feature names, cat_features, eval metrics

scripts/
└── train_catboost.py         ← CLI entrypoint: python scripts/train_catboost.py

simulation/
└── blend.py                  ← 70/30 blending function used by all three modes
```

---

## INPUT DATA

### Format
Ball-by-ball CSV. One row per delivery including extras.
Covers IPL seasons from 2008 onwards historically.

### Filter Rule — STRICT
Only use rows where `season` is in: `2020/21, 2021, 2022, 2023, 2024, 2025`.
Drop everything before 2020. The game has changed too much — flat pitches,
Impact Player rule from 2023, different team dynamics. Older data biases
the model toward a style of cricket that no longer exists.

### Key columns from the dataset
```
match_id, season
innings, batting_team, bowling_team
over, ball, ball_no
batter, bat_pos, bowler
team_runs, team_balls, team_wicket
runs_target                ← innings 2 only, NaN for innings 1
toss_winner, toss_decision
venue, city, month, year
match_won_by               ← TARGET SOURCE (match-level, repeated every row)
valid_ball                 ← 0 for wides/no-balls
result_type                ← exclude 'no result' matches (rain etc.)
```

---

## FEATURE ENGINEERING

Build all features in `feature_builder.py`. Use this file identically in
training AND inference — it is the single source of truth. Never derive
features in two places.

### Numeric features to derive
```
balls_remaining     = (120 - ball_no).clip(min=0)
wickets_in_hand     = 10 - team_wicket
current_run_rate    = team_runs / max(team_balls, 1) * 6
required_run_rate   = (runs_target - team_runs) / max(balls_remaining, 1) * 6
                      set to 0 for innings 1 (no target)
run_rate_diff       = current_run_rate - required_run_rate
pressure_index      = required_run_rate / max(current_run_rate, 0.1)
                      set to 1.0 for innings 1
phase               = 1 if over <= 5 else (3 if over >= 16 else 2)
                      1=powerplay  2=middle  3=death
is_innings_2        = 1 if innings == 2 else 0
balls_into_innings  = ball_no (raw position in innings)
runs_target         = fill NaN with 0 for innings 1
```

Pass these through as numeric (float):
```
over, ball_no, innings,
team_runs, team_balls, team_wicket,
balls_remaining, wickets_in_hand,
current_run_rate, required_run_rate,
run_rate_diff, pressure_index,
phase, is_innings_2, balls_into_innings, runs_target
```

### Categorical features (pass raw strings to CatBoost — no encoding)
```
batting_team, bowling_team
venue
toss_winner, toss_decision
month                       ← as string: '3', '4', '5'
batter, bowler              ← high cardinality, CatBoost handles fine
```

### Target variable
```
label = 1  if match_won_by == batting_team
label = 0  otherwise

Assign this label to EVERY row of a match. It is a match-level label
repeated per ball — this is correct and intentional.
```

### What NOT to include
```
runs_batter, runs_extras, runs_total  ← ball outcome, leaky at inference time
wicket_kind, player_out               ← ball outcome, leaky
match_id, date                        ← identifiers
match_won_by                          ← is the label source, not a feature
```

---

## TRAINING PIPELINE (`catboost_trainer.py`)

### Step 1 — Load and filter
```
Load the CSV
Filter: season in [2020/21, 2021, 2022, 2023, 2024, 2025]
Drop rows where result_type == 'no result'  ← rain-affected no-result matches
```

### Step 2 — Build features
```
Call feature_builder.build(df)
Returns: feature DataFrame + label Series
```

### Step 3 — Train / val / test split by season (NOT random)
```
Train : 2020/21, 2021, 2022, 2023
Val   : 2024
Test  : 2025

Never use random split. Match data has temporal dependency.
Splitting by season prevents data leakage from future matches.
```

### Step 4 — Train CatBoostClassifier
```
cat_features = [
    'batting_team', 'bowling_team', 'venue',
    'toss_winner', 'toss_decision', 'month',
    'batter', 'bowler'
]

CatBoostClassifier(
    iterations=1000,
    learning_rate=0.05,
    depth=6,
    loss_function='Logloss',
    eval_metric='AUC',
    random_seed=42,
    early_stopping_rounds=50,
    verbose=100,
    cat_features=cat_features,
)

Fit with eval_set=(X_val, y_val), use_best_model=True
```

### Step 5 — Evaluate on test set (2025 season)
Compute and print:
- AUC                   → target > 0.72
- Brier score           → target < 0.20
- Calibration: bin predictions into 10 buckets, print mean predicted vs
  actual win rate per bucket
- Accuracy at over 10, innings 2 only (mid-match accuracy sanity check)

### Step 6 — Save artifacts
```
model.save_model('backend/app/ml/models/win_prob.cbm')

win_prob_meta.json:
{
  "cat_features": [...],
  "numeric_features": [...],
  "seasons_trained": ["2020/21","2021","2022","2023"],
  "seasons_val": ["2024"],
  "seasons_test": ["2025"],
  "test_auc": float,
  "test_brier": float
}

Commit win_prob_meta.json.
Do NOT commit win_prob.cbm (add to .gitignore).
```

---

## INFERENCE WRAPPER (`catboost_predictor.py`)

### Class contract
```
class CatBoostPredictor:
    Load model once at simulation startup. Not per-ball, not per-sim.

    predict(match_state: MatchState) -> float
        Converts live MatchState to feature dict via feature_builder.build_single()
        Returns P(batting team wins) as float in [0.0, 1.0]
        Must complete in < 10ms. No I/O. No LLM. Pure inference.

    is_available() -> bool
        Returns False if model file not found.
        Simulation falls back to 100% sim result and logs a warning.
```

### When to call per simulation mode
```
probabilistic mode : call every ball    ← cheap, no LLM overhead anyway
hybrid mode        : call every ball    ← lightweight alongside prob base
persona mode       : call every over    ← LLM is the expensive part, keep cb light
```

---

## FEATURE BUILDER — INFERENCE SIDE (`feature_builder.py`)

The `build_single(match_state)` method maps the live `MatchState` object
(which already exists in the simulation engine) to the exact feature dict
the model expects. Attribute names must match what MatchState exposes.

Required MatchState attributes:
```
current_over, ball_no, innings
team_runs, team_balls, team_wicket
runs_target (None for innings 1)
batting_team, bowling_team
venue
toss_winner, toss_decision (None if not yet known)
match_month (integer: 3, 4, or 5)
current_batter, current_bowler (None if not yet set)
```

Fill any None values with the string 'Unknown' for categoricals.
Fill None runs_target with 0.

---

## BLENDING FUNCTION (`simulation/blend.py`)

```
def blend_with_catboost(sim_win_prob, cb_win_prob, mode) -> float:

    CB_WEIGHT  = 0.30
    SIM_WEIGHT = 0.70

    return (SIM_WEIGHT * sim_win_prob) + (CB_WEIGHT * cb_win_prob)

    mode parameter is accepted for logging/debugging but does not change
    the weights — all three modes use the same 70/30 split.
```

Called once per simulation run (not per ball) using the final sim win
probability and the CatBoost prediction at the last ball of the match.

Optional mid-simulation use: CatBoost win probability at over 10 can feed
into the pressure index as a calibration signal. If CB says P(win) < 0.15
but the simulation is trending to a batting-team win, increase pressure on
batting agents. This is optional — implement in a later iteration.

---

## CLI ENTRYPOINT (`scripts/train_catboost.py`)

```
Usage:
  python scripts/train_catboost.py --data path/to/ball_by_ball.csv

Arguments:
  --data        path to input CSV (required)
  --output      model output directory (default: backend/app/ml/models/)
  --iterations  CatBoost iterations (default: 1000)
  --verbose     log interval (default: 100)

What it does:
  1. Loads CSV, applies season filter
  2. Builds features
  3. Splits by season
  4. Trains model
  5. Evaluates and prints metrics
  6. Saves .cbm and _meta.json
  7. Prints summary line: "Model saved. Test AUC: X.XX Brier: X.XX"
```

---

## DEPENDENCIES

Add to `backend/pyproject.toml`:
```
catboost >= 1.2
pandas >= 2.0
scikit-learn >= 1.3    # calibration + Brier score utilities only
```

catboost ships its own inference engine. No extra install for prediction.

---

## GIT IGNORE

Add to `.gitignore`:
```
backend/app/ml/models/*.cbm
backend/app/ml/models/*.cbm.meta
```

The `.cbm` file can be 50–200MB. Share via S3, Google Drive, or repo
release artifact. The `win_prob_meta.json` IS committed — it documents
training provenance.

---

## DATA NOTES FOR THE OFFLINE TOOL

- `valid_ball == 0` means the delivery is a wide or no-ball. Keep these
  rows for match-state continuity. Be aware `ball_no` does not increment
  on invalid balls — this is correct behaviour in the raw data.

- `runs_target` is a match-level column only populated in innings 2.
  Fill with 0 for all innings 1 rows. Do not drop innings 1 rows.

- `match_won_by` is repeated identically on every ball of a match.
  It is a match-level label. This is correct — assign it to all rows.

- `result_type == 'no result'` means rain or other abandonment.
  Drop these matches entirely (all their rows) before training.

- Season column formats vary across years: '2020/21', '2021', '2022' etc.
  Normalise with a string membership check against the allowed list.
  Do not parse as a numeric year.

- `batter` and `bowler` will contain player names not seen during training
  (new IPL 2026 players). CatBoost handles unseen categorical values
  natively. No special handling or fallback needed.

- Some rows have empty `wicket_kind`, `player_out`, `fielders` columns
  when no wicket fell. These are correctly empty — do not treat as errors.

---

## SUCCESS CRITERIA

| Metric | Minimum to enable blend | Target |
|--------|------------------------|--------|
| Test AUC (2025 season) | 0.70 | 0.75 |
| Brier score | < 0.22 | < 0.18 |
| Mean calibration error | < 0.05 | < 0.03 |
| Inference latency | < 10ms | < 5ms |

If AUC < 0.70 on the held-out 2025 test set, do NOT enable the 30% blend.
Run simulation at 100% weight and log a startup warning:
"CatBoost model below accuracy threshold. Running simulation-only mode."
