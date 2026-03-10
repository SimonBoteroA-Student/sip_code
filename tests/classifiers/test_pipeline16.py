"""Tests for Phase 16 behaviors: IRIC feature expansion and pipeline integration.

These tests define the behavioral contracts for Phase 16. They are written
test-first: all 7 tests FAIL before Wave 1 implementation and PASS after.

Coverage:
- FEATURE_COLUMNS count expansion from 34 → 45
- All 11 IRIC binary component names present in FEATURE_COLUMNS
- build_features() loads IRIC columns via pd.read_parquet (not inline compute)
- build_features() auto-triggers build_iric() when iric_scores.parquet is missing
- compute_features() injects all 15 IRIC columns into its return dict
- Graceful degradation: build_features() warns (not raises) when parquet absent
- Graceful degradation: compute_features() warns (not raises) when thresholds absent
"""

from __future__ import annotations

import inspect

import pytest

IRIC_COMPONENTS = [
    "ausencia_proceso",
    "contratacion_directa",
    "datos_faltantes",
    "historial_proveedor_alto",
    "periodo_decision_extremo",
    "periodo_publicidad_extremo",
    "proveedor_multiproposito",
    "proveedor_retrasos_previos",
    "proveedor_sobrecostos_previos",
    "regimen_especial",
    "unico_proponente",
]

IRIC_AGGREGATES = [
    "iric_anomalias",
    "iric_competencia",
    "iric_score",
    "iric_transparencia",
]

ALL_IRIC_COLUMNS = IRIC_AGGREGATES + IRIC_COMPONENTS


# ---------------------------------------------------------------------------
# Feature schema tests
# ---------------------------------------------------------------------------


def test_feature_columns_count():
    """FEATURE_COLUMNS must have exactly 45 entries (30 Cat A/B/C + 15 Cat D IRIC)."""
    from sip_engine.classifiers.features.pipeline import FEATURE_COLUMNS

    assert len(FEATURE_COLUMNS) == 45, (
        f"Expected 45 FEATURE_COLUMNS (Phase 16 expansion: 30 A/B/C + 15 D), "
        f"got {len(FEATURE_COLUMNS)}"
    )


def test_feature_columns_has_iric_components():
    """All 11 binary IRIC component names must be present in FEATURE_COLUMNS."""
    from sip_engine.classifiers.features.pipeline import FEATURE_COLUMNS

    missing = [c for c in IRIC_COMPONENTS if c not in FEATURE_COLUMNS]
    assert not missing, (
        f"Missing IRIC binary components in FEATURE_COLUMNS: {missing}\n"
        f"All 11 components must be added to Cat D in Phase 16."
    )


# ---------------------------------------------------------------------------
# build_features() structural tests
# ---------------------------------------------------------------------------


def test_build_features_merges_iric_parquet():
    """build_features() must load IRIC columns via pd.read_parquet, not inline compute."""
    from sip_engine.classifiers.features.pipeline import build_features

    source = inspect.getsource(build_features)

    assert "read_parquet" in source, (
        "build_features() must use pd.read_parquet() to merge IRIC columns from "
        "iric_scores.parquet instead of computing them inline."
    )
    assert "iric_scores" in source, (
        "build_features() must reference iric_scores path for the IRIC parquet merge."
    )
    assert "_compute_iric" not in source, (
        "build_features() must NOT call _compute_iric() inline — "
        "all IRIC columns must come from the iric_scores.parquet merge."
    )


def test_build_features_auto_triggers_iric():
    """build_features() must auto-trigger build_iric() when iric_scores.parquet is missing."""
    from sip_engine.classifiers.features.pipeline import build_features

    source = inspect.getsource(build_features)

    assert "build_iric" in source, (
        "build_features() must call build_iric() (or _build_iric()) when "
        "iric_scores.parquet does not exist — auto-trigger pattern required."
    )


# ---------------------------------------------------------------------------
# compute_features() structural test
# ---------------------------------------------------------------------------


def test_compute_features_has_iric_columns():
    """compute_features() source must reference all 11 IRIC binary components."""
    from sip_engine.classifiers.features.pipeline import compute_features

    source = inspect.getsource(compute_features)
    missing = [c for c in IRIC_COMPONENTS if c not in source]
    assert not missing, (
        f"compute_features() must inject all 11 IRIC binary components. "
        f"Missing in source: {missing}"
    )


# ---------------------------------------------------------------------------
# Graceful degradation tests
# ---------------------------------------------------------------------------


def test_build_features_iric_missing_graceful():
    """build_features() must warn (not raise) when iric_scores.parquet is unavailable."""
    from sip_engine.classifiers.features.pipeline import build_features

    source = inspect.getsource(build_features)

    assert "logger.warning" in source, (
        "build_features() must emit logger.warning() when iric_scores.parquet "
        "is unavailable — no hard failure allowed (graceful degradation)."
    )
    assert "_compute_iric" not in source, (
        "build_features() must not fall back to inline _compute_iric() — "
        "NaN fill via the post-loop FEATURE_COLUMNS guard is the correct degradation path."
    )


def test_compute_features_iric_missing_graceful():
    """compute_features() must fill all 15 IRIC columns with NaN on FileNotFoundError."""
    from sip_engine.classifiers.features.pipeline import compute_features

    source = inspect.getsource(compute_features)

    assert "FileNotFoundError" in source, (
        "compute_features() must catch FileNotFoundError for missing IRIC thresholds."
    )
    assert "logger.warning" in source, (
        "compute_features() must emit logger.warning() when IRIC thresholds are missing."
    )
    for col in ALL_IRIC_COLUMNS:
        assert col in source, (
            f"compute_features() must include '{col}' in its IRIC fallback NaN dict "
            f"(inside the FileNotFoundError except block)."
        )
