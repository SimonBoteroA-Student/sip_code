---
phase: 07-model-training
verified: 2026-03-02T00:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
gaps: []
human_verification: []
---

# Phase 7: Model Training Verification Report

**Phase Goal:** 4 XGBoost binary classifiers (M1 cost overruns, M2 delays, M3 Comptroller records, M4 SECOP fines) are trained on pre-execution features only, with class imbalance strategy selected per model and hyperparameters optimized via random search, producing serialized .pkl artifacts.

**Verified:** 2026-03-02
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

All must-haves are sourced from Plan 07-01 and Plan 07-02 frontmatter.

#### Plan 07-01 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Stratified random 70/30 split preserves class proportions and is reproducible with seed=42 | VERIFIED | `_stratified_split()` at trainer.py:107 wraps `train_test_split(..., stratify=y, random_state=seed)`; `test_stratified_split_proportions` and `test_stratified_split_reproducibility` pass |
| 2 | Manual CV loop with upsampling inside folds produces valid AUC-ROC scores without leaking upsampled rows into validation | VERIFIED | `_cv_score_upsampling()` at trainer.py:199 upsamples only `X_tr/y_tr`, scores on original `X_val/y_val`; `test_upsampling_does_not_leak_to_val` passes |
| 3 | Both imbalance strategies evaluated with identical HP candidates and winner selected by mean CV AUC-ROC | VERIFIED | `_compare_strategies()` at trainer.py:281 runs both `_cv_score_scale_pos_weight` and `_cv_score_upsampling` with same params; winner = higher mean_cv_auc; ties go to scale_pos_weight |
| 4 | HP search with ParameterSampler and StratifiedKFold(5) completes for configurable n_iter | VERIFIED | `_hp_search()` at trainer.py:331 uses `ParameterSampler(PARAM_DIST, n_iter=n_iter, random_state=seed)` with `StratifiedKFold` inside each strategy scorer; `test_hp_search_quick` passes |

#### Plan 07-02 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 5 | `train_model('M1')` loads features.parquet + labels.parquet, drops NaN M1 labels, splits, runs HP search, refits on full train, and saves model.pkl + feature_registry.json + training_report.json | VERIFIED | `train_model()` at trainer.py:475 implements all 16 steps; `test_train_model_end_to_end_quick` parameterized over M1-M4 passes for all 4 models |
| 6 | `train_model` works for all 4 models (M1-M4) independently via --model flag | VERIFIED | CLI train subcommand at __main__.py:129 dispatches to `train_model(mid, ...)` for each model; `test_cli_train_help` confirms --model flag; parametrized end-to-end test covers all 4 IDs |
| 7 | `model.pkl` is the final model refitted on the FULL training set with best HPs (NOT a CV fold model) | VERIFIED | trainer.py:741-765 creates and fits `clf` on full `X_train` (or upsampled version) AFTER `_hp_search()` completes; `joblib.dump(clf, model_pkl_path)` at line 773 |
| 8 | `feature_registry.json` contains FEATURE_COLUMNS in exact order with all metadata | VERIFIED | trainer.py:779-798 builds registry with `"feature_columns": FEATURE_COLUMNS` (34 entries); `test_feature_registry_column_order` asserts exact match |
| 9 | CLI train command supports --model, --force, --quick, --n-iter, --n-jobs flags | VERIFIED | __main__.py:51-78 defines all 5 arguments; `python -m sip_engine train --help` output confirms all flags present |

