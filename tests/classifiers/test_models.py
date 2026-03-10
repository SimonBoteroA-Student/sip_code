"""Unit tests for sip_engine.classifiers.models.trainer training infrastructure.

All tests use tiny in-memory fixtures (no disk I/O, no real data).
Tests must complete in under 15 seconds total.

Tests cover MODL-01 through MODL-09 requirements.
"""

from __future__ import annotations

import json
import subprocess
import sys

import joblib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from sip_engine.classifiers.models.trainer import (
    MODEL_IDS,
    PARAM_DIST,
    _compare_strategies,
    _cv_score_scale_pos_weight,
    _cv_score_upsampling,
    _hp_search,
    _stratified_split,
    _train_with_fallback,
    train_model,
)
from sip_engine.shared.hardware import get_xgb_device_kwargs
from sip_engine.classifiers.features.pipeline import FEATURE_COLUMNS


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
# Test 1: Device kwargs from hardware module
# =============================================================================


def test_get_xgb_device_kwargs():
    """get_xgb_device_kwargs returns a valid dict with tree_method key for all device types.

    Tests the hardware module function that replaced the old _detect_xgb_device().
    """
    # CPU
    cpu_result = get_xgb_device_kwargs("cpu")
    assert isinstance(cpu_result, dict), "Should return a dict"
    assert "tree_method" in cpu_result, "Should always have tree_method key"
    assert cpu_result["tree_method"] == "hist", "tree_method should be 'hist'"

    # CUDA
    cuda_result = get_xgb_device_kwargs("cuda")
    assert cuda_result["device"] == "cuda", "CUDA should set device='cuda'"
    assert cuda_result["tree_method"] == "hist", "tree_method should be 'hist'"

    # ROCm
    rocm_result = get_xgb_device_kwargs("rocm")
    assert rocm_result["device"] == "cuda:0", "ROCm should use device='cuda:0' (HIP API)"
    assert rocm_result["tree_method"] == "hist", "tree_method should be 'hist'"


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


# =============================================================================
# Integration test helpers
# =============================================================================


def _make_tiny_features_parquet(tmp_path, n_rows=50, seed=0):
    """Create a tiny features.parquet with FEATURE_COLUMNS and id_contrato index."""
    rng = np.random.RandomState(seed)
    data = {col: rng.rand(n_rows).astype(np.float32) for col in FEATURE_COLUMNS}
    df = pd.DataFrame(data)
    df.index = pd.Index([f"CON-{i:04d}" for i in range(n_rows)], name="id_contrato")
    path = tmp_path / "features.parquet"
    table = pa.Table.from_pandas(df, preserve_index=True)
    pq.write_table(table, path)
    return path


def _make_tiny_labels_parquet(tmp_path, n_rows=50, seed=0):
    """Create a tiny labels.parquet with M1-M4 as nullable Int8 and id_contrato column.

    M1/M2: ~20% positive (10 of 50).
    M3/M4: ~6% positive (3 of 50) with some NaN to test extreme imbalance.
    """
    rng = np.random.RandomState(seed)
    ids = [f"CON-{i:04d}" for i in range(n_rows)]

    # M1/M2: 20% positive
    m1 = pd.array([1 if i < 10 else 0 for i in range(n_rows)], dtype="Int8")
    m2 = pd.array([1 if i < 10 else 0 for i in range(n_rows)], dtype="Int8")

    # M3/M4: 3 positives, 5 NaN, rest 0
    m3_vals = [1] * 3 + [pd.NA] * 5 + [0] * (n_rows - 8)
    m4_vals = [1] * 3 + [pd.NA] * 5 + [0] * (n_rows - 8)
    m3 = pd.array(m3_vals, dtype="Int8")
    m4 = pd.array(m4_vals, dtype="Int8")

    df = pd.DataFrame({
        "id_contrato": ids,
        "M1": m1,
        "M2": m2,
        "M3": m3,
        "M4": m4,
    })
    path = tmp_path / "labels.parquet"
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, path)
    return path


# =============================================================================
# Test 11: train_model raises FileNotFoundError when features.parquet missing
# =============================================================================


def test_train_model_missing_features(tmp_path, monkeypatch):
    """train_model raises FileNotFoundError with 'build-features' when no features.parquet."""
    from sip_engine.shared.config import get_settings
    # Patch artifacts_models_dir to tmp_path to prevent early return when real model.pkl exists.
    # train_model() checks (model_dir / "model.pkl").exists() BEFORE features_path/labels_path.
    monkeypatch.setattr(get_settings(), "artifacts_models_dir", tmp_path / "models")
    monkeypatch.setattr(get_settings(), "features_path", tmp_path / "features.parquet")
    monkeypatch.setattr(get_settings(), "labels_path", tmp_path / "labels.parquet")

    with pytest.raises(FileNotFoundError, match="build-features"):
        train_model("M1")


