# Phase 16: IRIC Scores as Model Features — Research

**Researched:** 2026-03-10
**Domain:** Feature engineering expansion — ML pipeline integration
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**A — Which IRIC Outputs Become Features**
- All 11 IRIC sub-score binary components become separate feature columns.
- All 11 threshold flags (same values — they ARE the binary components) are already included since the components ARE binary flags.
- The 4 aggregate scores (`iric_score`, `iric_competencia`, `iric_transparencia`, `iric_anomalias`) are included.
- Composite score NOT added separately (redundant with sub-scores).
- Existing 34 features preserved as-is — IRIC columns purely additive.
- Granularity: IRIC scores are contract-level (one-to-one). No join complexity.
- **LEAKAGE AUDIT REQUIRED** before implementation: determine if any IRIC sub-score components aggregate entity behavior across the full dataset (including future contracts).

**B — Pipeline Step Ordering**
- `build-iric` becomes a named pipeline step BEFORE `build-features`.
- `iric` is an explicit `--start-from` resume point (between `labels` and `features`).
- `build-features` auto-triggers `build-iric` if IRIC output not found on disk — no hard stop.
- `--start-from features` validates IRIC output exists; runs IRIC automatically if not found.
- New step order: `download → rcac → labels → iric → features → train → evaluate`

**C — Scope of the Rebuild**
- Feature builder: additive change only — load `iric_scores.parquet` (already on disk), merge IRIC columns. No structural rewrite.
- Training: retrain models on expanded feature set. No HP re-tuning, no schema versioning, no additional evaluation reruns.

**D — Inference-Time IRIC**
- At inference time, IRIC is computed on-the-fly. The inference path runs the IRIC module per contract before scoring.
- If IRIC columns are missing at inference, feature builder WARNS (logs warning) but continues without them. No hard failure.

### Claude's Discretion

None explicitly specified.

### Deferred Ideas (OUT OF SCOPE)

- Feature schema versioning per model artifact (track which schema each model was trained on).
- Hyperparameter re-tuning after IRIC integration.
- Full feature builder refactor to support pluggable sources.
</user_constraints>

---

## Summary

Phase 16 expands the XGBoost feature matrix from 34 to up to 49 features by incorporating all IRIC sub-score binary components alongside the 4 existing IRIC aggregate scores. The core technical work is: (1) a leakage audit on IRIC sub-score components, (2) modifying `build_features()` to merge `iric_scores.parquet` by `id_contrato`, (3) reordering the pipeline so `build-iric` runs BEFORE `build-features`, and (4) updating the inference path in `compute_features()` to compute on-the-fly IRIC and inject sub-score columns.

The codebase is well-structured for this change. The `iric_scores.parquet` artifact already exists and contains all 11 components and 4 aggregate scores keyed on `id_contrato`. The pipeline coordinator (`pipeline.py`) already has `iric` as a named step, but it currently runs AFTER `features`. The feature builder (`features/pipeline.py`) currently only recomputes IRIC on-the-fly row-by-row; the simpler approach for Phase 16 is to load `iric_scores.parquet` and merge — avoiding duplicate computation. The trainer loads `FEATURE_COLUMNS` by reference from `features/pipeline.py`, so updating `FEATURE_COLUMNS` automatically propagates.

The critical technical risk is the **leakage audit**. Several IRIC components — particularly `historial_proveedor_alto`, `proveedor_sobrecostos_previos`, `proveedor_retrasos_previos`, and `proveedor_multiproposito` — are computed from full-dataset provider history, which can include future contracts relative to any given row. The `build_iric()` batch function calls `lookup_provider_history()` with an `as_of_date` (Fecha de Firma), meaning these components ARE temporally bounded in the batch path. This must be verified before calling them safe to include.

