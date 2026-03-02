# Phase 11: Bug Fixes and Test Cleanup - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix two known bugs: (1) IRIC calculator key mismatch causing components 9/10 to always return 0, and (2) two environment-sensitive test failures in test_models.py. No new capabilities — code-only fixes with test verification.

</domain>

<decisions>
## Implementation Decisions

### IRIC Key Fix Scope
- Fix the key names in calculator.py (lines 332, 340): `num_sobrecostos` → `num_sobrecostos_previos`, `num_retrasos` → `num_retrasos_previos`
- Update the docstring (lines 193-194) to match the actual key names
- Add unit test(s) verifying components 9 and 10 return 1 when provider_history contains non-zero values for the correct keys
- Existing IRIC tests should continue passing (they test with 0 values which work either way)

### Test Isolation Approach
- Fix `test_train_model_missing_features` and `test_train_model_missing_labels` by ensuring Settings paths point to non-existent tmp_path locations
- Root cause: monkeypatch.setattr on the cached Settings singleton doesn't take effect because train_model resolves paths before the patch, or real artifacts on disk satisfy the existence check
- Fix pattern: ensure the monkeypatch targets the correct attribute resolution path so train_model sees tmp_path-based paths that don't exist

### Retrain Requirement
- This phase fixes code only — no pipeline rerun within the phase
- User runs the pipeline separately after fixes (same pattern as Phase 10)
- The IRIC fix will change components 9/10 values, which affects IRIC scores and downstream model features — retrain needed for accurate results

</decisions>

<specifics>
## Specific Details

### Bug 1: IRIC Key Mismatch (td-3)
- **File:** `src/sip_engine/iric/calculator.py` lines 332, 340
- **Issue:** Reads `provider_history.get("num_sobrecostos", 0)` but provider_history.py returns key `"num_sobrecostos_previos"`
- **Effect:** Components 9 (`proveedor_sobrecostos_previos`) and 10 (`proveedor_retrasos_previos`) always return 0
- **Confirmed:** provider_history.py lines 60-61, 343-344 use `_previos` suffix

### Bug 2: Test Isolation (td-5)
- **File:** `tests/test_models.py` lines 346-370
- **Issue:** Tests expect FileNotFoundError but real artifacts exist on disk, so no error raised
- **Current state:** 369 pass, 2 fail, 1 skip (371 total)
- **Target:** 371 pass, 0 fail, 1 skip (or all 372 pass if skip is resolvable)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 11-bug-fixes-and-test-cleanup*
*Context gathered: 2026-03-02*