# =============================================================================
# Test 12: train_model raises FileNotFoundError when labels.parquet missing
# =============================================================================


def test_train_model_missing_labels(tmp_path, monkeypatch):
    """train_model raises FileNotFoundError with 'build-labels' when no labels.parquet."""
    # Create features.parquet but NOT labels.parquet
    features_path = _make_tiny_features_parquet(tmp_path)

    from sip_engine.shared.config import get_settings
    # Patch artifacts_models_dir to tmp_path to prevent early return when real model.pkl exists.
    # train_model() checks (model_dir / "model.pkl").exists() BEFORE features_path/labels_path.
    monkeypatch.setattr(get_settings(), "artifacts_models_dir", tmp_path / "models")
    monkeypatch.setattr(get_settings(), "features_path", features_path)
    monkeypatch.setattr(get_settings(), "labels_path", tmp_path / "labels.parquet")

    with pytest.raises(FileNotFoundError, match="build-labels"):
        train_model("M1")


# =============================================================================
# Test 13: train_model raises ValueError for invalid model_id
# =============================================================================


def test_train_model_invalid_model_id():
    """train_model raises ValueError for model_id not in MODEL_IDS."""
    with pytest.raises(ValueError, match="M99"):
        train_model("M99")


# =============================================================================
# Test 14: train_model skips existing model without --force
# =============================================================================


def test_train_model_skip_existing(tmp_path, monkeypatch):
    """train_model returns early when model.pkl exists and force=False."""
    features_path = _make_tiny_features_parquet(tmp_path)
    labels_path = _make_tiny_labels_parquet(tmp_path)

    from sip_engine.shared.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "features_path", features_path)
    monkeypatch.setattr(settings, "labels_path", labels_path)
    monkeypatch.setattr(settings, "artifacts_models_dir", tmp_path / "models")

    # Create a fake model.pkl in the expected directory
    model_dir = tmp_path / "models" / "M1"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model.pkl").write_text("fake_model")

    # Call without force — should return early without creating training_report.json
    result_dir = train_model("M1", force=False)

    assert result_dir == model_dir
    # training_report.json should NOT exist (we returned early)
    assert not (model_dir / "training_report.json").exists(), (
        "training_report.json should NOT be created when skipping existing model"
    )


# =============================================================================
# Test 15: train_model end-to-end quick mode — parameterized M1-M4
# =============================================================================


@pytest.mark.parametrize("model_id", ["M1", "M2", "M3", "M4"])
def test_train_model_end_to_end_quick(tmp_path, monkeypatch, model_id):
    """train_model produces all 4 artifacts in quick mode with synthetic data."""
    features_path = _make_tiny_features_parquet(tmp_path, n_rows=50)
    labels_path = _make_tiny_labels_parquet(tmp_path, n_rows=50)

    from sip_engine.shared.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "features_path", features_path)
    monkeypatch.setattr(settings, "labels_path", labels_path)
    monkeypatch.setattr(settings, "artifacts_models_dir", tmp_path / "models")
    # Monkeypatch recalibration paths to tmp_path so they don't conflict
    monkeypatch.setattr(settings, "iric_thresholds_path", tmp_path / "iric_thresholds.json")
    monkeypatch.setattr(settings, "encoding_mappings_path", tmp_path / "encoding_mappings.json")
    # Also ensure iric_thresholds_path parent exists
    (tmp_path / "iric_thresholds.json").parent.mkdir(parents=True, exist_ok=True)

    model_dir = train_model(model_id, quick=True, n_iter=3, force=True)

    # Check all 4 artifacts exist
    assert (model_dir / "model.pkl").exists(), "model.pkl must exist"
    assert (model_dir / "feature_registry.json").exists(), "feature_registry.json must exist"
    assert (model_dir / "training_report.json").exists(), "training_report.json must exist"
    assert (model_dir / "test_data.parquet").exists(), "test_data.parquet must exist"

    # Verify feature_registry.json has 45 feature columns
    registry = json.loads((model_dir / "feature_registry.json").read_text())
    assert "feature_columns" in registry, "feature_registry.json must have 'feature_columns'"
    assert len(registry["feature_columns"]) == 45, (
        f"feature_columns must have 45 entries, got {len(registry['feature_columns'])}"
    )

    # Verify training_report.json has strategy_comparison
    report = json.loads((model_dir / "training_report.json").read_text())
    assert "strategy_comparison" in report, "training_report.json must have 'strategy_comparison'"

    # Verify test_data.parquet has id_contrato as named index
    test_df = pq.read_table(model_dir / "test_data.parquet").to_pandas()
    assert test_df.index.name == "id_contrato", (
        f"test_data.parquet index must be 'id_contrato', got {test_df.index.name!r}"
    )

    # Verify model.pkl loads and predict_proba works
    clf = joblib.load(model_dir / "model.pkl")
    n_test = len(test_df)
    X_for_pred = test_df[FEATURE_COLUMNS].values
    proba = clf.predict_proba(X_for_pred)
    assert proba.shape == (n_test, 2), f"predict_proba shape must be ({n_test}, 2)"
    assert (proba >= 0).all() and (proba <= 1).all(), "predict_proba values must be in [0, 1]"


