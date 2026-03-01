---
phase: 02-data-loaders
plan: "02"
subsystem: data
tags: [loaders, csv, generators, tqdm, encoding, currency-cleaning, chunked-io]
requirements: [DATA-06, DATA-07, DATA-10]

dependency_graph:
  requires:
    - 02-01: schemas.py with all USECOLS/DTYPE/CURRENCY_COLS/COLNAMES constants
    - 01-02: Settings dataclass with all *_path fields and chunk_size
  provides:
    - loaders.py: 14 generator-based CSV loader functions for all SIP sources
    - data/__init__.py: re-exports all 14 loaders for convenient import
  affects:
    - 03-*: RCAC builder calls load_paco_siri(), load_paco_resp_fiscales(),
            load_paco_colusiones(), load_paco_multas(), load_paco_sanciones_penales()
    - 04-*: Label construction calls load_contratos(), load_adiciones()
    - 05-*: Feature engineering calls load_contratos(), load_procesos(), load_ofertas()

tech_stack:
  added: []
  patterns:
    - "_load_csv() private helper: single implementation of validate/tqdm/bad-row-counter/currency-clean/INFO-log pattern"
    - "Generator protocol: all loaders yield pd.DataFrame chunks (never hold full file)"
    - "lru_cache test isolation: autouse clear_settings_cache fixture in conftest.py"
    - "_BadRowCounter(logging.Handler): counts ParserWarning 'Skipping line' messages"
    - "subprocess wc -l for tqdm total estimation (graceful fallback to 0 = spinner)"

key_files:
  created:
    - src/sip_engine/data/loaders.py
  modified:
    - src/sip_engine/data/__init__.py
    - tests/test_loaders.py
    - tests/conftest.py

decisions:
  - "Used private _load_csv() helper instead of duplicating tqdm/logging pattern 14 times — each public loader is a thin 3-line wrapper"
  - "autouse clear_settings_cache fixture added to conftest.py — ensures monkeypatch.setenv(SIP_*) takes effect per test when get_settings() is an lru_cache singleton"
  - "validate=False for headerless loaders (SIRI, multas) — integer usecols have no column names to validate; validate_columns() already handles this but explicit is clearer"
  - "MULTAS dtype passed as empty dict {} — all 15 columns read as pandas default (str/object), Phase 3 refines column types"

metrics:
  duration_seconds: 235
  completed_date: "2026-03-01"
  tasks_completed: 2
  files_created: 1
  files_modified: 3
  test_results: "25 passed, 0 failed, 0 xfails"
---

# Phase 02 Plan 02: CSV Loaders Summary

14 generator-based CSV loaders with shared `_load_csv()` helper — tqdm progress, INFO logging, currency cleaning, bad-row skipping, and encoding replacement across all 9 SECOP + 5 PACO source files.

## What Was Built

### Task 1: loaders.py + __init__.py

`src/sip_engine/data/loaders.py` (422 lines) implements the full loading layer for all 14 SIP data sources.

**Private infrastructure:**

- `_count_lines(path) -> int` — `subprocess wc -l` with timeout/graceful fallback to 0 (tqdm shows spinner instead of estimated ETA).
- `_total_chunks(path, chunk_size, has_header) -> int` — divides data rows by chunk_size, rounds up. `has_header=False` for SIRI and multas.
- `_BadRowCounter(logging.Handler)` — attaches to `py.warnings` logger, counts "Skipping line" messages emitted by pandas `on_bad_lines='warn'`.
- `_load_csv(path, desc, usecols, dtype, encoding, currency_cols, has_header, colnames, validate)` — single implementation of the full pattern: FileNotFoundError check → validate_columns → _BadRowCounter attach → pd.read_csv chunked → tqdm loop → column rename (headerless) → currency clean → yield → finally detach counter + INFO log.

**9 SECOP loaders (headed, UTF-8):**

