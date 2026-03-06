# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** Given any Colombian public contract, reliably flag corruption risk using multiple evidence-backed signals — so oversight actors can prioritize where to investigate.
**Current focus:** Milestone v1.1 complete — Cross-platform OS compatibility and Windows 10 support (Phases 12-13, 7 plans, all done)

## Current Position

Milestone: v1.2 — CLI & TUI Polish
Phase 14: CLI & TUI Fixes — Command Pipeline Refactor — **Not planned yet**
Status: Phase added, awaiting planning.

Progress: [░░░░░░░░░░░░░░░░░░░░] v1.2 Starting

## Accumulated Context

### Decisions

Phase 13-03 decisions:
- Matrix strategy with fail-fast: false — both OS jobs complete independently
- uv for CI dependency management — consistent with local workflow
- No macOS in matrix — not requested, saves CI minutes
- Windows 10 section placed as subsection of Installation with ToC link

Phase 13-01 decisions:
- Centralized all platform-specific logic in compat.py — no scattered if sys.platform guards
- Slider bar chars resolved once at widget creation time to avoid repeated detection checks
- Removed unused subprocess import from loaders.py after line-count migration

Phase 13-02 decisions:
- Loop over candidate nvidia-smi paths instead of if/else for clean extensibility
- ThreadPoolExecutor replaces no-op threading.Timer for Windows timeout
- sys.platform == 'win32' used in detector.py (matches CPython convention)

All v1.0 decisions archived in PROJECT.md Key Decisions table.

Phase 12-04 decisions:
- Kept curl as primary download method; requests is sequential fallback only
- Multi-stage Docker build to minimize runtime image size
- Non-root user (sip:1000) in both Docker images for security
- CUDA image uses nvidia/cuda:12.1.0-runtime-ubuntu22.04 with deadsnakes PPA

Phase 12-01 decisions:
- Apple Silicon returns gpu_type='cpu' because XGBoost has no Metal/MPS support
- GPU priority order: CUDA > Metal awareness > ROCm > CPU
- ROCm uses CUDA HIP API in XGBoost (device='cuda:0')
- Container RAM detection checks cgroup v2 then v1 before psutil fallback

Phase 12-02 decisions:
- Block-style Unicode sliders (█/░) with arrow key navigation and direct number entry
- Non-interactive fallback returns full defaults when stdin is not a TTY (CI/piped)
- psutil.cpu_percent(interval=None) for non-blocking CPU reads during training
- Rich Live at 4 refreshes/second for smooth updates without overhead

Phase 12-03 decisions:
- Config screen shown only once for batch training (first model), settings reused for remaining
- GPU fallback uses recursive _train_with_fallback() — strips device kwarg and retries on CPU
- CV scoring functions have inline GPU fallback to prevent mid-HP-search failures
- Non-interactive mode auto-detects CPU cores from hardware config when n_jobs=-1

### Roadmap Evolution

- Phase 14 added: CLI & TUI Fixes — Command Pipeline Refactor (chart edge clipping, hardware config display, command pipeline refactor)
- Phase 13 Plan 03 complete: CI pipeline + pathlib audit + README Windows docs + Docker verification
- Phase 13 Plan 01 complete: platform compatibility layer (compat.py) + consumer wiring
- Phase 13 Plan 02 complete: hardware detection & benchmark Windows fixes
- Phase 13 added: Windows 10 Compatibility
- Phase 12 added: Cross-platform OS compatibility and training optimization
- Phase 12 Plan 04 complete: requests fallback + Docker support
- Phase 12 Plan 01 complete: hardware detection foundation
- Phase 12 Plan 02 complete: interactive TUI config screen + progress display
- Phase 12 Plan 03 complete: training pipeline integration with hardware/TUI/GPU fallback

### Pending Todos

None — milestone complete.

### Blockers/Concerns

None — all prior blockers resolved.

## Session Continuity

Last session: 2026-03-06
Stopped at: Phase 14 context gathered
Resume file: .planning/phases/14-cli-tui-fixes-command-pipeline-refactor/14-CONTEXT.md
