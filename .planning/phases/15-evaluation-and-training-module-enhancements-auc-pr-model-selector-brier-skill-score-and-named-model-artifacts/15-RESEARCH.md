# Phase 15: Evaluation and Training Module Enhancements - Research

**Researched:** 2026-03-07
**Domain:** ML evaluation metrics, CLI UX, artifact management
**Confidence:** HIGH

## Summary

Phase 15 adds four interconnected but logically separable features to the SIP engine: (1) a TUI model selector for the `--model` flag, (2) AUC-PR metric and PR curve chart, (3) Brier Skill Score to the calibration section, and (4) named/versioned model artifacts with archival workflow. All four areas touch existing, well-understood code with clear insertion points.

The codebase already imports `sklearn.metrics` extensively, uses Rich for TUI, matplotlib for charts, and has established patterns for artifact I/O. The new features follow established patterns rather than introducing new paradigms. The main risk areas are: ensuring the multi-model `--model` flag works consistently across all three CLI entry points (`run-pipeline`, `train`, `evaluate`), PR curve array serialization (precision/recall arrays have different lengths than the thresholds array), and collision-safe run number scanning for named artifacts.

**Primary recommendation:** Implement in this order: (1) AUC-PR + BSS (pure metric additions, self-contained), (2) Named model artifacts (trainer changes), (3) Model selector TUI (CLI/UX layer).

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Area 1 - Model Selector UX:**
- Extend the existing `--model` flag to accept one or more model IDs (e.g., `--model M1`, `--model M1 M3`). No separate `--models` flag.
- Default (no flag): Show an interactive TUI checkbox picker. Default selection = all 4 models.
- Scope: `run-pipeline`, `train`, and `evaluate` all respect `--model` identically.
- Missing artifact: Hard fail with a clear error message. No auto-training fallback.
  - Error format: `"M2 artifact 'model.pkl' not found -- run: python -m sip_engine train --model M2"`
- Group aliases: Not supported. Only explicit IDs: M1, M2, M3, M4.
- The TUI picker must integrate with the existing Rich-based TUI (see `ui/config_screen.py` and `ui/progress.py`).
- `--model` must be consistent across all three CLI entry points -- do not solve it three separate ways.
- Omitting `--model` must show the TUI picker even in non-interactive contexts (e.g., piped input) -- handle gracefully (fall back to all 4 if stdin is not a TTY).

**Area 2 - AUC-PR and Brier Skill Score:**
- Add a new report section: `## 1b. Discrimination -- PR Curve`
- Show AUC-PR as a scalar metric in that section's table
- Generate a `pr_curve_m{n}.png` chart (e.g., `pr_curve_m1.png`) in the `images/` directory
- The PR curve chart plots Precision (y-axis) vs Recall (x-axis) with AUC-PR annotated
- Keep raw Brier Score and Brier Baseline (no removal)
- Add BSS as a new row: `BSS = 1 - (Brier / Baseline)`
- Include a note: `BSS > 0 = better than random; BSS = 1 = perfect`
- Placement: Section 6 (Calibration), alongside existing rows
- Add `auc_pr` and `brier_skill_score` columns to `summary.json`, `summary.csv`, and the console summary table
- `sklearn.metrics.precision_recall_curve` and `average_precision_score` are the correct functions for AUC-PR -- do not reimplement.
- BSS formula: `BSS = 1.0 - (brier_score / brier_baseline)`. Guard against `brier_baseline == 0` (return 0.0).
- The new `pr_curve` data (precision array, recall array, thresholds array) should be stored in `eval_dict["discrimination"]` alongside `roc_curve`.
- Chart file naming must follow the existing pattern in `visualizer.py`.