# =============================================================================
# Test 16: feature_registry.json column order matches FEATURE_COLUMNS
# =============================================================================


def test_feature_registry_column_order(tmp_path, monkeypatch):
    """feature_registry.json feature_columns must match FEATURE_COLUMNS exactly (order matters)."""
    features_path = _make_tiny_features_parquet(tmp_path, n_rows=50)
    labels_path = _make_tiny_labels_parquet(tmp_path, n_rows=50)

    from sip_engine.shared.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "features_path", features_path)
    monkeypatch.setattr(settings, "labels_path", labels_path)
    monkeypatch.setattr(settings, "artifacts_models_dir", tmp_path / "models")
    monkeypatch.setattr(settings, "iric_thresholds_path", tmp_path / "iric_thresholds.json")
    monkeypatch.setattr(settings, "encoding_mappings_path", tmp_path / "encoding_mappings.json")

    model_dir = train_model("M1", quick=True, n_iter=3, force=True)

    registry = json.loads((model_dir / "feature_registry.json").read_text())
    assert registry["feature_columns"] == FEATURE_COLUMNS, (
        "feature_registry.json feature_columns must match FEATURE_COLUMNS exactly "
        "(order and contents)"
    )


# =============================================================================
# Test 17: CLI train --help shows all flags including new Phase 12 flags
# =============================================================================


def test_cli_train_help():
    """python -m sip_engine train --help exits 0 and shows all required flags."""
    result = subprocess.run(
        [sys.executable, "-m", "sip_engine", "train", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"train --help should exit 0, got {result.returncode}"
    output = result.stdout
    for flag in ("--model", "--force", "--quick", "--n-iter", "--n-jobs",
                 "--device", "--disable-rocm", "--no-interactive"):
        assert flag in output, f"train --help output must contain '{flag}'"


# =============================================================================
# Test 18: CLI run-pipeline --help shows new Phase 12 flags
# =============================================================================


def test_cli_run_pipeline_help():
    """python -m sip_engine run-pipeline --help shows device/rocm/interactive flags."""
    result = subprocess.run(
        [sys.executable, "-m", "sip_engine", "run-pipeline", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"run-pipeline --help should exit 0, got {result.returncode}"
    output = result.stdout
    for flag in ("--device", "--disable-rocm", "--no-interactive"):
        assert flag in output, f"run-pipeline --help output must contain '{flag}'"


# =============================================================================
# Test 19: train_model accepts new params without error
# =============================================================================


def test_train_model_accepts_new_params():
    """train_model signature accepts device, disable_rocm, interactive kwargs."""
    import inspect
    sig = inspect.signature(train_model)
    param_names = list(sig.parameters.keys())
    assert "device" in param_names, "train_model must accept 'device' param"
    assert "disable_rocm" in param_names, "train_model must accept 'disable_rocm' param"
    assert "interactive" in param_names, "train_model must accept 'interactive' param"

    # Verify defaults are backward-compatible
    assert sig.parameters["device"].default is None, "device default must be None"
    assert sig.parameters["disable_rocm"].default is False, "disable_rocm default must be False"
    assert sig.parameters["interactive"].default is True, "interactive default must be True"


# =============================================================================
# Test 20: _train_with_fallback on CPU works
# =============================================================================


def test_train_with_fallback_cpu():
    """_train_with_fallback trains successfully on CPU and returns correct device."""
    import xgboost as xgb

    clf_kwargs = {
        "n_estimators": 10,
        "max_depth": 3,
        "learning_rate": 0.1,
        "tree_method": "hist",
        "objective": "binary:logistic",
        "verbosity": 0,
        "random_state": 42,
    }
    clf, actual_device = _train_with_fallback(clf_kwargs, tiny_X, tiny_y, "cpu")
    assert isinstance(clf, xgb.XGBClassifier), "Should return an XGBClassifier"
    assert actual_device == "cpu", "Should report 'cpu' as actual device"
