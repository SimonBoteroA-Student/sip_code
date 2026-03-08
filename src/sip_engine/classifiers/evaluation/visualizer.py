"""Visualization module for SIP evaluation reports.

Generates publication-quality charts for model evaluation metrics:
- Confusion matrix heatmap (at optimal threshold)
- ROC curve with AUC annotation
- Precision / Recall / F1 vs. decision threshold
- Ranking metrics bar chart (MAP@k, NDCG@k)
- Recall@K and Precision@K line chart
- Score distribution histogram (positive vs. negative class)
- Calibration summary bar chart (Brier score vs. baseline)
- SHAP feature importance horizontal bar chart (top-N by mean |SHAP|)

All functions accept pre-computed metric dicts (from evaluator.py) and
write PNG files to a specified output directory.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless rendering — no display required

import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)

# Consistent style across all charts
_STYLE_DEFAULTS = {
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "font.size": 10,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
}

_COLORS = {
    "primary": "#2563eb",
    "secondary": "#dc2626",
    "tertiary": "#16a34a",
    "neutral": "#6b7280",
    "bg_light": "#f8fafc",
}


def _apply_style() -> None:
    """Apply consistent matplotlib style."""
    plt.rcParams.update(_STYLE_DEFAULTS)


# =============================================================================
# Public chart functions
# =============================================================================


def plot_confusion_matrix(
    eval_dict: dict,
    output_dir: Path,
    filename: str = "confusion_matrix.png",
) -> Path:
    """Plot confusion matrix heatmap at the optimal threshold.

    Args:
        eval_dict: Full evaluation dictionary from evaluator.
        output_dir: Directory to save the image.
        filename: Output filename.

    Returns:
        Path to the saved image.
    """
    _apply_style()
    opt = eval_dict.get("optimal_threshold", {})
    cm = opt.get("confusion_matrix", {})
    model_id = eval_dict.get("model_id", "?")
    threshold = opt.get("value", "?")

    tn, fp, fn, tp = cm.get("tn", 0), cm.get("fp", 0), cm.get("fn", 0), cm.get("tp", 0)
    matrix = np.array([[tn, fp], [fn, tp]])
    labels = np.array([[f"TN\n{tn:,}", f"FP\n{fp:,}"], [f"FN\n{fn:,}", f"TP\n{tp:,}"]])

    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(matrix, cmap="Blues", aspect="auto")

    # Annotate cells
    for i in range(2):
        for j in range(2):
            color = "white" if matrix[i, j] > matrix.max() * 0.6 else "black"
            ax.text(j, i, labels[i, j], ha="center", va="center", fontsize=13, color=color)

    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(["Predicted 0", "Predicted 1"])
    ax.set_yticklabels(["Actual 0", "Actual 1"])
    ax.set_title(f"{model_id} — Confusion Matrix (threshold={threshold})")
    fig.colorbar(im, ax=ax, shrink=0.8)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_roc_curve(
    eval_dict: dict,
    output_dir: Path,
    filename: str = "roc_curve.png",
) -> Path:
    """Plot ROC curve with AUC annotation and diagonal reference.

    Args:
        eval_dict: Full evaluation dictionary from evaluator.
        output_dir: Directory to save the image.
        filename: Output filename.

    Returns:
        Path to the saved image.
    """
    _apply_style()
    disc = eval_dict.get("discrimination", {})
    roc = disc.get("roc_curve", {})
    auc = disc.get("auc_roc", 0.0)
    model_id = eval_dict.get("model_id", "?")

    fpr = np.array(roc.get("fpr", [0, 1]))
    tpr = np.array(roc.get("tpr", [0, 1]))

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(fpr, tpr, color=_COLORS["primary"], lw=2, label=f"ROC (AUC = {auc:.4f})")
    ax.plot([0, 1], [0, 1], color=_COLORS["neutral"], lw=1, ls="--", label="Random classifier")
    ax.fill_between(fpr, tpr, alpha=0.1, color=_COLORS["primary"])

    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title(f"{model_id} — ROC Curve")
    ax.legend(loc="lower right")
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.grid(True, alpha=0.3)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_pr_curve(
    eval_dict: dict,
    output_dir: Path,
    filename: str = "pr_curve.png",
) -> Path:
    """Plot Precision-Recall curve with AUC-PR annotation and random baseline.

    Args:
        eval_dict: Full evaluation dictionary from evaluator.
        output_dir: Directory to save the image.
        filename: Output filename.

    Returns:
        Path to the saved image.
    """
    _apply_style()
    disc = eval_dict.get("discrimination", {})
    pr = disc.get("pr_curve", {})
    auc_pr = disc.get("auc_pr", 0.0)
    model_id = eval_dict.get("model_id", "?")

    precision = np.array(pr.get("precision", [1, 0]))
    recall = np.array(pr.get("recall", [0, 1]))

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(recall, precision, color=_COLORS["primary"], lw=2,
            label=f"PR Curve (AUC-PR = {auc_pr:.4f})")
    ax.fill_between(recall, precision, alpha=0.1, color=_COLORS["primary"])

    # Baseline: horizontal line at positive_rate
    label_dist = eval_dict.get("label_distribution", {})
    pos_rate = label_dist.get("positive_rate", 0.0)
    if pos_rate > 0:
        ax.axhline(y=pos_rate, color=_COLORS["neutral"], ls="--", lw=1,
                   label=f"Random ({pos_rate:.2%})")

    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title(f"{model_id} — PR Curve")
    ax.legend(loc="upper right")
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.grid(True, alpha=0.3)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_precision_recall_f1(
    eval_dict: dict,
    output_dir: Path,
    filename: str = "precision_recall_f1.png",
) -> Path:
    """Plot Precision, Recall, and F1 vs. decision threshold.

    Args:
        eval_dict: Full evaluation dictionary from evaluator.
        output_dir: Directory to save the image.
        filename: Output filename.

    Returns:
        Path to the saved image.
    """
    _apply_style()
    ta = eval_dict.get("threshold_analysis", {})
    model_id = eval_dict.get("model_id", "?")
    opt = eval_dict.get("optimal_threshold", {})

    thresholds = ta.get("thresholds", [])
    precision = ta.get("precision", [])
    recall = ta.get("recall", [])
    f1 = ta.get("f1", [])

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(thresholds, precision, color=_COLORS["primary"], lw=2, marker="o", ms=4, label="Precision")
    ax.plot(thresholds, recall, color=_COLORS["secondary"], lw=2, marker="s", ms=4, label="Recall")
    ax.plot(thresholds, f1, color=_COLORS["tertiary"], lw=2, marker="^", ms=4, label="F1 Score")

    # Mark optimal threshold
    opt_val = opt.get("value")
    if opt_val is not None:
        ax.axvline(x=opt_val, color=_COLORS["neutral"], ls="--", lw=1, alpha=0.7)
        ax.annotate(
            f"Optimal\n({opt_val:.2f})",
            xy=(opt_val, opt.get("f1", 0)),
            xytext=(opt_val + 0.08, opt.get("f1", 0) + 0.05),
            arrowprops=dict(arrowstyle="->", color=_COLORS["neutral"]),
            fontsize=9,
        )

    ax.set_xlabel("Decision Threshold")
    ax.set_ylabel("Score")
    ax.set_title(f"{model_id} — Precision / Recall / F1 vs. Threshold")
    ax.legend(loc="best")
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.grid(True, alpha=0.3)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_ranking_metrics(
    eval_dict: dict,
    output_dir: Path,
    filename: str = "ranking_metrics.png",
) -> Path:
    """Plot grouped bar chart for MAP@k and NDCG@k.

    Args:
        eval_dict: Full evaluation dictionary from evaluator.
        output_dir: Directory to save the image.
        filename: Output filename.

    Returns:
        Path to the saved image.
    """
    _apply_style()
    ranking = eval_dict.get("ranking", {})
    model_id = eval_dict.get("model_id", "?")

    k_labels = ["@100", "@500", "@1000"]
    map_vals = [ranking.get(f"map_{k}", 0) for k in [100, 500, 1000]]
    ndcg_vals = [ranking.get(f"ndcg_{k}", 0) for k in [100, 500, 1000]]

    x = np.arange(len(k_labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(6, 4.5))
    bars1 = ax.bar(x - width / 2, map_vals, width, label="MAP@k", color=_COLORS["primary"])
    bars2 = ax.bar(x + width / 2, ndcg_vals, width, label="NDCG@k", color=_COLORS["tertiary"])

    # Value labels on bars
    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01, f"{h:.3f}", ha="center", va="bottom", fontsize=8)
    for bar in bars2:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01, f"{h:.3f}", ha="center", va="bottom", fontsize=8)

    ax.set_xlabel("k")
    ax.set_ylabel("Score")
    ax.set_title(f"{model_id} — Ranking Metrics")
    ax.set_xticks(x)
    ax.set_xticklabels(k_labels)
    ax.legend()
    ax.set_ylim([0.0, 1.15])
    ax.grid(True, alpha=0.3, axis="y")

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_recall_precision_at_k(
    eval_dict: dict,
    output_dir: Path,
    filename: str = "recall_precision_at_k.png",
) -> Path:
    """Plot Recall@K and Precision@K as a function of K.

    Shows dual lines: Recall@K (typically rises with K) and Precision@K
    (typically falls with K), illustrating the recall-precision trade-off
    as the ranked cutoff increases.

    Args:
        eval_dict: Full evaluation dictionary from evaluator (must contain
            "recall_precision_at_k" sub-dict).
        output_dir: Directory to save the image.
        filename: Output filename.

    Returns:
        Path to the saved image.
    """
    _apply_style()
    model_id = eval_dict.get("model_id", "?")
    rp = eval_dict.get("recall_precision_at_k", {})

    from sip_engine.classifiers.evaluation.evaluator import RECALL_K_VALUES

    k_vals = RECALL_K_VALUES
    recall_vals = [rp.get(f"recall_{k}", 0.0) for k in k_vals]
    prec_vals = [rp.get(f"precision_{k}", 0.0) for k in k_vals]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(k_vals, recall_vals, marker="o", color=_COLORS["tertiary"], label="Recall@K", linewidth=2)
    ax.plot(k_vals, prec_vals, marker="s", color=_COLORS["secondary"], label="Precision@K", linewidth=2)

    # Annotate each point
    for k, r, p in zip(k_vals, recall_vals, prec_vals):
        ax.annotate(f"{r:.3f}", (k, r), textcoords="offset points", xytext=(0, 6), fontsize=8, ha="center", color=_COLORS["tertiary"])
        ax.annotate(f"{p:.3f}", (k, p), textcoords="offset points", xytext=(0, -14), fontsize=8, ha="center", color=_COLORS["secondary"])

    ax.set_xlabel("K (rank cutoff)")
    ax.set_ylabel("Score")
    ax.set_title(f"{model_id} — Recall@K and Precision@K")
    ax.set_xscale("log")
    ax.set_xticks(k_vals)
    ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
    ax.set_ylim([0.0, 1.1])
    ax.legend()
    ax.grid(True, alpha=0.3)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_score_distribution(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    eval_dict: dict,
    output_dir: Path,
    filename: str = "score_distribution.png",
) -> Path:
    """Plot histogram of predicted scores for positive vs. negative class.

    Args:
        y_true: Binary ground truth labels.
        y_scores: Predicted probabilities.
        eval_dict: Full evaluation dictionary (for model_id).
        output_dir: Directory to save the image.
        filename: Output filename.

    Returns:
        Path to the saved image.
    """
    _apply_style()
    model_id = eval_dict.get("model_id", "?")

    scores_pos = y_scores[y_true == 1]
    scores_neg = y_scores[y_true == 0]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(scores_neg, bins=50, alpha=0.6, color=_COLORS["primary"], label=f"Negative (n={len(scores_neg):,})", density=True)
    ax.hist(scores_pos, bins=50, alpha=0.6, color=_COLORS["secondary"], label=f"Positive (n={len(scores_pos):,})", density=True)

    # Mark optimal threshold
    opt = eval_dict.get("optimal_threshold", {})
    opt_val = opt.get("value")
    if opt_val is not None:
        ax.axvline(x=opt_val, color=_COLORS["neutral"], ls="--", lw=1.5, label=f"Optimal threshold ({opt_val:.2f})")

    ax.set_xlabel("Predicted Probability")
    ax.set_ylabel("Density")
    ax.set_title(f"{model_id} — Score Distribution")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_calibration_summary(
    eval_dict: dict,
    output_dir: Path,
    filename: str = "calibration_summary.png",
) -> Path:
    """Plot Brier Score vs. baseline as a bar chart.

    Args:
        eval_dict: Full evaluation dictionary from evaluator.
        output_dir: Directory to save the image.
        filename: Output filename.

    Returns:
        Path to the saved image.
    """
    _apply_style()
    calib = eval_dict.get("calibration", {})
    model_id = eval_dict.get("model_id", "?")

    brier = calib.get("brier_score", 0)
    baseline = calib.get("brier_baseline", 0)

    labels = ["Model\nBrier Score", "Random Baseline\n(pos_rate × (1−pos_rate))"]
    values = [brier, baseline]
    colors = [_COLORS["primary"], _COLORS["neutral"]]

    fig, ax = plt.subplots(figsize=(5, 4))
    bars = ax.bar(labels, values, color=colors, width=0.5)

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.002, f"{val:.4f}", ha="center", va="bottom", fontsize=10)

    ax.set_ylabel("Brier Score (lower is better)")
    ax.set_title(f"{model_id} — Calibration")
    ax.set_ylim([0, max(values) * 1.3 if max(values) > 0 else 0.5])
    ax.grid(True, alpha=0.3, axis="y")

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_shap_importance(
    eval_dict: dict,
    output_dir: Path,
    filename: str = "shap_importance.png",
) -> Path | None:
    """Plot a horizontal bar chart of top-10 features by mean absolute SHAP value.

    Args:
        eval_dict: Full evaluation dictionary from evaluator (must contain "shap.top_features").
        output_dir: Directory to save the image.
        filename: Output filename.

    Returns:
        Path to the saved image, or None if no SHAP data is available.
    """
    shap = eval_dict.get("shap", {})
    top_features = shap.get("top_features", [])
    if not top_features:
        return None

    _apply_style()
    model_id = eval_dict.get("model_id", "?")

    features = [e["feature"] for e in top_features]
    values = [e["mean_abs_shap"] for e in top_features]

    # Reverse so highest bar is at the top
    features = features[::-1]
    values = values[::-1]

    fig, ax = plt.subplots(figsize=(8, max(4, len(features) * 0.45 + 1)))
    bars = ax.barh(features, values, color=_COLORS["primary"], alpha=0.85)

    # Value labels at end of each bar
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_width() + max(values) * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.4f}",
            va="center",
            fontsize=8,
        )

    ax.set_xlabel("Mean |SHAP value| (test set)")
    ax.set_title(f"{model_id} — SHAP Feature Importance (top {len(top_features)})")
    ax.set_xlim([0, max(values) * 1.18])
    ax.grid(True, alpha=0.3, axis="x")
    fig.tight_layout()

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path)
    plt.close(fig)
    return path


# =============================================================================
# Orchestrator
# =============================================================================


def generate_all_charts(
    eval_dict: dict,
    y_true: np.ndarray,
    y_scores: np.ndarray,
    output_dir: Path,
) -> list[Path]:
    """Generate all evaluation charts for a single model.

    Args:
        eval_dict: Full evaluation dictionary from evaluator.
        y_true: Binary ground truth labels.
        y_scores: Predicted probabilities.
        output_dir: Directory for images (e.g., artifacts/evaluation/M1/images/).

    Returns:
        List of paths to all generated image files.
    """
    model_id = eval_dict.get("model_id", "?")
    model_suffix = f"_{model_id.lower()}" if model_id != "?" else ""
    logger.info("Generating charts for %s → %s", model_id, output_dir)

    paths: list[Path] = []

    paths.append(plot_confusion_matrix(eval_dict, output_dir, filename=f"confusion_matrix{model_suffix}.png"))
    paths.append(plot_roc_curve(eval_dict, output_dir, filename=f"roc_curve{model_suffix}.png"))
    paths.append(plot_pr_curve(eval_dict, output_dir, filename=f"pr_curve{model_suffix}.png"))
    paths.append(plot_precision_recall_f1(eval_dict, output_dir, filename=f"precision_recall_f1{model_suffix}.png"))
    paths.append(plot_ranking_metrics(eval_dict, output_dir, filename=f"ranking_metrics{model_suffix}.png"))
    paths.append(plot_recall_precision_at_k(eval_dict, output_dir, filename=f"recall_precision_at_k{model_suffix}.png"))
    paths.append(plot_score_distribution(y_true, y_scores, eval_dict, output_dir, filename=f"score_distribution{model_suffix}.png"))
    paths.append(plot_calibration_summary(eval_dict, output_dir, filename=f"calibration_summary{model_suffix}.png"))

    shap_path = plot_shap_importance(eval_dict, output_dir, filename=f"shap_importance{model_suffix}.png")
    if shap_path is not None:
        paths.append(shap_path)

    logger.info("Generated %d charts for %s", len(paths), model_id)
    return paths
