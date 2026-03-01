# Phase 5: Feature Engineering — Research

**Researched:** 2026-03-01
**Researcher:** gsd-phase-researcher
**Phase:** 05-feature-engineering
**Requirements:** FEAT-01, FEAT-02, FEAT-03, FEAT-05, FEAT-06, FEAT-07, FEAT-08, FEAT-09, FEAT-10

---

## 1. Critical Discovery: Schema Additions Required Before Feature Engineering

Two source files need new columns added to their schema constants in `schemas.py` to support Phase 5. These are not in the current `CONTRATOS_USECOLS` or `PROCESOS_USECOLS`.

### 1.1 `CONTRATOS_USECOLS` — Missing Column

`"Codigo de Categoria Principal"` (col 14 in contratos_SECOP.csv) is the UNSPSC-like category code required for `unspsc_categoria` (FEAT-01). It contains values like `"V1.80111600"` where the segment code is the 2-digit prefix after `"V1."`.

**Action:** Add `"Codigo de Categoria Principal"` to `CONTRATOS_USECOLS` and `CONTRATOS_DTYPE` (as `str`).

### 1.2 `PROCESOS_USECOLS` — Missing Columns

Three columns are missing from the current schema that are needed for FEAT-02 temporal features:

| Column | Purpose |
|---|---|
| `"ID del Portafolio"` | **Join key** — links procesos to contratos via `Proceso de Compra`. Without this, the entire procesos join is impossible. |
| `"Fecha de Recepcion de Respuestas"` | Used for `dias_publicidad` (bid window end date, confirmed per VigIA) |
| `"Fecha Adjudicacion"` | Used for `dias_decision` (decision/award date) |

**Action:** Add all three to `PROCESOS_USECOLS` and `PROCESOS_DTYPE` (`str` for `ID del Portafolio`, date columns can remain as `str` for `parse_dates`-based coercion later).

---

## 2. The Contratos–Procesos Join

### 2.1 Correct Join Key (Critical Finding)

The join between `contratos_SECOP.csv` and `procesos_SECOP.csv` is **NOT** `contratos["Proceso de Compra"]` ↔ `procesos["ID del Proceso"]`. These use incompatible formats (`CO1.BDOS.*` vs `CO1.REQ.*`) and produce zero matches.

The correct join is:

```
contratos["Proceso de Compra"] ↔ procesos["ID del Portafolio"]
```

Both use the `CO1.BDOS.*` format (confirmed empirically). This was how VigIA implemented the join (`secop_2ce_3.merge(secop_22, left_on=['Proceso de Compra'], right_on=['ID del Portafolio'])`).

### 2.2 Match Rate

- Total unique `Proceso de Compra` in contratos: 325,098
- Unique `ID del Portafolio` in procesos: 4,471,557
- Overlap: 197,859 matches (**60.9% match rate**)
- Unmatched 39.1%: contracts without a BDOS portafolio record (typical for direct contracting, single-bidder processes, regime-special contracts)
- For unmatched contracts: `dias_publicidad`, `dias_decision`, `num_ofertas_recibidas`, `num_proponentes` will all be `NaN` — XGBoost handles this natively without imputation

### 2.3 Memory Strategy for Procesos Join

`procesos_SECOP.csv` is 5.3 GB. Stream it once, extract only the required columns, and build a dict keyed on `ID del Portafolio` for O(1) lookup during the contratos feature build. This dict will contain ~4.5M entries with 5 values each — approximately 500MB in memory. Acceptable.

**Alternative (preferred for large-scale):** Build a parquet index of procesos joined columns offline, serialize it, and load for the feature build step.

---

## 3. Feature-to-Column Mapping (All 9 Requirements)

### 3.1 Category A: Contract Features (FEAT-01)

