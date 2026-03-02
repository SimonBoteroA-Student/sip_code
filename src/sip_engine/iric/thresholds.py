"""IRIC threshold calibration and lazy loading.

Computes percentile-based thresholds (P1, P5, P95, P99) segmented by
tipo_contrato for use in the IRIC component firing rules. Rare contract
types (< min_group_size) are merged into 'Otro' before computing percentiles.

IRIC-06, IRIC-07, IRIC-08

Usage:
    from sip_engine.iric.thresholds import (
        calibrate_iric_thresholds,
        save_iric_thresholds,
        load_iric_thresholds,
        reset_iric_thresholds_cache,
        get_threshold,
    )

Phase 6 concern: calibrate_iric_thresholds accepts ANY DataFrame (no hardcoded
data loading). Phase 7 calls this function with training-only data to prevent
test-set leakage (IRIC-08).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sip_engine.config import get_settings

logger = logging.getLogger(__name__)

# ============================================================
# VigIA hardcoded fallback defaults
# These are used when a variable/percentile combo is not present
# in the thresholds dict (not in Otro either).
# Source: VigIA Bogota calibration values.
# ============================================================

_VIGIA_DEFAULTS: dict[str, dict[str, float]] = {
    "dias_publicidad": {"p99": 14},
    "dias_decision": {"p95": 43},
    "num_contratos_previos_nacional": {"p95": 3},
    "valor_contrato": {"p99": 500_000_000},
}

# ============================================================
# Calibration variables (what percentiles are computed for)
# ============================================================

_CALIBRATION_VARIABLES: list[str] = [
    "num_contratos_previos_nacional",
    "dias_publicidad",
    "dias_decision",
    "valor_contrato",
]

# Module-level cache (lazy-loaded)
_thresholds_cache: dict | None = None


# ============================================================
# Calibration
# ============================================================


def calibrate_iric_thresholds(
    df: pd.DataFrame,
    min_group_size: int = 30,
) -> dict:
    """Compute percentile thresholds segmented by tipo_contrato.

    Contract types with fewer than min_group_size rows are merged into 'Otro'
    before computing percentiles. This ensures stable estimates for rare types.

    Accepts ANY DataFrame — does NOT hardcode loading the full dataset.
    Phase 7 should call this with training-set-only data to prevent test-set
    leakage (IRIC-08).

    Args:
        df: DataFrame with columns [tipo_contrato, num_contratos_previos_nacional,
            dias_publicidad, dias_decision, valor_contrato].
        min_group_size: Minimum observations per tipo_contrato before merging
            into 'Otro'. Default: 30.

    Returns:
        Dict with structure:
        {
            "tipo_contrato": {
                "Prestacion de servicios": {
                    "num_contratos_previos_nacional": {"p1": ..., "p5": ..., "p95": ..., "p99": ...},
                    ...
                },
                "Otro": { ... },
            },
            "calibration_date": ISO8601,
            "n_contracts": int,
            "min_group_size": int,
        }
    """
    # Count rows per tipo_contrato
    type_counts = df["tipo_contrato"].value_counts()

    # Determine which types are rare (below threshold)
    rare_types = set(type_counts[type_counts < min_group_size].index)
    common_types = set(type_counts[type_counts >= min_group_size].index)

    # Build a mapping for the merged DataFrame
    def _remap_tipo(tipo: str) -> str:
        if tipo in common_types:
            return tipo
        return "Otro"

    df_mapped = df.copy()
    df_mapped["_tipo_group"] = df_mapped["tipo_contrato"].map(_remap_tipo)

    # Compute percentiles per group
    tipo_contrato_thresholds: dict[str, dict[str, dict[str, float]]] = {}

    for group_name, group_df in df_mapped.groupby("_tipo_group"):
        group_thresholds: dict[str, dict[str, float]] = {}

        for var in _CALIBRATION_VARIABLES:
            if var not in group_df.columns:
                continue

            values = group_df[var].values.astype(float)

            # Use nanpercentile to handle NaN values gracefully
            p1 = float(np.nanpercentile(values, 1))
            p5 = float(np.nanpercentile(values, 5))
            p95 = float(np.nanpercentile(values, 95))
            p99 = float(np.nanpercentile(values, 99))

            group_thresholds[var] = {"p1": p1, "p5": p5, "p95": p95, "p99": p99}

        tipo_contrato_thresholds[group_name] = group_thresholds

    result: dict[str, Any] = {
        "tipo_contrato": tipo_contrato_thresholds,
        "calibration_date": datetime.now(tz=timezone.utc).isoformat(),
        "n_contracts": len(df),
        "min_group_size": min_group_size,
    }

    logger.info(
        "IRIC thresholds calibrated: %d tipo_contrato groups (%d rare types merged into Otro), "
        "%d total contracts",
        len(tipo_contrato_thresholds),
        len(rare_types),
        len(df),
    )

    return result


# ============================================================
# Save / Load
# ============================================================


def save_iric_thresholds(
    thresholds: dict,
    path: Path | None = None,
) -> Path:
    """Write thresholds dict to JSON.

    Args:
        thresholds: Dict returned by calibrate_iric_thresholds().
        path: Destination path. Defaults to settings.iric_thresholds_path.

    Returns:
        Path to the written JSON file.
    """
    if path is None:
        settings = get_settings()
        path = settings.iric_thresholds_path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(thresholds, f, indent=2, ensure_ascii=False)

    logger.info("IRIC thresholds saved to %s", path)
    return path


def load_iric_thresholds(path: Path | None = None) -> dict:
    """Load IRIC thresholds from JSON with module-level caching.

    Same lazy-load pattern as rcac_lookup.py and provider_history.py.
    Use reset_iric_thresholds_cache() to force a re-read (e.g., in tests).

    Args:
        path: JSON file path. Defaults to settings.iric_thresholds_path.

    Returns:
        Thresholds dict (cached after first load).

    Raises:
        FileNotFoundError: If the thresholds file does not exist.
    """
    global _thresholds_cache

    if _thresholds_cache is not None:
        return _thresholds_cache

    if path is None:
        settings = get_settings()
        path = settings.iric_thresholds_path

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"IRIC thresholds not found at {path}. "
            "Run calibrate_iric_thresholds() and save_iric_thresholds() first, "
            "or run: python -m sip_engine build-iric"
        )

    with path.open("r", encoding="utf-8") as f:
        _thresholds_cache = json.load(f)

    logger.info("IRIC thresholds loaded from %s", path)
    return _thresholds_cache


def reset_iric_thresholds_cache() -> None:
    """Reset the module-level thresholds cache.

    Call this in tests to force a re-read from disk, or to ensure test
    isolation when different threshold files are used.
    """
    global _thresholds_cache
    _thresholds_cache = None


# ============================================================
# Threshold lookup
# ============================================================


def get_threshold(
    thresholds: dict,
    tipo_contrato: str,
    variable: str,
    percentile: str,
) -> float | None:
    """Look up a specific threshold value with fallback chain.

    Fallback chain:
    1. Exact tipo_contrato match in thresholds["tipo_contrato"]
    2. "Otro" fallback within the same thresholds dict
    3. VigIA hardcoded defaults (for known variables)
    4. None (should not happen for known variables/percentiles)

    Args:
        thresholds: Loaded thresholds dict (from load_iric_thresholds()).
        tipo_contrato: Contract type string (as-is from source data).
        variable: One of the 4 calibration variables.
        percentile: One of "p1", "p5", "p95", "p99".

    Returns:
        Threshold value as float, or None if not found anywhere.
    """
    tipo_section = thresholds.get("tipo_contrato", {})

    # 1. Exact match
    if tipo_contrato in tipo_section:
        var_data = tipo_section[tipo_contrato].get(variable, {})
        if percentile in var_data:
            return float(var_data[percentile])

    # 2. Otro fallback
    if "Otro" in tipo_section:
        var_data = tipo_section["Otro"].get(variable, {})
        if percentile in var_data:
            return float(var_data[percentile])

    # 3. VigIA hardcoded defaults
    if variable in _VIGIA_DEFAULTS and percentile in _VIGIA_DEFAULTS[variable]:
        return float(_VIGIA_DEFAULTS[variable][percentile])

    # 4. Not found
    return None
