---
phase: 06-iric
verified: 2026-03-01T00:00:00Z
status: passed
score: 9/9 must-haves verified
gaps: []
human_verification: []
---

# Phase 6: IRIC Verification Report

**Phase Goal:** The Contractual Irregularity Risk Index (IRIC) calculates all 11 binary components plus kurtosis and normalized relative difference anomaly measures, calibrated at national level by contract type using training data only, and outputs iric_thresholds.json
**Verified:** 2026-03-01
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | All 6 competition components fire correctly | VERIFIED | `calculator.py` lines 226-288: unico_proponente, proveedor_multiproposito, historial_proveedor_alto, contratacion_directa, regimen_especial, periodo_publicidad_extremo all implemented with correct logic and VigIA semantics |
| 2 | Both transparency components fire correctly | VERIFIED | `calculator.py` lines 296-321: datos_faltantes (3 sub-checks via `_compute_datos_faltantes`) and periodo_decision_extremo implemented with None-when-no-procesos behavior |
| 3 | All 3 anomaly components fire correctly, 0 for new providers | VERIFIED | `calculator.py` lines 329-341: proveedor_sobrecostos_previos and proveedor_retrasos_previos explicitly return 0 (not None) for new providers; ausencia_proceso fires when procesos_data is None |
| 4 | IRIC total score = (1/11)*sum, dimension sub-scores computed | VERIFIED | `calculator.py` lines 363-426: compute_iric_scores() divides by 11/6/2/3 with None→0 via _val() helper; 4 score keys confirmed |
| 5 | calibrate_iric_thresholds produces percentiles by tipo_contrato with rare-type merging | VERIFIED | `thresholds.py` lines 72-159: rare types (< min_group_size) remapped to "Otro" before groupby; np.nanpercentile for P1/P5/P95/P99; metadata fields present |
| 6 | Threshold calibration accepts arbitrary DataFrame (IRIC-08) | VERIFIED | `thresholds.py` line 81: function accepts `df: pd.DataFrame` — no hardcoded data loading anywhere in the function; Phase 7 can call with train-only data |
| 7 | Kurtosis (n>=4, Fisher unbiased) and DRN per Imhof (2018) | VERIFIED | `bid_stats.py` lines 64-86: scipy_kurtosis(fisher=True, bias=False) for n>=4; DRN=(sorted[1]-sorted[0])/sorted[0] for n>=3 with zero-guard; NaN for insufficient bids |
| 8 | IRIC scores injected as Category D (4 features) in 34-feature vector | VERIFIED | `features/pipeline.py` lines 78-83: FEATURE_COLUMNS has 34 entries (iric_anomalias, iric_competencia, iric_score, iric_transparencia appended after Cat C); both build_features() and compute_features() call compute_iric with thresholds |
| 9 | build_iric() produces iric_scores.parquet with all 11 components + 4 scores + kurtosis + DRN | VERIFIED | `iric/pipeline.py` lines 44-70: _IRIC_ARTIFACT_COLUMNS lists all 19 columns; build_iric() orchestrates all 7 steps and writes parquet |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/sip_engine/iric/calculator.py` | compute_iric_components() and compute_iric_scores() | VERIFIED | 427 lines, full implementation of all 11 components + 4 score aggregations. Substantive: imports normalize_numero, get_threshold; extensive conditional logic per VigIA pattern. |
| `src/sip_engine/iric/thresholds.py` | calibrate_iric_thresholds(), load_iric_thresholds(), reset_iric_thresholds_cache(), get_threshold(), save_iric_thresholds() | VERIFIED | 291 lines, all 5 functions present. VigIA hardcoded fallbacks defined, np.nanpercentile used, module-level cache with reset matches established pattern from rcac_lookup.py. |
| `src/sip_engine/iric/bid_stats.py` | compute_bid_stats() and build_bid_stats_lookup() | VERIFIED | 177 lines, kurtosis via scipy.stats.kurtosis(fisher=True, bias=False), DRN formula documented in docstring per Imhof (2018). Streaming memory strategy via load_ofertas() generator. |
| `src/sip_engine/iric/pipeline.py` | build_iric() batch orchestrator and compute_iric() online function | VERIFIED | 426 lines, 7-step batch pipeline (thresholds → bid stats → procesos → provider history → num_actividades → stream contratos → write parquet). compute_iric() for online parity (FEAT-07). |
| `src/sip_engine/iric/__init__.py` | Public API re-exports for IRIC module (11 symbols) | VERIFIED | 39 lines, re-exports all 11 public symbols from 4 submodules (calculator, bid_stats, thresholds, pipeline). __all__ defined. |
| `src/sip_engine/features/pipeline.py` | Updated FEATURE_COLUMNS with 34 features including Category D | VERIFIED | FEATURE_COLUMNS lines 62-84 has exactly 34 entries; Category D (iric_anomalias, iric_competencia, iric_score, iric_transparencia) at end in alphabetical order. Kurtosis/DRN explicitly excluded per design decision (NaN-heavy). |
| `tests/test_iric.py` | Tests for all 11 components, scores, threshold calibration, pipeline | VERIFIED | 80 test functions covering calibration, rare-type merging, all 11 components with edge cases, 4 score formulas, compute_iric online, build_iric parquet creation, FEATURE_COLUMNS assertions, CLI test. |
| `tests/test_bid_stats.py` | Tests for kurtosis and DRN formulas | VERIFIED | 36 test functions across 9 test classes covering 0/1/2/3/4 bids, NaN filtering, zero/negative filtering, identical bids (degenerate kurtosis), and mocked build_bid_stats_lookup integration. Deviation from plan: placed in test_bid_stats.py instead of test_iric.py due to parallel execution protocol — correctly noted in SUMMARY. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `iric/calculator.py` | `iric/thresholds.py` | get_threshold() for percentile lookups | WIRED | `from sip_engine.iric.thresholds import get_threshold` at line 45; called at lines 154, 247, 282, 315 for valor/contratos/publicidad/decision thresholds |
| `iric/calculator.py` | `data/rcac_builder.py` | normalize_numero() for datos_faltantes document validation | WIRED | `from sip_engine.data.rcac_builder import normalize_numero` at line 44; called at line 125 in _compute_datos_faltantes() |
| `iric/bid_stats.py` | `data/loaders.py` | load_ofertas() generator for streaming | WIRED | `from sip_engine.data.loaders import load_ofertas` at line 20; `for chunk in load_ofertas()` at line 128 in build_bid_stats_lookup() |
| `iric/pipeline.py` | `iric/calculator.py` | compute_iric_components + compute_iric_scores | WIRED | `from sip_engine.iric.calculator import compute_iric_components, compute_iric_scores` at line 34; called at lines 323, 330 (batch) and 411, 418 (online) |
| `iric/pipeline.py` | `iric/bid_stats.py` | build_bid_stats_lookup for batch kurtosis/DRN | WIRED | `from sip_engine.iric.bid_stats import build_bid_stats_lookup, compute_bid_stats` at line 33; `build_bid_stats_lookup()` called at line 234 |
| `features/pipeline.py` | `iric/pipeline.py` | compute_iric called from both compute_features and build_features | WIRED | Lazy import in build_features() at line 319 (`from sip_engine.iric.pipeline import compute_iric as _compute_iric`); called at line 419. In compute_features() at line 562; called at line 573. Lazy import prevents circular dependency. |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| IRIC-01 | 06-01 | 6 competition components: unico_proponente, proveedor_multiproposito, historial_proveedor_alto, contratacion_directa, regimen_especial, periodo_publicidad_extremo | SATISFIED | `calculator.py` lines 226-288; 14 dedicated tests in test_iric.py (test_unico_proponente_*, test_contratacion_directa_*, etc.) |
| IRIC-02 | 06-01 | 2 transparency components: datos_faltantes (3 sub-checks), periodo_decision_extremo | SATISFIED | `calculator.py` lines 296-321 + `_compute_datos_faltantes()` lines 95-163; 7 dedicated tests |
| IRIC-03 | 06-01 | 3 anomaly components: proveedor_sobrecostos_previos, proveedor_retrasos_previos, ausencia_proceso | SATISFIED | `calculator.py` lines 329-342; 0 for new providers confirmed in code and tests (test_proveedor_sobrecostos_previos_new_provider, test_proveedor_retrasos_previos_new_provider) |
| IRIC-04 | 06-02 | Bid kurtosis (curtosis_licitacion) per Imhof (2018) for processes with >=4 bids | SATISFIED | `bid_stats.py` lines 63-68: scipy_kurtosis(fisher=True, bias=False) for n>=4, NaN for n<4. 5+ test cases covering exactly this boundary. |
| IRIC-05 | 06-02 | Normalized relative difference (diferencia_relativa_norm) per Imhof (2018) for >=3 bids | SATISFIED | `bid_stats.py` lines 71-86: DRN=(sorted[1]-sorted[0])/sorted[0] for n>=3, NaN for n<3 or zero lowest. Formula documented in docstring. |
| IRIC-06 | 06-01 | IRIC total score = (1/11)*sum + dimension sub-scores | SATISFIED | `calculator.py` lines 363-426: iric_score/11, iric_competencia/6, iric_transparencia/2, iric_anomalias/3. None→0 via _val(). 5 dedicated score tests. |
| IRIC-07 | 06-01 | Calibrates IRIC thresholds at national level by contract type (percentiles P1/P5/P95/P99), outputting iric_thresholds.json | SATISFIED | `thresholds.py` calibrate_iric_thresholds() + save_iric_thresholds() writes JSON. Path is settings.iric_thresholds_path = artifacts_iric_dir / "iric_thresholds.json". |
| IRIC-08 | 06-01 | IRIC threshold calibration uses only training data | SATISFIED | `thresholds.py` line 81: function accepts arbitrary `df: pd.DataFrame`. No hardcoded dataset loading. SUMMARY and code comment explicitly document that Phase 7 must call with train-only data. build_iric() documents this in SUMMARY. |
| FEAT-04 | 06-03 | IRIC scores as Category D model input features: iric_score, iric_competencia, iric_transparencia, iric_anomalias | SATISFIED | `features/pipeline.py` FEATURE_COLUMNS includes 4 Cat D entries; both batch (build_features) and online (compute_features) paths compute and inject Cat D. test_feature_columns_count_34 passes. |

**All 9 requirements SATISFIED. No orphaned requirements.**

---

### Anti-Patterns Found

No anti-patterns detected. Searched all IRIC source files for:
- TODO/FIXME/HACK/PLACEHOLDER comments: None found
- Empty implementations (return null/return {}/return []): None found
- Console.log-only handlers: Not applicable (Python)
- Stub return values: None found

One notable design choice, NOT a bug: `build_features()` has a graceful NaN fallback for Category D when IRIC thresholds don't exist yet (lines 338-343), with an explicit warning log. This is correct behavior — build_features can run before build_iric. The thresholds are required at training time (Phase 7 enforces this via IRIC-08).

---

### Human Verification Required

None — all critical behaviors are verifiable programmatically for this phase:
- 11 binary components: logic verified by reading implementation + 80 tests
- Formula correctness (1/11 * sum): verified in code
- Threshold calibration structure: verified by reading implementation
- Parquet output: verified by artifact column list in pipeline.py
- CLI registration: verified in __main__.py

**No human verification items flagged.**

---

### Gaps Summary

No gaps. All 9 observable truths verified. All 9 requirements (IRIC-01 through IRIC-08, FEAT-04) satisfied with implementation evidence. All 8 required artifacts exist, are substantive (non-stub), and correctly wired. No anti-patterns detected.

**Phase 6 goal is fully achieved.**

Notable implementation quality observations:
- Components 9/10 correctly return 0 (not None) for new providers, matching VigIA semantics
- Components 1/6/8 correctly return None when procesos_data is None (captured by component 11)
- Lazy imports in features/pipeline.py prevent circular dependency with iric/pipeline.py
- Path-check before load_iric_thresholds() prevents stale module-level cache across tests
- bid_stats tests placed in test_bid_stats.py (not test_iric.py) due to parallel execution — correctly documented deviation
- FEATURE_COLUMNS has exactly 34 entries; kurtosis/DRN explicitly excluded with documented rationale (~60% NaN due to direct contracting)

---

_Verified: 2026-03-01_
_Verifier: Claude (gsd-verifier)_
