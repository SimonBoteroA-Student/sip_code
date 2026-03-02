# Phase 11: Bug Fixes and Test Cleanup — Research

**Phase:** 11-bug-fixes-and-test-cleanup
**Researched:** 2026-03-02
**Question:** What do I need to know to PLAN this phase well?

---

## What This Phase Must Deliver

Fix two isolated bugs and verify test suite health before v1 milestone completion:

1. **IRIC calculator key mismatch (td-3)**: Components 9/10 always return 0 due to incorrect dict key names — breaks IRIC-03 requirement validation
2. **Test isolation failures (td-5)**: Two tests in `test_models.py` fail when real model artifacts exist on disk — environment-sensitive, prevents clean CI/CD

**No new capabilities.** Code-only fixes with test verification. Close tech debt items identified in v1 milestone audit.

---

## Bug 1: IRIC Key Mismatch (td-3)

### Root Cause Analysis

**Files:**
- `src/sip_engine/iric/calculator.py` lines 332, 340
- `src/sip_engine/features/provider_history.py` lines 60-61, 343-344

**The mismatch:**

```python
# calculator.py line 332 (Component 9)
num_sobrecostos = provider_history.get("num_sobrecostos", 0) or 0
# ❌ Wrong key name

# calculator.py line 340 (Component 10)
num_retrasos = provider_history.get("num_retrasos", 0) or 0
# ❌ Wrong key name

# provider_history.py lines 60-61 (_ZERO_RESULT dict)
"num_sobrecostos_previos": 0,
"num_retrasos_previos": 0,
# ✅ Actual key names (with "_previos" suffix)

# provider_history.py lines 343-344 (return dict)
"num_sobrecostos_previos": num_sobrecostos,
"num_retrasos_previos": num_retrasos,
# ✅ Confirmed — keys have "_previos" suffix
```

**Impact:**
- Components 9 and 10 always return 0 for ALL providers (even those with documented cost overruns/delays)
- IRIC scores are systematically underestimated
- Affects IRIC-03 requirement: "System calculates 3 anomaly dimension components: `proveedor_sobrecostos_previos`, `proveedor_retrasos_previos`, `ausencia_proceso`"

**Why tests didn't catch this:**
- Existing tests in `test_iric.py` pass synthetic dicts with the WRONG key names: `{"num_sobrecostos": 2, "num_retrasos": 0}` (line 653 context)
- Tests verify component logic but use non-production dict keys — test data matched implementation bug
- Integration gap: no test uses `lookup_provider_history()` output directly

### Fix Strategy

**Code changes (minimal):**
1. `calculator.py` line 332: `"num_sobrecostos"` → `"num_sobrecostos_previos"`
2. `calculator.py` line 340: `"num_retrasos"` → `"num_retrasos_previos"`
3. Update docstring (lines 193-194) to match actual key names returned by `provider_history.py`

**Test updates (fix false positives):**
- Update all test fixtures in `test_iric.py` that pass synthetic `provider_history` dicts:
  - `test_proveedor_sobrecostos_previos_with_history` (line ~653)
  - `test_proveedor_sobrecostos_previos_zero_sobrecostos` (line ~663)
  - `test_proveedor_retrasos_previos_*` tests (similar pattern)
- Change `"num_sobrecostos"` → `"num_sobrecostos_previos"` in all test dicts
- Change `"num_retrasos"` → `"num_retrasos_previos"` in all test dicts

**Integration test (NEW — user decision from CONTEXT.md):**

Add test using real slice of contratos data to verify components fire:
- Find provider with M1=1 contracts → verify component 9 returns 1
- Find provider with M2=1 contracts → verify component 10 returns 1
- Find provider with no prior overruns/delays → verify both return 0
- Compute provider history from actual data using `build_provider_history_index()` → `lookup_provider_history()` path
- **Do NOT use synthetic dicts** — validates end-to-end wiring

**No IRIC score distribution comparison needed** (per user decision) — integration test proving components fire is sufficient verification.

---

## Bug 2: Test Isolation Failures (td-5)

### Root Cause Analysis

**Files:**
- `tests/test_models.py` lines 346-371
- `src/sip_engine/models/trainer.py` lines 535-543

