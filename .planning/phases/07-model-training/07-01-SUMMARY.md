---
phase: 07-model-training
plan: 01
subsystem: models
tags: [xgboost, sklearn, scipy, training-infrastructure, hp-search, cross-validation, imbalance]

# Dependency graph
requires:
  - phase: 06-iric
    provides: FEATURE_COLUMNS (34 features), features.parquet schema, iric pipeline
  - phase: 05-feature-engineering
    provides: encoding mappings pattern, provider history index

provides:
  - "_detect_xgb_device(): CUDA/CPU device detection for XGBoost 3.x"
  - "_stratified_split(): 70/30 stratified random split, seed=42, MODL-07"
  - "_cv_score_scale_pos_weight(): StratifiedKFold CV with scale_pos_weight strategy (Strategy A)"
  - "_cv_score_upsampling(): manual CV loop with 25% minority upsampling inside folds (Strategy B)"
  - "_compare_strategies(): runs both strategies, selects winner by mean AUC-ROC"
  - "_hp_search(): ParameterSampler loop over PARAM_DIST with tqdm progress, n_iter=200 default"
  - "PARAM_DIST: Gallego et al. (2021) HP search space (9 params, scipy.stats distributions)"
  - "MODEL_IDS: ['M1', 'M2', 'M3', 'M4']"
  - "tests/test_models.py: 10 unit tests for all infrastructure functions"

affects:
  - 07-02 (train_model() orchestrator — uses all 6 functions directly)
  - 08-evaluation (test split produced by _stratified_split)
  - 09-explainability (model artifacts produced after HP search)

# Tech tracking
tech-stack:
  added:
    - xgboost 3.2.0 (XGBClassifier, objective=binary:logistic)
    - scipy.stats (randint, loguniform, uniform for ParameterSampler)
    - sklearn.model_selection (ParameterSampler, StratifiedKFold, train_test_split)
    - sklearn.metrics (roc_auc_score)
    - sklearn.utils (resample for minority upsampling)
    - tqdm (progress bar for HP search loop)
  patterns:
    - Manual CV loop with ParameterSampler for upsampling-inside-folds (Strategy B)
    - Both imbalance strategies evaluated with same HP candidates for fair comparison
    - subprocess nvidia-smi check for CUDA detection (5s timeout, FileNotFoundError catch)
    - Ties in strategy comparison go to scale_pos_weight (simpler model)

key-files:
  created:
    - src/sip_engine/models/trainer.py
    - tests/test_models.py
  modified:
    - src/sip_engine/models/__init__.py

key-decisions:
  - "Both imbalance strategies (scale_pos_weight and 25% upsampling) use the same manual ParameterSampler CV loop for consistent comparison — not RandomizedSearchCV for A and manual for B"
  - "Upsampling target: n_target = int(n_maj * 0.25 / 0.75) achieves 25% minority ratio in upsampled fold training set"
  - "n_jobs parameter reserved but unused — manual CV loop with upsampling doesn't parallelize cleanly with joblib"
  - "Strategy tie goes to scale_pos_weight (simpler model, no synthetic data)"
  - "device_kwargs dict pattern: unpacked into XGBClassifier — allows passing {} for default or {'device': 'cuda', 'tree_method': 'hist'} for GPU"

patterns-established:
  - "Pattern: device kwargs as separate dict unpacked into XGBClassifier — clean separation of hardware from HP params"
  - "Pattern: all_results list accumulates every iteration result for thesis statistical reporting"
  - "Pattern: progress bar shows live best_auc with tqdm set_postfix"

requirements-completed:
  - MODL-05
  - MODL-06
  - MODL-07

# Metrics
duration: 3min
completed: 2026-03-02
---

# Phase 7 Plan 01: Model Training Infrastructure Summary

**XGBoost training infrastructure: 6 helper functions covering device detection, stratified 70/30 split, dual imbalance strategy CV scoring (scale_pos_weight + 25% upsampling-inside-folds), strategy comparison, and Gallego et al. HP search loop with tqdm progress**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-02T10:17:48Z
- **Completed:** 2026-03-02T10:20:48Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Created `trainer.py` with 6 functions + 3 constants (PARAM_DIST, MODEL_IDS, RANDOM_SEED), all importable
- Manual CV loop for both imbalance strategies using same ParameterSampler candidates — ensures fair comparison and correct upsampling-inside-folds (no leakage to val)
- 10 unit tests pass in 4.34s (well under 15s limit); full 300-test suite passing with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement training infrastructure functions in trainer.py** - `221d9ee` (feat)
2. **Task 2: Unit tests for training infrastructure** - `5f41a82` (test)

**Plan metadata:** (docs: complete plan — pending final commit)

## Files Created/Modified

- `src/sip_engine/models/trainer.py` - 6 training infrastructure functions + 3 constants (PARAM_DIST, MODEL_IDS, RANDOM_SEED)
- `src/sip_engine/models/__init__.py` - Updated with re-exports of all public symbols
- `tests/test_models.py` - 10 unit tests covering all 6 functions and constants

## Decisions Made

- Both strategies use the same manual CV loop (not RandomizedSearchCV for A and manual for B) — consistent, fair comparison; both can inject upsampling logic equivalently
- Upsampling fraction: n_target = int(n_maj * 0.25 / 0.75) — targets 25% minority ratio in upsampled training fold
- n_jobs reserved but not implemented — manual loops with upsampling don't parallelize cleanly with joblib without restructuring
- Strategy ties resolved in favor of scale_pos_weight (simpler, no synthetic data creation)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 6 infrastructure functions ready for use by `train_model()` orchestrator in Plan 07-02
- `_stratified_split()` will produce per-model train/test sets
- `_hp_search()` will be called once per model (M1-M4) with n_iter=200 default
- `_compare_strategies()` handles both imbalance strategies with correct fold isolation
- Plan 07-02 additionally needs: joblib serialization, artifact layout (artifacts/models/MX/), CLI train subcommand, leakage-safe IRIC recalibration

## Self-Check: PASSED

- FOUND: src/sip_engine/models/trainer.py
- FOUND: tests/test_models.py
- FOUND: .planning/phases/07-model-training/07-01-SUMMARY.md
- FOUND: commit 221d9ee (feat: training infrastructure functions)
- FOUND: commit 5f41a82 (test: unit tests for training infrastructure)

---
*Phase: 07-model-training*
*Completed: 2026-03-02*
