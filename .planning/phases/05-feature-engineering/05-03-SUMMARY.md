---
phase: 05-feature-engineering
plan: 03
subsystem: features
tags: [pipeline, batch, online-inference, train-serve-parity, feat08, feat09, cli, parquet]

# Dependency graph
requires:
  - phase: 05-01
    provides: build_provider_history_index, lookup_provider_history for Cat-C
  - phase: 05-02
    provides: compute_category_a/b/c, build_encoding_mappings, apply_encoding
  - phase: 04-label-construction
    provides: labels.parquet required before build_features() can run

provides:
  - build_features() — offline batch pipeline: features.parquet with 30 columns in canonical order
  - compute_features() — online inference path using same Cat A/B/C functions (FEAT-07 parity)
  - FEATURE_COLUMNS — canonical 30-column list with documented exclusion comments
  - build-features CLI subcommand with --force flag

affects:
  - 07-model-training (features.parquet path and column ordering)
  - 06-iric (IRIC adds 4 more Category D features post-pipeline)

# Tech tracking
tech-stack:
  added: [pyarrow.parquet (already present), subprocess (stdlib, for CLI tests)]
  patterns:
    - Shared compute path: build_features() and compute_features() both call compute_category_a/b/c — no duplicated logic
    - Procesos lookup dict keyed on ID del Portafolio (=Proceso de Compra in contratos) — O(1) join per contract
    - Proveedores lookup dict keyed on normalized NIT — O(1) registration date lookup
    - num_actividades_economicas precomputed from full contratos (static, not as-of) — separate pass before streaming
    - Fecha de Firma injected into procesos_data dict for dias_decision calculation in compute_category_b
    - df.set_index("id_contrato") before encoding — preserves contract identity in parquet index
    - REQUIRED_FIELDS checked before compute: rows missing Fecha de Firma/Valor/Tipo/Modalidad dropped with INFO logging

key-files:
  created:
    - src/sip_engine/features/pipeline.py
  modified:
    - src/sip_engine/__main__.py
    - src/sip_engine/features/__init__.py
    - src/sip_engine/features/category_a.py
    - tests/test_features.py

key-decisions:
  - "Procesos lookup built as dict from load_procesos() stream — O(1) per-contract join replaces expensive per-row streaming"
  - "Fecha de Firma injected into procesos_data dict in pipeline — category_b.compute_category_b uses procesos_data.get(Fecha de Firma) for dias_decision; contract date is the correct proxy"
  - "category_a.py NaN-safe string coercion added — pandas loader returns float NaN for empty CSV fields; (val or '') pattern fails since NaN is truthy"
  - "build_features sets index to id_contrato before writing parquet — enables direct lookup by contract ID in downstream phases and tests"

patterns-established:
  - "_make_pipeline_env() test helper creates full fake filesystem (contratos + procesos + proveedores + labels) for pipeline integration tests"
  - "Pipeline passes force=True to build_provider_history_index() and build_encoding_mappings() when force=True — cascades rebuild through all artifacts"

requirements-completed: [FEAT-07, FEAT-08, FEAT-09]

# Metrics
duration: 5min
completed: 2026-03-01
---

# Phase 5 Plan 03: Feature Engineering Pipeline Summary

**Unified feature pipeline (batch + online) with 30-column features.parquet, FEAT-08/09 exclusion enforcement, and CLI subcommand — completing Phase 5 feature engineering**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-01T22:55:40Z
- **Completed:** 2026-03-01T23:00:58Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- pipeline.py: `build_features()` offline batch path streams contratos, builds procesos/proveedores lookup dicts, precomputes num_actividades per provider, calls Cat A/B/C extractors, builds encoding mappings, applies encoding, writes 30-column features.parquet via pyarrow
- pipeline.py: `compute_features()` online inference path uses identical Cat A/B/C functions with pre-loaded encoding mappings for train-serve parity (FEAT-07)
- FEATURE_COLUMNS constant: 30 features in canonical alphabetical-within-category order (A→B→C) with documented FEAT-08 and FEAT-09 exclusion comment blocks
- Rows missing any of 4 required fields (Fecha de Firma, Valor del Contrato, Tipo de Contrato, Modalidad de Contratacion) are dropped with INFO-level logging per-reason
- `build-features` CLI subcommand added following exact build-rcac/build-labels pattern
- features/__init__.py re-exports build_features, compute_features, FEATURE_COLUMNS
- 15 new tests (12 pipeline + 3 CLI/init) added; 76 total in test_features.py; 174 total across all test files, all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement pipeline.py with batch and online paths** - `952bc34` (feat)
2. **Task 2: CLI wiring and final integration** - `c127274` (feat)

