# SIP — Intelligent Prediction System for Corruption in Public Procurement

## What This Is

A Python backend system that detects corruption risk in Colombian public procurement contracts. Given a SECOP II contract ID, SIP builds a Consolidated Corruption Background Registry (RCAC) from 7+ sanction sources, calculates an 11-component Contractual Irregularity Risk Index (IRIC), runs 4 pre-trained XGBoost models for different corruption indicators, and produces a Composite Risk Index (CRI) with feature-by-feature SHAP explanations. Built as an academic project with the explicit goal of becoming a practical tool for journalists, watchdog organizations, and government oversight agencies.

## Core Value

Given any Colombian public contract, reliably flag corruption risk using multiple evidence-backed signals — so oversight actors can prioritize where to investigate.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Build RCAC from 7+ sanction sources (Comptroller bulletins, SIRI sanctions, fiscal responsibilities, SECOP fines, SIC collusion, criminal sanctions FGN, organized people data, Monitor Ciudadano) with document normalization, deduplication, and legal representative cross-referencing
- [ ] RCAC lookup with O(1) access by (document_type, document_number)
- [ ] SECOP II data client (Socrata API) for bulk download and individual contract queries across 7 datasets
- [ ] Feature engineering pipeline producing 30+ features across 4 categories: contract variables (Category A), temporal/duration variables (Category B), provider variables (Category C), and IRIC-as-feature (Category D)
- [ ] IRIC calculation: 11 binary components across 3 dimensions (competition, transparency, anomalies) + 2 anomaly calculations (kurtosis, normalized relative difference), with national-level threshold calibration by contract type
- [ ] 4 XGBoost binary classification models: M1 (cost overruns), M2 (delays), M3 (Comptroller records), M4 (SECOP fines) — all using only pre-execution variables (early detection approach)
- [ ] Class imbalance handling: scale_pos_weight + up-sampling strategies, evaluated per model via stratified cross-validation
- [ ] Hyperparameter optimization: RandomizedSearchCV with 200 iterations, StratifiedKFold(5)
- [ ] Evaluation metrics: AUC-ROC (primary), MAP@100, MAP@1000, NDCG@k, Precision, Recall, Brier Score
- [ ] SHAP explainability: TreeSHAP values per prediction, top-N features with highest |SHAP value|
- [ ] Composite Risk Index (CRI): weighted average of P(M1) + P(M2) + P(M3) + P(M4) + IRIC, initial equal weights (1/5 each), configurable
- [ ] Feature pipeline shared between offline (batch training) and online (per-contract inference) — same code, different data source
- [ ] REST API (FastAPI): POST /analyze (individual), POST /analyze/batch, GET /health — complete JSON response with contract summary, CRI breakdown, IRIC detail, provider background, SHAP explanation, metadata
- [ ] Label construction from amendments dataset (cb9c-h8sn): M1 = has value amendment, M2 = has time amendment

### Out of Scope

- Frontend / UI — separate future phase, backend exposes REST API
- Cloud deployment infrastructure — architecture is cloud-ready but deployment is not v1
- Real-time model retraining — v1 uses offline-trained models with real-time inference
- OAuth / user authentication on the API — not needed until frontend
- Weight calibration for CRI — equal weights baseline, empirical calibration is future research
- Mobile application

## Context

### Academic Foundation

Based on three key academic works:
- **Gallego, Rivero & Martinez (2021)** — ML models for corruption detection in Colombian procurement. Established feature importance (contract value as top predictor), class imbalance strategies (scale_pos_weight of 25), and evaluation metrics (MAP@k, NDCG@k).
- **VigIA / Salazar, Perez & Gallego (2024)** — Extended the approach with IRIC (originally calibrated for Bogota), SHAP explainability, and the dual-role of IRIC as both descriptive statistic and model feature.
- **Mojica (2021)** — Additional hyperparameter tuning insights (136K combinations evaluated).

**Methodological advisor:** Jorge Gallego (IDB; co-author of VigIA and Gallego et al. 2021).

### Data Landscape

All data is available locally. Key datasets:

