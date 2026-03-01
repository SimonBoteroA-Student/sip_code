# Roadmap: SIP — Intelligent Prediction System for Corruption in Public Procurement

## Overview

SIP is built as a strictly sequential offline pipeline: a working Python environment unlocks data loading, which unlocks RCAC construction, which unlocks label construction, which unlocks feature engineering, which unlocks IRIC calibration, which unlocks model training, which unlocks evaluation, which unlocks SHAP explainability and the Composite Risk Index. Each phase completes one verifiable capability before the next begins. The result is 4 trained XGBoost models with a validated RCAC, full evaluation metrics, SHAP explanations, and a Composite Risk Index — the complete academic deliverable for v1.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Project Foundation** - Python 3.12 environment verified, project scaffold and config system in place (completed 2026-03-01)
- [x] **Phase 2: Data Loaders** - Chunked CSV loading for all large SECOP files, correct dtypes/encoding, memory-efficient processing (completed 2026-03-01)
- [x] **Phase 3: RCAC Builder** - 6-source sanction registry built, normalized, deduplicated, serialized, and queryable (completed 2026-03-01)
- [ ] **Phase 4: Label Construction** - M1/M2 labels from amendments, M3 from Comptroller bulletins, M4 from RCAC fines
- [ ] **Phase 5: Feature Engineering** - Shared feature pipeline (Categories A/B/C) with temporal leak guard and train-serve parity
- [ ] **Phase 6: IRIC** - 11-component irregularity index calculated, nationally calibrated by contract type, added as model feature
- [ ] **Phase 7: Model Training** - 4 XGBoost classifiers trained with class imbalance handling and hyperparameter optimization
- [ ] **Phase 8: Evaluation** - Full metrics suite (AUC-ROC, MAP@k, NDCG@k, Brier, Precision/Recall) with structured evaluation reports
- [ ] **Phase 9: Explainability, CRI, and Testing** - SHAP values, Composite Risk Index, deterministic JSON output, and full test suite

## Phase Details

### Phase 1: Project Foundation
**Goal**: Python 3.12 environment with XGBoost and SHAP confirmed working, project directory scaffold created, and all configuration (paths, API endpoints, encoding constants) centralized in `config/settings.py`
**Depends on**: Nothing (first phase)
**Requirements**: PROJ-01, PROJ-02
**Success Criteria** (what must be TRUE):
  1. `import xgboost; import shap` succeeds in the project venv without errors
  2. `config/settings.py` exists with all file paths, API URLs, and encoding constants — no hardcoded paths anywhere in business logic
  3. `config/model_weights.json` exists with equal CRI weights (0.20 each) ready to be loaded at runtime
  4. Running the project from any working directory produces the same paths (environment-variable-based resolution)
**Plans:** 2/2 plans complete
Plans:
- [ ] 01-01-PLAN.md — Python 3.12 environment setup, project scaffold, dependency verification
- [ ] 01-02-PLAN.md — Centralized configuration system (settings.py, model_weights.json, requirements.lock)

### Phase 2: Data Loaders
**Goal**: All local SECOP and RCAC CSV files can be read without memory crashes, with correct encoding and dtypes
**Depends on**: Phase 1
**Requirements**: DATA-06, DATA-07, DATA-10
**Success Criteria** (what must be TRUE):
  1. `procesos_SECOP.csv` (5.3 GB) and `ofertas_proceso_SECOP.csv` (3.4 GB) load completely using chunked iteration without exceeding available RAM
  2. All local CSV files load with correct dtypes and column selection (`usecols`, `dtype` arguments) to minimize memory footprint
  3. Each CSV file is read with its correct encoding (UTF-8 for all files — PACO files verified UTF-8 per research) — no mojibake or silent data corruption in string fields
  4. Loader functions are reusable across all data processing stages (RCAC building, feature engineering, label construction)
**Plans:** 2/2 plans complete
Plans:
- [ ] 02-01-PLAN.md — Column schemas, Settings encoding fix, test scaffold
- [ ] 02-02-PLAN.md — All 14 loader generator functions with tqdm, logging, and encoding handling

