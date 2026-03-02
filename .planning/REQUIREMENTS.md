# Requirements: SIP — Intelligent Prediction System

**Defined:** 2026-02-27
**Core Value:** Given any Colombian public contract, reliably flag corruption risk using multiple evidence-backed signals — so oversight actors can prioritize where to investigate.

## v1 Requirements

Requirements for initial milestone. v1 "done" = trained models + RCAC built and validated, with evaluation reports and SHAP explainability. REST API is deferred to v1.x.

### Data Infrastructure

- [x] **DATA-01**: System can build RCAC from 6 core sources: Comptroller bulletins (`boletines.csv`), SIRI sanctions (`sanciones_SIRI_PACO.csv`), fiscal responsibilities (`responsabilidades_fiscales_PACO.csv`), SECOP fines (`multas_SECOP_PACO.csv`), SIC collusion (`colusiones_en_contratacion_SIC.csv`), criminal sanctions FGN (`sanciones_penales_FGN.csv`)
- [x] **DATA-02**: System normalizes document identifiers across all sources — tipo_documento to controlled catalog (CC, NIT, CE, PASAPORTE, OTRO), numero_documento to pure numeric string (strip dots, dashes, spaces, NIT check digits)
- [x] **DATA-03**: System deduplicates RCAC records by (tipo_documento, numero_documento), aggregating counts across sources and tracking `num_fuentes_distintas`
- [x] **DATA-04**: System handles SIRI file (`sanciones_SIRI_PACO.csv`) by positional column parsing (no headers — columns 5 and 6 for document type and number)
- [x] **DATA-05**: System handles `responsabilidades_fiscales_PACO.csv` combined "Tipo y Num Documento" field parsing
- [x] **DATA-06**: System processes CSV files up to 5.3 GB without memory crashes using chunked reading strategies
- [x] **DATA-07**: System loads all local SECOP CSV files with correct dtypes and column selection to minimize memory footprint
- [x] **DATA-08**: System serializes RCAC as indexed dict via joblib for fast loading
- [x] **DATA-09**: System provides O(1) RCAC lookup by (document_type, document_number)
- [x] **DATA-10**: System handles encoding differences across sources (UTF-8 for SECOP, Latin-1 for PACO files) without silent data corruption
- [x] **DATA-11**: System constructs labels for M1 (cost overruns) and M2 (delays) from amendments dataset (`adiciones.csv`): M1=1 if contract has ≥1 value amendment, M2=1 if contract has ≥1 time amendment
- [x] **DATA-12**: System constructs label for M3 from Comptroller bulletins: M3=1 if provider appears as fiscal liability holder
- [x] **DATA-13**: System constructs label for M4 from RCAC: M4=1 if provider has SECOP fine/sanction

### Feature Engineering

- [x] **FEAT-01**: System generates contract features (Category A): `valor_contrato`, `tipo_contrato_cat`, `modalidad_contratacion_cat`, `es_contratacion_directa`, `es_regimen_especial`, `es_servicios_profesionales`, `unspsc_categoria`, `departamento_cat`, `origen_recursos_cat`, `tiene_justificacion_modalidad`
- [x] **FEAT-02**: System generates temporal features (Category B): `dias_firma_a_inicio`, `duracion_contrato_dias`, `dias_publicidad`, `dias_decision`, `dias_proveedor_registrado`, `firma_posterior_a_inicio`, `mes_firma`, `trimestre_firma`, `dias_a_proxima_eleccion`
- [x] **FEAT-03**: System generates provider/competition features (Category C, excluding RCAC-derived): `tipo_persona_proveedor`, `num_contratos_previos`, `num_ofertas_recibidas`, `num_proponentes`, `proponente_unico`, `num_actividades_economicas`, `valor_total_contratos_previos`, `num_sobrecostos_previos`, `num_retrasos_previos`
- [ ] **FEAT-04**: System generates IRIC scores as model input features (Category D): `iric_score`, `iric_competencia`, `iric_transparencia`, `iric_anomalias`
- [x] **FEAT-05**: System enforces temporal leak guard — all provider history features and RCAC lookups use `as_of_date` = contract signing date to prevent future information leakage during training
- [x] **FEAT-06**: System precomputes Provider History Index offline (num_contratos_previos, valor_total_contratos_previos, num_sobrecostos_previos, num_retrasos_previos per provider at each point in time) serialized to `.pkl`
- [x] **FEAT-07**: Feature engineering pipeline (`pipeline.py`) uses identical code for both offline batch processing and future online per-contract inference — same transformations, same column ordering
- [x] **FEAT-08**: System excludes all post-execution variables from feature vectors: no execution start/end dates, no payment data, no actual quantities delivered
- [x] **FEAT-09**: RCAC-derived features (proveedor_en_rcac, proveedor_responsable_fiscal, etc.) are explicitly EXCLUDED from XGBoost model inputs — RCAC is for labels, background checks, and the API response only
- [x] **FEAT-10**: System groups low-frequency categorical values (< 0.1% of observations) into "Other" category to prevent sparse feature issues

### IRIC

