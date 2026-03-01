# Phase 4: Label Construction — Research

**Researched:** 2026-03-01
**Researcher:** gsd-phase-researcher
**Phase:** 04-label-construction
**Requirements:** DATA-11, DATA-12, DATA-13

---

## 1. Critical Discovery: adiciones.csv tipo Values Are Not What the CONTEXT.md Says

This is the most important finding of this research. The CONTEXT.md states:

> M1 tipos = {"Adición en el valor", "Reducción en el valor"}
> M2 tipos = {"Extensión"}

**The actual tipo values in adiciones.csv are ALL CAPS and use different spellings:**

| Exact tipo string | Count (full file) | Count (matched to contratos) | Classification |
|---|---|---|---|
| `'MODIFICACION GENERAL'` | 6,659,652 | 404,055 | DISCARD |
| `'CONCLUSION'` | 3,847,600 | 230,077 | DISCARD |
| `'No definido'` | 2,945,127 | 178,166 | DISCARD |
| `'ADICION EN EL VALOR'` | 355,041 | 21,974 | **M1=1** |
| `'REACTIVACIoN'` | 192,413 | 11,652 | DISCARD |
| `'CESION'` | 185,238 | 10,724 | DISCARD |
| `'SUSPENSIoN'` | 169,475 | 10,593 | DISCARD |
| `'EXTENSION'` | 391 | 23 | **M2=1** |
| `'REDUCCION EN EL VALOR'` | 145 | 6 | **M1=1** |
| `'EXPIRACION'` | 1 | 0 | DISCARD |

**Key facts:**
- `'ADICION EN EL VALOR'` — not `'Adición en el valor'`. ALL CAPS, no accent on 'o'.
- `'REDUCCION EN EL VALOR'` — not `'Reducción en el valor'`. ALL CAPS.
- `'EXTENSION'` — not `'Extensión'`. ALL CAPS, no accent.
- `'REACTIVACIoN'`, `'SUSPENSIoN'` have a lowercase `'o'` (likely an encoding artifact) — NOT M2.
- `'No definido'` is mixed case — must handle case-insensitively.

**Matching must be case-insensitive** (`tipo.strip().upper()`) to handle `'No definido'` and any future variants. The sets to use after `.strip().upper()`:
- M1_TIPOS = `{"ADICION EN EL VALOR", "REDUCCION EN EL VALOR"}`
- M2_TIPOS = `{"EXTENSION"}`

---

## 2. Label Prevalence — Empirical Counts

All counts verified empirically on the actual production dataset.

### 2.1 M1 and M2 (from adiciones.csv)

| Metric | Value |
|---|---|
| Total adiciones rows | 14,355,083 |
| Rows matched to a known contratos ID | 867,270 (6.0%) |
| Orphan adiciones rows (no contratos match) | 13,487,813 (94.0%) |
| Total contratos (unique ID Contrato) | 340,479 |
| Contracts with ≥1 adicion row | 202,762 (59.6%) |
| Contracts with no adicion row (M1=0, M2=0) | 137,717 (40.4%) |
| **M1=1 contracts** (≥1 value amendment) | **11,536 (3.4%)** |
| **M2=1 contracts** (≥1 time extension) | **19 (0.006%)** |
| Both M1=1 and M2=1 | 7 |

**M2 is extremely sparse (19 contracts = 0.006%).** This is because `'EXTENSION'` is almost absent from matched rows (23 matched rows across 19 contracts). The planner must note this in the label output — M2 may not be trainable with the current data, but the pipeline should still construct the label correctly.

### 2.2 M3 (from boletines.csv)

| Metric | Value |
|---|---|
| boletines total rows | 10,817 |
| Unique (tipo, num) after normalization | 8,321 |
| contratos rows with malformed/null provider ID | 10,659 (3.1%) |
| **M3=1 contracts** (provider in boletines) | **187 (0.05%)** |

boletines.csv has only `'CC'` (9,323 rows) and `'NIT'` (1,458 rows) — already normalized. No mapping needed. M3 is also very sparse.

**Note:** CONTEXT.md explicitly states boletines.csv is currently incomplete. At 10,817 rows it represents only the first batch of records. The pipeline must log a runtime warning: "M3 labels are based on an incomplete boletines.csv snapshot — not ready for production training."

### 2.3 M4 (from RCAC lookup)

