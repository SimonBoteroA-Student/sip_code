---
phase: 06-iric
plan: 03
subsystem: iric
tags: [iric, pipeline, feature-engineering, category-d, cli, parquet, batch, online-inference]

# Dependency graph
requires:
  - phase: 06-iric plan: 01
    provides: compute_iric_components, compute_iric_scores, calibrate/load/save_iric_thresholds
  - phase: 06-iric plan: 02
    provides: compute_bid_stats, build_bid_stats_lookup
  - phase: 05-feature-engineering
    provides: build_provider_history_index, lookup_provider_history, FEATURE_COLUMNS (30)
  - phase: 04-label-construction
    provides: labels.parquet (required for provider history index)
provides:
  - build_iric(force) -> iric_scores.parquet (11 components + 4 scores + kurtosis + DRN per contract)
  - compute_iric(contract_row, ...) -> online IRIC function with identical logic
  - FEATURE_COLUMNS: 34 entries (adds iric_anomalias, iric_competencia, iric_score, iric_transparencia)
  - build-iric CLI subcommand
  - iric/__init__.py: all 11 public symbols re-exported
affects: [07-training]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Path-check before load to avoid stale module-level threshold cache across test runs
    - Lazy import of iric.pipeline from features.pipeline avoids circular dependency
    - Category D injected after Cat A/B/C encoding; Cat D values bypass encoding (already float)

key-files:
  created:
    - src/sip_engine/iric/pipeline.py
  modified:
    - src/sip_engine/config/settings.py
    - src/sip_engine/features/pipeline.py
    - src/sip_engine/iric/__init__.py
    - src/sip_engine/__main__.py
    - tests/test_iric.py
    - tests/test_features.py

key-decisions:
  - "iric_scores_path added to Settings derived from artifacts_iric_dir (same pattern as all artifact paths)"
  - "build_features() checks settings.iric_thresholds_path existence BEFORE calling load_iric_thresholds() — avoids stale module-level cache hitting wrong path in test isolation"
  - "kurtosis (curtosis_licitacion) and DRN (diferencia_relativa_norm) excluded from FEATURE_COLUMNS — NaN-heavy due to ~60% direct contracting share; stored in iric_scores.parquet artifact only"
  - "compute_features() accepts optional iric_thresholds and bid_values for flexibility; falls back gracefully to NaN if thresholds not yet built"
  - "iric.pipeline imports features.provider_history at function call time (lazy) to avoid circular import at module level"

requirements-completed: [FEAT-04]

# Metrics
duration: 12min
completed: 2026-03-01
tasks_completed: 2
tasks_total: 2
files_created: 1
files_modified: 6
tests_added: 80
---

# Phase 6 Plan 03: IRIC Pipeline Integration + CLI Summary

**IRIC wired into production pipeline: build_iric() batch orchestrator + compute_iric() online function + Category D (4 features) injected into FEATURE_COLUMNS (30 -> 34) + build-iric CLI + iric/__init__.py re-exports — 290 total tests passing**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-03-01
- **Tasks:** 2 of 2
- **Files modified:** 7 (1 new + 6 modified)
- **Tests added:** 80 (64 iric total + 16 feature count/Cat D + 3 warnings excluded)

## Accomplishments

### Task 1: iric/pipeline.py
- `build_iric(force)`: Full batch orchestrator — calibrates IRIC thresholds from features.parquet (or loads cached), builds bid stats lookup from ofertas, builds procesos/num_actividades lookups, streams contratos, computes 11 components + 4 scores + kurtosis + DRN per contract, writes `iric_scores.parquet`.
- `compute_iric(contract_row, ...)`: Online inference function for train-serve parity. Wraps `compute_iric_components` + `compute_iric_scores` + `compute_bid_stats`. Returns 18-key dict (11 components + 4 scores + 3 bid stats).
- `iric_scores_path` added to Settings (derived from `artifacts_iric_dir / "iric_scores.parquet"`).

### Task 2: Category D injection + exports + CLI
- `FEATURE_COLUMNS`: 30 → 34 entries. Added Category D in alphabetical order: `iric_anomalias`, `iric_competencia`, `iric_score`, `iric_transparencia`. Kurtosis/DRN excluded (NaN-heavy).
- `build_features()`: Loads IRIC thresholds via path-check (cache-safe), computes Cat D per row; falls back to NaN if thresholds not built yet. Bid stats lookup built from ofertas when thresholds available.
- `compute_features()`: New optional `iric_thresholds` and `bid_values` parameters; Cat D computed inline with path-checked threshold loading.
- `iric/__init__.py`: All 11 public symbols re-exported from 4 submodules (calculator, bid_stats, thresholds, pipeline).
- `__main__.py`: `build-iric` subcommand registered with `--force` flag, lazy import pattern.
- `tests/test_features.py`: Updated 3 hardcoded-30 references to 34.
- `tests/test_iric.py`: 23 new tests for Cat D membership, alphabetical order, __init__ exports, CLI.

