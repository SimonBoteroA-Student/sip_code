---
phase: 04-label-construction
plan: 01
subsystem: data
tags: [labels, M1, M2, adiciones, tdd]
dependency_graph:
  requires: [03-02]
  provides: [label_builder_skeleton, m1_m2_sets, contratos_base]
  affects: [04-02, 05-feature-engineering]
tech_stack:
  added: []
  patterns: [chunked-streaming, set-based-label-construction, dedup-by-id]
key_files:
  created:
    - src/sip_engine/data/label_builder.py
    - artifacts/labels/.gitkeep
    - tests/test_labels.py
  modified:
    - src/sip_engine/config/settings.py
    - src/sip_engine/data/schemas.py
decisions:
  - label_builder imports normalize_tipo/normalize_numero/is_malformed from rcac_builder now — establishes dependency for M3/M4 in Plan 04-02
  - _build_m1_m2_sets uses set membership (isin) for orphan filtering — O(1) per row lookup
  - Parquet write deferred to Plan 04-02 — skeleton returns labels_path but does not write until M3/M4 columns are also added
metrics:
  duration: "3 min"
  completed: "2026-03-01"
  tasks_completed: 2
  files_created: 3
  files_modified: 2
---

# Phase 4 Plan 1: M1/M2 Label Construction Infrastructure Summary

M1/M2 label builder skeleton with chunked adiciones streaming, contratos dedup, and 15 TDD tests — all 80 tests passing.

## What Was Built

### label_builder.py

New module at `src/sip_engine/data/label_builder.py` providing:

- **`M1_TIPOS`** — `{"ADICION EN EL VALOR", "REDUCCION EN EL VALOR"}` — contracts with value amendments
- **`M2_TIPOS`** — `{"EXTENSION"}` — contracts with time extensions
- **`_load_contratos_base()`** — streams all contratos chunks, selects 3 columns, deduplicates by `ID Contrato` (keep first), logs total vs unique counts
- **`_build_m1_m2_sets(contratos_ids)`** — streams adiciones.csv in chunks, filters orphan rows (id_contrato not in contratos), normalizes `tipo` via `.str.strip().str.upper()`, returns `(set[str], set[str])` for M1 and M2 contract IDs
- **`build_labels(force=False)`** — skeleton: checks cache, validates RCAC exists, loads contratos, builds M1/M2 sets, assigns `Int8` columns, logs summary + M2 sparsity warning. Parquet write deferred to Plan 04-02.

### Settings additions

`src/sip_engine/config/settings.py`:
- `artifacts_labels_dir` — `artifacts/labels/`
- `labels_path` — `artifacts/labels/labels.parquet`

### Schema fixes

`src/sip_engine/data/schemas.py`:
- Comment corrected: `adiciones.csv (5 cols, ~14.4M rows, ~4 GB)` (was "~1.3k rows, tiny")
- `ADICIONES_DTYPE` now includes `"tipo": str` — prevents DtypeWarning on mixed-type column

### Artifact scaffold

`artifacts/labels/.gitkeep` — force-tracked through gitignore.

## Test Results

```
tests/test_labels.py  15 passed
tests/test_loaders.py 25 passed
tests/test_rcac.py    40 passed
Total: 80 passed in 1.50s
```

Tests cover: M1/M2 constants, case-insensitive tipo matching, contratos dedup, orphan handling, zero-label defaults, tuple return type, RCAC existence check, M2 sparsity warning.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

Files created:
- [x] src/sip_engine/data/label_builder.py — exists
- [x] artifacts/labels/.gitkeep — exists
- [x] tests/test_labels.py — exists

Files modified:
- [x] src/sip_engine/config/settings.py — artifacts_labels_dir + labels_path confirmed
- [x] src/sip_engine/data/schemas.py — comment and tipo dtype confirmed

Commits:
- [x] 41b944c — feat(04-01): infrastructure
- [x] 33805d5 — test(04-01): 15 TDD tests