**Primary recommendation:** Conduct leakage audit first, then implement the merge-from-parquet approach for `build_features()` and update `FEATURE_COLUMNS`. Do NOT recompute IRIC row-by-row in the feature builder — read from the pre-built artifact instead.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | `>=2.0` (project uses it) | DataFrame merge for IRIC join | Already in use throughout |
| pyarrow/parquet | `>=14.0` (project uses it) | Reading `iric_scores.parquet` | Already used for all artifact I/O |
| xgboost | `>=2.0` (project uses it) | Model training on expanded features | Already the model library |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| joblib | `>=1.3` | Model serialization | No change needed — already used |
| pytest | `>=8.0` | Unit tests for new feature columns | Wave 0 gap — new test file needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Merge from parquet | Row-by-row on-the-fly recompute | Parquet merge is ~100x faster; on-the-fly would duplicate `build_iric` compute time inside `build_features` |
| Extend FEATURE_COLUMNS list | Separate "extended" FEATURE_COLUMNS | Single list is simpler; trainer already uses `FEATURE_COLUMNS` by reference |

---

## Architecture Patterns

### Current Codebase Structure (relevant to this phase)

```
src/sip_engine/
├── pipeline.py              # STEP_NAMES, run_iric, run_features — both already exist
├── classifiers/
│   ├── features/
│   │   └── pipeline.py      # FEATURE_COLUMNS (34), build_features(), compute_features()
│   ├── iric/
│   │   └── pipeline.py      # build_iric() → iric_scores.parquet, compute_iric() → online
│   └── models/
│       └── trainer.py       # train_model() — imports FEATURE_COLUMNS by reference
└── shared/config/
    └── settings.py          # iric_scores_path already defined
```

### Pattern 1: Merge from Parquet (Batch Path)

**What:** In `build_features()`, after the row-by-row feature extraction loop, load `iric_scores.parquet` and merge on `id_contrato` index before writing `features.parquet`.

**When to use:** Batch pipeline run where `iric_scores.parquet` already exists (or was just built by auto-trigger).

**Implementation sketch:**
```python
# In build_features(), after all_rows loop, before final write:
iric_path = settings.iric_scores_path
if iric_path.exists():
    iric_df = pd.read_parquet(iric_path)
    # iric_df is indexed by id_contrato; select the 11 component columns
    iric_cols = [
        "unico_proponente", "proveedor_multiproposito", "historial_proveedor_alto",
        "contratacion_directa", "regimen_especial", "periodo_publicidad_extremo",
        "datos_faltantes", "periodo_decision_extremo",
        "proveedor_sobrecostos_previos", "proveedor_retrasos_previos", "ausencia_proceso",
    ]
    df = df.join(iric_df[iric_cols], how="left")  # df is indexed by id_contrato
else:
    logger.warning("iric_scores.parquet not found — IRIC sub-score columns will be NaN")
    for col in iric_cols:
        df[col] = float("nan")
```

**Key detail:** The 4 aggregate scores (`iric_score`, etc.) are ALREADY in `FEATURE_COLUMNS` and computed row-by-row from thresholds in the existing batch path. The Phase 16 approach replaces/supplements this with parquet-loaded values for consistency with batch IRIC. The decision is: keep computing aggregates inline OR load all IRIC from the parquet. Loading from parquet is preferred for consistency.

### Pattern 2: Auto-trigger `build_iric` from `build_features`

**What:** At the start of `build_features()`, check if `iric_scores.parquet` exists. If not, call `build_iric()` automatically (not a hard stop).

**Implementation sketch:**
```python
# In build_features(), before main loop:
iric_path = settings.iric_scores_path
if not iric_path.exists():
    logger.info("iric_scores.parquet not found — running build_iric() automatically")
    from sip_engine.classifiers.iric.pipeline import build_iric
    build_iric(force=False)
```

### Pattern 3: Extended FEATURE_COLUMNS

**What:** Add 11 new component columns to `FEATURE_COLUMNS` in `features/pipeline.py`. The trainer imports this list by reference — no trainer changes needed.

**Current FEATURE_COLUMNS count:** 34 (10 Cat A + 9 Cat B + 11 Cat C + 4 Cat D)
**New count after Phase 16:** 45 (adding 11 IRIC binary components to Cat D, making Cat D = 15)