**Area 3 - Named Model Artifacts:**
- Naming format: `model_run{N:03d}_{metric}.pkl`
- N is zero-padded to 3 digits (001, 002, ...)
- `metric` is the CV scoring metric used during training (e.g., `auc_roc`, `f1`)
- Canonical file: `model.pkl` always exists and always points to the latest run (it is a copy, not a symlink -- for cross-platform compatibility).
- Archiving on new training run: (1) Before saving new artifacts, move existing `model.pkl` and `training_report.json` and `feature_registry.json` into `old/` subfolder (flat -- not date-keyed). (2) Save the new run as `model_run{N}_{metric}.pkl` + copy to `model.pkl`. (3) N is determined by scanning existing run files in `old/` + current dir.
- Evaluator `--artifact` flag: `evaluate --model M1 --artifact model_run001_auc_roc.pkl` loads that specific file instead of `model.pkl`. Path resolved relative to `artifacts/models/M1/` (and `old/` as fallback). If artifact does not exist, hard fail.
- Companion files: `model_run001_auc_roc.pkl` -> `training_report_run001_auc_roc.json`
- Canonical copies remain `model.pkl` and `training_report.json`
- No symlinks -- use file copies for cross-platform compatibility.
- Run number scanning must be deterministic and collision-safe even if runs from different days are interleaved.
- The `old/` directory is flat (not date-keyed) -- run files are self-identifying by number.
- Existing `artifacts/models/M1/old/2026-03-04/` subdirectories (created by previous archiving logic) must not be touched or removed.

**Area 4 - Backward Compatibility:**
- `model.pkl` remains canonical. All existing code requires no changes.
- No migration of existing artifacts.
- No manifest file needed.
- `--artifact` flag is additive.
- Do not remove or rename any existing artifact paths in `evaluator.py._load_artifacts()` -- only add the optional `--artifact` resolution path.
- The trainer's archiving logic must guard against the case where `model.pkl` does not yet exist (first-ever run).

### Claude's Discretion

None stated -- all decisions are locked.

### Deferred Ideas (OUT OF SCOPE)

- Named group aliases (`--model all`, `--model imbalanced`) -- noted for future phase
- `--artifact` targeting for `run-pipeline` (not just `evaluate`) -- future phase
- Model registry with metadata search (find "best AUC-PR run") -- future phase
- REST API exposure of model selector -- future phase (REST API phase)

</user_constraints>

## Standard Stack

### Core (already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| scikit-learn | 1.8.0 | `precision_recall_curve`, `average_precision_score` for AUC-PR | Already used for all other metrics |
| matplotlib | 3.10.8 | PR curve chart generation | Already used for all evaluation charts |
| Rich | 14.3.3 | TUI checkbox model picker | Already used for config screens and progress |
| joblib | (installed) | Model artifact serialization | Already used for model.pkl save/load |
| shutil | stdlib | File copy/move for artifact archiving | Already used in `_archive_existing_model()` |

### No New Dependencies

All Phase 15 features use existing installed packages. No `pip install` needed.

## Architecture Patterns

### Recommended Project Structure (changes only)

```
src/sip_engine/
├── __main__.py                    # MODIFY: --model nargs='+', --artifact flag
├── pipeline.py                    # MODIFY: PipelineConfig.models list, run_train/run_evaluate
├── classifiers/
│   ├── models/
│   │   └── trainer.py             # MODIFY: named artifact saving, flat old/ archival
│   ├── evaluation/
│   │   ├── evaluator.py           # MODIFY: AUC-PR, BSS, --artifact loading, pr_curve data
│   │   └── visualizer.py          # MODIFY: plot_pr_curve(), updated generate_all_charts()
│   └── ui/
│       └── config_screen.py       # ADD: show_model_picker() TUI checkbox screen
```

### Pattern 1: Multi-Model Flag (nargs='+')

**What:** Change `--model` from `choices` to `nargs='+'` with custom validation.
**When to use:** All three CLI subparsers (train, evaluate, run-pipeline).

**Current code (`__main__.py` line 81-84):**
```python
train_parser.add_argument(
    "--model",
    choices=["M1", "M2", "M3", "M4"],
    help="Train a single model (default: all 4)",
)
```

**New pattern:**
```python
train_parser.add_argument(
    "--model",
    nargs="+",
    choices=["M1", "M2", "M3", "M4"],
    metavar="MODEL",
    help="Model(s) to train (e.g., --model M1 M3). Default: interactive picker or all 4.",
)
```

