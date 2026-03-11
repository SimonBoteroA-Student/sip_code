---
phase: 17
plan: "02"
title: "Build Function Integration — RAM Management, Lifecycle Cleanup & Checkpoints"
subsystem: "label_builder, iric/pipeline, features/pipeline"
tags: ["memory-management", "hardware-optimization", "checkpoint-resume", "lifecycle-cleanup"]
dependency_graph:
  requires: ["shared/memory.py MemoryMonitor API (17-01)"]
  provides: ["RAM-budgeted build_labels()", "RAM-budgeted build_iric()", "RAM-budgeted build_features()", "checkpoint-resume for all 3 build steps"]
  affects: ["label_builder.py", "iric/pipeline.py", "features/pipeline.py"]
tech_stack:
  added: []
  patterns: ["MemoryMonitor in all 3 build functions", "chunk-level memory check (warning→gc / critical→checkpoint+abort)", "skip-based resume via load_checkpoint processed_ids", "del + cleanup() lifecycle pattern"]
key_files:
  created: []
  modified:
    - src/sip_engine/shared/data/label_builder.py
    - src/sip_engine/classifiers/iric/pipeline.py
    - src/sip_engine/classifiers/features/pipeline.py
decisions:
  - "build_labels M3/M4 computed in chunks (_M3M4_CHUNK_SIZE=5000) to enable checkpoint-save mid-computation"
  - "dict round-trip (to_dict/DataFrame) loses nullable Int8 — restored with astype('Int8') after reconstruction"
  - "features rows_processed initialized to len(processed_ids) so progress display is accurate on resume"
  - "del procesos_lookup / proveedores_lookup / num_actividades_lookup after streaming pass in iric and features"
metrics:
  duration: "~6 minutes"
  completed: "2026-03-11"
  tasks_completed: 4
  files_changed: 3
---

# Phase 17 Plan 02: Build Function Integration — RAM Management, Lifecycle Cleanup & Checkpoints Summary

**One-liner:** MemoryMonitor wired into all three build functions (labels, IRIC, features) with chunk-level pressure checks, gc.collect() at warning, checkpoint-and-abort at critical, and explicit del+gc.collect() lifecycle cleanup after large lookups.

## What Was Built

### Task 1 — `build_labels()` RAM management

- **MemoryMonitor** created when `max_ram_gb` is provided.
- **`_load_contratos_base(monitor, checkpoint_path)`** — checks memory before each contratos chunk; gc.collect() at warning; saves empty checkpoint + raises MemoryError at critical.
- **M3/M4 chunked processing** — `_compute_m3_m4()` called on `_M3M4_CHUNK_SIZE=5000` row slices; memory checked before each slice.
- **Checkpoint/resume** — `load_checkpoint()` at start; `processed_ids` used to skip already-computed rows; `save_checkpoint(all_rows, ...)` on critical abort; `remove_checkpoint()` on success.
- **Lifecycle cleanup** — `del m1_contracts, m2_contracts, dias_m2_ids; cleanup()` after M1/M2 assignment; `del boletines_set; cleanup()` after M3/M4 pass; `del all_rows; cleanup()` after DataFrame build.
- **Abort message** — shows current RSS (GB), budget (GB), row count saved, actionable suggestion.

### Task 2 — `build_iric()` RAM management

- Same MemoryMonitor pattern; check before each contratos chunk in the main streaming loop.
- Checkpoint path: `artifacts/iric/_checkpoint.parquet`.
- Skip already-processed `id_contrato` in inner row loop.
- Lifecycle cleanup: `del procesos_lookup, num_actividades_lookup, bid_stats_lookup; cleanup()` after streaming pass; `del all_rows; cleanup()` after DataFrame build.
- `remove_checkpoint()` on successful completion.

### Task 3 — `build_features()` RAM management

- Same MemoryMonitor pattern; check before each contratos chunk.
- Checkpoint path: `artifacts/features/_checkpoint.parquet`.
- `rows_processed` initialized to `len(processed_ids)` to keep progress display accurate on resume.
- Skip already-processed rows in inner loop.
- Lifecycle cleanup: `del procesos_lookup, proveedores_lookup, num_actividades_lookup; cleanup()` after streaming pass; `del all_rows; cleanup()` after DataFrame build.
- Updated docstring: `max_ram_gb` is now enforced, not informational.

### Task 4 — Full test suite verification

535 passed, 1 skipped — identical to Plan 17-01 baseline. No behavioral change when `max_ram_gb=None`.

## Verification Results

```
535 passed, 1 skipped, 3 warnings in 33.77s
```

All verify criteria passed:
```
# label_builder.py
grep -c "MemoryMonitor|monitor.check|save_checkpoint|cleanup" → 19  ✓ (≥5)

# iric/pipeline.py
grep -c "MemoryMonitor|monitor.check|save_checkpoint|cleanup" → 12  ✓ (≥5)

# features/pipeline.py
grep -c "MemoryMonitor|monitor.check|save_checkpoint|cleanup" → 12  ✓ (≥5)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Nullable Int8 dtype lost in dict round-trip (`build_labels`)**
- **Found during:** Task 1 (test run)
- **Issue:** `to_dict("records")` + `pd.DataFrame(all_rows)` reconstruction converts nullable `Int8` to `int64`, failing `test_labels_parquet_nullable_int8`
- **Fix:** Added explicit `out[col] = out[col].astype("Int8")` for M1–M4 columns after DataFrame reconstruction
- **Files modified:** `src/sip_engine/shared/data/label_builder.py`
- **Commit:** 0e31d5d

## Commits

| Hash | Message |
|------|---------|
| 0e31d5d | feat(17-02): integrate MemoryMonitor into build_labels() |
| f0e468e | feat(17-02): integrate MemoryMonitor into build_iric() |
| e47d58b | feat(17-02): integrate MemoryMonitor into build_features() |
| 34290c6 | test(17-02): verify full test suite passes — 535 passed, 1 skipped |

## Self-Check: PASSED

- `src/sip_engine/shared/data/label_builder.py` — FOUND ✓
- `src/sip_engine/classifiers/iric/pipeline.py` — FOUND ✓
- `src/sip_engine/classifiers/features/pipeline.py` — FOUND ✓
- Commits 0e31d5d, f0e468e, e47d58b, 34290c6 — all present in git log ✓
- 535 tests passing — verified ✓
