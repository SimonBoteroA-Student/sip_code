# Phase 9: Explainability, CRI, and Testing — Research

**Researched:** 2026-03-02
**Phase:** 09-explainability-cri-and-testing
**Goal:** SHAP values per prediction, CRI aggregation, deterministic JSON output, unit test gaps filled

---

## 1. What Exists (Carry-Forward from Phase 8)

### Codebase Structure
```
src/sip_engine/
├── config/
│   ├── settings.py           — Settings dataclass, get_settings() singleton
│   └── model_weights.json    — Currently: {"m1_cost_overruns": 0.20, ..., "iric": 0.20}
├── data/                     — loaders, rcac_builder, rcac_lookup, label_builder, schemas
├── features/
│   ├── pipeline.py           — build_features() (batch) + compute_features() (online, 34 features)
│   ├── category_{a,b,c}.py   — feature extractors
│   ├── encoding.py           — categorical encoding
│   └── provider_history.py   — as-of-date provider index
├── iric/
│   ├── pipeline.py           — build_iric() (batch) + compute_iric() (online, 11 components + 4 scores)
│   ├── calculator.py         — compute_iric_components(), compute_iric_scores()
│   ├── thresholds.py         — calibrate/load/save IRIC thresholds
│   └── bid_stats.py          — kurtosis, DRN
├── models/
│   └── trainer.py            — train_model(), XGBoost, joblib serialization
└── evaluation/
    └── evaluator.py          — evaluate_model(), map_at_k(), report generation
```

### Model Artifacts (per-model directory `artifacts/models/{M1,M2,M3,M4}/`)
- `model.pkl` — XGBoost `XGBClassifier` loaded via `joblib.load()`
- `test_data.parquet` — held-out test set with `id_contrato` index
- `training_report.json` — hyperparams, strategy, metadata
- `feature_registry.json` — `{"feature_columns": [...34 features...]}` — ordering guarantee

### Key Inference Path Already Exists
`compute_features(contract_row, as_of_date, ...)` in `features/pipeline.py` returns a
34-key dict with exactly `FEATURE_COLUMNS` (in order). This is the online inference entry
point for Phase 9's `analyze_contract()` to call.

### SHAP Library Already Installed
`shap>=0.46` in `pyproject.toml`. No new dependency required.

### Test Suite State
326 tests passing across 8 test files. PROJ-04 gap analysis:
- **RCAC round-trip**: `test_rcac.py::test_lookup_normalizes_input` — ALREADY COVERED (raw dotted number → normalize → lookup → found). May need one more for `build_rcac` → lookup round-trip with all sources.
- **Provider history as-of-date**: `test_features.py::test_lookup_future_contracts_excluded` + `test_lookup_same_day_excluded` — ALREADY COVERED.
- **IRIC component flags (≥4)**: `test_iric.py` has 7+ individual component tests — ALREADY COVERED.
- **predict_proba in [0,1]**: `test_models.py::test_train_model_end_to_end_quick` asserts `(proba >= 0).all() and (proba <= 1).all()` — ALREADY COVERED.

**Conclusion:** PROJ-04 gaps are minimal. The existing tests likely already satisfy all 4 criteria. Phase 9 needs to audit this explicitly and add targeted tests only for uncovered cases (e.g., `build_rcac` round-trip with raw inputs that include dots/dashes/letters, and verify that `build_rcac` → serialize → load → lookup works end-to-end).

---

## 2. New Code Required

### 2.1 New Module: `src/sip_engine/explainability/`

Three files + `__init__.py`:

**`shap_explainer.py`** — EXPL-01, EXPL-02
- `extract_shap_top_n(model, X_df, feature_names, n=10) -> list[dict]`
  - Uses `shap.TreeExplainer(model).shap_values(X_df)`
  - XGBoost binary classifier: `shap_values` shape is `(n_samples, n_features)` — single array (not list of two)
  - Per row: sort features by `|shap_value|` descending, take top-N
  - Each entry: `{"feature": str, "shap_value": float, "direction": "risk_increasing"|"risk_reducing", "original_value": Any}`
  - direction: "risk_increasing" if shap_value > 0, else "risk_reducing"
