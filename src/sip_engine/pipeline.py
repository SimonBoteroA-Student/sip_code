"""Pipeline coordinator — orchestrates the 6-step SIP pipeline.

Provides a typed PipelineConfig, per-step run_*() functions with lazy imports,
and a run_pipeline() orchestrator with --start-from / --force support.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PipelineConfig:
    """Immutable configuration shared across all pipeline steps."""

    n_jobs: int
    n_iter: int
    cv_folds: int
    max_ram_gb: int
    device: str
    force: bool = False
    model: list[str] | None = None
    quick: bool = False
    disable_rocm: bool = False
    show_stats: bool = True


# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------

STEP_NAMES: tuple[str, ...] = (
    "rcac",
    "labels",
    "iric",
    "features",
    "train",
    "evaluate",
)

_STEP_LABELS: dict[str, str] = {
    "rcac": "[1/6] RCAC",
    "labels": "[2/6] Labels",
    "iric": "[3/6] IRIC Scores",
    "features": "[4/6] Features",
    "train": "[5/6] Training Models",
    "evaluate": "[6/6] Evaluation",
}


# ---------------------------------------------------------------------------
# Per-step run functions (lazy imports to avoid circular deps)
# ---------------------------------------------------------------------------

def run_rcac(cfg: PipelineConfig) -> Path:
    """Build the RCAC corruption-antecedent corpus."""
    from sip_engine.shared.data.rcac_builder import build_rcac

    return build_rcac(force=cfg.force)


def run_labels(cfg: PipelineConfig) -> Path:
    """Build M1/M2/M3/M4 target labels."""
    from sip_engine.shared.data.label_builder import build_labels

    return build_labels(force=cfg.force)


def run_features(cfg: PipelineConfig) -> Path:
    """Build the feature matrix (contratos / procesos / proveedores)."""
    from sip_engine.classifiers.features.pipeline import build_features

    return build_features(
        force=cfg.force,
        n_jobs=cfg.n_jobs,
        max_ram_gb=cfg.max_ram_gb,
        device=cfg.device,
        interactive=False,
        show_progress=True,
    )


def run_iric(cfg: PipelineConfig) -> Path:
    """Build IRIC irregularity-risk-index scores."""
    from sip_engine.classifiers.iric.pipeline import build_iric

    return build_iric(force=cfg.force)


def run_train(cfg: PipelineConfig) -> list[Path]:
    """Train one or all XGBoost models."""
    from sip_engine.classifiers.models.trainer import train_model, MODEL_IDS

    model_ids: Sequence[str] = cfg.model if cfg.model else MODEL_IDS
    results: list[Path] = []
    for mid in model_ids:
        path = train_model(
            model_id=mid,
            force=cfg.force,
            quick=cfg.quick,
            n_iter=cfg.n_iter,
            n_jobs=cfg.n_jobs,
            device=cfg.device,
            disable_rocm=cfg.disable_rocm,
            interactive=False,
            show_stats=cfg.show_stats,
        )
        results.append(path)
    return results


def run_evaluate(cfg: PipelineConfig) -> Path:
    """Evaluate one or all trained models."""
    from sip_engine.classifiers.evaluation.evaluator import (
        evaluate_all,
        evaluate_model,
        MODEL_IDS,
    )

    model_ids = cfg.model if cfg.model else MODEL_IDS
    if len(model_ids) == len(MODEL_IDS):
        return evaluate_all()
    for mid in model_ids:
        evaluate_model(model_id=mid)
    return Path("artifacts/evaluation")


# ---------------------------------------------------------------------------
# Step dispatch table
# ---------------------------------------------------------------------------

_STEP_FN_NAMES: dict[str, str] = {
    "rcac": "run_rcac",
    "labels": "run_labels",
    "features": "run_features",
    "iric": "run_iric",
    "train": "run_train",
    "evaluate": "run_evaluate",
}

# Convenience alias for introspection / testing
_STEP_FNS: dict[str, object] = {
    "rcac": run_rcac,
    "labels": run_labels,
    "features": run_features,
    "iric": run_iric,
    "train": run_train,
    "evaluate": run_evaluate,
}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(cfg: PipelineConfig, start_from: str | None = None) -> None:
    """Run the full SIP pipeline (or resume from *start_from*).

    Parameters
    ----------
    cfg:
        Shared configuration for every step.
    start_from:
        Optional step name to resume from (e.g. ``"train"``).
        Skips all earlier steps.

    Raises
    ------
    ValueError
        If *start_from* is not a recognised step name.
    """
    from rich.console import Console
    from rich.panel import Panel

    con = Console()

    # Validate start_from ---------------------------------------------------
    if start_from is not None and start_from not in STEP_NAMES:
        raise ValueError(
            f"Unknown step '{start_from}'. "
            f"Valid steps: {', '.join(STEP_NAMES)}"
        )

    steps = list(STEP_NAMES)
    if start_from is not None:
        idx = steps.index(start_from)
        steps = steps[idx:]
        con.print(
            f"\n  [yellow]⚠ Starting from '{start_from}' "
            f"— assumes earlier steps have been run[/yellow]"
        )

    # Config banner ---------------------------------------------------------
    con.print(
        f"\n  [bold]Config:[/bold] "
        f"CPU cores=[cyan]{cfg.n_jobs}[/]  "
        f"HP iters=[cyan]{cfg.n_iter}[/]  "
        f"CV folds=[cyan]{cfg.cv_folds}[/]  "
        f"RAM=[cyan]{cfg.max_ram_gb} GB[/]  "
        f"Device=[cyan]{cfg.device}[/]\n"
    )

    # Execute steps ---------------------------------------------------------
    import sip_engine.pipeline as _self_mod

    for step in steps:
        label = _STEP_LABELS[step]
        con.rule(f"[bold]{label}")

        fn = getattr(_self_mod, _STEP_FN_NAMES[step])
        result = fn(cfg)

        # Post-step feedback
        if step == "train" and isinstance(result, list):
            for path in result:
                mid = path.name  # directory name is the model id
                con.print(f"  [green]✓[/green] Model {mid} trained: {path}")
        elif step == "evaluate":
            con.print(f"  [green]✓[/green] Evaluation complete: {result}")

    # Completion panel ------------------------------------------------------
    con.print()
    con.print(
        Panel(
            "  All stages completed successfully.",
            title="Pipeline Complete",
            border_style="bright_green",
        )
    )