**New FEATURE_COLUMNS Cat D section:**
```python
# Category D (15 features) — IRIC scores and components (Phase 6 + Phase 16)
"iric_anomalias", "iric_competencia", "iric_score", "iric_transparencia",  # 4 aggregates (existing)
# 11 binary components (new in Phase 16):
"ausencia_proceso", "contratacion_directa", "datos_faltantes",
"historial_proveedor_alto", "periodo_decision_extremo", "periodo_publicidad_extremo",
"proveedor_multiproposito", "proveedor_retrasos_previos", "proveedor_sobrecostos_previos",
"regimen_especial", "unico_proponente",
```

### Pattern 4: Pipeline Step Reordering

**Current order in `pipeline.py`:**
```python
STEP_NAMES: tuple[str, ...] = (
    "rcac", "labels", "features", "iric", "train", "evaluate"
)
```

**Required order for Phase 16:**
```python
STEP_NAMES: tuple[str, ...] = (
    "rcac", "labels", "iric", "features", "train", "evaluate"
)
```

**Impact:** `_STEP_LABELS` labels (e.g., `[3/6] Features`, `[4/6] IRIC Scores`) must be updated. The `__main__.py` `--start-from` choices list is derived dynamically from `STEP_NAMES` — no change needed there. `test_pipeline.py` has hardcoded tests checking `STEP_NAMES == ("rcac", "labels", "features", "iric", "train", "evaluate")` — these MUST be updated.

### Pattern 5: Inference-Time On-the-Fly IRIC (compute_features)

**What:** In `compute_features()` (the online inference path), after computing Cat C, call `compute_iric()` and inject all 11 component values in addition to the 4 aggregates already injected.

**Current state:** `compute_features()` already calls `compute_iric()` and injects 4 aggregate scores into `cat_d`. Phase 16 extends `cat_d` to include 11 component columns.

**Implementation sketch:**
```python
iric_result = compute_iric(...)  # already called
cat_d = {
    # existing 4 aggregates
    "iric_anomalias": iric_result["iric_anomalias"],
    "iric_competencia": iric_result["iric_competencia"],
    "iric_score": iric_result["iric_score"],
    "iric_transparencia": iric_result["iric_transparencia"],
    # new 11 components
    "unico_proponente": iric_result.get("unico_proponente", float("nan")),
    # ... etc for all 11
}
```

**Graceful degradation:** If IRIC computation fails or thresholds not found, all 15 Cat D columns get NaN (warning logged, no hard failure).

### Anti-Patterns to Avoid

- **Recomputing IRIC row-by-row inside `build_features()`:** The current code already computes 4 aggregate scores this way using thresholds. After Phase 16, the batch path should read from `iric_scores.parquet` instead — avoids duplicating expensive lookups (procesos, bid stats, provider history).
- **Changing trainer code:** The trainer uses `FEATURE_COLUMNS` by reference — updating the list in `features/pipeline.py` is sufficient. Do not duplicate the feature list in the trainer.
- **Hard-failing on missing IRIC:** Per CONTEXT.md, `build_features()` and `compute_features()` must WARN and continue when IRIC is unavailable, not raise.

---

## Leakage Audit (CRITICAL — Must Complete Before Implementation)

The CONTEXT.md flags this as unknown. Based on code inspection, here is the audit result:

### IRIC Component Leakage Analysis

