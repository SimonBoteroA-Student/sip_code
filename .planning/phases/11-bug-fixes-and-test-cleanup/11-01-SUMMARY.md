---
phase: 11-bug-fixes-and-test-cleanup
plan: "01"
subsystem: iric-calculator, test-isolation
tags: [bug-fix, iric, tests, provider-history]
dependency_graph:
  requires: []
  provides: [IRIC-03]
  affects: [src/sip_engine/iric/calculator.py, tests/test_iric.py, tests/test_models.py]
tech_stack:
  added: []
  patterns: [dict-key-mismatch-fix, monkeypatch-isolation]
key_files:
  created: []
  modified:
    - src/sip_engine/iric/calculator.py
    - tests/test_iric.py
    - tests/test_models.py
decisions:
  - "Use _ZERO_RESULT from provider_history.py as schema template for integration tests — real schema, not synthetic"
  - "Patch artifacts_models_dir to tmp_path in test_models.py to prevent early return at model.pkl existence check"
metrics:
  duration: "5 min"
  completed: "2026-03-02"
  tasks: 2
  files: 3
---

# Phase 11 Plan 01: IRIC Key Mismatch Fix + Test Isolation Summary

**One-liner:** Fixed 3 silent IRIC provider_history key mismatches (components 3/9/10 always returned 0) and isolated 2 environment-sensitive test_models.py tests from real disk artifacts.

## What Was Built

### Task 1: IRIC Calculator Key Mismatch Fix

Fixed 3 wrong dict key names in `calculator.py` that caused components 3, 9, and 10 to silently return 0 for all providers with history (`.get()` missed every time due to key name mismatch with `provider_history.py`).

**calculator.py fixes:**
- Component 3 (`historial_proveedor_alto`): `"num_contratos"` → `"num_contratos_previos_nacional"`
- Component 9 (`proveedor_sobrecostos_previos`): `"num_sobrecostos"` → `"num_sobrecostos_previos"`
- Component 10 (`proveedor_retrasos_previos`): `"num_retrasos"` → `"num_retrasos_previos"`
- Updated docstring to match actual key names

**test_iric.py fixes (6 locations):**
- `provider_history_normal` fixture: all 6 keys updated to real schema
- `TestHistorialProveedorAlto`: 2 inline dicts updated
- `TestProveedorSobrecostosPrevios`: 2 inline dicts updated
- `TestProveedorRetrasosPrevios`: 1 inline dict updated

**New integration test class `TestIRICProviderHistoryIntegration` (4 tests):**
- `test_component_9_fires_with_real_schema_key`: num_sobrecostos_previos=2 → component 9 = 1
- `test_component_10_fires_with_real_schema_key`: num_retrasos_previos=3 → component 10 = 1
- `test_component_3_fires_with_real_schema_key`: num_contratos_previos_nacional=10 > p95=3 → component 3 = 1
- `test_all_zero_result_fires_nothing`: _ZERO_RESULT → components 3, 9, 10 all return 0

### Task 2: test_models.py Isolation

Root cause: `train_model()` checks `(model_dir / "model.pkl").exists()` BEFORE checking `features_path`/`labels_path`. When real model artifacts exist on disk, it returns early — never reaching the `FileNotFoundError` the tests expected.

**Fix:** Added `monkeypatch.setattr(get_settings(), "artifacts_models_dir", tmp_path / "models")` to both tests before the features_path/labels_path patches, redirecting the model dir lookup to an empty tmp directory.

## Verification

**Full test suite: 375 passed, 1 skipped (intentional --real-data flag), 0 failures**

- `tests/test_iric.py`: 84 passed (includes 4 new integration tests)
- `tests/test_models.py::test_train_model_missing_features`: PASSED
- `tests/test_models.py::test_train_model_missing_labels`: PASSED

Key checks:
```
grep -n "num_sobrecostos_previos" src/sip_engine/iric/calculator.py  # line 332 ✓
grep -n "num_retrasos_previos" src/sip_engine/iric/calculator.py     # line 340 ✓
grep -n "num_contratos_previos_nacional" src/sip_engine/iric/calculator.py  # line 246 ✓
grep -n "artifacts_models_dir" tests/test_models.py  # both tests ✓
```

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1    | f9b1ec6 | fix(11-01): correct provider_history key mismatches in IRIC calculator + integration tests |
| 2    | a5b45ba | fix(11-01): isolate test_models.py tests from real model artifacts on disk |

## Self-Check: PASSED
