"""Training infrastructure for SIP XGBoost models.

This module provides the building blocks used by train_model() (Plan 07-02):
- Device detection for XGBoost
- Stratified train/test splitting
- Cross-validation scoring for both imbalance strategies
- Strategy comparison
- Hyperparameter search loop
- train_model() orchestrator (Plan 07-02)

All functions are designed for unit testing with tiny in-memory fixtures
and reuse across Model IDs M1-M4.

Anti-patterns avoided per RESEARCH.md:
- No use_label_encoder (removed in XGBoost 2.0+)
- No gpu_hist as tree_method (deprecated in XGBoost 3.x; use device='cuda')
- No early_stopping_rounds (Gallego approach: n_estimators is a search param)
- n_estimators always set explicitly (default is None in XGBoost 3.x)
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import scipy.stats as stats
from sklearn.model_selection import ParameterSampler, StratifiedKFold, train_test_split
from sklearn.metrics import roc_auc_score
from sklearn.utils import resample
from tqdm import tqdm
import xgboost as xgb

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

MODEL_IDS: list[str] = ["M1", "M2", "M3", "M4"]

RANDOM_SEED: int = 42

# Hyperparameter search space — Gallego et al. (2021) ranges.
# Using scipy.stats distributions for ParameterSampler compatibility.
PARAM_DIST: dict[str, Any] = {
    "n_estimators": stats.randint(50, 501),
    "max_depth": stats.randint(3, 8),
    "learning_rate": stats.loguniform(0.01, 0.3),
    "subsample": stats.uniform(0.5, 0.5),
    "colsample_bytree": stats.uniform(0.5, 0.5),
    "min_child_weight": stats.randint(1, 11),
    "gamma": [0, 0.1, 0.5, 1.0],
    "reg_alpha": [0, 0.1, 1.0],
    "reg_lambda": [0, 1, 5],
}


# =============================================================================
# Device detection
# =============================================================================


def _detect_xgb_device() -> dict:
    """Return XGBoost device kwargs appropriate for the current hardware.

    XGBoost 3.x API:
    - GPU: device='cuda' + tree_method='hist' (NOT 'gpu_hist' which is deprecated)
    - CPU: tree_method='hist' (fastest CPU method; device='cpu' implied)

    Apple Silicon (ARM64 Darwin): XGBoost has no MPS/Metal support — CPU only.

    Returns:
        Dict suitable for **unpacking into XGBClassifier kwargs, e.g.:
            {'tree_method': 'hist'}  for CPU
            {'device': 'cuda', 'tree_method': 'hist'}  for CUDA GPU
    """
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            logger.info("CUDA GPU detected via nvidia-smi — using device='cuda'")
            return {"device": "cuda", "tree_method": "hist"}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    logger.debug("No CUDA GPU detected — using CPU (tree_method='hist')")
    return {"tree_method": "hist"}


# =============================================================================
# Data splitting
# =============================================================================


def _stratified_split(
    X: pd.DataFrame,
    y: pd.Series,
    test_size: float = 0.3,
    seed: int = RANDOM_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Stratified random 70/30 train/test split.

    Implements MODL-07: stratified random split (NOT temporal ordering).
    Preserves class proportion in both splits. Fixed seed ensures reproducibility.

    Args:
        X: Feature DataFrame (any number of columns).
        y: Label Series aligned with X (must have the same index).
        test_size: Fraction for test set. Default 0.3 (30%).
        seed: Random seed for reproducibility. Default 42.

    Returns:
        Tuple (X_train, X_test, y_train, y_test) as DataFrames/Series.
    """
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=seed
    )
    return X_train, X_test, y_train, y_test


# =============================================================================
# CV scoring — Strategy A: scale_pos_weight
# =============================================================================


