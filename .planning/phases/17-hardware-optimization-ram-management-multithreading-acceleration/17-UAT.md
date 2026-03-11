---
status: testing
phase: 17-hardware-optimization-ram-management-multithreading-acceleration
source: [17-01-SUMMARY.md, 17-02-SUMMARY.md, 17-03-SUMMARY.md, 17-04-SUMMARY.md]
started: 2026-03-10T00:00:00Z
updated: 2026-03-10T00:00:00Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 1
name: CLI exposes n_jobs and max_ram_gb flags
expected: |
  Run: python -m sip_engine run-pipeline --help
  You should see --n-jobs and --max-ram-gb (or similar) flags listed in the output.
awaiting: user response

## Tests

### 1. CLI exposes n_jobs and max_ram_gb flags
expected: Run `python -m sip_engine run-pipeline --help` — output should list flags for controlling number of jobs/workers and RAM budget (e.g. --n-jobs, --max-ram-gb or similar).
result: [pending]

### 2. MemoryMonitor unit tests pass
expected: Run `PATH="$PWD/.venv/bin:$PATH" pytest tests/shared/test_memory.py -q --tb=short` — all 22 tests pass covering ok/warning/critical thresholds, adaptive chunk sizing, checkpoint round-trip, cleanup gc calls.
result: [pending]

### 3. Multiprocessing unit tests pass
expected: Run `PATH="$PWD/.venv/bin:$PATH" pytest tests/classifiers/test_multiprocessing.py -q --tb=short` — all 24 tests pass covering pool init, worker functions (labels/IRIC/features), processed_ids skipping, determinism.
result: [pending]

### 4. GPU optimization unit tests pass
expected: Run `PATH="$PWD/.venv/bin:$PATH" pytest tests/classifiers/test_gpu_optimization.py -q --tb=short` — 8 tests pass (1 skipped for CUDA not available). Tests verify max_bin=512 injection for CUDA, CPU path unchanged, HP search determinism.
result: [pending]

### 5. Full test suite passes with no regressions
expected: Run `PATH="$PWD/.venv/bin:$PATH" pytest tests/ -q --tb=short` — 567 passed, 2 skipped, 0 failures. All new Phase 17 tests included without breaking any existing tests.
result: [pending]

### 6. Checkpoint files created on disk for build functions
expected: Inspect that checkpoint paths are defined in code: `artifacts/labels/_checkpoint.parquet`, `artifacts/iric/_checkpoint.parquet`, `artifacts/features/_checkpoint.parquet`. Run `grep -r "_checkpoint.parquet" src/` — should find references in label_builder.py, iric/pipeline.py, features/pipeline.py.
result: [pending]

### 7. Multiprocessing dispatch present in all three build functions
expected: Run `grep -c "imap_unordered" src/sip_engine/shared/data/label_builder.py src/sip_engine/classifiers/iric/pipeline.py src/sip_engine/classifiers/features/pipeline.py` — each file should show at least 1 match (Pool.imap_unordered dispatch wired in).
result: [pending]

## Summary

total: 7
passed: 0
issues: 0
pending: 7
skipped: 0

## Gaps

[none yet]
