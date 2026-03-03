---
phase: 12-cross-platform-os-compatibility-and-training-optimization
plan: 01
subsystem: hardware
tags: [hardware-detection, cross-platform, gpu, xgboost, psutil, benchmark]

# Dependency graph
requires: []
provides:
  - HardwareConfig frozen dataclass for OS/CPU/RAM/GPU detection
  - detect_hardware() auto-detection function with container support
  - get_xgb_device_kwargs() for XGBoost device parameter mapping
  - benchmark_device() for GPU vs CPU performance comparison
  - select_best_device() for auto-selecting fastest device
affects: [12-02, 12-03, 12-04]

# Tech tracking
tech-stack:
  added: [psutil, rich, requests]
  patterns: [frozen-dataclass-config, gpu-priority-chain, cgroup-memory-detection, signal-based-timeout]

key-files:
  created:
    - src/sip_engine/hardware/__init__.py
    - src/sip_engine/hardware/detector.py
    - src/sip_engine/hardware/device.py
    - src/sip_engine/hardware/benchmark.py
    - tests/test_hardware.py
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Apple Silicon returns gpu_type='cpu' because XGBoost has no Metal/MPS support"
  - "GPU priority order: CUDA > Metal awareness > ROCm > CPU"
  - "ROCm uses CUDA HIP API in XGBoost (device='cuda:0')"
  - "Container RAM detection checks cgroup v2 then v1 before psutil fallback"

patterns-established:
  - "Frozen dataclass pattern: HardwareConfig as immutable config snapshot"
  - "GPU detection chain: priority-ordered detection with disable flags"
  - "Device kwargs mapping: centralized XGBoost device configuration"

requirements-completed: [PLAT-01, PLAT-02, PLAT-03]

# Metrics
duration: 9min
completed: 2026-03-03
---

# Phase 12 Plan 01: Hardware Detection Foundation Summary

**Cross-platform hardware detection with GPU priority chain (CUDA > Metal awareness > ROCm > CPU), frozen HardwareConfig dataclass, and XGBoost device benchmarking**

## Performance

- **Duration:** 9 minutes
- **Started:** 2026-03-03T19:54:42Z
- **Completed:** 2026-03-03T20:03:48Z
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments
- Created `src/sip_engine/hardware/` package with detector, device, and benchmark modules
- HardwareConfig frozen dataclass correctly detects Darwin arm64 (Apple Silicon) with cpu fallback
- GPU detection follows CUDA > Metal awareness > ROCm > CPU priority with disable_rocm flag
- Container cgroup memory limit detection (v1 and v2) with psutil fallback
- benchmark_device() completes in ~0.03s on CPU — well under 10s limit
- All 12 unit tests pass in <2 seconds

## Task Commits

Each task was committed atomically:

1. **Task 1: Create hardware detection module + add dependencies** - `883e424` (feat)
2. **Task 2: Unit tests for hardware detection module** - `10cf720` (test)

## Files Created/Modified
- `src/sip_engine/hardware/__init__.py` - Public API exports (HardwareConfig, detect_hardware, benchmark_device, get_xgb_device_kwargs)
- `src/sip_engine/hardware/detector.py` - OS, CPU, RAM, GPU detection with cross-platform support (243 lines)
- `src/sip_engine/hardware/device.py` - XGBoost device kwargs mapping for cuda/rocm/cpu (35 lines)
- `src/sip_engine/hardware/benchmark.py` - Quick device benchmark with signal/threading timeout (123 lines)
- `tests/test_hardware.py` - 12 unit tests covering all detection paths (207 lines)
- `pyproject.toml` - Added psutil>=5.9, rich>=13.0, requests>=2.31 dependencies
- `uv.lock` - Lock file updated with new dependencies

## Decisions Made
- Apple Silicon returns `gpu_type='cpu'` because XGBoost has no Metal/MPS support — `gpu_name` says "Apple Silicon (M-series) — XGBoost CPU only" for user display
- ROCm devices use `device='cuda:0'` in XGBoost because ROCm maps through the CUDA HIP API
- Container detection checks `/.dockerenv` and `/proc/1/cgroup` for docker/kubepods/containerd markers
- Benchmark uses `signal.SIGALRM` on Unix and `threading.Timer` on Windows for timeout handling
- `select_best_device()` requires GPU to be >20% faster than CPU to prefer it (avoids marginal GPU overhead)

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
- None

## Next Phase Readiness
- Hardware detection foundation complete, ready for Phase 12 Plans 02-04
- `detect_hardware()` and `get_xgb_device_kwargs()` available for trainer integration
- Existing `_detect_xgb_device()` in trainer.py can now delegate to hardware module

---
*Phase: 12-cross-platform-os-compatibility-and-training-optimization*
*Completed: 2026-03-03*
