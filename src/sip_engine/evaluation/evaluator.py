"""Evaluation module for SIP XGBoost models.

Computes comprehensive academic metrics and generates structured reports
(JSON, CSV, Markdown) for all 4 models (M1-M4) on held-out test data.

Metrics:
- AUC-ROC: Primary discrimination metric with ROC curve data points
- MAP@k: Mean Average Precision at k=100, 500, 1000 (critical for imbalanced M3/M4)
- NDCG@k: Normalized Discounted Cumulative Gain at k=100, 500, 1000
- Precision/Recall/F1: At 19 decision thresholds (0.05 to 0.95 in 0.05 steps)
- Brier Score: Probability calibration quality with baseline
- Optimal threshold: F1-maximizing threshold as recommended operating point
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    ndcg_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from tabulate import tabulate as tabulate_fn

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

MODEL_IDS: list[str] = ["M1", "M2", "M3", "M4"]

THRESHOLDS: list[float] = [round(t, 2) for t in np.arange(0.05, 1.0, 0.05)]  # 19 thresholds

K_VALUES: list[int] = [100, 500, 1000]

# =============================================================================
# Public metric function (exposed for testability)
# =============================================================================


def map_at_k(y_true: np.ndarray, y_scores: np.ndarray, k: int) -> float:
    """Compute Mean Average Precision at k (MAP@k).

    Sorts predictions by score descending, computes precision at each
    position where a positive label appears in the top-k, and returns
    the mean of those precisions.

    Args:
        y_true: Binary ground truth labels (0/1), shape (n,).
        y_scores: Predicted probabilities or scores, shape (n,).
        k: Cutoff rank. Clamped to len(y_true) if k > n.

    Returns:
        MAP@k in [0.0, 1.0]. Returns 0.0 if no positives in top-k.
    """
    n = len(y_true)
    k = min(k, n)

    # Sort by descending score
    sorted_indices = np.argsort(y_scores)[::-1]
    y_true_topk = y_true[sorted_indices][:k]

    precisions = []
    num_positives = 0
    for i, label in enumerate(y_true_topk):
        if label == 1:
            num_positives += 1
            precisions.append(num_positives / (i + 1))

    return float(np.mean(precisions)) if precisions else 0.0


# =============================================================================
# Private helpers: artifact loading
# =============================================================================


def _load_artifacts(
    model_id: str,
    models_dir: Path | None = None,
) -> tuple[Any, pd.DataFrame, dict, dict]:
    """Load model artifacts from disk.

    Args:
        model_id: One of M1, M2, M3, M4.
        models_dir: Base directory for model artifacts. Defaults to artifacts/models.

    Returns:
        Tuple of (model, test_df, training_report, feature_registry).

    Raises:
        FileNotFoundError: If any required artifact is missing.
    """
    if models_dir is None:
        models_dir = Path("artifacts/models")

    model_dir = models_dir / model_id

    required_files = {
        "model.pkl": model_dir / "model.pkl",
        "test_data.parquet": model_dir / "test_data.parquet",
        "training_report.json": model_dir / "training_report.json",
        "feature_registry.json": model_dir / "feature_registry.json",
    }

    for name, path in required_files.items():
        if not path.exists():
            raise FileNotFoundError(
                f"Model {model_id} artifact '{name}' not found at {path} — "
                f"run 'python -m sip_engine train --model {model_id}' first"
            )

    model = joblib.load(required_files["model.pkl"])
    test_df = pd.read_parquet(required_files["test_data.parquet"])
    training_report = json.loads(required_files["training_report.json"].read_text())
    feature_registry = json.loads(required_files["feature_registry.json"].read_text())

    return model, test_df, training_report, feature_registry


# =============================================================================
# Private helpers: metric computation
# =============================================================================


def _compute_discrimination_metrics(
    y_true: np.ndarray, y_scores: np.ndarray
) -> dict:
    """Compute AUC-ROC and ROC curve data (EVAL-01).

    Returns:
        Dict with "auc_roc" (float) and "roc_curve" (dict with fpr/tpr/thresholds lists).
    """
    auc = roc_auc_score(y_true, y_scores)
    fpr, tpr, thresholds = roc_curve(y_true, y_scores)
    return {
        "auc_roc": float(auc),
        "roc_curve": {
            "fpr": fpr.tolist(),
            "tpr": tpr.tolist(),
            "thresholds": thresholds.tolist(),
        },
    }


def _compute_ranking_metrics(
    y_true: np.ndarray, y_scores: np.ndarray
) -> dict:
    """Compute MAP@k and NDCG@k for k in K_VALUES (EVAL-02, EVAL-03).

    Returns:
        Dict with keys map_100, map_500, map_1000, ndcg_100, ndcg_500, ndcg_1000.
    """
    result: dict[str, float] = {}
    for k in K_VALUES:
        result[f"map_{k}"] = map_at_k(y_true, y_scores, k)
        result[f"ndcg_{k}"] = float(
            ndcg_score(y_true.reshape(1, -1), y_scores.reshape(1, -1), k=k)
        )
    return result


def _compute_calibration_metrics(
    y_true: np.ndarray, y_scores: np.ndarray
) -> dict:
    """Compute Brier Score and baseline (EVAL-05).

    Returns:
        Dict with "brier_score" and "brier_baseline" (positive_rate * (1 - positive_rate)).
    """
    brier = brier_score_loss(y_true, y_scores)
    positive_rate = float(y_true.mean())
    brier_baseline = positive_rate * (1.0 - positive_rate)
    return {
        "brier_score": float(brier),
        "brier_baseline": float(brier_baseline),
    }


def _compute_threshold_analysis(
    y_true: np.ndarray, y_scores: np.ndarray
) -> dict:
    """Compute Precision, Recall, F1 and confusion matrices at 19 thresholds (EVAL-04).

    Returns:
        Dict with threshold lists, metric lists, confusion matrices, and optimal_threshold.
    """
    thresholds_list: list[float] = []
    precision_list: list[float] = []
    recall_list: list[float] = []
    f1_list: list[float] = []
    cm_list: list[dict] = []

    for threshold in THRESHOLDS:
        y_pred = (y_scores >= threshold).astype(int)
        p = float(precision_score(y_true, y_pred, zero_division=0))
        r = float(recall_score(y_true, y_pred, zero_division=0))
        f = float(f1_score(y_true, y_pred, zero_division=0))
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        thresholds_list.append(threshold)
        precision_list.append(p)
        recall_list.append(r)
        f1_list.append(f)
        cm_list.append({"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)})

    # Find optimal threshold (F1-maximizing)
    best_idx = int(np.argmax(f1_list))
    optimal = {
        "value": thresholds_list[best_idx],
        "precision": precision_list[best_idx],
        "recall": recall_list[best_idx],
        "f1": f1_list[best_idx],
        "confusion_matrix": cm_list[best_idx],
    }

    return {
        "thresholds": thresholds_list,
        "precision": precision_list,
        "recall": recall_list,
        "f1": f1_list,
        "confusion_matrices": cm_list,
        "optimal_threshold": optimal,
    }


# =============================================================================
# Private helpers: output path
# =============================================================================


def _get_output_path(output_dir: Path, model_id: str, extension: str) -> Path:
    """Return a non-colliding output path for an evaluation report.

    If the base path doesn't exist, returns it directly.
    If it exists, adds a timestamp suffix to avoid overwriting.

    Args:
        output_dir: Root output directory (e.g., artifacts/evaluation).
        model_id: Model identifier (e.g., M1).
        extension: File extension including dot (e.g., ".json").

    Returns:
        A Path that does not yet exist on disk. Parent directory is created.
    """
    base_path = output_dir / model_id / f"{model_id}_eval{extension}"
    base_path.parent.mkdir(parents=True, exist_ok=True)

    if not base_path.exists():
        return base_path

    # Add timestamp to avoid overwriting
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return base_path.parent / f"{model_id}_eval_{ts}{extension}"


# =============================================================================
# Private helpers: report writers
# =============================================================================


def _write_json_report(eval_dict: dict, output_path: Path) -> None:
    """Write evaluation results as indented JSON.

    Args:
        eval_dict: Full evaluation dictionary with all metrics.
        output_path: Destination file path.
    """
    output_path.write_text(json.dumps(eval_dict, indent=2))


def _write_csv_report(eval_dict: dict, output_path: Path) -> None:
    """Write evaluation results as CSV.

    Format: 19 threshold rows followed by summary scalar rows.
    Columns: metric_type, threshold, value, precision, recall, f1, tn, fp, fn, tp

    Args:
        eval_dict: Full evaluation dictionary with all metrics.
        output_path: Destination file path.
    """
    ta = eval_dict.get("threshold_analysis", {})
    thresholds = ta.get("thresholds", [])
    precision_vals = ta.get("precision", [])
    recall_vals = ta.get("recall", [])
    f1_vals = ta.get("f1", [])
    cms = ta.get("confusion_matrices", [])

    disc = eval_dict.get("discrimination", {})
    ranking = eval_dict.get("ranking", {})
    calib = eval_dict.get("calibration", {})
    opt = eval_dict.get("optimal_threshold", {})

    with output_path.open("w", newline="") as f:
        writer = csv.writer(f)
        # Header
        writer.writerow(["metric_type", "threshold", "value", "precision", "recall", "f1", "tn", "fp", "fn", "tp"])

        # Threshold rows
        for i, t in enumerate(thresholds):
            cm = cms[i] if i < len(cms) else {}
            writer.writerow([
                "threshold",
                t,
                "",
                precision_vals[i] if i < len(precision_vals) else "",
                recall_vals[i] if i < len(recall_vals) else "",
                f1_vals[i] if i < len(f1_vals) else "",
                cm.get("tn", ""),
                cm.get("fp", ""),
                cm.get("fn", ""),
                cm.get("tp", ""),
            ])

        # Summary scalar rows
        scalar_metrics = [
            ("auc_roc", disc.get("auc_roc", "")),
            ("brier_score", calib.get("brier_score", "")),
            ("brier_baseline", calib.get("brier_baseline", "")),
            ("map_100", ranking.get("map_100", "")),
            ("map_500", ranking.get("map_500", "")),
            ("map_1000", ranking.get("map_1000", "")),
            ("ndcg_100", ranking.get("ndcg_100", "")),
            ("ndcg_500", ranking.get("ndcg_500", "")),
            ("ndcg_1000", ranking.get("ndcg_1000", "")),
            ("optimal_threshold_value", opt.get("value", "")),
            ("optimal_threshold_f1", opt.get("f1", "")),
            ("optimal_threshold_precision", opt.get("precision", "")),
            ("optimal_threshold_recall", opt.get("recall", "")),
        ]
        for name, value in scalar_metrics:
            writer.writerow(["summary", "", name, "", "", value, "", "", "", ""])


def _write_markdown_report(eval_dict: dict, output_path: Path) -> None:
    """Write a human-readable Markdown evaluation report.

    Args:
        eval_dict: Full evaluation dictionary with all metrics.
        output_path: Destination file path.
    """
    model_id = eval_dict.get("model_id", "Unknown")
    eval_date = eval_dict.get("evaluation_date", "Unknown")
    test_size = eval_dict.get("test_set_size", 0)
    label_dist = eval_dict.get("label_distribution", {})
    positive_rate = label_dist.get("positive_rate", 0.0)

    disc = eval_dict.get("discrimination", {})
    ranking = eval_dict.get("ranking", {})
    calib = eval_dict.get("calibration", {})
    ta = eval_dict.get("threshold_analysis", {})
    opt = eval_dict.get("optimal_threshold", {})
    ctx = eval_dict.get("training_context", {})

    lines = [
        f"# Evaluation Report — Model {model_id}",
        "",
        f"**Evaluation date:** {eval_date}  ",
        f"**Test set size:** {test_size:,}  ",
        f"**Positive rate:** {positive_rate:.4f} ({label_dist.get('n_positive', 0):,} positives / {test_size:,} total)  ",
        "",
        "---",
        "",
        "## Discrimination Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| AUC-ROC | {disc.get('auc_roc', 'N/A'):.4f} |",
        "",
        "> ROC curve data (FPR/TPR pairs) available in the JSON report for plotting.",
        "",
        "---",
        "",
        "## Ranking Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| MAP@100 | {ranking.get('map_100', 'N/A'):.4f} |",
        f"| MAP@500 | {ranking.get('map_500', 'N/A'):.4f} |",
        f"| MAP@1000 | {ranking.get('map_1000', 'N/A'):.4f} |",
        f"| NDCG@100 | {ranking.get('ndcg_100', 'N/A'):.4f} |",
        f"| NDCG@500 | {ranking.get('ndcg_500', 'N/A'):.4f} |",
        f"| NDCG@1000 | {ranking.get('ndcg_1000', 'N/A'):.4f} |",
        "",
        "---",
        "",
        "## Calibration Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Brier Score | {calib.get('brier_score', 'N/A'):.4f} |",
        f"| Brier Baseline (random) | {calib.get('brier_baseline', 'N/A'):.4f} |",
        "",
        "> Lower Brier Score is better. Baseline = positive_rate × (1 − positive_rate).",
        "",
        "---",
        "",
        "## Threshold Analysis",
        "",
        "| Threshold | Precision | Recall | F1 | TN | FP | FN | TP |",
        "|-----------|-----------|--------|----|----|----|----|-----|",
    ]

    thresholds = ta.get("thresholds", [])
    precision_vals = ta.get("precision", [])
    recall_vals = ta.get("recall", [])
    f1_vals = ta.get("f1", [])
    cms = ta.get("confusion_matrices", [])

    for i, t in enumerate(thresholds):
        cm = cms[i] if i < len(cms) else {}
        p = precision_vals[i] if i < len(precision_vals) else 0.0
        r = recall_vals[i] if i < len(recall_vals) else 0.0
        f = f1_vals[i] if i < len(f1_vals) else 0.0
        lines.append(
            f"| {t:.2f} | {p:.4f} | {r:.4f} | {f:.4f} | "
            f"{cm.get('tn', 0)} | {cm.get('fp', 0)} | {cm.get('fn', 0)} | {cm.get('tp', 0)} |"
        )

    opt_val = opt.get("value", "N/A")
    opt_p = opt.get("precision", 0.0)
    opt_r = opt.get("recall", 0.0)
    opt_f = opt.get("f1", 0.0)
    opt_cm = opt.get("confusion_matrix", {})

    lines += [
        "",
        "---",
        "",
        "## Optimal Threshold",
        "",
        f"**Recommended operating point (F1-maximizing):** threshold = {opt_val}",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Threshold | {opt_val} |",
        f"| Precision | {opt_p:.4f} |",
        f"| Recall | {opt_r:.4f} |",
        f"| F1 | {opt_f:.4f} |",
        f"| TN | {opt_cm.get('tn', 0)} |",
        f"| FP | {opt_cm.get('fp', 0)} |",
        f"| FN | {opt_cm.get('fn', 0)} |",
        f"| TP | {opt_cm.get('tp', 0)} |",
        "",
        "---",
        "",
        "## Training Context",
        "",
    ]

    best_params = ctx.get("best_params", {})
    strategy = ctx.get("imbalance_strategy", "Unknown")
    cv_scores = ctx.get("best_cv_scores", {})

    lines += [
        f"**Imbalance strategy:** {strategy}  ",
        "",
        "**Best hyperparameters:**",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
    ]
    for param, val in best_params.items():
        lines.append(f"| {param} | {val} |")

    if cv_scores:
        lines += [
            "",
            "**Cross-validation scores (best configuration):**",
            "",
            "| Fold | AUC-ROC |",
            "|------|---------|",
        ]
        for fold_score in cv_scores.get("scores", []):
            lines.append(f"| — | {fold_score:.4f} |")
        lines.append(f"| **Mean** | **{cv_scores.get('mean', 0.0):.4f}** |")
        lines.append(f"| **Std** | {cv_scores.get('std', 0.0):.4f} |")

    lines += [
        "",
        "---",
        "",
        "*See companion JSON and CSV files for full data including ROC curve points,*  ",
        "*hyperparameter search history (all iterations), and machine-readable metrics.*",
        "",
    ]

    output_path.write_text("\n".join(lines))


# =============================================================================
# Public orchestration functions
# =============================================================================


def evaluate_model(
    model_id: str,
    models_dir: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Evaluate a single trained model on its held-out test set.

    Loads model artifacts, computes all metrics (AUC-ROC, MAP@k, NDCG@k,
    Brier Score, threshold sweep), and writes JSON + CSV + Markdown reports.

    Args:
        model_id: Model identifier, one of M1, M2, M3, M4.
        models_dir: Directory containing model artifacts. Defaults to artifacts/models.
        output_dir: Root output directory for evaluation reports. Defaults to artifacts/evaluation.

    Returns:
        Path to the output directory for this model (e.g., artifacts/evaluation/M1/).

    Raises:
        FileNotFoundError: If model artifacts are missing.
        ValueError: If model_id is not recognized.
    """
    if output_dir is None:
        output_dir = Path("artifacts/evaluation")

    if model_id not in MODEL_IDS:
        raise ValueError(f"Unknown model_id '{model_id}'. Expected one of {MODEL_IDS}.")

    print(f"\nEvaluating model {model_id}...")

    # Step 1: Load artifacts
    model, test_df, training_report, feature_registry = _load_artifacts(model_id, models_dir)

    feature_columns: list[str] = feature_registry["feature_columns"]
    X_test = test_df[feature_columns]
    y_test = test_df[model_id].values.astype(int)

    n_samples = len(y_test)
    n_positive = int(y_test.sum())
    n_negative = n_samples - n_positive
    positive_rate = n_positive / n_samples if n_samples > 0 else 0.0

    print(f"  ✓ Loaded model and test data ({n_samples:,} samples, {positive_rate:.1%} positive)")

    # Step 2: Generate predictions
    y_scores = model.predict_proba(X_test)[:, 1]

    # Step 3: Compute metrics
    discrimination = _compute_discrimination_metrics(y_test, y_scores)
    print(f"  ✓ AUC-ROC: {discrimination['auc_roc']:.4f}")

    calibration = _compute_calibration_metrics(y_test, y_scores)
    print(f"  ✓ Brier Score: {calibration['brier_score']:.4f}")

    ranking = _compute_ranking_metrics(y_test, y_scores)
    print(
        f"  ✓ MAP@100: {ranking['map_100']:.4f}, "
        f"MAP@500: {ranking['map_500']:.4f}, "
        f"MAP@1000: {ranking['map_1000']:.4f}"
    )
    print(
        f"  ✓ NDCG@100: {ranking['ndcg_100']:.4f}, "
        f"NDCG@500: {ranking['ndcg_500']:.4f}, "
        f"NDCG@1000: {ranking['ndcg_1000']:.4f}"
    )

    threshold_analysis = _compute_threshold_analysis(y_test, y_scores)
    opt = threshold_analysis["optimal_threshold"]
    print(
        f"  ✓ Analyzed {len(THRESHOLDS)} decision thresholds "
        f"(optimal: {opt['value']:.2f}, F1={opt['f1']:.4f})"
    )

    # Step 4: Assemble eval dict
    eval_dict: dict = {
        "model_id": model_id,
        "evaluation_date": datetime.now(timezone.utc).isoformat(),
        "test_set_size": n_samples,
        "label_distribution": {
            "n_positive": n_positive,
            "n_negative": n_negative,
            "positive_rate": positive_rate,
        },
        "discrimination": discrimination,
        "ranking": ranking,
        "calibration": calibration,
        "threshold_analysis": threshold_analysis,
        "optimal_threshold": opt,
        "training_context": {
            "best_params": training_report.get("best_params", {}),
            "imbalance_strategy": training_report.get("imbalance_strategy", "Unknown"),
            "best_cv_scores": training_report.get("best_cv_scores", {}),
            "hp_search_history": training_report.get("hp_search_history", []),
            "train_size": training_report.get("train_size", None),
            "test_size": training_report.get("test_size", None),
        },
    }

    # Step 5: Write reports
    model_output_dir = output_dir / model_id
    model_output_dir.mkdir(parents=True, exist_ok=True)

    json_path = _get_output_path(output_dir, model_id, ".json")
    csv_path = _get_output_path(output_dir, model_id, ".csv")
    md_path = _get_output_path(output_dir, model_id, ".md")

    _write_json_report(eval_dict, json_path)
    _write_csv_report(eval_dict, csv_path)
    _write_markdown_report(eval_dict, md_path)

    print(f"  ✓ Reports written to {model_output_dir}/")

    return model_output_dir


