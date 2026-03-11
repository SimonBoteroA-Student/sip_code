# Phase 17 Research: Hardware Optimization — RAM Management & Multithreading Acceleration

**Produced:** 2026-03-10
**Consumed by:** gsd-planner for plan generation

---

## 1. Current Architecture & Hot Paths

### 1.1 Pipeline Step Execution Order

`pipeline.py` orchestrates 6 sequential steps: `rcac → labels → iric → features → train → evaluate`. Phase 17 targets three data-building steps (labels, iric, features) plus the GPU optimization in training. The step functions are called from `run_pipeline()` with a `PipelineConfig` dataclass carrying `n_jobs`, `max_ram_gb`, `device`.

**Critical finding:** `run_labels(cfg)` and `run_iric(cfg)` currently do NOT pass `n_jobs` or `max_ram_gb` to their build functions. Only `run_features(cfg)` passes these. The pipeline signatures for `build_labels(force)` and `build_iric(force)` must be extended to accept `n_jobs` and `max_ram_gb`.

### 1.2 Data Building — Common Pattern

All three build functions follow an identical pattern:
```
1. Build lookup dicts (stream CSV → dict in memory)
2. Stream contratos chunks: for chunk in load_contratos()
3. Row-level processing: for _, row in chunk.iterrows()
4. Accumulate results in all_rows: list[dict]
5. Convert to DataFrame at end
```

**Specific hot paths with `iterrows()`:**
- `label_builder.py`: `_build_boletines_set()` (line 140), `_compute_m3_m4()` loops (lines 191-213)
- `iric/pipeline.py`: `_build_iric_procesos_lookup()` (line 112), `_build_iric_num_actividades_lookup()` (line 138), main IRIC computation (line 283)
- `features/pipeline.py`: `_build_procesos_lookup()` (line 174), `_build_proveedores_lookup()` (line 199), `_build_num_actividades_lookup()` (line 234), main feature extraction (line 416)
- `iric/bid_stats.py`: `build_bid_stats_lookup()` (line 129)
- `provider_history.py`: `build_provider_history_index()` (line 134)

### 1.3 Lookup Dict Sizes (In-Memory)

These dicts are built once and used for every contratos row:
- **procesos_lookup**: ~6.4M rows → dict of ~millions of entries (~5-7 GB estimated in-memory)
- **proveedores_lookup**: smaller, normalized NIT → date mapping
- **num_actividades_lookup**: (tipo, num) → int count per provider
- **bid_stats_lookup**: proceso_id → 3 scalar values
- **provider_history_index**: (tipo, num) → {dates, valores, deptos, m1, m2} — serialized as pkl

**Key insight:** These lookups must be shared read-only across worker processes. They are pure Python dicts — they can be:
1. Built in the main process, then shared via `multiprocessing.Manager().dict()` (slow — proxy access)
2. Built in main, fork() inherits them via copy-on-write (Linux/macOS only — `multiprocessing.get_start_method() == 'fork'`)
3. Built in main, serialized to shared memory or a temp file, loaded by each worker

### 1.4 Data Sizes

- contratos_SECOP.csv: 9.4 GB (~5-6M rows at chunk_size=50,000 → ~100-120 chunks)
- procesos_SECOP.csv: 9.8 GB (~6.4M rows)
- ofertas_proceso_SECOP.csv: 7.5 GB (~9.7M rows)
- proveedores_registrados.csv: small
- boletines.csv: small
- adiciones.csv: tiny (~1.3k rows)

### 1.5 Settings chunk_size

`settings.chunk_size = 50_000` (in `config/settings.py` line 125). This is the single knob for adaptive chunk sizing. Currently hardcoded at init time — Phase 17 must make it dynamically adjustable per step.

### 1.6 Trainer HP Search Loop

`_hp_search()` (trainer.py line 455) runs `n_iter` iterations (default 200). Each iteration:
1. Calls `_compare_strategies()` → runs 2 strategies × 5 folds = 10 XGBoost fits
2. Each `XGBClassifier.fit()` on GPU is fast but followed by CPU-side Python bookkeeping
3. GPU utilization observed at 2-3% between fits, spikes to ~90% during fits

