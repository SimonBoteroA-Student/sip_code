"""IRIC (Indice de Riesgo Integrado de Corrupcion) module for sip_engine.

Public API re-exports for all IRIC submodules.

Usage:
    from sip_engine.classifiers.iric import compute_iric_components, compute_iric_scores
    from sip_engine.classifiers.iric import compute_bid_stats, build_bid_stats_lookup
    from sip_engine.classifiers.iric import calibrate_iric_thresholds, load_iric_thresholds
    from sip_engine.classifiers.iric import build_iric, compute_iric
"""

from sip_engine.classifiers.iric.calculator import compute_iric_components, compute_iric_scores
from sip_engine.classifiers.iric.bid_stats import compute_bid_stats, build_bid_stats_lookup
from sip_engine.classifiers.iric.thresholds import (
    calibrate_iric_thresholds,
    load_iric_thresholds,
    reset_iric_thresholds_cache,
    get_threshold,
    save_iric_thresholds,
)
from sip_engine.classifiers.iric.pipeline import build_iric, compute_iric

__all__ = [
    # calculator.py
    "compute_iric_components",
    "compute_iric_scores",
    # bid_stats.py
    "compute_bid_stats",
    "build_bid_stats_lookup",
    # thresholds.py
    "calibrate_iric_thresholds",
    "load_iric_thresholds",
    "reset_iric_thresholds_cache",
    "get_threshold",
    "save_iric_thresholds",
    # pipeline.py
    "build_iric",
    "compute_iric",
]
