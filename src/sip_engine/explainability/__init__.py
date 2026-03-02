"""Explainability package for SIP — SHAP feature attribution and CRI computation.

Provides TreeSHAP-based feature explanations for each XGBoost model and the
Composite Risk Index (CRI) that aggregates all model predictions into a single
configurable risk score with human-readable risk levels.
"""

from sip_engine.explainability.shap_explainer import extract_shap_top_n, save_shap_artifact
from sip_engine.explainability.cri import load_cri_config, compute_cri, classify_risk_level

__all__ = [
    "extract_shap_top_n",
    "save_shap_artifact",
    "load_cri_config",
    "compute_cri",
    "classify_risk_level",
]
