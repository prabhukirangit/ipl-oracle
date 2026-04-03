"""
CatBoost training pipeline for IPL win-probability model.

Trains on ball-by-ball IPL data (2020-2025 seasons only).
Season-based split: train=2020-2023, val=2024, test=2025.

Usage:
    python -m app.ml.catboost_trainer --data path/to/IPL.csv
    OR via scripts/train_catboost.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import roc_auc_score, brier_score_loss

from .feature_builder import (
    build,
    ALL_FEATURES,
    CAT_FEATURES,
    NUMERIC_FEATURES,
    ALLOWED_SEASONS,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = Path(__file__).parent / "models"

TRAIN_SEASONS = {"2020/21", "2021", "2022", "2023"}
VAL_SEASONS = {"2024"}
TEST_SEASONS = {"2025"}


def load_and_filter(csv_path: str | Path) -> pd.DataFrame:
    """Load CSV and filter to allowed seasons, drop no-result matches."""
    df = pd.read_csv(csv_path, low_memory=False)
    logger.info("Loaded %d rows from %s", len(df), csv_path)

    # Normalise season column to string
    df["season"] = df["season"].astype(str).str.strip()

    # Filter seasons
    df = df[df["season"].isin(ALLOWED_SEASONS)].copy()
    logger.info("After season filter (2020-2025): %d rows", len(df))

    # Drop no-result matches
    if "result_type" in df.columns:
        no_result_matches = df.loc[
            df["result_type"].astype(str).str.lower() == "no result", "match_id"
        ].unique()
        df = df[~df["match_id"].isin(no_result_matches)].copy()
        logger.info("After dropping no-result matches: %d rows", len(df))

    return df


def split_by_season(
    df: pd.DataFrame, X: pd.DataFrame, y: pd.Series
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Split into train/val/test by season."""
    train_mask = df["season"].isin(TRAIN_SEASONS)
    val_mask = df["season"].isin(VAL_SEASONS)
    test_mask = df["season"].isin(TEST_SEASONS)

    return (
        X[train_mask], y[train_mask],
        X[val_mask], y[val_mask],
        X[test_mask], y[test_mask],
    )


def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    iterations: int = 1000,
    verbose: int = 100,
) -> CatBoostClassifier:
    """Train CatBoostClassifier with early stopping on validation set."""
    cat_feature_indices = [ALL_FEATURES.index(c) for c in CAT_FEATURES]

    model = CatBoostClassifier(
        iterations=iterations,
        learning_rate=0.01,
        depth=6,
        l2_leaf_reg=5,
        loss_function="Logloss",
        eval_metric="AUC",
        random_seed=42,
        early_stopping_rounds=100,
        verbose=verbose,
        cat_features=cat_feature_indices,
    )

    train_pool = Pool(X_train, y_train, cat_features=cat_feature_indices)
    val_pool = Pool(X_val, y_val, cat_features=cat_feature_indices)

    model.fit(train_pool, eval_set=val_pool, use_best_model=True)

    return model