The `n_jobs` parameter is declared but currently unused (line 480 comment: "reserved for future parallel implementation").

---

## 2. RAM Management Design

### 2.1 Budget System

**Config source:** `PipelineConfig.max_ram_gb` (int, from hardware detection or user config screen).

**Monitoring mechanism:** `psutil.virtual_memory()` is already imported in `progress.py` and `detector.py`. The `process`-level RSS can be tracked via `psutil.Process().memory_info().rss`.

**Design decision from CONTEXT.md:** Use `max_ram_gb` as hard ceiling, not percentage-based.

**Implementation approach — `MemoryMonitor` class:**
```
class MemoryMonitor:
    def __init__(self, max_ram_gb: int):
        self.budget_bytes = max_ram_gb * (1024**3)
    
    def current_usage_bytes(self) -> int:
        return psutil.Process().memory_info().rss
    
    def usage_ratio(self) -> float:
        return self.current_usage_bytes() / self.budget_bytes
    
    def check(self) -> str:  # "ok" | "warning" | "critical" | "abort"
        ratio = self.usage_ratio()
        if ratio < 0.9: return "ok"
        if ratio < 1.0: return "warning"  # 90% threshold
        return "critical"  # 100% threshold
```

**Important consideration:** `psutil.Process().memory_info().rss` measures the current process RSS. With `multiprocessing`, child processes have their own address spaces. Total memory = parent RSS + sum of child RSS (minus shared pages on fork). The monitor should track the parent process's view; child workers won't independently trigger budget alerts — the parent monitors before dispatching new chunks.

### 2.2 Adaptive Chunk Sizing

**Decision from CONTEXT.md:** Worker count stays fixed; chunk sizes flex under memory pressure.

**Approach:**
- Start with default `chunk_size` from settings (50,000)
- At 90% of budget: halve chunk_size (to 25,000), trigger `gc.collect()`
- At 100% of budget: aggressive GC + retry current chunk once
- Above 100% after retry: abort with checkpoint

**Where to modify:** The chunk size used in `_load_csv()` comes from `settings.chunk_size`. The build functions call `load_contratos()` which reads `settings.chunk_size` once. To make chunk sizing dynamic:

Option A: Pass `chunk_size` as parameter to loader functions → requires modifying all loader signatures.
Option B: Temporarily mutate `settings.chunk_size` before each loader call → fragile, not thread-safe.
Option C: The build functions don't call the loaders directly for the main streaming pass; instead they manage their own `pd.read_csv()` with a controlled chunk_size → too much duplication.

**Recommended: Option A** — add optional `chunk_size: int | None = None` to `_load_csv()` and the public loader functions. If None, falls back to `settings.chunk_size`. The memory monitor in the build function can adjust the chunk_size between iterations of the outer chunk loop.

### 2.3 Lifecycle `del` + `gc.collect()`

**Decision from CONTEXT.md:** Explicit `del` + `gc.collect()` for completed data structures.

**Targets for explicit cleanup (by step):**
- **Labels:** After M1/M2 sets are assigned to columns, `del m1_contracts, m2_contracts`. After boletines_set is used in `_compute_m3_m4`, `del boletines_set`.
- **IRIC:** After all lookups are used in the streaming pass, `del procesos_lookup, num_actividades_lookup, bid_stats_lookup`. After `all_rows` is converted to DataFrame, `del all_rows`.
- **Features:** Same pattern — `del procesos_lookup, proveedores_lookup, num_actividades_lookup` after streaming pass. After `all_rows` → DataFrame, `del all_rows`.

### 2.4 Checkpoint & Resume

**Decision from CONTEXT.md:** On abort, save partial progress to temp Parquet so step can resume.

**Design:**
- Checkpoint file: `artifacts/<step>/_checkpoint.parquet` (e.g., `artifacts/iric/_checkpoint.parquet`)
- On abort: write accumulated `all_rows` to checkpoint Parquet
- On resume: load checkpoint, determine last processed `id_contrato`, skip rows already processed
- Resume detection: if checkpoint exists and `force=False`, load it and continue from where it left off
- On successful completion: delete checkpoint file