- `save_shap_artifact(shap_rows, model_id, output_dir) -> Path`
  - Writes `artifacts/shap/shap_{model_id}.parquet`
  - Columns: `id_contrato`, `feature`, `shap_value`, `direction`, `original_value`

**`cri.py`** — EXPL-03, EXPL-04, EXPL-05
- `load_cri_config() -> dict`
  - Reads `model_weights.json` (weights + thresholds)
- `compute_cri(p_m1, p_m2, p_m3, p_m4, iric_score, weights) -> float`
  - CRI = w_m1*P(M1) + w_m2*P(M2) + w_m3*P(M3) + w_m4*P(M4) + w_iric*IRIC
  - Returns float in [0, 1]
- `classify_risk_level(cri_score, thresholds) -> str`
  - 5 levels: Very Low [0,0.2), Low [0.2,0.4), Medium [0.4,0.6), High [0.6,0.8), Very High [0.8,1.0]
  - Boundary: inclusive lower, exclusive upper; Very High includes 1.0 exactly
  - Thresholds loaded from `model_weights.json` (configurable, not hardcoded)

**`analyzer.py`** — PROJ-03, all EXPL-*
- `analyze_contract(contract_row, ...) -> dict`
  - **THE** single-entry-point function for future v2 API (`POST /api/v1/analyze`)
  - Loads all 4 models + feature registries from `artifacts/models/`
  - Calls `compute_features(contract_row, ...)` for the 34-feature vector
  - Calls `model.predict_proba(X)[:, 1]` for each model → P(M1-M4)
  - Calls `extract_shap_top_n()` for each model
  - Gets IRIC score from feature vector (`iric_score` key)
  - Computes CRI via `compute_cri()` and `classify_risk_level()`
  - Returns structured dict (schema below)
  - Determinism: all floats rounded to 6 decimal places throughout
- `serialize_to_json(result_dict) -> str`
  - `json.dumps(result_dict, sort_keys=True, ensure_ascii=False)`
  - This is the determinism guarantee for IPFS hashing

### 2.2 JSON Report Schema (PROJ-03)
```json
{
  "contract_id": "CON-001",
  "metadata": {
    "timestamp": "2026-03-02T10:00:00Z",
    "model_versions": {"M1": "...", "M2": "...", "M3": "...", "M4": "..."}
  },
  "cri": {
    "score": 0.423000,
    "level": "Medium",
    "weights_used": {"m1_cost_overruns": 0.2, "m2_delays": 0.2, "m3_comptroller": 0.2, "m4_fines": 0.2, "iric": 0.2}
  },
  "models": {
    "M1": {
      "probability": 0.312000,
      "shap_top10": [
        {"feature": "num_contratos_previos_nacional", "shap_value": 0.120000, "direction": "risk_increasing", "original_value": 47}
      ]
    }
  },
  "iric_score": 0.636000,
  "raw_features": {"valor_contrato": 1200000, ...},
  "metadata": {"timestamp": "...", "model_versions": {...}}
}
```

### 2.3 Settings Update (`config/settings.py`)
Add `artifacts_shap_dir` and `artifacts_shap_path` (or per-model shap paths):
```python
self.artifacts_shap_dir = self.artifacts_dir / "shap"
```
This follows the existing artifact subdirectory pattern.

### 2.4 `model_weights.json` Update (EXPL-04, EXPL-05)
Add `risk_thresholds` key to centralize CRI configuration (context decision):
```json
{
  "m1_cost_overruns": 0.20,
  "m2_delays": 0.20,
  "m3_comptroller": 0.20,
  "m4_fines": 0.20,
  "iric": 0.20,
  "risk_thresholds": {
    "very_low":  [0.00, 0.20],
    "low":       [0.20, 0.40],
    "medium":    [0.40, 0.60],
    "high":      [0.60, 0.80],
    "very_high": [0.80, 1.00]
  }
}
```

---

## 3. SHAP API Details

