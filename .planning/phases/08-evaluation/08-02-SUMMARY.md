---
phase: 08-evaluation
plan: "02"
subsystem: evaluation
tags: [evaluation, CLI, tabulate, integration-tests, cross-model-summary, XGBoost]
depends_on:
  requires: [08-01]
  provides: [evaluate subcommand, cross-model summary table, integration tests]
  affects: []
tech_stack:
  added: [tabulate>=0.9.0]
  patterns:
    - "Lazy import of evaluation module inside CLI elif branch — avoids import cost at startup"
    - "tabulate 'grid' format for cross-model console summary table"
    - "_create_mock_model_artifacts() helper trains tiny XGBoost on DataFrames for feature-name matching"
    - "Fixture returns (models_dir, output_dir) tuple — integration tests own both dirs via tmp_path"
key_files:
  created:
    - tests/test_evaluation.py (5 new integration tests)
  modified:
    - src/sip_engine/__main__.py
    - src/sip_engine/evaluation/evaluator.py
    - pyproject.toml
decisions:
  - "feature_registry.json uses 'feature_columns' key (not 'feature_names') — must match evaluator._load_artifacts() lookup"
  - "XGBoost fixture trained on pd.DataFrame with named columns — prevents feature-name mismatch warning at predict_proba time"
  - "_print_summary_table updated in-place to use tabulate 'grid' format — no structural change to evaluate_all() needed"
  - "_create_mock_model_artifacts is a module-level helper (not fixture) — allows test_evaluate_all_summary_files to create all 4 models independently"
metrics:
  duration: "~3 min"
  completed: "2026-03-02"
  tasks_completed: 2
  files_created: 0
  files_modified: 4
---

# Phase 8 Plan 2: CLI Evaluate Subcommand, Tabulate Console Table, and Integration Tests Summary

**One-liner:** `python -m sip_engine evaluate` CLI with --model/--models-dir/--output-dir flags, tabulate grid console summary table, and 5 XGBoost-based integration tests verifying the full evaluate pipeline end-to-end.

---

## What Was Built

### `src/sip_engine/__main__.py`

**Added `evaluate` subcommand with full argument spec:**
- `--model {M1,M2,M3,M4}` — Evaluate a single model (default: all 4)
- `--models-dir PATH` — Override model artifacts directory
- `--output-dir PATH` — Override evaluation output directory
- Added `from pathlib import Path` import at module top

**Added evaluate command handler:**
- Single-model path: calls `evaluate_model()` → prints result path
- All-models path: calls `evaluate_all()` → prints summary directory
- `FileNotFoundError` → stderr + exit 1 (missing artifacts)
- Generic `Exception` → stderr + exit 1

### `src/sip_engine/evaluation/evaluator.py`

**Replaced ASCII `_print_summary_table()` with tabulate:**
- Added `from tabulate import tabulate as tabulate_fn` at module level
- `_print_summary_table()` now builds rows with columns: Model, AUC-ROC, Brier, MAP@100, MAP@1000, NDCG@100, Opt.Thresh, P@Opt, R@Opt
- Uses `tablefmt="grid"` for clean aligned console output
- Iterates over `summary.items()` (evaluated models only, not all MODEL_IDS)

### `pyproject.toml`

- Added `"tabulate>=0.9.0"` to `dependencies`

### `tests/test_evaluation.py`

**Added `_create_mock_model_artifacts(tmp_models_dir, model_id)` helper:**
- Trains a 5-feature, n_estimators=5 XGBClassifier on pd.DataFrame (feature names preserved)
- Saves: `model.pkl`, `test_data.parquet`, `feature_registry.json`, `training_report.json`
- Key: `feature_registry.json` uses `"feature_columns"` key to match `evaluator._load_artifacts()`

**Added `mock_model_artifacts` fixture:**
- Returns `(models_dir, output_dir)` tuple using `tmp_path`

**5 new integration tests:**

| Test | Validates |
|------|-----------|
| `test_evaluate_model_end_to_end` | 3 report files, JSON schema, metrics in [0,1], 19 thresholds, optimal_threshold keys, return Path |
| `test_evaluate_model_rerun_no_overwrite` | ≥4 files after 2 runs; base files preserved |
| `test_evaluate_model_missing_model` | FileNotFoundError for nonexistent models_dir |
| `test_evaluate_all_summary_files` | summary.json + summary.csv exist; 4 model entries; correct return Path |
| `test_cli_evaluate_help` | subprocess exit 0; --model/--models-dir/--output-dir present |

---

## Verification Results

```
# Evaluation tests (unit + integration)
19 passed in 3.26s

# CLI evaluate --help
usage: python -m sip_engine evaluate [-h] [--model {M1,M2,M3,M4}] [--models-dir MODELS_DIR] [--output-dir OUTPUT_DIR]
... shows all 3 flags

# tabulate installed
tabulate OK

# Full suite
3 failed (pre-existing iric), 326 passed, 3 warnings in 19.79s
```

---

## Decisions Made

1. **`feature_columns` key in fixture** — `evaluate_model()` reads `feature_registry["feature_columns"]`; the plan draft used `"feature_names"` which would have caused a `KeyError`. Fixed to match evaluator.

2. **XGBoost trained on pd.DataFrame** — Fitting with a DataFrame ensures feature names are embedded in the model, preventing mismatch warnings when `predict_proba()` receives a named DataFrame at evaluation time.

3. **`_print_summary_table` updated in-place** — Rather than adding tabulate code inline in `evaluate_all()` (as the plan showed), updated the existing `_print_summary_table()` function. Same behavior, cleaner separation.

4. **`_create_mock_model_artifacts` as module-level helper** — `test_evaluate_all_summary_files` needs to create 4 models independently of the fixture, so a non-fixture helper function is the right pattern.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed feature_registry key in test fixture**
- **Found during:** Task 2 — implementing mock_model_artifacts
- **Issue:** Plan draft used `{"feature_names": feature_names}` but `evaluator._load_artifacts()` reads `feature_registry["feature_columns"]`, which would raise `KeyError` at test runtime
- **Fix:** Changed fixture to use `{"feature_columns": feature_names}`
- **Files modified:** `tests/test_evaluation.py`
- **Commit:** abc7d18

---

## Self-Check: PASSED

Files exist:
- ✅ `src/sip_engine/__main__.py` (modified)
- ✅ `src/sip_engine/evaluation/evaluator.py` (modified)
- ✅ `pyproject.toml` (modified)
- ✅ `tests/test_evaluation.py` (modified)

Commits:
- ✅ `473fb6d` — feat(08-02): CLI evaluate subcommand + tabulate console summary table
- ✅ `abc7d18` — test(08-02): 5 integration tests for evaluate CLI and cross-model summary
