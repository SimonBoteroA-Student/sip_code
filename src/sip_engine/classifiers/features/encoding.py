"""Categorical encoding with rare-category grouping (FEAT-10).

Threshold: categories appearing in < 0.1% of training observations are grouped
into "Other". Encoding uses alphabetical ordering for deterministic integer codes.
"Other" always gets code 0. Mappings serialized to encoding_mappings.json for
train-serve parity (FEAT-07).

Design:
    - build_encoding_mappings(df_train): compute + serialize mappings from training data only
    - apply_encoding(df, mappings): apply mappings to any DataFrame (train or inference)
    - load_encoding_mappings(): reload serialized mappings for inference

Usage:
    # Training time
    mappings = build_encoding_mappings(df_train)

    # Inference time
    mappings = load_encoding_mappings()
    df_encoded = apply_encoding(df_features, mappings)
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

from sip_engine.shared.config import get_settings

logger = logging.getLogger(__name__)

# ============================================================
# Constants
# ============================================================

CATEGORICAL_COLUMNS: list[str] = [
    "tipo_contrato_cat",
    "modalidad_contratacion_cat",
    "departamento_cat",
    "origen_recursos_cat",
    "unspsc_categoria",
]

RARE_THRESHOLD: float = 0.001  # 0.1% — categories below this frequency are "Other"


# ============================================================
# Public API
# ============================================================


def build_encoding_mappings(df_train: pd.DataFrame, force: bool = False) -> dict[str, dict[str, int]]:
    """Compute and serialize encoding mappings from training data.

    For each categorical column in CATEGORICAL_COLUMNS:
    1. Count value frequencies (proportional to total row count)
    2. Group values strictly below RARE_THRESHOLD into "Other"
    3. Sort remaining values alphabetically
    4. Assign integer codes: "Other"=0, then alphabetical 1, 2, 3...
    5. Write to encoding_mappings.json (overwriting if force=True or if not exists)

    Args:
        df_train: Training DataFrame. Must contain all CATEGORICAL_COLUMNS.
        force: If True, always recompute even if JSON already exists.

    Returns:
        Dict of {column_name: {category_str: int_code}} for all categorical columns.
    """
    settings = get_settings()
    json_path = settings.encoding_mappings_path

    if json_path.exists() and not force:
        logger.info("Encoding mappings already exist at %s — skipping build", json_path)
        return load_encoding_mappings()

    n_rows = len(df_train)
    mappings: dict[str, dict[str, int]] = {}

    for col in CATEGORICAL_COLUMNS:
        if col not in df_train.columns:
            logger.warning("Column %s not found in training DataFrame — skipping", col)
            mappings[col] = {"Other": 0}
            continue

        # Compute frequency of each value (convert everything to str for consistency)
        series = df_train[col].dropna().astype(str)
        value_counts = series.value_counts()

        # Determine which values are frequent enough (strictly > RARE_THRESHOLD)
        # Note: "< 0.1%" means freq < threshold, so freq <= threshold → rare
        # Boundary: exactly 0.1% (freq == threshold) is grouped into Other
        if n_rows > 0:
            freq_ratios = value_counts / n_rows
            frequent_values = sorted(
                [v for v, ratio in freq_ratios.items() if ratio > RARE_THRESHOLD]
            )
        else:
            frequent_values = []

        # Build mapping: Other=0, then alphabetical 1, 2, 3...
        col_mapping: dict[str, int] = {"Other": 0}
        for code, category in enumerate(frequent_values, start=1):
            col_mapping[category] = code

        mappings[col] = col_mapping
        logger.debug(
            "Column %s: %d unique values → %d frequent + Other",
            col,
            len(value_counts),
            len(frequent_values),
        )

    # Serialize to JSON
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)

    logger.info("Encoding mappings written to %s", json_path)
    return mappings


def load_encoding_mappings() -> dict[str, dict[str, int]]:
    """Load encoding mappings from artifacts/features/encoding_mappings.json.

    Returns:
        Dict of {column_name: {category_str: int_code}}.

    Raises:
        FileNotFoundError: If encoding_mappings.json has not been built yet.
    """
    settings = get_settings()
    json_path = settings.encoding_mappings_path

    if not json_path.exists():
        raise FileNotFoundError(
            f"Encoding mappings not found at {json_path}. "
            "Run build_encoding_mappings() first."
        )

    with json_path.open("r", encoding="utf-8") as f:
        mappings = json.load(f)

    logger.info("Encoding mappings loaded from %s", json_path)
    return mappings


def apply_encoding(df: pd.DataFrame, mappings: dict[str, dict[str, int]]) -> pd.DataFrame:
    """Apply label encoding to categorical columns using pre-computed mappings.

    Unseen categories at inference time map to "Other" (code 0).
    NaN values remain NaN after encoding.

    Args:
        df: DataFrame with categorical columns to encode. Columns not in mappings
            are passed through unchanged.
        mappings: Mapping dict from build_encoding_mappings() or load_encoding_mappings().

    Returns:
        DataFrame with categorical columns replaced by integer codes.
        NaN values in categorical columns remain NaN (nullable float/Int64).
    """
    df_out = df.copy()

    for col, col_mapping in mappings.items():
        if col not in df_out.columns:
            continue

        other_code = col_mapping.get("Other", 0)

        def _encode_value(val: Any) -> Any:
            """Map a single value to its integer code."""
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            # Convert to string for consistent lookup (handles int categories)
            val_str = str(val)
            return col_mapping.get(val_str, other_code)

        df_out[col] = df_out[col].apply(_encode_value)

    return df_out
