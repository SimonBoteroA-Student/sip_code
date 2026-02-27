# Research Summary — SIP (Sistema Inteligente de Prediccion)

**Project:** ML-based corruption risk detection for Colombian public procurement (SECOP II)
**Synthesized:** 2026-02-27
**Research Files:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

---

## Executive Summary

SIP is a dual-pipeline ML system: an offline training pipeline that processes ~12 GB of Colombian procurement data to build sanction registries and train 4 XGBoost classifiers, and an online inference pipeline that exposes a FastAPI REST endpoint accepting a contract ID and returning a structured JSON risk report with a Composite Risk Index, IRIC red-flag checklist, provider background check, and SHAP feature explanations. The system is academically grounded in Gallego et al. (2021), VigIA/Salazar et al. (2024), and Mojica (2021), and is built for three user types — investigative journalists, watchdog organizations, and government oversight agencies — none of whom can run Python directly.

The recommended build approach is to sequence the work strictly by data dependencies: first establish robust data infrastructure (RCAC builder, chunked CSV loading, Socrata client, encoding standards), then build the shared feature engineering layer that is the critical parity boundary between training and inference, then train and evaluate models, then wrap the inference engine in a FastAPI application. The architecture's defining constraint is that the feature engineering code must be a single shared module used by both the offline training pipeline and the online inference endpoint — any divergence between these two code paths produces silently wrong predictions (training-serving skew), which is the most dangerous class of bug in this system.

The biggest risks are not algorithmic: they are data integrity risks. Temporal data leakage (provider history features computed without date cutoffs) can inflate AUC by 10-15 points and produce a model that looks excellent in validation but fails in production. RCAC document normalization failures silently eliminate 20-40% of sanction matches. IRIC threshold calibration on the full dataset (including the test set) inflates all downstream metrics. All three of these risks must be designed against from day one, not retrofitted. Python 3.14 wheel availability for XGBoost and SHAP is a secondary risk that can be mitigated by falling back to Python 3.12 with zero functional consequence.

---

## Key Findings

### From STACK.md

**Core technology decisions:**

| Technology | Rationale |
|------------|-----------|
| Python 3.14.3 (venv installed) / fallback Python 3.12 | 3.14 is live but XGBoost/SHAP wheel availability is UNVERIFIED — test before committing; 3.12 is universally safe |
| pandas 3.0.1 (installed) | Copy-on-Write semantics eliminates silent mutation bugs; chunked reads required for 5.3 GB files |
| numpy 2.4.2 (installed) | Required for IRIC kurtosis and normalized relative difference calculations |
| XGBoost >=2.0 | Mandated by academic literature; 2.x provides `tree_method="hist"` and improved imbalance handling |
| scikit-learn >=1.5 | `RandomizedSearchCV` + `StratifiedKFold` + metrics suite; XGBoost sklearn API requires >=1.0 |
| SHAP >=0.46 | TreeSHAP is the only correct explainability approach for XGBoost; exact, not approximate |
| FastAPI >=0.115 + Pydantic v2 | Async-first, auto OpenAPI docs, type-safe request/response schemas; strictly superior to Flask |
| joblib >=1.4 | Secure model serialization with compression; never use raw pickle |

**Critical version risk:** Python 3.14 wheel availability for XGBoost and SHAP is unverified. If wheels are not available, recreating the venv with Python 3.12 is the correct mitigation — no functional difference for this workload.

**Performance contingency:** If pandas chunked processing on `procesos_SECOP.csv` (5.3 GB) proves memory-constrained, Polars lazy API is the correct escalation path. Do not adopt Polars as primary in v1 — VigIA reference code is all pandas.

### From FEATURES.md

**Must-have (v1, P1):**
- RCAC registry from at least 4 confirmed sources with document normalization and O(1) lookup
- Temporal leak guard in RCAC lookup (as_of_date parameter from day one — cannot be retrofitted)
- IRIC calculation with national calibration by contract type (not Bogota-only)
- Provider History Index pre-computed offline (prevents unacceptable online latency)
- 4 trained XGBoost models (M1-M4) using only pre-execution features
- TreeSHAP explainability per model, top-N features
- CRI composite score + component breakdown
- REST API `POST /analyze` and `GET /health`
- Contract summary header and IRIC red flag checklist in API response

