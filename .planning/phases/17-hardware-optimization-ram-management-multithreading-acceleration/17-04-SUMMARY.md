---
phase: 17
plan: "04"
title: "GPU Optimization — DMatrix Caching & max_bin for HP Search"
subsystem: "classifiers/models/trainer"
tags: ["gpu-optimization", "xgboost", "dmatrix", "hp-search", "cuda"]
dependency_graph:
  requires: ["17-01"]
  provides: ["DMatrix fold caching for CUDA HP search", "max_bin=512 CUDA kwarg", "fold_dmats parameter API on CV scorers"]
  affects: ["src/sip_engine/classifiers/models/trainer.py"]
tech_stack:
  added: []
  patterns:
    - "Pre-built xgb.DMatrix folds reused across all HP iterations (CUDA only)"
    - "xgb.train() booster API instead of XGBClassifier.fit() when fold_dmats provided"
    - "max_bin=512 injected into device_kwargs for CUDA (more GPU work per split)"
    - "fold_dmats=None preserves existing CPU/ROCm XGBClassifier.fit() code path unchanged"
key_files:
  created:
    - tests/classifiers/test_gpu_optimization.py
  modified:
    - src/sip_engine/classifiers/models/trainer.py
decisions:
  - "DMatrix fold_dmats uses (dtrain, dval, y_val) tuple — y_val kept separately for roc_auc_score since DMatrix.get_label() returns numpy but keeping explicit ref is cleaner"
  - "CUDA-only DMatrix caching — ROCm path excluded (ROCm XGBoost DMatrix untested per plan notes)"
  - "max_bin=512 not overwritten if caller already set it explicitly (guard: 'max_bin' not in device_kwargs)"
  - "DMatrix is NOT pickle-serializable (ctypes pointer limitation) — test_dmatrix_fold_structure uses save_binary() round-trip instead"
  - "fold_dmats_spw and fold_dmats_ups both default to None — CPU path falls through to existing XGBClassifier.fit() code unchanged"
metrics:
  duration: "~15 minutes"
  completed: "2026-03-11"
  tasks_completed: 3
  files_changed: 2
---

# Phase 17 Plan 04: GPU Optimization — DMatrix Caching & max_bin for HP Search Summary

**One-liner:** Eliminate idle-GPU pattern in CUDA XGBoost HP search by pre-building fold DMatrix objects once before the loop and reusing across all iterations, plus max_bin=512 for more GPU work per split.

## What Was Built

### Task 1 — CV scoring functions accept pre-built DMatrix (`trainer.py`)

Both `_cv_score_scale_pos_weight()` and `_cv_score_upsampling()` now accept an optional `fold_dmats: list[tuple] | None = None` parameter:

- **When `fold_dmats` is provided (CUDA fast path):** Uses `xgb.train()` with pre-built `xgb.DMatrix` objects. Translates sklearn convention (`n_estimators` → `num_boost_round`, adds `objective`, `eval_metric`, `verbosity`, device kwargs). Scores via `booster.predict(dval)` → `roc_auc_score(y_val, preds)`. GPU error fallback to CPU preserved.
- **When `fold_dmats=None` (CPU path):** Existing `XGBClassifier.fit()` code path unchanged.

`_compare_strategies()` extended with `fold_dmats_spw` and `fold_dmats_ups` parameters that are forwarded to the respective scoring functions.

### Task 2 — Pre-build DMatrix folds in `_hp_search()` for CUDA

In `_hp_search()`, before the main HP iteration loop:

1. **max_bin=512 injection:** When `device_kwargs.get("device", "").startswith("cuda")` and `"max_bin"` not already present, creates a new dict `{**device_kwargs, "max_bin": 512}`. This enables more GPU work per histogram split.

2. **DMatrix pre-build block (CUDA only):** Uses `StratifiedKFold` with the same `n_splits` and `seed` to build 10 DMatrix objects (2 strategies × 5 folds):
   - Strategy A: `(dtrain_spw, dval, y_val)` — original training fold
   - Strategy B: `(dtrain_ups, dval, y_val)` — upsampled training fold (same seed = deterministic; upsampling logic mirrors `_cv_score_upsampling` CPU code)
   
3. `fold_dmats_spw` and `fold_dmats_ups` passed through `_compare_strategies()` to the CV scorers. CPU and ROCm paths left unchanged (`fold_dmats=None`).

### Task 3 — Unit tests (`tests/classifiers/test_gpu_optimization.py`)

9 tests (8 passing, 1 skipped — CUDA not available):

| Test | Coverage |
|------|----------|
| `test_cv_score_scale_pos_weight_cpu_path_unchanged` | CPU path returns valid (mean, std) floats |
| `test_cv_score_upsampling_cpu_path_unchanged` | CPU path returns valid (mean, std) floats |
| `test_dmatrix_fold_structure` | DMatrix shape + binary save/reload round-trip |
| `test_max_bin_added_to_cuda_kwargs` | Injection adds max_bin=512 |
| `test_max_bin_not_overwritten_when_already_set` | Caller's explicit value preserved |
| `test_max_bin_not_added_for_cpu` | CPU path not affected |
| `test_hp_search_cpu_determinism` | Same seed → identical best_cv_auc_mean |
| `test_compare_strategies_accepts_fold_dmats_params` | Signature check |
| `test_cv_score_scale_pos_weight_dmatrix_path` | *(skipped: CUDA not available)* |

## Verification Results

```
543 passed, 2 skipped, 3 warnings in 34.03s
```

All tests pass. 8 new GPU optimization tests added.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] xgb.DMatrix is not pickle-serializable**
- **Found during:** Task 3 (first test run)
- **Issue:** The plan specified `test_dmatrix_fold_structure` should verify DMatrix is "picklable" via `pickle.dumps()`. In practice, XGBoost's `DMatrix` holds ctypes pointers which cannot be pickled: `ValueError: ctypes objects containing pointers cannot be pickled`
- **Fix:** Updated test to verify DMatrix shape (`num_row()`, `num_col()`) and binary serialization round-trip via `dm.save_binary(path)` + `xgb.DMatrix(path)` — which is the correct XGBoost-native serialization API. Also removed unused `import pickle`.
- **Files modified:** `tests/classifiers/test_gpu_optimization.py`
- **Commit:** b76b456

## Commits

| Hash | Message |
|------|---------|
| 0a498a9 | feat(17-04): refactor CV scoring functions to accept pre-built DMatrix |
| e624991 | feat(17-04): pre-build DMatrix folds in _hp_search() for CUDA; add max_bin=512 |
| b76b456 | test(17-04): add GPU optimization unit tests |

## Self-Check: PASSED
