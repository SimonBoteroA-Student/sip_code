---
phase: 07-model-training
verified: 2026-03-02T15:19:27Z
status: human_needed
score: 5/5 success criteria verified (code); 2 require execution
re_verification:
  previous_status: passed
  previous_score: 9/9
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps: []
human_verification:
  - test: "Run full training pipeline against real data"
    expected: "artifacts/models/M{1,2,3,4}/model.pkl and feature_registry.json produced"
    why_human: "Requires features.parquet (from Phase 6 pipeline execution) and ~5-30 min training time per model"
---

# Phase 7: Model Training Verification Report

**Phase Goal:** 4 XGBoost binary classifiers (M1 cost overruns, M2 delays, M3 Comptroller records, M4 SECOP fines) are trained on pre-execution features only, with class imbalance strategy selected per model and hyperparameters optimized via random search, producing serialized .pkl artifacts.

**Verified:** 2026-03-02T15:19:27Z
**Status:** HUMAN_NEEDED — all code verified; production model artifacts require execution
**Re-verification:** Yes — previous verification existed (status: passed, 9/9)

## Goal Achievement

### Success Criteria Verification

| # | Success Criterion | Status | Evidence |
|---|-------------------|--------|----------|
| 1 | Stratified random 70/30 split (per-model stratification by label, fixed seed=42) — NOT temporal ordering | ✓ VERIFIED | `_stratified_split()` at trainer.py:127-128: `train_test_split(X, y, test_size=0.3, stratify=y, random_state=seed)` where `RANDOM_SEED=42`. Per-model: `train_model()` passes `y=merged[model_id]`. Tests `test_stratified_split_proportions` + `test_stratified_split_reproducibility` pass. |
| 2 | Both class imbalance strategies evaluated per model via stratified CV, better selected and documented | ✓ VERIFIED | `_compare_strategies()` at trainer.py:281 evaluates both `_cv_score_scale_pos_weight` and `_cv_score_upsampling` with identical params. Winner = higher mean CV AUC-ROC; ties → scale_pos_weight (line 317). `_hp_search()` calls this for every HP candidate. strategy_comparison saved to training_report.json. `test_compare_strategies` passes. |
| 3 | Manual CV loop with ParameterSampler (200 iterations) and StratifiedKFold(5) completes without errors | ✓ VERIFIED | `_hp_search()` at trainer.py:380: `ParameterSampler(PARAM_DIST, n_iter=n_iter, random_state=seed)` default n_iter=200. StratifiedKFold(n_splits=5) used inside both strategy scorers (lines 171, 233). Manual loop at 388-438 (NOT RandomizedSearchCV). `test_hp_search_quick` passes with n_iter=3. |
| 4 | Four serialized model files exist at artifacts/models/M{1-4}/model.pkl | ⚠ CODE VERIFIED / ARTIFACTS PENDING | Code at trainer.py:773 `joblib.dump(clf, model_pkl_path)` correctly serializes. `test_train_model_end_to_end_quick[M1-M4]` all pass — model.pkl created and loadable with valid `predict_proba()`. **But**: No model.pkl files exist on disk at artifacts/models/ because features.parquet doesn't exist (Phase 6 pipeline not yet executed). |
| 5 | feature_registry.json stored alongside each model with exact column names and ordering | ⚠ CODE VERIFIED / ARTIFACTS PENDING | Code at trainer.py:779-798 writes registry with `FEATURE_COLUMNS` (34 features). `test_feature_registry_column_order` asserts exact match (order + contents). **But**: No feature_registry.json files on disk — same dependency as SC4. |

**Score: 5/5 success criteria verified at code level. 2 (SC4, SC5) require pipeline execution to produce physical artifacts.**

### Required Artifacts

| Artifact | Expected | Exists | Lines | Status | Details |
|----------|----------|--------|-------|--------|---------|
| `src/sip_engine/models/trainer.py` | Training infrastructure + train_model() | ✓ | 879 | ✓ VERIFIED | Contains: `_detect_xgb_device`, `_stratified_split`, `_cv_score_scale_pos_weight`, `_cv_score_upsampling`, `_compare_strategies`, `_hp_search`, `train_model`, `_json_safe`, `PARAM_DIST`, `MODEL_IDS`, `RANDOM_SEED` |
| `src/sip_engine/models/__init__.py` | Re-exports public API | ✓ | 28 | ✓ VERIFIED | Re-exports all 10 symbols; `__all__` defined |
| `src/sip_engine/__main__.py` | CLI `train` subcommand | ✓ | 220 | ✓ VERIFIED | Lines 53-86: train parser with 6 flags (--model, --force, --quick, --n-iter, --n-jobs, --build-features). Lines 152-185: dispatch to `train_model()` |
| `tests/test_models.py` | Comprehensive test coverage | ✓ | 514 | ✓ VERIFIED | 17 test functions → 20 test items (parametrized M1-M4). **All 20 pass in 12.84s** |

### Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|-----|--------|---------|
| `trainer.py` | `sklearn.model_selection` | `train_test_split, StratifiedKFold, ParameterSampler` | ✓ WIRED | Line 36 imports all three; used at lines 128, 171, 233, 380 |
| `trainer.py` | `xgboost` | `XGBClassifier` | ✓ WIRED | Line 40: `import xgboost as xgb`; instantiated at lines 178, 259, 741 |
| `trainer.py` | `features/pipeline.py` | `FEATURE_COLUMNS` | ✓ WIRED | Line 519 lazy import inside `train_model()`; 34 columns confirmed via runtime check |
| `trainer.py` | `artifacts/models/MX/` | `joblib.dump` + `json.dumps` | ✓ WIRED | Line 773: `joblib.dump(clf, model_pkl_path)`; Lines 798, 849: `write_text(json.dumps(...))` |
| `__main__.py` | `trainer.py` | lazy import of `train_model, MODEL_IDS` | ✓ WIRED | Line 153: `from sip_engine.models.trainer import train_model, MODEL_IDS` |
| `trainer.py` | `iric/thresholds.py` | `calibrate_iric_thresholds`, `save_iric_thresholds` | ✓ WIRED | Lines 638-641: imported and called (inside try/except for test environments) |
| `trainer.py` | `features/encoding.py` | `build_encoding_mappings` | ✓ WIRED | Lines 658-660: imported and called (inside try/except) |
| `trainer.py` | `sklearn.utils.resample` | minority upsampling | ✓ WIRED | Line 38: `from sklearn.utils import resample`; used at lines 251, 754 |
| `trainer.py` | `scipy.stats` | PARAM_DIST distributions | ✓ WIRED | Line 35: `import scipy.stats as stats`; used at lines 55-58 |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| MODL-01 | 07-02 | Train M1 (cost overruns) XGBoost binary classifier using only pre-execution features | ✓ SATISFIED | `train_model("M1")` implemented; uses FEATURE_COLUMNS (34 pre-execution features); `test_train_model_end_to_end_quick[M1]` passes |
| MODL-02 | 07-02 | Train M2 (delays) XGBoost binary classifier using only pre-execution features | ✓ SATISFIED | `train_model("M2")` — same mechanism; `test_train_model_end_to_end_quick[M2]` passes |
| MODL-03 | 07-02 | Train M3 (Comptroller records) XGBoost binary classifier using only pre-execution features | ✓ SATISFIED | `train_model("M3")` — extreme imbalance handled via n_splits guard (lines 681-691); `test_train_model_end_to_end_quick[M3]` passes |
| MODL-04 | 07-02 | Train M4 (SECOP fines) XGBoost binary classifier using only pre-execution features | ✓ SATISFIED | `train_model("M4")` — same extreme imbalance handling; `test_train_model_end_to_end_quick[M4]` passes |
| MODL-05 | 07-01 | Evaluates 2 class imbalance strategies per model: scale_pos_weight + 25% upsampling; selects best based on CV | ✓ SATISFIED | `_compare_strategies()` evaluates both; winner = higher mean CV AUC-ROC; ties → scale_pos_weight (simpler) |
| MODL-06 | 07-01 | HP optimization via RandomizedSearchCV with 200 iterations and StratifiedKFold(5) | ✓ SATISFIED | `_hp_search()` uses `ParameterSampler` (equivalent sampling) with n_iter=200 default and StratifiedKFold(5); configurable via `--n-iter` |
| MODL-07 | 07-01 | 70/30 train/test split | ✓ SATISFIED (with documented override) | `_stratified_split()` uses stratified random split with seed=42. REQUIREMENTS.md says "temporal ordering" but CONTEXT.md documents explicit user decision for stratified random. |
| MODL-08 | 07-02 | Serializes trained models to .pkl via joblib with feature name ordering metadata | ✓ SATISFIED | `joblib.dump(clf, ...)` at line 773; `feature_names_in_` set on XGBClassifier by fitting on DataFrame with FEATURE_COLUMNS |
| MODL-09 | 07-02 | Stores feature_registry.json alongside each model | ✓ SATISFIED | feature_registry.json written at lines 797-798; `test_feature_registry_column_order` asserts exact column match |

