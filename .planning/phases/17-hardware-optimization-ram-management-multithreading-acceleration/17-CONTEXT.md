# Phase 17: Hardware Optimization — RAM Management & Multithreading Acceleration - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Optimize RAM usage according to system availability (using `max_ram_gb` as a hard ceiling), preventing crashouts and offloading data when no longer needed. Utilize multiprocessing to accelerate the label, feature, and IRIC building steps via chunk-level parallelism. Additionally, maximize GPU utilization during XGBoost training to eliminate the idle-GPU pattern observed in CUDA training.

</domain>

<decisions>
## Implementation Decisions

### RAM Budget Strategy
- Use `max_ram_gb` from `PipelineConfig` as the hard ceiling — no percentage-based or tiered auto-detection
- Active monitoring via `psutil.virtual_memory()` against the budget at runtime (not passive up-front estimation)
- Lifecycle-based offloading: explicitly `del` DataFrames and `gc.collect()` once data has served its purpose and will no longer be used
- Keep existing TUI RAM display as-is; no new messages for memory clearing/offloading events — memory management is silent

### Crash Prevention Behavior
- At 90% of `max_ram_gb`: trigger adaptive response — clean memory (`gc.collect()`) AND dynamically reduce chunk sizes (e.g. halve from 50k to 25k rows)
- At 100% of `max_ram_gb`: force aggressive GC + retry the current chunk once. If still over budget, abort cleanly
- On abort: checkpoint partial progress to a temp Parquet file so the step can resume from where it left off (skip already-processed rows on restart)
- Abort message should show current memory stats and suggest increasing `max_ram_gb` or freeing system memory

### Parallelism Scope
- All three data-building steps (labels, features, IRIC) get multicore acceleration
- Chunk-level parallelism only — no step-level concurrency (steps still run sequentially: rcac → labels → iric → features → train → evaluate)
- Use Python `multiprocessing` (separate processes) for true parallelism, not threading (GIL-limited for CPU-bound pandas work)

### Process Control
- Reuse `n_jobs` from `PipelineConfig` for the multiprocessing worker pool — same value that controls XGBoost training parallelism
- Fixed worker count: `n_jobs` does not adapt to memory pressure. Chunk sizes are the knob that flexes, not worker count
- Same `n_jobs` for everything — no separate `n_build_jobs` config. One value, one knob
- Merge strategy (in-memory concat vs incremental Parquet write) is Claude's discretion per step, based on workload and memory characteristics

### GPU Utilization for XGBoost Training
- Current problem: GPU stays at 2-3% usage most of the time, spikes to 90% briefly, then drops back. This is caused by the sequential HP search loop (`_hp_search`) where each XGBoost fit is small and fast on GPU, leaving the GPU idle during CPU-side bookkeeping between CV folds
- Goal: maximize GPU utilization during CUDA training — keep the GPU fed with work to reduce idle time
- The system should prefer GPU over CPU for XGBoost training when CUDA is available (GPU is faster for this dataset size)
- Claude has discretion on the specific optimization approach (e.g. batching HP candidates to keep GPU busy, using XGBoost's native CV with `xgb.cv()`, DMatrix caching to avoid repeated data transfers, increasing `max_bin` for more GPU work per split, or other appropriate techniques)

### Claude's Discretion
- Merge strategy per step (in-memory concat vs incremental Parquet write)
- Specific chunk sizes and how they scale with `max_ram_gb`
- GPU optimization technique for the HP search idle-GPU problem
- Checkpoint file format and naming conventions
- How to calculate `max_ram_gb` budget attribution across concurrent worker processes

</decisions>

<specifics>
## Specific Ideas

- The existing `PipelineConfig.max_ram_gb` field is already detected from hardware and passed through the pipeline — extend its usage to all build steps, not just features
- The IRIC pipeline already uses chunked CSV reading (`for chunk in load_contratos()`) — extend this pattern with multiprocessing
- The `psutil` library is already imported in `classifiers/ui/progress.py` — reuse for the active RAM monitor
- The user observed GPU at 2-3% → spike to 90% → back during CUDA training — this matches the sequential `_hp_search` loop doing 10 fits per iteration (2 strategies × 5 folds) with CPU bookkeeping between each
- Dataset sizes are ~33 GB raw on disk (9.4 GB contratos, 9.8 GB procesos, 7.5 GB ofertas, etc.)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 17-hardware-optimization-ram-management-multithreading-acceleration*
*Context gathered: 2026-03-10*
