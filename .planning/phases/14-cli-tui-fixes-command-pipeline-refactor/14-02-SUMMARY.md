---
phase: 14-cli-tui-fixes-command-pipeline-refactor
plan: 02
subsystem: cli
tags: [pipeline, refactor, cli, coordinator, dataclass]
dependency_graph:
  requires: []
  provides: [pipeline_coordinator, pipeline_config, start_from_resume]
  affects: [run-pipeline, build-rcac, build-labels, build-iric]
tech_stack:
  added: []
  patterns: [coordinator-pattern, frozen-dataclass-config, lazy-imports, dynamic-dispatch]
key_files:
  created:
    - src/sip_engine/pipeline.py
    - tests/classifiers/test_pipeline.py
  modified:
    - src/sip_engine/__main__.py
decisions:
  - Dynamic function resolution via getattr + _STEP_FN_NAMES dict instead of cached _STEP_FNS — enables proper unittest.mock.patch support
  - Only refactored simple standalone commands (build-rcac, build-labels, build-iric) to pipeline functions — complex commands (train, evaluate, build-features) kept inline for backward compatibility with their interactive paths
  - Config banner printed by run_pipeline() orchestrator — eliminates duplicate config printing logic
metrics:
  duration: "36 min"
  completed: "2026-03-06"
  tasks_completed: 2
  files_created: 2
  files_modified: 1
---

# Phase 14 Plan 2: Command Pipeline Refactor Summary

Pipeline coordinator module with PipelineConfig frozen dataclass, 6 run_*() functions with lazy imports, and run_pipeline() orchestrator with --start-from resume support.

## What Was Built

### pipeline.py (New)

New module at `src/sip_engine/pipeline.py` (232 lines) providing:

- **`PipelineConfig`** — frozen dataclass with 10 fields (n_jobs, n_iter, cv_folds, max_ram_gb, device, force, model, quick, disable_rocm, show_stats)
- **`STEP_NAMES`** — tuple of 6 step names in execution order: rcac → labels → features → iric → train → evaluate
- **`_STEP_LABELS`** — display labels with step numbers (e.g. "[1/6] RCAC")
- **`run_rcac(cfg)`** — lazy imports build_rcac, delegates with cfg.force
- **`run_labels(cfg)`** — lazy imports build_labels, delegates with cfg.force
- **`run_features(cfg)`** — lazy imports build_features, passes n_jobs/max_ram_gb/device/interactive=False
- **`run_iric(cfg)`** — lazy imports build_iric, delegates with cfg.force
- **`run_train(cfg)`** — lazy imports train_model + MODEL_IDS, iterates over models, returns list[Path]
- **`run_evaluate(cfg)`** — lazy imports evaluator, dispatches single model vs evaluate_all
- **`run_pipeline(cfg, start_from)`** — orchestrator: validates start_from, prints config banner + step banners, calls run_*() per step, shows ✓ success lines, prints completion Panel

### __main__.py (Refactored)

Reduced from 584 to 539 lines:

- **run-pipeline block**: Replaced ~120 lines of inline step calls with `run_pipeline(cfg, start_from=args.start_from)` — single function call
- **--start-from flag**: Added `--start-from {rcac,labels,features,iric,train,evaluate}` to run-pipeline subparser
- **build-rcac**: Now uses `PipelineConfig + run_rcac(cfg)` instead of direct import
- **build-labels**: Now uses `PipelineConfig + run_labels(cfg)` instead of direct import
- **build-iric**: Now uses `PipelineConfig + run_iric(cfg)` instead of direct import
- **build-features, train, evaluate**: Kept existing inline logic for backward compatibility (complex interactive paths)

### test_pipeline.py (New)

21 unit tests across 4 test classes:

- **TestPipelineConfig** (3 tests) — creation with defaults, custom values, frozen immutability
- **TestStepRegistry** (6 tests) — STEP_NAMES count/order, _STEP_LABELS, _STEP_FNS, _STEP_FN_NAMES, callable check
- **TestRunFunctions** (8 tests) — each run_*() delegates correctly (mocked domain modules)
- **TestRunPipeline** (4 tests) — invalid start_from raises ValueError, full pipeline calls all steps, start_from skips earlier steps

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Dynamic function dispatch for mockability**
- **Found during:** Task 1 (test execution)
- **Issue:** `_STEP_FNS` dict cached function references at module import time; `unittest.mock.patch` on module-level names didn't affect the cached dict, causing tests to call real domain modules and hang indefinitely
- **Fix:** Added `_STEP_FN_NAMES` dict mapping step names → function name strings; `run_pipeline` resolves functions via `getattr(module, name)` at call time
- **Files modified:** src/sip_engine/pipeline.py, tests/classifiers/test_pipeline.py
- **Commit:** c3357f5

## Verification Results

- `pytest tests/classifiers/test_pipeline.py tests/classifiers/test_ui.py -x -q` → 41 passed
- `python -m sip_engine --help` → shows all 10 commands
- `python -m sip_engine run-pipeline --help` → shows --start-from and --force flags
- `python -m sip_engine build-rcac --help` → still works
- `python -m sip_engine train --help` → shows all existing flags
- `grep -c "from sip_engine.pipeline import" __main__.py` → 4 (run-pipeline + 3 simple commands)
- `grep "def run_pipeline" pipeline.py` → confirms orchestrator exists
- `grep "class PipelineConfig" pipeline.py` → confirms dataclass exists

## Task Commits

| Task | Description | Commit | Key Files |
|------|-------------|--------|-----------|
| 1 | Create pipeline.py coordinator with PipelineConfig and step functions | c3357f5 | src/sip_engine/pipeline.py, tests/classifiers/test_pipeline.py |
| 2 | Refactor __main__.py to thin dispatch via pipeline.py | d4e6d5e | src/sip_engine/__main__.py |

## Self-Check: PASSED

All files exist, all commits verified.
