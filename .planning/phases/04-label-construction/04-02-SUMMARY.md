---
phase: 04-label-construction
plan: 02
subsystem: data
tags: [labels, M3, M4, boletines, rcac, parquet, tdd]
dependency_graph:
  requires: [04-01, 03-02]
  provides: [complete_label_builder, m3_m4_labels, labels_parquet, build_labels_cli]
  affects: [05-feature-engineering, 07-model-training]
tech_stack:
  added: [pyarrow==23.0.1]
  patterns: [nullable-Int8-columns, set-membership-M3-lookup, rcac-lookup-M4, parquet-output]
key_files:
  created: []
  modified:
    - src/sip_engine/data/label_builder.py
    - src/sip_engine/__main__.py
    - src/sip_engine/data/__init__.py
    - tests/test_labels.py
    - requirements.lock
decisions:
  - _build_boletines_set uses iterrows() for per-row normalization — clarity over vectorization since boletines is small
  - _compute_m3_m4 uses Python loop with is_malformed guard — clear null-handling logic per row
  - Null trigger is OR of is_malformed(normalized_num) | original isna() — covers both empty string and NaN inputs
  - M4 passes raw values to rcac_lookup() which normalizes internally — avoids double normalization path
  - pyarrow added to requirements.lock (installed as parquet engine dependency)
metrics:
  duration: "4 min"
  completed: "2026-03-01"
  tasks_completed: 2
  files_created: 0
  files_modified: 5
---

# Phase 4 Plan 2: M3/M4 Label Construction Summary

Complete M3/M4 label builder with boletines set lookup, RCAC-based classification, parquet output, CLI wiring, and 33 TDD tests — all 98 tests passing.

## What Was Built

### label_builder.py — Complete Implementation

Three new functions completing the label builder:

**`_build_boletines_set()`**
- Streams boletines.csv via `load_boletines()` generator
- Normalizes each row's `tipo de documento` + `numero de documento` via `normalize_tipo()` / `normalize_numero()`
- Skips rows where `is_malformed(num_norm)` is True
- Returns `set[tuple[str, str]]` for O(1) M3 membership tests
- Logs count of unique pairs and boletines incompleteness warning

**`_compute_m3_m4(df, boletines_set)`**
- Creates `tipo_norm` and `num_norm` series via `.apply(normalize_tipo/normalize_numero)`
- Malformed mask: `is_malformed(num_norm) | Documento Proveedor.isna()`
- M3: `1` if `(tipo_norm, num_norm) in boletines_set`, `0` if valid provider not in set, `pd.NA` if malformed
- M4: `1` if `rcac_lookup(raw_tipo, raw_num)` returns a record (not None), else `0` or `pd.NA`
- Returns DataFrame with `M3`, `M4`, `TipoDocProveedor_norm`, `DocProveedor_norm` columns added
- Logs M3/M4 positive counts and null counts

**`build_labels()` — Complete**
- Added: calls `_build_boletines_set()` after M1/M2 assignment
- Added: calls `_compute_m3_m4()` to populate M3/M4 columns
- Added: selects output columns `[id_contrato, M1, M2, M3, M4, TipoDocProveedor_norm, DocProveedor_norm]`
- Added: writes `labels.parquet` via `df.to_parquet(..., engine="pyarrow")`
- Added: final per-column summary log (positive/zero/null counts)

### CLI — build-labels subcommand

`src/sip_engine/__main__.py` now handles `build-labels`:
- `build_labels_parser` added with `--force` flag (same pattern as `build-rcac`)
- Dispatches to `build_labels(force=args.force)`
- Prints `Labels built: {path}` on success; stderr + exit 1 on error

### Package Re-export

`src/sip_engine/data/__init__.py` now imports and re-exports `build_labels`.

### Dependencies

`pyarrow==23.0.1` installed and added to `requirements.lock` — required by `pandas.DataFrame.to_parquet()` and `pd.read_parquet()`.

## Test Results

```
tests/test_labels.py  33 passed (was 15)
tests/test_loaders.py 25 passed
tests/test_rcac.py    40 passed
Total: 98 passed in 2.12s
```

New tests added (18):
- `test_build_boletines_set_*` (3): returns set, contains correct entry, count
- `test_m3_provider_in_boletines`, `test_m3_provider_not_in_boletines`
- `test_m3_null_for_malformed_provider`, `test_m3_null_for_missing_provider`
- `test_m4_provider_in_rcac`, `test_m4_provider_not_in_rcac`, `test_m4_null_for_malformed_provider`
- `test_m3_input_normalization`: raw type strings + dotted numbers normalize correctly
- `test_m4_uses_rcac_lookup`: integration test via result correctness
- `test_build_labels_creates_parquet`, `test_labels_parquet_schema`, `test_labels_parquet_nullable_int8`
- `test_build_labels_cache`, `test_build_labels_force_rebuilds`
- `test_m3_boletines_warning`

Fixture extended: `label_test_env` now yields (for teardown), creates 3-row boletines.csv (CC/12345678 matching), RCAC pkl with CC/12345678 entry, and calls `reset_rcac_cache()` in teardown.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

Files modified:
- [x] src/sip_engine/data/label_builder.py — _build_boletines_set, _compute_m3_m4, build_labels complete
- [x] src/sip_engine/__main__.py — build-labels subcommand present
- [x] src/sip_engine/data/__init__.py — build_labels in __all__
- [x] tests/test_labels.py — 33 tests, all pass
- [x] requirements.lock — pyarrow==23.0.1 added

Commits:
- [x] c40bf8a — feat(04-02): M3/M4 labels, boletines set, parquet output, CLI, exports
- [x] d2d8f8b — test(04-02): 18 TDD tests for M3/M4 labels, parquet output, cache behavior