**Key constraint:** `nargs='+'` with `choices` works correctly in argparse -- each provided value is validated against choices individually. This means `--model M1 M3` validates each of M1 and M3 against `["M1", "M2", "M3", "M4"]`.

**Result type:** `args.model` becomes `list[str] | None` (None when flag omitted).

### Pattern 2: TUI Checkbox Picker

**What:** A Rich-based interactive screen where the user selects models with checkboxes.
**When to use:** When `--model` is omitted and stdin is a TTY.

**Implementation approach:** Reuse the existing `_read_key()` cross-platform keyboard input and `_make_screen_layout()` from `config_screen.py`. Build a new `_CheckboxWidget` class similar to `_DeviceSelector` but with multi-select support using space/enter to toggle, and a separate confirm action.

```python
class _CheckboxWidget:
    """Multi-select checkbox: [ ] M1  [x] M2  [x] M3  [ ] M4"""

    def __init__(self, options: list[str], selected: set[str] | None = None):
        self.options = options
        self.selected = selected or set(options)  # Default: all selected
        self._cursor = 0

    def toggle(self) -> None:
        """Toggle current cursor item."""
        opt = self.options[self._cursor]
        if opt in self.selected:
            self.selected.discard(opt)
        else:
            self.selected.add(opt)

    def render(self) -> Text:
        """Render checkbox line with cursor indicator."""
        ...
```

**Non-interactive fallback:** When `sys.stdin.isatty()` is False, return all 4 models (matching existing convention from `show_config_screen`).

### Pattern 3: Named Artifact Saving

**What:** Save model as both `model_run{N:03d}_{metric}.pkl` and canonical `model.pkl`.
**When to use:** In `trainer.py` after model fitting.

**Run number scanning:**
```python
import re

def _next_run_number(model_dir: Path) -> int:
    """Scan model_dir and model_dir/old/ for existing run files and return next N."""
    pattern = re.compile(r"model_run(\d{3})_")
    existing_numbers: set[int] = set()

    for search_dir in [model_dir, model_dir / "old"]:
        if not search_dir.exists():
            continue
        for f in search_dir.iterdir():
            m = pattern.match(f.name)
            if m:
                existing_numbers.add(int(m.group(1)))

    return max(existing_numbers, default=0) + 1
```

**Critical detail:** The `old/` directory is now flat. The existing `_archive_existing_model()` function currently creates date-keyed subdirectories (`old/2026-03-04/`). This must be changed to move files directly into `old/` (flat). BUT existing date-keyed subdirectories must not be touched or removed.

### Pattern 4: PR Curve Data in eval_dict

**What:** Store PR curve arrays alongside ROC curve in `eval_dict["discrimination"]`.
**When to use:** During metric computation in `evaluator.py`.

```python
from sklearn.metrics import precision_recall_curve, average_precision_score

def _compute_discrimination_metrics(y_true, y_scores):
    # Existing ROC computation
    auc_roc = roc_auc_score(y_true, y_scores)
    fpr, tpr, roc_thresholds = roc_curve(y_true, y_scores)

    # New PR computation
    pr_precision, pr_recall, pr_thresholds = precision_recall_curve(y_true, y_scores)
    auc_pr = average_precision_score(y_true, y_scores)

    return {
        "auc_roc": float(auc_roc),
        "auc_pr": float(auc_pr),
        "roc_curve": {
            "fpr": fpr.tolist(),
            "tpr": tpr.tolist(),
            "thresholds": roc_thresholds.tolist(),
        },
        "pr_curve": {
            "precision": pr_precision.tolist(),
            "recall": pr_recall.tolist(),
            "thresholds": pr_thresholds.tolist(),
        },
    }
```

**CRITICAL GOTCHA:** `precision_recall_curve` returns precision and recall arrays with length `len(thresholds) + 1`. The last element is always precision=1.0, recall=0.0 (a sentinel for the full curve). When serializing to JSON, include all elements. When plotting, matplotlib handles this naturally since you plot precision vs recall (not vs thresholds).

