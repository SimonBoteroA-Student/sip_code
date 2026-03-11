---
phase: 17
plan: "03"
title: "Multiprocessing Acceleration"
subsystem: "shared/memory, label_builder, iric/pipeline, features/pipeline"
tags: ["multiprocessing", "hardware-optimization", "parallelism", "worker-pool"]
dependency_graph:
  requires: ["shared/memory.py MemoryMonitor API (17-01)", "RAM-budgeted build functions (17-02)"]
  provides: ["Pool.imap_unordered dispatch in all 3 build steps", "cross-platform worker pool utilities", "serialize_lookups/_init_worker/get_shared_lookups/create_worker_pool"]
  affects: ["label_builder.py", "iric/pipeline.py", "features/pipeline.py", "shared/memory.py"]
tech_stack:
  added: ["multiprocessing.Pool (stdlib, now used for chunk dispatch)"]
  patterns: ["module-level worker functions for picklability", "serialize_lookups → _init_worker → get_shared_lookups pattern", "Pool.imap_unordered with main-process MemoryMonitor between results", "n_jobs>1 MP path / n_jobs<=1 single-process path dual routing"]
key_files:
  created:
    - tests/classifiers/test_multiprocessing.py
  modified:
    - src/sip_engine/shared/memory.py
    - src/sip_engine/shared/data/label_builder.py
    - src/sip_engine/classifiers/iric/pipeline.py
    - src/sip_engine/classifiers/features/pipeline.py
decisions:
  - "Worker functions use lazy imports inside function body — avoids module-level circular import issues"
  - "provider_history lazy-loads from disk pkl in each worker (no explicit sharing) — simpler and cross-platform"
  - "processed_ids set included in shared lookups pickle — workers skip checkpoint-resumed rows"
  - "n_jobs>1 MP path does NOT use adaptive chunk sizing — fixed chunk size accepted trade-off"
  - "FeatureBuildProgressDisplay uses update_rows() in main process — no cross-process display needed"
  - "Lifecycle cleanup (del procesos_lookup/proveedores_lookup/num_actividades_lookup) remains in main process after pool joins"
metrics:
  duration: "~10 minutes"
  completed: "2026-03-11"
  tasks_completed: 6
  files_changed: 5
---

# Phase 17 Plan 03: Multiprocessing Acceleration Summary

**One-liner:** Cross-platform multiprocessing acceleration for all three build steps (labels, IRIC, features) via `multiprocessing.Pool.imap_unordered` with shared lookups serialized through temp pickle files — falls back to single-process when `n_jobs<=1`.

## What Was Built

### Task 1 — `src/sip_engine/shared/memory.py` — Pool utilities (HW-08)

Added four new functions to the memory module:
- **`_shared_lookups: dict`** — module-level dict populated by `_init_worker` in each worker process.
- **`_init_worker(lookups_path: str) -> None`** — Pool initializer: opens the temp pickle and loads into `_shared_lookups`. Called once per worker at pool creation. Works on both fork (macOS/Linux) and spawn (Windows) since data is always deserialized from file.
- **`serialize_lookups(lookups: dict, tmp_dir: str | None = None) -> str`** — Serializes lookup dicts to a temp `.pkl` file via `pickle.HIGHEST_PROTOCOL`. Returns path for cleanup by caller.
- **`get_shared_lookups() -> dict`** — Returns the module-global `_shared_lookups` dict (populated by initializer).
- **`create_worker_pool(n_jobs: int, lookups: dict) -> tuple[Pool | None, str]`** — Creates a Pool with `_init_worker` as initializer; returns `(None, '')` when `n_jobs <= 1` for caller's single-process path decision.

### Task 2 — `label_builder.py` — `_process_labels_chunk` + MP dispatch

- **`_LABELS_OUTPUT_COLS`** constant extracted from the build function (shared by worker and single-process path).
- **`_process_labels_chunk(chunk: pd.DataFrame) -> list[dict]`** — Module-level worker: gets `boletines_set` from `get_shared_lookups()`, calls `_compute_m3_m4()`, returns `list[dict]` of output rows.
- **`build_labels()`** — M3/M4 loop now has two paths:
  - `n_jobs > 1`: creates pool, dispatches `_label_chunk_gen()` slices via `pool.imap_unordered(_process_labels_chunk, ...)`, checks MemoryMonitor between results.
  - `n_jobs <= 1`: existing single-process loop (identical output, adaptive chunk sizing preserved).

### Task 3 — `iric/pipeline.py` — `_process_iric_chunk` + MP dispatch

- **`_process_iric_chunk(chunk: pd.DataFrame) -> list[dict]`** — Module-level worker: lazy-imports all required functions inside body, accesses `procesos_lookup`, `num_actividades_lookup`, `bid_stats_lookup`, `thresholds`, `processed_ids` from `get_shared_lookups()`. `lookup_provider_history` lazy-loads pkl from disk in each worker (simple, cross-platform).
- **`build_iric()`** — Step 6 now has two paths:
  - `n_jobs > 1`: packages 5 lookup dicts, creates pool, dispatches `load_contratos()` chunks via `pool.imap_unordered(_process_iric_chunk, ...)`.
  - `n_jobs <= 1`: existing single-process row-iteration loop.