### TreeExplainer for XGBoost Binary Classifiers
```python
import shap

explainer = shap.TreeExplainer(xgb_model)
shap_values = explainer.shap_values(X_df)  # shape: (n_samples, n_features)
# For binary classification, shap.TreeExplainer returns a single 2D array
# (NOT a list of two arrays like in older SHAP versions with some estimators)
# Positive = pushes toward positive class (risk_increasing)
# Negative = pushes toward negative class (risk_reducing)
```

### Top-N Extraction
```python
import numpy as np

def extract_top_n(shap_row, feature_names, original_values, n=10):
    indices = np.argsort(np.abs(shap_row))[::-1][:n]
    return [
        {
            "feature": feature_names[i],
            "shap_value": round(float(shap_row[i]), 6),
            "direction": "risk_increasing" if shap_row[i] > 0 else "risk_reducing",
            "original_value": original_values[i],
        }
        for i in indices
    ]
```

### Batch Parquet Artifact
- Location: `artifacts/shap/shap_{model_id}.parquet`
- Per-contract rows, columns: `id_contrato` (index), `rank` (1-10), `feature`, `shap_value`, `direction`, `original_value`
- One file per model (4 total: shap_M1.parquet, shap_M2.parquet, shap_M3.parquet, shap_M4.parquet)
- Written by `save_shap_artifact()` in `shap_explainer.py`

---

## 4. Determinism Strategy (PROJ-03)

The context decision: "sorted dict keys + consistent float rounding to 6 decimal places — sufficient for IPFS hashing"

Implementation:
1. All `predict_proba()` outputs: `round(float(val), 6)`
2. All SHAP values: `round(float(val), 6)`
3. All CRI scores: `round(float(val), 6)`
4. `serialize_to_json()` uses `json.dumps(..., sort_keys=True)`
5. Timestamp must be excluded OR frozen from outside to achieve byte-identical output — **timestamp should be passed as a parameter** to `analyze_contract()` (or excluded from the determinism contract but documented)

**Important**: `json.dumps` with `sort_keys=True` on a pre-rounded dict will produce byte-identical output on repeated calls with identical inputs. Python's `json` module is deterministic for the same input data.

---

## 5. Test Plan

### New: `tests/test_explainability.py`
Unit tests for Phase 9 code (all new modules):

1. `test_extract_shap_top_n_returns_10` — returns exactly 10 entries per prediction
2. `test_extract_shap_top_n_sorted_by_abs_value` — entries in descending |SHAP| order
3. `test_shap_direction_positive` — positive SHAP → "risk_increasing"
4. `test_shap_direction_negative` — negative SHAP → "risk_reducing"
5. `test_shap_entry_schema` — each entry has feature/shap_value/direction/original_value
6. `test_compute_cri_equal_weights` — 5 inputs = 0.5 → CRI = 0.5
7. `test_compute_cri_weights_sum_flexibility` — weights from json correctly applied
8. `test_classify_risk_level_boundaries` — 0.00, 0.199, 0.20, 0.399, 0.40, ... 1.00
9. `test_classify_very_high_includes_1` — 1.0 → "Very High"
10. `test_cri_config_modifiable` — change weights in json → CRI output changes
11. `test_analyze_contract_returns_required_keys` — contract_id, cri, models, iric_score, raw_features, metadata
12. `test_analyze_contract_shap_top10_per_model` — 4 models × top-10 in output
13. `test_json_determinism` — same input → `serialize_to_json()` twice → byte-identical
14. `test_json_sort_keys` — output has sorted keys

### New: `tests/test_system.py` (master system test)
Dual-mode: fixture-based (CI) or real-data (`--real-data` flag via `pytest` marker/conftest).

Fixture mode covers:
- data → build_rcac → build_labels → build_features → build_iric → train_model (M1 only) → analyze_contract
- Asserts: output has expected schema, CRI in [0,1], risk level valid string, SHAP top-10 non-empty
- Uses synthetic fixtures (reuse existing conftest fixtures where possible)
- Fast — uses tiny synthetic data, not real files

Real-data mode (skip by default in CI, triggered by `--real-data`):
- Runs against actual `data/` files
- Asserts same schema guarantees

