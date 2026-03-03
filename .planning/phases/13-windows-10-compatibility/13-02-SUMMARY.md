---
phase: 13-windows-10-compatibility
plan: 02
subsystem: hardware
tags: [nvidia-smi, windows, cuda, rocm, threadpoolexecutor, benchmark, gpu-detection]

# Dependency graph
requires:
  - phase: 12-cross-platform-os-compat
    provides: "Hardware detection (detector.py) and benchmark (benchmark.py) foundation"
provides:
  - "Windows-compatible nvidia-smi detection with System32 fallback"
  - "ROCm guard that skips filesystem checks on Windows"
  - "Functional Windows benchmark timeout via ThreadPoolExecutor"
affects: [13-windows-10-compatibility]

# Tech tracking
tech-stack:
  added: [concurrent.futures.ThreadPoolExecutor]
  patterns: [windows-path-fallback-loop, platform-guard-early-return]

key-files:
  created: []
  modified:
    - src/sip_engine/hardware/detector.py
    - src/sip_engine/hardware/benchmark.py
    - tests/test_hardware.py

key-decisions:
  - "Loop over candidate nvidia-smi paths instead of if/else for clean extensibility"
  - "ThreadPoolExecutor replaces no-op threading.Timer for Windows timeout"
  - "sys.platform == 'win32' used in detector.py (matches CPython convention)"

patterns-established:
  - "Windows path fallback: build candidate list, loop with try/except FileNotFoundError"
  - "Platform-specific timeout: SIGALRM on Unix, ThreadPoolExecutor on Windows"

requirements-completed: [WIN-04, WIN-08, WIN-09]

# Metrics
duration: 3min
completed: 2026-03-03
---

# Phase 13 Plan 02: Hardware Detection & Benchmark Windows Fixes Summary

**Windows nvidia-smi System32 fallback in CUDA detection, ROCm platform guard, and ThreadPoolExecutor benchmark timeout replacing no-op timer**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-03T22:57:36Z
- **Completed:** 2026-03-03T23:00:51Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- `_has_cuda()` and `_get_gpu_name()` now try `nvidia-smi` then fall back to `C:\Windows\System32\nvidia-smi.exe` on Windows
- `_has_rocm()` returns False immediately on Windows (no filesystem check for `/opt/rocm`)
- `benchmark_device()` uses `ThreadPoolExecutor` with `future.result(timeout=...)` on Windows instead of useless `threading.Timer`
- 5 new tests added (3 detector, 2 benchmark), all 17 hardware tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix detector.py — nvidia-smi Windows path + ROCm guard** - `d32fe06` (feat)
2. **Task 2: Fix benchmark.py — functional Windows timeout** - `e2779b5` (feat)

**Plan metadata:** [pending] (docs: complete plan)

## Files Created/Modified
- `src/sip_engine/hardware/detector.py` - Added sys import, nvidia-smi Windows System32 fallback in _has_cuda() and _get_gpu_name(), ROCm win32 guard
- `src/sip_engine/hardware/benchmark.py` - Replaced threading.Timer no-op with ThreadPoolExecutor timeout, removed unused threading import
- `tests/test_hardware.py` - Added 5 new tests: cuda fallback, rocm skip, gpu name fallback, benchmark Windows path, benchmark timeout trigger

## Decisions Made
- Used `sys.platform == "win32"` (CPython convention) for detector.py guards, while benchmark.py keeps existing `platform.system() != "Windows"` check for consistency with its own codebase
- ThreadPoolExecutor timeout doesn't kill the background thread (Python limitation), but it prevents the caller from blocking forever — acceptable since the tiny benchmark dataset completes in <1s
- Loop-based candidate path approach (vs if/else) for nvidia-smi makes it easy to add more fallback paths later

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Hardware detection and benchmarking are now fully Windows-compatible
- Ready for Plan 03 (path separators, encoding, cross-platform filesystem fixes)
- Pre-existing test failure in test_ui.py::TestSliderWidget::test_render (NameError: _FILLED) is unrelated to this plan

---
*Phase: 13-windows-10-compatibility*
*Completed: 2026-03-03*

## Self-Check: PASSED

All files exist, all commits verified.
