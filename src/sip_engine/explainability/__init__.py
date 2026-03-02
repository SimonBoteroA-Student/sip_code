"""Explainability package for SIP — SHAP feature attribution and CRI computation.

Provides TreeSHAP-based feature explanations for each XGBoost model and the
Composite Risk Index (CRI) that aggregates all model predictions into a single
configurable risk score with human-readable risk levels.

``analyze_contract()`` is the top-level entry point that composes all stages
into a single deterministic JSON-serialisable dict.
"""

from sip_engine.explainability.shap_explainer import extract_shap_top_n, save_shap_artifact
from sip_engine.explainability.cri import load_cri_config, compute_cri, classify_risk_level
from sip_engine.explainability.analyzer import analyze_contract, serialize_to_json

__all__ = [
    "extract_shap_top_n",
    "save_shap_artifact",
    "load_cri_config",
    "compute_cri",
    "classify_risk_level",
    "analyze_contract",
    "serialize_to_json",
]
