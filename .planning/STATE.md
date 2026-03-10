# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** Given any Colombian public contract, reliably flag corruption risk using multiple evidence-backed signals — so oversight actors can prioritize where to investigate.
**Current focus:** Phase 15 complete — Evaluation & Training Enhancements (3/3 plans verified)

## Current Position

Milestone: v1.3 — Evaluation & Training Enhancements
Phase 15: Evaluation & Training Module Enhancements — **Plan 3/3 Complete**
Status: All plans complete — 15-01 (AUC-PR + BSS), 15-02 (Named Artifacts), 15-03 (Model Selector).

Progress: [███░░░░░░░░░░░░░░░░░] Phase 15 complete (3/3 plans)

## Accumulated Context

### Decisions

Phase 15-03 decisions:
- _CheckboxWidget uses set[str] for selected — order-preserving output reconstructed from original list
- Space key support added to _read_key_unix() and _read_key_win() as ' ' literal
- run_evaluate subset path returns Path('artifacts/evaluation') — consistent return type
- evaluate handler does not show TUI picker — defaults to all models when --model omitted

Phase 15-02 decisions:
- Flat archiving to old/ replaces date-keyed archiving — run-numbered files are self-identifying
- Run number scanning checks model_dir + model_dir/old/ for collision-safety
- artifact=None preserves existing code paths; --artifact requires --model

Phase 15-01 decisions:
- BSS guarded against div-by-zero: returns 0.0 when brier_baseline == 0
- PR curve sentinel point preserved as-is (len = len(thresholds) + 1)
- plot_pr_curve follows exact same pattern as plot_roc_curve for consistency
- test_generate_all_charts updated from 7 to 8 expected charts

Phase 14-01 decisions:
- Layout with explicit size hints replaces Group at screen level — Rich needs dimension negotiation for Live(screen=True) alternate buffer
- Group(*lines) kept inside Panel bodies — correct for content within a fixed-size region
- Shared _make_screen_layout() helper DRYs three identical layout patterns

Phase 14-02 decisions:
- Dynamic function resolution via getattr + _STEP_FN_NAMES dict for mockability — cached dicts break unittest.mock.patch
- Only refactored simple standalone commands (build-rcac, build-labels, build-iric) to pipeline functions — complex commands kept inline for backward compatibility
- Config banner printed by run_pipeline() orchestrator — eliminates duplicate config printing logic

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

- Phase 17 added: Hardware Optimization — RAM management & multithreading acceleration for label, feature, and IRIC building
- Phase 16 added: Include IRIC scores as model features — rebuild feature builder and training pipeline
- Phase 14 Plan 01 complete: TUI rendering fix — Layout replaces Group at screen level in all 3 config screens
- Phase 14 Plan 02 complete: pipeline.py coordinator + CLI refactor + --start-from support
- Phase 15 Plan 03 complete: Multi-model --model nargs='+' flag + TUI checkbox picker + PipelineConfig list[str] type
- Phase 15 Plan 02 complete: Named model artifacts — run-numbered files, flat archiving, --artifact CLI flag
- Phase 15 Plan 01 complete: AUC-PR + BSS metrics in evaluator, PR curve chart in visualizer, 4 new tests
- Phase 15 added: Evaluation and Training Module Enhancements — AUC-PR, Model Selector, Brier Skill Score, and Named Model Artifacts
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

Last session: 2026-03-08
Stopped at: Completed 15-03-PLAN.md — Multi-model selector TUI + nargs='+' --model flag + PipelineConfig list[str]
Resume file: .planning/phases/15-evaluation-and-training-module-enhancements-auc-pr-model-selector-brier-skill-score-and-named-model-artifacts/15-03-SUMMARY.md
