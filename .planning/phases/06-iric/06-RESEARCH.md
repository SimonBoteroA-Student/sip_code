# Phase 6: IRIC — Research

**Created:** 2026-03-01
**Researcher:** Phase Research Agent
**Phase:** 6 of 9 — IRIC (Indice de Riesgo Integrado de Corrupcion)
**Requirements:** IRIC-01, IRIC-02, IRIC-03, IRIC-04, IRIC-05, IRIC-06, IRIC-07, IRIC-08, FEAT-04

---

## 1. What This Phase Must Deliver

Phase 6 must produce:

1. **11 binary IRIC component flags** across 3 dimensions (competition, transparency, anomaly)
2. **Bid kurtosis** (`curtosis_licitacion`) from Imhof (2018), per-process from `ofertas_proceso_SECOP.csv`
3. **Normalized relative difference** (`diferencia_relativa_norm`) from Imhof (2018), per-process
4. **4 IRIC aggregate scores**: `iric_score`, `iric_competencia`, `iric_transparencia`, `iric_anomalias`
5. **`iric_thresholds.json`** — calibration machinery (function) and artifact file path
6. **`category_d.py`** — integrates IRIC scores as Category D features in `pipeline.py` (FEAT-04)
7. **CLI `build-iric` subcommand** — parallel to `build-features`
8. **Tests** for all components

The `iric_thresholds.json` artifact produced in Phase 6 uses the full dataset (calibration machinery only). The FINAL artifact using training-set-only data (IRIC-08) will be produced in Phase 7 after the train/test split is defined. Phase 6 builds and validates the machinery.

---

## 2. Component Definitions (from VigIA Reference Code)

The VigIA reference implementation is in `/Users/simonb/SIP Code/Data/Vigia/SECOP_II_IRIC_exploration.txt`. This is the authoritative reference for SIP Phase 6. The code extracts from that notebook are reproduced here with adaptations for SIP's column names and national scope.

### 2.1 Competition Dimension (6 components)

**Component 1 — `unico_proponente`** (IRIC-01)
```python
# VigIA source: proponente_unico = 1 if proveedores_unicos_con <= 1
# SIP mapping: procesos "Proveedores Unicos con Respuestas" column
unico_proponente = 1 if num_proponentes <= 1 else 0
# NaN if procesos_data is None (no process match)
```

**Component 2 — `proveedor_multiproposito`** (IRIC-01)
```python
# VigIA source: proveedor_multiproposito = 1 if segmentos_de_categoria_principal > 1
# SIP: num_actividades_economicas (already computed in Phase 5, Category C)
# Threshold: > 1 distinct UNSPSC segment across provider's full history
proveedor_multiproposito = 1 if num_actividades_economicas > 1 else 0
```
Note: VigIA uses the literal threshold `> 1` (strictly more than one segment). No percentile needed here — the rule is binary.

**Component 3 — `historial_proveedor_alto`** (IRIC-01)
```python
# VigIA source (Bogota calibration):
#   Cedula de Ciudadania: > 3 contracts (P95)
#   NIT and others: > 6 contracts (P95)
# SIP adaptation: Use percentile-based thresholds from iric_thresholds.json,
#   segmented by tipo_contrato (as per CONTEXT.md decision).
# The threshold is: num_contratos_previos_nacional > P95_threshold_for_tipo_contrato
# Fallback if no threshold available: use VigIA values (3 for CC, 6 for others)
historial_proveedor_alto = 1 if num_contratos_previos_nacional > threshold_p95 else 0
```
The P95 threshold comes from `iric_thresholds.json`, keyed by `tipo_contrato`. Per CONTEXT.md: this is a volume outlier, not about category dominance.

**Component 4 — `contratacion_directa`** (IRIC-01)
```python
# VigIA source:
# 'Contratación directa' OR 'Contratación Directa (con ofertas)'
contratacion_directa = 1 if modalidad in {
    "Contratación directa",
    "Contratación Directa (con ofertas)"
} else 0
```
Source column: `contratos "Modalidad de Contratacion"`.

**Component 5 — `regimen_especial`** (IRIC-01)
```python
# VigIA source:
# 'Contratación régimen especial' OR 'Contratación régimen especial (con ofertas)'
regimen_especial = 1 if modalidad in {
    "Contratación régimen especial",
    "Contratación régimen especial (con ofertas)"
} else 0
```