The RCAC pkl is not yet built (no rcac.pkl at `artifacts/rcac/rcac.pkl`). However, from the Phase 3 research:
- RCAC has ~29,134 unique identities across 5 sources
- `en_boletines` alone already provides M3-equivalent data
- M4 includes ALL RCAC sources (boletines + SIRI + resp_fiscales + multas + colusiones)
- M4 will be higher prevalence than M3 alone (perhaps 2-5% of contracts based on RCAC size relative to contratos)

RCAC must be built (`python -m sip_engine build-rcac`) before Phase 4 can compute M4 labels. The label builder should check for the pkl and raise a clear error if it is missing.

---

## 3. Join Key Analysis

### 3.1 adiciones ↔ contratos join

- adiciones `id_contrato` format: `'CO1.PCCNTR.XXXXXX'` — matches contratos `'ID Contrato'` exactly.
- No null `id_contrato` in adiciones (0 null values confirmed).
- 94.0% of adiciones rows are orphans (no matching contratos). These must be logged and silently discarded.

**Root cause of 94% orphan rate:** adiciones.csv is a platform-wide log covering ALL SECOP contracts ever registered, while contratos.csv is a filtered dataset of actively managed contracts. The join correctly restricts to known contracts.

### 3.2 contratos ↔ boletines join (M3)

- contratos provider columns: `TipoDocProveedor` (e.g., `'Cédula de Ciudadanía'`, `'NIT'`) and `'Documento Proveedor'` (raw digit string)
- boletines columns: `'tipo de documento'` (`'CC'` or `'NIT'`) and `'numero de documento'` (raw digit string)
- Normalization: contratos `TipoDocProveedor` is raw (accented, mixed case) — must pass through `normalize_tipo()` from rcac_builder. boletines already uses `CC`/`NIT` (no normalization needed, but can be passed through normalize_tipo safely).
- Both document numbers must be passed through `normalize_numero()` before comparison.
- **The lookup is: normalize(contratos tipo, num) → check against boletines set.**
- Use a prebuilt set of `(tipo_norm, num_norm)` tuples from boletines for O(1) per-contract lookup.

### 3.3 contratos ↔ RCAC lookup (M4)

- Exact same approach: normalize contratos `TipoDocProveedor` → `normalize_tipo()`, normalize `Documento Proveedor` → `normalize_numero()`, then call `rcac_lookup(tipo_norm, num_norm)`.
- `rcac_lookup()` already normalizes internally — can pass raw contratos values directly per Phase 3 design.

---

## 4. contratos.csv Structural Issues

### 4.1 Duplicate rows (972 contracts appear 2-3 times)

341,727 rows but only 340,479 unique `ID Contrato` values. 972 contracts have 2-3 identical rows (same provider, same value — exact duplicates). The label builder must deduplicate before emitting the labeled dataset.

**Strategy:** `df.drop_duplicates(subset=['ID Contrato'], keep='first')` after loading contratos. The provider fields are identical across duplicate rows (confirmed empirically).

### 4.2 Missing/malformed provider IDs

10,659 rows (3.1%) have null or malformed `Documento Proveedor` after normalization. Per CONTEXT.md decision: these get `M3=null` and `M4=null` (excluded from training for those models). They still get M1 and M2 labels (those use the contract ID, not the provider ID).

### 4.3 `TipoDocProveedor` value distribution

| Value | Count (first 100k) | normalize_tipo() result |
|---|---|---|
| `'Cédula de Ciudadanía'` | 80,704 | `CC` |
| `'NIT'` | 15,985 | `NIT` |
| `'No Definido'` | 2,937 | `OTRO` |
| `'Otro'` | 221 | `OTRO` |
| `'Cédula de Extranjería'` | 119 | `CE` |
| `'Permiso por Protección Temporal'` | 18 | `OTRO` |
| `'Pasaporte'` | 7 | `PASAPORTE` |
| `'Tarjeta de Identidad'` | 3 | `OTRO` |
| Others | small | `OTRO` |

Providers classified as `OTRO` will fail to match in boletines (which has only CC/NIT) and may fail to match in RCAC. These are treated as: valid ID but no match → M3=0, M4=0.

---

## 5. Memory Strategy for adiciones.csv Processing

adiciones.csv is **14.35 million rows (~4GB)** — NOT tiny as the schema comment incorrectly states. Chunked streaming is mandatory.

**Two-pass strategy (recommended):**