- [ ] **IRIC-01**: System calculates 6 competition dimension components: `unico_proponente`, `proveedor_multiproposito`, `historial_proveedor_alto`, `contratacion_directa`, `regimen_especial`, `periodo_publicidad_extremo`
- [ ] **IRIC-02**: System calculates 2 transparency dimension components: `datos_faltantes`, `periodo_decision_extremo`
- [ ] **IRIC-03**: System calculates 3 anomaly dimension components: `proveedor_sobrecostos_previos`, `proveedor_retrasos_previos`, `ausencia_proceso`
- [x] **IRIC-04**: System calculates bid kurtosis (`curtosis_licitacion`) per Imhof (2018) formula for processes with ≥4 bids
- [x] **IRIC-05**: System calculates normalized relative difference (`diferencia_relativa_norm`) per Imhof (2018) for processes with ≥3 bids
- [ ] **IRIC-06**: System computes IRIC total score as (1/11) × Σ(11 components) ∈ [0,1], plus dimension sub-scores: `iric_competencia` = (1/6) × Σ(1-6), `iric_transparencia` = (1/2) × Σ(7-8), `iric_anomalias` = (1/3) × Σ(9-11)
- [ ] **IRIC-07**: System calibrates IRIC thresholds at national level by contract type (percentiles P1, P5, P95, P99 for relevant variables), outputting `iric_thresholds.json`
- [ ] **IRIC-08**: IRIC threshold calibration uses only training data (not full dataset) to prevent test-set leakage

### ML Models

- [ ] **MODL-01**: System trains M1 (cost overruns) XGBoost binary classifier using only pre-execution features
- [ ] **MODL-02**: System trains M2 (delays) XGBoost binary classifier using only pre-execution features
- [ ] **MODL-03**: System trains M3 (Comptroller records) XGBoost binary classifier using only pre-execution features
- [ ] **MODL-04**: System trains M4 (SECOP fines) XGBoost binary classifier using only pre-execution features
- [ ] **MODL-05**: System evaluates 2 class imbalance strategies per model: (1) XGBoost `scale_pos_weight` = n_neg/n_pos, (2) minority class upsampling to 25% target ratio — selects best based on cross-validation
- [ ] **MODL-06**: System performs hyperparameter optimization via RandomizedSearchCV with 200 iterations and StratifiedKFold(5) cross-validation
- [ ] **MODL-07**: System uses 70/30 train/test split with temporal ordering preserved
- [ ] **MODL-08**: System serializes trained models to `.pkl` via joblib with feature name ordering metadata
- [ ] **MODL-09**: System stores `feature_registry.json` alongside each model to guarantee correct feature column ordering between training and inference

### Evaluation

- [ ] **EVAL-01**: System reports AUC-ROC as primary metric for all 4 models
- [ ] **EVAL-02**: System reports MAP@100 and MAP@1000 for all models (critical for M3/M4 with severe imbalance)
- [ ] **EVAL-03**: System reports NDCG@k for ranking quality assessment
- [ ] **EVAL-04**: System reports Precision and Recall at multiple thresholds
- [ ] **EVAL-05**: System reports Brier Score for probability calibration assessment
- [ ] **EVAL-06**: System generates structured evaluation report (JSON + CSV) per model with all metrics, best hyperparameters, and class balance strategy used

### Explainability & Composite Index

- [ ] **EXPL-01**: System generates SHAP values via TreeExplainer for each prediction across all 4 models
- [ ] **EXPL-02**: System extracts top-N features by |SHAP value| per model per prediction
- [ ] **EXPL-03**: System computes CRI = Σ(wi × Pi) where Pi = P(Mi) for i=1..4 and P5 = IRIC score, with initial equal weights (wi = 0.20)
- [ ] **EXPL-04**: System categorizes CRI into risk levels: Very Low (0.00-0.20), Low (0.20-0.40), Medium (0.40-0.60), High (0.60-0.80), Very High (0.80-1.00)
- [ ] **EXPL-05**: CRI weights are configurable via `model_weights.json` without retraining models

### Project Foundation

- [x] **PROJ-01**: System uses Python 3.12 with verified compatibility for XGBoost, SHAP, and all ML dependencies
- [x] **PROJ-02**: System uses environment-based configuration (no hardcoded local paths in business logic) for future cloud deployment
- [ ] **PROJ-03**: System produces deterministic, serializable JSON reports for future IPFS anchoring compatibility
- [ ] **PROJ-04**: Unit tests for RCAC normalization, feature engineering, IRIC components, and model training/prediction

## v2 Requirements

Deferred to next milestone. Tracked but not in current roadmap.

### REST API

- **API-01**: POST /api/v1/analyze returns full JSON response (contract summary, CRI breakdown, IRIC detail, provider background, SHAP explanation, metadata)
- **API-02**: GET /api/v1/health returns system status (model version, RCAC date, SECOP API status)
- **API-03**: POST /api/v1/analyze/batch handles up to 1000 contract IDs
- **API-04**: API Key authentication (X-API-Key header) for access control
- **API-05**: CORS configuration for frontend consumption
- **API-06**: Pydantic v2 request/response schemas with validation

### Additional RCAC Sources