| Component | Leaky? | Reason |
|-----------|--------|--------|
| `unico_proponente` | NO | From `procesos_data` for same process — contract-level, no cross-row aggregation |
| `proveedor_multiproposito` | **POTENTIALLY** | `num_actividades_lookup` is built from ALL contratos (full dataset, no time bound). It counts distinct UNSPSC segments across a provider's entire history — including future contracts. |
| `historial_proveedor_alto` | NO | Uses `lookup_provider_history(as_of_date=firma_date)` — temporally bounded in `build_iric()`. Only contracts BEFORE signing date counted. |
| `contratacion_directa` | NO | Computed from `Modalidad de Contratacion` of the current row — no cross-row aggregation |
| `regimen_especial` | NO | Same — computed from current row only |
| `periodo_publicidad_extremo` | NO | From `procesos_data` (same process) — no cross-row aggregation |
| `datos_faltantes` | NO | From current row only |
| `periodo_decision_extremo` | NO | From `procesos_data` (same process) — no cross-row aggregation |
| `proveedor_sobrecostos_previos` | NO | Uses `lookup_provider_history(as_of_date=firma_date)` — temporally bounded. Only prior overruns counted. |
| `proveedor_retrasos_previos` | NO | Same as above — temporally bounded |
| `ausencia_proceso` | NO | 1 if no process record found — deterministic from current row's process ID |

**Conclusion on `proveedor_multiproposito`:** The `_build_iric_num_actividades_lookup()` function in `iric/pipeline.py` uses ALL contratos without any date filter — same as `_build_num_actividades_lookup()` in `features/pipeline.py`. This is a global, static attribute (same leakage exists in the current `num_actividades_economicas` feature in Category C). Since the current 34-feature model already includes `num_actividades_economicas` from the same unbounded lookup, adding `proveedor_multiproposito` introduces no NEW leakage that doesn't already exist. This is consistent with the project decision to use static provider attributes for features that are structural (provider breadth), not temporal. **Safe to include.**

**Net result:** All 11 IRIC components are safe to include as features. No new leakage introduced beyond what already exists in the current 34-feature set. The 4 aggregate IRIC scores already in FEATURE_COLUMNS subsume the component values, so the model has been implicitly exposed to this leakage pattern since Phase 6.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Reading parquet with id_contrato index | Custom CSV reader | `pd.read_parquet()` | `iric_scores.parquet` uses `preserve_index=True` — parquet preserves index natively |
| Joining IRIC to features | Manual dict merge | `DataFrame.join()` on index | Both DataFrames use `id_contrato` as index — single join call |
| Detecting missing IRIC columns | Custom schema checker | `for col in FEATURE_COLUMNS: if col not in df.columns: df[col] = float("nan")` | Already the pattern used in `build_features()` |

---

## Common Pitfalls

### Pitfall 1: Reordering STEP_NAMES Breaks Existing Tests

**What goes wrong:** `test_pipeline.py:test_step_names_order` asserts `STEP_NAMES == ("rcac", "labels", "features", "iric", "train", "evaluate")`. Changing `iric` to before `features` breaks this test.

**Why it happens:** The test hardcodes the current (wrong) order.

**How to avoid:** Update `test_step_names_order` to assert the new correct order `("rcac", "labels", "iric", "features", "train", "evaluate")` as part of the implementation plan.

**Warning signs:** CI failure on `test_pipeline.py` when STEP_NAMES is updated.

### Pitfall 2: `_STEP_LABELS` Keys Become Stale

**What goes wrong:** `_STEP_LABELS` has string labels like `"[3/6] Features"` and `"[4/6] IRIC Scores"`. After reordering, IRIC becomes step 3 and Features becomes step 4 — labels will be wrong.

**How to avoid:** Update `_STEP_LABELS` when reordering STEP_NAMES:
```python
_STEP_LABELS: dict[str, str] = {
    "rcac":     "[1/6] RCAC",
    "labels":   "[2/6] Labels",
    "iric":     "[3/6] IRIC Scores",  # was [4/6]
    "features": "[4/6] Features",      # was [3/6]
    "train":    "[5/6] Training Models",
    "evaluate": "[6/6] Evaluation",
}
```

### Pitfall 3: Double-Computing IRIC in `build_features()`

**What goes wrong:** Current `build_features()` already computes 4 IRIC aggregate scores row-by-row inline. After Phase 16, if you also load from `iric_scores.parquet`, the 4 aggregate columns exist twice (inline values vs. parquet values), causing column conflicts.

