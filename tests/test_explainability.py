"""Unit tests for sip_engine.explainability — SHAP extraction and CRI computation.

Tests cover EXPL-01 through EXPL-05 requirements.
All tests use tiny in-memory fixtures (no disk I/O beyond tmp_path).
Tests must complete in under 30 seconds total.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

from sip_engine.explainability import (
    classify_risk_level,
    compute_cri,
    extract_shap_top_n,
    load_cri_config,
    save_shap_artifact,
)


# =============================================================================
# Fixtures
# =============================================================================

_FEATURE_NAMES = ["feat_a", "feat_b", "feat_c", "feat_d", "feat_e"]

_RNG = np.random.RandomState(42)
_N_TRAIN = 50
_X_TRAIN = _RNG.rand(_N_TRAIN, 5).astype(np.float32)
_Y_TRAIN = np.array([0] * 40 + [1] * 10, dtype=np.int32)


@pytest.fixture(scope="module")
def toy_xgb_model():
    """Tiny XGBClassifier trained on 50 synthetic rows, 5 features."""
    model = xgb.XGBClassifier(
        n_estimators=5,
        max_depth=2,
        random_state=42,
        eval_metric="logloss",
    )
    X_df = pd.DataFrame(_X_TRAIN, columns=_FEATURE_NAMES)
    model.fit(X_df, _Y_TRAIN)
    return model


@pytest.fixture(scope="module")
def toy_features_df():
    """3-row DataFrame with 5 float columns matching the toy model."""
    data = {
        "feat_a": [0.10, 0.85, 0.45],
        "feat_b": [0.90, 0.05, 0.50],
        "feat_c": [0.20, 0.70, 0.30],
        "feat_d": [0.60, 0.15, 0.80],
        "feat_e": [0.40, 0.95, 0.10],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_weights_config():
    """Config dict with equal weights and default risk thresholds."""
    return {
        "m1_cost_overruns": 0.20,
        "m2_delays": 0.20,
        "m3_comptroller": 0.20,
        "m4_fines": 0.20,
        "iric": 0.20,
        "risk_thresholds": {
            "very_low":  [0.00, 0.20],
            "low":       [0.20, 0.40],
            "medium":    [0.40, 0.60],
            "high":      [0.60, 0.80],
            "very_high": [0.80, 1.00],
        },
    }


# =============================================================================
# SHAP tests (EXPL-01, EXPL-02)
# =============================================================================


def test_extract_shap_top_n_returns_n_entries(toy_xgb_model, toy_features_df):
    """With 5 features, n=3 returns exactly 3 entries per sample."""
    result = extract_shap_top_n(toy_xgb_model, toy_features_df, _FEATURE_NAMES, n=3)

    assert len(result) == len(toy_features_df), "One inner list per sample"
    for sample_entries in result:
        assert len(sample_entries) == 3, (
            f"Expected 3 entries per sample, got {len(sample_entries)}"
        )


def test_extract_shap_top_n_returns_all_if_n_exceeds_features(toy_xgb_model, toy_features_df):
    """n=10 with only 5 features returns 5 entries (not 10, not error)."""
    result = extract_shap_top_n(toy_xgb_model, toy_features_df, _FEATURE_NAMES, n=10)

    for sample_entries in result:
        assert len(sample_entries) == 5, (
            f"Expected 5 entries (= n_features) when n > n_features, got {len(sample_entries)}"
        )


def test_extract_shap_top_n_sorted_by_abs_value(toy_xgb_model, toy_features_df):
    """Entries within each sample are in descending |shap_value| order."""
    result = extract_shap_top_n(toy_xgb_model, toy_features_df, _FEATURE_NAMES, n=5)

    for sample_idx, sample_entries in enumerate(result):
        abs_values = [abs(e["shap_value"]) for e in sample_entries]
        assert abs_values == sorted(abs_values, reverse=True), (
            f"Sample {sample_idx}: entries not sorted by |shap_value| descending: {abs_values}"
        )


def test_shap_direction_positive_is_risk_increasing(toy_xgb_model, toy_features_df):
    """Any entry with positive shap_value has direction='risk_increasing'."""
    result = extract_shap_top_n(toy_xgb_model, toy_features_df, _FEATURE_NAMES, n=5)

    for sample_entries in result:
        for entry in sample_entries:
            if entry["shap_value"] > 0:
                assert entry["direction"] == "risk_increasing", (
                    f"Positive shap_value {entry['shap_value']} should be 'risk_increasing', "
                    f"got {entry['direction']!r}"
                )


def test_shap_direction_negative_is_risk_reducing(toy_xgb_model, toy_features_df):
    """Any entry with negative shap_value has direction='risk_reducing'."""
    result = extract_shap_top_n(toy_xgb_model, toy_features_df, _FEATURE_NAMES, n=5)

    for sample_entries in result:
        for entry in sample_entries:
            if entry["shap_value"] < 0:
                assert entry["direction"] == "risk_reducing", (
                    f"Negative shap_value {entry['shap_value']} should be 'risk_reducing', "
                    f"got {entry['direction']!r}"
                )


def test_shap_entry_has_required_keys(toy_xgb_model, toy_features_df):
    """Each entry dict contains exactly the 4 required keys."""
    required = {"feature", "shap_value", "direction", "original_value"}
    result = extract_shap_top_n(toy_xgb_model, toy_features_df, _FEATURE_NAMES, n=5)

    for sample_idx, sample_entries in enumerate(result):
        for entry in sample_entries:
            assert set(entry.keys()) == required, (
                f"Sample {sample_idx}: entry keys {set(entry.keys())} != {required}"
            )


def test_shap_values_are_rounded_to_6dp(toy_xgb_model, toy_features_df):
    """shap_value has at most 6 decimal places."""
    result = extract_shap_top_n(toy_xgb_model, toy_features_df, _FEATURE_NAMES, n=5)

    for sample_entries in result:
        for entry in sample_entries:
            val = entry["shap_value"]
            # Round-trip: round to 6 dp should not change the value
            assert round(val, 6) == val, (
                f"shap_value {val!r} has more than 6 decimal places"
            )


def test_json_serializable_shap_output(toy_xgb_model, toy_features_df):
    """json.dumps() on the full SHAP output succeeds — no numpy types leak."""
    result = extract_shap_top_n(toy_xgb_model, toy_features_df, _FEATURE_NAMES, n=5)

    try:
        serialized = json.dumps(result)
    except TypeError as exc:
        pytest.fail(f"SHAP output contains non-JSON-serialisable types: {exc}")

    # Sanity check: can round-trip
    recovered = json.loads(serialized)
    assert len(recovered) == len(result), "Round-trip length mismatch"


# =============================================================================
# CRI tests (EXPL-03, EXPL-04, EXPL-05)
# =============================================================================


def test_compute_cri_equal_weights_equal_inputs(sample_weights_config):
    """5 inputs all 0.5 with equal weights → CRI = 0.5."""
    cri = compute_cri(0.5, 0.5, 0.5, 0.5, 0.5, weights=sample_weights_config)
    assert abs(cri - 0.5) < 1e-6, f"Expected 0.5, got {cri}"


def test_compute_cri_custom_weights():
    """Custom unequal weights produce the manually computed expected CRI."""
    # weights: m1=0.4, m2=0.1, m3=0.1, m4=0.1, iric=0.3
    # inputs:  p_m1=0.8, p_m2=0.2, p_m3=0.2, p_m4=0.2, iric=0.6
    # CRI = 0.4*0.8 + 0.1*0.2 + 0.1*0.2 + 0.1*0.2 + 0.3*0.6
    #     = 0.32   + 0.02   + 0.02   + 0.02   + 0.18
    #     = 0.56
    custom_weights = {
        "m1_cost_overruns": 0.4,
        "m2_delays": 0.1,
        "m3_comptroller": 0.1,
        "m4_fines": 0.1,
        "iric": 0.3,
    }
    cri = compute_cri(0.8, 0.2, 0.2, 0.2, 0.6, weights=custom_weights)
    expected = 0.4 * 0.8 + 0.1 * 0.2 + 0.1 * 0.2 + 0.1 * 0.2 + 0.3 * 0.6
    assert abs(cri - expected) < 1e-6, f"Expected {expected}, got {cri}"


def test_classify_risk_level_all_boundaries(sample_weights_config):
    """Verify correct risk level across all band boundaries."""
    thresholds = sample_weights_config["risk_thresholds"]

    cases = [
        (0.00, "Very Low"),
        (0.199, "Very Low"),
        (0.20, "Low"),
        (0.399, "Low"),
        (0.40, "Medium"),
        (0.599, "Medium"),
        (0.60, "High"),
        (0.799, "High"),
        (0.80, "Very High"),
        (0.999, "Very High"),
        (1.0, "Very High"),
    ]

    for score, expected in cases:
        result = classify_risk_level(score, thresholds=thresholds)
        assert result == expected, (
            f"classify_risk_level({score}) = {result!r}, expected {expected!r}"
        )


def test_classify_very_high_includes_exactly_1(sample_weights_config):
    """classify_risk_level(1.0) → 'Very High' (upper boundary included)."""
    thresholds = sample_weights_config["risk_thresholds"]
    assert classify_risk_level(1.0, thresholds=thresholds) == "Very High"


def test_cri_config_loads_from_file():
    """load_cri_config() returns dict with all 5 weight keys + risk_thresholds."""
    config = load_cri_config()

    required_weight_keys = {
        "m1_cost_overruns",
        "m2_delays",
        "m3_comptroller",
        "m4_fines",
        "iric",
    }
    assert required_weight_keys.issubset(config.keys()), (
        f"Config missing weight keys: {required_weight_keys - set(config.keys())}"
    )
    assert "risk_thresholds" in config, "Config missing 'risk_thresholds' key"

    # Thresholds should have exactly 5 bands
    bands = {"very_low", "low", "medium", "high", "very_high"}
    assert bands == set(config["risk_thresholds"].keys()), (
        f"risk_thresholds has unexpected keys: {set(config['risk_thresholds'].keys())}"
    )


def test_cri_config_custom_weights_changes_output(tmp_path):
    """Custom model_weights.json with different weights changes compute_cri output."""
    # Write a custom weights file with very different weights
    custom_config = {
        "m1_cost_overruns": 0.90,
        "m2_delays": 0.025,
        "m3_comptroller": 0.025,
        "m4_fines": 0.025,
        "iric": 0.025,
        "risk_thresholds": {
            "very_low":  [0.00, 0.20],
            "low":       [0.20, 0.40],
            "medium":    [0.40, 0.60],
            "high":      [0.60, 0.80],
            "very_high": [0.80, 1.00],
        },
    }
    custom_path = tmp_path / "custom_weights.json"
    custom_path.write_text(json.dumps(custom_config), encoding="utf-8")

    # Default weights: CRI with inputs (0.9, 0.1, 0.1, 0.1, 0.1)
    default_config = load_cri_config()
    default_cri = compute_cri(0.9, 0.1, 0.1, 0.1, 0.1, weights=default_config)

    # Custom weights: same inputs, but M1 weight is 0.90
    loaded_custom = load_cri_config(weights_path=custom_path)
    custom_cri = compute_cri(0.9, 0.1, 0.1, 0.1, 0.1, weights=loaded_custom)

    assert default_cri != custom_cri, (
        f"Expected different CRI for different weights, but both are {default_cri}"
    )
    # Custom: 0.90*0.9 + 4*0.025*0.1 = 0.81 + 0.01 = 0.82
    expected_custom = 0.90 * 0.9 + 4 * 0.025 * 0.1
    assert abs(custom_cri - expected_custom) < 1e-6, (
        f"Expected custom CRI {expected_custom}, got {custom_cri}"
    )