No orphaned requirements found — all 9 MODL requirements mapped to Phase 7 are covered by plans 07-01 and 07-02.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/sip_engine/__main__.py` | 214 | `"not yet implemented"` fallthrough | ℹ️ Info | Only reached for `run-pipeline` command (Phase 9+ work). `train` command fully implemented. No impact on Phase 7. |

**No TODO/FIXME/placeholder/stub patterns found in trainer.py or test_models.py.** Zero anti-patterns in Phase 7 core files.

### Test Results

```
20 passed in 12.84s

tests/test_models.py::test_detect_xgb_device PASSED
tests/test_models.py::test_stratified_split_proportions PASSED
tests/test_models.py::test_stratified_split_reproducibility PASSED
tests/test_models.py::test_cv_score_scale_pos_weight PASSED
tests/test_models.py::test_cv_score_upsampling PASSED
tests/test_models.py::test_upsampling_does_not_leak_to_val PASSED
tests/test_models.py::test_compare_strategies PASSED
tests/test_models.py::test_hp_search_quick PASSED
tests/test_models.py::test_param_dist_valid PASSED
tests/test_models.py::test_model_ids PASSED
tests/test_models.py::test_train_model_missing_features PASSED
tests/test_models.py::test_train_model_missing_labels PASSED
tests/test_models.py::test_train_model_invalid_model_id PASSED
tests/test_models.py::test_train_model_skip_existing PASSED
tests/test_models.py::test_train_model_end_to_end_quick[M1] PASSED
tests/test_models.py::test_train_model_end_to_end_quick[M2] PASSED
tests/test_models.py::test_train_model_end_to_end_quick[M3] PASSED
tests/test_models.py::test_train_model_end_to_end_quick[M4] PASSED
tests/test_models.py::test_feature_registry_column_order PASSED
tests/test_models.py::test_cli_train_help PASSED
```

### Human Verification Required

### 1. Execute Full Training Pipeline

**Test:** Run `python -m sip_engine train --build-features` (or first build features.parquet via Phase 6, then `python -m sip_engine train`)
**Expected:** 
- artifacts/models/M1/model.pkl, feature_registry.json, training_report.json, test_data.parquet
- artifacts/models/M2/model.pkl, feature_registry.json, training_report.json, test_data.parquet
- artifacts/models/M3/model.pkl, feature_registry.json, training_report.json, test_data.parquet
- artifacts/models/M4/model.pkl, feature_registry.json, training_report.json, test_data.parquet
**Why human:** Requires features.parquet (currently missing — Phase 6 pipeline not yet executed against real SECOP data). Training with 200 iterations takes ~5-30 min per model. Cannot be verified in automated code review.

### 2. Verify Training Report Content

**Test:** After training, inspect `artifacts/models/M1/training_report.json` — check `strategy_comparison.winner` and `best_params`
**Expected:** Non-trivial AUC-ROC scores, sensible best hyperparameters, winner documented per model
**Why human:** Requires real data run; score reasonableness is a domain judgment

## Summary

### What's Verified (Code-Level)

The training infrastructure is **complete, substantive, and fully wired**:

- **879 lines** in trainer.py implementing the full training pipeline (16 steps)
- **514 lines** in test_models.py with 20 tests — all passing in 12.84s
- Stratified 70/30 split with seed=42, per-model stratification ✓
- Both imbalance strategies (scale_pos_weight + 25% upsampling) evaluated per HP candidate ✓
- Manual CV loop with ParameterSampler(200) + StratifiedKFold(5) ✓
- Final model refitted on FULL training set (not a CV fold model) — lines 741-765 ✓
- model.pkl via joblib.dump, feature_registry.json with exact FEATURE_COLUMNS ordering ✓
- CLI `train` command with all required flags (--model, --force, --quick, --n-iter, --n-jobs) ✓
- IRIC threshold recalibration and encoding mappings recomputation on train-only data ✓
- All 9 MODL requirements satisfied ✓

### What's Pending (Execution-Level)

Physical model artifacts at `artifacts/models/M{1-4}/` don't exist because:
1. `artifacts/features/features.parquet` does not exist (Phase 6 feature pipeline has not been executed against real SECOP data)
2. Without features.parquet, `train_model()` raises `FileNotFoundError` as designed
3. The `--build-features` flag exists to chain the full pipeline, but requires real data

**This is not a code gap** — the training infrastructure is complete and tested. The artifacts require pipeline execution against the actual SECOP dataset.

---
_Verified: 2026-03-02T15:19:27Z_
_Verifier: Claude (gsd-verifier)_
