# Phase 3: RCAC Builder — Research

**Researched:** 2026-03-01
**Researcher:** gsd-phase-researcher
**Phase:** 03-rcac-builder
**Requirements:** DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-08, DATA-09

---

## 1. Source File Audit

All 6 RCAC sources confirmed accessible at their settings paths. Key empirical findings:

| Source | Path | Rows | Unique (tipo,num) | Type info | Notes |
|---|---|---|---|---|---|
| boletines | secopDatabases/boletines.csv | 10,817 | 8,319 | Explicit: CC / NIT | 36 rows with NaN tipo |
| sanciones_SIRI | Data/Propia/PACO/sanciones_SIRI_PACO.csv | 46,584 | 15,029 | ALL = "CÉDULA DE CIUDADANÍA" | No header, col[4]=tipo, col[5]=num |
| resp_fiscales | Data/Propia/PACO/responsabilidades_fiscales_PACO.csv | 5,961 | 5,062 | NONE — numeric only | "Tipo y Num Docuemento" is just a number |
| multas | Data/Propia/PACO/multas_SECOP_PACO.csv | 1,721 | 1,040 | NONE — numeric only | No header, col[5]=NIT sancionado |
| colusiones | Data/Propia/PACO/colusiones_en_contratacion_SIC.csv | 103 | 103 | "Tipo de Persona Sancionada" | Maps to NIT/CC |
| sanciones_penales | Data/Propia/PACO/sanciones_penales_FGN.csv | 3,902 | **NONE** | **NO individual IDs** | Geographic aggregate — see §2 |

**Total unique identities (5 sources, pre-normalization): ~29,134**

---

## 2. Critical Discovery: sanciones_penales Has No Person-Level IDs

`sanciones_penales_FGN.csv` contains only geographic/crime-type aggregate data:

```
id, DEPARTAMENTO, MUNICIPIO_ID, CODIGO_DANE_MUNICIPIO, mpio, TITULO, CAPITULO, ARTICULO, AÑO_ACTUACION
```

There is no `tipo_documento` or `numero_documento` column. This means `en_sanciones_penales` **cannot be derived by (tipo_doc, num_doc) lookup** against this file.

**Resolution for planner:** `en_sanciones_penales` must be `False` for all RCAC records built in Phase 3. The field is reserved for future data source integration (v2 or beyond, when person-level FGN data becomes available). This is a data quality limitation, not an implementation error. The builder should log a warning at build time.

---

## 3. Document Type Normalization (DATA-02)

### 3.1 tipo_documento Catalog

Target catalog: `CC`, `NIT`, `CE`, `PASAPORTE`, `OTRO`

Mapping table from raw source values:

| Raw value | Source | Normalized |
|---|---|---|
| `CÉDULA DE CIUDADANÍA` | SIRI | `CC` |
| `Cédula de Ciudadanía` | contratos | `CC` |
| `CC` | boletines | `CC` |
| `NIT` | boletines / contratos | `NIT` |
| `Cédula de Extranjería` | contratos | `CE` |
| `Pasaporte` | contratos | `PASAPORTE` |
| `Personas Jurídicas` / `Persona Jurídica` | colusiones | `NIT` |
| `Personas Naturales` / `Personas Naturales ` | colusiones | `CC` |
| `Tarjeta de Identidad` | contratos | `OTRO` |
| `Permiso por Protección Temporal` | contratos | `OTRO` |
| `Permiso especial de permanencia` | contratos | `OTRO` |
| `Registro Civil` | contratos | `OTRO` |
| `No Definido` / NaN | any | `OTRO` |

All mappings are case-insensitive after stripping. Unrecognized values map to `OTRO`.

### 3.2 Sources Without tipo_documento

**resp_fiscales and multas have NO tipo field.** They carry only a raw number.

Options evaluated:
- **Option A — Store as OTRO:** Consistent but causes false negatives when Phase 4/5 queries with `tipo=NIT` or `tipo=CC`. Not acceptable for a lookup-based system.
- **Option B — Infer from document length:** Heuristic. Colombian NITs are typically 9 digits; CCs are 4-10 digits. Overlap makes this imprecise.
- **Option C — Infer from name pattern:** Scan the name field (col_6 in multas, Responsable Fiscal in resp_fiscales) for company keywords (LTDA, SAS, S.A., COOPERATIVA, etc.) to distinguish NIT from CC.