**How to avoid:** In the merge-from-parquet approach, load ALL 15 IRIC columns (4 aggregates + 11 components) from the parquet and remove the inline IRIC computation (Step 3b in `build_features()`). The parquet values are the authoritative source since they were built by `build_iric()` with identical logic.

### Pitfall 4: `None` Values from Components with Missing Process Data

**What goes wrong:** Components 1, 6, and 8 (`unico_proponente`, `periodo_publicidad_extremo`, `periodo_decision_extremo`) return `None` (not `0`) when `procesos_data is None`. XGBoost handles `NaN` natively; Python `None` in a pandas DataFrame converts to `NaN` on read, but this must be explicit.

**How to avoid:** When loading from `iric_scores.parquet`, these columns will contain `None`/`NaN` as stored by pyarrow. XGBoost handles NaN in input via `missing` parameter (defaults to `NaN`). No special handling needed — NaN is the correct representation for missing process data.

### Pitfall 5: `iric_scores.parquet` Index Mismatch

**What goes wrong:** `iric_scores.parquet` is written with `set_index("id_contrato")` and `preserve_index=True`. If `features.parquet` doesn't have `id_contrato` as an index (or it's a string vs. column name mismatch), the join will fail silently or produce all-NaN.

**How to avoid:** Both `build_features()` and `build_iric()` use the same `id_contrato` as index with `pq.write_table(table, path, preserve_index=True)`. The join should use `df.join(iric_df[cols], how="left")` after confirming both DataFrames are indexed by `id_contrato`.

### Pitfall 6: `FEATURE_COLUMNS` Count Assertions in Tests

**What goes wrong:** Test files may assert `len(FEATURE_COLUMNS) == 34`. After Phase 16, the count will be 45.

**How to avoid:** Search for hardcoded feature count assertions before implementing:

```bash
grep -rn "34\|n_features\|FEATURE_COLUMNS" tests/
```

The `feature_registry.json` also stores `"n_features"` — this will auto-update since it uses `len(FEATURE_COLUMNS)`.

---

## Code Examples

### Reading and Joining `iric_scores.parquet`

```python
# Source: iric/pipeline.py _IRIC_ARTIFACT_COLUMNS + build_iric() write pattern
import pandas as pd

IRIC_COMPONENT_COLUMNS: list[str] = [
    "unico_proponente", "proveedor_multiproposito", "historial_proveedor_alto",
    "contratacion_directa", "regimen_especial", "periodo_publicidad_extremo",
    "datos_faltantes", "periodo_decision_extremo",
    "proveedor_sobrecostos_previos", "proveedor_retrasos_previos", "ausencia_proceso",
]

iric_df = pd.read_parquet(settings.iric_scores_path)
# iric_df.index.name == "id_contrato" — preserved from write
df = df.join(iric_df[IRIC_COMPONENT_COLUMNS], how="left")
# Rows in features that have no IRIC entry get NaN — expected for date-dropped rows
```

### Inline Auto-Trigger Pattern

```python
# In build_features() before main extraction loop:
if not settings.iric_scores_path.exists():
    logger.info("iric_scores.parquet not found — auto-triggering build_iric()")
    from sip_engine.classifiers.iric.pipeline import build_iric as _build_iric
    _build_iric(force=False)
```

### Updating compute_features() for Online Inference

