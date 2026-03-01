---
phase: 03-rcac-builder
plan: 02
subsystem: data
tags: [rcac, lookup, joblib, cli, argparse, lazy-loading]

# Dependency graph
requires:
  - phase: 03-01
    provides: rcac_builder.py with build_rcac(), normalize_tipo(), normalize_numero(), is_malformed()
provides:
  - O(1) RCAC lookup via rcac_lookup(tipo_doc, num_doc) — lazy-loads pkl on first call
  - get_rcac_index() for bulk index access
  - reset_rcac_cache() for test isolation
  - CLI: python -m sip_engine build-rcac [--force] dispatches to build_rcac()
  - Package re-exports: rcac_lookup and build_rcac importable from sip_engine.data
affects:
  - 04-label-construction
  - 05-feature-engineering

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-level cache: _rcac_index global, loaded lazily on first call, reset via reset_rcac_cache() for test isolation"
    - "Input normalization at lookup boundary: callers pass raw strings, normalize_tipo/numero called internally"
    - "CLI dispatch: if args.command == 'build-rcac' pattern with try/except and sys.exit codes"

key-files:
  created:
    - src/sip_engine/data/rcac_lookup.py
  modified:
    - src/sip_engine/__main__.py
    - src/sip_engine/data/__init__.py
    - tests/test_rcac.py

key-decisions:
  - "Normalization at lookup boundary: rcac_lookup() calls normalize_tipo/normalize_numero internally so callers never need to pre-normalize"
  - "Malformed check before index touch: is_malformed() short-circuits before loading/querying index for speed and correctness"
  - "reset_rcac_cache() as autouse teardown fixture: ensures module-level _rcac_index doesn't bleed between tests"

patterns-established:
  - "Module-level singleton with explicit reset function: used for RCAC index cache, mirrors get_settings() lru_cache pattern"
  - "Lazy loading via global guard: if _rcac_index is None: call _load_rcac() — defer I/O to first use"

requirements-completed: [DATA-09]

# Metrics
duration: 2min
completed: 2026-03-01
---

# Phase 3 Plan 02: RCAC Lookup and CLI Wiring Summary

**Lazy-loading O(1) RCAC lookup via joblib pkl with input normalization, malformed rejection, and CLI build-rcac --force dispatch**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-01T16:11:41Z
- **Completed:** 2026-03-01T16:13:31Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- `rcac_lookup(tipo_doc, num_doc)` returns full record dict for known identities in O(1) via in-memory dict, normalizes inputs internally, returns None for unknown/malformed identities
- RCAC index loaded lazily from `artifacts/rcac/rcac.pkl` on first lookup call and cached in module state; `reset_rcac_cache()` enables clean test isolation
- CLI `python -m sip_engine build-rcac [--force]` fully dispatched to `build_rcac()` with `--force` flag, proper exit codes (0 on success, 1 on error)
- `rcac_lookup` and `build_rcac` re-exported from `sip_engine.data` — importable from top-level package
- 6 new lookup tests added; total test suite 65 tests, all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Create rcac_lookup module with lazy-loading O(1) lookup** - `4bcaaa5` (feat)
2. **Task 2: Wire CLI build-rcac command and package exports** - `9ead738` (feat)

**Plan metadata:** (pending docs commit)

## Files Created/Modified
- `src/sip_engine/data/rcac_lookup.py` - New module: `_load_rcac()`, `get_rcac_index()`, `reset_rcac_cache()`, `rcac_lookup()`; lazy loads pkl, normalizes inputs, rejects malformed
- `src/sip_engine/__main__.py` - Added `--force` arg to build-rcac subparser; replaced generic "not implemented" with real dispatch to `build_rcac()`
- `src/sip_engine/data/__init__.py` - Added `build_rcac` and `rcac_lookup` imports and `__all__` entries
- `tests/test_rcac.py` - Added 6 lookup tests (hit, miss, input normalization, malformed rejection, en_multas_secop flag, FileNotFoundError without pkl); added autouse `_reset_rcac` fixture

## Decisions Made
- Normalization at lookup boundary: `rcac_lookup()` always normalizes inputs via the same `normalize_tipo`/`normalize_numero` from `rcac_builder`, so callers never need to know normalization details.
- `is_malformed()` called before index access: short-circuits immediately for empty/all-zero/short numbers without touching the index.
- `reset_rcac_cache()` autouse teardown fixture added at module level (not class level) in test file — applies to all lookup tests without needing an explicit class.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 3 (RCAC Builder) is now complete: normalization engine, builder, deduplication, serialization (03-01) and lookup interface + CLI (03-02) all implemented.
- Phase 4 (Label Construction) can now import `rcac_lookup` from `sip_engine.data` to flag contractor corruption background in M1/M2 labels.
- Blocker: `adiciones.csv` still downloading — Phase 4 labels (M1/M2) are blocked until this file is available. Confirm download before executing Phase 4.

---
*Phase: 03-rcac-builder*
*Completed: 2026-03-01*