**Pass 1 — Build label sets:**
Stream adiciones.csv chunk by chunk. For each chunk:
1. Filter rows where `id_contrato` is in the contratos ID set (pre-loaded as a Python `set` — 340k strings ≈ 7MB in memory)
2. For matched rows, collect `id_contrato` into two sets: `m1_contracts` and `m2_contracts` based on tipo
3. Count orphans for diagnostics

**Pass 2 — Annotate contratos:**
Load contratos (341k rows, manageable in memory at ~50MB with selected columns), deduplicate by ID Contrato, then:
1. Add `M1 = id_contrato.isin(m1_contracts).astype(int)` — where nulls come from missing contract IDs
2. Add `M2 = id_contrato.isin(m2_contracts).astype(int)`
3. Add `M3 = provider (tipo, num) in boletines_set` — prebuilt set from boletines
4. Add `M4 = rcac_lookup(tipo, num) is not None` — calls into RCAC pkl

**Memory estimate:**
- contratos DataFrame (selected cols): ~50MB
- m1_contracts set (≤11,536 strings × 20 bytes): <1MB
- m2_contracts set (≤19 strings): negligible
- boletines set (8,321 tuples): negligible
- RCAC index (29k records): ~5MB
- Peak memory: well under 500MB total

---

## 6. Output Artifact Design

### 6.1 What Phase 5 needs

Phase 5 (Feature Engineering) needs the labeled contratos dataset to:
- Join feature vectors with target labels for training
- Know which contracts are excluded per model (null labels)

### 6.2 Recommended output format

Output: `artifacts/labels/labels.parquet`

Schema:
```
id_contrato: str              # CO1.PCCNTR.XXXXXX
M1: Int8 (nullable)           # 0, 1, or pd.NA
M2: Int8 (nullable)           # 0, 1, or pd.NA
M3: Int8 (nullable)           # 0, 1, or pd.NA (null if provider ID malformed)
M4: Int8 (nullable)           # 0, 1, or pd.NA (null if provider ID malformed)
TipoDocProveedor_norm: str    # normalized tipo (for audit)
Documento Proveedor_norm: str # normalized num (for audit)
```

The contratos provider fields are included normalized for audit purposes. Parquet handles nullable integer types natively and is efficient for column access in Phase 5.

### 6.3 Settings additions needed

Add to `src/sip_engine/config/settings.py`:
```python
# In __post_init__:
self.artifacts_labels_dir = self.artifacts_dir / "labels"
self.labels_path = self.artifacts_labels_dir / "labels.parquet"
```

The `artifacts/labels/` directory needs a `.gitkeep` to be tracked.

### 6.4 CLI command: build-labels

Add `build-labels` subcommand to `python -m sip_engine`:
```
python -m sip_engine build-labels [--force]
```

Pattern mirrors `build-rcac`: dispatches to `build_labels(force=False)` in `label_builder.py`, returns path to labels.parquet.

---

## 7. Module Structure

New file: `src/sip_engine/data/label_builder.py`

```python
# Public API:
def build_labels(force: bool = False) -> Path:
    """Build M1/M2/M3/M4 labels for all contratos and save to labels.parquet.

    Returns:
        Path to labels.parquet.
    """

# Internal helpers:
def _load_contratos_base() -> pd.DataFrame:
    """Load contratos with provider + ID columns, deduplicate by ID Contrato."""

def _build_m1_m2_sets() -> tuple[set, set]:
    """Stream adiciones.csv and return (m1_contract_ids, m2_contract_ids) sets."""

def _build_boletines_set() -> set:
    """Load boletines.csv and return normalized (tipo, num) set for M3 lookup."""

def _compute_labels(contratos_df, m1_set, m2_set, boletines_set) -> pd.DataFrame:
    """Apply all 4 labels to contratos DataFrame. Returns labeled DataFrame."""
```

Export from `src/sip_engine/data/__init__.py`:
```python
from sip_engine.data.label_builder import build_labels
```

---

## 8. Normalization Reuse from Phase 3

The label builder imports directly from `rcac_builder.py`:
```python
from sip_engine.data.rcac_builder import normalize_tipo, normalize_numero, is_malformed
```

And uses `rcac_lookup` for M4:
```python
from sip_engine.data.rcac_lookup import rcac_lookup
```

**No new normalization code needed.** All document normalization is handled by Phase 3 utilities.

---

## 9. ADICIONES_USECOLS Schema Fix Required

`src/sip_engine/data/schemas.py` has an incorrect comment:

```python
# ---- adiciones.csv (5 cols, ~1.3k rows, tiny) ----
```

The actual file is **14.35 million rows (~4GB)**. The schema constants (`ADICIONES_USECOLS`, `ADICIONES_DTYPE`) are correct, but the comment must be corrected to prevent future confusion.

No dtype changes needed: `identificador` and `id_contrato` as `str` is correct. `tipo` should be added to dtype as `str` (it currently is not in `ADICIONES_DTYPE`). The `descripcion` column can remain without an explicit dtype (str is pandas default for object columns).

---

## 10. Diagnostics and Logging Requirements

Per CONTEXT.md, the builder must log:

1. **Orphan adiciones count:** `logger.info("Adiciones orphans: %d rows (%.1f%%) with no matching contratos ID", orphan_count, pct)`
2. **M1/M2 label summary:** `logger.info("M1: %d positive (%.1f%%), M2: %d positive (%.1f%%)", m1_count, m1_pct, m2_count, m2_pct)`
3. **Null label counts:** `logger.info("Null M1/M2 due to missing contract ID: %d", null_m1_count)`
4. **M3 label summary:** `logger.info("M3: %d positive (%.1f%%), %d null (malformed provider ID)", m3_count, m3_pct, null_m3_count)`
5. **M4 label summary:** `logger.info("M4: %d positive (%.1f%%), %d null (malformed provider ID)", m4_count, m4_pct, null_m4_count)`
6. **M2 sparsity warning:** `logger.warning("M2 has only %d positive examples — model may not be trainable", m2_count)`
7. **M3 incompleteness warning:** `logger.warning("boletines.csv is incomplete — M3 labels not suitable for production training")`

---

## 11. Testing Strategy

Tests use tmp_path fixtures (no real data), following Phase 2/3 pattern. Target: ~25-30 tests.

### test_label_builder.py

| Test | What it validates |
|---|---|
| `test_m1_tipo_matching_case_insensitive` | `'adicion en el valor'` triggers M1=1 |
| `test_m1_adicion_en_el_valor` | `'ADICION EN EL VALOR'` → M1=1 |
| `test_m1_reduccion_en_el_valor` | `'REDUCCION EN EL VALOR'` → M1=1 |
| `test_m2_extension` | `'EXTENSION'` → M2=1 |
| `test_m1_m2_both` | contract with both tipo values → M1=1, M2=1 |
| `test_discard_tipos` | `'MODIFICACION GENERAL'`, `'CONCLUSION'`, `'SUSPENSIoN'` → M1=0, M2=0 |
| `test_orphan_adiciones_ignored` | adicion with unknown id_contrato → logged, not counted |
| `test_no_adicion_zero_labels` | contract with no adiciones entry → M1=0, M2=0 |
| `test_m3_provider_in_boletines` | provider (tipo, num) in boletines set → M3=1 |
| `test_m3_provider_not_in_boletines` | unknown provider → M3=0 |
| `test_m3_null_for_malformed_provider` | empty/zero/short provider num → M3=null |
| `test_m4_provider_in_rcac` | provider found in RCAC → M4=1 |
| `test_m4_provider_not_in_rcac` | unknown provider → M4=0 |
| `test_m4_null_for_malformed_provider` | malformed provider → M4=null |
| `test_duplicate_contratos_rows_deduped` | 3 identical rows for one contract → 1 row in output |
| `test_build_labels_creates_parquet` | labels.parquet written at settings.labels_path |
| `test_build_labels_cache` | existing parquet reused when force=False |
| `test_build_labels_force` | force=True always rebuilds |
| `test_labels_parquet_schema` | output has id_contrato, M1, M2, M3, M4 columns |
| `test_m3_input_normalization` | raw `'Cédula de Ciudadanía'` + `'43.922.546'` normalized before M3 lookup |
| `test_m4_uses_rcac_lookup` | M4 calls rcac_lookup with normalized inputs |
| `test_null_contract_id` | contratos row with null ID Contrato → M1=null, M2=null |

---

## 12. Phase Split Recommendation

Phase 4 naturally splits into 2 plans:

**Plan 04-01: M1/M2 labels from adiciones.csv**
- `label_builder.py` with `build_labels()` skeleton + `_build_m1_m2_sets()` + `_load_contratos_base()`
- adiciones.csv streaming loop with orphan counting
- Settings additions (`artifacts_labels_dir`, `labels_path`)
- `artifacts/labels/.gitkeep` scaffold
- Schema comment fix
- Tests for M1/M2 construction (~12 tests)