| Feature | Source Column | File | Notes |
|---|---|---|---|
| `valor_contrato` | `Valor del Contrato` | contratos | Already Float64 after `clean_currency()` |
| `tipo_contrato_cat` | `Tipo de Contrato` | contratos | Label-encode; ~15 distinct values |
| `modalidad_contratacion_cat` | `Modalidad de Contratacion` | contratos | Label-encode |
| `es_contratacion_directa` | `Modalidad de Contratacion` | contratos | Binary: 1 if "Contratación directa" (case-insensitive) |
| `es_regimen_especial` | `Modalidad de Contratacion` | contratos | Binary: 1 if "Contratación régimen especial" |
| `es_servicios_profesionales` | `Justificacion Modalidad de Contratacion` | contratos | Binary: 1 if contains "ServiciosProfesionales" or "Servicios Profesionales" |
| `unspsc_categoria` | `Codigo de Categoria Principal` | contratos | Extract 2-digit segment from `"V1.XXNNNNNN"` → integer; **NEW column needed** |
| `departamento_cat` | `Departamento` | contratos | Label-encode |
| `origen_recursos_cat` | `Origen de los Recursos` | contratos | Label-encode |
| `tiene_justificacion_modalidad` | `Justificacion Modalidad de Contratacion` | contratos | Binary: 1 if non-null and not "N/A"/"No definido" |

**`unspsc_categoria` extraction:** The code format is `V1.SSFFFFCC` where SS=segment (2 digits). Extract as integer: `int(code[3:5])` after stripping `"V1."`. Null/malformed codes → `NaN`.

### 3.2 Category B: Temporal Features (FEAT-02)

| Feature | Formula | Source Files |
|---|---|---|
| `dias_firma_a_inicio` | `Fecha de Inicio del Contrato` - `Fecha de Firma` | contratos |
| `duracion_contrato_dias` | `Fecha de Fin del Contrato` - `Fecha de Inicio del Contrato` | contratos |
| `dias_publicidad` | `Fecha de Recepcion de Respuestas` - `Fecha de Publicacion del Proceso` | procesos (via portafolio join) |
| `dias_decision` | `Fecha de Firma` (contratos) - `Fecha de Ultima Publicación` (procesos) | contratos + procesos join |
| `dias_proveedor_registrado` | `Fecha de Firma` (contratos) - `Fecha Creación` (proveedores) | contratos + proveedores |
| `firma_posterior_a_inicio` | Binary: 1 if `dias_firma_a_inicio` < 0 | derived |
| `mes_firma` | `Fecha de Firma`.month | contratos |
| `trimestre_firma` | `Fecha de Firma`.quarter | contratos |
| `dias_a_proxima_eleccion` | Distance in days to the next election date ≥ signing date | contratos + static calendar |

**VigIA confirmed formulas:**
- `dias_publicidad` = `Fecha de Recepcion de Respuestas` - `Fecha de Publicacion del Proceso` (VigIA calls this "Dias Proceso Contratacion Abierto")
- `dias_decision` = `Fecha de Firma` - `Fecha de Ultima Publicación` (VigIA calls this "Periodo de Decision")
- `dias_proveedor_registrado` = `Fecha de Firma` - `Fecha inscripcion proveedor`; NaN → 0 (not registered before signing)

**Null handling:** Negative values → clip to 0 (VigIA pattern). NaN from unmatched procesos join → XGBoost handles natively.

**`dias_firma_a_inicio`:** A negative value means the contract was signed AFTER the start date — a procedural anomaly. `firma_posterior_a_inicio = 1` when `dias_firma_a_inicio < 0`.

**Proveedores join key:** `proveedores["NIT"]` ↔ normalized `contratos["Documento Proveedor"]` (normalize_numero). The `Fecha Creación` column in proveedores has format `MM/DD/YYYY` (confirmed empirically).

### 3.3 Category C: Provider/Competition Features (FEAT-03)

| Feature | Source | Notes |
|---|---|---|
| `tipo_persona_proveedor` | `TipoDocProveedor` (contratos) | NIT → 1 (juridica), CC/CE/other → 0 (natural) |
| `num_contratos_previos_nacional` | Provider History Index | Count of provider's prior national contracts as-of signing date |
| `num_contratos_previos_depto` | Provider History Index | Count of provider's prior contracts in same department |
| `num_ofertas_recibidas` | `Respuestas al Procedimiento` (procesos) | NaN for unmatched; integer |
| `num_proponentes` | `Proveedores Unicos con Respuestas` (procesos) | NaN for unmatched; integer |
| `proponente_unico` | Derived | Binary: 1 if `num_proponentes == 1` |
| `num_actividades_economicas` | Derived from contratos history | Count of distinct UNSPSC segments (`unspsc_categoria`) a provider has won contracts in across all SECOP history. Computed from the full contratos dataset. |
| `valor_total_contratos_previos_nacional` | Provider History Index | Sum of prior national contract values as-of signing date |
| `valor_total_contratos_previos_depto` | Provider History Index | Sum of prior dept contract values as-of signing date |
| `num_sobrecostos_previos` | Provider History Index | Count of prior contracts with M1=1 (from labels.parquet) |
| `num_retrasos_previos` | Provider History Index | Count of prior contracts with M2=1 (from labels.parquet) |

