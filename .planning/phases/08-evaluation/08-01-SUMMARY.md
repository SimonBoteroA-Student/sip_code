---
phase: 08-evaluation
plan: "01"
subsystem: evaluation
tags: [evaluation, metrics, AUC-ROC, MAP@k, NDCG@k, Brier-Score, report-generation, XGBoost]
depends_on:
  requires: [07-02]
  provides: [evaluate_model, evaluate_all, map_at_k]
  affects: [08-02]
tech_stack:
  added: []
  patterns:
    - "Custom MAP@k via argsort descending + precision at positive positions"
    - "sklearn ndcg_score with 2D reshape for single-query ranking"
    - "Timestamped output paths for re-run safety (no overwrite)"
    - "Three report formats: JSON (plot-ready ROC), CSV (threshold+summary rows), Markdown (human-readable)"
key_files:
  created:
    - src/sip_engine/evaluation/__init__.py
    - src/sip_engine/evaluation/evaluator.py
    - tests/test_evaluation.py
  modified: []
decisions:
  - "map_at_k() is public (not private) for direct testability — enables edge case unit tests without mocking"
  - "evaluate_all() recomputes metrics from scratch rather than parsing JSON — avoids report format coupling"
  - "_write_csv_report uses stdlib csv.writer (not pandas) — avoids overhead for simple tabular output"
  - "_compute_threshold_analysis returns optimal_threshold as a sub-dict — callers get one lookup path"
metrics:
  duration: "~10 min"
  completed: "2026-03-02"
  tasks_completed: 2
  files_created: 3
  files_modified: 0
---

# Phase 8 Plan 1: Evaluation Module — Metrics Engine, Report Generation, and Unit Tests Summary

**One-liner:** Full evaluation pipeline (AUC-ROC, MAP@k, NDCG@k, Brier Score, 19-threshold sweep) with JSON/CSV/Markdown report generation tested by 14 synthetic-data unit tests.

---

## What Was Built

### `src/sip_engine/evaluation/evaluator.py`

Complete evaluation module with:

**Constants:**
- `MODEL_IDS = ["M1", "M2", "M3", "M4"]`
- `THRESHOLDS` — 19 values from 0.05 to 0.95 in 0.05 steps
- `K_VALUES = [100, 500, 1000]` — for MAP@k and NDCG@k

**Public metric function:**
- `map_at_k(y_true, y_scores, k)` — Custom MAP@k: sort by score descending, compute precision at each positive position in top-k, return mean. Returns 0.0 if no positives. Clamps k to len(y_true).

**Metric helpers:**
- `_compute_discrimination_metrics` — AUC-ROC + ROC curve (FPR/TPR/thresholds as lists for JSON)
- `_compute_ranking_metrics` — MAP@100/500/1000 and NDCG@100/500/1000 via sklearn ndcg_score
- `_compute_calibration_metrics` — Brier Score + baseline (positive_rate × (1 − positive_rate))
- `_compute_threshold_analysis` — Precision/Recall/F1 + confusion matrix at 19 thresholds; optimal F1-maximizing threshold as sub-dict

**Report writers:**
- `_write_json_report` — Full eval_dict as indented JSON (indent=2)
- `_write_csv_report` — 19 threshold rows + 13 summary scalar rows; stdlib csv.writer
- `_write_markdown_report` — Academic-style MD with tables for all metric categories
- `_get_output_path` — Returns base path if free, otherwise adds `YYYY-MM-DD_HH-MM-SS` timestamp

**Public orchestrators:**
- `evaluate_model(model_id, models_dir, output_dir)` — Loads Phase 7 artifacts, computes all metrics, writes 3 reports, verbose console output
- `evaluate_all(models_dir, output_dir)` — Runs all 4 models, writes summary.json + summary.csv, prints formatted cross-model table

### `src/sip_engine/evaluation/__init__.py`

Re-exports: `evaluate_model`, `evaluate_all`.

### `tests/test_evaluation.py`

14 unit tests using synthetic fixtures only (no real model artifacts):

| Test | Validates |
|------|-----------|
| `test_map_at_k_perfect_ranking` | MAP@3=MAP@8=1.0 for perfect classifier |
| `test_map_at_k_worst_ranking` | MAP@3=0.0 when all positives at bottom |
| `test_map_at_k_k_larger_than_n` | k>n clamps safely, no crash |
| `test_map_at_k_no_positives` | All-zero labels → 0.0 |
| `test_ndcg_computation` | NDCG@100 and NDCG@200 in [0,1] |
| `test_discrimination_metrics` | AUC-ROC > 0.5, ROC curve shape/keys |
| `test_ranking_metrics` | All 6 keys present, values in [0,1] |
| `test_calibration_metrics` | Brier > 0, baseline = 0.2×0.8 |
| `test_threshold_analysis` | 19 thresholds, optimal sub-dict keys |
| `test_threshold_analysis_confusion_matrices` | CM sums to n, low/high threshold behavior |
| `test_json_report_schema` | Required top-level keys, model_id value |
| `test_csv_report_parseable` | 19 threshold rows + ≥1 summary row |
| `test_markdown_report_generated` | Starts with `# Evaluation Report`, has AUC-ROC/MAP@/Brier/Threshold |
| `test_timestamped_output_no_overwrite` | Second call returns different timestamped path |

---

## Verification Results

```
# Evaluation tests
14 passed in 2.67s

# Smoke tests
Smoke OK: MAP@3=0.8333, THRESHOLDS=19, K_VALUES=[100, 500, 1000]
MAP@k verification OK
All imports OK

# Full suite (excluding pre-existing iric failures)
321 passed, 3 failed (pre-existing), 3 warnings in 26.95s
```

---

## Decisions Made

1. **`map_at_k()` is public** — exposes for direct testability without module-level mocking
2. **`evaluate_all()` recomputes from scratch** — avoids tight coupling to report format parsing
3. **stdlib `csv.writer` over pandas** — no overhead for simple tabular writes
4. **`optimal_threshold` as top-level key** — both in `threshold_analysis` dict AND as standalone key in eval_dict for convenience

---

## Deviations from Plan

### Pre-existing iric test failures (out of scope)

**Discovered during:** Task 2 — full test suite run

**Issue:** 3 tests in `tests/test_iric.py` fail due to pre-existing uncommitted changes to
`src/sip_engine/iric/calculator.py` (and other files) that predate this plan.

**Action:** Logged to `deferred-items.md`. Not caused by evaluation module changes.
Not fixed (out of scope per deviation rules — pre-existing, unrelated files).

**Commits:** None (no action taken)

---

## Self-Check: PASSED

Files exist:
- ✅ `src/sip_engine/evaluation/__init__.py`
- ✅ `src/sip_engine/evaluation/evaluator.py`
- ✅ `tests/test_evaluation.py`

Commits:
- ✅ `d585359` — feat(08-01): evaluation module
- ✅ `130f34b` — test(08-01): 14 unit tests