**Should-have (v1.x, P2 — add after core validated):**
- `POST /analyze/batch` endpoint
- Legal representative RCAC cross-reference
- API Key authentication (required before external partner access)
- Monitor Ciudadano RCAC integration
- Bid anomaly features (kurtosis, DRN) — NaN-heavy, verify data sufficiency first
- Election-cycle proximity feature (`dias_a_proxima_eleccion`)

**Explicitly deferred (v2+):**
- IPFS + Ethereum report anchoring (architecture must not block it — keep reports as plain serializable dicts)
- Frontend UI (FastAPI `/docs` serves as spec for v1)
- Cloud deployment
- Scheduled model retraining pipeline
- Entity-level aggregate risk scoring

**Anti-features to avoid:** Binary "corrupt/not-corrupt" labels (legal liability), LLM narrative generation (hallucination risk in investigative context), SMOTE (literature mandates scale_pos_weight + upsampling), entity-level aggregation in v1, OAuth in v1.

### From ARCHITECTURE.md

**Major components and responsibilities:**

| Component | Role | Critical Notes |
|-----------|------|----------------|
| `data_ingestion/` | Load all SECOP CSVs + RCAC sources; offline only | Chunked reads; per-file encoding constants; SIRI positional parser |
| `rcac/` | Build + query the sanction registry | Offline build → serialized dict → runtime O(1) lookup; shared between both pipelines |
| `features/` | Shared feature engineering (the critical parity boundary) | Zero dependency on `models/` or `secop_client/`; single source of truth for both pipelines |
| `models/` | Offline training only | 4x XGBoost + RandomizedSearchCV + evaluation metrics |
| `inference/` | Online prediction engine | Loads artifacts at startup; SHAP + CRI; does not import from `models/` |
| `secop_client/` | Live Socrata API queries | Isolated so data source is swappable without touching feature logic |
| `api/` | Thin FastAPI routing layer | Business logic lives in `inference/`; routes call engine methods |
| `artifacts/` | Hand-off point between offline and online | Offline writes; online reads at startup; becomes S3 path in cloud deployment |

**Key architecture patterns:**
1. **Shared Feature Transform (Train-Serve Parity)** — single `features/pipeline.py` imported by both training script and API handler; single-row dict (online) and full DataFrame (batch) use the same code path
2. **Registry-as-Artifact** — RCAC built offline, serialized, loaded once at API startup; O(1) lookup; never rebuilt per-request
3. **Lifespan-Loaded Model Cache** — FastAPI `lifespan` context manager loads all 4 models + RCAC + IRIC thresholds at startup; per-request inference touches only in-memory objects
4. **Chunked Batch Processing** — all files >500 MB must use `pd.read_csv(chunksize=50_000, usecols=REQUIRED_COLS)` from day one

**Build order enforced by dependency graph:** config/schemas → data ingestion → RCAC registry → feature engineering (IRIC calibration within this phase) → label construction → model training → inference engine → API. Feature engineering must be frozen before training begins — changing any feature definition after training invalidates all saved models.

### From PITFALLS.md

**Top 5 critical pitfalls (must be designed against from day one):**

| # | Pitfall | Prevention | Phase |
|---|---------|------------|-------|
| 1 | **Temporal leakage via provider history** — computing `num_contratos_previos` without date cutoff inflates AUC by 10-15 points and produces a model that fails in production | Implement `compute_provider_history_as_of(provider_id, cutoff_date)` with unit tests verifying no future dates appear in provider history | Phase 2 |
| 2 | **RCAC document normalization fails silently** — different formats across 7 sources (CC vs. C.C., NIT with/without check digit, SIRI positional columns, PACO fused fields) cause 20-40% silent match failures | Build normalization test suite with real examples before `rcac_builder.py`; compute and log match rate per source; fail loudly if any source has <5% match rate | Phase 1 |
| 3 | **IRIC thresholds calibrated on full dataset including test set** — percentile calibration on all data is a subtle form of leakage | Compute thresholds on training set only; apply to test set and production as-loaded | Phase 2 |
| 4 | **IRIC dual-role creates circular feature engineering** — IRIC components 9/10 (`proveedor_sobrecostos_previos`, `proveedor_retrasos_previos`) use the same `adiciones.csv` as M1/M2 labels | `compute_iric()` must accept and enforce `cutoff_date` parameter; test that IRIC components 9/10 return 0 for contracts without prior history | Phase 2 |
| 5 | **Memory crash on large CSVs** — `ofertas_proceso_SECOP.csv` (3.4 GB) + `procesos_SECOP.csv` (5.3 GB) exceed RAM when loaded naively | Chunked processing from first line of code; `usecols` + `dtype` optimization; pre-aggregate statistics per `ID Proceso` | Phase 1 |