def _cv_score_scale_pos_weight(
    params: dict,
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int = 5,
    seed: int = RANDOM_SEED,
    device_kwargs: dict | None = None,
) -> tuple[float, float]:
    """Cross-validate XGBClassifier using scale_pos_weight imbalance strategy.

    Strategy A: Passes the negative/positive ratio as scale_pos_weight directly
    to XGBClassifier. No synthetic oversampling — XGBoost handles imbalance
    by weighting the loss function.

    Args:
        params: XGBClassifier hyperparameter dict (from ParameterSampler).
        X: Feature array shape (n_samples, n_features).
        y: Binary label array shape (n_samples,).
        n_splits: Number of StratifiedKFold folds. Default 5.
        seed: Random seed for StratifiedKFold. Default 42.
        device_kwargs: XGBoost device kwargs from _detect_xgb_device(). If None,
            uses CPU default {'tree_method': 'hist'}.

    Returns:
        (mean_auc, std_auc) across folds. Both are floats.
    """
    if device_kwargs is None:
        device_kwargs = {"tree_method": "hist"}

    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    scale_pos_weight = n_neg / max(n_pos, 1)

    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    fold_scores: list[float] = []

    for train_idx, val_idx in cv.split(X, y):
        X_tr, y_tr = X[train_idx], y[train_idx]
        X_val, y_val = X[val_idx], y[val_idx]

        clf = xgb.XGBClassifier(
            **params,
            **device_kwargs,
            objective="binary:logistic",
            scale_pos_weight=scale_pos_weight,
            verbosity=0,
            random_state=seed,
        )
        clf.fit(X_tr, y_tr)
        proba = clf.predict_proba(X_val)[:, 1]
        score = roc_auc_score(y_val, proba)
        fold_scores.append(score)

    return float(np.mean(fold_scores)), float(np.std(fold_scores))


# =============================================================================
# CV scoring — Strategy B: 25% minority upsampling inside folds
# =============================================================================


def _cv_score_upsampling(
    params: dict,
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int = 5,
    seed: int = RANDOM_SEED,
    device_kwargs: dict | None = None,
) -> tuple[float, float]:
    """Cross-validate XGBClassifier with 25% minority upsampling inside CV folds.

    Strategy B: Upsamples the minority class (y==1) inside each training fold
    so that minority / (majority + minority) ~= 25%. The validation fold is
    NEVER upsampled — scores reflect original class distribution.

    Upsampling is done with replacement (bootstrap) via sklearn.utils.resample.

    The target minority count: n_target = int(n_maj * 0.25 / 0.75)
    This achieves 25% minority in the upsampled training set.

    Args:
        params: XGBClassifier hyperparameter dict (from ParameterSampler).
        X: Feature array shape (n_samples, n_features).
        y: Binary label array shape (n_samples,).
        n_splits: Number of StratifiedKFold folds. Default 5.
        seed: Random seed for StratifiedKFold and resample. Default 42.
        device_kwargs: XGBoost device kwargs from _detect_xgb_device(). If None,
            uses CPU default {'tree_method': 'hist'}.

    Returns:
        (mean_auc, std_auc) across folds. Both are floats.
    """
    if device_kwargs is None:
        device_kwargs = {"tree_method": "hist"}

    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    fold_scores: list[float] = []

    for train_idx, val_idx in cv.split(X, y):
        X_tr, y_tr = X[train_idx], y[train_idx]
        X_val, y_val = X[val_idx], y[val_idx]

        # Split fold training data into majority and minority
        maj_mask = y_tr == 0
        min_mask = y_tr == 1
        X_maj, y_maj = X_tr[maj_mask], y_tr[maj_mask]
        X_min, y_min = X_tr[min_mask], y_tr[min_mask]

        n_maj = len(X_maj)
        n_target = int(n_maj * 0.25 / 0.75)  # target 25% minority ratio

        if len(X_min) > 0 and n_target > 0:
            # Upsample minority with replacement — bootstrap sampling
            X_min_up = resample(X_min, n_samples=max(n_target, 1), replace=True, random_state=seed)
            y_min_up = np.ones(len(X_min_up), dtype=y.dtype)
            X_tr_up = np.vstack([X_maj, X_min_up])
            y_tr_up = np.concatenate([y_maj, y_min_up])
        else:
            # Fallback: no minority samples or degenerate fold — use as-is
            X_tr_up, y_tr_up = X_tr, y_tr

        clf = xgb.XGBClassifier(
            **params,
            **device_kwargs,
            objective="binary:logistic",
            verbosity=0,
            random_state=seed,
        )
        clf.fit(X_tr_up, y_tr_up)

        # Score on ORIGINAL validation fold (no upsampling)
        proba = clf.predict_proba(X_val)[:, 1]
        score = roc_auc_score(y_val, proba)
        fold_scores.append(score)

    return float(np.mean(fold_scores)), float(np.std(fold_scores))