### Task 4 — `features/pipeline.py` — `_process_features_chunk` + MP dispatch

- **`_process_features_chunk(chunk: pd.DataFrame) -> list[dict]`** — Module-level worker: lazy-imports category functions, accesses `procesos_lookup`, `proveedores_lookup`, `num_actividades_lookup`, `processed_ids` from `get_shared_lookups()`. Drops rows missing required fields (same logic as single-process path).
- **`build_features()`** — Step 4 now has two paths:
  - `n_jobs > 1`: packages 4 lookup dicts, creates pool, dispatches `load_contratos()` chunks. Progress display updated in main process via `update_rows()` after each chunk result.
  - `n_jobs <= 1`: existing single-process row-iteration loop.

### Task 5 — `tests/classifiers/test_multiprocessing.py` (NEW)

24 tests organized in 6 classes:
- **`TestSerializeAndLoadLookups`** (4 tests): pickle round-trip, `_init_worker` overwrites previous state, `get_shared_lookups` returns empty dict by default.
- **`TestCreateWorkerPool`** (4 tests): `n_jobs<=1` returns `(None,'')`, `n_jobs>1` returns live pool + path.
- **`TestProcessLabelsChunk`** (4 tests): returns list of dicts, output keys, M4=0 when rcac returns None, M3=1 when in boletines_set, determinism.
- **`TestProcessIricChunk`** (4 tests): returns list with IRIC keys, `iric_score` present, `processed_ids` skip, determinism.
- **`TestProcessFeaturesChunk`** (5 tests): returns list of dicts, feature keys present, missing required fields drops rows, `processed_ids` skip, determinism (NaN-safe via `pd.testing.assert_frame_equal`).
- **`TestPoolWithMemoryMonitor`** (2 tests): warning triggers gc.collect(), critical raises MemoryError.

### Task 6 — Full test suite verification

567 tests pass (2 skipped — pre-existing pyarrow skip + 1 other). No regressions from multiprocessing refactor.

## Verification Results

```
567 passed, 2 skipped, 3 warnings in 37.02s
```

All verify criteria:
```
grep -c "_process_labels_chunk|create_worker_pool|imap_unordered" label_builder.py → 4  ✓ (≥3)
grep -c "_process_iric_chunk|create_worker_pool|imap_unordered" iric/pipeline.py → 4  ✓ (≥3)
grep -c "_process_features_chunk|create_worker_pool|imap_unordered" features/pipeline.py → 4  ✓ (≥3)
python -m pytest tests/classifiers/test_multiprocessing.py → 24 passed ✓
python -m pytest tests/ → 567 passed, 0 failures ✓
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] NaN-safe determinism comparison in features test**
- **Found during:** Task 5 (first test run — `test_determinism_same_chunk` for features)
- **Issue:** Python `dict.__eq__` returns False when values contain `float('nan')` because NaN != NaN
- **Fix:** Used `pd.testing.assert_frame_equal(df1, df2, check_like=True)` which handles NaN equality correctly
- **Files modified:** `tests/classifiers/test_multiprocessing.py`
- **Commit:** 95e349c (fixed inline before commit)

**2. [Rule 1 - Bug] Pool type check incompatibility**
- **Found during:** Task 5 first test run
- **Issue:** `isinstance(pool, multiprocessing.Pool)` raises `TypeError: isinstance() arg 2 must be a type` — `Pool` is a function returning a `multiprocessing.pool.Pool` object, not a type
- **Fix:** Replaced with `hasattr(pool, 'imap_unordered')` duck-type check
- **Files modified:** `tests/classifiers/test_multiprocessing.py`
- **Commit:** 95e349c (fixed inline before commit)

**3. [Rule 1 - Bug] `display.advance()` called on FeatureBuildProgressDisplay which has no such method**
- **Found during:** Task 4 (code review before test run)
- **Issue:** Plan's suggested `progress.advance(len(chunk_results))` references a non-existent method; the actual API is `update_rows(rows_processed, kept, dropped)`
- **Fix:** Changed to `display.update_rows(rows_processed, len(all_rows), rows_dropped)` in the MP path
- **Files modified:** `src/sip_engine/classifiers/features/pipeline.py`
- **Commit:** 31a3171

## Commits

| Hash | Message |
|------|---------|
| 6650a92 | feat(17-03): add pool initialization utilities to shared/memory.py |
| 1d35887 | feat(17-03): extract _process_labels_chunk and parallelize build_labels() |
| 78fca02 | feat(17-03): extract _process_iric_chunk and parallelize build_iric() |
| 31a3171 | feat(17-03): extract _process_features_chunk and parallelize build_features() |
| 95e349c | test(17-03): add multiprocessing tests — pool init, worker functions, determinism, memory monitor |
| 89ddd20 | test(17-03): verify full test suite — 567 passed, 2 skipped, 0 failures |

## Self-Check: PASSED
