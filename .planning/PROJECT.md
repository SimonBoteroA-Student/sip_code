# SIP — Intelligent Prediction System for Corruption in Public Procurement

## What This Is

A Python offline ML pipeline that detects corruption risk in Colombian public procurement contracts. SIP builds a Consolidated Corruption Background Registry (RCAC) from 6 sanction sources, calculates an 11-component Contractual Irregularity Risk Index (IRIC), trains 4 XGBoost models for different corruption indicators (cost overruns, delays, Comptroller records, SECOP fines), and produces a Composite Risk Index (CRI) with feature-by-feature SHAP explanations. Shipped as v1.0 academic deliverable; REST API deferred to v2.

## Current State

**Version:** v1.1 shipped 2026-03-03
**Codebase:** 8,946 LOC source + 7,038 LOC tests (Python 3.12)
**Test suite:** 375 passed, 0 failures
**Tech stack:** XGBoost 3.2, SHAP 0.50, scikit-learn 1.8, pandas 3.0, Rich 13.9, psutil 6.0

## Core Value

Given any Colombian public contract, reliably flag corruption risk using multiple evidence-backed signals — so oversight actors can prioritize where to investigate.

## Requirements

### Validated (v1.0 & v1.1)

- ✓ RCAC from 6 sources with normalized document lookups and O(1) access — v1.0
- ✓ 14 chunked CSV loaders handling files up to 5.3 GB — v1.0
- ✓ M1–M4 binary labels from amendments, Comptroller bulletins, RCAC — v1.0
- ✓ 34-feature pipeline (Cat A/B/C/D) with temporal leak guard — v1.0
- ✓ IRIC: 11 components + kurtosis + DRN, nationally calibrated by contract type — v1.0
- ✓ 4 XGBoost classifiers with class imbalance selection + 200-iter HP search — v1.0
- ✓ Evaluation: AUC-ROC, MAP@k, NDCG@k, Precision/Recall, Brier Score — v1.0
- ✓ TreeSHAP explainability + CRI with configurable weights — v1.0
- ✓ Deterministic JSON output (IPFS-ready) — v1.0
- ✓ Shared batch/online feature pipeline (same code path) — v1.0
- ✓ Data leakage fix (duration from pre-amendment source, M2 labels from Dias adicionados) — v1.0
- ✓ Auto-hardware detection (OS/CPU/RAM/GPU) with container support — v1.1
- ✓ GPU benchmarking and auto-selection (CUDA→Metal→ROCm→CPU) — v1.1
- ✓ Interactive TUI config screen with live resource monitoring — v1.1
- ✓ GPU→CPU automatic fallback in training and CV scoring — v1.1
- ✓ Docker CPU and NVIDIA CUDA image support — v1.1
- ✓ Requests fallback for data downloads (curl-less systems) — v1.1
- ✓ UTF-8 console initialization and Windows compatibility — v1.1
- ✓ Safe atomic file operations and pure-Python line counting — v1.1
- ✓ Windows 10 CUDA detection and ThreadPoolExecutor timeout — v1.1
- ✓ GitHub Actions CI with Windows Server 2022 matrix — v1.1
- ✓ Windows 10 installation documentation and pathlib audit — v1.1

### Active (v2 candidates)

- [ ] REST API (FastAPI): POST /analyze, POST /analyze/batch, GET /health
- [ ] Socrata API client for SECOP II data download with pagination
- [ ] Additional RCAC sources: Monitor Ciudadano, organized_people_data, Fiscalia
- [ ] Legal representative cross-referencing for shell company detection
- [ ] Fix trainer IRIC threshold recalibration (pass raw tipo_contrato to calibrator)
- [ ] Fix trainer encoding mappings overwrite (rebuild from raw data, not encoded features)
- [ ] Per-contract-type model split (Es Pyme, Sector, Entidad Centralizada features)

### Out of Scope

