"""
CatBoost inference wrapper — called during simulation for win probability.

Loads the trained model once at startup. Prediction is pure inference (<10ms),
no I/O, no LLM calls.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from .feature_builder import ALL_FEATURES, CAT_FEATURES, NUMERIC_FEATURES, build_single

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = Path(__file__).parent / "models" / "win_prob.cbm"
DEFAULT_META_PATH = Path(__file__).parent / "models" / "win_prob_meta.json"

# AUC threshold — model below this is not used for blending
MIN_AUC_THRESHOLD = 0.70


class CatBoostPredictor:
    """
    Singleton-style CatBoost predictor for match win probability.

    Load once at simulation startup via `load()`. Call `predict()` per ball/over.
    Falls back gracefully if model unavailable.
    """

    def __init__(self) -> None:
        self._model = None
        self._meta: dict = {}
        self._cat_feature_indices: list[int] = []
        self._loaded = False
        self._below_threshold = False

    def load(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        meta_path: str | Path = DEFAULT_META_PATH,
    ) -> bool:
        """
        Load model from disk. Returns True if successfully loaded and above threshold.
        """
        model_path = Path(model_path)
        meta_path = Path(meta_path)

        if not model_path.exists():
            logger.warning("CatBoost model not found at %s. Running simulation-only mode.", model_path)
            return False

        try:
            from catboost import CatBoostClassifier

            self._model = CatBoostClassifier()
            self._model.load_model(str(model_path))

            # Load metadata
            if meta_path.exists():
                with open(meta_path) as f:
                    self._meta = json.load(f)

            # Check threshold
            test_auc = self._meta.get("test_auc", 0)
            if test_auc < MIN_AUC_THRESHOLD:
                logger.warning(
                    "CatBoost model below accuracy threshold (AUC %.4f < %.2f). "
                    "Running simulation-only mode.",
                    test_auc, MIN_AUC_THRESHOLD,
                )
                self._below_threshold = True
                self._loaded = True
                return False

            self._cat_feature_indices = [ALL_FEATURES.index(c) for c in CAT_FEATURES]
            self._loaded = True
            self._below_threshold = False
            logger.info(
                "CatBoost model loaded (AUC: %.4f, Brier: %.4f). 30%% blend enabled.",
                test_auc, self._meta.get("test_brier", 0),
            )
            return True

        except Exception as exc:
            logger.error("Failed to load CatBoost model: %s", exc)
            self._loaded = False
            return False

    def is_available(self) -> bool:
        """Returns True if model is loaded and above accuracy threshold."""
        return self._loaded and not self._below_threshold

    def predict(self, match_state: dict[str, Any]) -> float:
        """
        Predict P(batting team wins) from live match state.

        Args:
            match_state: Dict with keys matching feature_builder.build_single() contract.

        Returns:
            Win probability as float in [0.0, 1.0].
            Returns 0.5 (neutral) if model unavailable.
        """
        if not self.is_available():
            return 0.5

        features = build_single(match_state)

        # Build a single-row DataFrame matching training feature order
        row = {col: features[col] for col in ALL_FEATURES}
        df = pd.DataFrame([row])

        # Ensure types match training
        for col in NUMERIC_FEATURES:
            df[col] = df[col].astype(float)
        for col in CAT_FEATURES:
            df[col] = df[col].astype(str)

        from catboost import Pool
        pool = Pool(df, cat_features=self._cat_feature_indices)

        proba = self._model.predict_proba(pool)
        return float(proba[0][1])  # P(label=1) = P(batting team wins)

    def get_meta(self) -> dict:
        """Return model metadata (training info, metrics)."""
        return dict(self._meta)


# Module-level singleton — import and use directly
_predictor: CatBoostPredictor | None = None


def get_predictor() -> CatBoostPredictor:
    """Get or create the global CatBoost predictor (lazy-loaded)."""
    global _predictor
    if _predictor is None:
        _predictor = CatBoostPredictor()
        _predictor.load()
    return _predictor