### Pattern 5: Brier Skill Score

**What:** Add BSS = 1 - (brier / baseline) to calibration metrics.
**When to use:** Extend `_compute_calibration_metrics()`.

```python
def _compute_calibration_metrics(y_true, y_scores):
    brier = brier_score_loss(y_true, y_scores)
    positive_rate = float(y_true.mean())
    brier_baseline = positive_rate * (1.0 - positive_rate)

    # BSS: guard against division by zero
    if brier_baseline > 0:
        brier_skill_score = 1.0 - (brier / brier_baseline)
    else:
        brier_skill_score = 0.0

    return {
        "brier_score": float(brier),
        "brier_baseline": float(brier_baseline),
        "brier_skill_score": float(brier_skill_score),
    }
```

### Anti-Patterns to Avoid

- **Symlinks for canonical model.pkl:** Windows requires admin rights for symlinks. Use `shutil.copy2()` instead. This is explicitly locked in CONTEXT.md.
- **Reimplementing AUC-PR:** Do not compute area manually. Use `average_precision_score()` which handles interpolation correctly.
- **Three different --model implementations:** The `--model` parsing must be uniform across train, evaluate, and run-pipeline. Define the argument once via a helper function or copy-paste the identical `add_argument` call.
- **Date-keyed old/ directories for named artifacts:** The new archiving moves files flat into `old/`, NOT into `old/YYYY-MM-DD/`. Run numbers are self-identifying. But do NOT delete existing date-keyed subdirectories.
- **Modifying args.model type assumption:** Currently `args.model` is `str | None`. After the change it becomes `list[str] | None`. Every consumer of `args.model` must be updated.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| AUC-PR computation | Manual precision-recall integration | `sklearn.metrics.average_precision_score` | Handles interpolation, edge cases, and matches the definition used in ML literature |
| PR curve data points | Manual threshold sweep | `sklearn.metrics.precision_recall_curve` | Returns properly sorted arrays with correct endpoints |
| Cross-platform key reading | New keyboard input code | Existing `_read_key()` in `config_screen.py` | Already handles Unix termios + Windows msvcrt |
| File copy (no symlink) | os.link / os.symlink | `shutil.copy2()` | Preserves metadata, works on all platforms |

**Key insight:** All new metric computations have well-tested sklearn implementations. The TUI interaction model is already proven in `config_screen.py` with three working screens (`show_config_screen`, `show_features_config_screen`, `show_pipeline_config_screen`).

## Common Pitfalls

### Pitfall 1: PR Curve Array Length Mismatch

**What goes wrong:** `precision_recall_curve()` returns precision/recall arrays of length N+1 and thresholds of length N. Naively storing them as parallel arrays causes index-out-of-bounds or misalignment.
**Why it happens:** The function appends a sentinel point (precision=1.0, recall=0.0) without a corresponding threshold.
**How to avoid:** Store precision, recall, and thresholds as separate lists. When plotting, use `ax.plot(recall, precision)` (no thresholds needed). When serializing, document the length difference in the JSON schema.
**Warning signs:** `len(precision) != len(thresholds)` errors or off-by-one in chart data.

### Pitfall 2: Race Condition in Run Number Scanning

**What goes wrong:** If two training runs start concurrently for the same model, they could compute the same run number.
**Why it happens:** Scanning `old/` and computing max(N)+1 is not atomic.
**How to avoid:** This is extremely unlikely for a single-user CLI tool. The scan-then-write pattern is sufficient. If needed, add a secondary check: after computing N, verify the target filename doesn't exist before writing, and increment if it does.
**Warning signs:** Two files with the same run number in `old/`.

### Pitfall 3: PipelineConfig.model Type Change

