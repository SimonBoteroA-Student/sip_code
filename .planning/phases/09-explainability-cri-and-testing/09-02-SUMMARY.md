---
phase: 09-explainability-cri-and-testing
plan: "02"
subsystem: explainability
tags: [analyze-contract, deterministic-json, system-test, proj-04, shap, cri, xgboost]
requirements: [PROJ-03, PROJ-04]

dependency_graph:
  requires:
    - src/sip_engine/explainability/shap_explainer.py (extract_shap_top_n)
    - src/sip_engine/explainability/cri.py (compute_cri, classify_risk_level)
    - src/sip_engine/features/pipeline.py (compute_features)
    - src/sip_engine/config/settings.py (artifacts_models_dir)
    - artifacts/models/{M1,M2,M3,M4}/ (model.pkl, feature_registry.json)
  provides:
    - sip_engine.explainability.analyze_contract (per-contract analysis entry point)
    - sip_engine.explainability.serialize_to_json (deterministic JSON serialisation)
    - tests/test_system.py (master dual-mode system test)
  affects:
    - future v2 REST API (POST /api/v1/analyze calls analyze_contract)

tech_stack:
  added: []
  patterns:
    - Module-level import for monkeypatching (analyzer.py imports compute_features at top level)
    - Frozen timestamp pattern for deterministic JSON output
    - pytest.mark.system custom marker for dual-mode system tests
    - monkeypatch.setattr on module-level reference for clean test isolation

key_files:
  created:
    - src/sip_engine/explainability/analyzer.py
    - tests/test_system.py
  modified:
    - src/sip_engine/explainability/__init__.py (added analyze_contract, serialize_to_json)
    - tests/test_explainability.py (added tests 15-19, toy_model_dir fixture)
    - pyproject.toml (added [tool.pytest.ini_options] with system marker)

decisions:
  - "compute_features imported at module level in analyzer.py (not lazy) — enables monkeypatch.setattr in tests without ModuleNotFoundError; safe because features.pipeline does not import from explainability"
  - "timestamp parameter defaults to UTC now if None — caller freezes it for deterministic output"
  - "Missing model dirs degrade gracefully — log warning and default probability to 0.0 for that model"
  - "PROJ-04 gap audit: all 4 criteria covered by existing tests — no new gap tests required"
  - "pytest.mark.system registered in pyproject.toml to eliminate PytestUnknownMarkWarning"

metrics:
  duration: "7 min"
  completed: "2026-03-02"
  tasks: 2
  files_created: 2
  files_modified: 3
---

# Phase 9 Plan 02: Per-Contract Analyzer and System Test Summary

**One-liner:** `analyze_contract()` entry point composing features→models→SHAP→CRI into deterministic sorted-key JSON, with 7-test unit coverage and dual-mode system test.

## What Was Built

### `analyzer.py` — Per-Contract Analysis Entry Point (PROJ-03)

`analyze_contract()` integrates the full pipeline in a single call:

1. **Feature extraction** — calls `compute_features()` (same signature, train-serve parity FEAT-07)
2. **Model loading** — loads M1–M4 `model.pkl` + `feature_registry.json` from `models_dir`
3. **Per-model inference** — `model.predict_proba(X)[:, 1][0]` → probability (6dp)
4. **SHAP attribution** — `extract_shap_top_n(model, X, feature_names, n=10)` per model
5. **CRI scoring** — `compute_cri(p_m1, p_m2, p_m3, p_m4, iric_score, weights)` → score
6. **Risk classification** — `classify_risk_level(cri_score)` → one of 5 band strings
7. **Result assembly** — structured dict with contract_id, cri, models, iric_score, raw_features, metadata

**Private helpers:**
- `_serialize_value(v)` — converts numpy int/float/bool_ to Python-native types, rounds floats to 6dp, NaN → None
- `_load_model_artifacts(models_dir, model_id)` — loads model.pkl + feature_registry.json, extracts version from training_date

`serialize_to_json(result_dict)` — `json.dumps(sort_keys=True, ensure_ascii=False)`. Combined with pre-rounded floats and a frozen `timestamp` input, this guarantees byte-identical output for repeated calls.