**SECOP II (explanatory variables) — in `secopDatabases/`:**
- `contratos_SECOP.csv` (341K contracts, 87 cols, 570 MB) — main table
- `procesos_SECOP.csv` (5.1M rows, 59 cols, 5.3 GB) — procurement processes
- `ofertas_proceso_SECOP.csv` (6.5M rows, 163 cols, 3.4 GB) — bids
- `proponentes_proceso_SECOP.csv` (3.3M rows, 9 cols, 841 MB) — bidders
- `proveedores_registrados.csv` (1.6M rows, 55 cols, 564 MB) — provider registry
- `ejecucion_contratos.csv` (4.2M rows, 16 cols, 682 MB) — execution data
- `adiciones.csv` (downloading) — amendments for M1/M2 labels
- `suspensiones_contratos.csv` (91 MB) — suspended contracts
- `boletines.csv` (10.8K rows, 1.3 MB) — Comptroller bulletins

**RCAC sources (corruption backgrounds) — in `Data/Propia/`:**
- `PACO/sanciones_SIRI_PACO.csv` (46.6K rows, 19 MB) — disciplinary/criminal sanctions (largest source, no headers — positional)
- `PACO/responsabilidades_fiscales_PACO.csv` (737 KB) — fiscal responsibilities
- `PACO/multas_SECOP_PACO.csv` (580 KB) — SECOP fines
- `PACO/colusiones_en_contratacion_SIC.csv` (44 KB) — SIC collusion cases
- `PACO/sanciones_penales_FGN.csv` (541 KB) — criminal sanctions from Attorney General
- `organized_people_data.csv` (12 MB) — people involved in corruption (PACO)
- `Monitor/base_de_datos_hechos/` — Monitor Ciudadano data (4 Excel files, 2016-2022)
- `DatosAbiertos/multas_sanciones.csv` (169 KB) — fines and sanctions
- `DatosAbiertos/actuaciones_fiscalia.csv`, `indiciados_fiscalia.csv`, `procesos_fiscalia.csv` — Fiscalia data

**Total data footprint:** ~12 GB across all sources.

### Existing Code

Greenfield — only utility scripts exist (`extract_boletines.py`, `flat_text_to_csv.py`). Python 3.12 venv initialized.

## Constraints

- **Language:** Python 3.12 — non-negotiable, entire ecosystem built around it
- **Algorithm:** XGBoost for all 4 models — established by academic literature, not open to alternatives
- **Early detection:** Only pre-execution variables as features — post-execution variables (execution dates, payments) are explicitly excluded
- **Unit of analysis:** Individual contract — not aggregate/entity-level
- **Data size:** ~12 GB of local CSVs — feature engineering must handle large datasets efficiently (chunked processing, memory management)
- **IRIC thresholds:** Must be calibrated at national level by contract type (not Bogota-only like VigIA)
- **SIRI file format:** `sanciones_SIRI_PACO.csv` has no headers — must be parsed by positional columns
- **Monitor Ciudadano:** Data is in Excel format (.xlsx) — requires conversion/parsing

## Future Vision

### IPFS + Ethereum (post-v1)

Each generated risk report will be uploaded to IPFS (InterPlanetary File System) for decentralized, immutable storage. The SHA hash/CID of each report will be anchored on the Ethereum blockchain as a permanent provenance record. This ensures that corruption risk assessments cannot be tampered with or suppressed after publication. Architecture decisions in v1 should not block this integration (e.g., reports should be serializable, deterministic where possible).

### Cloud Deployment (post-v1)

The system should be structured for eventual cloud deployment: environment-based configuration, no hardcoded local paths in business logic, containerization-friendly design (Docker). Actual cloud infrastructure, CI/CD, and scaling are out of scope for v1.

### Frontend (post-v1)

React/Next.js frontend consuming the REST API. Visualizations: CRI gauge, model breakdown charts, IRIC flag checklist, RCAC detail section, SHAP waterfall charts. The FastAPI OpenAPI docs at `/docs` serve as the canonical specification.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| XGBoost for all 4 models | Academic literature consensus (Gallego et al., VigIA, Mojica) — proven on this exact domain | — Pending |
| IRIC as both feature and output | Dual role established by VigIA — gives models expert-coded signal while also being interpretable to users | — Pending |
| Equal CRI weights (1/5 each) | Baseline — empirical calibration requires trained models and validation data | — Pending |
| Early detection only | Pre-execution variables only — enables flagging contracts before problems manifest | — Pending |
| All RCAC sources integrated | Maximize detection coverage — 7+ sources better than 4 | — Pending |
| v1 = Models + RCAC (no API) | Academic deliverable focuses on the ML pipeline; API is a fast follow | — Pending |
| Cloud-ready but not cloud-deployed | Design for portability without premature infrastructure investment | — Pending |
| IPFS + Ethereum as future step | Immutability/provenance for reports — architecture should not block this | — Pending |

---
*Last updated: 2026-02-27 after initialization*
