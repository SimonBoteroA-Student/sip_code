---
phase: 02-data-loaders
plan: "01"
subsystem: data
tags: [schemas, column-definitions, currency-cleaning, encoding, test-fixtures]
requirements: [DATA-07, DATA-10]

dependency_graph:
  requires:
    - 01-02: Settings dataclass with paco_encoding field
  provides:
    - schemas.py: column/dtype constants for all 14 source files
    - clean_currency: currency string to Float64 utility
    - validate_columns: fail-fast header validation utility
    - test fixtures: tiny_contratos_csv, tiny_siri_csv, tiny_multas_csv, bad_byte_csv, missing_column_csv
  affects:
    - 02-02: loaders.py imports USECOLS/DTYPE/COLNAMES constants from schemas.py
    - 03-*: RCAC builder uses SIRI_COLNAMES, RESP_FISCALES_USECOLS, etc.

tech_stack:
  added: []
  patterns:
    - "Column schema constants: *_USECOLS, *_DTYPE, *_COLNAMES per source file"
    - "Nullable Float64 for currency columns (pd.NA-safe, not NaN)"
    - "Integer usecols for headerless files (SIRI, multas)"
    - "validate_columns() reads only nrows=0 — O(1) header check before full load"

key_files:
  created:
    - src/sip_engine/data/schemas.py
    - tests/conftest.py
    - tests/test_loaders.py
  modified:
    - src/sip_engine/config/settings.py

decisions:
  - "Used actual verified column names from file inspection rather than plan's approximate names (e.g., 'Proceso de Compra' not 'ID del Proceso' in contratos)"
  - "Included 'Respuestas al Procedimiento' and 'Proveedores Unicos con Respuestas' in PROCESOS_USECOLS as N_BIDS signal for feature engineering"
  - "xfail with strict=True and raises=ImportError for loader test stubs — ensures they fail for the right reason until Plan 02"

metrics:
  duration_seconds: 223
  completed_date: "2026-03-01"
  tasks_completed: 2
  files_created: 3
  files_modified: 1
  test_results: "11 passed, 9 xfailed"
---

# Phase 02 Plan 01: Schemas and Test Scaffold Summary

Column schema definitions + currency/validation utilities + test fixtures for all 14 data source files, with Settings.paco_encoding corrected from 'latin-1' to 'utf-8'.

## What Was Built

### Task 1: schemas.py + Settings paco_encoding fix

`src/sip_engine/data/schemas.py` defines the data contracts for all 14 CSV source files:

**SECOP files (9 files, all have headers, UTF-8):**
- `CONTRATOS_USECOLS/DTYPE/CURRENCY_COLS` — 20 columns, currency `Valor del Contrato`
- `PROCESOS_USECOLS/DTYPE/CURRENCY_COLS` — 20 columns including N_BIDS signal, currency `Precio Base` + `Valor Total Adjudicacion`; explicit `str` for `Nit Entidad` + `PCI` to prevent `DtypeWarning`
- `OFERTAS_USECOLS/DTYPE/CURRENCY_COLS` — 7 columns, currency `Valor de la Oferta`
- `PROPONENTES_USECOLS/DTYPE` — all 9 columns (small file)
- `PROVEEDORES_USECOLS/DTYPE` — all 25 columns (small file)
- `BOLETINES_USECOLS/DTYPE` — all 9 columns, `numero de documento` as str
- `EJECUCION_USECOLS/DTYPE` — all 16 post-execution columns (for RCAC use only)
- `SUSPENSIONES_USECOLS/DTYPE` — all 7 columns
- `ADICIONES_USECOLS/DTYPE` — all 5 columns (used for M1/M2 labels)

**PACO files (5 files, all UTF-8 confirmed):**
- `SIRI_USECOLS=[4,5]` / `SIRI_DTYPE={4:str,5:str}` / `SIRI_COLNAMES` — headerless, positional
- `MULTAS_USECOLS=None` / `MULTAS_COLNAMES=[col_0..col_14]` — headerless, load all 15 cols
- `RESP_FISCALES_USECOLS/DTYPE` — all 8 columns, combined doc field as str
- `COLUSIONES_USECOLS/DTYPE` — all 12 columns, Identificacion as str
- `SANCIONES_PENALES_USECOLS/DTYPE` — all 9 geographic columns