### Existing Test Gaps (PROJ-04)
After auditing the 326 tests:
- **RCAC round-trip**: `test_lookup_normalizes_input` in test_rcac.py covers normalize→lookup. Add `test_build_rcac_roundtrip` to verify full pipeline: raw CSV → build_rcac → serialize → load → lookup → correct entry returned. (Likely 1-2 new tests)
- **Provider as-of-date**: Already covered in test_features.py.
- **IRIC components**: Already covered in test_iric.py (7+ component tests).
- **predict_proba [0,1]**: Already covered in test_models.py::test_train_model_end_to_end_quick.

Plan: add explicit PROJ-04 coverage tests **only where truly missing** after confirming with `--collect-only`. The existing suite likely satisfies 3 of 4 criteria already.

---

## 6. Architecture Decisions for Planner

### Module Placement
`src/sip_engine/explainability/` is the natural home. Mirrors the `evaluation/` module pattern.

### Function vs Class
Use standalone functions (not a class). Consistent with all other modules in this codebase (`compute_features()`, `compute_iric()`, `evaluate_model()` are all module-level functions).

### analyze_contract() Signature
```python
def analyze_contract(
    contract_row: dict,
    as_of_date: datetime.date,
    procesos_data: dict | None = None,
    proveedor_fecha_creacion: datetime.date | None = None,
    num_actividades: int = 0,
    iric_thresholds: dict | None = None,
    bid_values: list[float] | None = None,
    models_dir: Path | None = None,
    timestamp: str | None = None,  # ISO8601; None = use current UTC time
) -> dict
```
- Mirrors `compute_features()` signature for consistency (same optional inputs)
- `models_dir` defaults to `get_settings().artifacts_models_dir`
- Returns a plain dict; caller calls `serialize_to_json()` to get JSON string

### Loading Models Inside analyze_contract()
Load all 4 models per call (no caching). This is consistent with the evaluation module pattern. Caching can be added later when the v2 REST API requires it (startup loading). For v1, this function is called occasionally, not at high frequency.

### SHAP Artifact vs Inline SHAP
The context decision specifies SHAP is **both** stored in batch Parquet AND returned inline in the per-contract analysis dict. The batch Parquet (`save_shap_artifact()`) is a separate function called during a batch analysis run; `analyze_contract()` computes SHAP inline and returns top-10 in the dict.

---

## 7. Suggested Plan Breakdown

**Plan 09-01: SHAP + CRI modules**
- Create `src/sip_engine/explainability/__init__.py`
- Create `src/sip_engine/explainability/shap_explainer.py` (EXPL-01, EXPL-02)
- Create `src/sip_engine/explainability/cri.py` (EXPL-03, EXPL-04, EXPL-05)
- Update `model_weights.json` with `risk_thresholds`
- Add `artifacts_shap_dir` to `Settings.__post_init__()`
- Tests: `tests/test_explainability.py` (SHAP + CRI unit tests, ~14 tests)

**Plan 09-02: Analyzer + Determinism + System Test**
- Create `src/sip_engine/explainability/analyzer.py` (PROJ-03) — `analyze_contract()` + `serialize_to_json()`
- Create `tests/test_system.py` — master dual-mode system test
- Add any missing PROJ-04 gap tests to existing test files (after audit)
- Verify determinism: same input → byte-identical JSON on repeated runs

---

## 8. Technical Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| SHAP output shape varies by XGBoost/SHAP version | Check `shap>=0.46` behavior: XGBoost binary → single 2D array. Add assertion on shape in tests. |
| Float non-determinism in SHAP values | SHAP TreeExplainer is deterministic given same model + same input. Round to 6dp for output. |
| models not trained yet (artifacts/models/ empty) | Test using `pytest-mock` or joblib-serialized toy XGBClassifier built in fixture — same pattern as test_models.py and test_evaluation.py already use |
| model_weights.json change breaks existing code | Only adds new key `risk_thresholds` — backward compatible; existing code reads only the 5 weight keys |
| analyze_contract() too slow for system test | Use toy model fixture (tiny training data) + synthetic contract row — mirrors test_train_model_end_to_end_quick pattern |

---

*Research complete: 2026-03-02*
*Output: .planning/phases/09-explainability-cri-and-testing/09-RESEARCH.md*
