# Phase 11: Bug Fixes and Test Cleanup - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix two known bugs: (1) IRIC calculator key mismatch causing components 9/10 to always return 0, and (2) two environment-sensitive test failures in test_models.py. Close tech debt items td-3 and td-5. No new capabilities — code-only fixes with test verification.

</domain>

<decisions>
## Implementation Decisions

### IRIC Key Fix
- Fix key names in `calculator.py` lines 332, 340: `num_sobrecostos` → `num_sobrecostos_previos`, `num_retrasos` → `num_retrasos_previos`
- Update the docstring (lines 193-194) to match actual key names
- Add integration test using a real slice of contratos data:
  - Find a provider with M1=1 contracts → verify component 9 fires (returns 1)
  - Find a provider with M2=1 contracts → verify component 10 fires (returns 1)
  - Verify a clean provider (no prior overruns/delays) returns 0 for both components
- Compute actual provider history from real data, don't use synthetic dicts
- No downstream IRIC score distribution comparison needed — integration test proving components fire is sufficient

### Test Isolation
- Root cause identified: `train_model()` checks `(model_dir / "model.pkl").exists()` BEFORE checking features/labels paths. When real model artifacts exist on disk, function returns early — never reaches the `FileNotFoundError` code the tests expect
- Fix: also patch `artifacts_models_dir` to `tmp_path` so no real model.pkl is found
- Add a brief comment in each test explaining the early-return trap (why `artifacts_models_dir` must be patched)
- Approach: fix Settings patching on the cached singleton (current pattern), not dependency injection or filesystem mocking

### Retrain
- Code-only fix — user runs pipeline separately (same pattern as Phase 10)
- IRIC fix will change component 9/10 values → changes IRIC scores → affects model features. Retrain needed for accurate results, but not in this phase

### Test Targets
- Target: 371 pass, 0 fail, 1 intentional skip (`test_system.py:242` requires `--real-data` flag — not a bug)
- Current: 369 pass, 2 fail, 1 skip

### Tech Debt Tracking
- Close td-3 (IRIC key mismatch) and td-5 (broken tests) in planning/tracking docs after fixes verified

</decisions>

<specifics>
## Specific Details

### Bug 1: IRIC Key Mismatch (td-3)
- **File:** `src/sip_engine/iric/calculator.py` lines 332, 340
- **Issue:** Reads `provider_history.get("num_sobrecostos", 0)` but `provider_history.py` returns key `"num_sobrecostos_previos"`
- **Effect:** Components 9 (`proveedor_sobrecostos_previos`) and 10 (`proveedor_retrasos_previos`) always return 0 for every provider
- **Confirmed:** `provider_history.py` lines 60-61 (defaults), 343-344 (return dict) use `_previos` suffix

### Bug 2: Test Isolation (td-5)
- **File:** `tests/test_models.py` lines 346-370
- **Tests:** `test_train_model_missing_features`, `test_train_model_missing_labels`
- **Root cause:** `train_model()` line 539 checks `(model_dir / "model.pkl").exists()` → returns early because `artifacts/models/M1/model.pkl` exists on disk. Tests only patch `features_path`/`labels_path` but not `artifacts_models_dir`
- **Fix:** Add `monkeypatch.setattr(get_settings(), "artifacts_models_dir", tmp_path / "models")` to both tests

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 11-bug-fixes-and-test-cleanup*
*Context gathered: 2026-03-02*