**Utility functions:**
- `clean_currency(series)` — strips `$` and `,`, converts to nullable `Float64`
- `validate_columns(path, expected, encoding)` — reads only header row (`nrows=0`), raises `ValueError` listing missing columns; skips for integer (headerless) usecols

**Settings fix:** `paco_encoding` changed from `'latin-1'` to `'utf-8'`. All 5 PACO files verified UTF-8 empirically during Phase 2 research; latin-1 would produce garbled Spanish characters (e.g., `CÃ\x89DULA` instead of `CÉDULA`).

### Task 2: test fixtures + test scaffold

`tests/conftest.py` — 5 shared fixtures:
- `tiny_contratos_csv` — 5-row CSV with real headers + `$X,XXX,XXX` currency format
- `tiny_siri_csv` — headerless 28-col CSV with Spanish chars in col[4]
- `tiny_multas_csv` — headerless 15-col CSV with NIT in col[5]
- `bad_byte_csv` — injects `\xff` byte into UTF-8 CSV (tests `encoding_errors='replace'`)
- `missing_column_csv` — drops last CONTRATOS_USECOLS column (tests `validate_columns`)

`tests/test_loaders.py` — 20 tests total:
- **11 passing** schema tests: `TestCleanCurrency` (6 tests) + `TestValidateColumns` (5 tests)
- **9 xfail** loader stubs: `TestLoadContratos` (4), `TestLoadPacoSiri` (3), `TestEncodingReplace` (2) — strict xfail with `raises=ImportError`, will pass once Plan 02 creates `loaders.py`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected column names to match actual file headers**
- **Found during:** Task 1 — file inspection before writing schemas
- **Issue:** Plan specified "ID del Proceso" as a column in contratos, but actual file uses "Proceso de Compra" for the process FK and "ID Contrato" for the contract identifier. Plan also specified columns not present in procesos (`Fecha de Publicacion del Proceso` is correct, but exact procesos column is `Fecha de Publicacion del Proceso` — confirmed matching).
- **Fix:** Used `python -c "pd.read_csv(path, nrows=0)"` on all files to get exact column names before writing any constants.
- **Files modified:** `src/sip_engine/data/schemas.py`
- **Commit:** 168a87b

**2. [Rule 2 - Enhancement] Added N_BIDS signal columns to PROCESOS_USECOLS**
- **Found during:** Task 1 — procesos has `Respuestas al Procedimiento` and `Proveedores Unicos con Respuestas` which are key inputs for the N_BIDS feature (FEAT-02)
- **Fix:** Included both columns in `PROCESOS_USECOLS` while they are available — easier to add now than retrofit in Phase 5
- **Files modified:** `src/sip_engine/data/schemas.py`
- **Commit:** 168a87b

**3. [Rule 2 - Enhancement] Added `empty_expected_list` test case**
- **Found during:** Task 2 — edge case not in plan, but trivially important to verify
- **Fix:** Added `test_empty_expected_list` to `TestValidateColumns` — ensures `validate_columns(path, [])` does not raise
- **Files modified:** `tests/test_loaders.py`
- **Commit:** 07ff38d

## Test Results

```
tests/test_loaders.py: 11 passed, 9 xfailed in 0.43s
```

Schema tests fully green. Loader test stubs correctly xfail (ImportError on `from sip_engine.data.loaders import ...`).

## Self-Check

Files exist:
- [x] `src/sip_engine/data/schemas.py` — 227 lines
- [x] `tests/conftest.py` — 5 fixtures
- [x] `tests/test_loaders.py` — 20 tests (11 pass, 9 xfail)
- [x] `src/sip_engine/config/settings.py` — paco_encoding = 'utf-8'

Commits exist:
- [x] 168a87b — feat(02-01): schemas.py + paco_encoding fix
- [x] 07ff38d — test(02-01): conftest + test_loaders