**Recommendation for planner:** Use **Option C (name-based inference)** as primary, with **Option B (length-based)** as fallback:
1. If name contains company keywords → `NIT`
2. Else if normalized digit length ≥ 9 → `NIT`
3. Else → `CC`

This is an approximation. Accept residual false negatives (minority of misclassified records). Document as data quality limitation.

### 3.3 numero_documento Normalization

**Rule:** Strip all non-digit characters (`re.sub(r'[^\d]', '', s)`).

**Malformed detection** (reject from index, write to bad-rows log):
1. Result is empty after stripping
2. Result is all zeros (`'0000000'`)
3. Result length < 3 digits

**Examples verified:**
- `'900123456-1'` → `'9001234561'` (10 digits — NIT with check digit stripped of hyphen, digits concatenated)
- `'43.922.546'` → `'43922546'` (dots stripped)
- `'1.030.629.839'` → `'1030629839'` (CC with dots)
- `'CE 289910'` → `'289910'` (prefix stripped — short CE number)
- `'TIA820427KP7'` → `'8204277'` (letters stripped — foreign ID, effectively malformed semantically but passes length check)

**NIT check digit handling:** Stripping all non-digits means `'900123456-1'` becomes `'9001234561'` (10 chars), which differs from the pure NIT `'900123456'` (9 chars). Since the lookup query also goes through the same normalizer, this is consistent — **as long as Phase 4/5 always normalizes query inputs through the same function before calling `rcac_lookup()`**. This must be documented as a contract.

**Note on `TIA820427KP7`:** Exists in boletines as `tipo=NIT`. After digit-only stripping it becomes `'8204277'` (7 chars, passes min-length check). It will be stored as-is. Not ideal but consistent and auditable via bad_rows log.

---

## 4. Deduplication Strategy (DATA-03)

One flat record per unique `(tipo_documento, numero_documento)` pair after normalization.

**Record schema:**
```python
{
    "tipo_documento": str,          # normalized: CC/NIT/CE/PASAPORTE/OTRO
    "numero_documento": str,         # digits-only string
    "en_boletines": bool,
    "en_siri": bool,
    "en_resp_fiscales": bool,
    "en_multas_secop": bool,
    "en_colusiones": bool,
    "en_sanciones_penales": bool,   # always False in v1
    "num_fuentes_distintas": int,   # count of True boolean flags (1–6)
    "malformed": bool,              # True = excluded from lookup index
}
```

**`num_fuentes_distintas`** = count of distinct source flags set to True. Two SIRI rows for the same person → still 1 (counted once).

**Build process:**
1. Load each source → normalize tipo + num → tag with source flag
2. Collect all rows as a list of `(tipo_norm, num_norm, source_flag)` tuples
3. Groupby (tipo_norm, num_norm) → OR all source flags, count distinct
4. Apply malformed check → route to bad_rows log if malformed
5. Build index dict: `{(tipo, num): record_dict}`

---

## 5. Special Parsing Cases (DATA-04, DATA-05)

### 5.1 SIRI — headerless, positional columns (DATA-04)

**Confirmed empirically:** `col[4]` = tipo_documento, `col[5]` = numero_documento (0-indexed).

`load_paco_siri()` already handles this. SIRI contains only `"CÉDULA DE CIUDADANÍA"` values for tipo — maps uniformly to `CC`. No splitting needed; direct normalization.

### 5.2 resp_fiscales — combined field (DATA-05)

**Discovery:** "Tipo y Num Docuemento" is misleadingly named. Empirically it contains **only the numeric document number**, not a combined type+number string. There is no `CC:` or `NIT:` prefix. The column name in the spec says "combined" but the data is purely numeric.

**Consequence:** No splitting logic required. The "combined field parsing" requirement (DATA-05) reduces to: read the column as-is, apply the tipo inference heuristic (§3.2), and normalize the digits.

One anomaly found: `'TIA820427KP7'` (alphanumeric). Falls into malformed handling.

### 5.3 multas — headerless, col[5] is sanctioned NIT (DATA-01)