**Additional high-priority pitfalls:**
- Class imbalance evaluated with wrong metrics: MAP@k as primary scorer for M3/M4, not AUC
- Socrata API incomplete downloads: authenticate + verify row count vs. `$count` endpoint
- CSV encoding inconsistency: SECOP = UTF-8, PACO = Latin-1, Excel = varied — define per-file encoding constants
- Monitor Ciudadano heterogeneous Excel schema: manual inspection required before parsing code
- SHAP on non-normalized features: log-transform all monetary features before training

---

## Implications for Roadmap

The dependency graph from ARCHITECTURE.md directly maps to phases. Each phase's outputs are the inputs for the next phase, and several correctness invariants (temporal cutoffs, feature schema, threshold calibration) must be established before the downstream phase begins. There is no parallelism between phases — the build order is strictly sequential.

### Suggested Phase Structure

**Phase 1 — Data Infrastructure (Foundation)**

Rationale: Every downstream component depends on reliable data loading and RCAC construction. RCAC normalization bugs and encoding issues must be caught here with tests, not discovered during model training. Chunked processing architecture must be established before any large-file joins are attempted.

Deliverables:
- Per-file encoding constants in `settings.py`; `normalize_text()` utility
- Chunked SECOP CSV loaders (`secop_loader.py`) with `usecols` + `dtype` optimization
- SIRI positional column parser with assertion tests
- Monitor Ciudadano Excel schema analysis and parser (all 4 files)
- RCAC builder for all available sources with document normalization and match-rate logging
- RCAC registry serialized to `artifacts/rcac_index.json`
- Socrata bulk downloader with authentication, exponential backoff, row-count verification
- `provider_history_index.pkl` pre-computed (offline parallel artifact to RCAC)
- Test suite: RCAC normalization round-trips; match rate >20% per source verified

Features from FEATURES.md addressed: RCAC registry (P1), Provider History Index (P1), temporal leak guard scaffolding
Pitfalls to avoid: #2 (RCAC normalization), #8 (memory crash), #11 (Socrata incomplete downloads), #12 (encoding), #13 (Monitor Excel schema), #9 (legal representative over-matching)

Research flag: NEEDS research — `organized_people_data.csv` and Monitor Ciudadano column structures require manual schema inspection. SIRI positional columns require ground-truth verification against known records.

---

**Phase 2 — Feature Engineering (The Parity Boundary)**

Rationale: This is the most critical phase architecturally. The shared feature module (`features/pipeline.py`) must be complete and correct before model training begins — changing it afterwards requires full retraining. IRIC threshold calibration must be done on training-set-only data. All temporal cutoffs must be enforced here.

Deliverables:
- `features/pipeline.py` — orchestrator accepting dict (online) or DataFrame row (offline)
- Category A (contract variables), B (temporal), C (provider/RCAC lookup), D (IRIC-as-feature)
- `features/iric/` — `calculator.py` with `cutoff_date` parameter enforced; `thresholds.py` calibrated on training-set-only contracts; `iric_thresholds.json` artifact
- `feature_schema.json` — pinned column order for XGBoost (position-sensitive)
- Log transformation for all monetary features (`log_valor_contrato`, etc.)
- Post-execution field exclusion list enforced in `process_features.py`
- Label constructor (`adiciones.csv` → M1/M2 binary; minimum execution-time filter applied)
- Unit tests: `compute_provider_history_as_of()` never includes future dates; IRIC components 9/10 return 0 before provider history exists; same feature vector produced for same contract input in both offline and online code paths

Features from FEATURES.md addressed: IRIC with national calibration (P1), shared feature pipeline (P1), temporal leak guard (P1), early detection constraint enforced
Pitfalls to avoid: #1 (temporal leakage), #3 (IRIC threshold leakage), #4 (IRIC dual-role), #6 (procesos_SECOP join leakage), #7 (unresolvable outcomes in training set), #15 (SHAP on non-normalized features)

Research flag: STANDARD PATTERNS — feature engineering for tabular XGBoost is well-documented. The domain-specific requirements (IRIC calibration, temporal cutoffs) are fully specified in FEATURES.md and PITFALLS.md.