**What goes wrong:** `PipelineConfig.model` is currently `str | None`. Changing to `list[str] | None` silently breaks all consumers that treat it as a single string.
**Why it happens:** Frozen dataclass fields are type-checked at definition but not enforced at runtime.
**How to avoid:** Search for every use of `cfg.model` in `pipeline.py`, `__main__.py`, and `trainer.py`. All must handle the list type. Key changes: (1) `run_train()` iterates over `cfg.model or MODEL_IDS`, (2) `run_evaluate()` iterates similarly, (3) `PipelineConfig.model` type annotation updated.
**Warning signs:** `TypeError: argument of type 'list' is not iterable` or models trained one at a time when all were selected.

### Pitfall 4: Existing Date-Keyed old/ Subdirectories

**What goes wrong:** The new flat archiving logic could conflict with existing `old/2026-03-04/` directories.
**Why it happens:** Previous archiving created date-keyed subdirectories. New archiving writes directly into `old/`.
**How to avoid:** The run number scanner must only scan for files matching `model_run\d{3}_.*` pattern in `old/`. It should ignore subdirectories and non-matching files. The `_archive_existing_model()` function must be updated to move canonical files (model.pkl, etc.) directly into `old/` rather than into a date-keyed subfolder. BUT it must NOT delete or modify existing date-keyed subdirectories.
**Warning signs:** Existing date-keyed archives disappearing, or run number scanner counting files inside date-keyed subdirectories.

### Pitfall 5: BSS Division by Zero

**What goes wrong:** If `brier_baseline == 0`, BSS formula divides by zero.
**Why it happens:** All-positive or all-negative datasets have `positive_rate * (1 - positive_rate) == 0`.
**How to avoid:** Guard: `if brier_baseline > 0: bss = 1 - (brier / brier_baseline) else: bss = 0.0`. This is explicitly specified in CONTEXT.md.
**Warning signs:** `ZeroDivisionError` or `inf` values in calibration metrics.

### Pitfall 6: --artifact Path Resolution

**What goes wrong:** User passes `--artifact model_run001_auc_roc.pkl` but the file is in `old/` not the main model directory.
**Why it happens:** After archiving, run-numbered files live in `old/`.
**How to avoid:** Resolution order: (1) Check `artifacts/models/{MID}/{artifact_name}`, (2) Check `artifacts/models/{MID}/old/{artifact_name}`, (3) Hard fail with descriptive error showing both searched paths.
**Warning signs:** "Artifact not found" when the file exists in `old/`.

## Code Examples

### AUC-PR Metric Computation (verified with sklearn 1.8.0)

```python
# Source: sklearn.metrics API (verified locally)
from sklearn.metrics import precision_recall_curve, average_precision_score

# precision_recall_curve returns:
#   precision: array, shape (n_thresholds + 1,) -- last entry is 1.0
#   recall: array, shape (n_thresholds + 1,) -- last entry is 0.0
#   thresholds: array, shape (n_thresholds,)
pr_precision, pr_recall, pr_thresholds = precision_recall_curve(y_true, y_scores)

# average_precision_score computes weighted mean of precisions
# at each threshold, using recall increase as weight
auc_pr = average_precision_score(y_true, y_scores)
```

### PR Curve Chart (follows existing visualizer.py pattern)

```python
def plot_pr_curve(
    eval_dict: dict,
    output_dir: Path,
    filename: str = "pr_curve.png",
) -> Path:
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
    ax.set_title(f"{model_id} -- PR Curve")
    ax.legend(loc="upper right")
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.grid(True, alpha=0.3)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path)
    plt.close(fig)
    return path
```

### Flat Archival with Run-Numbered Files

```python
import re
import shutil

def _next_run_number(model_dir: Path) -> int:
    """Scan for existing run-numbered files and return the next available number."""
    pattern = re.compile(r"model_run(\d{3})_")
    existing: set[int] = set()

    for search_dir in [model_dir, model_dir / "old"]:
        if not search_dir.exists():
            continue
        for item in search_dir.iterdir():
            if item.is_file():
                m = pattern.match(item.name)
                if m:
                    existing.add(int(m.group(1)))

    return max(existing, default=0) + 1


def _archive_existing_model_flat(model_dir: Path) -> None:
    """Move canonical artifacts to old/ (flat, not date-keyed)."""
    old_dir = model_dir / "old"
    old_dir.mkdir(parents=True, exist_ok=True)

    canonical_files = ["model.pkl", "training_report.json", "feature_registry.json",
                       "test_data.parquet"]
    for name in canonical_files:
        src = model_dir / name
        if src.exists():
            dest = old_dir / name
            # If canonical copy already exists in old/, overwrite
            if dest.exists():
                dest.unlink()
            shutil.move(str(src), str(dest))
```