**`num_actividades_economicas`:** Count of distinct `unspsc_categoria` segments the provider has won across ALL historical contracts (not just prior to signing date — this is a static provider characteristic computed from full dataset). Providers with only one UNSPSC segment score 1. This is an indicator of provider specialization vs. multipurpose capacity.

**`tipo_persona_proveedor`:** Binary indicator (1 = legal entity/NIT, 0 = natural person). Derived by checking if `normalize_tipo(TipoDocProveedor) == "NIT"`.

---

## 4. Provider History Index (FEAT-05, FEAT-06)

### 4.1 Purpose and Scope

The Provider History Index enables O(1) as-of-date lookup for all 6 provider history features: 2 national counts, 2 departmental counts, 2 label-derived counts. It is a required offline artifact serialized to `artifacts/features/provider_history_index.pkl`.

### 4.2 Data Source

The index is built entirely from:
- `contratos_SECOP.csv` — all 340,479 contracts (provider ID, dept, signing date, contract value)
- `artifacts/labels/labels.parquet` — M1/M2 labels for sobrecostos/retrasos history

### 4.3 Temporal Leak Guard (FEAT-05)

**Strict requirement:** For any contract with signing date `d`, the provider history must include ONLY contracts signed BEFORE `d` (strictly `<`, not `<=`). Same-day contracts are excluded from that provider's history — the contract being scored cannot appear in its own provider history.

### 4.4 Index Data Structure

Two viable structures for the index:

**Option A — Sorted list per provider (recommended):**
```python
{
    (tipo_norm, num_norm): [
        {"fecha_firma": date, "valor": float, "departamento": str, "m1": 0|1|null, "m2": 0|1|null},
        ...  # sorted ascending by fecha_firma
    ]
}
```
For any query `(provider, date, dept)`: binary search for the cutoff, then aggregate counts/sums from the slice before the cutoff date. Memory: ~340k contracts × ~50 bytes each = ~17MB for the full index.

**Option B — Precomputed cumulative per-provider-date (VigIA approach):**
Build a DataFrame of (provider, date) → cumulative counts/values. Look up by provider + bisect_left on dates.

**Recommendation: Option A** — it is more memory-efficient, supports exact as-of queries, and doesn't require materializing all (provider × date) combinations.

### 4.5 Serialization

Serialize via `joblib.dump()` to `artifacts/features/provider_history_index.pkl` following the same pattern as `rcac.pkl`.

### 4.6 Settings Addition Required

Add `provider_history_index_path: Path` to `Settings` in `config/settings.py`:
```python
self.provider_history_index_path = self.artifacts_features_dir / "provider_history_index.pkl"
```

### 4.7 Null Provider IDs in History Build

7.2% of contratos rows have null `Fecha de Firma`. These rows cannot be used for as-of computations and must be excluded from the index build (they cannot be ordered temporally). They still receive M1/M2 labels if applicable.

---

## 5. Colombian Election Calendar (FEAT-02)

### 5.1 Date Range of Data

Contratos signing dates span 2015-12-03 to 2026-02-07 (confirmed empirically on 100k sample). The election calendar must cover this entire range.

### 5.2 Colombian Election Types

Based on Gallego et al. (2021) and Colombian political cycles:

| Type | Cycle | First Round Dates |
|---|---|---|
| Presidential | 4 years | May 2018, May 2022, May 2026 |
| Congressional | 4 years (same cycle) | March 2018, March 2022, March 2026 |
| Local/Regional (alcaldes, gobernadores, concejales, diputados) | 4 years | Oct 2015, Oct 2019, Oct 2023 |

**Recommended calendar constant (covering 2015–2027):**
```python
COLOMBIAN_ELECTION_DATES: list[datetime.date] = [
    date(2015, 10, 25),  # Local/Regional
    date(2018, 3, 11),   # Congressional
    date(2018, 5, 27),   # Presidential first round
    date(2018, 6, 17),   # Presidential second round
    date(2019, 10, 27),  # Local/Regional
    date(2022, 3, 13),   # Congressional
    date(2022, 5, 29),   # Presidential first round
    date(2022, 6, 19),   # Presidential second round
    date(2023, 10, 29),  # Local/Regional
    date(2026, 3, 8),    # Congressional (est.)
    date(2026, 5, 31),   # Presidential first round (est.)
]
```

