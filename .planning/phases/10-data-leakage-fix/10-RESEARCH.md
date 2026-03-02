# Phase 10: Data Leakage Fix — Research

**Researched:** 2026-03-02
**Domain:** Data correctness / ML feature engineering / label construction
**Confidence:** HIGH

## Summary

Phase 10 addresses three data correctness issues in the SIP Engine pipeline: (1) `duracion_contrato_dias` uses post-amendment "Fecha de Fin del Contrato" instead of the original "Duración del contrato" text field — this was the #1 feature by importance and inflates M1 AUC by ~7-15pp; (2) M2 label construction uses only "EXTENSION" tipo from adiciones.csv (19 positives) instead of also using "Dias adicionados" from contratos_SECOP.csv (~39,153 positives); (3) v1 artifacts need to be backed up before re-execution for proper before/after comparison.

All three issues have been empirically verified against the actual CSV data. The "Duración del contrato" column (index 70) contains text in 6 formats that need parsing. The "Dias adicionados" column (index 48) is numeric with 18 comma-thousands-separator edge cases. The CONTEXT.md also asked whether "Valor del Contrato" is leaky — empirical analysis shows ~2.3x higher mean for M1 contracts, but this is consistent with legitimate correlation (larger contracts more likely amended). The field is treated as non-leaky per CONTEXT.md decision.