### TUI Checkbox Model Picker

```python
def show_model_picker(
    model_ids: list[str] | None = None,
) -> list[str]:
    """Interactive checkbox picker for model selection.

    Returns list of selected model IDs (e.g., ["M1", "M3"]).
    Falls back to all models if stdin is not a TTY.
    """
    if model_ids is None:
        model_ids = ["M1", "M2", "M3", "M4"]

    if not sys.stdin.isatty():
        return list(model_ids)

    # Build checkbox widget, run input loop, return selections
    ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `--model M1` (single choice) | `--model M1 M3` (multi-select) | Phase 15 | Users can train/evaluate subsets |
| Date-keyed old/ archiving | Flat old/ with run-numbered files | Phase 15 | Named artifacts are self-identifying |
| AUC-ROC only discrimination | AUC-ROC + AUC-PR dual discrimination | Phase 15 | Better metric for imbalanced M3/M4 |
| Brier Score + baseline only | Brier + baseline + BSS | Phase 15 | Interpretable calibration benchmark |

**Deprecated/outdated:**
- `_archive_existing_model()` date-keyed archiving: Replaced by flat archiving for run-numbered files. Existing date-keyed directories are preserved but no new ones are created.

## Open Questions

1. **CV scoring metric name for artifact filenames**
   - What we know: The CONTEXT specifies format `model_run{N:03d}_{metric}.pkl` where metric is "the CV scoring metric used during training (e.g., auc_roc, f1)".
   - What's unclear: The current trainer always uses `roc_auc_score` for CV scoring. There is no configurable scoring metric. So all runs will be `model_runNNN_auc_roc.pkl`.
   - Recommendation: Use `"auc_roc"` as the metric string since that is the current CV scoring function. This is correct and future-proof -- if a configurable scoring metric is added later, the filename naturally adapts.

2. **Should the old canonical-file archival (model.pkl -> old/model.pkl) happen before or after the run-numbered file is created?**
   - What we know: CONTEXT says "Before saving new artifacts, move existing model.pkl..." into old/.
   - What's unclear: If old/model.pkl already exists from a previous archival, it gets overwritten. That's fine because the run-numbered copy in old/ preserves it.
   - Recommendation: Move canonical -> old/ first (overwriting old/model.pkl if exists), then save new run-numbered + canonical. The run-numbered files in old/ are the permanent records; the old/model.pkl is a transient canonical copy.

## Sources

### Primary (HIGH confidence)
- **sklearn.metrics API (verified locally):** `precision_recall_curve`, `average_precision_score` confirmed working with sklearn 1.8.0. Array shape behavior verified: precision/recall have len(thresholds)+1.
- **Codebase inspection:** evaluator.py (1078 lines), trainer.py (1191 lines), visualizer.py (509 lines), config_screen.py (609 lines), __main__.py (539 lines), pipeline.py (233 lines) -- all read in full.
- **Package versions verified:** sklearn=1.8.0, xgboost=3.2.0, rich=14.3.3, matplotlib=3.10.8.
- **Artifact directory structure verified:** `artifacts/models/M1/old/` exists with date-keyed subdirectories (2026-03-02, 2026-03-04).

### Secondary (MEDIUM confidence)
- **argparse nargs='+' with choices:** Standard Python stdlib behavior. Each value in the nargs list is validated against choices individually. Confirmed by Python docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already installed and verified
- Architecture: HIGH - patterns directly follow existing codebase conventions
- Pitfalls: HIGH - based on direct code inspection and verified API behavior

**Research date:** 2026-03-07
**Valid until:** 2026-04-07 (stable domain, no rapidly changing APIs)