**Challenge:** The current loaders yield chunks from `pd.read_csv()` which has no concept of "resume from row N". Two approaches:
1. **Skip-based:** Load checkpoint, extract processed IDs as a set, skip rows whose `id_contrato` is in the set. Simple but slightly wasteful (re-reads already-processed chunks from CSV).
2. **Offset-based:** Track the byte offset in the CSV file. Complex and fragile.

**Recommended: Skip-based** — simpler, and the CSV reading is I/O-bound while the skip-check is O(1) set lookup.

### 2.5 Budget Attribution for Workers

**Decision from CONTEXT.md:** Claude's discretion on budget attribution.

With `n_jobs` workers, the memory budget should account for:
- Main process: holds lookup dicts + accumulates results
- Workers: each holds a chunk of data + intermediate computation

**Recommended formula:**
- Reserve 60% of `max_ram_gb` for the main process (lookups + results accumulation)
- Remaining 40% split among `n_jobs` workers (each gets `0.4 * max_ram_gb / n_jobs`)
- Chunk size per worker = f(worker_budget, estimated_bytes_per_row)
- Monitor checks main process RSS; if over 90%, reduce chunk sizes for future dispatches

---

## 3. Multiprocessing Design

### 3.1 Parallelism Strategy

**Decision from CONTEXT.md:** Chunk-level parallelism via `multiprocessing`, not threading (GIL-limited for CPU-bound pandas work).

**Pattern for all three build steps:**
```
1. Main process: build lookup dicts (sequential — these are large shared state)
2. Main process: read contratos chunks sequentially via loader
3. Dispatch chunks to worker pool for row-level processing
4. Workers return processed rows (list[dict])
5. Main process accumulates results
```

### 3.2 Worker Function Design

Each worker receives:
- A chunk (pd.DataFrame) — serialized via pickle when sent to worker
- Read-only lookup dicts — must be accessible without per-chunk serialization

**Critical: Lookup dict sharing strategy**

On macOS (development platform) and Linux (deployment): `multiprocessing` default start method is `fork`. Forked children inherit the parent's memory space with copy-on-write. This means lookup dicts built in the parent before `pool.map()` are readable by children without serialization overhead.

On Windows (test target): Default start method is `spawn`. Children start fresh — lookups would need to be serialized per-worker or loaded from disk.

**Cross-platform approach:**
1. Use `multiprocessing.get_context('fork')` on macOS/Linux for COW sharing
2. On Windows (`sys.platform == 'win32'`): serialize lookups to a temp pickle file, workers load once at init
3. Wrap in a platform check in `compat.py` (existing pattern from Phase 13)

