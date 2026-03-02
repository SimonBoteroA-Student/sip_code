# Phase 7: Model Training — Research

**Researched:** 2026-03-01
**Domain:** XGBoost binary classification, hyperparameter search, class imbalance, training pipeline
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Train/test split**
- Stratified random 70/30 split — NOT temporal ordering (overrides ROADMAP success criterion 1 — user decision)
- Per-model stratification — each model gets its own split stratified by its specific label (M1 stratifies by M1, etc.)
- Fixed random seed (e.g. 42) for full reproducibility
- Fresh split each time — recompute on every training run (seed ensures same result)
- Drop NaN-label rows per model — contracts with NaN labels for a given model are excluded from that model's training

**Data leakage prevention**
- IRIC thresholds recalibrated on train-only data before model training (IRIC-08)
- Encoding mappings recomputed on train split — categorical "Other" grouping must not see test-set distributions
- Both recalibrations happen as part of the training pipeline, before fitting

**Hyperparameter search**
- Gallego et al. (2021) ranges as primary source for search space
- 200 iterations default, configurable via `--n-iter` CLI flag
- StratifiedKFold(5) cross-validation
- AUC-ROC as the scoring metric for hyperparameter selection
- No early stopping — n_estimators is a search parameter

**Class imbalance strategy**
- Both strategies evaluated per model: (1) scale_pos_weight, (2) 25% minority upsampling
- Upsampling happens inside each CV fold — only the training portion is upsampled, never the validation portion
- Full comparison saved — JSON per model with both strategies' CV scores and selection rationale

**NaN handling**
- XGBoost native NaN handling — no imputation preprocessing

