# Phase 12: Cross-platform OS Compatibility and Training Optimization - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the SIP pipeline run automatically on any major OS (macOS, Linux, Windows, Docker) and auto-tune training based on detected hardware (GPU type, RAM, CPU cores). The system should detect available resources, propose optimal settings, let the user confirm/override via interactive CLI, and handle failures gracefully. No new ML models or features — this is infrastructure and UX.

</domain>

<decisions>
## Implementation Decisions

### Target Platforms
- Support macOS (Intel + Apple Silicon), Linux, and Windows
- Keep Python 3.12+ requirement (no version broadening)
- Provide a working Dockerfile for containerized runs
- Replace `curl` dependency with Python `requests` fallback when `curl` is not available (keeps curl as primary, adds fallback)

### Hardware Auto-Tuning
- Auto-detect hardware on every run (no caching between sessions)
- Show detected hardware and proposed config before training starts
- User confirms or overrides settings via interactive TUI sliders (arrow keys to adjust, or type value directly)
- CPU core count: user selects via slider (default proposed, not hardcoded)
- Full HP iterations and CV folds always — no auto-reduction for low RAM
- Use chunking and crash-prevention strategies (already partially implemented) instead of reducing workload

### GPU Support
- Support NVIDIA CUDA, Apple Metal/MPS, and AMD ROCm
- ROCm support includes a `--disable-rocm` flag for when it's unstable
- Auto-detect best device with a quick benchmark on first use per session
- User can override with `--device` flag (e.g., `--device cpu`, `--device cuda`)
- If GPU fails mid-training (VRAM OOM, driver error): automatically fall back to CPU with a warning logged
- Priority when benchmark not run: CUDA > Metal > ROCm > CPU

### Training UX
- Rich progress bars (using `rich` library) with ETA and resource usage
- Live resource monitoring during training: CPU%, RAM usage, GPU utilization
- During HP search: show best score found so far and improvement trend
- Pre-training config screen: interactive block sliders for each parameter (cores, n_iter, cv_folds, device, etc.) — adjust with left/right arrow keys or type specific value
- User presses Enter to confirm and start training

### Claude's Discretion
- Specific `rich` layout/panel design for the TUI
- Benchmark duration and methodology (should be <10 seconds)
- Exact crash-prevention strategies for memory management
- Docker base image choice (slim Python vs. CUDA-enabled)
- Whether to provide separate Dockerfiles for CPU-only and GPU

</decisions>

<specifics>
## Specific Ideas

- Interactive pre-training config should feel like a "system check" screen — show all detected hardware, then let user tweak settings with slider controls before launching
- The slider UX: block-style `[████████░░░░]` adjustable with left/right keys, with the option to type a number directly
- HP search should show a live "best so far" metric updating as iterations complete
- Resource monitor should be non-intrusive (e.g., a status bar at bottom of terminal, not flooding log output)

</specifics>

<deferred>
## Deferred Ideas

- Distributed training across multiple machines — separate phase
- Cloud deployment (AWS/GCP/Azure) — separate phase
- Web-based training dashboard — separate phase

</deferred>

---

*Phase: 12-cross-platform-os-compatibility-and-training-optimization*
*Context gathered: 2026-03-03*
