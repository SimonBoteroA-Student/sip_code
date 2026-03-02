# Phase 9: Explainability, CRI, and Testing - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Generate SHAP explanations per prediction for all 4 models, compute a Composite Risk Index (CRI) aggregating model probabilities + IRIC into a single configurable score, expose a deterministic per-contract analysis function for future API/IPFS use, and consolidate test coverage with a master system test. This phase does NOT add new features, APIs, or data sources.

</domain>

<decisions>
## Implementation Decisions

### SHAP Output Shape
- Extract **top-10 features** per model per prediction (by absolute SHAP value)
- Store SHAP results in a **batch Parquet artifact** (per-contract rows, one file per model run)
- Only top-10 SHAP values stored per contract per model (not full feature matrix)
- Each SHAP entry contains: **feature name + SHAP value + direction (positive/negative) + original feature value**
  - Example: `{"feature": "num_contratos_previos", "shap_value": 0.12, "direction": "risk_increasing", "original_value": 47}`

### CRI Presentation & Thresholds
- Risk level boundaries are **configurable** (not hardcoded)
- Thresholds added to **existing `model_weights.json`** — centralizes all CRI configuration
- Default thresholds: 0.20 intervals (Very Low: [0.00, 0.20), Low: [0.20, 0.40), Medium: [0.40, 0.60), High: [0.60, 0.80), Very High: [0.80, 1.00])
- Boundary convention: **inclusive lower, exclusive upper** — except Very High which includes 1.00
- CRI output includes **full breakdown**: CRI score + risk level + per-model probabilities (P(M1), P(M2), P(M3), P(M4), IRIC) + per-model SHAP top-10 summaries

### JSON Report Structure
- JSON report is an **inference-time capability**, NOT a training artifact
- Output is **per contract** — a Python function takes a contract and returns a structured dict
- Exposed as a **core Python function** returning a dict (callers serialize to JSON) — designed for future REST API (v2) reuse
- Schema includes: contract ID, CRI block (score, level, weights used), per-model block (probability, top-10 SHAP entries), IRIC score, **raw feature values used for prediction**, metadata (timestamp, model versions)
- Determinism via **sorted dict keys + consistent float rounding to 6 decimal places** — sufficient for IPFS hashing
- No CLI subcommand for JSON in this phase — function-level API only

### Test Coverage Scope
- **Audit existing 326 tests** and fill gaps for PROJ-04 requirements (RCAC round-trips, feature engineering, IRIC components, predict_proba)
- **Unit tests for all new Phase 9 code**: SHAP extraction, CRI computation, JSON determinism
- **Master system test** (`test_system.py`): single consolidated end-to-end test exercising the full pipeline (data → features → IRIC → model → SHAP → CRI → JSON)
- System test is **dual-mode, configurable by CLI flag**: fixture-based (fast, synthetic data, CI-friendly) OR real-data mode (runs against actual `data/` files)
- Existing per-stage tests remain untouched — master test complements them

### Claude's Discretion
- SHAP Parquet file naming and directory structure within `artifacts/`
- Internal architecture of the analysis function (class vs function, module placement)
- Specific synthetic fixture data design for system tests
- How to expose the fixture/real-data flag in the CLI test runner

</decisions>

<specifics>
## Specific Ideas

- The analysis function should be the single entry point that a future v2 REST API (`POST /api/v1/analyze`) would call — design the interface with that in mind
- Master system test should reuse existing test helper functions where possible, not duplicate test logic

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-explainability-cri-and-testing*
*Context gathered: 2026-03-02*
