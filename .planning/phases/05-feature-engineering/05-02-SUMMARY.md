---
phase: 05-feature-engineering
plan: 02
subsystem: features
tags: [category-a, category-b, category-c, encoding, election-calendar, unspsc, bisect, temporal-features, label-encoding]

# Dependency graph
requires:
  - phase: 05-01
    provides: lookup_provider_history for as-of provider counts in Cat-C
  - phase: 03-rcac-builder
    provides: normalize_tipo used in category_c for NIT detection
  - phase: 04-label-construction
    provides: labels.parquet consumed indirectly via provider history index
provides:
  - compute_category_a() — 10 contract features (valor, 4 categoricals, 3 binary flags, UNSPSC segment, has_justificacion)
  - compute_category_b() — 9 temporal features with election calendar, procesos durations, proveedor registration age
  - compute_category_c() — 11 provider/competition features with dual-scope history counts
  - COLOMBIAN_ELECTION_DATES — hardcoded 2015-2026 election calendar constant
  - build_encoding_mappings() — rare-category grouping at 0.1% threshold, alphabetical ordering, JSON serialization
  - apply_encoding() — applies mappings with unseen→Other fallback, NaN preserved
  - load_encoding_mappings() — loads JSON for inference-time parity
affects:
  - 05-03 (pipeline.py — calls all compute_category_* and encoding functions)
  - 07-model-training (features.parquet encoded via apply_encoding)

# Tech tracking
tech-stack:
  added: [json (stdlib)]
  patterns:
    - Dependency injection for provider_history in compute_category_c — caller pre-fetches lookup result and passes it in (enables test isolation without mocking the index)
    - Election calendar as module-level constant list — iterated linearly (11 entries, O(n) is fine)
    - RARE_THRESHOLD strictly less than (not <=) for frequency check — exactly 0.1% is treated as rare
    - NaN propagated as float('nan') throughout feature dicts — consistent with pandas Float64 nullable semantics

key-files:
  created:
    - src/sip_engine/features/category_a.py
    - src/sip_engine/features/category_b.py
    - src/sip_engine/features/category_c.py
    - src/sip_engine/features/encoding.py
  modified:
    - src/sip_engine/features/__init__.py
    - tests/test_features.py

key-decisions:
  - "compute_category_c receives provider_history as pre-fetched dict (not tipo_doc/num_doc/as_of_date) — caller controls lookup, enabling test injection without mocking module-level index cache"
  - "RARE_THRESHOLD uses strictly-greater-than comparison (freq > threshold) — exactly 0.1% is treated as rare and grouped into Other"
  - "Election calendar iterated linearly (11 entries) rather than bisect — O(n) acceptable for constant-size list, simpler to verify correctness"
  - "unspsc_categoria extracts chars [0:2] of numeric part after stripping 'V1.' prefix — segment is first 2 digits in UNSPSC 8-digit code"

patterns-established:
  - "Feature extractor signature pattern: compute_category_X(row: dict, ...) -> dict — row dict keys mirror raw column names, return dict keys are feature names"
  - "NaN returned as float('nan') not pd.NA — keeps feature dicts pure Python, compatible with both pandas and XGBoost"
  - "Negative temporal durations clipped to 0 at computation time — dias_publicidad, dias_decision, dias_proveedor_registrado"
  - "Encoding Other=0 invariant: every column mapping always contains 'Other': 0 regardless of training data"

requirements-completed: [FEAT-01, FEAT-02, FEAT-03, FEAT-10]

# Metrics
duration: 5min
completed: 2026-03-01
---

# Phase 5 Plan 02: Feature Engineering Summary

