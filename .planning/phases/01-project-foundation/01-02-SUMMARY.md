---
phase: 01-project-foundation
plan: 02
subsystem: infra
tags: [python, dataclass, pathlib, configuration, settings, env-vars, xgboost, shap, requirements-lock]

# Dependency graph
requires:
  - phase: 01-01
    provides: Python 3.12.12 venv, sip-engine editable install, src/sip_engine/config/__init__.py stub
provides:
  - Settings dataclass in src/sip_engine/config/settings.py — single source of truth for all paths, encodings, constants
  - get_settings() singleton via functools.lru_cache
  - SIP_PROJECT_ROOT / SIP_SECOP_DIR / SIP_PACO_DIR / SIP_ARTIFACTS_DIR env var overrides
  - model_weights.json — CRI weights for M1-M4 + IRIC (equal 0.20 each, sums to 1.0)
  - requirements.lock — exact pip freeze of all 36 installed packages
affects: [all phases — every phase imports Settings for file paths and constants]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Path(__file__).resolve() for CWD-independent path resolution — never os.getcwd()"
    - "dataclass with __post_init__ for derived field computation and env var override injection"
    - "functools.lru_cache on get_settings() for cheap singleton access"
    - "SIP_* env var prefix convention for all runtime overrides"

key-files:
  created:
    - src/sip_engine/config/settings.py
    - src/sip_engine/config/model_weights.json
    - requirements.lock
  modified:
    - src/sip_engine/config/__init__.py

key-decisions:
  - "Path(__file__).resolve() used (not os.getcwd()) — ensures Settings works from any working directory, including subprocesses and test runners"
  - "SIP_* env var overrides applied in __post_init__ after defaults set — allows partial override (e.g. only SIP_ARTIFACTS_DIR) without affecting other paths"
  - "model_weights.json is a committed, user-editable file — not hardcoded in Python — so CRI weight tuning requires no code change"
  - "requirements.lock generated via pip freeze (not pip-compile) — captures exact transitive versions of all 36 packages actually installed"

patterns-established:
  - "All business logic accesses paths via Settings attributes — zero hardcoded paths in any non-settings file"
  - "Per-file paths derived from directory paths inside __post_init__ — changing SIP_SECOP_DIR automatically updates all 9 SECOP CSV paths"

requirements-completed: [PROJ-02]

# Metrics
duration: 2min
completed: 2026-03-01
---

# Phase 1 Plan 02: Configuration System Summary

**CWD-independent Settings dataclass with SIP_* env var overrides, equal CRI model weights (0.20 x 5), and pip-frozen requirements.lock — all 7 Phase 1 verification checks pass**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-01T05:46:00Z
- **Completed:** 2026-03-01T05:47:28Z
- **Tasks:** 2 of 2
- **Files modified:** 4

## Accomplishments
- Settings dataclass resolves 9 SECOP paths, 5 PACO paths, 5 artifact subdirs, and all artifact file paths from any working directory via Path(__file__).resolve()
- SIP_PROJECT_ROOT / SIP_SECOP_DIR / SIP_PACO_DIR / SIP_ARTIFACTS_DIR env var overrides verified working
- model_weights.json with 5 equal weights (0.20 each) summing to 1.0, user-editable without code changes
- requirements.lock capturing exact versions of all 36 installed packages for reproducibility
- All 7 Phase 1 verification checks pass (Python 3.12.12, XGBoost/SHAP, settings, weights, CLI, editable install, lock file)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create settings.py with dataclass configuration and env var overrides** - `b8ce286` (feat)
2. **Task 2: Create model_weights.json, generate requirements.lock, run full verification** - `dd01e3a` (feat)

**Plan metadata:** _(docs commit follows)_

## Files Created/Modified
- `src/sip_engine/config/settings.py` - Settings dataclass, _project_root(), get_settings() singleton
- `src/sip_engine/config/__init__.py` - Updated to export Settings and get_settings
- `src/sip_engine/config/model_weights.json` - CRI weights: m1_cost_overruns, m2_delays, m3_comptroller, m4_fines, iric (all 0.20)
- `requirements.lock` - pip freeze output, 36 packages with exact versions

## Decisions Made
- **Path(__file__).resolve() for root detection:** Plan explicitly required this (not os.getcwd()) — ensures the project runs correctly from any working directory including test runners, subprocesses, and IDE integrations.
- **model_weights.json as committed file:** Weights are operationally tunable without code changes — a user or researcher can adjust CRI component weights by editing JSON.
- **pip freeze for lock file:** Captures all 36 transitively-installed packages at exact versions. pip-compile was not used to avoid adding another dev dependency.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
None — all 6 task verification checks and all 7 plan-level checks passed on first run.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Phase 2 (Data Loaders) can begin immediately — Settings provides all 9 SECOP and 5 PACO CSV paths
- Phase 3 (RCAC Builder) has all PACO paths ready via siri_path, responsabilidades_fiscales_path, etc.
- All phases can import `from sip_engine.config import get_settings` to access any path or constant

## Self-Check: PASSED

Files verified:
- src/sip_engine/config/settings.py: FOUND
- src/sip_engine/config/model_weights.json: FOUND
- requirements.lock: FOUND

Commits verified:
- b8ce286: FOUND (Task 1 — feat(01-02): add Settings dataclass)
- dd01e3a: FOUND (Task 2 — feat(01-02): add model_weights.json and requirements.lock)

---
*Phase: 01-project-foundation*
*Completed: 2026-03-01*