Gallego et al. (2021) found this feature predictive for M3 (Comptroller findings). The feature measures **days to the NEXT election only** (`dias_a_proxima_eleccion`). For contracts signed after the last known election, set a large value (e.g., 9999) or NaN — planner should decide.

### 5.3 Implementation

For each contract with signing date `d`:
1. `next_election = min(e for e in COLOMBIAN_ELECTION_DATES if e >= d)`
2. `dias_a_proxima_eleccion = (next_election - d).days`
3. If no future election in the calendar: `NaN` (XGBoost handles)

---

## 6. Categorical Encoding (FEAT-10)

### 6.1 Distribution of Key Categorical Columns

From a 100k sample of contratos:

| Column | Approximate Distinct Values | High-Frequency Pattern |
|---|---|---|
| `Tipo de Contrato` | ~15 | "Prestación de servicios" dominates (~70%) |
| `Modalidad de Contratacion` | ~10 | "Contratación directa" and "régimen especial" dominate |
| `Departamento` | ~33 + some special | Standard 32 departments + "Distrito Capital" |
| `Origen de los Recursos` | ~10 | "Distribuido" and "Recursos Propios" dominate |
| `unspsc_categoria` (segment) | ~25 | Segment 80 (services) = 74.6% |
| `Justificacion Modalidad de Contratacion` | ~50+ | Very long tail expected |

### 6.2 Frequency Threshold (FEAT-10)

- Threshold: < 0.1% of training observations → grouped into "Other"
- Applied to `tipo_contrato_cat`, `modalidad_contratacion_cat`, `departamento_cat`, `origen_recursos_cat`, `unspsc_categoria`
- **Critical:** Threshold computed on training data only, then applied to test/inference data
- Mapping serialized to `artifacts/features/encoding_mappings.json` per CONTEXT.md decision (FEAT-07 train-serve parity)
- At inference time: unseen categories → "Other"

### 6.3 Label Encoding (Integer Codes)

Per CONTEXT.md decision: label encoding (category → integer), alphabetical ordering for determinism. This maps directly to XGBoost's ability to handle integer-coded categoricals as numeric with learned split directions.

### 6.4 Encoding Mappings File Format

```json
{
  "tipo_contrato_cat": {"Consultoría": 1, "Obra": 2, "Other": 0, ...},
  "modalidad_contratacion_cat": {"Contratación directa": 1, "Other": 0, ...},
  "departamento_cat": {"Antioquia": 1, "Bogotá D.C.": 2, "Other": 0, ...},
  "origen_recursos_cat": {"Distribuido": 1, "Other": 0, ...},
  "unspsc_categoria": {80: 1, 85: 2, "Other": 0, ...}
}
```

---

## 7. Feature Pipeline Architecture (FEAT-07, FEAT-08, FEAT-09)

### 7.1 Module: `src/sip_engine/features/pipeline.py`

Single entry point for all feature construction (train-serve parity requirement).

**Public API:**
```python
def build_features(force: bool = False) -> Path:
    """Build offline feature matrix for all contracts → features.parquet."""

def compute_features(contract_row: dict, as_of_date: date) -> dict:
    """Online per-contract inference: returns feature dict for XGBoost prediction."""

def build_provider_history_index(force: bool = False) -> Path:
    """Build and serialize provider_history_index.pkl."""

def build_encoding_mappings(df_train: pd.DataFrame) -> dict:
    """Compute encoding mappings from training data (FEAT-10 threshold)."""
```

**Offline (batch) path:** `build_features()` streams contratos, joins procesos lookup dict and proveedores lookup dict, computes all features, writes `artifacts/features/features.parquet`.

**Online (inference) path:** `compute_features()` accepts a single contract dict and returns a feature vector using the same transformation code. Loads `provider_history_index.pkl` and `encoding_mappings.json` from artifacts.

### 7.2 Feature Exclusions (FEAT-08, FEAT-09)

**Explicitly excluded (post-execution, FEAT-08):**
- `Fecha de Inicio de Ejecucion`, `Fecha de Fin de Ejecucion` (execution dates)
- `Valor Facturado`, `Valor Pagado`, `Valor Pendiente de Pago` (payment data)
- All columns from `ejecucion_contratos.csv`

