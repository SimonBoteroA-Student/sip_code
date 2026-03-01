---
phase: 05-feature-engineering
plan: 01
subsystem: features
tags: [provider-history, temporal-leak-guard, bisect, joblib, parquet, schemas, settings]

# Dependency graph
requires:
  - phase: 04-label-construction
    provides: labels.parquet with M1/M2 flags per contract (for sobrecostos/retrasos counts)
  - phase: 03-rcac-builder
    provides: normalize_tipo, normalize_numero, is_malformed utilities for provider ID normalization
  - phase: 02-data-loaders
    provides: load_contratos() chunked streaming loader used to build index
provides:
  - Provider History Index (provider_history_index.pkl) with sorted per-provider contract lists
  - build_provider_history_index() — offline builder with force/skip-existing pattern
  - lookup_provider_history() — O(log n) as-of-date lookup with strict < temporal guard
  - load_provider_history_index() — lazy-loading module-level cache
  - Extended CONTRATOS_USECOLS with Codigo de Categoria Principal (str dtype)
  - Extended PROCESOS_USECOLS with ID del Portafolio, Fecha de Recepcion de Respuestas, Fecha Adjudicacion
  - Settings paths: provider_history_index_path, encoding_mappings_path, features_path
affects:
  - 05-02 (Cat-A/B/C feature extractors — uses provider history index for Cat-C features)
  - 05-03 (pipeline.py — calls build_provider_history_index() at pipeline start)
  - 07-model-training (features.parquet path needed)

# Tech tracking
tech-stack:
  added: [bisect (stdlib), joblib (already present via rcac)]
  patterns:
    - Sorted parallel arrays per provider (dates/valores/deptos/m1/m2) for O(log n) bisect lookup
    - Module-level cache with reset function for test isolation (same as rcac_lookup pattern)
    - Normalization at lookup boundary — callers pass raw strings, normalize internally
    - Strict < temporal guard: bisect_left on sorted dates ensures same-day exclusion

key-files:
  created:
    - src/sip_engine/features/provider_history.py
    - tests/test_features.py
  modified:
    - src/sip_engine/data/schemas.py
    - src/sip_engine/config/settings.py
    - src/sip_engine/features/__init__.py
    - tests/conftest.py
    - tests/test_labels.py

key-decisions:
  - "Parallel sorted arrays per provider (dates/valores/deptos/m1/m2) chosen over list of dicts — enables bisect_left on plain list without key extraction overhead"
  - "bisect_left used for strict < cutoff — same-day contracts land AT or AFTER cutoff index, enforcing FEAT-05 temporal leak guard"
  - "M1/M2 treated as 0 when pd.NA — nullable Int8 from labels.parquet; pd.isna() check before int() cast prevents TypeError"
  - "Null Fecha de Firma rows silently dropped with counter logged (not raised as error) — 7.2% of contratos expected to have null dates"
  - "conftest.py tiny_contratos_csv and test_labels.py _CONTRATOS_HEADER updated to include Codigo de Categoria Principal (Rule 1 auto-fix)"

patterns-established:
  - "Parallel array index structure: store separate lists for each attribute, all sorted together by date key"
  - "reset_provider_history_cache() mirrors reset_rcac_cache() pattern — explicit cache reset for test isolation"
  - "Provider ID normalized at lookup boundary: normalize_tipo(tipo_doc) + normalize_numero(num_doc) inside lookup function"

requirements-completed: [FEAT-05, FEAT-06]

# Metrics
duration: 4min
completed: 2026-03-01
---

# Phase 5 Plan 01: Feature Engineering Infrastructure Summary

**Provider History Index with bisect-based temporal leak guard: sorted parallel arrays per provider, O(log n) as-of-date lookup, M1/M2 label integration for sobrecostos/retrasos counts**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-01T22:38:44Z
- **Completed:** 2026-03-01T22:43:09Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Schemas extended with 4 new columns (Codigo de Categoria Principal in CONTRATOS, plus 3 in PROCESOS) for Phase 5 feature extraction
- Settings extended with 3 new artifact paths (provider_history_index_path, encoding_mappings_path, features_path)
- Provider History Index builder streams contratos, joins M1/M2 labels, groups and sorts per-provider, serializes via joblib
- lookup_provider_history() returns national + departmental counts, total values, and sobrecostos/retrasos counts — all zero for first-time providers
- 20 tests covering schema additions, settings paths, build/rebuild/skip behavior, temporal exclusion, scoping, and label counts

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend schemas.py and settings.py for Phase 5** - `9b461c7` (feat)
2. **Task 2: Build Provider History Index with TDD** - `a17eedb` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `src/sip_engine/features/provider_history.py` — Provider History Index builder, loader, lookup, and cache reset
- `src/sip_engine/features/__init__.py` — Re-exports public API (build, load, lookup)
- `src/sip_engine/data/schemas.py` — CONTRATOS_USECOLS/DTYPE + PROCESOS_USECOLS/DTYPE extensions
- `src/sip_engine/config/settings.py` — 3 new artifact file paths in field declarations and __post_init__
- `tests/test_features.py` — 20 tests (7 schema/settings + 13 provider history)
- `tests/conftest.py` — tiny_contratos_csv updated to include Codigo de Categoria Principal
- `tests/test_labels.py` — _CONTRATOS_HEADER and _make_contrato_row updated for new column

## Decisions Made

- Parallel sorted arrays per provider chosen over list-of-dicts: enables bisect_left on a plain Python list without needing a key extraction step at lookup time
- bisect_left enforces strictly < as_of_date: same-day contracts have dates[i] == as_of_date which bisect_left places at or after the cutoff — no extra comparison needed
- pd.NA from nullable Int8 labels treated as 0 for M1/M2 counting: pd.isna() check before int() cast prevents TypeError
- Null dates logged and skipped (not raised): 7.2% null rate in contratos is expected, not an error condition

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test fixtures to include new Codigo de Categoria Principal column**
- **Found during:** Task 1 (schema extension)
- **Issue:** Adding Codigo de Categoria Principal to CONTRATOS_USECOLS caused validate_columns() to fail on existing test CSV fixtures that did not include the column, breaking 98 previously-passing tests
- **Fix:** Updated conftest.py tiny_contratos_csv fixture and test_labels.py _CONTRATOS_HEADER/_make_contrato_row to include the new column with placeholder values
- **Files modified:** tests/conftest.py, tests/test_labels.py
- **Verification:** All 98 existing tests still pass after schema extension
- **Committed in:** 9b461c7 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug caused by schema extension breaking test fixtures)
**Impact on plan:** Necessary correctness fix; test data must mirror schema exactly for validate_columns() to pass. No scope creep.

## Issues Encountered

None — plan executed as specified with one Rule 1 auto-fix for test fixtures.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Provider History Index infrastructure complete — Cat-C features in 05-02 can call lookup_provider_history() directly
- Schema constants updated — loaders will pick up new columns on next load_contratos()/load_procesos() call
- Settings paths established — 05-02/05-03 can use settings.provider_history_index_path and settings.features_path without hardcoding

---
*Phase: 05-feature-engineering*
*Completed: 2026-03-01*