---

**Phase 3 — Model Training and Evaluation**

Rationale: Can only begin after Phase 2 feature schema is frozen. Four models, each requiring class imbalance strategy selection evaluated via MAP@k (not just AUC). Temporal holdout must be reserved before any hyperparameter search begins.

Deliverables:
- Label construction for M3 (boletines.csv) and M4 (multas_SECOP_PACO.csv)
- Temporal train/test split (sort by `Fecha de Firma`; most recent 10-15% as holdout)
- Custom MAP@k sklearn scorer implemented before hyperparameter search
- 4x XGBoost `RandomizedSearchCV`: 200 iterations for M1/M2, 50-100 for M3/M4 (small positive class)
- Imbalance strategy comparison: `scale_pos_weight` vs. upsampling, evaluated on AUC + MAP@100 + Brier
- XGBoost early stopping to avoid overfitting on M3/M4 small positive classes
- Evaluation report: AUC-ROC, MAP@100, MAP@1000, NDCG@k, Brier Score; CV-to-holdout gap reported and flagged if >0.05
- 4x `.joblib` model artifacts + SHAP validation on a stratified sample
- Baseline model (majority class predictor) in evaluation report

Features from FEATURES.md addressed: 4 XGBoost models M1-M4 (P1), evaluation metrics (P1), class imbalance handling
Pitfalls to avoid: #5 (wrong class imbalance metrics), #7 (spurious negatives in training), #14 (hyperparameter search overfit on small positive class)

Research flag: NEEDS research — specific `scale_pos_weight` values for M3/M4 (Gallego et al. used 25 for M3; may differ for national vs. Bogota corpus). MAP@k implementation pattern for `RandomizedSearchCV` custom scorer.

---

**Phase 4 — Inference Engine and REST API**

Rationale: With trained model artifacts available, the inference engine assembles the full CRI pipeline (RCAC lookup + IRIC + 4x predict_proba + SHAP + CRI aggregation) and the API layer wraps it in HTTP routing. The Socrata client (online data source) is also built here.

Deliverables:
- `inference/engine.py` — loads all artifacts at startup; `analyze(contract_id) -> RiskReport`
- `inference/cri.py` — weighted average of M1-M4 probabilities + IRIC
- `inference/explainer.py` — TreeSHAP wrapper, top-N features per model
- `inference/schemas.py` — Pydantic v2 response models (full JSON risk report schema)
- `secop_client/` — Socrata wrapper for 7 datasets; async HTTP (`httpx`); retry + timeout
- `api/main.py` — FastAPI with lifespan model loading; `POST /analyze`; `GET /health`
- Integration test: submit contract known to have Comptroller background; verify `provider_background.in_rcac = true` in response
- Verification: same contract scores identically via offline feature pipeline and online API (parity test)

Features from FEATURES.md addressed: REST API `POST /analyze` + `GET /health` (P1), SHAP explainability (P1), CRI composite score + breakdown (P1), contract summary header (P1), RCAC flags in response (P1)
Pitfalls to avoid: training-serving skew (verified by parity test); lifespan model loading pattern

Research flag: STANDARD PATTERNS — FastAPI lifespan loading, Pydantic v2 schemas, and SHAP TreeExplainer usage are well-documented patterns.

---

**Phase 5 — Hardening and v1.x Features**

Rationale: After the core pipeline is validated end-to-end, add security, batch processing, and the remaining RCAC sources before any external partner access.

Deliverables:
- API Key authentication (`X-API-Key` header) — required before external access
- `POST /analyze/batch` endpoint (up to 1000 contracts; async processing)
- Legal representative RCAC cross-reference (document-ID-only matching; null if data missing)
- Monitor Ciudadano full integration into RCAC (once schema analysis from Phase 1 confirms CC/NIT coverage)
- Bid anomaly features (kurtosis, DRN) if `ofertas_proceso_SECOP.csv` has sufficient multi-bid processes
- Election-cycle proximity feature (`dias_a_proxima_eleccion`)
- CORS configuration (for future frontend)

Features from FEATURES.md addressed: all P2 features
Research flag: STANDARD PATTERNS

---

### Phase Summary