**Explicitly excluded (RCAC-derived, FEAT-09):**
- `proveedor_en_rcac`, `proveedor_responsable_fiscal`, `en_siri`, `en_multas_secop`, `en_colusiones`
- All RCAC lookup results

A comment block in `pipeline.py` must explicitly list these exclusions with their requirement references for auditability.

### 7.3 Feature Column Ordering Convention

Alphabetical within each category, categories in order A → B → C:

```
# Category A (10 features):
departamento_cat, es_contratacion_directa, es_regimen_especial, es_servicios_profesionales,
modalidad_contratacion_cat, origen_recursos_cat, tiene_justificacion_modalidad,
tipo_contrato_cat, unspsc_categoria, valor_contrato

# Category B (9 features):
dias_a_proxima_eleccion, dias_decision, dias_firma_a_inicio, dias_proveedor_registrado,
dias_publicidad, duracion_contrato_dias, firma_posterior_a_inicio, mes_firma, trimestre_firma

# Category C (11 features, dual-scope provider history):
num_actividades_economicas, num_contratos_previos_depto, num_contratos_previos_nacional,
num_ofertas_recibidas, num_proponentes, num_retrasos_previos, num_sobrecostos_previos,
proponente_unico, tipo_persona_proveedor,
valor_total_contratos_previos_depto, valor_total_contratos_previos_nacional

# Total: 30 features (Category D / IRIC features added in Phase 6 = 4 more → 34 total)
```

This ordering is serialized to `feature_registry.json` per MODL-09 requirement.

---

## 8. Settings Additions Required

| Setting | Path | Notes |
|---|---|---|
| `provider_history_index_path` | `artifacts/features/provider_history_index.pkl` | New in Phase 5 |
| `encoding_mappings_path` | `artifacts/features/encoding_mappings.json` | New in Phase 5 |
| `features_path` | `artifacts/features/features.parquet` | New in Phase 5 |

The `feature_registry_path` is already defined in settings.py as `artifacts/features/feature_registry.json`.

---

## 9. CLI Extension

Add `build-features` subcommand to `python -m sip_engine`:
```
python -m sip_engine build-features [--force]
```

Pattern mirrors `build-rcac` and `build-labels`. Must check that:
1. `labels.parquet` exists (Provider History Index requires M1/M2 labels)
2. Dispatches to `build_features(force=False)` in `features/pipeline.py`

---

## 10. Memory and Performance Considerations

### 10.1 Offline Feature Build

| Step | Memory | Strategy |
|---|---|---|
| Load full contratos (selected cols) | ~70MB (8 cols × 340k rows) | Direct load, fits in RAM |
| Build procesos lookup dict | ~200MB (5 cols × 197k matched rows) | Stream and build dict |
| Build proveedores lookup dict | ~50MB (2 cols × 1.6M rows, NIT-keyed) | Stream and build dict |
| Build provider history index | ~17MB | Stream contratos, sort by date per provider |
| Feature matrix (30 features × 340k contracts) | ~300MB | Build in-memory, write to parquet |

Peak memory: approximately 500-700MB — acceptable for the target environment.

### 10.2 Proveedores Join Match Rate

Proveedores has 1.6M registered entries, but contratos has only ~340k unique provider IDs. Many providers in contratos will not appear in the proveedores registry (direct registration not always done). For unmatched providers:
- `dias_proveedor_registrado` → NaN
- `num_actividades_economicas` → count from contratos history only (not proveedores categories)

### 10.3 Null Handling Summary

| Feature | Missing When | Treatment |
|---|---|---|
| All Category A features except `valor_contrato` | Missing signing date (7.2%) | Row dropped (CONTEXT.md decision) |
| `valor_contrato` | Truly missing | Row dropped |
| `dias_publicidad`, `dias_decision` | 39.1% no procesos match | `NaN` (XGBoost native) |
| `dias_proveedor_registrado` | Unregistered provider | `NaN` → per CONTEXT.md, not imputed; XGBoost handles |
| `num_ofertas_recibidas`, `num_proponentes` | No procesos match | `NaN` (XGBoost native) |
| `num_actividades_economicas` | First-time provider | `0` (no prior distinct categories) |
| All Provider History features | First-time provider | `0` (CONTEXT.md: "no history, not null") |
| `dias_a_proxima_eleccion` | Date beyond calendar range | `NaN` |

