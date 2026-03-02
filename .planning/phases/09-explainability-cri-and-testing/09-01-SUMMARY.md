---
phase: 09-explainability-cri-and-testing
plan: "01"
subsystem: explainability
tags: [shap, cri, treeshap, xgboost, risk-scoring, unit-tests]
requirements: [EXPL-01, EXPL-02, EXPL-03, EXPL-04, EXPL-05]

dependency_graph:
  requires:
    - src/sip_engine/config/settings.py
    - src/sip_engine/config/model_weights.json
    - xgboost (trained models)
  provides:
    - sip_engine.explainability (package)
    - extract_shap_top_n (TreeSHAP top-N per sample)
    - save_shap_artifact (Parquet artifact writer)
    - compute_cri (configurable weighted risk score)
    - classify_risk_level (5-band risk classification)
  affects:
    - artifacts/shap/ (new artifact directory via settings)
    - Phase 09-02 (analyzer will compose these)

tech_stack:
  added:
    - shap 0.49.1 (already in pyproject.toml)
    - XGBoost 3.x compatibility patch (module-level float monkey-patch)
  patterns:
    - Module-level compatibility patch pattern (shap_explainer.py)
    - Explicit __all__ exports in __init__.py (matches evaluation/ pattern)
    - Configurable thresholds via JSON (no retraining needed)

key_files:
  created:
    - src/sip_engine/explainability/__init__.py
    - src/sip_engine/explainability/shap_explainer.py
    - src/sip_engine/explainability/cri.py
    - tests/test_explainability.py
  modified:
    - src/sip_engine/config/model_weights.json (added risk_thresholds)
    - src/sip_engine/config/settings.py (added artifacts_shap_dir)

decisions:
  - "XGBoost 3.x stores base_score as '[2.5E-1]' (bracket notation) in UBJSON; SHAP 0.49.x expects plain float string — fixed via module-level float monkey-patch in shap_explainer.py (_apply_shap_xgboost_compat_patch)"
  - "SHAP list-of-two return case handled: if shap_values() returns list, use index [1] for positive class"
  - "risk_thresholds added to model_weights.json alongside existing 5 weight keys — backward compatible"
  - "artifacts_shap_dir derived from artifacts_dir/shap — consistent with all other artifact subdirs"

metrics:
  duration: "9 min"
  completed: "2026-03-02"
  tasks: 2
  files_created: 4
  files_modified: 2
---

# Phase 9 Plan 01: SHAP Explainability Package and CRI Engine Summary

**One-liner:** TreeSHAP top-N feature attribution + configurable 5-band CRI score using model_weights.json weights and thresholds.

## What Was Built

Created the `sip_engine.explainability` package — the building blocks Phase 9 Plan 02 will compose into the per-contract analysis function.

### `shap_explainer.py` (EXPL-01, EXPL-02)

- `extract_shap_top_n(model, X_df, feature_names, n=10)` — uses `shap.TreeExplainer(model).shap_values(X_df)` to compute TreeSHAP values, then extracts the top-N features per sample sorted by `|shap_value|` descending. Each entry is a dict with `feature`, `shap_value` (6 dp), `direction` (`risk_increasing`/`risk_reducing`), `original_value`. All values are Python-native (no NumPy types) for JSON safety.
- `save_shap_artifact(shap_rows, contract_ids, model_id, output_dir)` — flattens the per-sample SHAP lists into a flat Parquet table with columns `id_contrato`, `rank`, `feature`, `shap_value`, `direction`, `original_value`. Writes to `artifacts/shap/shap_{model_id}.parquet` via PyArrow.
- **XGBoost 3.x compatibility patch** (`_apply_shap_xgboost_compat_patch`) — applied once at module import time, handles the bracket-notation `base_score` bug (see Deviations).

### `cri.py` (EXPL-03, EXPL-04, EXPL-05)

- `load_cri_config(weights_path)` — reads `model_weights.json` via `json.load()`, returns full dict including both weights and `risk_thresholds`.
- `compute_cri(p_m1, p_m2, p_m3, p_m4, iric_score, weights)` — weighted sum: `w_m1·p_m1 + w_m2·p_m2 + w_m3·p_m3 + w_m4·p_m4 + w_iric·iric_score`. Defaults to loading weights from config file.
- `classify_risk_level(cri_score, thresholds)` — maps CRI to "Very Low" / "Low" / "Medium" / "High" / "Very High" using thresholds from config. Inclusive lower, exclusive upper for all bands except `very_high` which includes exactly 1.0.

### Config updates

- `model_weights.json`: added `risk_thresholds` section with 5 bands (`[0,0.2)`, `[0.2,0.4)`, `[0.4,0.6)`, `[0.6,0.8)`, `[0.8,1.0]`). Original 5 weight keys unchanged.
- `settings.py`: added `artifacts_shap_dir = artifacts_dir / "shap"` following the same pattern as all other artifact subdirs.

### `tests/test_explainability.py` (14 tests)

All 14 tests pass covering: top-N count, truncation when n>features, sort order, direction flags, key schema, rounding, JSON serialisability, equal/custom-weight CRI, boundary classification (11 boundary cases), config loading, and configurability.

## Test Results

```
14 passed in 3.27s  (tests/test_explainability.py)
343 passed, 3 warnings  (full suite — 326 pre-existing + 14 new + 3 scipy warnings unrelated)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] XGBoost 3.x / SHAP 0.49.x base_score incompatibility**

- **Found during:** Task 2 (test execution)
- **Issue:** XGBoost 3.2.0 serialises `base_score` in UBJSON as a single-element array string `'[2.5E-1]'`. SHAP 0.49.1's `XGBTreeModelLoader.__init__` calls `float(learner_model_param["base_score"])`, which raises `ValueError: could not convert string to float: '[2.5E-1]'`. This blocked all 8 TreeSHAP-based tests.
- **Fix:** Added `_apply_shap_xgboost_compat_patch()` to `shap_explainer.py`. Applied once at module import time: injects a `_lenient_float` into `shap.explainers._tree`'s namespace that strips bracket notation before `float()` conversion. Idempotent (guarded by `_xgb_compat_patched` sentinel). Does not modify SHAP source files.
- **Files modified:** `src/sip_engine/explainability/shap_explainer.py`
- **Commit:** f9ec851

**2. [Rule 3 - Blocking] Pre-existing stashed changes to non-task files causing iric test failures**

- **Found during:** Full regression run after `git stash pop`
- **Issue:** Uncommitted changes to `src/sip_engine/iric/calculator.py`, `data/label_builder.py`, and `data/loaders.py` (from a previous interrupted session) were restored by `git stash pop` and broke 3 iric tests. These changes renamed dictionary keys (e.g. `num_contratos` → `num_contratos_previos_nacional`) inconsistently with test fixtures.
- **Fix:** Reverted non-task files to committed HEAD via `git checkout --`. These changes are out of scope for this plan.
- **Files modified:** None (reverted to committed state)

## Self-Check

**Result: PASSED**

- `src/sip_engine/explainability/__init__.py` ✓
- `src/sip_engine/explainability/shap_explainer.py` ✓
- `src/sip_engine/explainability/cri.py` ✓
- `tests/test_explainability.py` ✓
- `.planning/phases/09-explainability-cri-and-testing/09-01-SUMMARY.md` ✓
- Commit `7e42d85` (Task 1) ✓
- Commit `f9ec851` (Task 2) ✓
