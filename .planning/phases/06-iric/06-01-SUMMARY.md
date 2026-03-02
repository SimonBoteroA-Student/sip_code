---
phase: 06-iric
plan: 01
subsystem: iric
tags: [numpy, pandas, iric, corruption-index, thresholds, percentiles, viga]

# Dependency graph
requires:
  - phase: 05-feature-engineering
    provides: provider_history dict with num_contratos/num_sobrecostos/num_retrasos
  - phase: 05-feature-engineering
    provides: num_actividades_lookup (UNSPSC segment counts per provider)
  - phase: 03-rcac-builder
    provides: normalize_numero() for datos_faltantes document validation
provides:
  - compute_iric_components(row, procesos_data, provider_history, thresholds, num_actividades) -> dict of 11 binary flags
  - compute_iric_scores(components) -> dict of 4 aggregate scores (iric_score, iric_competencia, iric_transparencia, iric_anomalias)
  - calibrate_iric_thresholds(df, min_group_size=30) -> percentile thresholds by tipo_contrato
  - save_iric_thresholds / load_iric_thresholds / reset_iric_thresholds_cache
  - get_threshold() with 3-level fallback: exact -> Otro -> VigIA defaults
affects: [06-02, 06-03, 07-training]

# Tech tracking
tech-stack:
  added: [numpy.nanpercentile for NaN-safe percentile computation]
  patterns:
    - Module-level cache with reset function (same pattern as rcac_lookup, provider_history)
    - None vs 0 sentinel: components 1/6/8 return None when procesos absent; 9/10 return 0 for new providers
    - Accent-normalized modality string matching via unicodedata.normalize NFD

key-files:
  created:
    - src/sip_engine/iric/thresholds.py
    - src/sip_engine/iric/calculator.py
    - tests/test_iric.py
  modified: []

key-decisions:
  - "Components 9/10 return 0 (not None) for new providers — VigIA fills NaN as 0 (new providers not anomalous by default)"
  - "Components 1/6/8 return None when procesos_data is None — absence captured by component 11 (ausencia_proceso)"
  - "calibrate_iric_thresholds accepts arbitrary DataFrame — no hardcoded data loading; Phase 7 recalibrates on train-only data"
  - "Accent normalization via unicodedata NFD strips tildes/accents from modality strings before matching directa/regimen variants"
  - "get_threshold fallback chain: exact tipo_contrato -> Otro -> VigIA Bogota hardcoded defaults (publicidad p99=14, decision p95=43)"

patterns-established:
  - "IRIC component firing: None = data unavailable (not applicable), 0 = condition absent, 1 = condition present (red flag)"
  - "dias_publicidad and dias_decision must be injected into procesos_data by caller (already computed by Category B in pipeline)"
  - "Rare tipo_contrato merging: types with < min_group_size rows merge into 'Otro' before percentile computation"

requirements-completed: [IRIC-01, IRIC-02, IRIC-03, IRIC-06, IRIC-07, IRIC-08]

# Metrics
duration: 5min
completed: 2026-03-02
---

# Phase 6 Plan 01: IRIC Calculator + Threshold Calibration Summary

**11-component IRIC calculator (VigIA-aligned) with percentile calibration machinery — 57 TDD tests passing, None-vs-0 semantics for missing data correctly distinguishing new providers from absent process records**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-02T02:09:37Z
- **Completed:** 2026-03-02T02:14:37Z
- **Tasks:** 2
- **Files modified:** 3 (2 created + 1 test file)

## Accomplishments

- `thresholds.py`: calibrate_iric_thresholds() computes P1/P5/P95/P99 by tipo_contrato with rare-type merging (< 30 rows → "Otro"), lazy-load cache, 3-level fallback in get_threshold()
- `calculator.py`: all 11 binary IRIC components across 3 dimensions (competition/transparency/anomaly) with correct VigIA None/0 semantics; compute_iric_scores() produces 4 aggregate scores as (1/N)*sum with None→0
- 57 tests covering all edge cases: new providers (0 not NaN), missing procesos (None not 0), accent variants, rare type merging, VigIA fallback defaults

## Task Commits

1. **Task 1: thresholds.py** - `c7a038f` (feat)
2. **Task 2: calculator.py** - `babd910` (feat)

## Files Created/Modified

- `src/sip_engine/iric/thresholds.py` — calibrate_iric_thresholds, save/load/reset/get_threshold
- `src/sip_engine/iric/calculator.py` — compute_iric_components (11 components), compute_iric_scores (4 scores)
- `tests/test_iric.py` — 57 TDD tests for both modules

## Decisions Made

- Components 9/10 return 0 (not None) for new providers: VigIA pattern ("en caso de NaN al ser proveedor nuevo lo suma como 0"). New providers are not anomalous by default.
- Components 1/6/8 return None when procesos_data is None: absence is captured by component 11 (ausencia_proceso = 1). Summing None as 0 in aggregate scores is correct.
- calibrate_iric_thresholds accepts any DataFrame (no hardcoded full dataset loading). This is intentional for IRIC-08: Phase 7 must recalibrate thresholds on training data only.
- Accent normalization (unicodedata NFD) strips tildes/accents from modality strings before matching, handling "Contratación directa" and "Contratacion directa" as equivalent.
- get_threshold fallback: exact tipo_contrato → "Otro" → VigIA Bogota hardcoded defaults. VigIA values used: dias_publicidad P99=14, dias_decision P95=43, num_contratos P95=3, valor P99=500M.
- dias_publicidad and dias_decision are NOT recomputed in calculator.py — they must be injected into procesos_data by the pipeline (already computed by Category B). Avoids code duplication.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None — all components and scores implemented cleanly on first pass.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `calculator.py` and `thresholds.py` are complete and tested
- Plan 06-02 (bid anomaly stats, kurtosis + DRN) can proceed in parallel — no dependency on this plan
- Plan 06-03 (pipeline integration) depends on both 06-01 and 06-02
- Phase 7 should call `calibrate_iric_thresholds(train_df)` on training-only data and overwrite `iric_thresholds.json` before model training (IRIC-08 enforcement)

## Self-Check: PASSED

- FOUND: src/sip_engine/iric/thresholds.py
- FOUND: src/sip_engine/iric/calculator.py
- FOUND: tests/test_iric.py
- FOUND: .planning/phases/06-iric/06-01-SUMMARY.md
- FOUND commit c7a038f (Task 1)
- FOUND commit babd910 (Task 2)

---
*Phase: 06-iric*
*Completed: 2026-03-02*
