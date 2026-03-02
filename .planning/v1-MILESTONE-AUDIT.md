---
milestone: v1
audited: 2026-03-02T22:55:00Z
status: tech_debt
scores:
  requirements: 53/53
  phases: 10/11
  integration: 47/47
  flows: 3/3
gaps:
  requirements: []
  integration:
    - id: "IRIC-08-partial"
      description: "Trainer IRIC threshold recalibration silently fails (KeyError on tipo_contrato in encoded features)"
      severity: "low"
      affected_requirements: ["IRIC-08"]
      evidence: "trainer.py:640 calibrate_iric_thresholds(X_train) raises KeyError caught by try/except at line 637-652"
    - id: "FEAT-07-encoding-overwrite"
      description: "Trainer encoding mappings rebuild overwrites correct string→int mappings with int→int mappings"
      severity: "medium"
      affected_requirements: ["FEAT-07", "FEAT-10"]
      evidence: "trainer.py:660 build_encoding_mappings(X_train, force=True) receives already-encoded int columns"
  flows: []
tech_debt:
  - phase: 07-model-training
    items:
      - "__main__.py line 214: 'not yet implemented' fallthrough for run-pipeline CLI (deferred to v2; train --build-features is equivalent)"
      - "Phase 7 VERIFICATION.md status is human_needed — code verified but production model artifacts require full pipeline execution against real SECOP data"
  - phase: 08-evaluation
    items:
      - "evaluator.py line 467: best_cv_scores key never populated — Markdown 'Cross-validation scores' section always empty (cosmetic)"
  - phase: 10-data-leakage-fix
    items:
      - "MISSING VERIFICATION.md — Phase 10 has 2 SUMMARY.md files and passing tests (351 total at completion) but was never formally verified via gsd-verifier"
      - "FEAT-02 and FEAT-08 marked 'Re-verification Pending' in REQUIREMENTS.md traceability table — functionally satisfied by code changes + 88 feature tests passing"
  - phase: cross-cutting
    items:
      - "REQUIREMENTS.md DATA-10 text says 'Latin-1 for PACO files' but all PACO files are actually UTF-8 — documentation inaccuracy"
      - "9 SUMMARY.md files lack requirements-completed frontmatter (DATA-11–13, EVAL-01–06 phases) — verified via VERIFICATION.md instead"
      - "Trainer IRIC threshold recalibration fails silently (see integration finding IRIC-08-partial)"
      - "Trainer encoding mappings overwrite degrades online inference after training (see integration finding FEAT-07-encoding-overwrite)"
closed_from_prior_audit:
  - "Phase 6 IRIC key mismatch bug (calculator.py components 9/10) — CLOSED by Phase 11"
  - "Phase 7 environment-sensitive test failures (test_models.py) — CLOSED by Phase 11"
  - "Data leakage from post-amendment Fecha de Fin and Valor del Contrato — CLOSED by Phase 10"
  - "M2 label bug (19 positives instead of ~39K) — CLOSED by Phase 10"
---

# v1 Milestone Audit Report (Post Gap-Closure)

**Milestone:** v1 — Trained Models + RCAC + Evaluation + Explainability
**Audited:** 2026-03-02T22:55:00Z
**Status:** ⚡ TECH DEBT — All 53 requirements satisfied at code level. No critical blockers. Accumulated tech debt needs review.
**Auditor:** Claude (gsd audit-milestone workflow)
**Supersedes:** Prior audit from 2026-03-02T17:50:00Z (9 phases, pre-gap-closure)

---

## Executive Summary

All 53 v1 requirements are satisfied across 11 completed phases (9 original + 2 gap-closure). Phases 10 and 11 successfully closed the 4 critical tech debt items identified in the prior audit: IRIC key mismatch, environment-sensitive test failures, data leakage, and M2 label bug. 375 tests pass with 0 failures. Two non-critical integration degradations found: trainer's IRIC threshold recalibration and encoding mappings rebuild both silently fail when operating on already-encoded features.parquet data. Phase 10 is missing its VERIFICATION.md (process gap, not code gap — all tests pass).

---

## 1. Phase Verification Summary

