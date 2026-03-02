# Phase 7: Model Training - Context

**Gathered:** 2026-03-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Train 4 XGBoost binary classifiers (M1 cost overruns, M2 delays, M3 Comptroller records, M4 SECOP fines) on pre-execution features only, with class imbalance strategy selected per model and hyperparameters optimized via randomized search. Produce serialized model artifacts with feature registries. Evaluation metrics and SHAP explainability belong to Phases 8 and 9.

</domain>

<decisions>
## Implementation Decisions

### Train/test split
- **Stratified random 70/30 split** — NOT temporal ordering (overrides ROADMAP success criterion 1 — user decision)
- **Per-model stratification** — each model gets its own split stratified by its specific label (M1 stratifies by M1, etc.)
- **Fixed random seed** (e.g. 42) for full reproducibility
- **Fresh split each time** — recompute on every training run (seed ensures same result)
- **Drop NaN-label rows per model** — contracts with NaN labels for a given model are excluded from that model's training

### Data leakage prevention
- **IRIC thresholds recalibrated on train-only data** before model training (IRIC-08)
- **Encoding mappings recomputed on train split** — categorical "Other" grouping must not see test-set distributions
- Both recalibrations happen as part of the training pipeline, before fitting

### Hyperparameter search
- **Gallego et al. (2021) ranges** as primary source for search space; fall back to standard XGBoost ranges if paper doesn't document specific params
- **200 iterations default**, configurable via `--n-iter` CLI flag
- **StratifiedKFold(5)** cross-validation
- **AUC-ROC** as the scoring metric for hyperparameter selection
- **No early stopping** — n_estimators is a search parameter (Gallego approach)

### Class imbalance strategy
- Both strategies evaluated per model: (1) scale_pos_weight, (2) 25% minority upsampling
- **Upsampling happens inside each CV fold** — only the training portion is upsampled, never the validation portion
- **Full comparison saved** — JSON per model with both strategies' CV scores and selection rationale

### NaN handling
- **XGBoost native NaN handling** — no imputation preprocessing. XGBoost learns optimal split direction for missing values.

### Training output & artifacts
- **Subdirectory per model**: artifacts/models/M1/, artifacts/models/M2/, etc.
- Each subdirectory contains: model.pkl, feature_registry.json, training report
- **Artifacts saved**: CV fold results (all 200 iterations), best HP + strategy summary JSON, training metadata (sizes, class distributions, feature count, duration, seed)
- **Imbalance strategy comparison** saved per model (both strategies' scores + winner)

### CLI behavior
- **`train` command** trains all 4 models by default
- **`--model M1` flag** (CRITICAL) — train a single model independently. --force scoped to selected model only.
- **`--force` flag** — retrain even if artifacts exist; skip if artifacts present without --force. Consistent with other commands.
- **`--quick` flag** — reduced iterations (~20) and 3-fold CV for fast dev testing
- **`--n-iter N`** — override iteration count
- **`--n-jobs N`** — configure parallelism (default: -1 = all cores)
- **Require pre-built artifacts** — fail with clear message if features.parquet or labels.parquet don't exist

### Progress reporting
- **Verbose progress bars** per model (tqdm) with percentage and important milestones
- Log key events: model start, imbalance strategy comparison result, best HP found, model saved

### Compute / hardware
- **Support all platforms**: MacBook Apple Silicon, MacBook Intel, cloud GPU
- Auto-detect hardware and configure XGBoost tree method accordingly (hist for CPU, gpu_hist for GPU)
- **Configurable parallelism** — n_jobs=-1 default, overridable via CLI

### Claude's Discretion
- Exact XGBoost tree method detection logic
- Training report JSON schema details
- Logging format and tqdm configuration
- Temp file handling during training

</decisions>

<specifics>
## Specific Ideas

- Follow Gallego et al. (2021) methodology as closely as possible — hyperparameter ranges, RandomizedSearchCV pattern, no early stopping
- Per-model training flag is essential for development iteration — must be able to retrain M1 without waiting for M2-M4
- All training artifacts should support thesis writeup: strategy comparison tables, CV results for statistical reporting

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-model-training*
*Context gathered: 2026-03-01*