**Alternative: Module-level globals pattern.** Set lookup dicts as module-level globals via a pool initializer. On `spawn`, the initializer runs in each worker process:
```python
_shared_lookups = {}

def _init_worker(lookups_path):
    global _shared_lookups
    _shared_lookups = joblib.load(lookups_path)

pool = Pool(n_jobs, initializer=_init_worker, initargs=(temp_pkl_path,))
```
This works cross-platform. The lookups are serialized once to disk, loaded once per worker. On `fork` platforms, this is slightly wasteful (would've gotten COW for free), but it's consistent and avoids platform-specific branching.

**Recommended:** Module-level globals + pool initializer for cross-platform consistency. The one-time serialization/deserialization cost is negligible compared to the minutes-long build process.

### 3.3 Worker Function Signatures

For IRIC build step (example):
```python
def _process_iric_chunk(chunk: pd.DataFrame) -> list[dict]:
    """Process a single contratos chunk — compute IRIC per row.
    
    Accesses _shared_lookups global (set by pool initializer).
    Returns list of result dicts (one per valid row).
    """
    # Access shared lookups
    procesos_lookup = _shared_lookups['procesos']
    num_actividades_lookup = _shared_lookups['num_actividades']
    bid_stats_lookup = _shared_lookups['bid_stats']
    thresholds = _shared_lookups['thresholds']
    
    results = []
    for _, row in chunk.iterrows():
        # ... same logic as current build_iric inner loop ...
        results.append(result_row)
    return results
```

Same pattern for features and labels.

### 3.4 Pool Management

```python
from multiprocessing import Pool

with Pool(n_jobs, initializer=_init_worker, initargs=(lookups_path,)) as pool:
    for chunk_results in pool.imap_unordered(_process_chunk, chunk_generator):
        all_rows.extend(chunk_results)
        # Memory check here
```

**`pool.imap_unordered`** is ideal because:
- Processes chunks as they arrive (no ordering constraint for append-based accumulation)
- Lower memory footprint than `pool.map` (doesn't buffer all results)
- Allows memory monitoring between chunk completions

### 3.5 Merge Strategy (In-Memory vs Incremental Parquet)

**Decision from CONTEXT.md:** Claude's discretion per step.

Analysis:
- **Labels:** Output is small (one row per unique contract, ~600k rows, ~7 columns). In-memory concat is fine.
- **IRIC:** Output is ~600k rows × 19 columns (mostly float). In-memory list[dict] → DataFrame at end is fine. ~50-100 MB.
- **Features:** Output is ~600k rows × 45 columns. In-memory list[dict] → DataFrame is fine. ~200-400 MB.

**Recommendation:** In-memory concat for all three steps. The outputs are small relative to the lookup dicts and source data. Incremental Parquet write adds complexity (schema tracking, row group management) without meaningful benefit at these output sizes.

### 3.6 Serialization Concerns

Worker functions and their arguments must be picklable:
- `pd.DataFrame` chunks: picklable ✓
- Return `list[dict]` with Python primitives: picklable ✓
- Lookup dicts (str → dict, tuple → int): picklable ✓
- `compute_iric_components`, `compute_iric_scores`: module-level functions, picklable ✓
- `_to_date_iric`, `normalize_tipo`, `normalize_numero`: module-level functions, picklable ✓

No lambda or closure concerns — all functions are defined at module level.

---

## 4. GPU Optimization for HP Search

### 4.1 Current Problem

In `_hp_search()` (trainer.py line 539):
```python
for i, params in enumerate(param_samples):
    comparison = _compare_strategies(params, X, y, ...)
```

Each `_compare_strategies()` calls:
- `_cv_score_scale_pos_weight()`: 5 XGBoost fits (one per fold)
- `_cv_score_upsampling()`: 5 XGBoost fits

Total: 10 sequential `XGBClassifier.fit()` calls per HP iteration. Between each fit, Python does fold splitting, upsampling, score computation — GPU sits idle.

### 4.2 Optimization Options

**Option A: DMatrix Caching**
Pre-convert `X` and `y` to `xgb.DMatrix` once, reuse across all iterations. Currently, `XGBClassifier.fit()` internally converts numpy arrays to DMatrix on every call. Since the data doesn't change (folds use index slicing), pre-building DMatrix objects for each fold avoids repeated GPU data transfers.

Implementation: Pre-split data into fold DMatrix objects before the HP loop:
```python
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
fold_dmatrices = []
for train_idx, val_idx in cv.split(X, y):
    dtrain = xgb.DMatrix(X[train_idx], label=y[train_idx])
    dval = xgb.DMatrix(X[val_idx], label=y[val_idx])
    fold_dmatrices.append((dtrain, dval))
```
Then use `xgb.train()` instead of `XGBClassifier.fit()` to reuse cached DMatrix objects.

**Compatibility note:** This requires switching from `XGBClassifier` (sklearn API) to `xgb.train()` (native API) for the CV loop. The final refit (line ~1070) can stay with `XGBClassifier` since it only runs once.

**Option B: xgb.cv() for Batch CV**
Use `xgb.cv()` which runs all folds in a single call with internal optimization. However, `xgb.cv()` doesn't support the upsampling strategy (Strategy B) because upsampling happens inside each fold's training data.

**Verdict: Option A is better** — it supports both strategies while eliminating data transfer overhead.

**Option C: Batch HP Candidates**
Instead of evaluating one HP set at a time, batch multiple HP candidates. However, XGBoost's GPU implementation already utilizes the GPU for a single model — batching models wouldn't increase utilization, just queue them.

**Option D: Increase max_bin for More GPU Work**
Setting `max_bin=512` or `1024` (default 256) gives the GPU more work per split computation, increasing per-iteration GPU time. This is a simple parameter change.

### 4.3 Recommended GPU Strategy

Combine Option A + D:
1. **DMatrix caching:** Pre-build fold DMatrix objects, use `xgb.train()` for CV scoring
2. **Increased max_bin:** Add `max_bin=512` to device_kwargs when `device='cuda'`
3. **Keep fold structure identical** to maintain reproducibility — same `StratifiedKFold` splits

**Impact on upsampling strategy:** For Strategy B, the upsampled training data changes per fold but not per iteration (same seed). So DMatrix for upsampled folds can also be pre-built.

Wait — actually the upsampling uses a fixed `random_state=seed`, so the upsampled data IS the same across iterations. DMatrix caching works for both strategies.

### 4.4 DMatrix Caching Implementation Sketch

```python
# Pre-build fold DMatrices for both strategies
cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
fold_data_spw = []  # scale_pos_weight folds
fold_data_ups = []  # upsampling folds

for train_idx, val_idx in cv.split(X, y):
    X_tr, y_tr = X[train_idx], y[train_idx]
    X_val, y_val = X[val_idx], y[val_idx]
    
    # SPW fold
    dtrain_spw = xgb.DMatrix(X_tr, label=y_tr)
    dval = xgb.DMatrix(X_val, label=y_val)
    fold_data_spw.append((dtrain_spw, dval, y_val))
    
    # Upsampled fold
    X_tr_up, y_tr_up = _upsample(X_tr, y_tr, seed)
    dtrain_ups = xgb.DMatrix(X_tr_up, label=y_tr_up)
    fold_data_ups.append((dtrain_ups, dval, y_val))

# In HP loop — only change params, reuse DMatrix
for params in param_samples:
    xgb_params = {**params, **device_kwargs, 'objective': 'binary:logistic'}
    
    # SPW scoring
    for dtrain, dval, y_val in fold_data_spw:
        model = xgb.train(xgb_params, dtrain, num_boost_round=params['n_estimators'])
        proba = model.predict(dval)
        auc = roc_auc_score(y_val, proba)
```

**Memory impact of DMatrix caching:** Each DMatrix stores data in internal format. With 5 folds × 2 strategies = 10 DMatrix objects. For ~600k rows × 45 features, each DMatrix is ~200MB. Total: ~2GB. This is significant — must account for it in the RAM budget. However, `xgb.DMatrix` with GPU stores data on GPU memory, not RAM. With CUDA, the RAM impact is minimal (GPU VRAM handles it). On CPU, 2GB is within budget for typical 16-32GB machines.

---

## 5. File Modification Plan

### 5.1 New Module: `src/sip_engine/shared/memory.py`

**Purpose:** `MemoryMonitor` class + adaptive chunk sizing logic + checkpoint utilities.

**Contents:**
- `MemoryMonitor` class with `check()`, `current_usage_bytes()`, `usage_ratio()`
- `adaptive_chunk_size(monitor, base_chunk_size)` → returns adjusted chunk_size
- `save_checkpoint(rows, path)` and `load_checkpoint(path)` for Parquet checkpointing
- `cleanup(*objects)` → `del` each + `gc.collect()`

### 5.2 Modified: `src/sip_engine/shared/data/loaders.py`

- Add `chunk_size: int | None = None` parameter to `_load_csv()` and all public loader functions
- If provided, override `settings.chunk_size` for that call

### 5.3 Modified: `src/sip_engine/shared/data/label_builder.py`

- `build_labels(force, n_jobs=1, max_ram_gb=None)` — extended signature
- Add MemoryMonitor integration
- Extract row-processing logic into a worker function for multiprocessing
- Add lifecycle `del` + `gc.collect()` calls
- Note: Labels is the simplest step — M1/M2 use set operations (already fast), M3/M4 use iterrows. M3/M4 computation is the parallelization target.

### 5.4 Modified: `src/sip_engine/classifiers/iric/pipeline.py`

- `build_iric(force, n_jobs=1, max_ram_gb=None)` — extended signature
- Extract main IRIC loop (lines 282-361) into `_process_iric_chunk()` worker function
- Add multiprocessing pool for chunk-level parallelism
- Add MemoryMonitor integration + checkpoint support
- Add lifecycle cleanup

### 5.5 Modified: `src/sip_engine/classifiers/features/pipeline.py`

- Extend `build_features()` to use multiprocessing for the main contratos streaming loop
- Extract lines 415-470 into `_process_features_chunk()` worker function
- Add MemoryMonitor integration + checkpoint support
- Add lifecycle cleanup
- **Progress display integration:** The existing `FeatureBuildProgressDisplay` tracks rows — update it from main process after each chunk completes

### 5.6 Modified: `src/sip_engine/classifiers/models/trainer.py`

- Modify `_cv_score_scale_pos_weight()` and `_cv_score_upsampling()` to accept pre-built DMatrix objects
- Modify `_hp_search()` to pre-build DMatrix objects before the loop
- Add `max_bin=512` to device_kwargs when CUDA is detected
- Keep `XGBClassifier` for final refit (line ~1070+) — only CV loop switches to native API

### 5.7 Modified: `src/sip_engine/pipeline.py`

- `run_labels(cfg)` — pass `n_jobs=cfg.n_jobs, max_ram_gb=cfg.max_ram_gb`
- `run_iric(cfg)` — pass `n_jobs=cfg.n_jobs, max_ram_gb=cfg.max_ram_gb`
- (run_features already passes these)

---

## 6. Risk Analysis

### 6.1 Multiprocessing Risks

| Risk | Mitigation |
|------|-----------|
| Pickle overhead for large chunks | Each 50k-row chunk is ~20-40 MB serialized — acceptable for IPC |
| Lookup dict serialization on spawn | Use pool initializer + temp pickle — one-time cost per worker |
| Worker crash from memory | Workers don't monitor memory independently — main process controls dispatch rate |
| Deadlocks from pool.imap | Use `pool.imap_unordered` with timeouts; wrap in try/finally for pool cleanup |
| Windows `spawn` start method | Module-level globals + initializer pattern works cross-platform |
| Non-determinism from unordered results | Acceptable — results are accumulated in a list, final sort by id_contrato if needed |

### 6.2 RAM Management Risks

| Risk | Mitigation |
|------|-----------|
| RSS measurement includes shared pages | Conservative — overestimates usage on fork platforms (safe) |
| Race between memory check and dispatch | Check before dispatching each chunk batch — no async dispatch |
| Checkpoint file corruption on crash | Write checkpoint atomically (write to temp, rename) |
| Checkpoint stale after code change | Include a version hash in checkpoint metadata; invalidate on mismatch |

### 6.3 GPU Optimization Risks

| Risk | Mitigation |
|------|-----------|
| DMatrix API differs from sklearn API | Map params carefully: `n_estimators` → `num_boost_round`, remove from params dict |
| DMatrix VRAM overflow | With ~600k rows × 45 features at float32, ~100MB per DMatrix — well within GPU VRAM (typically 4-24 GB) |
| scale_pos_weight handling in native API | Pass directly in params dict to `xgb.train()` — supported natively |
| GPU fallback path must still work | Keep existing `try/except` GPU→CPU fallback; DMatrix caching is a CUDA-only optimization, CPU path stays unchanged |

---

## 7. Testing Strategy

### 7.1 Unit Tests for MemoryMonitor

- Test `check()` returns correct status at various mock RSS levels
- Test `adaptive_chunk_size()` halves at 90%, minimum floor at 1000
- Test checkpoint save/load round-trip

### 7.2 Unit Tests for Multiprocessing Worker Functions

- Test `_process_iric_chunk()` produces correct output for a small chunk
- Test `_process_features_chunk()` produces correct output
- Test with `n_jobs=1` (no pool) produces identical results to current implementation
- **Determinism test:** Same input with `n_jobs=1` vs `n_jobs=2` should produce same set of output rows (order may differ)

### 7.3 Integration Tests

- Existing `test_pipeline.py` and `test_pipeline16.py` cover end-to-end pipeline
- Run with `n_jobs=2` to verify multiprocessing works without error
- Verify output parquet files are identical (or equivalent) to single-threaded output

### 7.4 GPU Tests

- Test DMatrix caching path produces same CV scores as current sklearn path
- Mock GPU device for CI (no GPU in GitHub Actions)

---

## 8. Dependencies & Compatibility

### 8.1 No New Dependencies

- `multiprocessing` — stdlib
- `psutil` — already in deps (used in progress.py, detector.py)
- `gc` — stdlib
- `tempfile` — stdlib
- `xgb.DMatrix`, `xgb.train()` — already have `xgboost` in deps

### 8.2 Platform Compatibility

- macOS (dev): `fork` start method default — COW for free, but module-globals pattern also works
- Windows 10 (test): `spawn` start method — module-globals + initializer handles this
- Linux (deploy): `fork` default — same as macOS
- Docker: Linux-based — `fork` works. Container cgroup RAM limits already detected by `detector.py`

### 8.3 Python 3.12

- `multiprocessing.Pool` fully supported
- No known issues with `fork` safety on Python 3.12 (but note: Python 3.12 deprecates `fork` as default on macOS due to potential issues with forking multithreaded processes — our case is single-threaded before fork, so safe)

---

## 9. Performance Expectations

### 9.1 Multiprocessing Speedup

With `n_jobs=4` on a 4-core machine:
- Lookup building: no change (still sequential, I/O-bound)
- Main contratos streaming: theoretical ~3.5x speedup (accounting for IPC overhead)
- Expected wall-clock improvement: 50-70% reduction for feature/IRIC/label build steps

### 9.2 GPU Optimization Speedup

- DMatrix caching eliminates ~200 data transfer events per HP iteration (200 iter × 10 fits)
- `max_bin=512` increases GPU work per split by ~2x
- Expected: GPU utilization from 2-3% average → 20-40% average
- Wall-clock HP search improvement: estimated 20-40% faster with CUDA

### 9.3 RAM Overhead

- MemoryMonitor: negligible (<1 KB)
- Pool workers: each holds one chunk (~20-40 MB) — with 4 workers, ~80-160 MB additional
- DMatrix caching: ~200 MB per DMatrix × 10 = ~2 GB (on GPU VRAM for CUDA, RAM for CPU)

---

## 10. Implementation Ordering

### Recommended Plan Structure: 2 Plans

**Plan 17-01: RAM Management + Lifecycle Cleanup + Checkpoint System**
- New `memory.py` module (MemoryMonitor, adaptive chunk sizing, checkpoint)
- Modify `loaders.py` for dynamic chunk_size parameter
- Add lifecycle `del` + `gc.collect()` to all three build steps
- Add checkpoint save/abort/resume to all three build steps
- Extend `build_labels()` and `build_iric()` signatures
- Update `pipeline.py` run_labels/run_iric to pass config
- Tests for MemoryMonitor + checkpoint

**Plan 17-02: Multiprocessing + GPU Optimization**
- Extract worker functions for labels, IRIC, features
- Add multiprocessing pool with module-globals initializer pattern
- Integrate with MemoryMonitor from Plan 01 for adaptive chunk dispatch
- DMatrix caching for HP search
- max_bin=512 for CUDA training
- Integration tests with n_jobs=2
- GPU CV scoring tests

This ordering ensures Plan 01 provides the foundation (monitoring, cleanup, checkpointing) that Plan 02 builds upon (parallelism under memory constraints).

---

*Research complete. Ready for gsd-planner consumption.*