| Phase | Name | VERIFICATION.md | Status | Score | Requirements |
|-------|------|-----------------|--------|-------|-------------|
| 01 | Project Foundation | ✅ Present | passed | 4/4 | PROJ-01, PROJ-02 |
| 02 | Data Loaders | ✅ Present | passed | 4/4 | DATA-06, DATA-07, DATA-10 |
| 03 | RCAC Builder | ✅ Present | passed | 5/5 | DATA-01–05, DATA-08, DATA-09 |
| 04 | Label Construction | ✅ Present | passed | 5/5 | DATA-11, DATA-12, DATA-13 |
| 05 | Feature Engineering | ✅ Present | passed | 6/6 | FEAT-01–03, FEAT-05–10 |
| 06 | IRIC | ✅ Present | passed | 6/6 | IRIC-01–08, FEAT-04 |
| 07 | Model Training | ✅ Present | human_needed | 5/5 code | MODL-01–09 |
| 08 | Evaluation | ✅ Present | passed | 6/6 | EVAL-01–06 |
| 09 | Explainability, CRI, Testing | ✅ Present | passed | 11/11 | EXPL-01–05, PROJ-03, PROJ-04 |
| 10 | Data Leakage Fix | ⚠️ **MISSING** | unverified | — | FEAT-02*, FEAT-08* |
| 11 | Bug Fixes and Test Cleanup | ✅ Present | passed | 4/4 | IRIC-03* |

*Re-verification requirement from prior audit gap-closure.

**10/11 phases formally verified. Phase 10 functionally complete (351 tests at completion, 375 current) but lacks VERIFICATION.md.**

---

## 2. Gap Closure Report (Phases 10–11)

The prior audit (2026-03-02T17:50:00Z) identified 9 tech debt items across 5 categories. Phases 10 and 11 closed the 4 critical items:

| Prior Audit Item | Severity | Closed By | Evidence |
|-----------------|----------|-----------|----------|
| IRIC key mismatch (components 9/10 always 0) | ⚠️ Functional | Phase 11 | calculator.py:246,332,340 now use correct keys; 5 integration tests pass |
| Environment-sensitive test failures (2 tests) | ⚠️ Functional | Phase 11 | test_models.py patches artifacts_models_dir → tmp_path; 375/0/1 pass/fail/skip |
| Data leakage (Fecha de Fin post-amendment) | ⚠️ Functional | Phase 10 | _parse_duracion_contrato() uses "Duración del contrato"; 0 refs to Fecha de Fin in features |
| M2 label bug (19 positives only) | ⚠️ Functional | Phase 10 | label_builder.py augments M2 from "Dias adicionados" OR EXTENSION; 2 new tests |

**Remaining tech debt** (carried forward + newly discovered): 9 items — see Section 6.

---

## 3. Requirements Coverage (3-Source Cross-Reference)

### Source Legend
- **V** = VERIFICATION.md status (passed/gaps_found/missing)
- **S** = SUMMARY.md frontmatter requirements field (listed/missing)
- **R** = REQUIREMENTS.md traceability table (status)

### Data Infrastructure (13 requirements)

| REQ-ID | V | S | R | Final Status |
|--------|---|---|---|-------------|
| DATA-01 | passed | missing | Complete | ✅ satisfied |
| DATA-02 | passed | missing | Complete | ✅ satisfied |
| DATA-03 | passed | missing | Complete | ✅ satisfied |
| DATA-04 | passed | missing | Complete | ✅ satisfied |
| DATA-05 | passed | missing | Complete | ✅ satisfied |
| DATA-06 | passed | listed | Complete | ✅ satisfied |
| DATA-07 | passed | listed | Complete | ✅ satisfied |
| DATA-08 | passed | missing | Complete | ✅ satisfied |
| DATA-09 | passed | missing | Complete | ✅ satisfied |
| DATA-10 | passed | listed | Complete | ✅ satisfied |
| DATA-11 | passed | missing | Complete | ✅ satisfied |
| DATA-12 | passed | missing | Complete | ✅ satisfied |
| DATA-13 | passed | missing | Complete | ✅ satisfied |

### Feature Engineering (10 requirements)

| REQ-ID | V | S | R | Final Status |
|--------|---|---|---|-------------|
| FEAT-01 | passed | missing | Complete | ✅ satisfied |
| FEAT-02 | **missing** (Phase 10) | missing | Re-verification Pending | ✅ satisfied† |
| FEAT-03 | passed | missing | Complete | ✅ satisfied |
| FEAT-04 | passed | listed | Complete | ✅ satisfied |
| FEAT-05 | passed | missing | Complete | ✅ satisfied |
| FEAT-06 | passed | missing | Complete | ✅ satisfied |
| FEAT-07 | passed | missing | Complete | ✅ satisfied‡ |
| FEAT-08 | **missing** (Phase 10) | missing | Re-verification Pending | ✅ satisfied† |
| FEAT-09 | passed | missing | Complete | ✅ satisfied |
| FEAT-10 | passed | missing | Complete | ✅ satisfied‡ |