**Component 6 — `periodo_publicidad_extremo`** (IRIC-01)
```python
# VigIA source: duracion_extrema_proceso
# = 1 if "Dias Proceso Contratacion Abierto" == 0 OR > threshold
# "Dias Proceso Contratacion Abierto" = (Fecha de Ultima Publicación - Fecha de Publicacion del Proceso).days
# VigIA Bogota thresholds: PS = P99 = 14 days; non-PS = P99 = 31 days
# SIP: use iric_thresholds.json P99 by tipo_contrato
# Negative values are clipped to 0 (VigIA approach)
periodo_publicidad_extremo = 1 if (dias_publicidad == 0 or dias_publicidad > p99_threshold) else 0
```
Note: `dias_publicidad` is already computed in Category B as a feature. Can reuse it.

### 2.2 Transparency Dimension (2 components)

**Component 7 — `datos_faltantes`** (IRIC-02)
```python
# VigIA source: presencia_errores
# Combines 3 sub-checks:
#   1. Error in provider document ID:
#      - tipodocproveedor == 'No Definido'
#      - documento length < 6
#      - documento is all special characters or letters (no digits)
#   2. Absence of modalidad justification:
#      - justificacion is NaN or == 'no especificado' (case-insensitive)
#   3. Contract value outlier:
#      - value > P99 threshold for tipo_contrato (from iric_thresholds.json)
# SIP adaptation: modality-aware per CONTEXT.md
# Direct contracting legitimately has no justification for bid-related fields
# BUT still requires justificacion_modalidad (it should say WHY direct contracting)
# presencia_errores = 1 if ANY of the 3 sub-checks fires
datos_faltantes = 1 if (error_documento or error_justificacion or error_valor) else 0
```

Sub-check details:
- **error_documento**: `TipoDocProveedor == "No Definido"` OR `len(normalize_numero(Documento Proveedor)) < 6` OR doc is all non-digits
- **error_justificacion**: `Justificacion Modalidad de Contratacion` is NaN or `"no especificado"` (case-insensitive, stripped)
- **error_valor**: `Valor del Contrato > P99_threshold_by_tipo_contrato` (from `iric_thresholds.json`)

Per CONTEXT.md: this covers both publication incompleteness AND data quality issues.

**Component 8 — `periodo_decision_extremo`** (IRIC-02)
```python
# VigIA source: periodo_decision_extremo
# "Periodo de Decision" = (Fecha de Firma - Fecha de Ultima Publicacion).days
# = 1 if periodo == 0 OR periodo > threshold
# VigIA Bogota thresholds: PS = P95 = 43 days; non-PS = P95 = 55 days
# SIP: use iric_thresholds.json P95 by tipo_contrato
# Negative values clipped to 0 (VigIA approach)
periodo_decision_extremo = 1 if (dias_decision == 0 or dias_decision > p95_threshold) else 0
```
Note: `dias_decision` is already computed in Category B. Can reuse it.

### 2.3 Anomaly Dimension (3 components)

**Component 9 — `proveedor_sobrecostos_previos`** (IRIC-03)
```python
# VigIA source: adicion_valor_proveedor = 1 if provider had ANY prior cost overrun
# SIP: uses Provider History Index from Phase 5
# num_sobrecostos_previos is already in provider_history dict (Category C)
proveedor_sobrecostos_previos = 1 if num_sobrecostos_previos > 0 else 0
# = 0 for providers with no contract history before signing date (IRIC success criterion 6)
```

**Component 10 — `proveedor_retrasos_previos`** (IRIC-03)
```python
# VigIA source: adicion_tiempo_proveedor = 1 if provider had ANY prior delay
# SIP: uses Provider History Index from Phase 5
proveedor_retrasos_previos = 1 if num_retrasos_previos > 0 else 0
# = 0 for providers with no contract history before signing date
```