| Function | File | Notes |
|---|---|---|
| `load_contratos()` | contratos_SECOP.csv | currency: `Valor del Contrato` |
| `load_procesos()` | procesos_SECOP.csv | currency: `Precio Base` + `Valor Total Adjudicacion` |
| `load_ofertas()` | ofertas_proceso_SECOP.csv | currency: `Valor de la Oferta` |
| `load_proponentes()` | proponentes_proceso_SECOP.csv | small, no currency |
| `load_proveedores()` | proveedores_registrados.csv | small, no currency |
| `load_boletines()` | boletines.csv | doc IDs as str |
| `load_ejecucion()` | ejecucion_contratos.csv | RCAC only (FEAT-08 excluded) |
| `load_suspensiones()` | suspensiones_contratos.csv | small |
| `load_adiciones()` | adiciones.csv | tiny, M1/M2 labels |

**5 PACO loaders (all UTF-8 verified in 02-01):**

| Function | File | Notes |
|---|---|---|
| `load_paco_resp_fiscales()` | responsabilidades_fiscales_PACO.csv | combined doc field, typo preserved |
| `load_paco_colusiones()` | colusiones_en_contratacion_SIC.csv | tiny, 103 rows |
| `load_paco_sanciones_penales()` | sanciones_penales_FGN.csv | geographic/crime data |
| `load_paco_siri()` | sanciones_SIRI_PACO.csv | **headerless**, cols [4,5] → tipo/numero_documento |
| `load_paco_multas()` | multas_SECOP_PACO.csv | **headerless**, all 15 cols → col_0..col_14 |

**`src/sip_engine/data/__init__.py`** re-exports all 14 functions so `from sip_engine.data import load_contratos` works.

### Task 2: Test updates + edge-case tests

Removed `@pytest.mark.xfail` from `TestLoadContratos`, `TestLoadPacoSiri`, `TestEncodingReplace` — all 9 previously-xfail tests now pass.

New test classes added:

- `TestFileNotFound` — asserts `FileNotFoundError` with "contratos" in message when `SIP_SECOP_DIR` points to empty dir.
- `TestChunkedMemorySafety` — 5-row CSV with `chunk_size=2` yields exactly 3 chunks of sizes [2, 2, 1]. Validates DATA-06.
- `TestAllLoadersImportable` — all 14 functions importable and callable (no instantiation of generators).
- `test_encoding_replace_produces_replacement_char` — DATA-10 explicit test: U+FFFD present, no UnicodeDecodeError.

**autouse `clear_settings_cache` fixture** added to `conftest.py` — clears `get_settings.cache_clear()` before and after each test, enabling `monkeypatch.setenv(SIP_*)` overrides to take effect.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Settings lru_cache prevented monkeypatched env vars from taking effect**
- **Found during:** Task 2 — `test_replacement_char_present` and `test_file_not_found` failed because `get_settings()` returned a cached `Settings()` built before `monkeypatch.setenv()` ran
- **Issue:** `get_settings()` uses `@functools.lru_cache(maxsize=1)` — the first call from any test in the module locks the Settings singleton. Subsequent tests' `monkeypatch.setenv()` changes never reach `Settings.__post_init__`.
- **Fix:** Added `autouse=True` fixture `clear_settings_cache` to `conftest.py` that calls `get_settings.cache_clear()` before and after each test. This is the idiomatic pytest solution for lru_cache singletons.
- **Files modified:** `tests/conftest.py`
- **Commit:** 8c22ea3

## Test Results

```
tests/test_loaders.py: 25 passed in 0.67s (0 failed, 0 xfails)
tests/ full suite:     25 passed in 0.52s
```

All 14 loader functions satisfy the plan's must_haves:
- [x] Yield DataFrame chunks from each source file
- [x] FileNotFoundError on missing file
- [x] tqdm progress bar per loader
- [x] INFO log summary (rows loaded, skipped, elapsed)
- [x] Bad rows skipped (on_bad_lines='warn')
- [x] Encoding errors replaced with U+FFFD (encoding_errors='replace')
- [x] Currency columns cleaned to Float64
- [x] Headerless SIRI/multas use positional columns and rename

## Self-Check

Files exist:
- [x] `src/sip_engine/data/loaders.py` — 422 lines
- [x] `src/sip_engine/data/__init__.py` — re-exports all 14 loaders
- [x] `tests/test_loaders.py` — 25 tests passing
- [x] `tests/conftest.py` — autouse cache_clear fixture added

Commits exist:
- [x] 2f00fe6 — feat(02-02): implement all 14 generator-based CSV loader functions
- [x] 8c22ea3 — test(02-02): remove xfail marks, add edge-case tests, fix settings cache

## Self-Check: PASSED