## Task Commits

1. **Task 1: iric/pipeline.py** - `e9a7db4` (feat)
2. **Task 2: Category D + exports + CLI** - `c822961` (feat)

## Files Created/Modified

- `src/sip_engine/iric/pipeline.py` (new) — build_iric, compute_iric, helper lookups
- `src/sip_engine/config/settings.py` — iric_scores_path field + __post_init__ derivation
- `src/sip_engine/features/pipeline.py` — FEATURE_COLUMNS 34, build_features/compute_features Cat D
- `src/sip_engine/iric/__init__.py` — full re-exports for all 11 public symbols
- `src/sip_engine/__main__.py` — build-iric CLI subcommand
- `tests/test_iric.py` — 23 new tests (pipeline + Cat D + exports + CLI)
- `tests/test_features.py` — updated 3 count assertions from 30 to 34

## Decisions Made

- `iric_scores_path` derived in `Settings.__post_init__` following the exact same pattern as all other artifact paths.
- Path existence check before `load_iric_thresholds()` in `build_features()` prevents stale module-level cache from returning wrong-path thresholds during test isolation. The `reset_iric_thresholds_cache()` + explicit path argument ensures each test gets a fresh load from the correct temp directory.
- Kurtosis and DRN excluded from `FEATURE_COLUMNS` per design decision in MEMORY.md and RESEARCH.md: ~60% of contracts are direct contracting (0-1 bids), making these stats NaN-heavy and inappropriate as model inputs. They are stored in `iric_scores.parquet` artifact for analytical use.
- `compute_features()` gracefully falls back to NaN for Category D if thresholds not built. This allows `build_features()` to succeed as a standalone step even before `build_iric()` is run (with a warning).
- Lazy imports of `sip_engine.iric.pipeline` inside function bodies (not module top-level) prevent circular dependency: `iric.pipeline` imports `features.provider_history` at module load time; if `features.pipeline` imported `iric.pipeline` at module top-level this would create a circular import.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stale IRIC thresholds module-level cache in build_features() tests**

- **Found during:** Task 2 (first test run)
- **Issue:** `TestBuildIricCreatesParquet.test_build_iric_creates_parquet` in test_iric.py creates real iric thresholds in a temp dir and loads them into the module-level `_thresholds_cache`. The subsequent `test_build_features_creates_parquet` test runs `build_features()` which calls `load_iric_thresholds()` — and gets the CACHED thresholds from the previous test instead of raising FileNotFoundError for the new temp dir. This caused `_build_bid_stats_lookup()` to be called, which tried to open `ofertas_proceso_SECOP.csv` (not present in the _make_pipeline_env test setup), raising FileNotFoundError.
- **Fix:** Changed `build_features()` to check `settings.iric_thresholds_path.exists()` before calling `load_iric_thresholds()`. Added `reset_iric_thresholds_cache()` + explicit path argument so each call loads from the path matching the current settings instance. Same pattern applied to `compute_features()`.
- **Files modified:** src/sip_engine/features/pipeline.py
- **Commit:** c822961 (included in main task commit)

## Issues Encountered

None beyond the auto-fixed stale cache issue above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 6 is now COMPLETE (3/3 plans):
  - 06-01: calculator.py + thresholds.py
  - 06-02: bid_stats.py
  - 06-03: pipeline.py + feature integration + CLI
- Phase 7 (Model Training) can proceed:
  - Must call `calibrate_iric_thresholds(train_df)` + `save_iric_thresholds()` on training-only data before training (IRIC-08)
  - Split: RANDOM (not temporal), per MEMORY.md decision
  - Feature vector is now 34-dimensional (FEATURE_COLUMNS)
  - `build_iric(force=True)` after recalibration will produce corrected iric_scores.parquet

## Self-Check: PASSED

- FOUND: src/sip_engine/iric/pipeline.py
- FOUND: src/sip_engine/config/settings.py (modified)
- FOUND: src/sip_engine/features/pipeline.py (modified)
- FOUND: src/sip_engine/iric/__init__.py (modified)
- FOUND: src/sip_engine/__main__.py (modified)
- FOUND commit e9a7db4 (Task 1)
- FOUND commit c822961 (Task 2)
- 290/290 tests passing

---
*Phase: 06-iric*
*Completed: 2026-03-01*