**Component 11 — `ausencia_proceso`** (IRIC-03)
```python
# VigIA source: ausencia_proceso_contratacion = 1 - tiene_variables_portafolio
# SIP: a contract has no linked procurement process if procesos_data is None
# (no match in the procesos_lookup by "ID del Portafolio" / "Proceso de Compra")
ausencia_proceso = 1 if procesos_data is None else 0
```
VigIA comment: "Aquí no se eliminan los nulos de proceso de contratación dado que la ausencia de estos datos indica una irregularidad contemplada en el IRIC." (missing process data IS the irregularity).

---

## 3. Aggregate Score Formula (IRIC-06)

```python
# VigIA source: iric = sum(vars_indice) / len(vars_indice)
# SIP formula (IRIC-06 from requirements):
iric_score = (1/11) * sum([
    unico_proponente, proveedor_multiproposito, historial_proveedor_alto,
    contratacion_directa, regimen_especial, periodo_publicidad_extremo,  # competition (6)
    datos_faltantes, periodo_decision_extremo,                            # transparency (2)
    proveedor_sobrecostos_previos, proveedor_retrasos_previos, ausencia_proceso  # anomaly (3)
])

iric_competencia    = (1/6) * sum(components[1:7])    # components 1-6
iric_transparencia  = (1/2) * sum(components[7:9])    # components 7-8
iric_anomalias      = (1/3) * sum(components[9:12])   # components 9-11
```

NaN handling: VigIA fills NaN provider history components with 0 ("en caso de NaN al ser proveedor nuevo lo suma como 0"). SIP must do the same — new providers with no history get 0 for components 9 and 10.

---

## 4. Bid Distribution Anomaly Measures (IRIC-04, IRIC-05)

These come from Imhof (2018) and are computed at the **process level** (not contract level), then joined to contracts via `Proceso de Compra` → `ID del Proceso de Compra` in `ofertas_proceso_SECOP.csv`.

### 4.1 Kurtosis (`curtosis_licitacion`) — IRIC-04

Standard excess kurtosis formula (Fisher definition):
```
K = [n(n+1) / ((n-1)(n-2)(n-3))] × Σ((xi - x̄)/s)^4 - 3(n-1)^2 / ((n-2)(n-3))
```
Where:
- `n` = number of bids in the process
- `xi` = bid amount i
- `x̄` = mean bid amount
- `s` = sample standard deviation of bids

**Minimum bid requirement:** `n >= 4` (IRIC-04 success criterion 2).
- Processes with `n < 4` → `curtosis_licitacion = NaN`
- Processes with 0 bids (direct contracting, no offers) → `NaN`

Implementation: `scipy.stats.kurtosis(bids, fisher=True, bias=False)` computes the unbiased excess kurtosis. Alternatively, pandas `Series.kurt()` uses Fisher's definition by default.

### 4.2 Normalized Relative Difference (`diferencia_relativa_norm`) — IRIC-05

DRN formula from Imhof (2018):
```
DRN = (b_min - b_second_min) / b_second_min   [if interpreted as relative diff from second]
```
OR more commonly:
```
DRN = (b_max - b_min) / mean(bids)   [normalized range]
```

The exact Imhof formula needs verification. Based on the FEATURES.md research doc: "normalized relative difference (DRN) for collusion detection." The VigIA code does not implement kurtosis or DRN (it precomputes IRIC at the contract/provider level). The Imhof (2018) paper defines:

- **DRN (Différence Relative Normalisée)**: `(b2 - b1) / b1` where `b1 = minimum bid`, `b2 = second lowest bid`. This measures how close the two lowest bids are — tight clustering suggests bid rigging.
- **Alternative interpretation**: `(b_max - b_min) / b_mean` — normalized range.

**Minimum bid requirement:** `n >= 3` (IRIC-05 success criterion 3).
- Processes with `n < 3` → `diferencia_relativa_norm = NaN`

The most defensible formula given the Imhof context (bid rigging detection by distribution shape):
```python
# DRN = (second_lowest - lowest) / lowest
# = relative gap between the two cheapest bids
sorted_bids = sorted(bids)  # ascending
drn = (sorted_bids[1] - sorted_bids[0]) / sorted_bids[0]
# if lowest bid == 0: NaN (division by zero guard)
```

