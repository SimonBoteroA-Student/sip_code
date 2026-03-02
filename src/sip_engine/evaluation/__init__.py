"""Evaluation package for SIP XGBoost models.

Provides comprehensive academic evaluation including AUC-ROC, MAP@k, NDCG@k,
Precision/Recall threshold sweep, Brier Score, and report generation.
"""

from sip_engine.evaluation.evaluator import evaluate_model, evaluate_all

__all__ = ["evaluate_model", "evaluate_all"]
