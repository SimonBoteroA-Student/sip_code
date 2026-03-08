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
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    ndcg_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from tabulate import tabulate as tabulate_fn

from sip_engine.classifiers.evaluation.visualizer import generate_all_charts

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

MODEL_IDS: list[str] = ["M1", "M2", "M3", "M4"]

THRESHOLDS: list[float] = [round(t, 2) for t in np.arange(0.05, 1.0, 0.05)]  # 19 thresholds

K_VALUES: list[int] = [100, 500, 1000]

RECALL_K_VALUES: list[int] = [10, 50, 100, 500, 1000]

# =============================================================================
# Public metric functions (exposed for testability)
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


def recall_at_k(y_true: np.ndarray, y_scores: np.ndarray, k: int) -> float:
    """Compute Recall@K.

    Sorts predictions by score descending and counts what fraction of all
    real positives appear in the top-K results.

    Formula: Recall@K = positives_in_top_K / total_positives

    Args:
        y_true: Binary ground truth labels (0/1), shape (n,).
        y_scores: Predicted probabilities or scores, shape (n,).
        k: Cutoff rank. Clamped to len(y_true) if k > n.

    Returns:
        Recall@K in [0.0, 1.0]. Returns 0.0 if no positives in dataset.
    """
    if len(y_true) != len(y_scores):
        raise ValueError(
            f"y_true and y_scores must have the same length, "
            f"got {len(y_true)} and {len(y_scores)}"
        )
    k = min(k, len(y_true))
    total_positives = int(y_true.sum())
    if total_positives == 0:
        return 0.0
    sorted_indices = np.argsort(y_scores)[::-1]
    positives_in_topk = int(y_true[sorted_indices][:k].sum())
    return positives_in_topk / total_positives


def precision_at_k(y_true: np.ndarray, y_scores: np.ndarray, k: int) -> float:
    """Compute Precision@K.

    Sorts predictions by score descending and counts what fraction of the
    top-K results are real positives.

    Formula: Precision@K = positives_in_top_K / K

    Args:
        y_true: Binary ground truth labels (0/1), shape (n,).
        y_scores: Predicted probabilities or scores, shape (n,).
        k: Cutoff rank. Clamped to len(y_true) if k > n.

    Returns:
        Precision@K in [0.0, 1.0].
    """
    if len(y_true) != len(y_scores):
        raise ValueError(
            f"y_true and y_scores must have the same length, "
            f"got {len(y_true)} and {len(y_scores)}"
        )
    k = min(k, len(y_true))
    if k == 0:
        return 0.0
    sorted_indices = np.argsort(y_scores)[::-1]
    positives_in_topk = int(y_true[sorted_indices][:k].sum())
    return positives_in_topk / k