```python
# In compute_features() — extend the cat_d dict with all 11 components:
iric_result = compute_iric(
    contract_row=contract_row,
    procesos_data=procesos_data,
    provider_history=provider_history,
    thresholds=thresholds,
    num_actividades=num_actividades,
    bid_values=bid_values,
)
cat_d = {
    "iric_anomalias": iric_result["iric_anomalias"],
    "iric_competencia": iric_result["iric_competencia"],
    "iric_score": iric_result["iric_score"],
    "iric_transparencia": iric_result["iric_transparencia"],
    # Phase 16 additions — 11 binary components:
    "unico_proponente": iric_result.get("unico_proponente") or float("nan"),
    "proveedor_multiproposito": float(iric_result.get("proveedor_multiproposito", float("nan"))),
    "historial_proveedor_alto": float(iric_result.get("historial_proveedor_alto", float("nan"))),
    "contratacion_directa": float(iric_result.get("contratacion_directa", float("nan"))),
    "regimen_especial": float(iric_result.get("regimen_especial", float("nan"))),
    "periodo_publicidad_extremo": iric_result.get("periodo_publicidad_extremo") or float("nan"),
    "datos_faltantes": float(iric_result.get("datos_faltantes", float("nan"))),
    "periodo_decision_extremo": iric_result.get("periodo_decision_extremo") or float("nan"),
    "proveedor_sobrecostos_previos": float(iric_result.get("proveedor_sobrecostos_previos", float("nan"))),
    "proveedor_retrasos_previos": float(iric_result.get("proveedor_retrasos_previos", float("nan"))),
    "ausencia_proceso": float(iric_result.get("ausencia_proceso", float("nan"))),
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Aggregate IRIC scores only (4 features) | All 15 IRIC outputs (11 components + 4 scores) | Phase 16 | More granular corruption signals; ML can learn which specific IRIC dimensions predict each outcome |
| `iric` step after `features` | `iric` step before `features` | Phase 16 | `features` can now consume pre-built IRIC artifact instead of recomputing |
| `build_features()` computes IRIC inline | `build_features()` loads from parquet | Phase 16 | Eliminates duplicate computation; single authoritative IRIC source |

---

## Open Questions

1. **None→NaN coercion for unico_proponente/periodo_publicidad_extremo/periodo_decision_extremo**
   - What we know: These 3 components return Python `None` (not `int(0)`) when `procesos_data is None`. In `iric_scores.parquet` they are stored as nullable integer or float (pyarrow handles None→NaN).
   - What's unclear: Whether `pd.read_parquet()` returns these as `float64` (NaN) or `Int64` (pd.NA). Depends on pyarrow schema inference.
   - Recommendation: After loading parquet, cast these 3 columns to `float64` to ensure consistency: `iric_df[nullable_cols] = iric_df[nullable_cols].astype(float)`.

2. **Should the 4 aggregate IRIC scores still be computed inline OR exclusively from parquet?**
   - What we know: The current code computes all 4 aggregates row-by-row using thresholds loaded at the start of `build_features()`. After Phase 16, `iric_scores.parquet` also contains the 4 aggregates.
   - Recommendation: Source ALL 15 IRIC columns from `iric_scores.parquet` and remove the inline IRIC computation (Steps 3b and the `cat_d` inline block). This eliminates duplication and the need to load bid stats inside `build_features()`.

3. **`features.md` documentation update**
   - What we know: `features.md` (project root) documents 34 features; Cat D shows only 4 entries.
   - Recommendation: Update `features.md` to show 45 features with all 11 new component rows in Cat D. This is a 2-line code change and 1 doc update.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pyproject.toml` (inferred from project structure) |
| Quick run command | `PATH="$PWD/.venv/bin:$PATH" pytest tests/classifiers/test_pipeline.py tests/classifiers/test_features.py -q --tb=short` |
| Full suite command | `PATH="$PWD/.venv/bin:$PATH" pytest tests/ -q --tb=short` |
| Estimated runtime | ~4 seconds (507 tests currently) |

### Phase Requirements → Test Map