**Note for planner:** The exact Imhof DRN formula is not in the local VigIA code. The planner should choose a defensible formula and document it. The `(second_lowest - lowest) / lowest` interpretation is most consistent with bid rigging detection literature (tight bids = suspicious). If the project has the Imhof paper PDF, it should be checked. In absence of confirmation, the formula above is the recommended implementation.

### 4.3 Data Source for Bid Anomalies

`ofertas_proceso_SECOP.csv` — already loaded via `load_ofertas()` in Phase 2.
- Schema: `OFERTAS_USECOLS` includes `"ID del Proceso de Compra"`, `"Valor de la Oferta"`, `"NIT del Proveedor"`
- `"Valor de la Oferta"` is already currency-cleaned (Float64) by the loader
- Join key: `contratos["Proceso de Compra"]` → `ofertas["ID del Proceso de Compra"]`

**Strategy:** Build an offline bid statistics lookup dict (same pattern as `_build_procesos_lookup()`):
```python
# bid_stats_lookup: {proceso_id: {"curtosis": float|NaN, "drn": float|NaN, "n_bids": int}}
# Built by streaming ofertas_proceso_SECOP.csv, grouping by proceso, computing stats
```
This dict is built once during `build_iric()` and is reused for all contracts in the batch. For online `compute_iric()`, the caller passes pre-fetched bid values.

---

## 5. Threshold Calibration (IRIC-07, IRIC-08)

### 5.1 Segmentation Variable

Per CONTEXT.md: segment by `tipo_contrato` (e.g., "Prestación de servicios", "Compraventa", "Obra", "Suministro"). Rare types (< 30 observations) → merged into "Otro".

### 5.2 Variables to Calibrate (Percentiles P1, P5, P95, P99)

| Variable | Used By | Source Column |
|---|---|---|
| `num_contratos_previos_nacional` | `historial_proveedor_alto` (P95) | provider_history |
| `dias_publicidad` | `periodo_publicidad_extremo` (P99) | Category B |
| `dias_decision` | `periodo_decision_extremo` (P95) | Category B |
| `valor_contrato` | `datos_faltantes` error_valor sub-check (P99) | Category A |

### 5.3 Threshold JSON Structure

```json
{
  "tipo_contrato": {
    "Prestación de servicios": {
      "num_contratos_previos_nacional": {"p1": 1, "p5": 1, "p95": 3, "p99": 7},
      "dias_publicidad": {"p1": 0, "p5": 0, "p95": 10, "p99": 14},
      "dias_decision": {"p1": 0, "p5": 0, "p95": 43, "p99": 125},
      "valor_contrato": {"p1": 0, "p5": 0, "p95": 120000000, "p99": 221053429}
    },
    "Otro": { ... }
  },
  "calibration_date": "...",
  "n_contracts": 123456,
  "min_group_size": 30
}
```

### 5.4 Phase 6 vs Phase 7 Split (IRIC-08)

- **Phase 6**: Build `calibrate_iric_thresholds(df, min_group_size=30) -> dict` function + write to `iric_thresholds.json` using the FULL dataset (for development and testing)
- **Phase 7**: After train/test split is defined, re-run calibration on training set only (call Phase 6 function with train_df). The `iric_thresholds.json` artifact is OVERWRITTEN with training-only thresholds before model training begins.

The Phase 7 concern: IRIC thresholds must NOT be computed from the test set. The machinery is in Phase 6; the enforcement is in Phase 7.

---

## 6. Integration with Feature Pipeline (FEAT-04)

### 6.1 Category D Features

Four IRIC aggregate scores become Category D model input features:
```python
CATEGORY_D_FEATURES = ["iric_anomalias", "iric_competencia", "iric_score", "iric_transparencia"]
# Alphabetical order, consistent with A/B/C ordering convention
```

These are added to `FEATURE_COLUMNS` in `pipeline.py`, bringing the total from 30 to 34 features.

### 6.2 IRIC Component Flags (NOT model features)

The 11 binary components are computed but are NOT added to `FEATURE_COLUMNS`. They are:
- Used internally to compute the 4 aggregate scores
- Available for reporting/explainability (the "red flag checklist" in API responses)
- Stored in a separate `iric_components.parquet` artifact (or embedded in the IRIC result dict)

### 6.3 Bid Anomaly Features (NOT model features in v1)