## Files Created/Modified

- `src/sip_engine/features/pipeline.py` — build_features(), compute_features(), FEATURE_COLUMNS, REQUIRED_FIELDS, helper functions
- `src/sip_engine/__main__.py` — build-features subcommand with --force flag and lazy import handler
- `src/sip_engine/features/__init__.py` — re-exports build_features, compute_features, FEATURE_COLUMNS (13 total exports)
- `src/sip_engine/features/category_a.py` — NaN-safe _to_str_or_none() helper + NaN guard in _has_justificacion() (Rule 1 auto-fix)
- `tests/test_features.py` — 76 total tests (up from 61), 15 new for this plan

## Decisions Made

- Procesos lookup built as a complete in-memory dict from streaming load_procesos() — enables O(1) per-contract lookup during contratos stream without re-streaming procesos per row
- Fecha de Firma (from contratos) injected into the procesos_data dict before passing to compute_category_b() — category_b uses `procesos_data.get("Fecha de Firma")` for dias_decision; using the contract signing date is the correct semantic match
- build_features() indexes the DataFrame by id_contrato before writing parquet — downstream phases and tests can use df.loc["CON-001"] directly
- Pipeline cascades force flag to build_provider_history_index and build_encoding_mappings — ensures consistent rebuild behavior across all artifacts

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] NaN-safe string coercion in category_a.py**
- **Found during:** Task 1 (test_build_features_creates_parquet)
- **Issue:** category_a.compute_category_a() used `(justificacion_raw or "")` pattern which fails when pandas loader returns `float('nan')` for empty CSV cells. `float('nan')` is truthy so `nan or ""` returns `nan`, and calling `.lower()` on `nan` raises AttributeError.
- **Fix:** Added `_to_str_or_none()` helper that returns None for `None` and `float('nan')`, applied to all raw string fields. Also added NaN guard to `_has_justificacion()`.
- **Files modified:** src/sip_engine/features/category_a.py
- **Commit:** 952bc34 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug caused by pandas NaN returned from CSV loader for empty/N/A fields)
**Impact on plan:** Correctness fix; category_a must handle pandas NaN values from real CSV data. No scope creep.

## Issues Encountered

None beyond the Rule 1 auto-fix above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 5 feature engineering complete — all 30 features (Cat A/B/C) implemented, tested, and integrated into pipeline
- features.parquet will be produced by `python -m sip_engine build-features` once real data is available
- Phase 6 IRIC will add 4 Category D features to the feature vector (iric_thresholds already in settings)
- Phase 7 model training can call build_features() with a train subset before splitting — encoding mappings built from training data only per design

## Self-Check: PASSED

- [x] `src/sip_engine/features/pipeline.py` — FOUND
- [x] `src/sip_engine/__main__.py` — FOUND (updated)
- [x] `src/sip_engine/features/__init__.py` — FOUND (updated)
- [x] `src/sip_engine/features/category_a.py` — FOUND (updated)
- [x] `tests/test_features.py` — FOUND (76 tests)
- [x] `.planning/phases/05-feature-engineering/05-03-SUMMARY.md` — FOUND
- [x] Commit `952bc34` (Task 1) — FOUND
- [x] Commit `c127274` (Task 2) — FOUND
- [x] 76 tests in test_features.py — ALL PASSING
- [x] 174 total tests — ALL PASSING
- [x] `python -m sip_engine build-features --help` — WORKS

---
*Phase: 05-feature-engineering*
*Completed: 2026-03-01*
