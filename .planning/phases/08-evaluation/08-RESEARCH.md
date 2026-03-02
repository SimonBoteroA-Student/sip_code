# Phase 8: Evaluation — Research

**Researched:** 2026-03-02
**Domain:** Binary classifier evaluation, ranking metrics (MAP@k, NDCG@k), probability calibration, report generation
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Metrics Suite**
- AUC-ROC: Primary discrimination metric for all 4 models
- MAP@k: Computed at k=100, k=500, k=1000 (ranking quality for imbalanced models)
- NDCG@k: Same k values as MAP (k=100, k=500, k=1000) for consistency
- Precision/Recall: Fine threshold sweep from 0.05 to 0.95 in 0.05 increments (19 thresholds)
- Brier Score: Probability calibration quality indicator
- Optimal threshold: F1-maximizing threshold on test set per model (recommended operating point)

**Report Structure & Formats**
- Three output formats per model: JSON (machine-readable), CSV (tabular), Markdown (human-readable)
- JSON includes ROC curve data points (FPR/TPR pairs) for plot-ready output
- Confusion matrices computed at each decision threshold (19 per model)
- Class imbalance strategy comparison results from Phase 7 included (both strategies' CV scores + selection rationale)
- Full hyperparameter search history (all 200 iterations) included to show optimization landscape
- Label prevalence and test set size included per model for metric contextualization

**Cross-Model Comparison**
- Per-model reports at `artifacts/evaluation/M{n}/` subdirectories
- Cross-model summary reports: `artifacts/evaluation/summary.json` and `artifacts/evaluation/summary.csv`
- Console output: verbose — print all metrics during evaluation, ending with a formatted summary table of key metrics across all 4 models
- No minimum performance thresholds or pass/fail gates — metrics reported as-is (academic context)
- Summary includes dataset context: test set size, label prevalence per model

**Evaluation CLI & Workflow**
- `python -m sip_engine evaluate` runs all 4 models by default
- `python -m sip_engine evaluate --model M1` evaluates a single model
- Re-runs produce timestamped versions (e.g., `M1_eval_2026-03-02.json`) — no overwrite
- Auto-discovers models from `artifacts/models/M*/model.pkl` by default
- Optional `--models-dir` flag to override model artifact directory
- Output structure: `artifacts/evaluation/M{n}/` per-model subdirectories mirroring model artifact structure

### Claude's Discretion
- Exact markdown report formatting and section ordering
- Console table library choice (rich, tabulate, prettytable)
- Internal metric computation approach (prefer sklearn where available)
- JSON schema nesting and key naming (as long as it's machine-readable and complete)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EVAL-01 | System reports AUC-ROC as primary metric for all 4 models | `sklearn.metrics.roc_auc_score` + `roc_curve` for curve data |
| EVAL-02 | System reports MAP@100 and MAP@1000 for all models | Custom implementation using `label_ranking_average_precision_score` |
| EVAL-03 | System reports NDCG@k for ranking quality assessment | `sklearn.metrics.ndcg_score` (available in sklearn 0.24+) |
| EVAL-04 | System reports Precision and Recall at multiple thresholds | `precision_recall_curve` or manual computation with `confusion_matrix` |
| EVAL-05 | System reports Brier Score for probability calibration | `sklearn.metrics.brier_score_loss` |
| EVAL-06 | System generates structured evaluation report (JSON + CSV + MD) per model with all metrics, best hyperparameters, and class balance strategy | File I/O + pandas DataFrame to CSV + JSON serialization |

</phase_requirements>

---

## Summary

Phase 8 evaluates all 4 trained XGBoost models (M1-M4) on the held-out test set using a comprehensive academic metrics suite: AUC-ROC (discrimination), MAP@k and NDCG@k (ranking quality for imbalanced classes), Precision/Recall at multiple thresholds (decision boundary analysis), and Brier Score (calibration quality). The phase produces structured evaluation reports in three formats (JSON, CSV, Markdown) per model plus a cross-model summary.

**Critical insight from PITFALLS.md:** For M3 (Comptroller records, ~1-2% positive) and M4 (SECOP fines, ~1% positive), MAP@100/MAP@1000 are the metrics that matter for operational use — "Can the model identify the riskiest 100 contracts for investigation?" AUC-ROC can be inflated by calibration effects. Phase 7 used AUC-ROC for hyperparameter selection (established), but Phase 8 must report ranking metrics to validate that the models actually rank high-risk contracts at the top of the score distribution.

**Key architectural decision:** This is a pure evaluation phase — no model retraining, no hyperparameter search, no feature engineering. All models and test data artifacts already exist from Phase 7. The evaluation module loads `artifacts/models/M{n}/model.pkl`, `artifacts/models/M{n}/test_data.parquet` (with id_contrato index and label column), and `artifacts/models/M{n}/training_report.json` (for context), then computes metrics and writes reports.

---

## Standard Stack

### Core (all already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| scikit-learn | 1.8.0 | All metrics computation (AUC-ROC, Brier, NDCG, Precision/Recall) | Standard ML evaluation toolkit |
| pandas | 2.x | Load test_data.parquet, organize metrics into tables, write CSV reports | Already in project |
| pyarrow | 23.0.1 | Parquet file reading for test_data.parquet | Already in project |
| joblib | 1.5.3 | Load serialized models (model.pkl) | XGBoost + sklearn standard |
| numpy | 1.26+ | Array operations, threshold sweeps, ranking computations | Already in environment |
| xgboost | 3.2.0 | Model.predict() and .predict_proba() calls | Model prediction interface |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json | stdlib | Read training_report.json, write eval JSON reports | All metadata I/O |
| csv | stdlib | Alternative to pandas for simple CSV writes (optional) | If pandas overhead is unnecessary |
| datetime | stdlib | Timestamp for versioned evaluation runs | Report metadata |
| pathlib | stdlib | Path manipulation for artifact discovery | All file operations |
| logging | stdlib | Structured logging per established project pattern | Match existing module logging style |
| tabulate | 0.9+ (or rich) | Console table formatting for cross-model summary | Human-readable summary output |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sklearn.metrics.ndcg_score | Manual NDCG implementation | sklearn NDCG available in 0.24+; prefer stdlib unless bugs found |
| sklearn.metrics.label_ranking_average_precision_score | Manual MAP@k loop | sklearn function is for single k; manual loop needed for k=100/500/1000 |
| pandas.DataFrame.to_csv() | csv.DictWriter | pandas is heavier but handles nested data and index preservation better |
| tabulate | rich.table | tabulate is lighter, rich has better color/formatting; either acceptable |
| JSON schema generation | Manual dict construction | Manual is simpler for this use case; schema validation is overkill for v1 |

---

## Architecture Patterns

### Recommended Project Structure

```
src/sip_engine/evaluation/
├── __init__.py           # Public symbols: evaluate_model, evaluate_all
└── evaluator.py          # NEW — full evaluation pipeline

artifacts/evaluation/
├── .gitkeep              # existing
├── M1/
│   ├── M1_eval.json      # Machine-readable report
│   ├── M1_eval.csv       # Tabular metrics
│   └── M1_eval.md        # Human-readable report
├── M2/
│   ├── M2_eval.json
│   ├── M2_eval.csv
│   └── M2_eval.md
├── M3/
│   ├── M3_eval.json
│   ├── M3_eval.csv
│   └── M3_eval.md
├── M4/
│   ├── M4_eval.json
│   ├── M4_eval.csv
│   └── M4_eval.md
├── summary.json          # Cross-model comparison (JSON)
└── summary.csv           # Cross-model comparison (CSV)
```

### Evaluation Pipeline Flow

**Per-Model Evaluation** (`evaluate_model(model_id)` function):

1. **Load artifacts**
   - `model = joblib.load(f"artifacts/models/{model_id}/model.pkl")`
   - `test_df = pd.read_parquet(f"artifacts/models/{model_id}/test_data.parquet")`
   - `training_report = json.load(f"artifacts/models/{model_id}/training_report.json")`

2. **Extract X_test and y_test**
   - `y_test = test_df[model_id].values` (label column)
   - `X_test = test_df[FEATURE_COLUMNS].values` (34 feature columns from feature_registry.json)

3. **Generate predictions**
   - `y_pred_proba = model.predict_proba(X_test)[:, 1]` (positive class probabilities)
   - `y_pred_binary = model.predict(X_test)` (binary predictions — default threshold 0.5)

4. **Compute metrics**
   - **AUC-ROC**: `roc_auc_score(y_test, y_pred_proba)`
   - **ROC curve data**: `fpr, tpr, thresholds = roc_curve(y_test, y_pred_proba)`
   - **Brier Score**: `brier_score_loss(y_test, y_pred_proba)`
   - **MAP@k**: Custom loop for k=100, 500, 1000 (see below)
   - **NDCG@k**: `ndcg_score(y_test.reshape(1, -1), y_pred_proba.reshape(1, -1), k=k)` for k=100, 500, 1000
   - **Precision/Recall sweep**: Loop over thresholds [0.05, 0.10, ..., 0.95], compute confusion matrix, derive P/R
   - **Optimal threshold**: Find threshold that maximizes F1 score on test set
   - **Confusion matrices**: Compute at each threshold for full decision boundary analysis

5. **Build evaluation report**
   - Aggregate all metrics into structured dict
   - Include training context from training_report.json (best_params, strategy, CV scores)
   - Add dataset context (test_set_size, positive_count, negative_count, positive_rate)

6. **Write three output files**
   - JSON: Full nested structure with all metrics, ROC curve points, threshold sweep results
   - CSV: Flattened tabular format (one row per threshold with P/R/F1, plus summary rows for AUC/Brier/MAP/NDCG)
   - Markdown: Human-readable report with sections for each metric category

**Cross-Model Summary** (`evaluate_all()` function after all 4 models):

7. **Aggregate key metrics across models**
   - AUC-ROC, Brier Score, MAP@100, MAP@1000, NDCG@100, NDCG@1000
   - Optimal threshold per model, precision/recall at optimal threshold
   - Test set size and positive rate per model

8. **Console summary table**
   - Print formatted table (tabulate or rich) with rows = models, columns = key metrics
   - Example columns: Model | AUC | Brier | MAP@100 | MAP@1000 | NDCG@100 | Optimal Threshold | P@Optimal | R@Optimal

9. **Write summary files**
   - `summary.json`: Nested dict with all models' key metrics
   - `summary.csv`: Tabular format (one row per model)

---

## Metric Implementation Details

### 1. AUC-ROC (EVAL-01)

**Sklearn API:**
```python
from sklearn.metrics import roc_auc_score, roc_curve

auc = roc_auc_score(y_true, y_scores)
fpr, tpr, thresholds = roc_curve(y_true, y_scores)
```

**What it measures:** Area under the ROC curve — probability that a randomly chosen positive example ranks higher than a randomly chosen negative example. Range [0, 1], higher is better. Threshold-independent.

**When it's useful:** General discrimination quality. Works for all 4 models but can be inflated by calibration for highly imbalanced M3/M4.

**JSON output format:**
```json
{
  "auc_roc": 0.7854,
  "roc_curve": {
    "fpr": [0.0, 0.01, 0.02, ..., 1.0],
    "tpr": [0.0, 0.15, 0.31, ..., 1.0],
    "thresholds": [1.0, 0.95, 0.91, ..., 0.0]
  }
}
```

**Warning:** For M3/M4, AUC > 0.80 may indicate overfitting or leakage (Gallego et al. achieved ~0.78 for M3). Cross-check with MAP@100.

---

### 2. MAP@k (EVAL-02)

**Manual implementation required** — sklearn's `label_ranking_average_precision_score` computes label ranking AP (different formulation). For binary classification with imbalanced classes, we need MAP@k where k = top-k ranked predictions.

**Algorithm:**
```python
def map_at_k(y_true, y_scores, k):
    """
    Mean Average Precision at k.
    
    For binary classification:
    1. Rank all predictions by score (descending)
    2. Select top k predictions
    3. Compute precision at each position where a positive appears
    4. Average those precisions
    
    Args:
        y_true: Binary labels (0/1), shape (n_samples,)
        y_scores: Predicted probabilities, shape (n_samples,)
        k: Number of top predictions to consider
    
    Returns:
        MAP@k score (float)
    """
    # Sort by predicted score descending
    sorted_indices = np.argsort(y_scores)[::-1]
    y_true_sorted = y_true[sorted_indices]
    
    # Truncate to top k
    y_true_topk = y_true_sorted[:k]
    
    # Compute precision at each positive position
    precisions = []
    num_positives = 0
    for i, label in enumerate(y_true_topk):
        if label == 1:
            num_positives += 1
            precision_at_i = num_positives / (i + 1)
            precisions.append(precision_at_i)
    
    # Average precision (return 0 if no positives in top k)
    return np.mean(precisions) if precisions else 0.0
```

**What it measures:** How well the model ranks positive examples at the top of the score distribution. Critical for M3/M4 where investigators will review the top 100-1000 contracts.

**When it's useful:** Imbalanced classification where top-k retrieval matters operationally. More informative than AUC for M3/M4.

**Expected ranges (from PITFALLS.md):**
- M3 (Comptroller, ~1-2% positive): MAP@100 should be > 0.10 (10%) to be useful. Values < 0.05 indicate poor ranking.
- M4 (SECOP fines, ~1% positive): Similar — MAP@100 > 0.10 baseline.
- M1/M2 (~16-18% positive): MAP@100 may be higher (0.30-0.50) due to higher positive density.

**JSON output format:**
```json
{
  "map_at_k": {
    "map_100": 0.1234,
    "map_500": 0.0987,
    "map_1000": 0.0856
  }
}
```

---

### 3. NDCG@k (EVAL-03)

**Sklearn API:**
```python
from sklearn.metrics import ndcg_score

# Reshape for sklearn API (expects 2D: samples x items)
y_true_2d = y_true.reshape(1, -1)
y_scores_2d = y_scores.reshape(1, -1)

ndcg_100 = ndcg_score(y_true_2d, y_scores_2d, k=100)
ndcg_500 = ndcg_score(y_true_2d, y_scores_2d, k=500)
ndcg_1000 = ndcg_score(y_true_2d, y_scores_2d, k=1000)
```

**What it measures:** Normalized Discounted Cumulative Gain — ranking quality with position-based discounting (top positions weighted more heavily). Range [0, 1], higher is better.

**When it's useful:** Complements MAP@k for ranking evaluation. More forgiving of slight ranking errors at lower positions.

**JSON output format:**
```json
{
  "ndcg_at_k": {
    "ndcg_100": 0.2345,
    "ndcg_500": 0.1987,
    "ndcg_1000": 0.1756
  }
}
```

---

### 4. Precision/Recall at Multiple Thresholds (EVAL-04)

**Two implementation approaches:**

**Option A: Use precision_recall_curve (recommended):**
```python
from sklearn.metrics import precision_recall_curve

precision, recall, thresholds = precision_recall_curve(y_true, y_scores)

# Interpolate to desired threshold values [0.05, 0.10, ..., 0.95]
target_thresholds = np.arange(0.05, 1.0, 0.05)
precision_at_thresholds = []
recall_at_thresholds = []

for t in target_thresholds:
    y_pred_at_t = (y_scores >= t).astype(int)
    p = precision_score(y_true, y_pred_at_t, zero_division=0)
    r = recall_score(y_true, y_pred_at_t, zero_division=0)
    precision_at_thresholds.append(p)
    recall_at_thresholds.append(r)
```

**Option B: Manual computation with confusion matrix:**
```python
from sklearn.metrics import confusion_matrix

for threshold in [0.05, 0.10, 0.15, ..., 0.95]:
    y_pred = (y_scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    # Store (threshold, precision, recall, f1, confusion_matrix)
```

**What it measures:**
- **Precision:** Of all contracts predicted as high-risk, what % are truly high-risk? (False positive control)
- **Recall:** Of all truly high-risk contracts, what % are detected? (False negative control)
- **F1:** Harmonic mean of P and R (balanced metric)

**When it's useful:** Understanding decision boundary tradeoffs. Low thresholds (0.05-0.20) maximize recall (catch all risks, many false positives). High thresholds (0.70-0.95) maximize precision (few false positives, miss some risks).

**Optimal threshold (F1-maximizing):**
```python
f1_scores = []
for t in thresholds:
    y_pred = (y_scores >= t).astype(int)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    f1_scores.append(f1)

optimal_idx = np.argmax(f1_scores)
optimal_threshold = thresholds[optimal_idx]
optimal_f1 = f1_scores[optimal_idx]
```

**JSON output format:**
```json
{
  "threshold_analysis": {
    "thresholds": [0.05, 0.10, 0.15, ..., 0.95],
    "precision": [0.12, 0.15, 0.18, ..., 0.95],
    "recall": [0.98, 0.94, 0.89, ..., 0.05],
    "f1": [0.21, 0.26, 0.30, ..., 0.09],
    "confusion_matrices": [
      {"threshold": 0.05, "tn": 10000, "fp": 500, "fn": 2, "tp": 98},
      ...
    ]
  },
  "optimal_threshold": {
    "value": 0.35,
    "precision": 0.45,
    "recall": 0.67,
    "f1": 0.54
  }
}
```

**CSV format (one row per threshold):**
```csv
threshold,precision,recall,f1,tn,fp,fn,tp
0.05,0.12,0.98,0.21,10000,500,2,98
0.10,0.15,0.94,0.26,10200,300,6,94
...
```

---

### 5. Brier Score (EVAL-05)

**Sklearn API:**
```python
from sklearn.metrics import brier_score_loss

brier = brier_score_loss(y_true, y_scores)
```

**What it measures:** Mean squared error between predicted probabilities and true labels. Range [0, 1], lower is better. Measures calibration quality — are predicted probabilities well-calibrated to true positive rates?

**When it's useful:** Complementary to AUC-ROC. A model can have high AUC (good ranking) but poor Brier (badly calibrated probabilities). For this project, probabilities are used in the CRI composite index, so calibration matters.

**Expected ranges:**
- Well-calibrated model: < 0.15
- Poor calibration: > 0.25
- Trivial baseline (always predict positive rate): = positive_rate * (1 - positive_rate)

**JSON output format:**
```json
{
  "brier_score": 0.1234,
  "brier_baseline": 0.1568
}
```

**Baseline computation** (for context):
```python
positive_rate = y_true.mean()
brier_baseline = positive_rate * (1 - positive_rate)
```

---

## Report Schemas

### JSON Report Schema (per model)

```json
{
  "model_id": "M1",
  "evaluation_date": "2026-03-02T12:34:56Z",
  "test_set_size": 102300,
  "label_distribution": {
    "0": 83884,
    "1": 18416,
    "positive_rate": 0.180
  },
  
  "discrimination": {
    "auc_roc": 0.7854,
    "roc_curve": {
      "fpr": [...],
      "tpr": [...],
      "thresholds": [...]
    }
  },
  
  "ranking": {
    "map_100": 0.3456,
    "map_500": 0.2987,
    "map_1000": 0.2654,
    "ndcg_100": 0.4123,
    "ndcg_500": 0.3876,
    "ndcg_1000": 0.3654
  },
  
  "calibration": {
    "brier_score": 0.1234,
    "brier_baseline": 0.1476
  },
  
  "threshold_analysis": {
    "thresholds": [0.05, 0.10, ..., 0.95],
    "precision": [...],
    "recall": [...],
    "f1": [...],
    "confusion_matrices": [...]
  },
  
  "optimal_threshold": {
    "value": 0.35,
    "precision": 0.45,
    "recall": 0.67,
    "f1": 0.54,
    "confusion_matrix": {"tn": 10500, "fp": 300, "fn": 50, "tp": 150}
  },
  
  "training_context": {
    "best_params": {...},
    "strategy_selected": "scale_pos_weight",
    "strategy_comparison": {...},
    "n_iter": 200,
    "n_splits": 5,
    "cv_auc_mean": 0.7621,
    "cv_auc_std": 0.0234
  }
}
```

### CSV Report Schema (per model)

**Option 1: Threshold-centric (one row per threshold):**
```csv
metric_type,threshold,value,precision,recall,f1,tn,fp,fn,tp
threshold,0.05,,0.12,0.98,0.21,10000,500,2,98
threshold,0.10,,0.15,0.94,0.26,10200,300,6,94
...
summary,optimal_threshold,0.35,0.45,0.67,0.54,10500,300,50,150
summary,auc_roc,0.7854,,,,,,
summary,brier_score,0.1234,,,,,,
summary,map_100,0.3456,,,,,,
summary,map_500,0.2987,,,,,,
summary,map_1000,0.2654,,,,,,
summary,ndcg_100,0.4123,,,,,,
summary,ndcg_500,0.3876,,,,,,
summary,ndcg_1000,0.3654,,,,,,
```

**Option 2: Metric-centric (one row per metric category):**
```csv
metric_category,metric_name,value
discrimination,auc_roc,0.7854
ranking,map_100,0.3456
ranking,map_500,0.2987
ranking,map_1000,0.2654
ranking,ndcg_100,0.4123
ranking,ndcg_500,0.3876
ranking,ndcg_1000,0.3654
calibration,brier_score,0.1234
optimal,threshold,0.35
optimal,precision,0.45
optimal,recall,0.67
optimal,f1,0.54
```

**Recommendation:** Use Option 1 for threshold analysis detail, Option 2 for summary reports. Phase decision: Claude's discretion per CONTEXT.md.

### Markdown Report Structure

```markdown
# Evaluation Report: Model M1

**Generated:** 2026-03-02 12:34:56 UTC
**Model Path:** artifacts/models/M1/model.pkl
**Test Set Size:** 102,300 contracts
**Positive Rate:** 18.0% (18,416 / 102,300)

---

## Discrimination Metrics

| Metric | Value |
|--------|-------|
| AUC-ROC | 0.7854 |

The ROC curve data is available in `M1_eval.json` for plotting.

---

## Ranking Metrics

| Metric | Value | Interpretation |
|--------|-------|----------------|
| MAP@100 | 0.3456 | Average precision in top 100 ranked contracts |
| MAP@500 | 0.2987 | Average precision in top 500 ranked contracts |
| MAP@1000 | 0.2654 | Average precision in top 1000 ranked contracts |
| NDCG@100 | 0.4123 | Ranking quality (top 100) with position discounting |
| NDCG@500 | 0.3876 | Ranking quality (top 500) with position discounting |
| NDCG@1000 | 0.3654 | Ranking quality (top 1000) with position discounting |

---

## Calibration Metrics

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Brier Score | 0.1234 | Lower is better (well-calibrated < 0.15) |
| Baseline Brier | 0.1476 | Trivial predictor (always predict positive rate) |

---

## Threshold Analysis

**Optimal Threshold (F1-Maximizing):** 0.35

| Threshold | Precision | Recall | F1 | TN | FP | FN | TP |
|-----------|-----------|--------|----|----|----|----|-----|
| 0.05 | 0.12 | 0.98 | 0.21 | 10000 | 500 | 2 | 98 |
| 0.10 | 0.15 | 0.94 | 0.26 | 10200 | 300 | 6 | 94 |
| ... | ... | ... | ... | ... | ... | ... | ... |

Full threshold sweep available in `M1_eval.csv`.

---

## Training Context

**Selected Strategy:** scale_pos_weight

**Best Hyperparameters:**
- n_estimators: 350
- max_depth: 6
- learning_rate: 0.05
- subsample: 0.8
- colsample_bytree: 0.7
- ...

**Cross-Validation Performance:**
- Mean AUC-ROC: 0.7621 ± 0.0234

**Strategy Comparison:**
- scale_pos_weight: CV AUC = 0.7621
- upsampling_25pct: CV AUC = 0.7512

Full training details in `artifacts/models/M1/training_report.json`.
```

---

## Cross-Model Summary Schema

### JSON Schema

```json
{
  "evaluation_date": "2026-03-02T12:34:56Z",
  "models": {
    "M1": {
      "test_set_size": 102300,
      "positive_rate": 0.180,
      "auc_roc": 0.7854,
      "brier_score": 0.1234,
      "map_100": 0.3456,
      "map_1000": 0.2654,
      "ndcg_100": 0.4123,
      "ndcg_1000": 0.3654,
      "optimal_threshold": 0.35,
      "precision_at_optimal": 0.45,
      "recall_at_optimal": 0.67
    },
    "M2": {...},
    "M3": {...},
    "M4": {...}
  }
}
```

### CSV Schema

```csv
model_id,test_set_size,positive_rate,auc_roc,brier_score,map_100,map_500,map_1000,ndcg_100,ndcg_500,ndcg_1000,optimal_threshold,precision_at_optimal,recall_at_optimal
M1,102300,0.180,0.7854,0.1234,0.3456,0.2987,0.2654,0.4123,0.3876,0.3654,0.35,0.45,0.67
M2,102300,0.165,0.7621,0.1356,0.3123,0.2765,0.2456,0.3987,0.3654,0.3421,0.32,0.42,0.64
M3,102300,0.012,0.7412,0.0123,0.1234,0.0987,0.0856,0.2345,0.1987,0.1756,0.18,0.08,0.52
M4,102300,0.010,0.7298,0.0112,0.1156,0.0923,0.0812,0.2198,0.1876,0.1654,0.15,0.07,0.48
```

---

## CLI Integration

### Argument Parsing (`__main__.py` updates)

Already exists: `subparsers.add_parser("evaluate", help="Evaluate trained models")`

**Add arguments to evaluate subparser:**
```python
evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate trained models")
evaluate_parser.add_argument(
    "--model",
    choices=["M1", "M2", "M3", "M4"],
    help="Evaluate a single model (default: all 4)",
)
evaluate_parser.add_argument(
    "--models-dir",
    type=Path,
    help="Override model artifacts directory (default: artifacts/models)",
)
evaluate_parser.add_argument(
    "--output-dir",
    type=Path,
    help="Override evaluation output directory (default: artifacts/evaluation)",
)
```

### CLI Implementation

```python
elif args.command == "evaluate":
    from sip_engine.evaluation.evaluator import evaluate_all, evaluate_model
    
    models_to_eval = [args.model] if args.model else MODEL_IDS
    
    try:
        if len(models_to_eval) == 1:
            # Single model evaluation
            report_path = evaluate_model(
                model_id=models_to_eval[0],
                models_dir=args.models_dir,
                output_dir=args.output_dir,
            )
            print(f"Evaluation complete: {report_path}")
        else:
            # All models evaluation + cross-model summary
            summary_path = evaluate_all(
                models_dir=args.models_dir,
                output_dir=args.output_dir,
            )
            print(f"Evaluation complete: {summary_path}")
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error during evaluation: {e}", file=sys.stderr)
        sys.exit(1)
```

---

## Implementation Strategy

### Module: `src/sip_engine/evaluation/evaluator.py`

**Public API:**
- `evaluate_model(model_id: str, models_dir: Path | None, output_dir: Path | None) -> Path`
- `evaluate_all(models_dir: Path | None, output_dir: Path | None) -> Path`

**Private helpers:**
- `_load_artifacts(model_id, models_dir) -> (model, test_df, training_report)`
- `_compute_discrimination_metrics(y_true, y_scores) -> dict`
- `_compute_ranking_metrics(y_true, y_scores) -> dict`
- `_compute_calibration_metrics(y_true, y_scores) -> dict`
- `_compute_threshold_analysis(y_true, y_scores) -> dict`
- `_write_json_report(eval_dict, output_path)`
- `_write_csv_report(eval_dict, output_path)`
- `_write_markdown_report(eval_dict, output_path)`
- `_print_summary_table(models_summary)`

### Timestamping Strategy

Per CONTEXT.md: "Re-runs produce timestamped versions — no overwrite"

**Implementation:**
```python
from datetime import datetime

def _get_output_path(output_dir: Path, model_id: str, extension: str) -> Path:
    """Generate timestamped output path if file exists."""
    base_path = output_dir / model_id / f"{model_id}_eval{extension}"
    
    if not base_path.exists():
        return base_path
    
    # File exists — add timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    timestamped_path = output_dir / model_id / f"{model_id}_eval_{timestamp}{extension}"
    return timestamped_path
```

### Progress Reporting

**Console output pattern:**
```
Evaluating model M1...
  ✓ Loaded model and test data (10,230 samples, 18.0% positive)
  ✓ Computed AUC-ROC: 0.7854
  ✓ Computed Brier Score: 0.1234
  ✓ Computed MAP@100: 0.3456, MAP@500: 0.2987, MAP@1000: 0.2654
  ✓ Computed NDCG@100: 0.4123, NDCG@500: 0.3876, NDCG@1000: 0.3654
  ✓ Analyzed 19 decision thresholds
  ✓ Reports written to artifacts/evaluation/M1/
    - M1_eval.json
    - M1_eval.csv
    - M1_eval.md

Evaluating model M2...
...

Cross-Model Summary:
┌────────┬──────────┬──────┬────────┬─────────┬─────────┬──────────┐
│ Model  │ AUC-ROC  │ MAP  │ NDCG   │ Brier   │ Optimal │ P@Opt    │
│        │          │ @100 │ @100   │ Score   │ Thresh  │          │
├────────┼──────────┼──────┼────────┼─────────┼─────────┼──────────┤
│ M1     │ 0.7854   │ 0.35 │ 0.41   │ 0.1234  │ 0.35    │ 0.45     │
│ M2     │ 0.7621   │ 0.31 │ 0.40   │ 0.1356  │ 0.32    │ 0.42     │
│ M3     │ 0.7412   │ 0.12 │ 0.23   │ 0.0123  │ 0.18    │ 0.08     │
│ M4     │ 0.7298   │ 0.12 │ 0.22   │ 0.0112  │ 0.15    │ 0.07     │
└────────┴──────────┴──────┴────────┴─────────┴─────────┴──────────┘

Summary reports written to artifacts/evaluation/
```

---

## Testing Strategy

### Unit Tests (`tests/test_evaluation.py`)

**Fixtures:**
```python
@pytest.fixture
def mock_test_data():
    """Minimal test dataset for metric computation."""
    np.random.seed(42)
    n = 100
    y_true = np.array([1] * 20 + [0] * 80)  # 20% positive
    y_scores = np.random.rand(n)
    # Make positives slightly higher scoring on average
    y_scores[:20] += 0.3
    y_scores = np.clip(y_scores, 0, 1)
    return y_true, y_scores
```

**Test cases:**
- `test_map_at_k_computation()` — verify MAP@k logic with known ranking
- `test_ndcg_at_k_computation()` — verify NDCG@k sklearn API usage
- `test_threshold_analysis()` — verify precision/recall at multiple thresholds
- `test_optimal_threshold_f1()` — verify F1-maximizing threshold selection
- `test_brier_score()` — verify sklearn brier_score_loss usage
- `test_roc_auc()` — verify sklearn roc_auc_score usage
- `test_json_report_schema()` — verify JSON structure completeness
- `test_csv_report_format()` — verify CSV parsability
- `test_markdown_report_generation()` — verify MD file generation (smoke test)
- `test_timestamped_output()` — verify no overwrite behavior

### Integration Tests

**Prerequisite:** Run `python -m sip_engine train --quick` to generate M1 model artifacts

**Test case:**
```python
def test_evaluate_model_end_to_end(tmp_path):
    """Full evaluation pipeline on real trained model."""
    # Assumes artifacts/models/M1/ exists from Phase 7
    output_dir = tmp_path / "evaluation"
    
    report_path = evaluate_model(
        model_id="M1",
        models_dir=None,  # Use default
        output_dir=output_dir,
    )
    
    # Verify all three report files exist
    assert (output_dir / "M1" / "M1_eval.json").exists()
    assert (output_dir / "M1" / "M1_eval.csv").exists()
    assert (output_dir / "M1" / "M1_eval.md").exists()
    
    # Verify JSON schema completeness
    json_report = json.loads((output_dir / "M1" / "M1_eval.json").read_text())
    assert "discrimination" in json_report
    assert "ranking" in json_report
    assert "calibration" in json_report
    assert "threshold_analysis" in json_report
    assert "optimal_threshold" in json_report
    assert "training_context" in json_report
```

---

## Edge Cases & Error Handling

### Edge Case 1: Zero positives in test set
**Scenario:** M3 or M4 has no positive examples in test set (extreme split luck)
**Handling:** Metrics return NaN/0.0 gracefully, report includes warning note

### Edge Case 2: Model file missing
**Scenario:** `artifacts/models/M1/model.pkl` doesn't exist
**Handling:** Raise `FileNotFoundError` with clear message: "Model M1 not found — run 'python -m sip_engine train --model M1' first"

### Edge Case 3: test_data.parquet missing
**Scenario:** Model exists but test_data.parquet doesn't (incomplete Phase 7)
**Handling:** Raise `FileNotFoundError` with clear message

### Edge Case 4: Feature column mismatch
**Scenario:** test_data.parquet columns don't match model's feature_names_in_
**Handling:** Raise ValueError with column diff

### Edge Case 5: All predictions same value (model collapsed)
**Scenario:** Model predicts constant score (e.g., all 0.5)
**Handling:** AUC-ROC = 0.5, MAP/NDCG = 0, report includes warning note

### Edge Case 6: Label column not in test_data.parquet
**Scenario:** Model ID column missing from test_data.parquet
**Handling:** Raise `KeyError` with clear message: "Label column 'M1' not found in test_data.parquet"

---

## Performance Considerations

### Memory Usage
- Test set size: ~100K contracts × 34 features = ~3.4M float64 values = ~27 MB (negligible)
- ROC curve data: ~100K thresholds × 3 arrays (fpr, tpr, thresholds) = ~2.4 MB (acceptable)
- Threshold analysis: 19 thresholds × confusion matrices = ~1 KB (trivial)

**No memory optimization needed** — full test set fits easily in memory.

### Computation Time
- AUC-ROC: O(n log n) for sorting — ~10ms for 100K samples
- ROC curve: O(n) — ~5ms
- Brier Score: O(n) — <1ms
- MAP@k: O(n log n) for sorting + O(k) for top-k — ~10ms
- NDCG@k: O(n log n) + sklearn overhead — ~20ms
- Threshold analysis: 19 iterations × O(n) confusion matrix — ~50ms
- **Total per model: ~100-200ms**

**No parallelization needed** — evaluation is I/O bound (loading artifacts), not compute bound.

### Disk Usage
- JSON report: ~500 KB per model (includes full ROC curve)
- CSV report: ~50 KB per model (threshold sweep)
- Markdown report: ~10 KB per model
- **Total per model: ~600 KB × 4 models = ~2.4 MB**

Negligible compared to model artifacts (~50 MB per model from Phase 7).

---

## Risks & Mitigations

### Risk 1: MAP@k implementation bug (incorrect ranking)
**Likelihood:** MEDIUM — manual implementation required
**Impact:** HIGH — primary metric for M3/M4
**Mitigation:** Unit test with known ranking where MAP@k is hand-computable. Verify against sklearn's `label_ranking_average_precision_score` for single-k case.

### Risk 2: NDCG@k sklearn API misuse (dimension mismatch)
**Likelihood:** LOW — well-documented API
**Impact:** MEDIUM — crashes evaluation
**Mitigation:** Test with minimal fixture, verify 2D reshape requirement in docs

### Risk 3: Threshold analysis performance (19 iterations × 4 models)
**Likelihood:** LOW — fast operations
**Impact:** LOW — slightly slower evaluation
**Mitigation:** Profile if needed; threshold sweep is already fast (<100ms per model)

### Risk 4: Report file overwrite (user loses previous evaluation)
**Likelihood:** MEDIUM — user re-runs evaluation
**Impact:** MEDIUM — loss of historical data
**Mitigation:** Timestamped filenames when file exists (already specified in CONTEXT.md)

### Risk 5: M3/M4 MAP@100 < 0.05 (model not useful)
**Likelihood:** LOW — Phase 7 HP search used AUC as scorer, but models should still rank reasonably
**Impact:** HIGH — model is not operationally useful despite good AUC
**Mitigation:** Report MAP@100 prominently; add interpretation note in markdown report

---

## Dependencies Already Installed

All required libraries are already in the environment from Phases 1-7:

```
scikit-learn==1.8.0
pandas==2.2.3
pyarrow==23.0.1
numpy==1.26.4
xgboost==3.2.0
joblib==1.5.3
```

**No new dependencies required.**

Optional for console table formatting:
- `tabulate` (not installed yet — add to pyproject.toml if needed)
- OR use `rich` (heavier but prettier)
- OR implement manual table formatting with f-strings (lightweight)

**Recommendation:** Add `tabulate>=0.9.0` to pyproject.toml for clean cross-model summary tables. Fallback to manual formatting if not installed.

---

## Research Conclusion

Phase 8 is a pure evaluation phase with clear metric definitions, well-established sklearn APIs, and straightforward report generation. The critical insight from PITFALLS.md is that MAP@k must be computed for M3/M4 to validate operational usefulness — AUC-ROC alone is insufficient for highly imbalanced models.

**Implementation complexity: LOW** — no model training, no hyperparameter search, no data transformations. All inputs already exist from Phase 7.

**Testing complexity: MEDIUM** — MAP@k requires manual implementation and careful unit testing. Threshold analysis requires confusion matrix verification at 19 thresholds.

**Risk level: LOW** — No leakage concerns (pure read-only evaluation), no data pipeline dependencies. Worst case: report formatting bugs or MAP@k off-by-one errors, both easily caught in testing.

**Primary recommendation:** Implement `src/sip_engine/evaluation/evaluator.py` with modular helper functions for each metric category, write comprehensive unit tests for MAP@k and threshold analysis, and expose via CLI `evaluate` subcommand with `--model` and `--models-dir` flags per CONTEXT.md specification.

---

*Research complete. Ready for planning.*