**The early return trap:**

```python
# trainer.py lines 537-543
model_dir = settings.artifacts_models_dir / model_id
if (model_dir / "model.pkl").exists() and not force:
    logger.info("Model %s already exists at %s. Use --force to retrain.", ...)
    return model_dir  # ⚠️ Returns BEFORE checking features_path/labels_path
```

**Why tests fail when artifacts exist:**
1. Tests patch `features_path` / `labels_path` to non-existent paths in `tmp_path`
2. Tests expect `FileNotFoundError` when `train_model()` tries to load missing files
3. BUT: `train_model()` checks `(model_dir / "model.pkl").exists()` FIRST (line 537)
4. When real `artifacts/models/M1/model.pkl` exists on disk → function returns early (line 543)
5. Never reaches the feature/label loading code → never raises the expected error

**Current test code:**
```python
# test_models.py line 349-350
monkeypatch.setattr(get_settings(), "features_path", tmp_path / "features.parquet")
monkeypatch.setattr(get_settings(), "labels_path", tmp_path / "labels.parquet")
# ❌ Missing: artifacts_models_dir patch
```

**Why this is environment-sensitive:**
- Tests pass on fresh checkout (no artifacts exist yet)
- Tests fail after running full pipeline (artifacts/models/M1/model.pkl now exists)
- CI/CD with clean environments would pass, local development fails

### Fix Strategy

**Minimal fix (user-approved approach from CONTEXT.md):**

Patch `artifacts_models_dir` to `tmp_path` in both tests to prevent early return:

```python
# test_models.py line 346-353 (test_train_model_missing_features)
monkeypatch.setattr(get_settings(), "artifacts_models_dir", tmp_path / "models")  # NEW
monkeypatch.setattr(get_settings(), "features_path", tmp_path / "features.parquet")
monkeypatch.setattr(get_settings(), "labels_path", tmp_path / "labels.parquet")

# test_models.py line 361-371 (test_train_model_missing_labels)  
monkeypatch.setattr(get_settings(), "artifacts_models_dir", tmp_path / "models")  # NEW
# ... rest stays the same
```

**Add explanatory comment** in each test:
```python
# Patch artifacts_models_dir to tmp_path to prevent early return when real model.pkl exists.
# train_model() checks (model_dir / "model.pkl").exists() BEFORE features_path/labels_path.
```

**Why this approach:**
- Minimal change: 1 line + 1 comment per test
- No refactoring of `trainer.py` logic
- No dependency injection changes
- No filesystem mocking
- Uses existing Settings patching pattern (see STATE.md decision: "Phase 02-data-loaders: autouse clear_settings_cache fixture in conftest.py isolates lru_cache singleton per test")

**Alternative approaches considered and rejected:**
1. **Filesystem mocking (`mock_open`)**: Over-engineering for this issue
2. **Dependency injection of paths**: Breaking change to `train_model()` API
3. **Reordering checks in `trainer.py`**: Risky — early return is intentional optimization
4. **Mock `(model_dir / "model.pkl").exists()`**: Fragile, tests implementation detail

---

## Retrain Decision

**User decision from CONTEXT.md:**
> "Code-only fix — user runs pipeline separately (same pattern as Phase 10)"

**Rationale:**
- IRIC fix changes component 9/10 values → changes IRIC scores → affects model features
- Model retraining needed for accurate production results
- BUT: Phase 11 scope is code fixes, not full pipeline rebuild
- Retrain deferred to user's manual pipeline run (matches Phase 10 workflow)

**No code changes needed for retrain** — existing `sip build-all` command handles full rebuild.

---

## Test Targets

**Current state:**
- 369 tests pass
- 2 tests fail: `test_train_model_missing_features`, `test_train_model_missing_labels`
- 1 intentional skip: `test_system.py:242` (requires `--real-data` flag — not a bug)

**Target state after Phase 11:**
- 371 tests pass
- 0 tests fail
- 1 intentional skip (unchanged)

**Verification command:**
```bash
python -m pytest tests/ -v --tb=short
```

---

## Tech Debt Closure

**Documents to update after verification:**