**Confirmed empirically:** `col[5]` (0-indexed) = NIT of sanctioned provider. `col[6]` = provider name (used for tipo inference).

`load_paco_multas()` already loads all 15 columns. Phase 3 builder reads `col_5` and `col_6` by column-name convention (`col_5`, `col_6` as set in `MULTAS_COLNAMES`).

---

## 6. Serialization (DATA-08)

**Requirement:** Serialize as indexed dict via joblib.

**Performance note:** Benchmarked on a 100k-entry dict:
- `pickle` (protocol 5): write 0.1s, read 0.1s
- `joblib` (compress=0): write 3.4s, read 1.75s

Both produce the same file size (~6MB for 100k entries). For actual RCAC (~29k entries), sizes will be ~1.7MB and times proportionally smaller.

**Recommendation:** Use `joblib.dump` / `joblib.load` to satisfy DATA-08 literally. The performance difference at 29k entries is negligible (~1s total). The file extension `.pkl` is already configured in `settings.rcac_path`.

---

## 7. Lookup Interface (DATA-09)

```python
def rcac_lookup(tipo_doc: str, num_doc: str) -> dict | None:
    """Look up a person/entity in the RCAC index.

    Both arguments are required. Inputs are normalized before lookup
    (same normalization as build time) so callers do NOT need to pre-normalize.

    Returns:
        Full record dict if found (malformed=False records only).
        None if not found, malformed, or RCAC not loaded.
    """
```

**Key contract:** Normalizes inputs internally (strip non-digits from `num_doc`, map tipo to catalog). This prevents caller errors from denormalized input.

**Loading pattern:** RCAC dict is loaded once into module-level state (lazy load on first call). Subsequent calls use in-memory dict. This gives true O(1) lookup (verified: 1M lookups in 0.16s = 0.00016ms each).

**Module structure:**
```
src/sip_engine/data/rcac_builder.py   # build_rcac(force: bool = False) -> Path
src/sip_engine/data/rcac_lookup.py    # rcac_lookup(tipo, num) -> dict | None
                                       # + _load_rcac() private loader
                                       # + get_rcac_index() for testing/inspection
```

---

## 8. CLI Integration

`python -m sip_engine build-rcac` stub already exists in `src/sip_engine/__main__.py`. Implementation needed:

```python
# In __main__.py, build-rcac handler:
from sip_engine.data.rcac_builder import build_rcac
force = args.force  # --force flag
build_rcac(force=force)
```

Add `--force` argument to the `build-rcac` subparser.

---

## 9. Settings Additions Needed

Add to `src/sip_engine/config/settings.py`:

```python
# In __post_init__:
self.rcac_bad_rows_path = self.artifacts_rcac_dir / "rcac_bad_rows.csv"
```

`rcac_path` already exists: `artifacts/rcac/rcac.pkl`.

---

## 10. Bad-Rows Log Format

File: `artifacts/rcac/rcac_bad_rows.csv`

Columns:
```
source, tipo_documento_raw, numero_documento_raw, reason
```

`reason` values: `empty_after_strip`, `all_zeros`, `length_lt_3`

Written by the builder after processing all sources. Appended if file exists (or overwritten on force rebuild). CSV format for auditability.

---

## 11. Testing Strategy

Tests run without real data (fixtures only), following Phase 2 pattern.

**Tests to write:**

### test_rcac_normalization.py (or combined test_rcac.py)

| Test | What it validates |
|---|---|
| `test_normalize_strips_dots_hyphens` | `'43.922.546'` → `'43922546'` |
| `test_normalize_strips_spaces` | `'CE 289910'` → `'289910'` |
| `test_normalize_rejects_empty` | `''` → `(None, malformed=True)` |
| `test_normalize_rejects_all_zeros` | `'000000'` → `(None, malformed=True)` |
| `test_normalize_rejects_lt3_digits` | `'12'` → `(None, malformed=True)` |
| `test_tipo_mapping_siri` | `'CÉDULA DE CIUDADANÍA'` → `'CC'` |
| `test_tipo_mapping_personas_juridicas` | `'Personas Jurídicas'` → `'NIT'` |
| `test_tipo_unknown_maps_to_otro` | `'Tipo Raro'` → `'OTRO'` |