**Primary recommendation:** Fix duration computation and M2 labels in source code, backup v1 artifacts, write comparison template script. User runs the full pipeline afterward.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Duration Leakage Fix**: Replace `Fecha de Fin del Contrato` minus `Fecha de Inicio del Contrato` with parsed "Duración del contrato" (col 70) text field
- **Parsing**: Convert all formats to days — Dia(s)→days, Mes(es)→×30, Año(s)→×365, Semana(s)→×7, Hora(s)→÷24
- **Month precision**: Use Mes×30 (approximation acceptable for ML features)
- **"No definido" (5.2%)**: Return NaN — XGBoost handles missing values natively
- **Unknown formats**: Log warning + return NaN (don't crash pipeline)
- **Schema change**: Add "Duración del contrato" to CONTRATOS_USECOLS in schemas.py
- **Remove**: Drop "Fecha de Fin del Contrato" from CONTRATOS_USECOLS entirely (prevent accidental re-use)
- **Keep**: "Fecha de Inicio del Contrato" stays — used for non-leaky category_b features (dias_desde_firma_hasta_inicio, es_inicio_rapido)
- **Feature name**: Keep `duracion_contrato_dias` unchanged — downstream consumers (FEATURE_COLUMNS, model training) unaffected
- **Parse location**: category_b.py (which already owns duracion_contrato_dias computation)
- **M2 Fix**: Add "Dias adicionados" column from contratos_SECOP.csv as PRIMARY M2 source (OR with existing EXTENSION)
- **Expected result**: ~39,153 M2 positives (11.5%) matching Vigia reference
- **Schema change**: Add "Dias adicionados" to CONTRATOS_USECOLS
- **Artifact Versioning**: Move old artifacts to `artifacts/v1_baseline/` BEFORE running pipeline
- **Git**: Commit v1_baseline to git (permanent record, not gitignored)
- **Comparison Report**: Both comparison.md and comparison.json in `artifacts/evaluation/`
- **Phase 10 does NOT run the pipeline** — code fixes only
- **Valor del Contrato**: Likely NOT leaky, researcher should empirically verify

### Claude's Discretion
- Duration parser implementation details (regex patterns, edge case handling)
- Exact structure of comparison report template
- Test updates needed for changed behavior
- Git commit granularity within the phase

### Deferred Ideas (OUT OF SCOPE)
- Missing Vigia Features (Es Pyme, Sector, EsPostConflicto, etc.) — Future Phase
- Per-Contract-Type Model Split — Future enhancement
- IRIC Key Mismatch (Phase 11) — `calculator.py:332` uses "num_sobrecostos" but provider_history returns "num_sobrecostos_previos"
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FEAT-02 | System generates temporal features (Category B): `duracion_contrato_dias` etc. | Duration leakage fix: replace post-amendment end date computation with parsed "Duración del contrato" text field |
| FEAT-08 | System excludes all post-execution variables from feature vectors | Re-verification: "Fecha de Fin del Contrato" is post-amendment (leaky), must be removed from schema entirely |
</phase_requirements>

## Duration Leakage Fix

### Current Implementation

**File:** `src/sip_engine/features/category_b.py` lines 72-92

```python
# Current (LEAKY) — uses post-amendment end date
fin_date = _to_date(row.get("Fecha de Fin del Contrato"))

# ---- 3. duracion_contrato_dias ----
if inicio_date is not None and fin_date is not None:
    duracion_contrato_dias = (fin_date - inicio_date).days
else:
    duracion_contrato_dias = float("nan")
```

The function signature documents `"Fecha de Fin del Contrato"` as a required key (line 58). The computed duration reflects post-amendment end dates — if a contract was extended by 6 months, this captures the extended duration, not the original.

### Required Changes

**Replace** the `fin_date` computation in `category_b.py` with a new `_parse_duracion_contrato()` function that parses the "Duración del contrato" text field.

The new code should:
1. Read `row.get("Duración del contrato")` instead of `row.get("Fecha de Fin del Contrato")`
2. Parse the text format into days using the parsing rules below
3. Return NaN for unparseable/missing values
4. Remove `fin_date` entirely from the function (no longer needed)
5. Update the docstring to reflect the new data source

### Duration Column Format (Empirically Verified)

**Column:** "Duración del contrato" at CSV index 70 (0-based) in `contratos_SECOP.csv`

| Format | Example | Count | Percentage | Conversion |
|--------|---------|-------|------------|------------|
| `N Dia(s)` | "143 Dia(s)" | 194,706 | 56.98% | N (direct days) |
| `N Mes(es)` | "3 Mes(es)" | 127,563 | 37.33% | N × 30 |
| `No definido` | "No definido" | 17,647 | 5.16% | NaN |
| `Dia(s)` (bare) | "Dia(s)" | 13,960 | 4.09%* | NaN (no number) |
| `N Año(s)` | "5 Año(s)" | 1,341 | 0.39% | N × 365 |
| `N Hora(s)` | "4 Hora(s)" | 247 | 0.07% | N ÷ 24 (float → round) |
| `N Semana(s)` | "6 Semana(s)" | 218 | 0.06% | N × 7 |

*Note: "Dia(s)" without a number is a subset of the "N Dia(s)" count above (13,960 of the 194,706 reported as Dia(s)). Total is 341,727 rows.

**1,317 unique values** exist but ALL follow the `"N Unit"` pattern or `"No definido"` or bare `"Dia(s)"`. No edge cases outside these patterns were found.

### Parsing Algorithm (Recommended)

```python
import re
import math
import logging

logger = logging.getLogger(__name__)

_DURACION_PATTERN = re.compile(r"^(\d+)\s+(Dia|Mes|Año|Semana|Hora)\((?:s|es)\)$", re.IGNORECASE)

_UNIT_TO_DAYS = {
    "dia": 1,
    "mes": 30,
    "año": 365,
    "semana": 7,
    "hora": 1 / 24,
}

def _parse_duracion_contrato(raw_value) -> float:
    """Parse 'Duración del contrato' text field to days.
    
    Returns float('nan') for 'No definido', bare 'Dia(s)', empty, or unknown formats.
    """
    if raw_value is None:
        return float("nan")
    text = str(raw_value).strip()
    if not text or text.lower() == "no definido":
        return float("nan")
    
    match = _DURACION_PATTERN.match(text)
    if match:
        number = int(match.group(1))
        unit = match.group(2).lower()
        multiplier = _UNIT_TO_DAYS.get(unit, None)
        if multiplier is not None:
            result = number * multiplier
            return round(result) if isinstance(result, float) else result
    
    # Bare "Dia(s)" without number — treat as NaN
    if text.lower().startswith("dia"):
        return float("nan")
    
    logger.warning("Unknown duration format: %r — returning NaN", text)
    return float("nan")
```

### Edge Cases

| Case | Count | Handling | Rationale |
|------|-------|----------|-----------|
| "No definido" | 17,647 (5.16%) | NaN | XGBoost handles natively (CONTEXT.md decision) |
| "Dia(s)" (no number) | 13,960 (4.09%) | NaN | Missing number means unknown duration |
| "4 Hora(s)" | 247 (0.07%) | 4/24 ≈ 0 days | Round to nearest integer |
| Empty string | ~0 | NaN | Standard null handling |
| NaN/None | — | NaN | Standard null handling |

**Total NaN rate after fix:** ~9.3% (No definido + bare Dia(s)) — acceptable for XGBoost.

## M2 Label Bug Fix

### Current Implementation

**File:** `src/sip_engine/data/label_builder.py` lines 37-38, 71-125

```python
M2_TIPOS: set[str] = {"EXTENSION"}
```

The `_build_m1_m2_sets()` function streams adiciones.csv and checks `tipo.upper()` against `M2_TIPOS`. Only 391 rows in adiciones.csv have tipo="EXTENSION", and after filtering to valid contratos IDs, only **19 contracts** get M2=1.

**File:** `src/sip_engine/data/label_builder.py` lines 45-68 (`_load_contratos_base`)

```python
def _load_contratos_base() -> pd.DataFrame:
    needed_cols = ["ID Contrato", "TipoDocProveedor", "Documento Proveedor"]
    chunks: list[pd.DataFrame] = []
    for chunk in load_contratos():
        chunks.append(chunk[needed_cols])
    # ...
```

Currently only loads 3 columns from contratos. Does NOT load "Dias adicionados".

### Required Changes

1. **Add "Dias adicionados" to `needed_cols`** in `_load_contratos_base()`:
   ```python
   needed_cols = ["ID Contrato", "TipoDocProveedor", "Documento Proveedor", "Dias adicionados"]
   ```

2. **After `_build_m1_m2_sets()` returns, union additional M2 positives from contratos:**
   ```python
   m1_contracts, m2_contracts = _build_m1_m2_sets(contratos_ids)
   
   # Add M2 positives from "Dias adicionados" column in contratos
   dias_col = df["Dias adicionados"]
   # Handle comma thousands separators (e.g., "1,826")
   dias_numeric = pd.to_numeric(
       dias_col.astype(str).str.replace(",", "", regex=False),
       errors="coerce"
   ).fillna(0)
   dias_m2_ids = set(df.loc[dias_numeric != 0, "ID Contrato"].tolist())
   m2_contracts = m2_contracts | dias_m2_ids
   
   logger.info("M2 from Dias adicionados: %d additional contracts", len(dias_m2_ids - m2_contracts_before))
   ```

3. **Keep M2_TIPOS constant** — the EXTENSION source still contributes (even if only 19 rows), maintaining the Vigia OR logic.

### "Dias adicionados" Column Data (Empirically Verified)

**Column:** "Dias adicionados" at CSV index 48 (0-based) in `contratos_SECOP.csv`

| Category | Count | Notes |
|----------|-------|-------|
| Zero (0) | 302,551 | M2=0 |
| Positive (non-zero numeric) | 39,153 | M2=1 |
| Negative | 0 | None found |
| Non-numeric (comma thousands) | 18 | E.g., "1,826", "1,095" — all are large positive numbers |
| Total non-zero | 39,153 + 18 = **39,171** | After comma handling, all become positive |

**Expected M2 label distribution after fix:** ~39,171 positives (11.46%) — aligns with Vigia reference of ~18.7% on their Bogotá-only dataset.

### Non-Numeric Values (18 rows)

All use comma as thousands separator — `pd.to_numeric(str.replace(",",""), errors="coerce")` handles these correctly:
```
"1,826", "1,095", "1,096", "1,212", "1,461", "730,491", "1,827",
"1,277", "1,861", "1,461", "1,307", "1,461", "3,652", "1,825",
"1,979", "1,827", "1,460", "2,191"
```

Note: "730,491" could be 730491 days (data error) or 730.491 (unlikely — field is integer days). Treating as 730491 is safe since any non-zero value → M2=1.

### Expected Impact

| Metric | Before Fix | After Fix |
|--------|-----------|-----------|
| M2 positives | 19 (0.006%) | ~39,171 (11.46%) |
| M2 AUC-ROC | 0.996 (meaningless) | Expected ~0.5-0.8 (realistic) |
| M2 test positives | ~6 | ~11,751 (30% of 39,171) |
| `num_retrasos_previos` | Always ~0 | Meaningful per-provider history |

## Schema Changes

**File:** `src/sip_engine/data/schemas.py`

### CONTRATOS_USECOLS Changes

| Action | Column | Reason |
|--------|--------|--------|
| **ADD** | `"Duración del contrato"` | Duration leakage fix — new source for duracion_contrato_dias |
| **ADD** | `"Dias adicionados"` | M2 label fix — primary source for delay labels |
| **REMOVE** | `"Fecha de Fin del Contrato"` | Prevent accidental re-use of post-amendment end date |

### CONTRATOS_DTYPE Changes

| Action | Column | Type | Reason |
|--------|--------|------|--------|
| **ADD** | `"Duración del contrato"` | `str` | Text field ("143 Dia(s)"), not numeric |
| **ADD** | `"Dias adicionados"` | `str` | Has comma thousands separators, needs pre-processing |

### SUSPENSIONES_USECOLS

"Fecha de Fin del Contrato" also appears in SUSPENSIONES_USECOLS (line 238). This is a different file (suspensiones_contratos.csv) and is NOT used in feature engineering — **no change needed** there.

## Cascading Impacts

### Provider History (`provider_history.py`)

**Impact level:** HIGH — M2 fix changes label distribution, which feeds into provider history index.

- `build_provider_history_index()` loads `labels.parquet` and joins M1/M2 on `id_contrato` (lines 99-108)
- After M2 label fix, the `m2` array in provider history changes from mostly-zeros to ~11.5% ones
- `lookup_provider_history()` computes `num_retrasos_previos = sum(m2_flags[:cutoff])` (line 326)
- **Before fix:** `num_retrasos_previos` was always ~0 (only 19 M2 positives total)
- **After fix:** `num_retrasos_previos` becomes meaningful — providers with delay history will have non-zero counts
- **No code change needed** in `provider_history.py` — it reads M2 from labels.parquet, which will be correct after rebuild

### IRIC Calculator Key Mismatch (Phase 11 — OUT OF SCOPE)

`calculator.py:340` reads `provider_history.get("num_retrasos", 0)` but provider_history returns `"num_retrasos_previos"`. This means IRIC component 10 is always 0 regardless of M2 labels. This is a separate bug tracked in Phase 11 — **not fixed in Phase 10**.

However, after Phase 10's M2 fix, `category_c.py:88` correctly reads `"num_retrasos_previos"` from provider_history, so the **feature** `num_retrasos_previos` in the XGBoost model WILL be correct.

### Feature Pipeline (`pipeline.py`)

**No code changes needed.** The pipeline calls:
1. `compute_category_b(row_dict, ...)` — which will use the updated parsing logic
2. The `row_dict` comes from `load_contratos()` which uses `CONTRATOS_USECOLS` — adding "Duración del contrato" there is sufficient

The `FEATURE_COLUMNS` list (line 62-84) already has `"duracion_contrato_dias"` — no change needed.

`REQUIRED_FIELDS` (line 87-91) currently includes `"Valor del Contrato"`, `"Fecha de Firma"`, `"Tipo de Contrato"`, `"Modalidad de Contratacion"` — does NOT include "Fecha de Fin del Contrato", so removing it from USECOLS doesn't affect drop logic.

### Online Inference (`compute_features()`)

`compute_features()` (line 503) calls `compute_category_b(contract_row, ...)`. The `contract_row` dict must now include `"Duración del contrato"` instead of `"Fecha de Fin del Contrato"`. Update the docstring accordingly. The analyzer module (`analyzer.py`) that calls `compute_features()` must also be updated to pass the right key.

### Encoding Mappings / Category D (IRIC)

**No changes needed.** Duration is numeric (not categorical), so encoding_mappings.json is unaffected. IRIC scores use provider_history and thresholds — no direct dependency on duration.

## Tests Requiring Updates

### `tests/conftest.py`
- **Line 44:** CSV header includes `"Fecha de Fin del Contrato"` — must be replaced with `"Duración del contrato"` and `"Dias adicionados"`
- **Line 165:** Missing column fixture references `CONTRATOS_USECOLS[:-1]` which was "Fecha de Fin del Contrato" — update reference or fixture logic

### `tests/test_features.py` (76 tests, ~25 references to "Fecha de Fin del Contrato")
- **Lines 94, 1291:** CSV header strings in fixture functions — update
- **Lines 625, 638, 651, 659, 672, 686, 699, 716, 734, 753, 775, 796, 809, 825, 848, 1573:** All `compute_category_b()` test calls pass `"Fecha de Fin del Contrato"` in row dict — must change to `"Duración del contrato"` with appropriate text values
- **Line 665-676 (`test_duracion_contrato_dias`):** Currently tests `(Fecha de Fin - Fecha de Inicio).days` — must be rewritten to test duration text parsing
- **New tests needed:** Duration parsing edge cases (Dia(s), Mes(es), Año(s), Hora(s), Semana(s), No definido, bare Dia(s), unknown format)

### `tests/test_labels.py` (30+ tests)
- **Line 46:** CSV header includes "Fecha de Fin del Contrato" — update
- **Line 159-161:** `test_m2_tipos_constant()` asserts `M2_TIPOS == {"EXTENSION"}` — still correct but may want to add M2 Dias adicionados test
- **New tests needed:** M2 labeling from "Dias adicionados" column (non-zero → M2=1, zero → M2=0, comma-separated values, NaN handling)

### `tests/test_loaders.py`
- Grep shows no direct "Fecha de Fin" reference, but `tiny_contratos_csv` in conftest.py is shared — updating conftest.py header is sufficient

### `tests/test_system.py`
- May reference contratos fixture — check for "Fecha de Fin" references

## Valor del Contrato Analysis (CONTEXT.md Verification)

**Empirical finding:** Contracts WITH M1 value amendments have mean Valor=$849M vs. WITHOUT mean Valor=$374M (~2.3x ratio). Median ratio is $35.4M vs. $19.3M (~1.8x).

**Assessment:** This difference is **consistent with legitimate correlation** — larger contracts are more likely to have value amendments because: (a) they span longer periods with more scope changes, (b) they're more visible and formally amended vs. informally adjusted, (c) the Vigia notebooks used "Valor del Contrato" directly as a feature.

**Recommendation:** Keep "Valor del Contrato" as-is. The CONTEXT.md decision stands: "Likely NOT leaky." The field represents the at-signing value in the SECOP database schema (amendments are tracked separately in adiciones.csv). No code change needed.

## Artifact Versioning

### Current Artifact Structure

```
artifacts/
├── evaluation/          # M1-M4 eval reports (JSON, CSV, MD, images)
│   ├── M1/             # M1_eval.json, M1_eval.csv, M1_eval.md, images/
│   ├── M2/             # Same structure
│   ├── M3/
│   ├── M4/
│   ├── summary.csv
│   └── summary.json
├── features/
│   ├── encoding_mappings.json
│   ├── features.parquet
│   └── provider_history_index.pkl
├── iric/
│   ├── iric_scores.parquet
│   └── iric_thresholds.json
├── labels/
│   └── labels.parquet
├── models/
│   ├── M1/              # model.pkl, feature_registry.json, test_data.parquet, training_report.json
│   ├── M2/              # Same structure
│   ├── M3/
│   └── M4/
└── rcac/
    ├── rcac.pkl
    └── rcac_bad_rows.csv
```

### Backup Plan

**Strategy:** Create `artifacts/v1_baseline/` and copy (not move) all artifacts into it. This preserves v1 for comparison while allowing the pipeline to overwrite `artifacts/` in-place.

**Git handling:** `artifacts/` is gitignored with `!artifacts/**/.gitkeep`. The CONTEXT.md says to commit v1_baseline. This requires:
1. Add a `.gitignore` exception: `!artifacts/v1_baseline/**`
2. Or create a separate `artifacts/v1_baseline/` with force-add

**Implementation:** A Python utility function (or CLI command) that:
```python
import shutil
from pathlib import Path

def backup_v1_artifacts():
    src = Path("artifacts")
    dst = src / "v1_baseline"
    if dst.exists():
        raise FileExistsError(f"v1_baseline already exists at {dst}")
    dst.mkdir()
    for subdir in ["evaluation", "features", "iric", "labels", "models"]:
        src_sub = src / subdir
        if src_sub.exists():
            shutil.copytree(src_sub, dst / subdir)
    # Don't copy rcac — it doesn't change
```

**Size estimate:** ~200MB total (models dominate). Acceptable for git LFS or direct commit depending on project policy. Since artifacts/ is gitignored, the user would need to explicitly `git add -f artifacts/v1_baseline/` or modify .gitignore.

## Comparison Reporting

### Template Design

A comparison script/module that:
1. Reads `artifacts/v1_baseline/evaluation/summary.json` (v1 metrics)
2. Reads `artifacts/evaluation/summary.json` (v2 metrics after re-run)
3. Computes deltas for all metrics
4. Reads feature importance from training reports
5. Outputs both `comparison.md` (human-readable) and `comparison.json` (machine-readable)

### V1 Baseline Metrics (from current `summary.json`)

| Model | AUC-ROC | Brier | MAP@100 | MAP@1000 | Positive Rate |
|-------|---------|-------|---------|----------|---------------|
| M1 | 0.851 | 0.060 | 0.958 | 0.726 | 3.67% |
| M2 | 0.996 | 0.036 | 0.100 | 0.030 | 0.006% |
| M3 | 0.705 | 0.047 | 0.000 | 0.009 | 0.056% |
| M4 | 0.707 | 0.011 | 0.000 | 0.002 | 0.012% |

### Expected Changes After Fix

| Model | Expected AUC | Why |
|-------|-------------|-----|
| M1 | ~0.70-0.78 | Duration leakage was #1 feature; removing it drops AUC by ~7-15pp (Gallego et al. achieved ~0.78 max) |
| M2 | ~0.50-0.80 | Currently meaningless (6 test positives). With ~11K test positives, realistic discrimination |
| M3 | ~0.70 (stable) | No label or feature change |
| M4 | ~0.71 (stable) | No label or feature change |

### Comparison Report Template Structure

```markdown
# SIP Engine v1 → v2 Comparison Report

## Summary
- Duration leakage: FIXED (Duración del contrato replaces Fecha de Fin)
- M2 labels: FIXED (Dias adicionados added, {v2_m2_positives} positives vs 19)

## Metrics Comparison
| Model | Metric | v1 | v2 | Delta |
|-------|--------|----|----|-------|
...

## Feature Importance Shift
| Model | Feature | v1 Rank | v2 Rank | Direction |
|-------|---------|---------|---------|-----------|
...

## Label Distribution
| Model | v1 Positives | v1 Rate | v2 Positives | v2 Rate |
...
```

## File Change Map

### Core Code Changes

| File | Change | Scope |
|------|--------|-------|
| `src/sip_engine/data/schemas.py` | Add "Duración del contrato" + "Dias adicionados" to CONTRATOS_USECOLS; add both to CONTRATOS_DTYPE as `str`; remove "Fecha de Fin del Contrato" from CONTRATOS_USECOLS | Lines 24-57 |
| `src/sip_engine/features/category_b.py` | Add `_parse_duracion_contrato()` function; replace `fin_date` computation with duration parsing; remove "Fecha de Fin del Contrato" from docstring; update `compute_category_b()` to read "Duración del contrato" | Lines 47-92, new function ~20 lines |
| `src/sip_engine/data/label_builder.py` | Update `_load_contratos_base()` to include "Dias adicionados"; add M2 labeling from Dias adicionados after `_build_m1_m2_sets()`; update build_labels() docstring | Lines 56, 285-293, docstring |

### New Files

| File | Purpose |
|------|---------|
| `src/sip_engine/evaluation/comparison.py` | v1 vs v2 metrics comparison template generator |

### Test Changes

| File | Change | Lines Affected |
|------|--------|---------------|
| `tests/conftest.py` | Update `tiny_contratos_csv` header: remove "Fecha de Fin del Contrato", add "Duración del contrato" and "Dias adicionados"; update `missing_column_csv` fixture | Lines 44, 165 |
| `tests/test_features.py` | Update all 20+ category_b test row dicts: replace "Fecha de Fin del Contrato" with "Duración del contrato"; rewrite `test_duracion_contrato_dias()`; add new duration parsing tests; update CSV headers in integration fixtures | ~25 locations |
| `tests/test_labels.py` | Update CSV header; add tests for M2 from Dias adicionados; update `_make_contrato_row()` helper | Lines 46, new tests |

### Artifact/Config Changes

| File | Change |
|------|--------|
| `.gitignore` | Add exception for `!artifacts/v1_baseline/` |
| `artifacts/v1_baseline/` | Backup of all v1 artifacts (created by backup utility) |

### Files That DON'T Need Changes (Verified)

| File | Why No Change |
|------|---------------|
| `pipeline.py` | Reads from `row_dict` which comes from `load_contratos()` (schema-driven); calls `compute_category_b()` which is updated |
| `provider_history.py` | Reads M2 from labels.parquet (schema-driven); no code change, just rebuild |
| `category_a.py` | No dependency on duration or M2 |
| `category_c.py` | Reads `num_retrasos_previos` from provider_history dict — correct key already |
| `encoding.py` | Duration is numeric, not categorical |
| `loaders.py` | Uses `CONTRATOS_USECOLS` from schemas.py — no direct column references |
| IRIC modules | Phase 11 scope for key mismatch |

## Risk Assessment

### Risk 1: Duration Parsing Errors
**What could go wrong:** Unknown format in production data that wasn't in our sample.
**Mitigation:** Log warning + return NaN for unknown formats. XGBoost handles NaN natively. The 1,317 unique values were exhaustively verified — all match the 6 known patterns.
**Probability:** LOW — no edge cases found.

### Risk 2: M2 Label Explosion Destabilizes Models
**What could go wrong:** Going from 19→39K M2 positives changes the entire M2 model behavior. The HP search may need different parameters.
**Mitigation:** Same HP search config (200 iterations, StratifiedKFold 5) ensures fair comparison. Scale_pos_weight and upsampling strategies will automatically adapt to new class ratio.
**Probability:** LOW — the M2 model was essentially untrained before.

### Risk 3: Provider History Rebuild Cascade
**What could go wrong:** Rebuilding labels → provider_history → features → models is a full pipeline re-execution. If any intermediate step fails, all downstream artifacts are stale.
**Mitigation:** Phase 10 only changes code. User runs the full pipeline sequentially: build-labels → build-features → train → evaluate → shap/cri. Each step checks for prerequisites.
**Probability:** LOW — pipeline already handles sequential dependencies.

### Risk 4: Test Fixture Header Changes Break Other Tests
**What could go wrong:** Updating conftest.py CSV headers affects all tests that use `tiny_contratos_csv`.
**Mitigation:** The conftest.py header change must be coordinated with all test files that create inline CSV fixtures. The CSV data rows in fixtures also need updating (adding dummy duration and dias_adicionados values).
**Probability:** MEDIUM — manual coordination across multiple test files.

### Risk 5: Artifacts Backup Size
**What could go wrong:** Model .pkl files and parquet files could be large; committing to git bloats repo.
**Mitigation:** Evaluate total v1_baseline size. If >50MB, use git LFS or keep backup as a local-only directory (not committed). CONTEXT.md says "commit to git" but the gitignore already excludes artifacts/.
**Probability:** LOW — models are typically <10MB each with XGBoost.

### Risk 6: "Valor del Contrato" Actually IS Leaky
**What could go wrong:** If the CSV field is updated when amendments occur, the model still has a leaky feature.
**Mitigation:** CONTEXT.md decision: "Likely NOT leaky." The empirical test shows correlation but not proof of leakage. Vigia used it directly. If future evidence confirms leakage, it's a separate fix. No action in Phase 10 per CONTEXT.md.
**Probability:** LOW — SECOP schema stores original value; amendments tracked separately.

## Sources

### Primary (HIGH confidence)
- **Empirical data analysis:** contratos_SECOP.csv (341,727 rows) — column indices, format distributions, value counts all verified directly
- **Source code:** All 10 source files read in full (category_b.py, label_builder.py, schemas.py, provider_history.py, pipeline.py, category_a.py, category_c.py, loaders.py, conftest.py, test_features.py)
- **comparison.md:** Project-internal analysis of Vigia vs. SIP differences

### Secondary (MEDIUM confidence)
- **CONTEXT.md decisions:** User-locked implementation choices (parsing rules, artifact strategy)
- **ROADMAP.md:** Phase 10 success criteria and requirements mapping

## Metadata

**Confidence breakdown:**
- Duration fix: HIGH — empirically verified column format, code changes precisely scoped
- M2 label fix: HIGH — column data verified, expected counts match Vigia reference
- Schema changes: HIGH — exact column names verified against CSV headers
- Test changes: MEDIUM — broad scope (~25 locations), may discover additional references during implementation
- Artifact versioning: MEDIUM — git handling needs careful .gitignore management

**Research date:** 2026-03-02
**Valid until:** Indefinite — data and code changes are deterministic