### Tests Added to `test_explainability.py` (Tests 15-19)

New `toy_model_dir` module-scoped fixture creates 4 model dirs (M1–M4), each with:
- Tiny XGBClassifier (n_estimators=5, max_depth=2) trained on 50×34 synthetic rows
- `model.pkl`, `feature_registry.json`, `training_report.json`

5 new tests:
- **test_analyze_contract_returns_required_keys** — validates top-level schema
- **test_analyze_contract_cri_block_has_score_level_weights** — CRI float/str/5-key dict
- **test_analyze_contract_shap_top10_per_model** — 4 models, each with probability∈[0,1] and shap_top10 list
- **test_json_determinism_byte_identical** — frozen timestamp → byte-identical serialised JSON
- **test_json_sort_keys_verified** — recursive check that every nested dict has sorted keys

### `tests/test_system.py` — Master Dual-Mode System Test

`test_full_pipeline_fixture_mode` (CI-friendly):
- Monkeypatches `compute_features` → synthetic 34-feature dict
- Creates M1–M4 toy models via `toy_models_dir` fixture
- Calls `analyze_contract()` on a synthetic contract row
- Asserts full schema, CRI [0,1] and valid level, per-model probabilities, 34 raw features, valid JSON, byte-identical determinism

`test_full_pipeline_real_data` (skipped by default):
- Requires `--real-data` flag and `artifacts/models/M1/model.pkl`
- Same assertions as fixture mode but with real trained models

**PROJ-04 audit** documented as comment block:
1. RCAC round-trips ✓ — `test_lookup_normalizes_input`, `test_lookup_hit_returns_record`
2. Provider as-of-date ✓ — `test_lookup_future_contracts_excluded`, `test_lookup_same_day_excluded`
3. IRIC components ≥4 ✓ — 15+ component tests in `test_iric.py`
4. predict_proba [0,1] ✓ — `test_train_model_end_to_end_quick` (M1–M4 parametrized)

No gap tests needed — all criteria covered by existing test suite.

## Test Results

```
19 passed  (tests/test_explainability.py — 14 prior + 5 new)
1 passed, 1 skipped  (tests/test_system.py — fixture mode + real-data skipped)
349 passed, 1 skipped, 3 warnings  (full suite — 343 prior + 6 new)
3 scipy RuntimeWarnings — pre-existing, unrelated to this plan
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] compute_features lazy import prevented monkeypatching**

- **Found during:** Task 2 test execution
- **Issue:** `compute_features` was imported inside `analyze_contract()` with `from sip_engine.features.pipeline import compute_features` — a local variable in the function body. `monkeypatch.setattr(_analyzer_mod, "compute_features", ...)` raised `AttributeError` because the attribute didn't exist at module level.
- **Fix:** Moved `compute_features` import to module level in `analyzer.py`. Added docstring comment explaining this is safe (no circular imports) and intentional for testability.
- **Files modified:** `src/sip_engine/explainability/analyzer.py`
- **Commit:** cc3a7d6

**2. [Rule 2 - Missing critical] pytest.mark.system PytestUnknownMarkWarning**

- **Found during:** Task 2 test execution
- **Issue:** `@pytest.mark.system` on two tests triggered `PytestUnknownMarkWarning` — mark not registered anywhere in the project configuration.
- **Fix:** Added `[tool.pytest.ini_options]` section to `pyproject.toml` with the `system` marker definition.
- **Files modified:** `pyproject.toml`
- **Commit:** cc3a7d6

## Self-Check

**Result: PASSED**

- `src/sip_engine/explainability/analyzer.py` ✓
- `src/sip_engine/explainability/__init__.py` ✓
- `tests/test_explainability.py` ✓
- `tests/test_system.py` ✓
- `.planning/phases/09-explainability-cri-and-testing/09-02-SUMMARY.md` ✓
- Commit `3a76a51` (Task 1 — analyzer.py) ✓
- Commit `cc3a7d6` (Task 2 — tests) ✓
