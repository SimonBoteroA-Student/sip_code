"""V1-vs-V2 comparison report generator for Phase 10 data leakage fix.

Provides two functions:
- backup_v1_artifacts(): snapshot current artifacts to artifacts/v1_baseline/
- generate_comparison_report(): produce comparison.md + comparison.json

Usage:
    python -m sip_engine backup-v1
    python -m sip_engine compare-v1v2
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sip_engine.config import get_settings

logger = logging.getLogger(__name__)

# Subdirectories to back up (rcac excluded — unchanged by Phase 10)
_BACKUP_DIRS = ["evaluation", "features", "iric", "labels", "models"]


def backup_v1_artifacts(artifacts_dir: Path | None = None) -> Path:
    """Copy current artifacts to artifacts/v1_baseline/ for comparison.

    Copies: evaluation/, features/, iric/, labels/, models/ subdirectories.
    Skips: rcac/ (unchanged by Phase 10 fixes).

    Raises FileExistsError if v1_baseline/ already exists (prevent accidental overwrite).
    Returns path to v1_baseline directory.
    """
    if artifacts_dir is None:
        artifacts_dir = get_settings().artifacts_dir

    v1_dir = artifacts_dir / "v1_baseline"
    if v1_dir.exists():
        raise FileExistsError(
            f"v1_baseline already exists at {v1_dir}. "
            "Delete it manually if you want to re-backup."
        )

    v1_dir.mkdir(parents=True)

    for subdir_name in _BACKUP_DIRS:
        src = artifacts_dir / subdir_name
        if src.exists():
            shutil.copytree(src, v1_dir / subdir_name)
            logger.info("Backed up %s -> %s", src, v1_dir / subdir_name)
        else:
            logger.warning("Skipping %s (not found)", src)

    logger.info("V1 baseline backup complete: %s", v1_dir)
    return v1_dir


def _load_json_safe(path: Path) -> dict | None:
    """Load a JSON file, returning None if missing."""
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _build_metrics_comparison(v1_summary: dict | None, v2_summary: dict | None) -> dict:
    """Build per-model metrics comparison from summary.json files."""
    metrics = {}
    model_ids = ["M1", "M2", "M3", "M4"]
    metric_keys = [
        "auc_roc", "map_at_100", "map_at_1000",
        "ndcg_at_100", "ndcg_at_1000",
        "brier_score",
        "precision_at_0.5", "recall_at_0.5",
    ]

    for mid in model_ids:
        metrics[mid] = {}
        v1_model = (v1_summary or {}).get(mid, {})
        v2_model = (v2_summary or {}).get(mid, {})

        for key in metric_keys:
            v1_val = v1_model.get(key)
            v2_val = v2_model.get(key)
            delta = None
            if v1_val is not None and v2_val is not None:
                delta = round(v2_val - v1_val, 6)
            metrics[mid][key] = {"v1": v1_val, "v2": v2_val, "delta": delta}

    return metrics


def _build_label_distribution(v1_summary: dict | None, v2_summary: dict | None) -> dict:
    """Extract label positive counts from summaries."""
    dist = {}
    for mid in ["M1", "M2", "M3", "M4"]:
        v1_pos = (v1_summary or {}).get(mid, {}).get("n_positive_test")
        v2_pos = (v2_summary or {}).get(mid, {}).get("n_positive_test")
        dist[mid] = {"v1_positives": v1_pos, "v2_positives": v2_pos}
    return dist


def _format_metric_table(metrics: dict) -> str:
    """Format metrics as a Markdown table."""
    lines = ["| Model | Metric | v1 | v2 | Delta |", "|-------|--------|-----|-----|-------|"]
    for mid, mdata in metrics.items():
        for key, vals in mdata.items():
            v1 = f"{vals['v1']:.4f}" if vals['v1'] is not None else "—"
            v2 = f"{vals['v2']:.4f}" if vals['v2'] is not None else "PENDING"
            delta = f"{vals['delta']:+.4f}" if vals['delta'] is not None else "—"
            lines.append(f"| {mid} | {key} | {v1} | {v2} | {delta} |")
    return "\n".join(lines)


def _format_label_table(dist: dict) -> str:
    """Format label distribution as a Markdown table."""
    lines = ["| Model | v1 Positives | v2 Positives |", "|-------|-------------|-------------|"]
    for mid, vals in dist.items():
        v1 = str(vals['v1_positives']) if vals['v1_positives'] is not None else "—"
        v2 = str(vals['v2_positives']) if vals['v2_positives'] is not None else "PENDING"
        lines.append(f"| {mid} | {v1} | {v2} |")
    return "\n".join(lines)


def generate_comparison_report(
    v1_dir: Path | None = None,
    v2_dir: Path | None = None,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Generate v1-vs-v2 comparison report in both Markdown and JSON formats.

    Reads:
    - v1_dir/evaluation/summary.json (v1 metrics)
    - v2_dir/evaluation/summary.json (v2 metrics)

    Produces:
    - output_dir/comparison.md — human-readable Markdown
    - output_dir/comparison.json — machine-readable JSON

    Returns (md_path, json_path).
    Gracefully handles missing v2 files (reports "PENDING — run pipeline first").
    """
    settings = get_settings()
    if v1_dir is None:
        v1_dir = settings.artifacts_dir / "v1_baseline"
    if v2_dir is None:
        v2_dir = settings.artifacts_dir
    if output_dir is None:
        output_dir = settings.artifacts_dir / "evaluation"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load summaries
    v1_summary = _load_json_safe(v1_dir / "evaluation" / "summary.json")
    v2_summary = _load_json_safe(v2_dir / "evaluation" / "summary.json")

    if v1_summary is None:
        logger.warning("v1 summary.json not found at %s", v1_dir / "evaluation" / "summary.json")
    if v2_summary is None:
        logger.warning("v2 summary.json not found — run pipeline first")

    # Build comparison data
    metrics = _build_metrics_comparison(v1_summary, v2_summary)
    label_dist = _build_label_distribution(v1_summary, v2_summary)
    generated_at = datetime.now(timezone.utc).isoformat()

    # ---- JSON output ----
    comparison_data = {
        "version": "v1_vs_v2",
        "fixes_applied": ["duration_leakage", "m2_label_bug"],
        "metrics": metrics,
        "label_distribution": label_dist,
        "generated_at": generated_at,
    }
    json_path = output_dir / "comparison.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(comparison_data, f, indent=2)
    logger.info("Comparison JSON written: %s", json_path)

    # ---- Markdown output ----
    md_lines = [
        "# V1 vs V2 Comparison Report",
        "",
        "## Summary",
        "",
        "**Fixes applied in v2:**",
        "1. **Duration leakage fix**: `duracion_contrato_dias` now parsed from pre-amendment "
        '"Duración del contrato" text, not post-amendment end date',
        "2. **M2 label bug fix**: M2 now uses non-zero \"Dias adicionados\" as primary source "
        "(OR with EXTENSION from adiciones). Expected ~39K positives instead of 19.",
        "",
        "## Metrics Comparison",
        "",
        _format_metric_table(metrics),
        "",
        "## Label Distribution",
        "",
        _format_label_table(label_dist),
        "",
        f"*Generated: {generated_at}*",
    ]
    md_path = output_dir / "comparison.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    logger.info("Comparison Markdown written: %s", md_path)

    return md_path, json_path