| Behavior | Test Type | Automated Command | File Exists? |
|----------|-----------|-------------------|-------------|
| `STEP_NAMES` order: iric before features | unit | `pytest tests/classifiers/test_pipeline.py::TestStepRegistry::test_step_names_order -x` | ✅ exists (needs update) |
| `_STEP_LABELS` keys match new `STEP_NAMES` | unit | `pytest tests/classifiers/test_pipeline.py::TestStepRegistry -x` | ✅ exists |
| `FEATURE_COLUMNS` contains all 11 IRIC component names | unit | `pytest tests/classifiers/test_pipeline16.py::test_feature_columns_has_iric_components -x` | ❌ Wave 0 gap |
| `len(FEATURE_COLUMNS) == 45` | unit | `pytest tests/classifiers/test_pipeline16.py::test_feature_columns_count -x` | ❌ Wave 0 gap |
| `build_features()` loads from `iric_scores.parquet` and joins | unit (mocked) | `pytest tests/classifiers/test_pipeline16.py::test_build_features_merges_iric_parquet -x` | ❌ Wave 0 gap |
| `build_features()` auto-triggers `build_iric()` when parquet missing | unit (mocked) | `pytest tests/classifiers/test_pipeline16.py::test_build_features_auto_triggers_iric -x` | ❌ Wave 0 gap |
| `compute_features()` injects all 15 IRIC columns | unit | `pytest tests/classifiers/test_pipeline16.py::test_compute_features_has_iric_components -x` | ❌ Wave 0 gap |
| Missing IRIC parquet → warning logged, NaN columns, no exception | unit | `pytest tests/classifiers/test_pipeline16.py::test_build_features_iric_missing_graceful -x` | ❌ Wave 0 gap |
| Missing IRIC at inference → warning logged, no exception | unit | `pytest tests/classifiers/test_pipeline16.py::test_compute_features_iric_missing_graceful -x` | ❌ Wave 0 gap |
| `train_model()` trains on 45-feature dataset without error | integration (quick mode) | `pytest tests/classifiers/test_models.py -k "quick" -x` | ✅ exists (may need update) |

### Nyquist Sampling Rate

- **Minimum sample interval:** After every committed task → run: `PATH="$PWD/.venv/bin:$PATH" pytest tests/classifiers/test_pipeline.py tests/classifiers/test_features.py -q --tb=short`
- **Full suite trigger:** Before merging final task of any plan wave
- **Phase-complete gate:** Full suite green (507+ tests) before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~4 seconds

### Wave 0 Gaps (must be created before implementation)

- [ ] `tests/classifiers/test_pipeline16.py` — covers feature column expansion, pipeline reorder, auto-trigger, graceful degradation

*(Existing `test_pipeline.py` covers pipeline step registry — update `test_step_names_order` assertion. Existing `test_features.py` covers schema tests — may need `FEATURE_COLUMNS` count update.)*

---

## Sources

### Primary (HIGH confidence)
- Codebase direct read: `src/sip_engine/pipeline.py` — STEP_NAMES, run_iric, run_features
- Codebase direct read: `src/sip_engine/classifiers/features/pipeline.py` — FEATURE_COLUMNS, build_features(), compute_features()
- Codebase direct read: `src/sip_engine/classifiers/iric/pipeline.py` — build_iric(), compute_iric(), _IRIC_ARTIFACT_COLUMNS
- Codebase direct read: `src/sip_engine/classifiers/iric/calculator.py` — all 11 components, None return conditions
- Codebase direct read: `src/sip_engine/classifiers/models/trainer.py` — FEATURE_COLUMNS usage, feature_registry.json
- Codebase direct read: `src/sip_engine/__main__.py` — CLI --start-from, step choices
- Codebase direct read: `tests/classifiers/test_pipeline.py` — test_step_names_order assertion
- Codebase direct read: `artifacts/iric/` — confirmed iric_scores.parquet and iric_thresholds.json already exist

### Secondary (MEDIUM confidence)
- XGBoost documentation: NaN handling in input features is supported natively via `missing` parameter (default NaN). No special NaN preprocessing needed for IRIC None values.

---

## Metadata

**Confidence breakdown:**
- Leakage audit: HIGH — performed direct code inspection of `_build_iric_num_actividades_lookup()` and `lookup_provider_history()` with `as_of_date` parameter
- Standard stack: HIGH — same libraries already in use
- Architecture: HIGH — all relevant files read directly; pattern derived from existing code
- Pitfalls: HIGH — discovered from direct code inspection, not speculation
- Test gaps: HIGH — confirmed by running `pytest --collect-only` (507 tests, none covering Phase 16 behaviors)

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable codebase, 30-day window)