# =============================================================================
# Strategy comparison
# =============================================================================


def _compare_strategies(
    params: dict,
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int = 5,
    seed: int = RANDOM_SEED,
    device_kwargs: dict | None = None,
) -> dict:
    """Compare both imbalance strategies with a given hyperparameter set.

    Runs both Strategy A (scale_pos_weight) and Strategy B (25% upsampling)
    using the same params and the same CV splits. The winner is the strategy
    with higher mean CV AUC-ROC. Ties go to scale_pos_weight (simpler model).

    Args:
        params: XGBClassifier hyperparameter dict.
        X: Feature array shape (n_samples, n_features).
        y: Binary label array shape (n_samples,).
        n_splits: Number of StratifiedKFold folds. Default 5.
        seed: Random seed. Default 42.
        device_kwargs: XGBoost device kwargs. If None, uses CPU default.

    Returns:
        Dict with keys:
            "scale_pos_weight": {"mean_cv_auc": float, "std_cv_auc": float}
            "upsampling_25pct": {"mean_cv_auc": float, "std_cv_auc": float}
            "winner": "scale_pos_weight" | "upsampling_25pct"
    """
    spw_mean, spw_std = _cv_score_scale_pos_weight(
        params, X, y, n_splits=n_splits, seed=seed, device_kwargs=device_kwargs
    )
    ups_mean, ups_std = _cv_score_upsampling(
        params, X, y, n_splits=n_splits, seed=seed, device_kwargs=device_kwargs
    )

    # Winner = higher mean AUC. Ties go to scale_pos_weight (simpler).
    winner = "upsampling_25pct" if ups_mean > spw_mean else "scale_pos_weight"

    return {
        "scale_pos_weight": {"mean_cv_auc": spw_mean, "std_cv_auc": spw_std},
        "upsampling_25pct": {"mean_cv_auc": ups_mean, "std_cv_auc": ups_std},
        "winner": winner,
    }


# =============================================================================
# Hyperparameter search
# =============================================================================


def _hp_search(
    X: np.ndarray,
    y: np.ndarray,
    n_iter: int = 200,
    n_splits: int = 5,
    seed: int = RANDOM_SEED,
    n_jobs: int = -1,
    device_kwargs: dict | None = None,
    progress: bool = True,
) -> dict:
    """Randomized hyperparameter search with strategy comparison.

    Implements MODL-05 (both imbalance strategies evaluated) and MODL-06
    (randomized search with configurable iterations and StratifiedKFold).

    Generates n_iter random HP candidates from PARAM_DIST (using ParameterSampler
    with the provided seed for reproducibility). For each candidate, both
    imbalance strategies are evaluated via manual CV loops. The best overall
    result (highest mean CV AUC-ROC across both strategies) is tracked.

    Note: n_jobs is reserved for future parallel implementation. The current
    implementation is sequential — manual CV loops with upsampling inside folds
    don't parallelize cleanly with joblib without restructuring. For production
    training with 200 iterations this runs in ~5-30 minutes depending on hardware.

    Args:
        X: Feature array shape (n_samples, n_features).
        y: Binary label array shape (n_samples,).
        n_iter: Number of random HP candidates to evaluate. Default 200.
        n_splits: Number of StratifiedKFold folds per candidate. Default 5.
        seed: Random seed for ParameterSampler and CV. Default 42.
        n_jobs: Reserved for future parallel execution (currently unused).
        device_kwargs: XGBoost device kwargs from _detect_xgb_device(). If None,
            uses CPU default {'tree_method': 'hist'}.
        progress: If True, show tqdm progress bar. Default True.

    Returns:
        Dict with keys:
            "best_params": dict — HP dict of the best-scoring candidate
            "best_strategy": str — "scale_pos_weight" | "upsampling_25pct"
            "best_cv_auc_mean": float — mean CV AUC-ROC of the best candidate
            "best_cv_auc_std": float — std CV AUC-ROC of the best candidate
            "all_results": list[dict] — all n_iter results with params and scores
            "n_iter": int — number of iterations performed
            "n_splits": int — number of CV folds used
    """
    if device_kwargs is None:
        device_kwargs = {"tree_method": "hist"}

    param_samples = list(ParameterSampler(PARAM_DIST, n_iter=n_iter, random_state=seed))

    best_params: dict = {}
    best_strategy: str = ""
    best_cv_auc_mean: float = -1.0
    best_cv_auc_std: float = 0.0
    all_results: list[dict] = []

    iterator = tqdm(param_samples, desc="HP search", disable=not progress)

    for params in iterator:
        comparison = _compare_strategies(
            params=params,
            X=X,
            y=y,
            n_splits=n_splits,
            seed=seed,
            device_kwargs=device_kwargs,
        )

        winner = comparison["winner"]
        winner_mean = comparison[winner]["mean_cv_auc"]
        winner_std = comparison[winner]["std_cv_auc"]

        result_entry = {
            "params": params,
            "scale_pos_weight": comparison["scale_pos_weight"],
            "upsampling_25pct": comparison["upsampling_25pct"],
            "winner": winner,
            "best_mean_cv_auc": winner_mean,
            "best_std_cv_auc": winner_std,
        }
        all_results.append(result_entry)

        if winner_mean > best_cv_auc_mean:
            best_cv_auc_mean = winner_mean
            best_cv_auc_std = winner_std
            best_params = dict(params)
            best_strategy = winner

        if progress:
            iterator.set_postfix(best_auc=f"{best_cv_auc_mean:.4f}")

    logger.info(
        "HP search complete: best_strategy=%s, best_cv_auc=%.4f±%.4f over %d iterations",
        best_strategy,
        best_cv_auc_mean,
        best_cv_auc_std,
        n_iter,
    )

    return {
        "best_params": best_params,
        "best_strategy": best_strategy,
        "best_cv_auc_mean": best_cv_auc_mean,
        "best_cv_auc_std": best_cv_auc_std,
        "all_results": all_results,
        "n_iter": n_iter,
        "n_splits": n_splits,
    }


