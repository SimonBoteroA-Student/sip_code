"""Per-contract analysis entry point for SIP — compose features, models, SHAP, and CRI.

`analyze_contract()` is the single function a future v2 REST API
(``POST /api/v1/analyze``) would call.  It integrates all prior pipeline
stages — feature engineering, XGBoost inference, TreeSHAP attribution, and
CRI scoring — into one deterministic JSON-serialisable dict.

`serialize_to_json()` guarantees byte-identical output for the same dict by
using sorted keys and pre-rounded floats.

Public API:
    analyze_contract  — full per-contract analysis pipeline
    serialize_to_json — deterministic JSON serialisation
"""

from __future__ import annotations

import datetime
import json
import logging
from datetime import timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

# Import compute_features at module level so it can be monkeypatched in tests.
# This is safe — features.pipeline does not import from explainability.
from sip_engine.classifiers.features.pipeline import compute_features  # noqa: E402

logger = logging.getLogger(__name__)

# Model IDs to load in order M1 → M4
_MODEL_IDS: list[str] = ["M1", "M2", "M3", "M4"]


# =============================================================================
# Private helpers
# =============================================================================


def _serialize_value(v: Any) -> Any:
    """Convert a value to a JSON-safe Python native type.

    - numpy integer → int
    - numpy floating → float (rounded to 6 dp)
    - numpy bool_ → bool
    - Python float → rounded to 6 dp
    - str, int, bool, None → returned as-is
    - Anything else → str(v)
    """
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        val = float(v)
        if val != val:  # NaN
            return None
        return round(val, 6)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, float):
        if v != v:  # NaN
            return None
        return round(v, 6)
    if isinstance(v, (int, str, bool)) or v is None:
        return v
    # Fallback for unexpected types
    return str(v)


def _load_model_artifacts(
    models_dir: Path,
    model_id: str,
) -> tuple[Any, list[str], str] | None:
    """Load model.pkl and feature_registry.json for one model.

    Returns:
        (model, feature_columns, version_str) or None if any artifact is missing.
    """
    model_dir = models_dir / model_id
    model_pkl = model_dir / "model.pkl"
    registry_path = model_dir / "feature_registry.json"

    if not model_pkl.exists():
        logger.warning("model.pkl not found for %s at %s — skipping", model_id, model_pkl)
        return None
    if not registry_path.exists():
        logger.warning(
            "feature_registry.json not found for %s at %s — skipping", model_id, registry_path
        )
        return None

    model = joblib.load(model_pkl)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    feature_columns: list[str] = registry["feature_columns"]

    # Extract version identifier — prefer training_date from feature_registry
    version = registry.get("training_date", "unknown")

    # Fall back to training_report.json if no training_date in registry
    if version == "unknown":
        report_path = model_dir / "training_report.json"
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                version = report.get("training_date", "unknown")
            except Exception:
                pass

    return model, feature_columns, str(version)


# =============================================================================
# Public API
# =============================================================================


