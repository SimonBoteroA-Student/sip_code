"""Model training and inference module for sip_engine."""

from sip_engine.models.trainer import (
    MODEL_IDS,
    PARAM_DIST,
    RANDOM_SEED,
    _compare_strategies,
    _cv_score_scale_pos_weight,
    _cv_score_upsampling,
    _hp_search,
    _stratified_split,
    _train_with_fallback,
    train_model,
)

__all__ = [
    "MODEL_IDS",
    "PARAM_DIST",
    "RANDOM_SEED",
    "_compare_strategies",
    "_cv_score_scale_pos_weight",
    "_cv_score_upsampling",
    "_hp_search",
    "_stratified_split",
    "_train_with_fallback",
    "train_model",
]