def recall_precision_at_k(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    k_values: list[int],
) -> dict:
    """Compute Recall@K and Precision@K for multiple cutoffs.

    Sorts predictions by score descending once, then iterates through all
    K values efficiently.

    Args:
        y_true: Binary ground truth labels (0/1), shape (n,). Must be numpy array.
        y_scores: Predicted probabilities or scores, shape (n,). Must be numpy array.
        k_values: List of K cutoffs to evaluate (e.g. [10, 50, 100, 500, 1000]).

    Returns:
        Dict with "recall" and "precision" sub-dicts keyed by K value::

            {
              "recall":    {10: 0.08, 50: 0.35, 100: 0.62, ...},
              "precision": {10: 0.40, 50: 0.28, 100: 0.17, ...},
            }

    Raises:
        ValueError: If y_true and y_scores have different lengths or invalid types.

    Example::

        result = recall_precision_at_k(y_true, y_scores, [10, 100, 1000])
        print(result["recall"][100])    # fraction of positives in top-100
        print(result["precision"][100]) # fraction of top-100 that are positive
    """
    y_true = np.asarray(y_true)
    y_scores = np.asarray(y_scores)
    if y_true.ndim != 1 or y_scores.ndim != 1:
        raise ValueError("y_true and y_scores must be 1-D arrays.")
    if len(y_true) != len(y_scores):
        raise ValueError(
            f"y_true and y_scores must have the same length, "
            f"got {len(y_true)} and {len(y_scores)}"
        )

    n = len(y_true)
    total_positives = int(y_true.sum())
    sorted_indices = np.argsort(y_scores)[::-1]
    y_sorted = y_true[sorted_indices]

    recall_dict: dict[int, float] = {}
    precision_dict: dict[int, float] = {}

    for k in k_values:
        k_eff = min(k, n)
        positives_in_topk = int(y_sorted[:k_eff].sum())
        recall_dict[k] = positives_in_topk / total_positives if total_positives > 0 else 0.0
        precision_dict[k] = positives_in_topk / k_eff if k_eff > 0 else 0.0

    return {"recall": recall_dict, "precision": precision_dict}


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
    """Compute AUC-ROC, ROC curve, AUC-PR, and PR curve data.

    Returns:
        Dict with "auc_roc", "roc_curve", "auc_pr", and "pr_curve".
        pr_curve contains precision/recall arrays (len = len(thresholds) + 1)
        and thresholds array.
    """
    auc = roc_auc_score(y_true, y_scores)
    fpr, tpr, thresholds = roc_curve(y_true, y_scores)

    pr_precision, pr_recall, pr_thresholds = precision_recall_curve(y_true, y_scores)
    auc_pr = average_precision_score(y_true, y_scores)

    return {
        "auc_roc": float(auc),
        "roc_curve": {
            "fpr": fpr.tolist(),
            "tpr": tpr.tolist(),
            "thresholds": thresholds.tolist(),
        },
        "auc_pr": float(auc_pr),
        "pr_curve": {
            "precision": pr_precision.tolist(),
            "recall": pr_recall.tolist(),
            "thresholds": pr_thresholds.tolist(),
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


def _compute_recall_precision_at_k(
    y_true: np.ndarray, y_scores: np.ndarray
) -> dict:
    """Compute Recall@K and Precision@K for K in RECALL_K_VALUES.

    Returns:
        Dict with keys recall_10, recall_50, ..., precision_10, precision_50, ...
    """
    rp = recall_precision_at_k(y_true, y_scores, RECALL_K_VALUES)
    result: dict[str, float] = {}
    for k in RECALL_K_VALUES:
        result[f"recall_{k}"] = rp["recall"][k]
        result[f"precision_{k}"] = rp["precision"][k]
    return result


def _compute_calibration_metrics(
    y_true: np.ndarray, y_scores: np.ndarray
) -> dict:
    """Compute Brier Score, baseline, and Brier Skill Score (BSS).

    BSS = 1 - (brier / brier_baseline). Returns 0.0 if baseline == 0
    (all-positive or all-negative labels).

    Returns:
        Dict with "brier_score", "brier_baseline", and "brier_skill_score".
    """
    brier = brier_score_loss(y_true, y_scores)
    positive_rate = float(y_true.mean())
    brier_baseline = positive_rate * (1.0 - positive_rate)
    if brier_baseline > 0:
        brier_skill_score = 1.0 - (brier / brier_baseline)
    else:
        brier_skill_score = 0.0
    return {
        "brier_score": float(brier),
        "brier_baseline": float(brier_baseline),
        "brier_skill_score": float(brier_skill_score),
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


def _archive_existing_evaluation(model_output_dir: Path) -> None:
    """Move existing evaluation artifacts to old/{YYYY-MM-DD}/ subfolder.

    Archives JSON/CSV/MD reports, images/, and shap_*.parquet files.
    Reads the evaluation_date from the existing JSON report to determine
    the archive folder name; falls back to file modification time.
    """
    import shutil

    if not model_output_dir.exists():
        return

    # Check if there's anything to archive
    existing_files = list(model_output_dir.iterdir())
    # Filter out the old/ directory itself
    existing_files = [f for f in existing_files if f.name != "old"]
    if not existing_files:
        return

    # Determine archive date from existing JSON report
    archive_date = None
    for f in existing_files:
        if f.suffix == ".json" and "_eval" in f.name:
            try:
                data = json.loads(f.read_text())
                eval_date_str = data.get("evaluation_date", "")
                if eval_date_str:
                    archive_date = eval_date_str[:10]  # YYYY-MM-DD
            except Exception:
                pass
            break

    if archive_date is None:
        # Fall back to modification time of oldest file
        oldest = min(existing_files, key=lambda p: p.stat().st_mtime)
        archive_date = datetime.fromtimestamp(oldest.stat().st_mtime).strftime("%Y-%m-%d")

    archive_dir = model_output_dir / "old" / archive_date
    archive_dir.mkdir(parents=True, exist_ok=True)

    for item in existing_files:
        dest = archive_dir / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.move(str(item), str(dest))
        else:
            shutil.move(str(item), str(dest))

    logger.info("Archived existing evaluation to %s", archive_dir)


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
    rp = eval_dict.get("recall_precision_at_k", {})

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
        for k in RECALL_K_VALUES:
            scalar_metrics.append((f"recall_{k}", rp.get(f"recall_{k}", "")))
            scalar_metrics.append((f"precision_at_{k}", rp.get(f"precision_{k}", "")))
        for name, value in scalar_metrics:
            writer.writerow(["summary", "", name, "", "", value, "", "", "", ""])


def _write_markdown_report(eval_dict: dict, output_path: Path) -> None:
    """Write a human-readable Markdown evaluation report with embedded charts.

    Args:
        eval_dict: Full evaluation dictionary with all metrics.
        output_path: Destination file path.
    """
    model_id = eval_dict.get("model_id", "Unknown")
    eval_date = eval_dict.get("evaluation_date", "Unknown")
    test_size = eval_dict.get("test_set_size", 0)
    label_dist = eval_dict.get("label_distribution", {})
    positive_rate = label_dist.get("positive_rate", 0.0)
    n_positive = label_dist.get("n_positive", 0)
    n_negative = label_dist.get("n_negative", 0)

    disc = eval_dict.get("discrimination", {})
    ranking = eval_dict.get("ranking", {})
    calib = eval_dict.get("calibration", {})
    ta = eval_dict.get("threshold_analysis", {})
    opt = eval_dict.get("optimal_threshold", {})
    ctx = eval_dict.get("training_context", {})
    rp = eval_dict.get("recall_precision_at_k", {})

    # Image paths relative to the Markdown file (sibling images/ dir)
    img = "images"
    ms = f"_{model_id.lower()}" if model_id != "Unknown" else ""

    lines: list[str] = [
        f"# Evaluation Report — Model {model_id}",
        "",
        "| Property | Value |",
        "|----------|-------|",
        f"| Evaluation date | {eval_date} |",
        f"| Test set size | {test_size:,} |",
        f"| Positives | {n_positive:,} ({positive_rate:.2%}) |",
        f"| Negatives | {n_negative:,} ({1 - positive_rate:.2%}) |",
        "",
        "---",
        "",
        "## 1. Discrimination — ROC Curve",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| **AUC-ROC** | **{disc.get('auc_roc', 0):.4f}** |",
        "",
        f"![ROC Curve]({img}/roc_curve{ms}.png)",
        "",
        "---",
        "",
        "## 1b. Discrimination — PR Curve",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| **AUC-PR** | **{disc.get('auc_pr', 0):.4f}** |",
        "",
        f"![PR Curve]({img}/pr_curve{ms}.png)",
        "",
        "---",
        "",
        "## 2. Score Distribution",
        "",
        f"![Score Distribution]({img}/score_distribution{ms}.png)",
        "",
        "---",
        "",
        "## 3. Precision / Recall / F1 vs. Threshold",
        "",
        f"![Precision-Recall-F1]({img}/precision_recall_f1{ms}.png)",
        "",
    ]

    # Threshold analysis table
    thresholds = ta.get("thresholds", [])
    precision_vals = ta.get("precision", [])
    recall_vals = ta.get("recall", [])
    f1_vals = ta.get("f1", [])
    cms = ta.get("confusion_matrices", [])

    lines += [
        "<details>",
        "<summary>Threshold Analysis Table (click to expand)</summary>",
        "",
        "| Threshold | Precision | Recall | F1 | TN | FP | FN | TP |",
        "|:---------:|:---------:|:------:|:--:|---:|---:|---:|---:|",
    ]

    for i, t in enumerate(thresholds):
        cm = cms[i] if i < len(cms) else {}
        p = precision_vals[i] if i < len(precision_vals) else 0.0
        r = recall_vals[i] if i < len(recall_vals) else 0.0
        f = f1_vals[i] if i < len(f1_vals) else 0.0
        marker = " **←**" if abs(t - opt.get("value", -1)) < 0.001 else ""
        lines.append(
            f"| {t:.2f}{marker} | {p:.4f} | {r:.4f} | {f:.4f} | "
            f"{cm.get('tn', 0):,} | {cm.get('fp', 0):,} | {cm.get('fn', 0):,} | {cm.get('tp', 0):,} |"
        )

    lines += [
        "",
        "</details>",
        "",
        "---",
        "",
        "## 4. Optimal Threshold & Confusion Matrix",
        "",
    ]

    opt_val = opt.get("value", "N/A")
    opt_p = opt.get("precision", 0.0)
    opt_r = opt.get("recall", 0.0)
    opt_f = opt.get("f1", 0.0)
    opt_cm = opt.get("confusion_matrix", {})

    lines += [
        f"**Recommended operating point (F1-maximizing):** threshold = **{opt_val}**",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Threshold | {opt_val} |",
        f"| Precision | {opt_p:.4f} |",
        f"| Recall | {opt_r:.4f} |",
        f"| F1 | {opt_f:.4f} |",
        f"| TN | {opt_cm.get('tn', 0):,} |",
        f"| FP | {opt_cm.get('fp', 0):,} |",
        f"| FN | {opt_cm.get('fn', 0):,} |",
        f"| TP | {opt_cm.get('tp', 0):,} |",
        "",
        f"![Confusion Matrix]({img}/confusion_matrix{ms}.png)",
        "",
        "---",
        "",
        "## 5. Ranking Metrics",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| MAP@100 | {ranking.get('map_100', 0):.4f} |",
        f"| MAP@500 | {ranking.get('map_500', 0):.4f} |",
        f"| MAP@1000 | {ranking.get('map_1000', 0):.4f} |",
        f"| NDCG@100 | {ranking.get('ndcg_100', 0):.4f} |",
        f"| NDCG@500 | {ranking.get('ndcg_500', 0):.4f} |",
        f"| NDCG@1000 | {ranking.get('ndcg_1000', 0):.4f} |",
        "",
        f"![Ranking Metrics]({img}/ranking_metrics{ms}.png)",
        "",
        "---",
        "",
        "## 5b. Recall@K and Precision@K",
        "",
        "> Recall@K = fraction of all positives captured in top-K.  "
        "Precision@K = fraction of top-K results that are positive.",
        "",
        "| K | Recall@K | Precision@K |",
        "|--:|--------:|------------:|",
    ]
    for k in RECALL_K_VALUES:
        lines.append(
            f"| {k} | {rp.get(f'recall_{k}', 0):.4f} | {rp.get(f'precision_{k}', 0):.4f} |"
        )
    lines += [
        "",
        f"![Recall & Precision @K]({img}/recall_precision_at_k{ms}.png)",
        "",
        "---",
        "",
        "## 6. Calibration",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Brier Score | {calib.get('brier_score', 0):.4f} |",
        f"| Brier Baseline (random) | {calib.get('brier_baseline', 0):.4f} |",
        f"| Brier Skill Score (BSS) | {calib.get('brier_skill_score', 0):.4f} |",
        "",
        "> Lower Brier Score = better calibration. Baseline = positive_rate × (1 − positive_rate).",
        "> BSS > 0 = better than random; BSS = 1 = perfect.",
        "",
        f"![Calibration]({img}/calibration_summary{ms}.png)",
        "",
        "---",
        "",
    ]

    # SHAP explainability section (optional)
    shap = eval_dict.get("shap", {})
    top_features = shap.get("top_features", [])

    if top_features:
        lines += [
            "## 8. SHAP Feature Importance",
            "",
            "Top features by mean absolute SHAP value (test set):",
            "",
            "| Rank | Feature | Mean abs SHAP |",
            "|-----:|--------|--------------:|",
        ]
        for idx, feat in enumerate(top_features, 1):
            lines.append(f"| {idx} | {feat.get('feature', '')} | {feat.get('mean_abs_shap', 0.0):.6f} |")
        lines += [
            "",
            f"![SHAP Feature Importance]({img}/shap_importance{ms}.png)",
            "",
            f"SHAP artifact (parquet): {Path(shap.get('parquet', '')).name}",
            "",
            "---",
            "",
        ]
    else:
        lines += [
            "## 8. SHAP Feature Importance",
            "",
            "No SHAP explainability available for this evaluation run.",
            "",
            "---",
            "",
        ]

    lines += [
        "## 9. Training Context",
        "",
    ]

    best_params = ctx.get("best_params", {})
    strategy = ctx.get("imbalance_strategy", "Unknown")
    cv_scores = ctx.get("best_cv_scores", {})

    lines += [
        f"**Imbalance strategy:** {strategy}",
        "",
        "**Best hyperparameters:**",
        "",
        "| Parameter | Value |",
        "|-----------|------:|",
    ]
    for param, val in best_params.items():
        lines.append(f"| {param} | {val} |")

    if cv_scores:
        scores = cv_scores.get("scores", [])
        lines += [
            "",
            "**Cross-validation scores (best configuration):**",
            "",
            "| Fold | AUC-ROC |",
            "|-----:|--------:|",
        ]
        for idx, fold_score in enumerate(scores, 1):
            lines.append(f"| {idx} | {fold_score:.4f} |")
        lines.append(f"| **Mean** | **{cv_scores.get('mean', 0.0):.4f}** |")
        lines.append(f"| **Std** | {cv_scores.get('std', 0.0):.4f} |")

    lines += [
        "",
        "---",
        "",
        "*Report generated automatically by SIP Engine evaluation module.*  ",
        "*See companion JSON and CSV files for machine-readable data.*",
        "",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")


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

    # Archive existing evaluation artifacts before writing new ones
    _archive_existing_evaluation(output_dir / model_id)

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
    print(f"  AUC-PR: {discrimination['auc_pr']:.4f}")

    calibration = _compute_calibration_metrics(y_test, y_scores)
    print(f"  ✓ Brier Score: {calibration['brier_score']:.4f}")
    print(f"  BSS: {calibration['brier_skill_score']:.4f}")

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

    recall_precision = _compute_recall_precision_at_k(y_test, y_scores)
    print(
        f"  ✓ Recall@100: {recall_precision['recall_100']:.4f}, "
        f"Recall@500: {recall_precision['recall_500']:.4f}, "
        f"Recall@1000: {recall_precision['recall_1000']:.4f}"
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
        "recall_precision_at_k": recall_precision,
        "calibration": calibration,
        "threshold_analysis": threshold_analysis,
        "optimal_threshold": opt,
        "training_context": {
            "best_params": training_report.get("best_params", {}),
            "imbalance_strategy": training_report.get("strategy_comparison", {}).get("winner", "Unknown"),
            "strategy_comparison": training_report.get("strategy_comparison", {}),
            "train_size": training_report.get("label_distribution", {}).get("0", None),
            "test_size": training_report.get("test_size", None),
        },
    }

    # Step 5: Generate charts (and compute SHAP explainability)
    # Compute SHAP explainability and write Parquet artifact + summary into eval_dict["shap"]
    try:
        from sip_engine.classifiers.explainability.shap_explainer import extract_shap_top_n, save_shap_artifact

        if len(feature_columns) > 0 and len(X_test) > 0:
            shap_rows_all = extract_shap_top_n(model, X_test, feature_columns, n=len(feature_columns))

            # Resolve contract ids from test_df if available
            if "id_contrato" in test_df.columns:
                contract_ids = test_df["id_contrato"].astype(str).tolist()
            elif "ID Contrato" in test_df.columns:
                contract_ids = test_df["ID Contrato"].astype(str).tolist()
            elif "id" in test_df.columns:
                contract_ids = test_df["id"].astype(str).tolist()
            else:
                contract_ids = [str(i) for i in range(len(test_df))]

            # Save shap Parquet to model-specific output dir
            shap_out_path = save_shap_artifact(shap_rows_all, contract_ids, model_id, output_dir=output_dir / model_id)

            # Aggregate mean absolute SHAP per feature across test set
            importance: dict[str, float] = {}
            n_samples = len(shap_rows_all)
            for sample in shap_rows_all:
                for entry in sample:
                    importance[entry["feature"]] = importance.get(entry["feature"], 0.0) + abs(float(entry["shap_value"]))
            mean_abs = [{"feature": f, "mean_abs_shap": importance[f] / n_samples} for f in importance]
            mean_abs.sort(key=lambda x: x["mean_abs_shap"], reverse=True)
            top_features = [{"feature": e["feature"], "mean_abs_shap": round(float(e["mean_abs_shap"]), 6)} for e in mean_abs[:10]]

            eval_dict["shap"] = {"parquet": str(shap_out_path), "top_features": top_features}
            print(f"  ✓ SHAP explainability computed and saved → {shap_out_path}")
        else:
            eval_dict["shap"] = {}
    except Exception as e:
        logger.exception("Failed to compute SHAP explainability: %s", e)
        eval_dict["shap"] = {}

    images_dir = output_dir / model_id / "images"
    chart_paths = generate_all_charts(eval_dict, y_test, y_scores, images_dir)
    print(f"  ✓ Generated {len(chart_paths)} charts → {images_dir}/")

    # Step 6: Write reports
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
            # Delegate to evaluate_model for full pipeline (metrics + charts + reports)
            evaluate_model(model_id, models_dir=models_dir, output_dir=output_dir)

            # Read back the generated JSON to extract summary metrics
            json_path = output_dir / model_id / f"{model_id}_eval.json"
            report = json.loads(json_path.read_text())
            disc = report["discrimination"]
            rank = report["ranking"]
            calib = report["calibration"]
            opt = report["optimal_threshold"]
            rp = report.get("recall_precision_at_k", {})

            summary[model_id] = {
                "auc_roc": disc["auc_roc"],
                "auc_pr": disc.get("auc_pr", 0.0),
                "brier_score": calib["brier_score"],
                "brier_skill_score": calib.get("brier_skill_score", 0.0),
                "map_100": rank["map_100"],
                "map_500": rank["map_500"],
                "map_1000": rank["map_1000"],
                "ndcg_100": rank["ndcg_100"],
                "ndcg_500": rank["ndcg_500"],
                "ndcg_1000": rank["ndcg_1000"],
                "recall_100": rp.get("recall_100", 0.0),
                "recall_500": rp.get("recall_500", 0.0),
                "recall_1000": rp.get("recall_1000", 0.0),
                "precision_at_100": rp.get("precision_100", 0.0),
                "precision_at_500": rp.get("precision_500", 0.0),
                "precision_at_1000": rp.get("precision_1000", 0.0),
                "optimal_threshold": opt["value"],
                "precision_at_optimal": opt["precision"],
                "recall_at_optimal": opt["recall"],
                "f1_at_optimal": opt["f1"],
                "test_set_size": report["test_set_size"],
                "positive_rate": report["label_distribution"]["positive_rate"],
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

    headers = ["Model", "AUC-ROC", "AUC-PR", "Brier", "BSS", "MAP@100", "MAP@1000", "Recall@100", "Recall@1000", "P@K100", "Opt.Thresh", "R@Opt"]
    rows = []
    for mid, m in summary.items():
        rows.append([
            mid,
            f"{m['auc_roc']:.4f}",
            f"{m.get('auc_pr', 0):.4f}",
            f"{m['brier_score']:.4f}",
            f"{m.get('brier_skill_score', 0):.4f}",
            f"{m['map_100']:.4f}",
            f"{m['map_1000']:.4f}",
            f"{m.get('recall_100', 0):.4f}",
            f"{m.get('recall_1000', 0):.4f}",
            f"{m.get('precision_at_100', 0):.4f}",
            f"{m['optimal_threshold']:.2f}",
            f"{m['recall_at_optimal']:.4f}",
        ])

    print("\nCross-Model Summary:")
    print(tabulate_fn(rows, headers=headers, tablefmt="grid"))