**Score: 9/9 truths verified**

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|---------|--------|---------|
| `src/sip_engine/models/trainer.py` | Training infrastructure + train_model() | VERIFIED | 879 lines; contains `_detect_xgb_device`, `_stratified_split`, `_cv_score_scale_pos_weight`, `_cv_score_upsampling`, `_compare_strategies`, `_hp_search`, `train_model`, `_json_safe`, `PARAM_DIST`, `MODEL_IDS`, `RANDOM_SEED` |
| `src/sip_engine/models/__init__.py` | Re-exports of all public symbols | VERIFIED | Re-exports `train_model`, `MODEL_IDS`, `PARAM_DIST`, `RANDOM_SEED`, all 6 infrastructure functions; `__all__` list defined |
| `src/sip_engine/__main__.py` | CLI train subcommand with all 5 flags | VERIFIED | Lines 51-78 define all 5 flags; lines 129-148 dispatch to `train_model()` with lazy import |
| `tests/test_models.py` | 20 tests (10 unit + 10 integration) | VERIFIED | 514 lines; 20 tests, all passing in 13.36s |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `trainer.py` | `sklearn.model_selection` | `train_test_split, StratifiedKFold, ParameterSampler` | WIRED | Line 36: `from sklearn.model_selection import ParameterSampler, StratifiedKFold, train_test_split` |
| `trainer.py` | `xgboost` | `XGBClassifier` | WIRED | Line 40: `import xgboost as xgb`; used at lines 178, 259, 741 |
| `trainer.py` | `features/pipeline.py` | `FEATURE_COLUMNS import` | WIRED | Line 519 (lazy inside `train_model`): `from sip_engine.features.pipeline import FEATURE_COLUMNS`; confirmed 34 columns |
| `trainer.py` | `artifacts/models/MX/` | `joblib.dump model + json.dump registry` | WIRED | Line 773: `joblib.dump(clf, model_pkl_path)`; lines 798, 849: `write_text(json.dumps(...))` |
| `__main__.py` | `trainer.py` | `lazy import of train_model` | WIRED | Line 130: `from sip_engine.models.trainer import train_model, MODEL_IDS` |
| `trainer.py` | `iric/thresholds.py` | `calibrate_iric_thresholds + save_iric_thresholds` | WIRED | Lines 638: `from sip_engine.iric.thresholds import calibrate_iric_thresholds, save_iric_thresholds`; called at lines 640-641 (inside try/except) |
| `trainer.py` | `features/encoding.py` | `build_encoding_mappings on train split` | WIRED | Line 658: `from sip_engine.features.encoding import build_encoding_mappings`; called at line 660 (inside try/except) |
| `trainer.py` | `test_data.parquet` | `id_contrato as named index in saved test data` | WIRED | Lines 855-866: asserts `X_test.index.name == "id_contrato"`, uses `pa.Table.from_pandas(test_df, preserve_index=True)` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|------------|------------|-------------|--------|---------|
| MODL-01 | 07-02 | Train M1 (cost overruns) XGBoost binary classifier using only pre-execution features | SATISFIED | `train_model("M1")` implemented; uses FEATURE_COLUMNS (34 pre-execution features only); parameterized test passes |
| MODL-02 | 07-02 | Train M2 (delays) XGBoost binary classifier using only pre-execution features | SATISFIED | `train_model("M2")` implemented; same mechanism as M1; parameterized test passes |
| MODL-03 | 07-02 | Train M3 (Comptroller records) XGBoost binary classifier using only pre-execution features | SATISFIED | `train_model("M3")` implemented; n_splits guard handles extreme imbalance (3 positives in 50-row test); parameterized test passes |
| MODL-04 | 07-02 | Train M4 (SECOP fines) XGBoost binary classifier using only pre-execution features | SATISFIED | `train_model("M4")` implemented; same severe-imbalance handling as M3; parameterized test passes |
| MODL-05 | 07-01 | Evaluates 2 class imbalance strategies per model: scale_pos_weight + 25% upsampling; selects best based on CV | SATISFIED | `_compare_strategies()` evaluates both strategies with identical HP candidates; winner = higher mean CV AUC-ROC; ties go to scale_pos_weight |
| MODL-06 | 07-01 | HP optimization via RandomizedSearchCV with 200 iterations and StratifiedKFold(5) | SATISFIED | `_hp_search()` uses `ParameterSampler` (equivalent to RandomizedSearchCV's sampling) with n_iter=200 default and StratifiedKFold(5) default; configurable via `--n-iter` flag |
| MODL-07 | 07-01 | 70/30 train/test split — CONTEXT.md overrides requirement wording to stratified random (not temporal) | SATISFIED (with documented deviation) | `_stratified_split()` uses `train_test_split(..., stratify=y, random_state=42)`. REQUIREMENTS.md still says "temporal ordering preserved" but CONTEXT.md and MEMORY.md document explicit user decision to use stratified random split. Implementation matches decision. |
| MODL-08 | 07-02 | Serializes trained models to .pkl via joblib with feature name ordering metadata | SATISFIED | `joblib.dump(clf, model_dir / "model.pkl")` at trainer.py:773; final refit uses DataFrame with FEATURE_COLUMNS column names so `feature_names_in_` is set on the XGBClassifier object |
| MODL-09 | 07-02 | Stores `feature_registry.json` alongside each model to guarantee correct feature column ordering | SATISFIED | `feature_registry.json` written at trainer.py:797-798 with `"feature_columns": FEATURE_COLUMNS` in exact order (34 features); `test_feature_registry_column_order` asserts exact match |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/sip_engine/__main__.py` | 151 | `"not yet implemented"` fallthrough | Info | Only reached for `evaluate` and `run-pipeline` subcommands (Phase 8/9 work). The `train` command is fully implemented. No impact on Phase 7 goal. |

No blocker or warning anti-patterns found in Phase 7 files.

### Human Verification Required

None. All Phase 7 deliverables are code infrastructure verifiable programmatically. The actual model artifacts (model.pkl, feature_registry.json, etc.) will be produced when `python -m sip_engine train` is executed against the real SECOP data. That is outside the scope of a code-phase verification.

### Gaps Summary

No gaps. All 9 must-have truths verified. All 4 artifacts substantive and wired. All 9 key links active. All 9 MODL requirements satisfied.

**Notable design decisions implemented correctly:**
- IRIC/encoding recalibrations wrapped in try/except — prevents training failure with test fixtures lacking domain columns; recalibration still occurs against real data
- n_splits auto-reduced when `n_pos_train < n_splits` — handles M3/M4 extreme imbalance (documented at trainer.py:681-691)
- `_json_safe()` recursive numpy type converter ensures JSON serialization never raises on numpy scalars
- `feature_names_in_` set on final model by fitting on DataFrame with FEATURE_COLUMNS — Phase 8 and 9 can use this for column validation

**MODL-07 documentation note:** REQUIREMENTS.md still states "temporal ordering preserved" but this was overridden by explicit user decision (documented in CONTEXT.md line 17 and MEMORY.md). The trainer.py docstring at line 116 confirms: "Implements MODL-07: stratified random split (NOT temporal ordering)." REQUIREMENTS.md should be updated in a future cleanup pass to reflect the actual decision, but this does not constitute a gap — the user decision supersedes the stale requirement text.

---
_Verified: 2026-03-02_
_Verifier: Claude (gsd-verifier)_