| Phase | Name | Key Output | Research Needed |
|-------|------|-----------|----------------|
| 1 | Data Infrastructure | RCAC artifact + Provider History Index | YES — schema inspection of SIRI, Monitor Ciudadano, organized_people_data |
| 2 | Feature Engineering | Shared feature pipeline (frozen schema) | NO — fully specified |
| 3 | Model Training | 4x trained .joblib models + evaluation report | YES — MAP@k scorer pattern, scale_pos_weight calibration |
| 4 | Inference Engine + API | Running FastAPI service | NO — standard patterns |
| 5 | Hardening + v1.x | Authenticated batch API | NO — standard patterns |

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Stack | MEDIUM-HIGH | pandas 3.0.1 + numpy 2.4.2 confirmed from live venv; XGBoost/SHAP/FastAPI versions from training knowledge, unverified against PyPI for Python 3.14. Python 3.12 fallback is HIGH confidence. |
| Features | HIGH | Three peer-reviewed academic works + VigIA codebase + complete SIP PRD. Feature list is fully specified and academically validated. |
| Architecture | HIGH | Standard MLOps dual-pipeline pattern (offline training + online inference); FastAPI lifespan loading is well-documented; artifact store boundaries are clear. |
| Pitfalls | HIGH | Grounded in academic literature + direct data file inspection + VigIA source analysis. Most pitfalls are domain-specific variants of known ML failure modes. |

**Overall: MEDIUM-HIGH.** The approach is well-validated by academic precedent and existing code (VigIA). The primary uncertainty is Python 3.14 package availability and the specific characteristics of edge cases in the local data files (SIRI column positions, PACO fused fields, Monitor Ciudadano schema heterogeneity).

---

## Gaps to Address During Planning

1. **Python 3.14 wheel availability:** Before committing to Phase 1 work, test `pip install xgboost shap` in the existing venv. If wheels are unavailable, recreate with `python3.12 -m venv .venv` immediately. This is a 30-minute check that eliminates the single highest-risk stack issue.

2. **adiciones.csv status:** PROJECT.md notes this file is "(downloading)." M1 and M2 labels cannot be constructed without it. Phase 3 is blocked until this file is available. Confirm download status before planning Phase 3 timeline.

3. **organized_people_data.csv schema:** Column structure and document identifier fields are unverified. Required before RCAC builder can incorporate this source. Manual inspection needed in Phase 1.

4. **Monitor Ciudadano CC/NIT coverage:** PITFALLS.md warns that >50% of Monitor events may lack CC/NIT identifiers, making the source of limited value for RCAC cross-referencing. Manual inspection in Phase 1 will determine whether this source contributes meaningfully or should be documented as low-coverage.

5. **SIRI positional column ground-truth:** The claim that column 4 = doc type and column 5 = doc number in `sanciones_SIRI_PACO.csv` requires verification against known sanctioned entities before the parser is built.

6. **Scale_pos_weight calibration for national corpus:** Gallego et al. used `scale_pos_weight=25` for M3 on a subset of Colombian data. The positive rate on the national 341K contract dataset may differ, requiring recalibration. This is a Phase 3 decision point.

---

## Sources (Aggregated)

**Academic literature:**
- Gallego, Rivero & Martínez (2021) — "Preventing Rather than Punishing: An Early Warning Model of Malfeasance in Public Procurement"
- Salazar, Pérez & Gallego (2024) — VigIA
- Mojica (2021) — hyperparameter tuning methodology
- Imhof (2018) — bid-rigging detection statistics (kurtosis, normalized relative difference)
- Fazekas & Kocsis (2020) — Registry of corruption risk indicators
- Baltrunaite et al. (2020) — competition suppression as collusion indicator

**Codebase and data:**
- `/Users/simonb/SIP Code/.venv/pyvenv.cfg` — Python 3.14.3 confirmed
- `/Users/simonb/SIP Code/data/Vigia/` — VigIA reference implementation (Python 3.7 notebooks)
- `/Users/simonb/SIP Code/.planning/PROJECT.md` — project constraints and requirements
- Local data files: SIRI, PACO sources, Monitor Ciudadano — inspected directly for schema validation

**Reference frameworks:**
- Chip Huyen, "Designing Machine Learning Systems" (O'Reilly 2022) — train-serve parity, artifact store patterns
- FastAPI documentation — lifespan context manager
- Socrata Open Data API / SECOP II documentation

---

*Synthesized from STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md*
*Research for: SIP — Sistema Inteligente de Prediccion de Corrupcion en Contratacion Publica Colombiana*
*Synthesized: 2026-02-27*
