---
phase: 03-rcac-builder
plan: 01
subsystem: data
tags: [rcac, normalization, deduplication, joblib, tdd, pandas, unicodedata]

# Dependency graph
requires:
  - phase: 02-data-loaders
    provides: 14 generator-based CSV loaders (load_boletines, load_paco_siri, load_paco_resp_fiscales, load_paco_multas, load_paco_colusiones)
  - phase: 01-project-foundation
    provides: Settings dataclass with rcac_path, artifacts_rcac_dir; get_settings() singleton

provides:
  - normalize_numero(raw) -> str — strip all non-digit chars, handle NaN/None
  - is_malformed(numero) -> bool — empty/all-zeros/length<3 rejection
  - normalize_tipo(raw) -> str — accent-insensitive mapping to CC/NIT/CE/PASAPORTE/OTRO
  - _infer_tipo(name, numero) -> str — company keyword + 9-digit NIT heuristic
  - Source extractors: _extract_boletines, _extract_siri, _extract_resp_fiscales, _extract_multas, _extract_colusiones
  - build_rcac(force=False) -> Path — full pipeline with dedup, bad-rows CSV, joblib pkl, cache
  - Settings.rcac_bad_rows_path attribute (artifacts/rcac/rcac_bad_rows.csv)
  - 34 TDD tests in tests/test_rcac.py covering all normalization and builder behaviors

affects:
  - 03-02: lookup module reads rcac.pkl built by build_rcac()
  - 04-label-construction: M4 label uses en_multas_secop flag; all labels query rcac_lookup()
  - 05-feature-engineering: RCAC flag features derived from lookup results
  - 09-explainability: CRI score uses RCAC as one of 5 signals

# Tech tracking
tech-stack:
  added: [joblib (serialization), unicodedata (accent stripping), re (digit normalization), csv (bad-rows writer)]
  patterns:
    - TDD red-green: write failing tests first, implement to pass
    - Source-flag deduplication: defaultdict(set) keyed on (tipo, num) collects source sets
    - NaN-safe normalization: try/except pd.isna() around all scalar checks
    - Accent stripping: unicodedata.normalize("NFD") + filter Mn category chars

key-files:
  created:
    - src/sip_engine/data/rcac_builder.py
    - tests/test_rcac.py
  modified:
    - src/sip_engine/config/settings.py

key-decisions:
  - "normalize_numero uses re.sub(r'[^\\d]', '', str(raw)) — strips ALL non-digits including letters"
  - "is_malformed rejects: empty, all-zeros (set check), or fewer than 3 digits"
  - "normalize_tipo uses _strip_accents (unicodedata NFD) before keyword matching — handles CÉDULA DE CIUDADANÍA and CEDULA DE CIUDADANIA equally"
  - "_infer_tipo checks 14 company keywords (LTDA, SAS, S.A., COOPERATIVA, etc.) then falls back to 9-digit NIT heuristic"
  - "resp_fiscales 'Tipo y Num Docuemento' is purely numeric — normalize_numero() sufficient, no splitting needed (confirmed by CONTEXT.md)"
  - "en_sanciones_penales is always False — FGN source has no person-level document IDs (v1 limitation)"
  - "Bad rows written to rcac_bad_rows.csv with columns: source, tipo_documento_raw, numero_documento_raw, reason"
  - "build_rcac() uses cache by default (checks pkl mtime), force=True triggers full rebuild"

patterns-established:
  - "Source extractors return (tipo_norm, num_norm, source_flag, raw_tipo, raw_num) 5-tuples for auditability"
  - "All normalization functions are pure — no side effects, testable in isolation"
  - "Settings attributes for artifact paths added as both field declaration (default=None) and __post_init__ assignment"

requirements-completed: [DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-08]

# Metrics
duration: 4min
completed: 2026-03-01
---

# Phase 3 Plan 01: RCAC Normalization Engine and Builder Summary

**Document normalization engine (normalize_numero/tipo/_infer_tipo) + build_rcac() pipeline with dedup via defaultdict(set), bad-rows CSV audit log, and joblib pkl serialization — 34 TDD tests, 59 total passing**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-01T16:05:00Z
- **Completed:** 2026-03-01T16:08:27Z
- **Tasks:** 2 (RED + GREEN TDD cycle)
- **Files modified:** 3

## Accomplishments
- Implemented full RCAC normalization: `normalize_numero` strips non-digits, `is_malformed` catches empty/zeros/short, `normalize_tipo` maps 10+ raw Colombian document type strings to CC/NIT/CE/PASAPORTE/OTRO with accent normalization
- Built `build_rcac()` pipeline: extracts from 5 sources, deduplicates via `defaultdict(set)` keyed on `(tipo, num)`, writes malformed to bad-rows CSV, serializes index via joblib, with cache/force-rebuild semantics
- 34 new tests (normalization, tipo mapping, tipo inference, dedup, serialization, bad-rows, cache) all passing; 59 total (zero regressions from Phase 1/2)

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — Write failing tests for normalization, builder, and deduplication** - `70d8f32` (test)
2. **Task 2: GREEN — Implement rcac_builder.py to pass all tests** - `2218d19` (feat)

_Note: TDD plan — 2 commits (test RED -> feat GREEN)_

## Files Created/Modified
- `src/sip_engine/data/rcac_builder.py` (248 lines) — normalize_numero, is_malformed, normalize_tipo, _infer_tipo, 5 source extractors, build_rcac()
- `tests/test_rcac.py` (~300 lines) — 34 tests with rcac_source_dirs fixture (tiny CSV files + monkeypatched env vars)
- `src/sip_engine/config/settings.py` — added `rcac_bad_rows_path` field and `__post_init__` assignment

## Decisions Made
- `resp_fiscales` "Tipo y Num Docuemento" field is purely numeric — CONTEXT.md clarifies no splitting needed, just `normalize_numero()` to extract digits
- Company keyword list for `_infer_tipo`: 14 keywords including LTDA, SAS, S.A., COOPERATIVA, FUNDACION, UNION TEMPORAL, CONSORCIO, E.S.P, E.S.E, E.I.C.E, SOCIEDAD
- Bad-rows CSV reason field uses three values: "empty", "all_zeros", "too_short"
- `_infer_tipo` for 9-digit threshold: Colombian NITs are 9 digits, CCs are typically 6-10 but company keyword check takes precedence

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed incorrect expected key in test_build_dedup_duplicate_rows_same_source**
- **Found during:** Task 2 (GREEN phase, running tests)
- **Issue:** Test expected `("CC", "900654321")` for the second SIRI fixture row, but that row has `tipo=NIT` (from the raw CSV), which `normalize_tipo("NIT")` maps to `"NIT"` — so the correct key is `("NIT", "900654321")`
- **Fix:** Updated test to assert `("NIT", "900654321")` in index with `en_siri=True`, `num_fuentes_distintas=1`
- **Files modified:** tests/test_rcac.py
- **Verification:** All 34 tests pass after fix
- **Committed in:** `2218d19` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in test fixture key)
**Impact on plan:** Test logic correction only — no implementation changes. Implementation was correct; test had wrong expected key.

## Issues Encountered
None beyond the test key deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `build_rcac()` and all normalization functions are ready
- Plan 03-02 can now implement `rcac_lookup.py` (O(1) dict lookup interface) and wire up the `build-rcac` CLI subcommand
- The pkl artifact path and bad-rows path are both in Settings, ready for 03-02 to import

---
*Phase: 03-rcac-builder*
*Completed: 2026-03-01*