### Phase 3: RCAC Builder
**Goal**: A validated Consolidated Corruption Background Registry (RCAC) built from 6 sanction sources, serialized to `artifacts/rcac.pkl`, providing O(1) lookup by (document_type, document_number)
**Depends on**: Phase 2
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-08, DATA-09
**Success Criteria** (what must be TRUE):
  1. RCAC contains records from all 6 sources: Comptroller bulletins, SIRI sanctions, fiscal responsibilities, SECOP fines, SIC collusion, and criminal sanctions FGN
  2. Every record has a normalized `tipo_documento` (CC/NIT/CE/PASAPORTE/OTRO) and a `numero_documento` consisting only of digits with no dots, dashes, spaces, or NIT check digits
  3. SIRI file is parsed by positional columns 5 and 6 (no headers); `responsabilidades_fiscales_PACO.csv` combined "Tipo y Num Documento" field is correctly split
  4. Records from multiple sources for the same person are deduplicated into a single entry with `num_fuentes_distintas` correctly counted
  5. `rcac_lookup.py` returns a record in O(1) time for any (document_type, document_number) key, returning `None` for unknown identifiers
**Plans:** 2/2 plans complete
Plans:
- [x] 03-01-PLAN.md — RCAC normalization engine and builder (TDD: normalization, dedup, serialization)
- [x] 03-02-PLAN.md — RCAC lookup interface, CLI wiring, and package exports

### Phase 4: Label Construction
**Goal**: Binary target labels for all 4 models exist as correctly constructed columns on the training dataset, using only the correct source for each label
**Depends on**: Phase 3
**Requirements**: DATA-11, DATA-12, DATA-13
**Success Criteria** (what must be TRUE):
  1. M1 label equals 1 for any contract in `adiciones.csv` with at least one value amendment, 0 otherwise
  2. M2 label equals 1 for any contract in `adiciones.csv` with at least one time amendment, 0 otherwise
  3. M3 label equals 1 for any contract whose provider appears as a fiscal liability holder in Comptroller bulletins
  4. M4 label equals 1 for any contract whose provider has a SECOP fine or sanction in the RCAC — with no label leakage from future records (label uses provider document from RCAC built in Phase 3)
**Plans**: TBD

### Phase 5: Feature Engineering
**Goal**: A shared feature pipeline (`features/pipeline.py`) produces a complete, correctly ordered feature vector for any contract, enforcing temporal leak prevention and excluding all post-execution variables and RCAC-derived inputs
**Depends on**: Phase 4
**Requirements**: FEAT-01, FEAT-02, FEAT-03, FEAT-05, FEAT-06, FEAT-07, FEAT-08, FEAT-09, FEAT-10
**Success Criteria** (what must be TRUE):
  1. `pipeline.py` produces identical feature vectors for the same contract input regardless of whether it is called from the offline batch path or the online inference path
  2. Provider history features (`num_contratos_previos`, `valor_total_contratos_previos`, `num_sobrecostos_previos`, `num_retrasos_previos`) are computed as-of the contract signing date — no future contracts appear in any provider's history
  3. The Provider History Index is serialized offline to `.pkl` and loaded for batch processing without recomputation per contract
  4. All post-execution variables (execution start/end dates, payment data) are absent from the feature vector
  5. RCAC-derived features (`proveedor_en_rcac`, `proveedor_responsable_fiscal`, etc.) are explicitly excluded from the XGBoost feature vector
  6. Categorical values representing less than 0.1% of observations are grouped into "Other" before encoding
**Plans**: TBD

### Phase 6: IRIC
**Goal**: The Contractual Irregularity Risk Index (IRIC) calculates all 11 binary components plus kurtosis and normalized relative difference anomaly measures, calibrated at national level by contract type using training data only, and outputs `iric_thresholds.json`
**Depends on**: Phase 5
**Requirements**: IRIC-01, IRIC-02, IRIC-03, IRIC-04, IRIC-05, IRIC-06, IRIC-07, IRIC-08, FEAT-04
**Success Criteria** (what must be TRUE):
  1. All 11 binary components fire correctly: 6 competition components, 2 transparency components, and 3 anomaly components each produce the expected value on known test cases
  2. Kurtosis (`curtosis_licitacion`) is calculated per the Imhof (2018) formula for processes with at least 4 bids; processes with fewer bids receive NaN
  3. Normalized relative difference (`diferencia_relativa_norm`) is calculated per Imhof (2018) for processes with at least 3 bids
  4. `iric_thresholds.json` contains national-level percentiles (P1, P5, P95, P99) segmented by contract type, computed only from training-set contracts
  5. IRIC scores (`iric_score`, `iric_competencia`, `iric_transparencia`, `iric_anomalias`) are present as Category D features in the feature vector produced by `pipeline.py`
  6. IRIC anomaly components 9 and 10 (`proveedor_sobrecostos_previos`, `proveedor_retrasos_previos`) return 0 for providers with no contract history before the signing date