---

## 11. Testing Strategy

### 11.1 Test File

`tests/test_features.py` — follows the same pattern as Phase 3/4 tests: `tmp_path`, `monkeypatch.setenv("SIP_*", ...)`, minimal CSV fixtures.

### 11.2 Key Test Categories

| Category | Tests |
|---|---|
| **Schema additions** | `CONTRATOS_USECOLS` contains `"Codigo de Categoria Principal"`, `PROCESOS_USECOLS` contains `"ID del Portafolio"`, `"Fecha de Recepcion de Respuestas"`, `"Fecha Adjudicacion"` |
| **Category A features** | `valor_contrato` = Float64; `es_contratacion_directa`=1 for "Contratación directa"; `tiene_justificacion_modalidad`=0 for "N/A"; `unspsc_categoria` extracts segment correctly |
| **Category B temporal** | `dias_firma_a_inicio` negative when firma > inicio; `firma_posterior_a_inicio`=1 for negative values; `mes_firma` = month int; `trimestre_firma` = quarter |
| **Election calendar** | `dias_a_proxima_eleccion` > 0 for a date before a known election; decreases as date approaches election; NaN for date beyond calendar |
| **Category C provider** | `tipo_persona_proveedor` = 1 for NIT, 0 for CC; `proponente_unico`=1 when `num_proponentes`=1; first-time provider gets 0 for all history counts |
| **Provider History Index** | As-of guard: future contracts not included; same-day contract not included; national vs dept scope correct; M1/M2 label join correct |
| **FEAT-10 encoding** | Rare category (< 0.1% in training) maps to "Other"; encoding_mappings.json written; unseen category at inference maps to "Other" |
| **FEAT-07 parity** | `compute_features()` and `build_features()` produce identical vectors for the same contract |
| **FEAT-08 exclusion** | Post-execution columns not in feature vector; `ejecucion_contratos.csv` columns absent |
| **FEAT-09 exclusion** | RCAC-derived columns not in feature vector |
| **Pipeline CLI** | `build-features --force` runs without error (with mock data); produces `features.parquet` |
| **Drop-row behavior** | Contract with null signing date → excluded from output with INFO log |

Target: ~35-45 tests.

---

## 12. Phase Split Recommendation

Phase 5 should split into 3 plans:

### Plan 05-01: Infrastructure — Schema Additions, Settings, Provider History Index

**Files modified:**
- `src/sip_engine/data/schemas.py` — add `Codigo de Categoria Principal` to `CONTRATOS_USECOLS`, add `ID del Portafolio`/`Fecha de Recepcion de Respuestas`/`Fecha Adjudicacion` to `PROCESOS_USECOLS`
- `src/sip_engine/config/settings.py` — add `provider_history_index_path`, `encoding_mappings_path`, `features_path`
- `src/sip_engine/features/provider_history.py` — new module: `build_provider_history_index()`, `lookup_provider_history(tipo, num, date, dept)`
- `src/sip_engine/features/__init__.py` — re-exports
- `artifacts/features/.gitkeep` — already exists per scaffold
- `tests/test_features.py` — tests for schema additions, Settings, provider history as-of, national vs dept scope

### Plan 05-02: Category A/B/C Feature Builders

**Files modified:**
- `src/sip_engine/features/category_a.py` — contract feature extractors (FEAT-01)
- `src/sip_engine/features/category_b.py` — temporal feature extractors with election calendar (FEAT-02)
- `src/sip_engine/features/category_c.py` — provider/competition feature extractors (FEAT-03)
- `src/sip_engine/features/encoding.py` — categorical encoding with FEAT-10 threshold logic
- `tests/test_features.py` — extend with A/B/C feature tests and encoding tests

### Plan 05-03: Pipeline Integration and CLI

**Files modified:**
- `src/sip_engine/features/pipeline.py` — main pipeline: `build_features()`, `compute_features()`, exclusion enforcement (FEAT-07/08/09)
- `src/sip_engine/__main__.py` — add `build-features` subcommand
- `src/sip_engine/features/__init__.py` — re-export `build_features`
- `tests/test_features.py` — pipeline integration tests, CLI test, FEAT-07 parity test

---

## 13. Open Questions for Planner