†FEAT-02/08: Phase 10 code changes verified by 88 feature tests (12 new duration tests). No formal VERIFICATION.md.
‡FEAT-07/10: Integration checker found encoding mappings overwrite issue (medium severity, online inference only).

### IRIC (8 requirements)

| REQ-ID | V | S | R | Final Status |
|--------|---|---|---|-------------|
| IRIC-01 | passed | missing | Complete | ✅ satisfied |
| IRIC-02 | passed | missing | Complete | ✅ satisfied |
| IRIC-03 | passed (Phase 11) | missing | Re-verification Pending | ✅ satisfied |
| IRIC-04 | passed | listed | Complete | ✅ satisfied |
| IRIC-05 | passed | listed | Complete | ✅ satisfied |
| IRIC-06 | passed | missing | Complete | ✅ satisfied |
| IRIC-07 | passed | missing | Complete | ✅ satisfied |
| IRIC-08 | passed | missing | Complete | ✅ satisfied‡ |

‡IRIC-08: Integration checker found trainer recalibration silently fails (low severity, thresholds remain from full-dataset calibration).

### ML Models (9 requirements)

| REQ-ID | V | S | R | Final Status |
|--------|---|---|---|-------------|
| MODL-01 | passed | missing | Complete | ✅ satisfied |
| MODL-02 | passed | missing | Complete | ✅ satisfied |
| MODL-03 | passed | missing | Complete | ✅ satisfied |
| MODL-04 | passed | missing | Complete | ✅ satisfied |
| MODL-05 | passed | missing | Complete | ✅ satisfied |
| MODL-06 | passed | missing | Complete | ✅ satisfied |
| MODL-07 | passed | missing | Complete | ✅ satisfied |
| MODL-08 | passed | missing | Complete | ✅ satisfied |
| MODL-09 | passed | missing | Complete | ✅ satisfied |

### Evaluation (6 requirements)

| REQ-ID | V | S | R | Final Status |
|--------|---|---|---|-------------|
| EVAL-01 | passed | missing | ✅ Complete | ✅ satisfied |
| EVAL-02 | passed | missing | ✅ Complete | ✅ satisfied |
| EVAL-03 | passed | missing | ✅ Complete | ✅ satisfied |
| EVAL-04 | passed | missing | ✅ Complete | ✅ satisfied |
| EVAL-05 | passed | missing | ✅ Complete | ✅ satisfied |
| EVAL-06 | passed | missing | ✅ Complete | ✅ satisfied |

### Explainability & Project (9 requirements)

| REQ-ID | V | S | R | Final Status |
|--------|---|---|---|-------------|
| EXPL-01 | passed | listed | Complete | ✅ satisfied |
| EXPL-02 | passed | missing | Complete | ✅ satisfied |
| EXPL-03 | passed | listed | Complete | ✅ satisfied |
| EXPL-04 | passed | listed | Complete | ✅ satisfied |
| EXPL-05 | passed | listed | Complete | ✅ satisfied |
| PROJ-01 | passed | missing | Complete | ✅ satisfied |
| PROJ-02 | passed | missing | Complete | ✅ satisfied |
| PROJ-03 | passed | listed | Complete | ✅ satisfied |
| PROJ-04 | passed | listed | Complete | ✅ satisfied |

### Coverage Summary

- **53/53 requirements satisfied** (100%)
- **0 unsatisfied** requirements
- **0 orphaned** requirements
- **2 requirements** lack VERIFICATION.md source (FEAT-02, FEAT-08) — verified by tests + code inspection
- **3 requirements** with integration degradation notes (FEAT-07, FEAT-10, IRIC-08) — non-critical

---

## 4. Cross-Phase Integration

**Integration checker report: 47 connected / 0 broken / 2 degraded / 1 orphaned**