def analyze_contract(
    contract_row: dict,
    as_of_date: datetime.date,
    procesos_data: dict | None = None,
    proveedor_fecha_creacion: datetime.date | None = None,
    num_actividades: int = 0,
    iric_thresholds: dict | None = None,
    bid_values: list[float] | None = None,
    models_dir: Path | None = None,
    timestamp: str | None = None,
) -> dict:
    """Run the full per-contract analysis pipeline.

    Integrates feature engineering, model inference, TreeSHAP attribution, and
    CRI computation into a single deterministic JSON-serialisable dict.

    The first 7 parameters mirror ``compute_features()`` exactly — this is the
    train-serve parity contract (FEAT-07).

    Args:
        contract_row: Raw contratos column values (dict).
        as_of_date: Contract signing date — used as temporal cutoff for
            provider history lookup.
        procesos_data: Procesos row dict for this contract's process, or None.
        proveedor_fecha_creacion: Provider registration date, or None.
        num_actividades: Count of distinct UNSPSC segments for this provider.
        iric_thresholds: Pre-loaded IRIC thresholds dict, or None to load from
            disk (same semantics as compute_features).
        bid_values: Optional bid amounts for this process.
        models_dir: Directory containing M1–M4 subdirs with model.pkl and
            feature_registry.json.  Defaults to
            ``get_settings().artifacts_models_dir``.
        timestamp: ISO-8601 timestamp string to embed in metadata. Defaults to
            the current UTC time.  **Pass a frozen value for deterministic
            output** (the timestamp is the only non-deterministic element).

    Returns:
        Dict with the following top-level keys:
            - contract_id   (str)
            - cri           (dict: score, level, weights_used)
            - models        (dict keyed by model_id: probability, shap_top10)
            - iric_score    (float, 6 dp)
            - raw_features  (dict: all 34 feature values, JSON-safe)
            - metadata      (dict: model_versions, timestamp)
    """
    # ---- Resolve defaults ----
    if models_dir is None:
        from sip_engine.shared.config import get_settings
        models_dir = get_settings().artifacts_models_dir
    models_dir = Path(models_dir)

    if timestamp is None:
        timestamp = datetime.datetime.now(timezone.utc).isoformat()

    # ---- Step 1: Compute 34-feature vector ----
    feature_dict = compute_features(
        contract_row=contract_row,
        as_of_date=as_of_date,
        procesos_data=procesos_data,
        proveedor_fecha_creacion=proveedor_fecha_creacion,
        num_actividades=num_actividades,
        iric_thresholds=iric_thresholds,
        bid_values=bid_values,
    )

    # ---- Step 2: Load all models + compute per-model predictions + SHAP ----
    from sip_engine.classifiers.explainability.shap_explainer import extract_shap_top_n

    model_results: list[tuple[str, float, list[dict]]] = []
    model_versions: dict[str, str] = {}

    for model_id in _MODEL_IDS:
        artifacts = _load_model_artifacts(models_dir, model_id)
        if artifacts is None:
            logger.warning("Skipping %s — artifacts missing", model_id)
            continue

        model, feature_columns, version = artifacts
        model_versions[model_id] = version

        # Build single-row DataFrame in registry column order
        row_data = {col: feature_dict.get(col, float("nan")) for col in feature_columns}
        X_df = pd.DataFrame([row_data], columns=feature_columns)

        # Predict probability of positive class
        prob = float(model.predict_proba(X_df)[:, 1][0])
        prob = round(prob, 6)

        # Extract SHAP top-10 for this single row
        shap_result = extract_shap_top_n(model, X_df, feature_columns, n=10)
        shap_top10 = shap_result[0]  # Only one row

        model_results.append((model_id, prob, shap_top10))

    # ---- Step 3: Extract IRIC score from feature dict ----
    iric_raw = feature_dict.get("iric_score", 0.0)
    iric_val = float(iric_raw) if iric_raw == iric_raw else 0.0  # NaN → 0
    iric_score = round(iric_val, 6)

    # ---- Step 4: Compute CRI ----
    from sip_engine.classifiers.explainability.cri import load_cri_config, compute_cri, classify_risk_level

    config = load_cri_config()
    weights = {k: v for k, v in config.items() if k != "risk_thresholds"}

    # Build probability map for the 4 models (default to 0 if model missing)
    prob_map: dict[str, float] = {mid: 0.0 for mid in _MODEL_IDS}
    for mid, prob, _ in model_results:
        prob_map[mid] = prob

    cri_score = compute_cri(
        p_m1=prob_map["M1"],
        p_m2=prob_map["M2"],
        p_m3=prob_map["M3"],
        p_m4=prob_map["M4"],
        iric_score=iric_score,
        weights=weights,
    )
    risk_level = classify_risk_level(cri_score, thresholds=config.get("risk_thresholds"))

    # ---- Step 5: Resolve contract_id ----
    contract_id = str(
        contract_row.get("ID Contrato", contract_row.get("id_contrato", "unknown"))
    )

    # ---- Step 6: Build result dict ----
    result: dict = {
        "contract_id": contract_id,
        "cri": {
            "score": round(float(cri_score), 6),
            "level": risk_level,
            "weights_used": {k: float(v) for k, v in weights.items()},
        },
        "models": {
            mid: {
                "probability": round(float(prob), 6),
                "shap_top10": shap_entries,
            }
            for mid, prob, shap_entries in model_results
        },
        "iric_score": iric_score,
        "raw_features": {k: _serialize_value(v) for k, v in feature_dict.items()},
        "metadata": {
            "model_versions": model_versions,
            "timestamp": timestamp,
        },
    }

    return result


def serialize_to_json(result_dict: dict) -> str:
    """Serialise an analyze_contract result dict to a deterministic JSON string.

    Determinism is guaranteed by:
        - ``sort_keys=True`` — consistent key ordering at every nesting level
        - Pre-rounded floats (all floats already 6 dp in the result dict)
        - No separators kwarg — uses Python's default compact delimiters

    Args:
        result_dict: Output of ``analyze_contract()``.

    Returns:
        JSON string with sorted keys and no trailing whitespace.
    """
    return json.dumps(result_dict, sort_keys=True, ensure_ascii=False)