- Frontend / UI — separate future phase; backend exposes REST API
- Cloud deployment infrastructure — architecture is cloud-ready but deployment is not v1
- Real-time model retraining — v1 uses offline-trained models
- OAuth / user authentication — not needed until frontend
- SMOTE for class imbalance — scale_pos_weight + upsampling validated for this domain
- Alternative ML algorithms — XGBoost is the academically established choice
- Post-execution features — early detection constraint is core value
- RCAC-derived features as XGBoost inputs — excluded to avoid circular leakage
- Mobile application

## Context

### Academic Foundation

Based on three key academic works:
- **Gallego, Rivero & Martinez (2021)** — ML models for corruption detection in Colombian procurement
- **VigIA / Salazar, Perez & Gallego (2024)** — Extended with IRIC, SHAP, dual IRIC role
- **Mojica (2021)** — Additional hyperparameter tuning insights

**Methodological advisor:** Jorge Gallego (IDB)

### Data Landscape

~12 GB local CSVs. Key datasets in `secopDatabases/` (contratos 570MB, procesos 5.3GB, ofertas 3.4GB, proponentes 841MB, proveedores 564MB, ejecucion 682MB, adiciones ~4GB) and `Data/Propia/PACO/` (5 RCAC sources).

## Constraints

- **Language:** Python 3.12
- **Algorithm:** XGBoost for all 4 models
- **Early detection:** Only pre-execution variables as features
- **Unit of analysis:** Individual contract
- **Data size:** ~12 GB — chunked processing required
- **IRIC thresholds:** National level by contract type

## Future Vision

- **IPFS + Ethereum** — immutable report storage with blockchain provenance anchoring
- **Cloud Deployment** — Docker, CI/CD, environment-based config (already cloud-ready)
- **Frontend** — React/Next.js consuming REST API with CRI gauge, SHAP waterfall charts

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| XGBoost for all 4 models | Academic literature consensus (Gallego et al., VigIA, Mojica) | ✓ Validated v1.0 |
| IRIC as both feature and output | Dual role from VigIA — expert-coded signal + interpretable output | ✓ Validated v1.0 |
| Equal CRI weights (1/5 each) | Baseline — empirical calibration requires investigation feedback | ✓ Shipped (tunable via model_weights.json) |
| Early detection only | Pre-execution variables — enables flagging before problems manifest | ✓ Validated v1.0 |
| RCAC features excluded from XGBoost | Avoid circular leakage — RCAC for labels/background checks only | ✓ Validated v1.0 |
| v1 = Models + RCAC (no API) | Academic deliverable focus; API is fast follow | ✓ Shipped v1.0 |
| Stratified random split (not temporal) | User decision — enables balanced class representation | ✓ Validated v1.0 |
| Duration from "Duración del contrato" text | Avoids post-amendment leakage from "Fecha de Fin" | ✓ Fixed v1.0 (Phase 10) |
| M2 labels from Dias adicionados OR EXTENSION | Union of both sources — 39K+ positives vs 19 from EXTENSION alone | ✓ Fixed v1.0 (Phase 10) |
| Cloud-ready but not cloud-deployed | Design for portability without premature infrastructure | ✓ Enabled v1.1 (Docker, CI/CD) |
| IPFS + Ethereum as future step | Immutability/provenance — architecture does not block this | — Pending |
| Centralized platform compat (compat.py) | No scattered if sys.platform guards — single source of truth | ✓ Shipped v1.1 |
| Slider chars resolved at widget creation | Avoid repeated detection checks at render time | ✓ Shipped v1.1 |
| ThreadPoolExecutor for Windows timeout | Cross-platform timeout without threading.Timer no-ops | ✓ Shipped v1.1 |
| Hardware auto-selection via GPU priority chain | CUDA→Metal→ROCm→CPU enables best-device detection | ✓ Shipped v1.1 |
| Docker non-root execution (sip:1000) | Security isolation and permission model compatibility | ✓ Shipped v1.1 |
| CI matrix fail-fast: false | Both OS jobs complete independently for parallel insights | ✓ Shipped v1.1 |
| No macOS in Windows-focused CI | Not requested, focuses effort on Windows validation | ✓ Shipped v1.1 |

---
*Last updated: 2026-03-03 after v1.1 milestone completion*