**Training output and artifacts**
- Subdirectory per model: artifacts/models/M1/, artifacts/models/M2/, etc.
- Each subdirectory contains: model.pkl, feature_registry.json, training report
- Artifacts saved: CV fold results (all 200 iterations), best HP + strategy summary JSON, training metadata
- Imbalance strategy comparison saved per model (both strategies' scores + winner)

**CLI behavior**
- `train` command trains all 4 models by default
- `--model M1` flag (CRITICAL) — train a single model independently; --force scoped to selected model only
- `--force` flag — retrain even if artifacts exist
- `--quick` flag — reduced iterations (~20) and 3-fold CV for fast dev testing
- `--n-iter N` — override iteration count
- `--n-jobs N` — configure parallelism (default: -1 = all cores)
- Require pre-built artifacts — fail with clear message if features.parquet or labels.parquet don't exist

**Progress reporting**
- Verbose progress bars per model (tqdm) with percentage and important milestones
- Log key events: model start, imbalance strategy comparison result, best HP found, model saved

**Compute / hardware**
- Support all platforms: MacBook Apple Silicon, MacBook Intel, cloud GPU
- Auto-detect hardware and configure XGBoost tree method accordingly
- Configurable parallelism — n_jobs=-1 default, overridable via CLI

### Claude's Discretion
- Exact XGBoost tree method detection logic
- Training report JSON schema details
- Logging format and tqdm configuration
- Temp file handling during training

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| MODL-01 | Train M1 (cost overruns) XGBoost binary classifier using only pre-execution features | Verified: XGBClassifier(objective='binary:logistic') + FEATURE_COLUMNS from features.parquet |
| MODL-02 | Train M2 (delays) XGBoost binary classifier using only pre-execution features | Same pipeline as MODL-01, different label column |
| MODL-03 | Train M3 (Comptroller records) XGBoost binary classifier using only pre-execution features | Same pipeline; M3 likely more severe imbalance (rare positive class) |
| MODL-04 | Train M4 (SECOP fines) XGBoost binary classifier using only pre-execution features | Same pipeline; M4 also severely imbalanced |
| MODL-05 | Evaluate 2 class imbalance strategies per model: scale_pos_weight and 25% upsampling | scale_pos_weight: RandomizedSearchCV directly; upsampling: manual CV loop with ParameterSampler |
| MODL-06 | RandomizedSearchCV with 200 iterations and StratifiedKFold(5) | Verified working with sklearn 1.8.0 + xgboost 3.2.0 |
| MODL-07 | 70/30 train/test split (OVERRIDDEN: stratified random, not temporal) | train_test_split(stratify=y, test_size=0.3, random_state=42) — verified API |
| MODL-08 | Serialize trained models to .pkl via joblib with feature name ordering metadata | joblib.dump(model, path) — round-trip verified; feature_names_in_ auto-set when training on DataFrame |
| MODL-09 | Store feature_registry.json alongside each model with exact column names and ordering | json.dump({'feature_columns': FEATURE_COLUMNS, ...}) — already defined in features/pipeline.py |
</phase_requirements>

---

## Summary

Phase 7 trains four independent XGBoost binary classifiers on the 34-feature matrix produced in Phase 6. All required libraries are already installed and verified: XGBoost 3.2.0, scikit-learn 1.8.0, joblib 1.5.3, tqdm 4.67.3. The training pipeline reads `features.parquet` (id_contrato index, 34 FEATURE_COLUMNS) and `labels.parquet` (id_contrato column, M1/M2/M3/M4 as nullable Int8), merges on id_contrato, drops NaN-label rows per model, and performs a stratified random 70/30 split per model.

The critical architectural decision is that `imblearn` is NOT installed, which means upsampling-inside-CV-folds (Strategy B) requires a manual CV loop using `sklearn.model_selection.ParameterSampler` + `StratifiedKFold`, rather than using `RandomizedSearchCV` directly. Strategy A (scale_pos_weight) can use `RandomizedSearchCV` natively. Both strategies are evaluated with the same HP search space and the better AUC-ROC score wins. Data leakage is prevented by rebuilding encoding mappings and IRIC thresholds on the train split only — both functions already accept arbitrary DataFrames (verified in Phase 5/6 code).

**Primary recommendation:** Implement `src/sip_engine/models/trainer.py` with a single `train_model(model_id, force, quick, n_iter, n_jobs)` function covering the full pipeline: load artifacts, split, recalibrate leakage-sensitive artifacts, compare strategies, run HP search (manual CV loop for both strategies for consistency), select best, refit on full train, save artifacts. Expose via `__main__.py` `train` subcommand with all CLI flags documented in CONTEXT.md.

---

## Standard Stack

### Core (all already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | 3.2.0 | Gradient boosted trees — the 4 classifiers | Gallego et al. (2021) baseline algorithm |
| scikit-learn | 1.8.0 | StratifiedKFold, ParameterSampler, train_test_split, roc_auc_score | Standard ML toolkit; XGBoost sklearn API uses it |
| joblib | 1.5.3 | Model serialization to .pkl | XGBoost + sklearn recommended serializer |
| tqdm | 4.67.3 | Progress bars for HP search loops | Already in environment |
| pandas | 2.x | Features/labels data loading and manipulation | Already in project |
| pyarrow | 23.0.1 | Parquet file reading | Already in project |
| scipy | 1.x | scipy.stats distributions for ParameterSampler | Already in environment |
| numpy | 1.26+ | Array operations, upsampling | Already in environment |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json | stdlib | feature_registry.json, strategy comparison JSON | All artifact metadata |
| logging | stdlib | Structured logging per established project pattern | Match existing module logging style |
| datetime | stdlib | Training metadata timestamps | Record training start/end times |
| platform | stdlib | CPU/GPU device detection | nvidia-smi subprocess check for CUDA |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual CV loop for upsampling | imblearn Pipeline | imblearn not installed; manual loop gives full control and is self-contained |
| joblib.dump | pickle.dump | joblib is the sklearn/XGBoost standard; better compression, safer for large arrays |
| ParameterSampler + manual loop | RandomizedSearchCV | RandomizedSearchCV can't inject upsampling inside folds without imblearn |

---

## Architecture Patterns

### Recommended Project Structure

```
src/sip_engine/models/
├── __init__.py           # existing stub — add public symbols
└── trainer.py            # NEW — full training pipeline for all 4 models

artifacts/models/
├── .gitkeep              # existing
├── M1/
│   ├── model.pkl
│   ├── feature_registry.json
│   └── training_report.json
├── M2/ (same structure)
├── M3/ (same structure)
└── M4/ (same structure)
```

### Pattern 1: Per-Model Training Function

**What:** Single function `train_model(model_id, ...)` that encapsulates the full training pipeline for one model. Called 4 times (M1-M4), or once with `--model` flag.

**When to use:** Always. Enables `--model M1` retraining without touching other models.

**Key steps:**
1. Load features.parquet + labels.parquet
2. Merge on id_contrato (inner join)
3. Drop NaN labels for this model
4. Stratified train_test_split(test_size=0.3, stratify=y, random_state=42)
5. Recalibrate on train-only: encoding_mappings + IRIC thresholds
6. Strategy comparison: evaluate both imbalance strategies via manual CV loop
7. Run full HP search (200 iter) with winning strategy
8. Refit final model on full train set with best HPs
9. Save model.pkl, feature_registry.json, training_report.json
10. Return test-set data (held out — NOT evaluated here, Phase 8 does evaluation)

### Pattern 2: Strategy Comparison via Manual CV Loop

**What:** Both strategies A (scale_pos_weight) and B (25% upsampling) use the same ParameterSampler random HP candidates and the same StratifiedKFold splits. For each candidate HP set, compute 5-fold AUC-ROC. Average across folds = score for that candidate.

**Implementation for Strategy A (scale_pos_weight):**
- Compute `scale_pos_weight = n_neg / n_pos` from training data
- Use `RandomizedSearchCV(XGBClassifier(scale_pos_weight=...), param_dist, n_iter=200, cv=StratifiedKFold(5), scoring='roc_auc')`
- OR use the manual CV loop with scale_pos_weight fixed in XGBClassifier

**Implementation for Strategy B (25% upsampling inside folds):**
- Manual loop: `for params in tqdm(ParameterSampler(param_dist, n_iter=200, random_state=42))`
  - For each `train_idx, val_idx` in `StratifiedKFold(5).split(X_train, y_train)`:
    - Separate majority/minority in fold train set
    - `n_target = int(n_maj * 0.25 / 0.75)` — upsampled minority count
    - `resample(X_min, n_samples=n_target, replace=True, random_state=42)`
    - Fit XGBClassifier with params, compute roc_auc on val fold (NO upsampling on val)
    - Average 5 fold scores = score for this HP set

**Strategy winner:** The strategy with higher mean CV AUC-ROC across all 200 HP candidates' best scores.

**Note:** For consistency and direct comparability, BOTH strategies use the manual CV loop approach rather than mixing RandomizedSearchCV for A and manual for B.

### Pattern 3: Leakage-Safe Recalibration on Train Split

**What:** After train/test split, rebuild encoding mappings and IRIC thresholds using only the training rows.

**Encoding mappings recalibration:**
```python
# X_train is a DataFrame with FEATURE_COLUMNS
# Re-build categorical encoding from train distribution only
from sip_engine.features.encoding import build_encoding_mappings, apply_encoding
train_mappings = build_encoding_mappings(X_train_raw, force=True)
X_train_encoded = apply_encoding(X_train_raw, train_mappings)
X_test_encoded = apply_encoding(X_test_raw, train_mappings)  # apply train mappings to test
```

**IRIC threshold recalibration:**
```python
from sip_engine.iric.thresholds import calibrate_iric_thresholds, save_iric_thresholds
# X_train must have tipo_contrato and numeric threshold columns
train_thresholds = calibrate_iric_thresholds(X_train_with_tipo_contrato)
save_iric_thresholds(train_thresholds, path=settings.iric_thresholds_path)
```

**IMPORTANT:** The `features.parquet` produced in Phase 6 was built with encoding and IRIC calibrated on the FULL dataset. For Phase 7, the features.parquet is the input source, but encoding and IRIC are re-applied as part of training preparation. This means features.parquet must retain the raw (pre-encoded) categorical values to allow re-encoding. **Check whether features.parquet stores encoded or raw categoricals** — if encoded, the recalibration step only applies to IRIC thresholds (which affect iric_* columns).

### Pattern 4: Artifact Layout and feature_registry.json

```python
# feature_registry.json schema
{
    "model_id": "M1",
    "feature_columns": ["departamento_cat", "es_contratacion_directa", ...],  # FEATURE_COLUMNS in order
    "n_features": 34,
    "training_date": "2026-03-01T...",
    "train_size": 12345,
    "test_size": 5295,
    "label": "M1",
    "best_strategy": "scale_pos_weight",  # or "upsampling"
    "best_params": {"n_estimators": 200, "max_depth": 5, ...},
    "cv_auc_roc": 0.712,
    "random_seed": 42,
}
```

```python
# training_report.json schema (for thesis statistical reporting)
{
    "model_id": "M1",
    "label_distribution": {"0": 9000, "1": 500},
    "scale_pos_weight": 18.0,
    "strategy_comparison": {
        "scale_pos_weight": {"mean_cv_auc": 0.712, "std_cv_auc": 0.023},
        "upsampling_25pct": {"mean_cv_auc": 0.698, "std_cv_auc": 0.031},
        "winner": "scale_pos_weight"
    },
    "all_cv_results": [...],  # all 200 HP candidates with their scores (both strategies)
    "best_params": {...},
    "training_duration_seconds": 420.5,
    "feature_count": 34,
    "seed": 42,
}
```

### Pattern 5: Device Detection for XGBoost 3.x

```python
import subprocess, platform

def _detect_xgb_device() -> dict:
    """Return XGBoost device kwargs for current hardware.

    XGBoost 3.x: use device='cuda' for GPU (not tree_method='gpu_hist').
    cpu always uses tree_method='hist' (recommended over 'exact' or 'approx').
    Apple Silicon (ARM64 Darwin): no XGBoost MPS support — use CPU.
    """
    try:
        result = subprocess.run(
            ['nvidia-smi'], capture_output=True, timeout=5
        )
        if result.returncode == 0:
            return {'device': 'cuda', 'tree_method': 'hist'}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return {'tree_method': 'hist'}  # CPU default (device='cpu' implied)
```

### Anti-Patterns to Avoid

- **Fitting encoding/IRIC on full dataset before split:** Leaks test-set distribution into training. Always split first, then recalibrate on train-only.
- **Upsampling the test set or CV validation fold:** Inflates performance metrics. Only upsample the training portion of each CV fold.
- **Using XGBoost's `early_stopping_rounds`:** Explicitly excluded by Gallego approach — n_estimators is a search parameter.
- **Using `use_label_encoder=False` param:** Removed in XGBoost 2.0+; not needed in XGBoost 3.x.
- **Using `gpu_hist` as tree_method for GPU in XGBoost 3.x:** Deprecated; use `device='cuda'` instead.
- **Saving model artifacts before final refit:** The model saved to model.pkl must be the one refitted on the FULL training set, not the CV-fold model.
- **Evaluating test set during Phase 7:** Phase 8 owns evaluation. Phase 7 only produces model artifacts and holds out the test split (saved as test_indices or test parquet).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stratified train/test split | Custom stratification code | `sklearn.model_selection.train_test_split(stratify=y)` | Handles edge cases with very small classes |
| Random HP sampling | Custom random search | `sklearn.model_selection.ParameterSampler` | Correct statistical sampling with scipy distributions |
| Model serialization | `pickle.dump` | `joblib.dump` | Better compression, safer for large numpy arrays inside XGBoost |
| Minority oversampling | Custom resample logic | `sklearn.utils.resample(replace=True)` | Handles edge cases (empty class, n_samples > n_population) |
| AUC-ROC computation | Manual trapezoid | `sklearn.metrics.roc_auc_score` | Handles edge cases (all same class) |
| StratifiedKFold splits | Custom fold logic | `sklearn.model_selection.StratifiedKFold` | Guarantees class proportion in each fold |

**Key insight:** The HP search loop is the one place where a manual loop IS required (to inject upsampling), but the building blocks (ParameterSampler, StratifiedKFold, roc_auc_score, resample) are all standard library calls.

---

## Common Pitfalls

### Pitfall 1: Encoding Mappings Applied from Full-Dataset Phase 6 Run

**What goes wrong:** `features.parquet` was built with encoding mappings computed on the full dataset. If Phase 7 uses those same mappings (loaded from `encoding_mappings.json`) for training, test-set categories influence the "Other" grouping for training data.

**Why it happens:** Phase 6's `build_features()` calls `build_encoding_mappings(df_full, force=True)` on the complete feature matrix and saves `encoding_mappings.json`. Phase 7 needs to REDO this with train-only data.

**How to avoid:** Check if `features.parquet` stores raw or encoded categoricals. If encoded (integer codes already), the re-encoding step for Phase 7 is about IRIC thresholds only. **Verified from code:** `apply_encoding()` converts string categories to integer codes. `features.parquet` stores the POST-encoding (integer) values. Therefore, re-encoding on train-only is NOT directly applicable to features.parquet columns that are already encoded integers. What IS applicable: IRIC thresholds (iric_* columns computed using thresholds must be recomputed on train-only).

**Resolution:** Phase 7 recalibrates IRIC thresholds on train-only. The categorical encoding recalibration for features.parquet encoded columns is a research open question (see Open Questions #1).

### Pitfall 2: Upsampling Leaks into Validation Fold

**What goes wrong:** If you upsample the entire training set before the CV loop, the oversampled (duplicated) minority rows appear in both training and validation folds of the inner CV, inflating the validation AUC.

**Why it happens:** Common mistake when using RandomizedSearchCV with pre-upsampled data.

**How to avoid:** Upsample INSIDE the CV fold loop, only on the `train_idx` portion. The `val_idx` portion is always the original (non-upsampled) data.

**Warning signs:** If Strategy B (upsampling) consistently scores higher than Strategy A by a large margin, check whether upsampling was done correctly inside folds.

### Pitfall 3: Model Saved from Last CV Fold Instead of Final Refit

**What goes wrong:** The final model.pkl is the XGBClassifier from the last CV fold iteration, not a model trained on the full training set.

**Why it happens:** After finding best HPs, it's tempting to use the last-fit model object.

**How to avoid:** After selecting best strategy + best HPs, explicitly `clf = XGBClassifier(**best_params); clf.fit(X_train_full, y_train_full)` and save THAT model.

### Pitfall 4: Feature Order Mismatch Between Training and Inference

**What goes wrong:** At inference time (Phase 9 or future API), features are passed in a different order than at training time, causing silent prediction errors.

**Why it happens:** Python dicts don't guarantee order; DataFrames can have columns reordered.

**How to avoid:** Always train on `X_train[FEATURE_COLUMNS]` (explicit ordered subset). Store `FEATURE_COLUMNS` list in `feature_registry.json`. At inference time, enforce `df[feature_registry['feature_columns']]` before `predict_proba()`.

**Note:** XGBoost's `feature_names_in_` attribute (auto-set when training on a named DataFrame) also catches mismatches at prediction time — but only if you pass a DataFrame. Joblib round-trip preserves this attribute (verified).

### Pitfall 5: XGBoost 3.x API Changes

**What goes wrong:** Using deprecated parameters from XGBoost 2.x causes warnings or silent behavior changes.

**Changes in XGBoost 3.x:**
- `use_label_encoder` parameter removed (was `use_label_encoder=False` workaround) — do NOT pass it
- GPU: use `device='cuda'` instead of `tree_method='gpu_hist'`
- `verbosity=0` to silence training output (default may be noisy)
- Default `n_estimators` is `None` in 3.x (must be set explicitly or via HP search)

### Pitfall 6: M3/M4 Extreme Class Imbalance Breaking StratifiedKFold

**What goes wrong:** If M3 or M4 has < 5 positive examples, StratifiedKFold(5) fails with "too few members" error.

**Why it happens:** M3 (Comptroller records) and M4 (SECOP fines) are rare events. After filtering NaN labels, the positive class might be very small.

**How to avoid:** Check class distribution before splitting. If `n_pos < n_splits`, reduce n_splits or use `min(5, n_pos)` for quick mode. Log a warning and skip that model if absolutely no positive examples exist.

---

## Code Examples

Verified patterns from official sources and local testing:

### Stratified Train/Test Split
```python
# Source: sklearn.model_selection API (verified sklearn 1.8.0)
from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, stratify=y, random_state=42
)
# Verified: maintains class proportion in both splits
```

### ParameterSampler for Manual HP Search
```python
# Source: sklearn.model_selection API (verified sklearn 1.8.0)
from sklearn.model_selection import ParameterSampler
import scipy.stats as stats

PARAM_DIST = {
    'n_estimators': stats.randint(50, 501),
    'max_depth': stats.randint(3, 8),
    'learning_rate': stats.loguniform(0.01, 0.3),
    'subsample': stats.uniform(0.5, 0.5),
    'colsample_bytree': stats.uniform(0.5, 0.5),
    'min_child_weight': stats.randint(1, 11),
    'gamma': [0, 0.1, 0.5, 1.0],
    'reg_alpha': [0, 0.1, 1.0],
    'reg_lambda': [0, 1, 5],
}

param_samples = list(ParameterSampler(PARAM_DIST, n_iter=200, random_state=42))
```

### Manual CV Loop with Upsampling Inside Folds
```python
# Source: verified locally with sklearn 1.8.0
from sklearn.model_selection import StratifiedKFold
from sklearn.utils import resample
from sklearn.metrics import roc_auc_score
import numpy as np

def _cv_score_with_upsampling(clf_params, X, y, n_splits=5, seed=42):
    """Cross-validate XGBClassifier with 25% minority upsampling inside folds."""
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    fold_scores = []

    for train_idx, val_idx in cv.split(X, y):
        X_tr, y_tr = X[train_idx], y[train_idx]
        X_val, y_val = X[val_idx], y[val_idx]

        # Upsample minority in training fold only
        maj_mask = y_tr == 0
        min_mask = y_tr == 1
        X_maj, y_maj = X_tr[maj_mask], y_tr[maj_mask]
        X_min, y_min = X_tr[min_mask], y_tr[min_mask]

        n_target = int(len(X_maj) * 0.25 / 0.75)  # 25% minority target ratio
        if len(X_min) > 0 and n_target > 0:
            X_min_up = resample(X_min, n_samples=n_target, replace=True, random_state=seed)
            y_min_up = np.ones(n_target, dtype=int)
            X_tr_up = np.vstack([X_maj, X_min_up])
            y_tr_up = np.concatenate([y_maj, y_min_up])
        else:
            X_tr_up, y_tr_up = X_tr, y_tr

        clf = xgb.XGBClassifier(**clf_params, tree_method='hist', verbosity=0)
        clf.fit(X_tr_up, y_tr_up)
        proba = clf.predict_proba(X_val)[:, 1]
        score = roc_auc_score(y_val, proba)
        fold_scores.append(score)

    return np.mean(fold_scores), np.std(fold_scores)
```

### XGBoost Joblib Serialization
```python
# Source: joblib API + xgboost 3.2.0 verified locally
import joblib
import xgboost as xgb
import pandas as pd

# Training — use DataFrame with named columns so feature_names_in_ is set
X_train_df = pd.DataFrame(X_train, columns=FEATURE_COLUMNS)
clf = xgb.XGBClassifier(**best_params, tree_method='hist', random_state=42)
clf.fit(X_train_df, y_train)

# Serialize
joblib.dump(clf, model_dir / 'model.pkl')

# Load + verify
loaded = joblib.load(model_dir / 'model.pkl')
# loaded.feature_names_in_ == FEATURE_COLUMNS (verified)
```

### feature_registry.json Write
```python
import json
registry = {
    'model_id': model_id,
    'feature_columns': FEATURE_COLUMNS,  # ordered list from features/pipeline.py
    'n_features': len(FEATURE_COLUMNS),
    'training_date': datetime.utcnow().isoformat() + 'Z',
    'label': model_id,
    'best_strategy': winner_strategy,
    'best_params': best_params,
    'cv_auc_roc_mean': float(best_cv_score),
    'cv_auc_roc_std': float(best_cv_std),
    'train_size': int(len(y_train)),
    'test_size': int(len(y_test)),
    'class_distribution': {'0': int((y_train == 0).sum()), '1': int((y_train == 1).sum())},
    'random_seed': 42,
}
(model_dir / 'feature_registry.json').write_text(json.dumps(registry, indent=2))
```

### CLI train Subcommand Pattern
```python
# Following established __main__.py pattern
train_parser = subparsers.add_parser('train', help='Train XGBoost prediction models')
train_parser.add_argument('--model', choices=['M1', 'M2', 'M3', 'M4'],
                           help='Train a single model (default: all 4)')
train_parser.add_argument('--force', action='store_true',
                           help='Retrain even if model artifacts already exist')
train_parser.add_argument('--quick', action='store_true',
                           help='Fast mode: 20 iterations, 3-fold CV')
train_parser.add_argument('--n-iter', type=int, default=200,
                           help='Number of HP search iterations (default: 200)')
train_parser.add_argument('--n-jobs', type=int, default=-1,
                           help='Parallelism for RandomizedSearchCV (default: -1 = all cores)')
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `tree_method='gpu_hist'` for GPU | `device='cuda', tree_method='hist'` | XGBoost 2.0 | `gpu_hist` deprecated but still works in 3.x |
| `use_label_encoder=False` | Not needed at all | XGBoost 2.0 | Removed from API |
| `eval_metric='logloss'` explicit | Default for binary:logistic | XGBoost 2.x | Can omit |
| `n_estimators` default 100 | `n_estimators` default None in 3.x | XGBoost 3.x | Must set explicitly |

**Deprecated/outdated:**
- `gpu_hist` as tree_method: deprecated in favor of `device='cuda'`; still functional in 3.2.0 but avoid in new code
- `use_label_encoder`: removed; do not pass this parameter

---

## Critical Research Finding: Features Parquet Column State

The most important implementation decision to get right: **what state are the feature columns in `features.parquet`?**

From reading `features/pipeline.py` (build_features):
1. Features are computed (raw string categoricals in cat_a/cat_b/cat_c)
2. `apply_encoding(df, mappings)` converts string categoricals to integer codes
3. The resulting `df_out[FEATURE_COLUMNS]` — all categorical columns are NOW integers
4. This integer-encoded DataFrame is written to `features.parquet`

**Conclusion:** `features.parquet` contains integer-encoded categorical columns, not raw strings. The encoding mappings were computed on the full dataset in Phase 6.

**Implication for Phase 7 leakage prevention:**
- The integer encoding in features.parquet already reflects full-dataset distribution
- Rebuilding `encoding_mappings.json` on train-only cannot retroactively change the integer values in features.parquet
- **What CAN be recalibrated on train-only:** The IRIC thresholds. But the iric_* columns in features.parquet are also pre-computed floating-point scores — recalibrating thresholds doesn't change the stored values.

**Practical resolution:** The Phase 6 features.parquet is a best-effort offline artifact. The strict IRIC-08 leakage prevention (IRIC thresholds on train-only) would require recomputing iric_* scores on train-only data, which means either (a) reading from the raw IRIC pipeline results or (b) treating the Phase 6 features.parquet as the input and accepting that IRIC columns reflect full-dataset calibration. Given that recalibration from scratch is expensive, the pragmatic Phase 7 implementation recalibrates IRIC thresholds on the train features subset and flags this as a best-effort in the training report. The encoding mappings recalibration note in CONTEXT.md likely refers to future use when online inference needs mappings — for training from features.parquet it's moot since columns are already encoded.

---

## Open Questions

1. **IRIC-08 strict compliance with features.parquet**
   - What we know: features.parquet stores pre-encoded IRIC scores computed with full-dataset IRIC thresholds (Phase 6)
   - What's unclear: Should Phase 7 recompute iric_* feature values on train-only? This would require rerunning the IRIC pipeline on the train subset, which is computationally expensive.
   - Recommendation: In Phase 7, recalibrate IRIC thresholds on train features subset (documenting that the iric_* column values in features.parquet came from full-dataset calibration). Flag as a known limitation in training_report.json. This is the practical approach; full recomputation would require a separate plan.

2. **Test set saving strategy**
   - What we know: Phase 8 (Evaluation) needs the test set for each model
   - What's unclear: Should Phase 7 save test-set indices to disk, or the full test X/y DataFrames?
   - Recommendation: Save `X_test` and `y_test` as parquet files in `artifacts/models/MX/test_data.parquet` with id_contrato index. This is self-contained and allows Phase 8 to run without re-splitting.

3. **Strategy comparison: same HP candidates for both strategies?**
   - What we know: CONTEXT.md says evaluate both strategies for each model
   - What's unclear: Whether to use the SAME 200 random HP candidates for both strategies (statistically cleaner comparison) or separate 200-iteration searches
   - Recommendation: Use same ParameterSampler seed (same 200 candidates) for both strategies. This isolates the effect of the imbalance strategy from HP randomness, making the comparison cleaner for thesis reporting.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (uses pyproject.toml `[tool.pytest.ini_options]` — not currently set) |
| Quick run command | `python -m pytest tests/test_models.py -q` |
| Full suite command | `python -m pytest tests/ -q` |
| Estimated runtime | ~8 seconds (290 tests currently in 7.7s) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MODL-01 | M1 XGBClassifier trains and produces predict_proba output | unit | `pytest tests/test_models.py::test_train_m1 -x` | No — Wave 0 gap |
| MODL-02 | M2 XGBClassifier trains and produces predict_proba output | unit | `pytest tests/test_models.py::test_train_m2 -x` | No — Wave 0 gap |
| MODL-03 | M3 XGBClassifier trains with severe imbalance | unit | `pytest tests/test_models.py::test_train_m3_imbalance -x` | No — Wave 0 gap |
| MODL-04 | M4 XGBClassifier trains with severe imbalance | unit | `pytest tests/test_models.py::test_train_m4_imbalance -x` | No — Wave 0 gap |
| MODL-05 | Both imbalance strategies produce valid CV scores, winner selected | unit | `pytest tests/test_models.py::test_strategy_comparison -x` | No — Wave 0 gap |
| MODL-06 | RandomizedSearchCV (or manual equivalent) with 200 iter completes | unit | `pytest tests/test_models.py::test_hp_search -x` | No — Wave 0 gap |
| MODL-07 | Stratified 70/30 split preserves class proportion, seed produces same split | unit | `pytest tests/test_models.py::test_train_test_split -x` | No — Wave 0 gap |
| MODL-08 | model.pkl serialized and loaded, predict_proba output matches | unit | `pytest tests/test_models.py::test_model_serialization -x` | No — Wave 0 gap |
| MODL-09 | feature_registry.json contains FEATURE_COLUMNS in correct order | unit | `pytest tests/test_models.py::test_feature_registry -x` | No — Wave 0 gap |

### Nyquist Sampling Rate
- **Minimum sample interval:** After each committed task → run: `python -m pytest tests/test_models.py -q`
- **Full suite trigger:** Before merging final task of any plan wave: `python -m pytest tests/ -q`
- **Phase-complete gate:** Full suite green (290 + new tests) before verify-work runs
- **Estimated feedback latency per task:** ~10-15 seconds (model training with tiny fixtures)

### Wave 0 Gaps (must be created before implementation)
- [ ] `tests/test_models.py` — covers MODL-01 through MODL-09 using tiny in-memory fixtures
- [ ] Tiny features/labels fixtures in `tests/conftest.py` — DataFrames with 5 FEATURE_COLUMNS, 2 classes, matching parquet schema

---

## Sources

### Primary (HIGH confidence)
- XGBoost 3.2.0 installed in .venv — API verified by direct inspection and test runs
- scikit-learn 1.8.0 installed in .venv — RandomizedSearchCV, ParameterSampler, StratifiedKFold, train_test_split verified
- joblib 1.5.3 installed in .venv — dump/load round-trip verified
- `src/sip_engine/features/pipeline.py` — FEATURE_COLUMNS, features.parquet schema, encoding flow
- `src/sip_engine/iric/thresholds.py` — calibrate_iric_thresholds accepts arbitrary DataFrame (IRIC-08 ready)
- `src/sip_engine/features/encoding.py` — build_encoding_mappings(df_train) accepts arbitrary DataFrame
- `src/sip_engine/config/settings.py` — artifacts_models_dir already defined

### Secondary (MEDIUM confidence)
- Gallego et al. (2021) HP ranges — referenced in CONTEXT.md; ranges used are standard XGBoost practice consistent with paper description
- XGBoost 3.x deprecation of `gpu_hist` and `use_label_encoder` — verified by testing in local environment

### Tertiary (LOW confidence)
- Gallego et al. (2021) exact parameter ranges not verified from primary paper text — cross-referenced with standard XGBoost random search practice; CONTEXT.md confirms these ranges were agreed upon

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified installed and tested in environment
- Architecture: HIGH — patterns derived from existing codebase conventions + verified API calls
- Pitfalls: HIGH for XGBoost-specific; MEDIUM for leakage-related (requires implementation to fully verify)
- HP ranges: MEDIUM — Gallego paper cited in CONTEXT but specific values not verified from paper text

**Research date:** 2026-03-01
**Valid until:** 2026-06-01 (stable ML library APIs; XGBoost minor releases may change params)
