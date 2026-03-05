"""Composite Risk Index (CRI) computation for SIP.

CRI aggregates the four model probabilities (M1–M4) and the IRIC score into a
single weighted risk score, then maps it to one of five human-readable risk
levels using configurable thresholds from model_weights.json.

Public API:
    load_cri_config      — load weights + thresholds from model_weights.json
    compute_cri          — weighted sum of 5 inputs → CRI score in [0, 1]
    classify_risk_level  — map CRI score to risk level string
"""

from __future__ import annotations

import json
from pathlib import Path


def load_cri_config(weights_path: Path | None = None) -> dict:
    """Load CRI weights and risk thresholds from model_weights.json.

    Args:
        weights_path: Path to model_weights.json. Defaults to
            ``get_settings().model_weights_path``.

    Returns:
        Full config dict containing the 5 model weight keys and the
        ``risk_thresholds`` section.
    """
    if weights_path is None:
        from sip_engine.shared.config import get_settings
        weights_path = get_settings().model_weights_path

    with open(weights_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def compute_cri(
    p_m1: float,
    p_m2: float,
    p_m3: float,
    p_m4: float,
    iric_score: float,
    weights: dict | None = None,
) -> float:
    """Compute Composite Risk Index as a configurable weighted sum.

    CRI = w_m1·p_m1 + w_m2·p_m2 + w_m3·p_m3 + w_m4·p_m4 + w_iric·iric_score

    Weight key mapping in model_weights.json:
        "m1_cost_overruns" → p_m1
        "m2_delays"        → p_m2
        "m3_comptroller"   → p_m3
        "m4_fines"         → p_m4
        "iric"             → iric_score

    Args:
        p_m1: Predicted probability from M1 (cost overruns model), in [0, 1].
        p_m2: Predicted probability from M2 (delays model), in [0, 1].
        p_m3: Predicted probability from M3 (comptroller model), in [0, 1].
        p_m4: Predicted probability from M4 (fines model), in [0, 1].
        iric_score: Normalised IRIC score, in [0, 1].
        weights: Dict with the 5 weight keys. If None, loads from
            ``load_cri_config()``.

    Returns:
        CRI score rounded to 6 decimal places.
    """
    if weights is None:
        weights = load_cri_config()

    w_m1 = float(weights["m1_cost_overruns"])
    w_m2 = float(weights["m2_delays"])
    w_m3 = float(weights["m3_comptroller"])
    w_m4 = float(weights["m4_fines"])
    w_iric = float(weights["iric"])

    result = (
        w_m1 * float(p_m1)
        + w_m2 * float(p_m2)
        + w_m3 * float(p_m3)
        + w_m4 * float(p_m4)
        + w_iric * float(iric_score)
    )
    return round(float(result), 6)


def classify_risk_level(
    cri_score: float,
    thresholds: dict | None = None,
) -> str:
    """Classify a CRI score into one of five risk level strings.

    Risk bands (default, inclusive lower / exclusive upper except very_high):
        Very Low  — [0.00, 0.20)
        Low       — [0.20, 0.40)
        Medium    — [0.40, 0.60)
        High      — [0.60, 0.80)
        Very High — [0.80, 1.00]  ← includes exactly 1.0

    Args:
        cri_score: CRI value, in [0, 1].
        thresholds: Dict mapping level keys to [lower, upper] bounds. If None,
            loads from ``load_cri_config()["risk_thresholds"]``.

    Returns:
        Title-case risk level string: one of "Very Low", "Low", "Medium",
        "High", "Very High".

    Raises:
        ValueError: If cri_score falls outside all thresholds.
    """
    if thresholds is None:
        thresholds = load_cri_config()["risk_thresholds"]

    # Ordered from lowest to highest
    ordered = [
        ("very_low", "Very Low"),
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("very_high", "Very High"),
    ]

    score = float(cri_score)

    for key, label in ordered:
        lo, hi = thresholds[key]
        lo, hi = float(lo), float(hi)
        if key == "very_high":
            # Inclusive on both ends for the top band
            if lo <= score <= hi:
                return label
        else:
            # Inclusive lower, exclusive upper
            if lo <= score < hi:
                return label

    raise ValueError(
        f"CRI score {score!r} does not fall within any configured risk threshold band. "
        f"Thresholds: {thresholds}"
    )
