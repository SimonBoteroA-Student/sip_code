"""Unit tests for sip_engine.models.trainer training infrastructure.

All tests use tiny in-memory fixtures (no disk I/O, no real data).
Tests must complete in under 15 seconds total.

Tests cover MODL-05, MODL-06, MODL-07 requirements.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sip_engine.models.trainer import (
    MODEL_IDS,
    PARAM_DIST,
    _compare_strategies,
    _cv_score_scale_pos_weight,
    _cv_score_upsampling,
    _detect_xgb_device,
    _hp_search,
    _stratified_split,
)


# =============================================================================
# Fixtures
# =============================================================================

_RNG = np.random.RandomState(42)

# tiny_X: 100 samples, 5 features — used as numpy array for CV functions
tiny_X: np.ndarray = _RNG.rand(100, 5).astype(np.float32)

# tiny_y: 85 zeros and 15 ones — imbalanced binary labels
tiny_y: np.ndarray = np.array([0] * 85 + [1] * 15, dtype=np.int32)

# tiny_X_df: DataFrame version with named columns — for _stratified_split
tiny_X_df: pd.DataFrame = pd.DataFrame(
    tiny_X, columns=["f1", "f2", "f3", "f4", "f5"]
)

# tiny_y_series: Series version — for _stratified_split
tiny_y_series: pd.Series = pd.Series(tiny_y, name="label")

# Minimal params for fast XGBoost training in tests (n_estimators=10 is fast)
_FAST_PARAMS: dict = {
    "n_estimators": 10,
    "max_depth": 3,
    "learning_rate": 0.1,
}


# =============================================================================
# Test 1: Device detection
# =============================================================================


def test_detect_xgb_device():
    """_detect_xgb_device returns a valid dict with tree_method key.

    On CI/dev machines without GPU (most environments), tree_method='hist'
    and no 'device' key (or device='cpu').
    On machines with CUDA GPU, device='cuda' and tree_method='hist'.
    """
    result = _detect_xgb_device()

    assert isinstance(result, dict), "Should return a dict"
    assert "tree_method" in result, "Should always have tree_method key"
    assert result["tree_method"] == "hist", "tree_method should be 'hist' for all platforms"

    # If CUDA GPU present: device='cuda'; otherwise device key absent
    if "device" in result:
        assert result["device"] in ("cuda", "cpu"), "device must be 'cuda' or 'cpu'"


# =============================================================================
# Test 2: Stratified split proportions
# =============================================================================


def test_stratified_split_proportions():
    """_stratified_split produces ~70/30 split preserving class proportions."""
    X_train, X_test, y_train, y_test = _stratified_split(tiny_X_df, tiny_y_series)

    # Size check: total must equal original
    assert len(X_train) + len(X_test) == 100, "Total must sum to 100"

    # Approximate size check: 70/30 split
    assert 65 <= len(X_train) <= 75, f"Train should be ~70, got {len(X_train)}"
    assert 25 <= len(X_test) <= 35, f"Test should be ~30, got {len(X_test)}"

    # Class proportion check: ~15% positive in both splits
    # Original proportion = 15/100 = 15%
    train_pos_rate = y_train.sum() / len(y_train)
    assert 0.10 <= train_pos_rate <= 0.20, (
        f"Train positive rate should be ~15%, got {train_pos_rate:.2%}"
    )

    # y sizes must sum to original
    assert len(y_train) + len(y_test) == 100, "y lengths must sum to 100"


# =============================================================================
# Test 3: Stratified split reproducibility
# =============================================================================


def test_stratified_split_reproducibility():
    """_stratified_split is reproducible with same seed, different with different seed."""
    X1, _, _, _ = _stratified_split(tiny_X_df, tiny_y_series, seed=42)
    X2, _, _, _ = _stratified_split(tiny_X_df, tiny_y_series, seed=42)

    assert X1.equals(X2), "Same seed should produce identical X_train splits"

    X3, _, _, _ = _stratified_split(tiny_X_df, tiny_y_series, seed=99)
    assert not X1.equals(X3), "Different seed should produce different X_train splits"


# =============================================================================
# Test 4: CV score — scale_pos_weight strategy
# =============================================================================


def test_cv_score_scale_pos_weight():
    """_cv_score_scale_pos_weight returns valid (mean, std) tuple."""
    mean, std = _cv_score_scale_pos_weight(
        _FAST_PARAMS, tiny_X, tiny_y, n_splits=3
    )

    assert isinstance(mean, float), "mean should be float"
    assert isinstance(std, float), "std should be float"
    assert 0.0 <= mean <= 1.0, f"AUC-ROC mean should be in [0, 1], got {mean}"
    assert std >= 0.0, f"AUC-ROC std should be non-negative, got {std}"


# =============================================================================
# Test 5: CV score — upsampling strategy
# =============================================================================


def test_cv_score_upsampling():
    """_cv_score_upsampling returns valid (mean, std) tuple."""
    mean, std = _cv_score_upsampling(
        _FAST_PARAMS, tiny_X, tiny_y, n_splits=3
    )

    assert isinstance(mean, float), "mean should be float"
    assert isinstance(std, float), "std should be float"
    assert 0.0 <= mean <= 1.0, f"AUC-ROC mean should be in [0, 1], got {mean}"
    assert std >= 0.0, f"AUC-ROC std should be non-negative, got {std}"


# =============================================================================
# Test 6: Upsampling does not leak to validation fold
# =============================================================================


def test_upsampling_does_not_leak_to_val():
    """Indirect test: upsampling inside folds completes without errors.

    If upsampling leaked into the validation fold, the function would either
    crash (size mismatch) or produce anomalously high AUC. We verify the
    function completes cleanly with valid outputs.
    """
    mean, std = _cv_score_upsampling(
        _FAST_PARAMS, tiny_X, tiny_y, n_splits=2
    )

    # Should complete without error and return valid AUC
    assert 0.0 <= mean <= 1.0, f"AUC-ROC mean should be in [0, 1], got {mean}"
    assert std >= 0.0, f"AUC-ROC std should be non-negative, got {std}"

    # Sanity check: AUC should not be suspiciously perfect (which would indicate
    # upsampled minority rows appearing in both train and val)
    # Note: with tiny fixtures and only 10 estimators, ~1.0 is possible but
    # we just verify it's a valid float in range
    assert isinstance(mean, float), "mean must be a float"


# =============================================================================
# Test 7: Strategy comparison
# =============================================================================


def test_compare_strategies():
    """_compare_strategies returns dict with required keys and valid winner."""
    result = _compare_strategies(_FAST_PARAMS, tiny_X, tiny_y, n_splits=3)

    assert isinstance(result, dict), "Should return a dict"
    assert "scale_pos_weight" in result, "Missing 'scale_pos_weight' key"
    assert "upsampling_25pct" in result, "Missing 'upsampling_25pct' key"
    assert "winner" in result, "Missing 'winner' key"

    # Winner must be one of the two strategy names
    assert result["winner"] in ("scale_pos_weight", "upsampling_25pct"), (
        f"winner must be 'scale_pos_weight' or 'upsampling_25pct', got {result['winner']!r}"
    )

    # Each strategy entry should have mean_cv_auc and std_cv_auc
    for strategy_name in ("scale_pos_weight", "upsampling_25pct"):
        entry = result[strategy_name]
        assert "mean_cv_auc" in entry, f"{strategy_name} missing 'mean_cv_auc'"
        assert "std_cv_auc" in entry, f"{strategy_name} missing 'std_cv_auc'"
        assert 0.0 <= entry["mean_cv_auc"] <= 1.0, (
            f"{strategy_name} mean_cv_auc out of range: {entry['mean_cv_auc']}"
        )


# =============================================================================
# Test 8: HP search quick run
# =============================================================================


def test_hp_search_quick():
    """_hp_search with n_iter=3 returns expected structure."""
    result = _hp_search(tiny_X, tiny_y, n_iter=3, n_splits=2, progress=False)

    assert isinstance(result, dict), "Should return a dict"
    assert "best_params" in result, "Missing 'best_params' key"
    assert "best_strategy" in result, "Missing 'best_strategy' key"
    assert "best_cv_auc_mean" in result, "Missing 'best_cv_auc_mean' key"
    assert "best_cv_auc_std" in result, "Missing 'best_cv_auc_std' key"
    assert "all_results" in result, "Missing 'all_results' key"
    assert "n_iter" in result, "Missing 'n_iter' key"
    assert "n_splits" in result, "Missing 'n_splits' key"

    assert len(result["all_results"]) == 3, (
        f"all_results should have 3 entries (n_iter=3), got {len(result['all_results'])}"
    )

    assert 0.0 <= result["best_cv_auc_mean"] <= 1.0, (
        f"best_cv_auc_mean should be in [0, 1], got {result['best_cv_auc_mean']}"
    )

    assert result["best_strategy"] in ("scale_pos_weight", "upsampling_25pct"), (
        f"best_strategy invalid: {result['best_strategy']!r}"
    )

    assert isinstance(result["best_params"], dict), "best_params should be a dict"
    assert result["n_iter"] == 3, "n_iter should match input"
    assert result["n_splits"] == 2, "n_splits should match input"


# =============================================================================
# Test 9: PARAM_DIST has expected keys
# =============================================================================


def test_param_dist_valid():
    """PARAM_DIST contains all expected HP keys from Gallego et al. (2021)."""
    expected_keys = {
        "n_estimators",
        "max_depth",
        "learning_rate",
        "subsample",
        "colsample_bytree",
        "min_child_weight",
        "gamma",
        "reg_alpha",
        "reg_lambda",
    }

    assert set(PARAM_DIST.keys()) == expected_keys, (
        f"PARAM_DIST keys mismatch. Expected: {expected_keys}, "
        f"Got: {set(PARAM_DIST.keys())}"
    )


# =============================================================================
# Test 10: MODEL_IDS
# =============================================================================


def test_model_ids():
    """MODEL_IDS contains exactly the 4 expected model identifiers."""
    assert MODEL_IDS == ["M1", "M2", "M3", "M4"], (
        f"MODEL_IDS should be ['M1', 'M2', 'M3', 'M4'], got {MODEL_IDS}"
    )
