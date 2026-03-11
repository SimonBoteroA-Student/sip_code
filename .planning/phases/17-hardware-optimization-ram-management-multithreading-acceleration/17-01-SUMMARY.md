---
phase: 17
plan: "01"
title: "MemoryMonitor Foundation, Loaders & Pipeline Wiring"
subsystem: "shared/memory, loaders, pipeline"
tags: ["memory-management", "hardware-optimization", "chunked-loading", "pipeline"]
dependency_graph:
  requires: []
  provides: ["shared/memory.py MemoryMonitor API", "chunk_size loader passthrough", "n_jobs/max_ram_gb pipeline wiring"]
  affects: ["loaders.py", "label_builder.py", "iric/pipeline.py", "pipeline.py"]
tech_stack:
  added: ["psutil (existing dep, now used in MemoryMonitor)"]
  patterns: ["MemoryMonitor check() → ok/warning/critical status", "adaptive_chunk_size() halving with floor", "atomic Parquet checkpoints via safe_rename", "generator-based loader chunk_size override"]
key_files:
  created:
    - src/sip_engine/shared/memory.py
    - tests/shared/test_memory.py
  modified:
    - src/sip_engine/shared/data/loaders.py
    - src/sip_engine/shared/data/label_builder.py
    - src/sip_engine/classifiers/iric/pipeline.py
    - src/sip_engine/pipeline.py
    - tests/classifiers/test_pipeline.py
decisions:
  - "load_checkpoint returns (empty_df, empty_set) for missing file — callers do not need to handle FileNotFoundError"
  - "MemoryMonitor uses psutil.Process().memory_info().rss for RSS — consistent with Phase 12 hardware detection"
  - "adaptive_chunk_size uses max(halved, min_chunk_size) at warning — prevents zero-size chunks"
  - "n_jobs/max_ram_gb accepted but unused in build_labels/build_iric until Plan 17-02"
metrics:
  duration: "~7 minutes"
  completed: "2026-03-11"
  tasks_completed: 4
  files_changed: 7
---

# Phase 17 Plan 01: MemoryMonitor Foundation, Loaders & Pipeline Wiring Summary

**One-liner:** RAM budget enforcement via MemoryMonitor (ok/warning/critical) + adaptive chunk sizing + Parquet checkpoints + chunk_size passthrough to all CSV loaders + n_jobs/max_ram_gb wired through pipeline.

## What Was Built

### Task 1 — `src/sip_engine/shared/memory.py` (NEW)
Core memory management module:
- **`MemoryMonitor`** class — tracks RSS against a `max_ram_gb` budget; `check()` returns `'ok'` (<90%), `'warning'` (90-100%), `'critical'` (≥100%)
- **`adaptive_chunk_size()`** — returns base size if ok, halved at warning (floor-clamped), `min_chunk_size` if critical
- **`save_checkpoint()` / `load_checkpoint()` / `remove_checkpoint()`** — atomic Parquet checkpoint round-trip using `compat.safe_rename`; `load_checkpoint` returns `(empty_df, empty_set)` for missing files
- **`cleanup(*objects)`** — dereferences objects and calls `gc.collect()` once

### Task 2 — `loaders.py` chunk_size passthrough
All 14 public `load_*()` functions and `_load_csv()` accept optional `chunk_size: int | None = None`. When `None`, falls back to `settings.chunk_size` (existing behaviour preserved). HW-06 requirement satisfied.

### Task 3 — Extended signatures + pipeline wiring
- `build_labels(force, n_jobs=1, max_ram_gb=None)` — extended (params accepted, no-op until 17-02)
- `build_iric(force, n_jobs=1, max_ram_gb=None)` — extended (params accepted, no-op until 17-02)
- `run_labels(cfg)` — now passes `n_jobs=cfg.n_jobs, max_ram_gb=cfg.max_ram_gb`
- `run_iric(cfg)` — now passes `n_jobs=cfg.n_jobs, max_ram_gb=cfg.max_ram_gb`

### Task 4 — Unit tests (`tests/shared/test_memory.py`)
22 new tests covering: MemoryMonitor thresholds (ok/warning/critical + boundary conditions), usage_ratio calculation, adaptive_chunk_size (all states + floor enforcement), checkpoint roundtrip + empty rows + missing id_contrato column, remove_checkpoint (existing + nonexistent), load_nonexistent_checkpoint (returns empty df/set), cleanup gc.collect() calls.

## Verification Results

All 535 tests pass (1 skipped — pre-existing pyarrow skip).

```
535 passed, 1 skipped, 3 warnings in 31.67s
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_pipeline.py call assertions after pipeline wiring**
- **Found during:** Task 4 full test suite run
- **Issue:** `test_run_labels` and `test_run_iric` in `tests/classifiers/test_pipeline.py` expected `build_labels(force=True)` / `build_iric(force=True)` but Task 3 wired `n_jobs` and `max_ram_gb` through, changing the call to include those kwargs
- **Fix:** Updated both test assertions to `assert_called_once_with(force=True, n_jobs=2, max_ram_gb=4)` matching the PipelineConfig fixture
- **Files modified:** `tests/classifiers/test_pipeline.py`
- **Commit:** a9ec6b5

**2. [Rule 1 - Bug] Fixed boundary test for 90% MemoryMonitor threshold**
- **Found during:** Task 4 (first test run)
- **Issue:** `test_check_at_90_percent_boundary` used `int(budget_bytes * 0.90)` which truncates to just below 90%, making `check()` return `'ok'` instead of `'warning'`
- **Fix:** Added `+1` byte to ensure the RSS value is at or above the 90% boundary
- **Files modified:** `tests/shared/test_memory.py`
- **Commit:** a9ec6b5

## Commits

| Hash | Message |
|------|---------|
| 88470b3 | feat(17-01): create shared/memory.py — MemoryMonitor + utilities |
| 04648b4 | feat(17-01): add chunk_size parameter to all CSV loaders |
| e2d698e | feat(17-01): extend build signatures and wire pipeline.py |
| a9ec6b5 | test(17-01): add unit tests for memory.py; fix test_pipeline.py call assertions |

## Self-Check: PASSED