1. `.planning/ROADMAP.md` — Phase 11 status: Pending → Complete
2. `.planning/v1-MILESTONE-AUDIT.md` frontmatter — Remove td-3 and td-5 from `tech_debt` list
3. `.planning/REQUIREMENTS.md` traceability table — IRIC-03: "Re-verification Pending" → "Complete"

**No new tech debt expected** — fixes are surgical and well-scoped.

---

## Key Implementation Insights

### 1. Dict Key Naming Convention Pattern

**Discovered pattern:**
- Features stored in Provider History Index use `*_previos` suffix (adjective form)
- This distinguishes "historical prior counts" from "current contract counts"
- Example: `num_sobrecostos_previos` = count of PRIOR cost overruns (as of contract date)
- vs. hypothetical `num_sobrecostos` = current contract overrun flag (doesn't exist)

**Why the mismatch happened:**
- Calculator likely written before Provider History module finalized schema
- No integration test exercising end-to-end wiring
- Unit tests passed synthetic dicts, hiding the key name drift

### 2. Settings Singleton Patching Pattern

**Critical pattern from conftest.py (referenced in STATE.md):**
```python
@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear lru_cache on get_settings() before each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

**Why this matters:**
- `get_settings()` uses `@lru_cache` — returns same instance across calls
- `monkeypatch.setattr(get_settings(), "key", value)` modifies the cached singleton
- `autouse` fixture ensures clean slate per test
- Tests can safely patch Settings fields without cross-test pollution

**For Phase 11 fixes:**
- `artifacts_models_dir` patch works BECAUSE of this fixture
- No additional setup needed — existing infra supports the fix

### 3. Test Design Lesson: Integration Gaps

**Why both bugs survived testing:**

Bug 1 (IRIC keys):
- Unit tests used **synthetic data matching implementation** instead of production schema
- No test called `lookup_provider_history()` → `compute_iric_components()` end-to-end

Bug 2 (test isolation):
- Tests validated logic but not **environmental assumptions** (artifact existence)
- Missing patch revealed by state change (pipeline execution creates artifacts)

**Mitigation for Phase 11:**
- Add integration test using real `provider_history.py` output (Bug 1)
- Patch all environment-sensitive paths in isolation tests (Bug 2)

### 4. Test Suite Execution Order

**From audit:**
- 80 tests in `test_iric.py` (largest test file)
- Tests distributed across 10 modules
- Parallel execution via pytest-xdist (implied by "06-02: tests written to test_bid_stats.py to avoid merge conflicts")

**For Phase 11:**
- Integration test should go in `test_iric.py` (IRIC component coverage)
- No merge conflicts expected (single-phase work)
- Can run subset: `pytest tests/test_iric.py tests/test_models.py -v` for quick validation

---

## Research Findings Summary

**What the planner needs to know:**

1. **IRIC fix is 3-line change** (2 key names + 1 docstring) with test fixture updates
2. **Test isolation fix is 2-line change** (artifacts_models_dir patch × 2 tests) with comments
3. **Integration test pattern:** Use real contratos slice + actual `lookup_provider_history()` output
4. **No retrain in this phase** — code-only scope, user runs pipeline separately
5. **Existing Settings patching infra supports all fixes** — no new test scaffolding needed
6. **Success metric:** 371 pass, 0 fail, 1 skip (target clear and measurable)

**Critical dependencies:**
- No external dependencies
- No schema changes
- No artifact rebuilds required by phase itself
- All fixes are internal code corrections

**Risk assessment:**
- **Low risk** — changes are surgical and localized
- Both bugs have clear root cause analysis
- Test coverage validates fixes
- No backward compatibility concerns (internal implementation details)

---

## Open Questions for Planner

**None.** All necessary context provided in CONTEXT.md and confirmed via code inspection.

User decisions are explicit:
- ✅ Fix strategy approved (key rename + artifacts_models_dir patch)
- ✅ Integration test scope defined (real data slice, no distribution comparison)
- ✅ Retrain scope clarified (deferred to user's manual run)
- ✅ Tech debt closure process defined (3 documents to update)

**Planner can proceed directly to task breakdown.**

---

*Research complete: 2026-03-02*
*Context source: 11-CONTEXT.md, REQUIREMENTS.md, STATE.md, code inspection*
*Ready for: gsd-planner agent*
