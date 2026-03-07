# Phase 15 — Context

**Phase:** 15 — Evaluation and Training Module Enhancements
**Discussed:** 2026-03-07
**Status:** Ready for planning

---

## Area 1: Model Selector UX

### Decisions

- **Flag:** Extend the existing `--model` flag to accept one or more model IDs (e.g., `--model M1`, `--model M1 M3`). No separate `--models` flag.
- **Default (no flag):** Show an interactive TUI checkbox picker. Default selection = all 4 models.
- **Scope:** `run-pipeline`, `train`, and `evaluate` all respect `--model` identically.
- **Missing artifact:** Hard fail with a clear error message. No auto-training fallback.
  - Error format: `"M2 artifact 'model.pkl' not found — run: python -m sip_engine train --model M2"`
- **Group aliases:** Not supported. Only explicit IDs: M1, M2, M3, M4.

### Constraints for planner

- The TUI picker must integrate with the existing Rich-based TUI (see `ui/config_screen.py` and `ui/progress.py`).
- `--model` must be consistent across all three CLI entry points — do not solve it three separate ways.
- Omitting `--model` must show the TUI picker even in non-interactive contexts (e.g., piped input) — handle gracefully (fall back to all 4 if stdin is not a TTY).

---

## Area 2: AUC-PR and Brier Skill Score

### Decisions

**AUC-PR:**
- Add a new report section: `## 1b. Discrimination — PR Curve`
- Show AUC-PR as a scalar metric in that section's table
- Generate a `pr_curve_m{n}.png` chart (e.g., `pr_curve_m1.png`) in the `images/` directory
- The PR curve chart plots Precision (y-axis) vs Recall (x-axis) with AUC-PR annotated

**Brier Skill Score (BSS):**
- Keep raw Brier Score and Brier Baseline (no removal)
- Add BSS as a new row: `BSS = 1 - (Brier / Baseline)`
- Include a note: `BSS > 0 = better than random; BSS = 1 = perfect`
- Placement: Section 6 (Calibration), alongside existing rows

**Summary table and files:**
- Add `auc_pr` and `brier_skill_score` columns to `summary.json`, `summary.csv`, and the console summary table printed by `_print_summary_table()`

### Constraints for planner

- `sklearn.metrics.precision_recall_curve` and `average_precision_score` are the correct functions for AUC-PR — do not reimplement.
- BSS formula: `BSS = 1.0 - (brier_score / brier_baseline)`. Guard against `brier_baseline == 0` (return 0.0).
- The new `pr_curve` data (precision array, recall array, thresholds array) should be stored in `eval_dict["discrimination"]` alongside `roc_curve`.
- Chart file naming must follow the existing pattern in `visualizer.py`.

---

## Area 3: Named Model Artifacts

### Decisions

**Naming format:** `model_run{N:03d}_{metric}.pkl`
- N is zero-padded to 3 digits (001, 002, ...)
- `metric` is the CV scoring metric used during training (e.g., `auc_roc`, `f1`)
- Examples: `model_run001_auc_roc.pkl`, `model_run002_f1.pkl`

**Canonical file:** `model.pkl` always exists and always points to the latest run (it is a copy, not a symlink — for cross-platform compatibility). All existing code that reads `model.pkl` continues to work unchanged.

**Archiving on new training run:**
1. Before saving new artifacts, move existing `model.pkl` and `training_report.json` and `feature_registry.json` into `old/` subfolder (flat — not date-keyed, because run-numbered files are already self-identifying).
2. Save the new run as `model_run{N}_{metric}.pkl` + copy to `model.pkl`.
3. N is determined by scanning existing run files in `old/` + current dir to find the next available number.

**Evaluator --artifact flag:**
- `evaluate --model M1 --artifact model_run001_auc_roc.pkl` loads that specific file instead of `model.pkl`.
- The artifact path is resolved relative to `artifacts/models/M1/` (and `old/` as fallback).
- If the specified artifact does not exist, hard fail with a clear error.

**Companion files:** Each run file should have a matching report:
- `model_run001_auc_roc.pkl` → `training_report_run001_auc_roc.json`
- The canonical copies remain `model.pkl` and `training_report.json`

### Constraints for planner

- No symlinks — use file copies for cross-platform compatibility (Windows does not support symlinks without admin rights).
- Run number scanning must be deterministic and collision-safe even if runs from different days are interleaved.
- The `old/` directory is flat (not date-keyed) — run files are self-identifying by number.
- Existing `artifacts/models/M1/old/2026-03-04/` subdirectories (created by previous archiving logic) must not be touched or removed.

---

## Area 4: Backward Compatibility

### Decisions

- **model.pkl remains canonical.** All existing code (`evaluator.py`, `pipeline.py`, `comparison.py`) that loads `model.pkl` requires no changes.
- **No migration of existing artifacts.** Existing `model.pkl` files on disk are left in place. On the next training run, the old `model.pkl` is moved to `old/` and a new run-numbered file + fresh `model.pkl` are written.
- **No manifest file needed.** `model.pkl` is the manifest — it is always the current model.
- **--artifact flag is additive.** It does not break any existing workflow; omitting it gives the current behavior.

### Constraints for planner

- Do not remove or rename any existing artifact paths in `evaluator.py._load_artifacts()` — only add the optional `--artifact` resolution path.
- The trainer's archiving logic must guard against the case where `model.pkl` does not yet exist (first-ever run).

---

## Deferred Ideas (out of scope for Phase 15)

- Named group aliases (`--model all`, `--model imbalanced`) — noted for future phase
- `--artifact` targeting for `run-pipeline` (not just `evaluate`) — future phase
- Model registry with metadata search (find "best AUC-PR run") — future phase
- REST API exposure of model selector — future phase (REST API phase)