**Plans**: TBD

### Phase 7: Model Training
**Goal**: 4 XGBoost binary classifiers (M1 cost overruns, M2 delays, M3 Comptroller records, M4 SECOP fines) are trained on pre-execution features only, with class imbalance strategy selected per model and hyperparameters optimized via random search, producing serialized `.pkl` artifacts
**Depends on**: Phase 6
**Requirements**: MODL-01, MODL-02, MODL-03, MODL-04, MODL-05, MODL-06, MODL-07, MODL-08, MODL-09
**Success Criteria** (what must be TRUE):
  1. Training data is split with temporal ordering preserved (earliest 70% as train, latest 30% as test holdout) — no shuffling before the split
  2. For each of the 4 models, both class imbalance strategies (scale_pos_weight and 25% minority upsampling) are evaluated via stratified cross-validation, and the better strategy is selected and documented
  3. RandomizedSearchCV with 200 iterations and StratifiedKFold(5) completes for each model without errors
  4. Four serialized model files exist at `artifacts/models/M1.pkl`, `M2.pkl`, `M3.pkl`, `M4.pkl`
  5. A `feature_registry.json` is stored alongside each model containing the exact column names and ordering used during training
**Plans**: TBD

### Phase 8: Evaluation
**Goal**: All 4 models are comprehensively evaluated with the full academic metrics suite, and structured evaluation reports (JSON + CSV) are generated per model documenting performance, class balance strategy, and best hyperparameters
**Depends on**: Phase 7
**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05, EVAL-06
**Success Criteria** (what must be TRUE):
  1. AUC-ROC is reported for all 4 models on the held-out test set
  2. MAP@100 and MAP@1000 are computed for all 4 models (using the ranking-based scorer, not accuracy)
  3. NDCG@k is computed at at least 2 values of k for all 4 models
  4. Precision and Recall are reported at multiple decision thresholds (e.g., 0.3, 0.5, 0.7) for each model
  5. Brier Score is reported for each model as a calibration quality indicator
  6. A structured evaluation report file exists per model (`artifacts/evaluation/M1_eval.json` etc.) containing all metrics, the selected class balance strategy, and best hyperparameters from random search
**Plans**: TBD

### Phase 9: Explainability, CRI, and Testing
**Goal**: SHAP values are generated per prediction for all 4 models, the Composite Risk Index aggregates them into a single configurable score, the full pipeline produces deterministic serializable JSON output, and the codebase has unit tests covering RCAC normalization, feature engineering, IRIC components, and model prediction
**Depends on**: Phase 8
**Requirements**: EXPL-01, EXPL-02, EXPL-03, EXPL-04, EXPL-05, PROJ-03, PROJ-04
**Success Criteria** (what must be TRUE):
  1. TreeSHAP values are generated for a given contract across all 4 models, and the top-N features by absolute SHAP value are extractable per model
  2. CRI is computed as a weighted average of P(M1) + P(M2) + P(M3) + P(M4) + IRIC using weights from `model_weights.json` — modifying weights in that file changes CRI output without retraining
  3. Every CRI score is classified into exactly one of the 5 risk levels (Very Low / Low / Medium / High / Very High) based on the 0.20-interval thresholds
  4. Given the same contract input, the full pipeline produces byte-identical JSON output on repeated runs (deterministic)
  5. Unit tests pass for: RCAC document normalization round-trips, provider history as-of-date (no future dates), at least 4 IRIC component flags, and model predict_proba returning values in [0,1]

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Project Foundation | 2/2 | Complete   | 2026-03-01 |
| 2. Data Loaders | 2/2 | Complete   | 2026-03-01 |
| 3. RCAC Builder | 2/2 | Complete | 2026-03-01 |
| 4. Label Construction | 0/TBD | Not started | - |
| 5. Feature Engineering | 0/TBD | Not started | - |
| 6. IRIC | 0/TBD | Not started | - |
| 7. Model Training | 0/TBD | Not started | - |
| 8. Evaluation | 0/TBD | Not started | - |
| 9. Explainability, CRI, and Testing | 0/TBD | Not started | - |