**Category A/B/C feature extractors (30 features total) and categorical encoding with rare-category grouping using 0.1% threshold, alphabetical ordering, and JSON-serialized mappings for train-serve parity**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-01T22:46:04Z
- **Completed:** 2026-03-01T22:51:34Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Category A produces 10 contract features: valor_contrato, 4 categorical pass-throughs, 3 binary modality flags, UNSPSC segment extraction, has_justificacion flag
- Category B produces 9 temporal features: dias_firma_a_inicio, firma_posterior_a_inicio, duracion_contrato_dias, mes_firma, trimestre_firma, dias_a_proxima_eleccion (with 11-entry Colombian election calendar 2015-2026), dias_publicidad, dias_decision (clipped to 0), dias_proveedor_registrado (NaN when no match)
- Category C produces 11 provider/competition features: tipo_persona_proveedor (NIT→juridica), num_proponentes, num_ofertas_recibidas, proponente_unico (NaN when no procesos), plus all 6 provider history fields and num_actividades_economicas
- Encoding module: build_encoding_mappings groups rare values (<0.1%) into Other=0, assigns alphabetical codes 1-N, serializes to JSON; apply_encoding handles unseen categories (→Other=0) and NaN preservation; load_encoding_mappings enables inference-time parity
- 41 new tests (30 category + 11 encoding) added to tests/test_features.py; 159 total passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Category A/B/C feature extractors with TDD** - `96f3c66` (feat)
2. **Task 2: Categorical encoding module with TDD** - `b1e1e46` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `src/sip_engine/features/category_a.py` — 10 contract features with UNSPSC extraction and binary flags
- `src/sip_engine/features/category_b.py` — 9 temporal features with COLOMBIAN_ELECTION_DATES constant and procesos duration calculations
- `src/sip_engine/features/category_c.py` — 11 provider/competition features with provider history injection pattern
- `src/sip_engine/features/encoding.py` — Rare-category grouping, alphabetical label encoding, JSON serialization/loading
- `src/sip_engine/features/__init__.py` — Re-exports all 7 new public symbols plus existing 3
- `tests/test_features.py` — 61 total tests (up from 20), 41 new for this plan

## Decisions Made

- compute_category_c receives pre-fetched provider_history dict rather than raw doc IDs — caller controls the lookup_provider_history call, enabling test injection without mocking the module-level index cache (same principle as rcac_lookup boundary normalization)
- RARE_THRESHOLD uses strictly-greater-than (freq > threshold) — values at exactly 0.1% are treated as rare and grouped into Other
- Election calendar iterated linearly across 11 entries rather than using bisect — O(n) acceptable for constant-size list, simpler to audit
- UNSPSC segment extracted from chars [0:2] of numeric part after stripping "V1." prefix — first 2 digits in 8-digit UNSPSC code are the segment

## Deviations from Plan

None — plan executed exactly as written. All test names, behavior contracts, and implementation details followed the plan specification without requiring any auto-fixes.

## Issues Encountered

None — all tests passed on first implementation attempt.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All 30 feature extractors (Cat A/B/C) implemented and tested — pipeline.py in 05-03 can call them directly
- Encoding module complete — pipeline.py can call build_encoding_mappings() at training time and apply_encoding() at inference
- __init__.py exports all public symbols — pipeline.py only needs `from sip_engine.features import compute_category_a, compute_category_b, compute_category_c, build_encoding_mappings, apply_encoding`

## Self-Check: PASSED

- [x] `src/sip_engine/features/category_a.py` — FOUND
- [x] `src/sip_engine/features/category_b.py` — FOUND
- [x] `src/sip_engine/features/category_c.py` — FOUND
- [x] `src/sip_engine/features/encoding.py` — FOUND
- [x] `src/sip_engine/features/__init__.py` — FOUND (updated)
- [x] `.planning/phases/05-feature-engineering/05-02-SUMMARY.md` — FOUND
- [x] Commit `96f3c66` (Task 1) — FOUND
- [x] Commit `b1e1e46` (Task 2) — FOUND
- [x] 61 tests in test_features.py — ALL PASSING
- [x] 159 total tests — ALL PASSING

---
*Phase: 05-feature-engineering*
*Completed: 2026-03-01*