- **RCAC-01**: Monitor Ciudadano Excel data integrated into RCAC (4 files, 2016-2022)
- **RCAC-02**: organized_people_data.csv integrated into RCAC after schema analysis
- **RCAC-03**: Fiscalia data (actuaciones, indiciados, procesos) integrated into RCAC
- **RCAC-04**: Legal representative cross-referencing for shell company detection

### Enhancements

- **ENH-01**: Online inference pipeline (SECOP API → features → prediction → JSON in real-time)
- **ENH-02**: Provider History Index loaded at server startup for O(1) online lookup
- **ENH-03**: Socrata API client for SECOP II data download with pagination and rate limit handling (for data refresh and online queries)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Frontend / UI | Separate future phase; backend exposes REST API; FastAPI /docs as specification |
| Cloud deployment infrastructure | Architecture is cloud-ready but deployment (Docker, CI/CD, scaling) is not v1 |
| Real-time model retraining | v1 uses offline-trained models; scheduled retraining requires validation pipeline maturity |
| OAuth / user authentication | Not needed until frontend; API Key sufficient for v1.x |
| Mobile application | Web-first, mobile later; REST API is mobile-consumable |
| Entity-level aggregate risk scores | Unit of analysis is individual contract; aggregation conflates volume with risk |
| Binary "corrupt/not corrupt" output | Labels are proxies, not ground truth; output probability, not verdict |
| LLM-generated report narratives | Hallucination risk in corruption context is unacceptable; use SHAP + templates |
| SMOTE for class imbalance | Literature validates scale_pos_weight + upsampling for this domain; SMOTE is a deviation |
| Alternative ML algorithms | XGBoost is the academically established choice; switching breaks comparison baseline |
| Post-execution features in models | Early detection constraint is the core value; post-execution defeats the purpose |
| RCAC-derived features as XGBoost inputs | Design decision to exclude RCAC from model features to avoid potential circular leakage |
| IPFS + Ethereum report anchoring | Future vision (post-v2); architecture must not block it but integration deferred |
| Configurable CRI weights (empirical) | Requires trained models + investigation feedback; equal weights is the v1 baseline |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 3 | Complete |
| DATA-02 | Phase 3 | Complete |
| DATA-03 | Phase 3 | Complete |
| DATA-04 | Phase 3 | Complete |
| DATA-05 | Phase 3 | Complete |
| DATA-06 | Phase 2 | Complete |
| DATA-07 | Phase 2 | Complete |
| DATA-08 | Phase 3 | Complete |
| DATA-09 | Phase 3 | Complete |
| DATA-10 | Phase 2 | Complete |
| DATA-11 | Phase 4 | Pending |
| DATA-12 | Phase 4 | Complete |
| DATA-13 | Phase 4 | Complete |
| FEAT-01 | Phase 5 | Complete |
| FEAT-02 | Phase 5 | Complete |
| FEAT-03 | Phase 5 | Complete |
| FEAT-04 | Phase 6 | Pending |
| FEAT-05 | Phase 5 | Complete |
| FEAT-06 | Phase 5 | Complete |
| FEAT-07 | Phase 5 | Complete |
| FEAT-08 | Phase 5 | Complete |
| FEAT-09 | Phase 5 | Complete |
| FEAT-10 | Phase 5 | Complete |
| IRIC-01 | Phase 6 | Pending |
| IRIC-02 | Phase 6 | Pending |
| IRIC-03 | Phase 6 | Pending |
| IRIC-04 | Phase 6 | Complete |
| IRIC-05 | Phase 6 | Complete |
| IRIC-06 | Phase 6 | Pending |
| IRIC-07 | Phase 6 | Pending |
| IRIC-08 | Phase 6 | Pending |
| MODL-01 | Phase 7 | Pending |
| MODL-02 | Phase 7 | Pending |
| MODL-03 | Phase 7 | Pending |
| MODL-04 | Phase 7 | Pending |
| MODL-05 | Phase 7 | Pending |
| MODL-06 | Phase 7 | Pending |
| MODL-07 | Phase 7 | Pending |
| MODL-08 | Phase 7 | Pending |
| MODL-09 | Phase 7 | Pending |
| EVAL-01 | Phase 8 | Pending |
| EVAL-02 | Phase 8 | Pending |
| EVAL-03 | Phase 8 | Pending |
| EVAL-04 | Phase 8 | Pending |
| EVAL-05 | Phase 8 | Pending |
| EVAL-06 | Phase 8 | Pending |
| EXPL-01 | Phase 9 | Pending |
| EXPL-02 | Phase 9 | Pending |
| EXPL-03 | Phase 9 | Pending |
| EXPL-04 | Phase 9 | Pending |
| EXPL-05 | Phase 9 | Pending |
| PROJ-01 | Phase 1 | Complete |
| PROJ-02 | Phase 1 | Complete |
| PROJ-03 | Phase 9 | Pending |
| PROJ-04 | Phase 9 | Pending |

**Coverage:**
- v1 requirements: 53 total
- Mapped to phases: 53
- Unmapped: 0

---
*Requirements defined: 2026-02-27*
*Last updated: 2026-02-27 after roadmap creation — all 53 requirements mapped*