def evaluate_all(
    models_dir: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Evaluate all 4 SIP models (M1-M4) and produce a cross-model summary.

    Calls evaluate_model() for each model in MODEL_IDS, then writes
    summary.json and summary.csv aggregating key metrics across all models.

    Args:
        models_dir: Directory containing model artifacts. Defaults to artifacts/models.
        output_dir: Root output directory for evaluation reports. Defaults to artifacts/evaluation.

    Returns:
        Path to the root evaluation output directory.
    """
    if output_dir is None:
        output_dir = Path("artifacts/evaluation")

    summary: dict[str, dict] = {}
    errors: dict[str, str] = {}

    for model_id in MODEL_IDS:
        try:
            # Re-run evaluate_model and capture metrics by re-loading artifacts
            model, test_df, training_report, feature_registry = _load_artifacts(model_id, models_dir)
            feature_columns = feature_registry["feature_columns"]
            X_test = test_df[feature_columns]
            y_test = test_df[model_id].values.astype(int)
            y_scores = model.predict_proba(X_test)[:, 1]

            disc = _compute_discrimination_metrics(y_test, y_scores)
            rank = _compute_ranking_metrics(y_test, y_scores)
            calib = _compute_calibration_metrics(y_test, y_scores)
            ta = _compute_threshold_analysis(y_test, y_scores)
            opt = ta["optimal_threshold"]

            n_samples = len(y_test)
            positive_rate = float(y_test.mean())

            summary[model_id] = {
                "auc_roc": disc["auc_roc"],
                "brier_score": calib["brier_score"],
                "map_100": rank["map_100"],
                "map_500": rank["map_500"],
                "map_1000": rank["map_1000"],
                "ndcg_100": rank["ndcg_100"],
                "ndcg_500": rank["ndcg_500"],
                "ndcg_1000": rank["ndcg_1000"],
                "optimal_threshold": opt["value"],
                "precision_at_optimal": opt["precision"],
                "recall_at_optimal": opt["recall"],
                "f1_at_optimal": opt["f1"],
                "test_set_size": n_samples,
                "positive_rate": positive_rate,
            }
        except FileNotFoundError as e:
            logger.warning("Skipping %s: %s", model_id, e)
            errors[model_id] = str(e)

    if not summary:
        logger.error("No models evaluated — check that model artifacts exist.")
        return output_dir

    # Write summary.json
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_json_path = output_dir / "summary.json"
    summary_json_path.write_text(json.dumps(summary, indent=2))

    # Write summary.csv
    summary_csv_path = output_dir / "summary.csv"
    if summary:
        fieldnames = ["model_id"] + list(next(iter(summary.values())).keys())
        with summary_csv_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for model_id, metrics in summary.items():
                writer.writerow({"model_id": model_id, **metrics})

    # Print console summary table
    _print_summary_table(summary)

    if errors:
        print(f"\n⚠ Skipped models: {', '.join(errors.keys())} (artifacts not found)")

    return output_dir


def _print_summary_table(summary: dict[str, dict]) -> None:
    """Print a formatted cross-model summary table to console using tabulate."""
    if not summary:
        return

    headers = ["Model", "AUC-ROC", "Brier", "MAP@100", "MAP@1000", "NDCG@100", "Opt.Thresh", "P@Opt", "R@Opt"]
    rows = []
    for mid, m in summary.items():
        rows.append([
            mid,
            f"{m['auc_roc']:.4f}",
            f"{m['brier_score']:.4f}",
            f"{m['map_100']:.4f}",
            f"{m['map_1000']:.4f}",
            f"{m['ndcg_100']:.4f}",
            f"{m['optimal_threshold']:.2f}",
            f"{m['precision_at_optimal']:.4f}",
            f"{m['recall_at_optimal']:.4f}",
        ])

    print("\nCross-Model Summary:")
    print(tabulate_fn(rows, headers=headers, tablefmt="grid"))
