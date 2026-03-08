---
phase: 15-evaluation-and-training-module-enhancements
plan: "02"
subsystem: training-artifacts
tags: [named-artifacts, versioning, archiving, evaluation, cli]
dependency_graph:
  requires: []
  provides: [named-model-artifacts, flat-archiving, artifact-resolution, artifact-cli-flag]
  affects: [trainer, evaluator, pipeline, __main__]
tech_stack:
  added: []
  patterns: [run-numbered-files, flat-archival, companion-reports, artifact-resolution-fallback]
key_files:
  created:
    - tests/classifiers/test_named_artifacts.py
  modified:
    - src/sip_engine/classifiers/models/trainer.py
    - src/sip_engine/classifiers/evaluation/evaluator.py
    - src/sip_engine/__main__.py
    - src/sip_engine/pipeline.py
    - tests/classifiers/test_pipeline.py
decisions:
  - "Flat archiving (old/) replaces date-keyed archiving for canonical files — run-numbered files are self-identifying by N"
  - "Run number scanning checks both model_dir and model_dir/old/ for collision-safety across sessions"
  - "Companion report resolved by replacing model_run prefix with training_report_run in filename"
  - "artifact=None preserves all existing code paths unchanged"
metrics:
  duration: "~25 minutes"
  completed: "2026-03-08"
  tasks_completed: 2
  files_modified: 5
  files_created: 1
---

# Phase 15 Plan 02: Named Model Artifacts Summary

**One-liner:** Named run artifacts (model_run001_auc_roc.pkl) with flat archiving, companion reports, and --artifact evaluation flag for reproducible model versioning.

## What Was Built

### Task 1: Named artifact saving and flat archiving in trainer

- **`_next_run_number(model_dir)`** — scans `model_dir` and `model_dir/old/` for `model_run\d{3}_` pattern files, returns `max + 1` (deterministic, collision-safe across sessions)
- **`_archive_existing_model_flat(model_dir)`** — moves canonical files (`model.pkl`, `training_report.json`, `feature_registry.json`, `test_data.parquet`) to flat `old/`. Existing date-keyed subdirectories (`old/2026-03-04/`) are NOT touched.
- **`train_model()` updated:** replaces `_archive_existing_model()` call with `_archive_existing_model_flat()`, then saves `model_run{N:03d}_auc_roc.pkl` (copy of `model.pkl`) and `training_report_run{N:03d}_auc_roc.json` (copy of `training_report.json`)
- **`training_report.json`** now contains `run_number` and `run_filename` fields for self-documentation

### Task 2: --artifact flag in evaluator + CLI + tests

- **`_load_artifacts()`** updated: accepts optional `artifact` parameter; resolves path in `model_dir` then `model_dir/old/`; attempts companion report lookup before falling back to canonical `training_report.json`; hard-fails with both searched paths if artifact not found
- **`evaluate_model()`** updated: accepts and passes `artifact` through to `_load_artifacts()`; existing `artifact=None` behavior unchanged
- **`__main__.py`** updated: `--artifact ARTIFACT` flag added to `evaluate` subparser; validates `--artifact` requires `--model` (single-model only)
- **`pipeline.py`** updated: `run_evaluate()` passes `getattr(cfg, 'artifact', None)` through to `evaluate_model()`
- **`tests/classifiers/test_named_artifacts.py`** created: 10 tests across `TestNextRunNumber` (6 tests) and `TestArchiveFlat` (4 tests)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_run_evaluate_single_model to match new artifact kwarg**
- **Found during:** Task 2 regression check
- **Issue:** Existing test asserted `evaluate_model(model_id="M3")` but we now call `evaluate_model(model_id="M3", artifact=None)`. The mock strict match failed.
- **Fix:** Updated assertion to `assert_called_once_with(model_id="M3", artifact=None)`
- **Files modified:** `tests/classifiers/test_pipeline.py`
- **Commit:** 8ba5638

## Verification

```
# All tests pass
468 passed, 1 skipped, 3 warnings

# Named artifacts test file: 10/10
tests/classifiers/test_named_artifacts.py .......... 10 passed

# CLI flag exists
--artifact ARTIFACT   Load a specific model artifact (e.g., model_run001_auc_roc.pkl)
```

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | 0e3af80 | feat(15-02): named artifact saving and flat archiving in trainer |
| Task 2 | 8ba5638 | feat(15-02): --artifact flag in evaluator, CLI, and tests for named artifacts |

## Self-Check: PASSED

All files exist and all commits verified:
- `src/sip_engine/classifiers/models/trainer.py` ✓
- `src/sip_engine/classifiers/evaluation/evaluator.py` ✓
- `src/sip_engine/__main__.py` ✓
- `tests/classifiers/test_named_artifacts.py` ✓
- Commit 0e3af80 ✓
- Commit 8ba5638 ✓