| Connection | From → To | Status | Notes |
|-----------|-----------|--------|-------|
| Config propagation | Phase 1 → All | ✅ | get_settings() imported everywhere |
| Loaders → RCAC | Phase 2 → Phase 3 | ✅ | 5 PACO loaders |
| Loaders → Labels | Phase 2 → Phase 4 | ✅ | contratos + adiciones + boletines |
| Loaders → Features | Phase 2 → Phase 5 | ✅ | contratos + procesos + proveedores |
| Loaders → IRIC | Phase 2 → Phase 6 | ✅ | ofertas + procesos + contratos |
| RCAC → Labels | Phase 3 → Phase 4 | ✅ | rcac_lookup() for M4 |
| Labels → Features | Phase 4 → Phase 5 | ✅ | labels.parquet for provider history |
| Features → IRIC | Phase 5 → Phase 6 | ✅ | FEATURE_COLUMNS 30→34, provider history |
| Features → Training | Phase 5 → Phase 7 | ✅ | features.parquet + FEATURE_COLUMNS |
| IRIC → Training | Phase 6 → Phase 7 | ✅ | 4 Cat D features |
| Training → Evaluation | Phase 7 → Phase 8 | ✅ | model.pkl + test_data.parquet |
| Training → Explainability | Phase 7 → Phase 9 | ✅ | model.pkl for SHAP |
| Features → Inference | Phase 5 → Phase 9 | ✅ | compute_features() |
| IRIC → CRI | Phase 6 → Phase 9 | ✅ | iric_score as 5th CRI component |
| Phase 10 schemas → Features | Phase 10 → Phase 5 | ✅ | Duración del contrato, Dias adicionados |
| Phase 11 keys → IRIC | Phase 11 → Phase 6 | ✅ | 3 corrected provider_history keys |

### Degraded Connections

1. **Trainer → IRIC recalibration** (LOW): `calibrate_iric_thresholds(X_train)` fails with KeyError on `tipo_contrato` (encoded to `tipo_contrato_cat` in features.parquet). Caught by try/except. Thresholds remain from full-dataset calibration. Affects online inference precision only.

2. **Trainer → Encoding mappings** (MEDIUM): `build_encoding_mappings(X_train, force=True)` receives already-encoded int columns, producing int→int mappings. Overwrites correct string→int mappings. Affects `compute_features()` online inference path after training. Mitigated by re-running `build-features`.

### Orphaned

- `run-pipeline` CLI command registered but not implemented (has `train --build-features` equivalent)

---

## 5. End-to-End Flows

| Flow | Steps | Status |
|------|-------|--------|
| Batch CLI Pipeline | build-rcac → build-labels → build-features → build-iric → train → evaluate | ✅ Complete |
| Online Inference | analyze_contract → compute_features → predict_proba → SHAP → CRI → JSON | ✅ Complete* |
| V1/V2 Comparison | backup-v1 → (re-pipeline) → compare-v1v2 | ✅ Complete |

*Online inference has encoding degradation after trainer runs (see Section 4). Mitigated by re-running build-features.

**Flows score: 3/3**

---

## 6. Test Suite Health

| Metric | Value |
|--------|-------|
| Total tests | 376 |
| Passing | 375 |
| Failing | 0 |
| Skipped | 1 |
| Duration | 25.74s |

**Skipped:** `test_full_pipeline_real_data` — requires `--real-data` flag (by design)

---

## 7. Tech Debt Summary

### Phase 7: Model Training
- `__main__.py` line 214: `run-pipeline` "not yet implemented" fallthrough (deferred to v2; `train --build-features` is equivalent)
- VERIFICATION.md status `human_needed` — code verified but production artifacts require full pipeline execution

### Phase 8: Evaluation
- `evaluator.py` line 467: `best_cv_scores` key never populated — cosmetic only

### Phase 10: Data Leakage Fix
- **Missing VERIFICATION.md** — phase functionally complete (2 plans, 2 summaries, 351 tests at completion), but never formally verified
- FEAT-02 and FEAT-08 still marked "Re-verification Pending" in REQUIREMENTS.md traceability table

### Cross-Cutting
- REQUIREMENTS.md DATA-10 text says "Latin-1 for PACO files" — should say UTF-8
- 9 SUMMARY.md files lack `requirements-completed` frontmatter
- **Trainer IRIC threshold recalibration silently fails** — thresholds remain from full-dataset calibration (IRIC-08 partial, low severity)
- **Trainer encoding mappings overwrite** — degrades online inference after training until `build-features` re-runs (FEAT-07/10 partial, medium severity)

### Total: 9 items (2 functional/medium, 7 cosmetic/documentation)

---

## 8. Scores

| Dimension | Score | Notes |
|-----------|-------|-------|
| Requirements | 53/53 | All satisfied (2 via code inspection due to missing Phase 10 VERIFICATION.md) |
| Phases | 10/11 verified | Phase 10 functionally complete but missing VERIFICATION.md |
| Integration | 47/47 connected | 2 degraded connections (non-fatal), 1 orphaned CLI command |
| Flows | 3/3 | Batch + online inference + v1/v2 comparison all complete |

---

_Audited: 2026-03-02T22:55:00Z_
_Auditor: Claude (gsd audit-milestone)_
_Supersedes: v1-MILESTONE-AUDIT.md from 2026-03-02T17:50:00Z_