1. **`dias_a_proxima_eleccion` beyond calendar:** For contracts signed after the last election date in the constant (e.g., 2026-07-01), should the feature be `NaN` or a large sentinel like 9999? XGBoost handles NaN natively, so NaN is safer.

2. **`num_actividades_economicas` as static vs as-of:** The CONTEXT.md says this is derived from "all prior contracts" of the provider. Should this also use the as-of guard (count distinct segments only for contracts before signing date), or is it a static provider attribute computed from the full history? Recommendation: **static** — it describes the provider's general specialization pattern, not a real-time accumulating count. This avoids complexity and is consistent with how VigIA treats provider characteristics.

3. **Procesos join in batch vs streaming:** The full procesos file is 5.3GB. The recommended strategy is to build an in-memory dict keyed on `ID del Portafolio` → (dates, bid counts) before processing contratos. This requires ~200MB but avoids multiple passes. Planner should decide between streaming join vs in-memory dict.

4. **`dias_proveedor_registrado` null handling:** VigIA imputes NaN → 0 (treating "unregistered" as "0 days registered"). Per CONTEXT.md: NaN, no imputation. These two approaches are different. Recommendation: **NaN**, consistent with the CONTEXT.md "non-critical missing fields remain as NaN" decision.

5. **Feature column ordering:** The alphabetical-within-category ordering above produces 30 features. Planner must confirm this becomes the canonical order in `feature_registry.json`, and document that Phase 6 IRIC features (4 more) will be appended at the end.

---

## 14. Module Update Checklist

| File | Change |
|---|---|
| `src/sip_engine/data/schemas.py` | Add `"Codigo de Categoria Principal"` to `CONTRATOS_USECOLS/DTYPE`; add 3 cols to `PROCESOS_USECOLS` |
| `src/sip_engine/config/settings.py` | Add `provider_history_index_path`, `encoding_mappings_path`, `features_path` |
| `src/sip_engine/features/__init__.py` | Re-export `build_features`, `build_provider_history_index` |
| `src/sip_engine/features/provider_history.py` | New: index builder + as-of lookup |
| `src/sip_engine/features/category_a.py` | New: FEAT-01 extractors |
| `src/sip_engine/features/category_b.py` | New: FEAT-02 extractors + election calendar |
| `src/sip_engine/features/category_c.py` | New: FEAT-03 extractors |
| `src/sip_engine/features/encoding.py` | New: FEAT-10 rare-category grouping + label encoding |
| `src/sip_engine/features/pipeline.py` | New: batch `build_features()`, online `compute_features()` |
| `src/sip_engine/__main__.py` | Add `build-features` CLI subcommand |
| `tests/test_features.py` | New: all feature engineering tests (~40 tests) |

---

## 15. Empirical Data Summary

| Source | Rows | Used For |
|---|---|---|
| contratos_SECOP.csv | 341,727 (340,479 unique) | Base dataset, Category A+B+C source |
| procesos_SECOP.csv | ~6.4M | Category B (temporal) + C (bid counts); join via `ID del Portafolio` |
| proveedores_registrados.csv | ~1.6M | `dias_proveedor_registrado`; join via NIT |
| labels.parquet | 340,479 | Provider history M1/M2 label counts |

| Feature Category | Count | Source |
|---|---|---|
| Category A (contract) | 10 | contratos only |
| Category B (temporal) | 9 | contratos + procesos + proveedores |
| Category C (provider/competition) | 11 | contratos + procesos + Provider History Index |
| Category D (IRIC) | 4 | Phase 6 (not in scope here) |
| **Phase 5 total** | **30** | |

| Key Distribution | Value |
|---|---|
| Contratos with null signing date (dropped) | 24,736 (7.2%) |
| Contratos matched to procesos portafolio | 197,859 (60.9%) |
| Unique providers with prior history | TBD (built at runtime) |

---

*Research complete. All 9 requirements (FEAT-01 through FEAT-03, FEAT-05 through FEAT-10) addressed.*
*Critical finding: contratos-procesos join must use `Proceso de Compra` ↔ `ID del Portafolio` (not `ID del Proceso`) — zero match otherwise.*
*Critical finding: `Codigo de Categoria Principal` and 3 procesos columns missing from current schemas — must be added before feature build.*
*Critical finding: 7.2% of contracts have null signing date — these must be dropped as they cannot support temporal ordering or as-of computations.*