Per FEATURES.md research: kurtosis and DRN are "flagged as NaN-heavy" and were listed as P2 (v1.x) features. However, requirements IRIC-04 and IRIC-05 explicitly require them. The planner must decide: compute them as part of the IRIC module (required by IRIC-04/05) but NOT include them in FEATURE_COLUMNS (since they'll be mostly NaN for direct contracting contracts which are 60%+ of the dataset).

**Recommendation:** Compute kurtosis and DRN, store in the IRIC result dict and in a separate artifact, but do NOT add them to FEATURE_COLUMNS. The requirement says "calculate" not "include as XGBoost feature." FEAT-04 only specifies 4 aggregate scores as Category D.

### 6.4 Pipeline Integration Points

**Batch path (`build_iric()`):**
```python
# New function, parallel to build_features()
# Reads: features.parquet (or raw contratos), iric_thresholds.json
# Writes: artifacts/iric/iric_scores.parquet (id_contrato + 4 scores + 11 flags + kurtosis + drn)
```

**Pipeline extension (`pipeline.py`):**
```python
# After Cat C computation, add Cat D:
iric_result = compute_iric(contract_row, procesos_data, provider_history, thresholds)
cat_d = {
    "iric_score": iric_result["iric_score"],
    "iric_competencia": iric_result["iric_competencia"],
    "iric_transparencia": iric_result["iric_transparencia"],
    "iric_anomalias": iric_result["iric_anomalias"],
}
```

**Online path (`compute_iric()`):**
```python
# Analogous to compute_category_a/b/c
# Accepts contract_row dict, procesos_data dict, provider_history dict, thresholds dict
# Returns all 11 components + 4 scores + kurtosis + drn
```

**Threshold loading:** `load_iric_thresholds()` — lazy-load pattern (same as rcac_lookup, provider_history). `reset_iric_thresholds_cache()` for test isolation.

---

## 7. Module Structure

```
src/sip_engine/iric/
    __init__.py             # re-exports public API
    components.py           # compute_iric_components(row, procesos_data, provider_history, thresholds) -> dict
    bid_stats.py            # build_bid_stats_lookup(), compute_bid_stats(bids) -> dict
    thresholds.py           # calibrate_iric_thresholds(df), load_iric_thresholds(), reset cache
    scores.py               # compute_iric_scores(components) -> dict (4 aggregates)
    pipeline.py             # build_iric(force), compute_iric(online) — orchestrators
```

Or a flatter structure with fewer files (since this is a moderate-complexity module):
```
src/sip_engine/iric/
    __init__.py
    calculator.py           # all 11 components + 4 scores (compute_iric_components, compute_iric_scores)
    bid_stats.py            # kurtosis + DRN (build_bid_stats_lookup, compute_bid_stats)
    thresholds.py           # calibrate + load + reset
    pipeline.py             # build_iric(force), compute_iric(online)
```

**Recommendation for planner:** Use the 4-file flatter structure. `calculator.py` handles all component and score logic. `bid_stats.py` is isolated because bid data requires a separate streaming pass. `thresholds.py` handles calibration and loading. `pipeline.py` orchestrates.

---

## 8. Data Available from Prior Phases

The following data is already computed by Phase 5 and available to IRIC:

| Data | Source | How Available |
|---|---|---|
| `num_actividades_economicas` | `num_actividades_lookup` (pipeline.py) | Pass to `compute_iric()` |
| `num_contratos_previos_nacional` | `provider_history` dict | From `lookup_provider_history()` |
| `num_sobrecostos_previos` | `provider_history` dict | From `lookup_provider_history()` |
| `num_retrasos_previos` | `provider_history` dict | From `lookup_provider_history()` |
| `dias_publicidad` | Category B | From `compute_category_b()` |
| `dias_decision` | Category B | From `compute_category_b()` |
| `procesos_data` dict | `_build_procesos_lookup()` | Already in pipeline |
| `Proveedores Unicos con Respuestas` | `procesos_data` | `procesos_data.get(...)` |
| `Modalidad de Contratacion` | `contratos` row | `row.get("Modalidad de Contratacion")` |
| `Justificacion Modalidad de Contratacion` | `contratos` row | `row.get(...)` |
| `TipoDocProveedor`, `Documento Proveedor` | `contratos` row | Already used in Cat C |
| `Valor del Contrato` | `contratos` row / Category A | Already in pipeline |

**What is NOT yet available (Phase 6 must add):**
- Bid values per process (from `ofertas_proceso_SECOP.csv`) — new streaming pass in `build_bid_stats_lookup()`
- IRIC thresholds JSON — new artifact
- `ausencia_proceso` logic — trivially `procesos_data is None`

---

## 9. Key Implementation Decisions for Planner

### 9.1 NaN vs 0 for Missing Provider History

VigIA fills NaN with 0: "en caso de NaN al ser proveedor nuevo lo suma como 0." SIP success criterion 6 confirms: components 9 and 10 return 0 for providers with no prior history. This is consistent with VigIA and with the requirement.

### 9.2 `ausencia_proceso` When `procesos_data is None`

The component fires when `procesos_data is None`. This means the join between `contratos["Proceso de Compra"]` and `procesos["ID del Portafolio"]` found no match. VigIA explicitly says this IS the irregularity — do not fill or impute, fire the flag.

Consequence: `unico_proponente` and `periodo_publicidad_extremo` and `periodo_decision_extremo` will also be based on missing procesos data when `ausencia_proceso = 1`. These should return NaN (not 0) when procesos data is absent, because the absence is already captured by `ausencia_proceso = 1`. Summing NaN as 0 for the aggregate IRIC score is correct (VigIA pattern).

### 9.3 Threshold Lookup by `tipo_contrato`

When looking up a percentile threshold:
1. Normalize `tipo_contrato` string (strip, lowercase? — keep original case to match JSON keys)
2. Try exact match in `iric_thresholds["tipo_contrato"]`
3. Fall back to `"Otro"` if not found or group was too small
4. If even `"Otro"` is missing, use a hardcoded fallback (VigIA values: publicidad P99=14, decision P95=43, contracts P95=3)

### 9.4 Bid Stats Lookup for Online Path

For online `compute_iric()`, the caller must pass bid values for the contract's process. The `pipeline.py` online path already receives `procesos_data` — it needs to also receive bid values. This means the online pipeline must be extended to fetch bid data.

Options:
a. Pass `bids: list[float] | None` as a parameter to `compute_iric()`
b. Build a bid stats lookup in the online caller (not feasible at runtime)

**Recommendation:** Add `bid_values: list[float] | None = None` parameter to `compute_iric()`. When `None`, kurtosis and DRN are `NaN`. The batch path (`build_iric`) pre-builds the bid stats lookup offline.

### 9.5 Rare Contract Type Merging

Per CONTEXT.md: `min_group_size = 30`. Contract types with < 30 observations are merged into `"Otro"` for percentile computation. The planner should implement this in `calibrate_iric_thresholds()`.

### 9.6 FEATURE_COLUMNS Update

`pipeline.py` currently defines 30 features. Phase 6 must update `FEATURE_COLUMNS` to add the 4 Category D features (alphabetically within D):
```python
# Category D (4 features) — IRIC scores (computed after Cat A/B/C)
"iric_anomalias", "iric_competencia", "iric_score", "iric_transparencia",
```
Total: 34 features.

---

## 10. Testing Strategy

Tests for IRIC must cover all 11 success criteria from the phase description:

| Test | What to Test |
|---|---|
| `test_unico_proponente` | Fires on 1 bidder, does not fire on 2, NaN when no procesos |
| `test_proveedor_multiproposito` | Fires on > 1 UNSPSC segment, not on 1 |
| `test_historial_proveedor_alto` | Fires above P95 threshold, not below |
| `test_contratacion_directa` | Fires on both "Contratación directa" variants |
| `test_regimen_especial` | Fires on both "régimen especial" variants |
| `test_periodo_publicidad_extremo` | Fires on 0 days, fires above P99, not in normal range |
| `test_datos_faltantes` | Each of 3 sub-checks triggers the flag independently |
| `test_periodo_decision_extremo` | Fires on 0 days, fires above P95, not in normal range |
| `test_proveedor_sobrecostos_previos` | Returns 0 when no history (new provider) |
| `test_proveedor_retrasos_previos` | Returns 0 when no history (new provider) |
| `test_ausencia_proceso` | Fires when procesos_data is None |
| `test_curtosis_licitacion` | Correct value for 4+ bids, NaN for < 4 bids |
| `test_diferencia_relativa_norm` | Correct value for 3+ bids, NaN for < 3 bids |
| `test_iric_score_formula` | (1/11) × sum of all 11 components |
| `test_iric_dimension_scores` | Competencia, transparencia, anomalias sub-sums |
| `test_calibrate_thresholds` | Rare types merged into Otro, P1/P5/P95/P99 computed |
| `test_threshold_fallback` | Unknown tipo_contrato falls back to Otro |
| `test_feature_columns` | FEATURE_COLUMNS now has 34 entries including 4 Cat D |

---

## 11. Existing Codebase Hooks

Key files Phase 6 must read and extend:

| File | Relevant Content | Change Required |
|---|---|---|
| `src/sip_engine/features/pipeline.py` | `FEATURE_COLUMNS`, `build_features()`, `compute_features()` | Add Cat D features, call `compute_iric()` |
| `src/sip_engine/features/__init__.py` | Re-exports | Add IRIC exports if needed |
| `src/sip_engine/iric/__init__.py` | Empty placeholder | Populate with public API |
| `src/sip_engine/config/settings.py` | `iric_thresholds_path`, `artifacts_iric_dir` | Already present — no change |
| `src/sip_engine/__main__.py` | CLI subcommands | Add `build-iric` subcommand |
| `src/sip_engine/data/schemas.py` | `OFERTAS_USECOLS` | Already has bid fields — no change |
| `src/sip_engine/data/loaders.py` | `load_ofertas()` | Already exists — no change |

Already defined in settings:
- `settings.artifacts_iric_dir` → `artifacts/iric/`
- `settings.iric_thresholds_path` → `artifacts/iric/iric_thresholds.json`

---

## 12. VigIA Column Name Mapping (SIP vs VigIA)

| VigIA Column | SIP Source | SIP Column / Variable |
|---|---|---|
| `proveedores_unicos_con` | procesos | `Proveedores Unicos con Respuestas` |
| `modalidad_de_contratacion` | contratos | `Modalidad de Contratacion` |
| `justificacion_modalidad_de` | contratos | `Justificacion Modalidad de Contratacion` |
| `tipodocproveedor` | contratos | `TipoDocProveedor` |
| `documento_proveedor` | contratos | `Documento Proveedor` |
| `valor_del_contrato` | contratos | `Valor del Contrato` (Float64) |
| `tipo_de_contrato` | contratos | `Tipo de Contrato` |
| `Dias Proceso Contratacion Abierto` | computed | `dias_publicidad` (Category B) |
| `Periodo de Decision` | computed | `dias_decision` (Category B) |
| `tiene_variables_portafolio` | computed | `procesos_data is not None` |
| `segmentos_de_categoria_principal` | computed | `num_actividades_economicas` (Category C) |
| `numero_adiciones_valor > 0` | computed | `num_sobrecostos_previos > 0` (provider_history) |
| `numero_adiciones_tiempo > 0` | computed | `num_retrasos_previos > 0` (provider_history) |
| `numero_procesos` | computed | `num_contratos_previos_nacional` (provider_history) |

---

## 13. Suggested Plan Breakdown

The planner should consider 3 plans:

**06-01: IRIC Calculator + Threshold Calibration**
- `iric/calculator.py` — all 11 components + 4 aggregate scores
- `iric/thresholds.py` — `calibrate_iric_thresholds()` + `load_iric_thresholds()` + `reset_iric_thresholds_cache()`
- `build-iric-thresholds` CLI or integrated into build_iric
- Tests for all 11 components and threshold calibration

**06-02: Bid Anomaly Stats (Kurtosis + DRN)**
- `iric/bid_stats.py` — `build_bid_stats_lookup()` + `compute_bid_stats()`
- Integration into pipeline batch path
- Tests for kurtosis and DRN formulas

**06-03: Pipeline Integration (FEAT-04) + CLI**
- `iric/pipeline.py` — `build_iric(force)` + `compute_iric(online)`
- Extend `features/pipeline.py` — add Cat D features to `build_features()` and `compute_features()`
- Update `FEATURE_COLUMNS` (30 → 34)
- Update `iric/__init__.py` re-exports
- Add `build-iric` CLI subcommand to `__main__.py`
- Integration tests

---

## 14. Critical Risks and Pitfalls

1. **NaN propagation in IRIC score**: VigIA sums NaN as 0 by using `sum(axis=1)` which skips NaN. In SIP's per-contract Python loop, explicit NaN checks are needed: `value = component if component is not None else 0.0`.

2. **`ausencia_proceso` vs missing procesos fields**: Component 11 fires when there is NO process record at all. Components 6, 7 (sub-check for publicidad), and 8 depend on procesos fields that are individually missing even when a process record exists. Treat these as two distinct missing-data situations.

3. **Bid stats lookup memory**: `ofertas_proceso_SECOP.csv` is 3.4 GB, 9.7M rows. Build the bid stats lookup in a streaming pass that only accumulates bid values per process ID — do NOT load all bid rows into memory. The result dict (one entry per unique proceso_id with pre-computed kurtosis/DRN) will be much smaller.

4. **Train/test split timing**: Phase 6 writes `iric_thresholds.json` using ALL data. Phase 7 must overwrite this with training-data-only thresholds before model training. The `calibrate_iric_thresholds(df)` function must accept an arbitrary DataFrame, not hardcode loading the full dataset.

5. **`dias_publicidad` and `dias_decision` already computed**: Do NOT recompute these in the IRIC calculator. Pass them in from the Category B results. This avoids code duplication and ensures the same value is used for both the Category B feature and the IRIC component.

6. **`proveedor_multiproposito` vs `historial_proveedor_alto`**: VigIA called `proveedor_recurrente` what SIP calls `historial_proveedor_alto`. VigIA's `proveedor_multiproposito` corresponds to SIP's `proveedor_multiproposito`. Both are in the competition dimension.

7. **The VigIA IRIC has 11 components, same as SIP**: The VigIA `vars_indice` list contains exactly 11 variables (though some paper versions have different counts). Confirm by counting: proponente_unico, proveedor_multiproposito, proveedor_recurrente, contratacion_directa, contratacion_regimen_especial, presencia_errores, duracion_extrema_proceso, periodo_decision_extremo, adicion_valor_proveedor, adicion_tiempo_proveedor, ausencia_proceso_contratacion = 11. ✓

---

## 15. Summary: What the Planner Needs to Know

1. **11 components are fully defined** from VigIA reference code — exact Python equivalents are in Section 2 above. No ambiguity.

2. **Kurtosis**: `scipy.stats.kurtosis(bids, fisher=True, bias=False)` for excess kurtosis. Minimum 4 bids.

3. **DRN**: `(sorted_bids[1] - sorted_bids[0]) / sorted_bids[0]` — relative gap between the two cheapest bids. Minimum 3 bids. Document this formula choice explicitly.

4. **Thresholds** are percentiles by `tipo_contrato`, with `"Otro"` fallback. VigIA Bogota values serve as fallback defaults if calibration fails.

5. **Category D adds 4 features** to `FEATURE_COLUMNS` (34 total). The 11 component flags and kurtosis/DRN are in a separate artifact, NOT in the model feature vector.

6. **Provider history reuse**: Components 9 and 10 reuse data already computed by Phase 5's `lookup_provider_history()`. No new data needed.

7. **`ausencia_proceso` is free**: `procesos_data is None` in the pipeline means the process was not found. Component 11 fires directly from this.

8. **One new data streaming pass is needed**: `bid_stats_lookup` from `ofertas_proceso_SECOP.csv`. This is the only new I/O requirement in Phase 6.

9. **Settings already has all needed paths**: `settings.iric_thresholds_path` and `settings.artifacts_iric_dir` are already defined in Phase 1.

10. **Test isolation pattern**: Use `reset_iric_thresholds_cache()` (same pattern as `reset_rcac_cache()` and `reset_provider_history_cache()`).

---

*Research complete: 2026-03-01*
*All references: VigIA/Salazar et al. 2024 (local codebase at `/Users/simonb/SIP Code/Data/Vigia/`), Gallego et al. 2021, Imhof 2018, SIP REQUIREMENTS.md, 06-CONTEXT.md*
