"""Evaluation package for SIP XGBoost models.

Provides comprehensive academic evaluation including AUC-ROC, MAP@k, NDCG@k,
Precision/Recall threshold sweep, Brier Score, Recall@K, Precision@K,
and report generation.
"""

from sip_engine.evaluation.evaluator import (
    evaluate_all,
    evaluate_model,
    map_at_k,
    precision_at_k,
    recall_at_k,
    recall_precision_at_k,
)

__all__ = [
    "evaluate_model",
    "evaluate_all",
    "map_at_k",
    "recall_at_k",
    "precision_at_k",
    "recall_precision_at_k",
]