**Plan 04-02: M3/M4 labels + CLI + exports**
- `_build_boletines_set()` + M3 label computation
- M4 via `rcac_lookup()`
- Parquet output with nullable Int8 types
- `build-labels` CLI subcommand
- `data/__init__.py` re-export of `build_labels`
- Remaining tests (~15 tests)

---

## 13. Open Questions for Planner

1. **M2 trainability warning:** With only 19 positive M2 examples, should the builder emit a `logger.error()` (not just warning) and potentially skip saving M2 labels, or always include M2 in the output and leave trainability to Phase 7?
   - **Recommendation:** Always include M2. Log a `logger.warning()`. Phase 7 will decide whether to train M2.

2. **Labels output format — parquet vs pkl:** Parquet is standard for tabular data with type metadata. However, Phase 5 may need to join on this. Is parquet acceptable, or should the output be a CSV for maximum compatibility?
   - **Recommendation:** Parquet. pandas reads it in seconds, and the nullable Int8 type (`pd.Int8Dtype()`) is critical for distinguishing null (missing provider) from 0 (no sanction found).

3. **Should `build_labels()` check that RCAC pkl exists before running, or should it fail gracefully mid-run?**
   - **Recommendation:** Check at startup (before streaming adiciones) and raise `FileNotFoundError` with a clear message: "RCAC index not found. Run `python -m sip_engine build-rcac` first."

4. **Should null M1/M2 (missing contract ID) be included in the output or excluded?**
   - Per CONTEXT.md: contracts with missing `id_contrato` → `M1=null`, `M2=null`. Since `id_contrato` in contratos IS the primary key, any null ID contract row should be dropped at deduplification (it cannot be joined anyway). In practice, all contratos rows have an ID Contrato.

5. **SCHEMA fix: should `tipo` be added to `ADICIONES_DTYPE`?**
   - **Recommendation:** Yes. Add `"tipo": str` to `ADICIONES_DTYPE`. This prevents any mixed-type parsing warnings.

---

## 14. Module Update Checklist

| File | Change |
|---|---|
| `src/sip_engine/config/settings.py` | Add `artifacts_labels_dir`, `labels_path` |
| `src/sip_engine/data/schemas.py` | Fix comment "~1.3k rows, tiny" → "~14.4M rows, 4GB". Add `"tipo": str` to ADICIONES_DTYPE |
| `src/sip_engine/data/label_builder.py` | New: `build_labels()`, helpers for M1/M2/M3/M4 |
| `src/sip_engine/data/__init__.py` | Re-export `build_labels` |
| `src/sip_engine/__main__.py` | Add `build-labels` subcommand dispatching to `build_labels()` |
| `artifacts/labels/.gitkeep` | Create for scaffold |
| `tests/test_labels.py` | New: all label construction tests (~25-30 tests) |

---

## 15. Empirical Summary Table

| Data Source | File | Rows | Used For |
|---|---|---|---|
| adiciones.csv | secopDatabases/ | 14,355,083 | M1, M2 labels |
| contratos_SECOP.csv | secopDatabases/ | 341,727 (340,479 unique) | Base dataset |
| boletines.csv | secopDatabases/ | 10,817 (8,321 unique pairs) | M3 labels (direct query) |
| rcac.pkl | artifacts/rcac/ | ~29,134 entries (est.) | M4 labels (RCAC lookup) |

| Label | Positive Rate | Source | Ready for Training? |
|---|---|---|---|
| M1 | 3.4% (11,536/340,479) | adiciones ADICION/REDUCCION tipos | Yes |
| M2 | 0.006% (19/340,479) | adiciones EXTENSION tipo | Possibly no (too sparse) |
| M3 | 0.05% (187/340,479) | boletines.csv direct | No (file incomplete) |
| M4 | ~1-5% (estimate) | RCAC pkl | Yes (once RCAC built) |

---

*Research complete. All 3 requirements (DATA-11, DATA-12, DATA-13) addressed.*
*Critical finding: adiciones.csv tipo values are all-caps and different from CONTEXT.md — matching must use `tipo.strip().upper()` with the corrected sets.*
*Critical finding: M2 has only 19 positive examples — planner must flag trainability concern.*
*Critical finding: adiciones.csv is 14.35M rows, not ~1.3k — chunked processing mandatory.*
