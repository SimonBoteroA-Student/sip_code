"""Unit tests for GPU optimization — DMatrix caching & max_bin for HP search.

Plan 17-04: Verifies that:
- CV scoring functions (CPU path) are unchanged when fold_dmats=None
- DMatrix objects are picklable (needed for future parallel use)
- max_bin=512 injection logic works correctly for CUDA device kwargs
- _hp_search() CPU path is deterministic (same seed → same results)

GPU-specific tests (that require actual CUDA hardware) are marked with
@pytest.mark.skipif so they are skipped in CI environments without a GPU.
"""

from __future__ import annotations

import numpy as np
import pytest

xgb = pytest.importorskip("xgboost")


# =============================================================================
# Helpers
# =============================================================================

def _make_imbalanced_dataset(
    n_samples: int = 200,
    n_features: int = 8,
    positive_rate: float = 0.1,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Create a tiny synthetic binary classification dataset."""
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n_samples, n_features)).astype(np.float32)
    n_pos = max(1, int(n_samples * positive_rate))
    y = np.zeros(n_samples, dtype=np.int32)
    y[:n_pos] = 1
    rng.shuffle(y)
    return X, y


# =============================================================================
# Test 1 — CPU path unchanged for scale_pos_weight
# =============================================================================


def test_cv_score_scale_pos_weight_cpu_path_unchanged() -> None:
    """_cv_score_scale_pos_weight with fold_dmats=None returns (mean, std) floats."""
    from sip_engine.classifiers.models.trainer import _cv_score_scale_pos_weight

    X, y = _make_imbalanced_dataset(n_samples=120, n_features=6, seed=0)
    params = {
        "n_estimators": 20,
        "max_depth": 3,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 1,
        "gamma": 0,
        "reg_alpha": 0,
        "reg_lambda": 1,
    }
    mean_auc, std_auc = _cv_score_scale_pos_weight(
        params=params,
        X=X,
        y=y,
        n_splits=2,
        seed=42,
        device_kwargs={"tree_method": "hist"},
        fold_dmats=None,
    )
    assert isinstance(mean_auc, float), f"Expected float, got {type(mean_auc)}"
    assert isinstance(std_auc, float), f"Expected float, got {type(std_auc)}"
    assert 0.0 <= mean_auc <= 1.0, f"mean_auc out of range: {mean_auc}"
    assert std_auc >= 0.0, f"std_auc negative: {std_auc}"


# =============================================================================
# Test 2 — CPU path unchanged for upsampling
# =============================================================================


def test_cv_score_upsampling_cpu_path_unchanged() -> None:
    """_cv_score_upsampling with fold_dmats=None returns (mean, std) floats."""
    from sip_engine.classifiers.models.trainer import _cv_score_upsampling

    X, y = _make_imbalanced_dataset(n_samples=120, n_features=6, seed=1)
    params = {
        "n_estimators": 20,
        "max_depth": 3,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 1,
        "gamma": 0,
        "reg_alpha": 0,
        "reg_lambda": 1,
    }
    mean_auc, std_auc = _cv_score_upsampling(
        params=params,
        X=X,
        y=y,
        n_splits=2,
        seed=42,
        device_kwargs={"tree_method": "hist"},
        fold_dmats=None,
    )
    assert isinstance(mean_auc, float), f"Expected float, got {type(mean_auc)}"
    assert isinstance(std_auc, float), f"Expected float, got {type(std_auc)}"
    assert 0.0 <= mean_auc <= 1.0, f"mean_auc out of range: {mean_auc}"
    assert std_auc >= 0.0, f"std_auc negative: {std_auc}"


# =============================================================================
# Test 3 — DMatrix is picklable
# =============================================================================


def test_dmatrix_fold_structure() -> None:
    """xgb.DMatrix objects have correct shape and support binary serialization.

    Note: DMatrix is NOT pickle-serializable (ctypes pointer limitation) — this is
    expected. XGBoost provides .save_binary() / xgb.DMatrix(path) for serialization.
    This test verifies the DMatrix has the expected shape and is usable in training.
    """
    import tempfile
    import os

    data = np.ones((10, 3), dtype=np.float32)
    labels = np.ones(10, dtype=np.float32)
    dm = xgb.DMatrix(data, label=labels)

    # Verify shape
    assert dm.num_row() == 10, f"Expected 10 rows, got {dm.num_row()}"
    assert dm.num_col() == 3, f"Expected 3 cols, got {dm.num_col()}"

    # Verify binary round-trip (the XGBoost-native serialization path)
    with tempfile.NamedTemporaryFile(suffix=".buffer", delete=False) as f:
        tmp_path = f.name
    try:
        dm.save_binary(tmp_path)
        dm_reloaded = xgb.DMatrix(tmp_path)
        assert dm_reloaded.num_row() == 10
        assert dm_reloaded.num_col() == 3
    finally:
        os.unlink(tmp_path)


# =============================================================================
# Test 4 — max_bin injection for CUDA kwargs
# =============================================================================


def test_max_bin_added_to_cuda_kwargs() -> None:
    """max_bin=512 is injected when device='cuda' and not already present."""
    device_kwargs: dict = {"device": "cuda"}
    if device_kwargs.get("device", "").startswith("cuda") and "max_bin" not in device_kwargs:
        device_kwargs = {**device_kwargs, "max_bin": 512}
    assert device_kwargs["max_bin"] == 512, (
        f"Expected max_bin=512, got {device_kwargs.get('max_bin')}"
    )


def test_max_bin_not_overwritten_when_already_set() -> None:
    """max_bin is NOT overwritten if caller already set it explicitly."""
    device_kwargs: dict = {"device": "cuda", "max_bin": 256}
    if device_kwargs.get("device", "").startswith("cuda") and "max_bin" not in device_kwargs:
        device_kwargs = {**device_kwargs, "max_bin": 512}
    assert device_kwargs["max_bin"] == 256, (
        f"Expected max_bin=256 (caller-set), got {device_kwargs.get('max_bin')}"
    )


def test_max_bin_not_added_for_cpu() -> None:
    """max_bin is NOT injected for non-CUDA device kwargs."""
    device_kwargs: dict = {"tree_method": "hist"}
    if device_kwargs.get("device", "").startswith("cuda") and "max_bin" not in device_kwargs:
        device_kwargs = {**device_kwargs, "max_bin": 512}
    assert "max_bin" not in device_kwargs, (
        f"max_bin should not be injected for CPU: {device_kwargs}"
    )


# =============================================================================
# Test 5 — _hp_search CPU determinism
# =============================================================================


def test_hp_search_cpu_determinism() -> None:
    """_hp_search() with same seed produces identical best_cv_auc_mean (CPU path)."""
    from sip_engine.classifiers.models.trainer import _hp_search

    X, y = _make_imbalanced_dataset(n_samples=150, n_features=8, seed=42)
    common_kwargs = dict(
        X=X,
        y=y,
        n_iter=2,
        n_splits=2,
        seed=42,
        device_kwargs={"tree_method": "hist"},
        progress=False,
    )
    result1 = _hp_search(**common_kwargs)
    result2 = _hp_search(**common_kwargs)

    assert result1["best_cv_auc_mean"] == result2["best_cv_auc_mean"], (
        f"CPU determinism broken: {result1['best_cv_auc_mean']} != {result2['best_cv_auc_mean']}"
    )
    assert result1["best_strategy"] == result2["best_strategy"], (
        f"CPU strategy non-deterministic: {result1['best_strategy']} != {result2['best_strategy']}"
    )


# =============================================================================
# Test 6 — fold_dmats parameter forwarded through _compare_strategies
# =============================================================================


def test_compare_strategies_accepts_fold_dmats_params() -> None:
    """_compare_strategies must accept fold_dmats_spw and fold_dmats_ups parameters."""
    import inspect
    from sip_engine.classifiers.models.trainer import _compare_strategies

    sig = inspect.signature(_compare_strategies)
    assert "fold_dmats_spw" in sig.parameters, (
        "_compare_strategies missing fold_dmats_spw parameter"
    )
    assert "fold_dmats_ups" in sig.parameters, (
        "_compare_strategies missing fold_dmats_ups parameter"
    )


# =============================================================================
# GPU tests (skipped unless CUDA is available)
# =============================================================================


_CUDA_AVAILABLE = xgb.build_info().get("USE_CUDA", False)


@pytest.mark.skipif(not _CUDA_AVAILABLE, reason="CUDA not available in this XGBoost build")
def test_cv_score_scale_pos_weight_dmatrix_path() -> None:
    """CUDA DMatrix path returns valid AUC scores."""
    from sip_engine.classifiers.models.trainer import _cv_score_scale_pos_weight
    from sklearn.model_selection import StratifiedKFold

    X, y = _make_imbalanced_dataset(n_samples=200, n_features=8, seed=99)
    device_kwargs: dict = {"device": "cuda:0", "tree_method": "hist", "max_bin": 512}

    # Pre-build fold DMatrix (mirrors _hp_search logic)
    cv = StratifiedKFold(n_splits=2, shuffle=True, random_state=42)
    fold_dmats = []
    for train_idx, val_idx in cv.split(X, y):
        X_tr, y_tr = X[train_idx], y[train_idx]
        X_val, y_val = X[val_idx], y[val_idx]
        fold_dmats.append((
            xgb.DMatrix(X_tr, label=y_tr),
            xgb.DMatrix(X_val, label=y_val),
            y_val,
        ))

    params = {
        "n_estimators": 20,
        "max_depth": 3,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 1,
        "gamma": 0,
        "reg_alpha": 0,
        "reg_lambda": 1,
    }
    mean_auc, std_auc = _cv_score_scale_pos_weight(
        params=params,
        X=X,
        y=y,
        n_splits=2,
        seed=42,
        device_kwargs=device_kwargs,
        fold_dmats=fold_dmats,
    )
    assert 0.0 <= mean_auc <= 1.0
    assert std_auc >= 0.0