def evaluate(
    model: CatBoostClassifier,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    df_test: pd.DataFrame | None = None,
) -> dict:
    """Evaluate model on test set. Returns metrics dict."""
    cat_feature_indices = [ALL_FEATURES.index(c) for c in CAT_FEATURES]
    test_pool = Pool(X_test, cat_features=cat_feature_indices)

    y_prob = model.predict_proba(test_pool)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    auc = roc_auc_score(y_test, y_prob)
    brier = brier_score_loss(y_test, y_prob)
    accuracy = (y_pred == y_test.values).mean()

    print(f"\n{'='*50}")
    print(f"TEST SET EVALUATION (2025 season)")
    print(f"{'='*50}")
    print(f"AUC:      {auc:.4f}  (target > 0.72)")
    print(f"Brier:    {brier:.4f}  (target < 0.20)")
    print(f"Accuracy: {accuracy:.4f}")

    # Calibration: 10 buckets
    print(f"\nCalibration (10 buckets):")
    print(f"{'Bucket':>10} {'Mean Pred':>10} {'Actual Win%':>12} {'Count':>8}")
    buckets = pd.cut(y_prob, bins=10)
    cal_df = pd.DataFrame({"prob": y_prob, "actual": y_test.values, "bucket": buckets})
    for bucket, group in cal_df.groupby("bucket", observed=True):
        if len(group) > 0:
            print(f"{str(bucket):>10} {group['prob'].mean():>10.3f} {group['actual'].mean():>12.3f} {len(group):>8}")

    # Mid-match accuracy (innings 2, over >= 10) if we have the test df
    if df_test is not None and "over" in df_test.columns and "innings" in df_test.columns:
        mid_mask = (df_test["innings"] == 2) & (df_test["over"] >= 10)
        if mid_mask.any():
            mid_prob = y_prob[mid_mask.values]
            mid_actual = y_test.values[mid_mask.values]
            mid_pred = (mid_prob >= 0.5).astype(int)
            mid_acc = (mid_pred == mid_actual).mean()
            print(f"\nMid-match accuracy (Inn 2, Over 10+): {mid_acc:.4f}")

    metrics = {
        "test_auc": round(auc, 4),
        "test_brier": round(brier, 4),
        "test_accuracy": round(accuracy, 4),
    }

    # Check threshold
    if auc < 0.70:
        print(f"\n*** WARNING: AUC {auc:.4f} < 0.70 threshold. Model will NOT be used for blending. ***")
        metrics["below_threshold"] = True
    else:
        metrics["below_threshold"] = False

    return metrics


def save_artifacts(
    model: CatBoostClassifier,
    metrics: dict,
    output_dir: str | Path = DEFAULT_MODEL_DIR,
) -> None:
    """Save trained model and metadata."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = output_dir / "win_prob.cbm"
    model.save_model(str(model_path))
    print(f"\nModel saved to: {model_path}")

    meta = {
        "cat_features": CAT_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "all_features": ALL_FEATURES,
        "seasons_trained": sorted(TRAIN_SEASONS),
        "seasons_val": sorted(VAL_SEASONS),
        "seasons_test": sorted(TEST_SEASONS),
        **metrics,
    }

    meta_path = output_dir / "win_prob_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"Metadata saved to: {meta_path}")


def run_training(
    csv_path: str | Path,
    output_dir: str | Path = DEFAULT_MODEL_DIR,
    iterations: int = 1000,
    verbose: int = 100,
) -> dict:
    """Full training pipeline. Returns metrics dict."""
    # Step 1: Load and filter
    df = load_and_filter(csv_path)

    # Step 2: Build features
    X, y = build(df)
    print(f"Feature matrix: {X.shape[0]} rows x {X.shape[1]} features")
    print(f"Label distribution: {y.value_counts().to_dict()}")

    # Step 3: Split by season
    X_train, y_train, X_val, y_val, X_test, y_test = split_by_season(df, X, y)
    print(f"\nTrain: {len(X_train)} rows | Val: {len(X_val)} rows | Test: {len(X_test)} rows")

    # Step 4: Train
    print(f"\nTraining CatBoost ({iterations} iterations, early stop 50)...")
    model = train_model(X_train, y_train, X_val, y_val, iterations, verbose)

    # Step 5: Evaluate
    # Get the test slice of original df for mid-match analysis
    test_mask = df["season"].isin(TEST_SEASONS)
    df_test = df[test_mask].reset_index(drop=True)
    metrics = evaluate(model, X_test, y_test, df_test)

    # Step 6: Save
    save_artifacts(model, metrics, output_dir)

    print(f"\nModel saved. Test AUC: {metrics['test_auc']:.4f} Brier: {metrics['test_brier']:.4f}")
    return metrics


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Train CatBoost IPL win-probability model")
    parser.add_argument("--data", required=True, help="Path to ball-by-ball CSV")
    parser.add_argument("--output", default=str(DEFAULT_MODEL_DIR), help="Model output directory")
    parser.add_argument("--iterations", type=int, default=1000, help="CatBoost iterations")
    parser.add_argument("--verbose", type=int, default=100, help="Log interval")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_training(args.data, args.output, args.iterations, args.verbose)


if __name__ == "__main__":
    main()
