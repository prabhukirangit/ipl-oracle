#!/usr/bin/env python3
"""
CLI entrypoint for training the CatBoost IPL win-probability model.

Usage:
    cd ipl-oracle
    uv run python scripts/train_catboost.py --data Dataset/IPL.csv

    # Custom options
    uv run python scripts/train_catboost.py --data Dataset/IPL.csv --iterations 2000 --verbose 50
"""

import sys
from pathlib import Path

# Add backend to path so we can import app.ml
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ml.catboost_trainer import main

if __name__ == "__main__":
    main()