# =============================================================================
# JSON serialization helper
# =============================================================================


def _json_safe(obj: Any) -> Any:
    """Recursively convert numpy/pandas scalar types to Python natives for JSON.

    Handles: np.integer, np.floating, np.bool_, np.ndarray, pd.NA, dicts, lists.
    All other types passed through as-is.
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(item) for item in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if obj is pd.NA:
        return None
    return obj


# =============================================================================
# train_model() orchestrator
# =============================================================================


def train_model(
    model_id: str,
    force: bool = False,
    quick: bool = False,
    n_iter: int = 200,
    n_jobs: int = -1,
) -> Path:
    """Train a single XGBoost classifier and serialize all artifacts.

    Implements MODL-01 through MODL-04 and MODL-08/09 — the full training
    pipeline for one model (M1, M2, M3, or M4):

    1. Validate model_id
    2. Check force / existing artifacts
    3. Load features.parquet + labels.parquet
    4. Merge on id_contrato (inner join), set id_contrato as named index
    5. Drop NaN labels for this model
    6. Stratified 70/30 split
    7. Recalibrate IRIC thresholds on train-only (IRIC-08)
    7b. Recompute encoding mappings on train-only (for online inference)
    8. Quick-mode adjustments
    9. HP search with strategy comparison
    10. Final refit on full training set with best HPs
    11. Save model.pkl
    12. Save feature_registry.json
    13. Save training_report.json
    14. Save test_data.parquet (with id_contrato as named index)
    15. Log completion and return model_dir

    Args:
        model_id: One of 'M1', 'M2', 'M3', 'M4'.
        force: If True, retrain even if model.pkl already exists.
        quick: If True, use reduced iterations (~20) and 3-fold CV.
        n_iter: Number of HP search iterations. Default 200.
        n_jobs: Reserved for future parallel execution (currently unused).

    Returns:
        Path to the model directory containing all serialized artifacts.

    Raises:
        ValueError: If model_id is not in MODEL_IDS.
        FileNotFoundError: If features.parquet or labels.parquet don't exist.
    """
    from sip_engine.config import get_settings
    from sip_engine.features.pipeline import FEATURE_COLUMNS

    t_start = time.time()

    # ------------------------------------------------------------------
    # Step 1: Validate model_id
    # ------------------------------------------------------------------
    if model_id not in MODEL_IDS:
        raise ValueError(
            f"Invalid model_id {model_id!r}. Must be one of {MODEL_IDS}."
        )

    settings = get_settings()

    # ------------------------------------------------------------------
    # Step 2: Check force / existing artifacts
    # ------------------------------------------------------------------
    model_dir = settings.artifacts_models_dir / model_id
    if (model_dir / "model.pkl").exists() and not force:
        logger.info(
            "Model %s already exists at %s. Use --force to retrain.",
            model_id,
            model_dir,
        )
        return model_dir

    model_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Training model %s — artifacts will be saved to %s", model_id, model_dir)

    # ------------------------------------------------------------------
    # Step 3: Load features.parquet + labels.parquet
    # ------------------------------------------------------------------
    features_path = settings.features_path
    labels_path = settings.labels_path

    if not features_path.exists():
        raise FileNotFoundError(
            f"features.parquet not found at {features_path}. "
            "Run 'python -m sip_engine build-features' first."
        )
    if not labels_path.exists():
        raise FileNotFoundError(
            f"labels.parquet not found at {labels_path}. "
            "Run 'python -m sip_engine build-labels' first."
        )

    logger.info("Loading features.parquet from %s", features_path)
    features_df = pq.read_table(features_path).to_pandas()

    logger.info("Loading labels.parquet from %s", labels_path)
    labels_df = pq.read_table(labels_path).to_pandas()

    # ------------------------------------------------------------------
    # Step 4: Merge on id_contrato, set as named index
    # ------------------------------------------------------------------
    # features_df has id_contrato as index (from build_features parquet write)
    # labels_df has id_contrato as a regular column
    if features_df.index.name == "id_contrato":
        features_df = features_df.reset_index()

    merged = features_df.merge(labels_df, on="id_contrato", how="inner")
    merged = merged.set_index("id_contrato")
    assert merged.index.name == "id_contrato", "id_contrato must be the named index"

    # Ensure all FEATURE_COLUMNS are present (add NaN columns if missing)
    for col in FEATURE_COLUMNS:
        if col not in merged.columns:
            merged[col] = float("nan")

    X = merged[FEATURE_COLUMNS]
    y = merged[model_id]

    # ------------------------------------------------------------------
    # Step 5: Drop NaN labels
    # ------------------------------------------------------------------
    mask = y.notna()
    n_dropped = (~mask).sum()
    X = X[mask]
    y = y[mask].astype(int)

    logger.info(
        "Model %s: %d rows dropped (NaN labels), %d remaining "
        "(%d positive, %d negative)",
        model_id,
        n_dropped,
        len(y),
        int((y == 1).sum()),
        int((y == 0).sum()),
    )

    if (y == 1).sum() == 0:
        logger.warning(
            "Model %s: no positive examples found after dropping NaN labels. "
            "Cannot train. Returning early.",
            model_id,
        )
        return model_dir

    # ------------------------------------------------------------------
    # Step 6: Stratified split
    # ------------------------------------------------------------------
    X_train, X_test, y_train, y_test = _stratified_split(X, y)
    logger.info(
        "Model %s split — train: %d (pos=%d, neg=%d), test: %d (pos=%d, neg=%d)",
        model_id,
        len(y_train),
        int((y_train == 1).sum()),
        int((y_train == 0).sum()),
        len(y_test),
        int((y_test == 1).sum()),
        int((y_test == 0).sum()),
    )
    assert X_train.index.name == "id_contrato", "X_train must have id_contrato index"
    assert X_test.index.name == "id_contrato", "X_test must have id_contrato index"

    # ------------------------------------------------------------------
    # Step 7: IRIC threshold recalibration on train-only (IRIC-08)
    # ------------------------------------------------------------------
    try:
        from sip_engine.iric.thresholds import calibrate_iric_thresholds, save_iric_thresholds

        train_thresholds = calibrate_iric_thresholds(X_train)
        save_iric_thresholds(train_thresholds)
        logger.info(
            "IRIC thresholds recalibrated on train-only data and saved. "
            "Note: iric_* feature column VALUES in features.parquet still reflect "
            "full-dataset calibration from Phase 6. Saved thresholds are for future "
            "online inference."
        )
    except Exception as exc:
        logger.warning(
            "IRIC threshold recalibration failed (%s). Continuing without recalibration.",
            exc,
        )

    # ------------------------------------------------------------------
    # Step 7b: Encoding mappings recalibration on train-only
    # ------------------------------------------------------------------
    try:
        from sip_engine.features.encoding import build_encoding_mappings

        build_encoding_mappings(X_train, force=True)
        logger.info(
            "Encoding mappings recomputed on train-only data for online inference. "
            "features.parquet integer codes unchanged."
        )
    except Exception as exc:
        logger.warning(
            "Encoding mappings recalibration failed (%s). Continuing without recalibration.",
            exc,
        )

    # ------------------------------------------------------------------
    # Step 8: Quick mode adjustments
    # ------------------------------------------------------------------
    if quick:
        n_iter = min(n_iter, 20)
        n_splits = 3
        logger.info("Quick mode: n_iter=%d, n_splits=%d", n_iter, n_splits)
    else:
        n_splits = 5

    # Guard against extreme class imbalance breaking StratifiedKFold
    n_pos_train = int((y_train == 1).sum())
    if n_pos_train < n_splits:
        n_splits = max(2, n_pos_train)
        logger.warning(
            "Model %s: only %d positive examples in train set. "
            "Reducing n_splits to %d to avoid StratifiedKFold error.",
            model_id,
            n_pos_train,
            n_splits,
        )

    # ------------------------------------------------------------------
    # Step 9: HP search
    # ------------------------------------------------------------------
    device_kwargs = _detect_xgb_device()
    logger.info(
        "Starting HP search for model %s: n_iter=%d, n_splits=%d, device=%s",
        model_id,
        n_iter,
        n_splits,
        device_kwargs,
    )

    search_result = _hp_search(
        X_train.values,
        y_train.values,
        n_iter=n_iter,
        n_splits=n_splits,
        seed=RANDOM_SEED,
        n_jobs=n_jobs,
        device_kwargs=device_kwargs,
        progress=True,
    )

    best_params = search_result["best_params"]
    best_strategy = search_result["best_strategy"]
    logger.info(
        "HP search complete — best strategy: %s, best CV AUC-ROC: %.4f±%.4f",
        best_strategy,
        search_result["best_cv_auc_mean"],
        search_result["best_cv_auc_std"],
    )

    # ------------------------------------------------------------------
    # Step 10: Final refit on full training set
    # ------------------------------------------------------------------
    scale_pos_weight_value = float((y_train == 0).sum()) / max(int((y_train == 1).sum()), 1)

    clf_kwargs: dict = {
        **best_params,
        **device_kwargs,
        "objective": "binary:logistic",
        "verbosity": 0,
        "random_state": RANDOM_SEED,
    }

    if best_strategy == "scale_pos_weight":
        clf_kwargs["scale_pos_weight"] = scale_pos_weight_value

    clf = xgb.XGBClassifier(**clf_kwargs)

    if best_strategy == "upsampling_25pct":
        # Upsample minority on full training set before final fit
        X_train_arr = X_train.values
        y_train_arr = y_train.values
        maj_mask = y_train_arr == 0
        min_mask = y_train_arr == 1
        X_maj, y_maj = X_train_arr[maj_mask], y_train_arr[maj_mask]
        X_min, y_min = X_train_arr[min_mask], y_train_arr[min_mask]
        n_maj = len(X_maj)
        n_target = int(n_maj * 0.25 / 0.75)
        if len(X_min) > 0 and n_target > 0:
            X_min_up = resample(X_min, n_samples=max(n_target, 1), replace=True, random_state=RANDOM_SEED)
            y_min_up = np.ones(len(X_min_up), dtype=y_train_arr.dtype)
            X_fit_arr = np.vstack([X_maj, X_min_up])
            y_fit_arr = np.concatenate([y_maj, y_min_up])
        else:
            X_fit_arr, y_fit_arr = X_train_arr, y_train_arr
        # Wrap in DataFrame with column names so feature_names_in_ is set
        X_fit_df = pd.DataFrame(X_fit_arr, columns=FEATURE_COLUMNS)
        clf.fit(X_fit_df, y_fit_arr)
    else:
        # scale_pos_weight strategy — fit on training DataFrame directly
        clf.fit(X_train[FEATURE_COLUMNS], y_train)

    logger.info("Final model refitted on full training set (%d samples)", len(y_train))

    # ------------------------------------------------------------------
    # Step 11: Save model.pkl
    # ------------------------------------------------------------------
    model_pkl_path = model_dir / "model.pkl"
    joblib.dump(clf, model_pkl_path)
    logger.info("model.pkl saved to %s", model_pkl_path)

    # ------------------------------------------------------------------
    # Step 12: Save feature_registry.json
    # ------------------------------------------------------------------
    feature_registry = _json_safe({
        "model_id": model_id,
        "feature_columns": FEATURE_COLUMNS,
        "n_features": len(FEATURE_COLUMNS),
        "training_date": datetime.now(tz=timezone.utc).isoformat(),
        "label": model_id,
        "best_strategy": best_strategy,
        "best_params": best_params,
        "cv_auc_roc_mean": search_result["best_cv_auc_mean"],
        "cv_auc_roc_std": search_result["best_cv_auc_std"],
        "train_size": len(y_train),
        "test_size": len(y_test),
        "class_distribution": {
            "0": int((y_train == 0).sum()),
            "1": int((y_train == 1).sum()),
        },
        "random_seed": RANDOM_SEED,
    })
    registry_path = model_dir / "feature_registry.json"
    registry_path.write_text(json.dumps(feature_registry, indent=2))
    logger.info("feature_registry.json saved to %s", registry_path)

    # ------------------------------------------------------------------
    # Step 13: Save training_report.json
    # ------------------------------------------------------------------
    t_duration = time.time() - t_start

    # Build strategy comparison summary from HP search
    # Find the best-scoring candidate for each strategy
    spw_scores = [r["scale_pos_weight"]["mean_cv_auc"] for r in search_result["all_results"]]
    ups_scores = [r["upsampling_25pct"]["mean_cv_auc"] for r in search_result["all_results"]]
    strategy_comparison = {
        "scale_pos_weight": {
            "mean_cv_auc": float(np.mean(spw_scores)) if spw_scores else 0.0,
            "best_cv_auc": float(max(spw_scores)) if spw_scores else 0.0,
        },
        "upsampling_25pct": {
            "mean_cv_auc": float(np.mean(ups_scores)) if ups_scores else 0.0,
            "best_cv_auc": float(max(ups_scores)) if ups_scores else 0.0,
        },
        "winner": best_strategy,
    }

    training_report = _json_safe({
        "model_id": model_id,
        "label_distribution": {
            "0": int((y == 0).sum()),
            "1": int((y == 1).sum()),
        },
        "scale_pos_weight_value": scale_pos_weight_value,
        "strategy_comparison": strategy_comparison,
        "all_cv_results": search_result["all_results"],
        "best_params": best_params,
        "training_duration_seconds": t_duration,
        "feature_count": len(FEATURE_COLUMNS),
        "seed": RANDOM_SEED,
        "n_iter": n_iter,
        "n_splits": n_splits,
        "quick_mode": quick,
        "iric_note": (
            "IRIC thresholds recalibrated on train-only and saved for online inference. "
            "iric_* feature column VALUES in features.parquet still reflect full-dataset "
            "calibration from Phase 6."
        ),
        "encoding_note": (
            "encoding_mappings.json recomputed on train-only for online inference. "
            "features.parquet integer codes unchanged."
        ),
    })
    report_path = model_dir / "training_report.json"
    report_path.write_text(json.dumps(training_report, indent=2))
    logger.info("training_report.json saved to %s", report_path)

    # ------------------------------------------------------------------
    # Step 14: Save test_data.parquet (with id_contrato as named index)
    # ------------------------------------------------------------------
    assert X_test.index.name == "id_contrato", (
        f"X_test index must be 'id_contrato', got {X_test.index.name!r}"
    )
    test_df = X_test[FEATURE_COLUMNS].copy()
    test_df[model_id] = y_test
    assert test_df.index.name == "id_contrato", (
        "test_df must have 'id_contrato' as named index"
    )
    test_parquet_path = model_dir / "test_data.parquet"
    import pyarrow as pa
    test_table = pa.Table.from_pandas(test_df, preserve_index=True)
    pq.write_table(test_table, test_parquet_path)
    logger.info("test_data.parquet saved to %s", test_parquet_path)

    # ------------------------------------------------------------------
    # Step 15: Log completion
    # ------------------------------------------------------------------
    logger.info(
        "Model %s trained in %.1fs. Saved to %s",
        model_id,
        t_duration,
        model_dir,
    )

    return model_dir