### test_rcac_builder.py

| Test | What it validates |
|---|---|
| `test_build_creates_pkl` | pkl file written at correct path |
| `test_build_returns_expected_keys` | (tipo, num) tuples in index |
| `test_dedup_across_sources` | same person in 2 sources → 1 record, 2 flags |
| `test_malformed_excluded_from_index` | empty/zeros/short not in index |
| `test_bad_rows_log_written` | rcac_bad_rows.csv created with correct columns |
| `test_num_fuentes_distintas_counted` | correct source count per record |
| `test_force_flag_rebuilds` | --force overwrites existing pkl |
| `test_cache_used_when_pkl_exists` | without --force, existing pkl reused |

### test_rcac_lookup.py

| Test | What it validates |
|---|---|
| `test_lookup_hit_returns_record` | found record has expected keys |
| `test_lookup_miss_returns_none` | unknown ID → None |
| `test_lookup_normalizes_input` | raw `'43.922.546'` matched by `'43922546'` |
| `test_lookup_malformed_returns_none` | malformed record not in index |
| `test_en_multas_secop_flag` | correct source flag on matched record |
| `test_lookup_without_pkl_raises` | FileNotFoundError if pkl missing |

---

## 12. Module Update Checklist

| File | Change |
|---|---|
| `src/sip_engine/config/settings.py` | Add `rcac_bad_rows_path` |
| `src/sip_engine/data/rcac_builder.py` | New: `build_rcac()`, normalization logic, source parsers |
| `src/sip_engine/data/rcac_lookup.py` | New: `rcac_lookup()`, `_load_rcac()`, `get_rcac_index()` |
| `src/sip_engine/data/__init__.py` | Re-export `rcac_lookup`, `build_rcac` |
| `src/sip_engine/__main__.py` | Implement `build-rcac` handler with `--force` flag |
| `tests/test_rcac.py` | New: all normalization, builder, lookup tests |

---

## 13. Open Questions for Planner

1. **sanciones_penales `en_sanciones_penales=False`**: Is it acceptable to always set this flag to `False` in Phase 3, with a logged warning? The data source simply has no person-level IDs.

2. **tipo inference for resp_fiscales/multas**: Name-pattern + length heuristic recommended. Does the user want a stricter policy (always OTRO, accept false negatives) or the heuristic (imperfect but practical)?

3. **NIT check-digit consistency**: Normalizing `'900123456-1'` → `'9001234561'` (10 chars) means callers must normalize identically. Should `rcac_lookup()` normalize inputs internally (recommended), or should callers be responsible?

4. **Single vs split test file**: One `tests/test_rcac.py` covering normalization + builder + lookup, or separate files? Given Phase 2 used one `test_loaders.py`, single file is consistent.

5. **MULTAS schema update**: `MULTAS_COLNAMES` in schemas.py currently names all 15 columns as `col_0`…`col_14`. Phase 3 uses `col_5` and `col_6`. Should schemas.py be updated with semantic names for these two? Recommended: yes, update `MULTAS_COLNAMES` and `MULTAS_USECOLS` to select only cols [5, 6] with names `['numero_documento', 'nombre_sancionado']`.

---

## 14. Implementation Notes (Phase-Specific)

- **No chunked processing needed for RCAC:** All 5 sources with IDs are small (largest = SIRI at 46k rows × 2 cols = ~1MB). Load entire source into DataFrame, normalize, then merge. No generator pattern required.
- **Merge order:** boletines → SIRI → resp_fiscales → multas → colusiones (ascending by source flag name for reproducibility).
- **CLI return code:** `build-rcac` should `sys.exit(0)` on success, `sys.exit(1)` on error.
- **Logging:** Use `logging.getLogger(__name__)` in both builder and lookup modules. Builder logs INFO: "RCAC built — N records, M malformed" at completion.
- **`get_rcac_index()` helper:** Returns the loaded dict (loads if needed). Useful for tests to inspect index without calling `rcac_lookup()`.

---

*Research complete. All 7 requirements (DATA-01–05, DATA-08, DATA-09) addressed.*
*Key open question: sanciones_penales cannot provide person-level flags — planner must decide handling.*
