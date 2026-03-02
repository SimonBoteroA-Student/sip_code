"""SHAP feature attribution for SIP XGBoost models.

Uses TreeSHAP (shap.TreeExplainer) to extract per-feature attributions for
each prediction. The top-N features by |SHAP value| are extracted per sample
and saved as Parquet artifacts.

Public API:
    extract_shap_top_n  — return top-N SHAP entries per sample
    save_shap_artifact  — flatten and persist SHAP rows to Parquet
"""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import shap

if TYPE_CHECKING:
    pass


def _apply_shap_xgboost_compat_patch() -> None:
    """Patch SHAP's internal float() to handle XGBoost >=3.x bracket notation.

    XGBoost 3.x serialises base_score in UBJSON as a single-element array
    string like '[2.5E-1]'.  SHAP <=0.49.x calls float(base_score_str)
    which raises ValueError for that format.

    Fix: inject a lenient float into shap.explainers._tree namespace that
    strips leading/trailing brackets before converting.

    This patch is applied once at module import time and is idempotent.
    """
    import shap.explainers._tree as _tree_mod

    if getattr(_tree_mod, "_xgb_compat_patched", False):
        return  # already patched

    _orig_float = builtins.float

    def _lenient_float(val):
        if isinstance(val, str):
            s = val.strip()
            if s.startswith("[") and s.endswith("]"):
                s = s[1:-1].strip()
            return _orig_float(s)
        return _orig_float(val)

    _tree_mod.float = _lenient_float
    _tree_mod._xgb_compat_patched = True


_apply_shap_xgboost_compat_patch()


def extract_shap_top_n(
    model,
    X_df: pd.DataFrame,
    feature_names: list[str],
    n: int = 10,
) -> list[list[dict]]:
    """Compute TreeSHAP values and return the top-N features per sample.

    Args:
        model: A trained XGBClassifier (or any tree model compatible with
            shap.TreeExplainer).
        X_df: DataFrame of shape (n_samples, n_features) — the input rows to
            explain. Column order must match feature_names.
        feature_names: Ordered list of feature names corresponding to X_df
            columns.
        n: Number of top features to return per sample (by |shap_value|).
            If n exceeds the number of features, all features are returned.

    Returns:
        A list of lists — one inner list per sample in X_df. Each inner list
        contains up to n dicts:
            {
                "feature": str,
                "shap_value": float (rounded to 6 dp),
                "direction": "risk_increasing" | "risk_reducing",
                "original_value": float | int | str,
            }
        Entries are ordered by descending |shap_value| within each sample.
    """
    explainer = shap.TreeExplainer(model)
    raw = explainer.shap_values(X_df)

    # XGBoost binary classifier: shap_values returns array of shape
    # (n_samples, n_features). Guard against the list-of-two case
    # (some SHAP versions return [neg_class, pos_class]).
    if isinstance(raw, list):
        shap_matrix = raw[1]  # positive class values
    else:
        shap_matrix = raw

    n_features = shap_matrix.shape[1]
    actual_n = min(n, n_features)

    results: list[list[dict]] = []

    for row_idx in range(shap_matrix.shape[0]):
        shap_row = shap_matrix[row_idx]  # shape (n_features,)
        # Descending sort by absolute value
        top_indices = np.argsort(np.abs(shap_row))[::-1][:actual_n]

        entries: list[dict] = []
        for col_idx in top_indices:
            val = float(shap_row[col_idx])
            orig = X_df.iloc[row_idx, col_idx]
            # Convert numpy scalars to Python-native for JSON safety
            if isinstance(orig, (np.integer,)):
                orig = int(orig)
            elif isinstance(orig, (np.floating,)):
                orig = float(orig)
            elif isinstance(orig, (np.bool_,)):
                orig = bool(orig)

            entries.append(
                {
                    "feature": str(feature_names[col_idx]),
                    "shap_value": round(val, 6),
                    "direction": "risk_increasing" if val > 0 else "risk_reducing",
                    "original_value": orig,
                }
            )
        results.append(entries)

    return results


def save_shap_artifact(
    shap_rows: list[list[dict]],
    contract_ids: list[str],
    model_id: str,
    output_dir: Path | None = None,
) -> Path:
    """Flatten SHAP top-N rows and write them to a Parquet artifact.

    Output schema (one row per contract × rank):
        id_contrato   — contract identifier
        rank          — 1-based rank within the sample (1 = highest |shap_value|)
        feature       — feature name
        shap_value    — SHAP value (float, rounded to 6 dp)
        direction     — "risk_increasing" or "risk_reducing"
        original_value — feature value in the contract row

    Args:
        shap_rows: Output of extract_shap_top_n — list of lists of dicts.
        contract_ids: List of id_contrato strings, same length as shap_rows.
        model_id: Model identifier string (e.g. "M1"). Used in filename.
        output_dir: Directory to write ``shap_{model_id}.parquet``. Defaults
            to ``get_settings().artifacts_shap_dir``.

    Returns:
        Absolute Path to the written Parquet file.
    """
    if output_dir is None:
        from sip_engine.config import get_settings
        output_dir = get_settings().artifacts_shap_dir

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for sample_idx, (contract_id, entries) in enumerate(zip(contract_ids, shap_rows)):
        for rank_zero, entry in enumerate(entries):
            rows.append(
                {
                    "id_contrato": str(contract_id),
                    "rank": rank_zero + 1,
                    "feature": entry["feature"],
                    "shap_value": entry["shap_value"],
                    "direction": entry["direction"],
                    "original_value": float(entry["original_value"])
                    if isinstance(entry["original_value"], (int, float))
                    else str(entry["original_value"]),
                }
            )

    df = pd.DataFrame(
        rows,
        columns=["id_contrato", "rank", "feature", "shap_value", "direction", "original_value"],
    )
    table = pa.Table.from_pandas(df, preserve_index=False)
    out_path = output_dir / f"shap_{model_id}.parquet"
    pq.write_table(table, out_path)
    return out_path
