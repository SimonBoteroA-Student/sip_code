# Feature Research

**Domain:** Corruption Detection / Public Procurement Risk Analysis (Colombian SECOP II)
**Researched:** 2026-02-27
**Confidence:** HIGH — grounded in three peer-reviewed academic works (Gallego et al. 2021, VigIA/Salazar et al. 2024, Mojica 2021), the existing VigIA codebase, and the fully-specified SIP PRD.

---

## Context: Who Uses This System

SIP's outputs are consumed by three distinct actor types with different mental models:

- **Journalists / investigative reporters** — want a single, shareable risk score and a plain-language narrative of WHY. They do not read feature vectors.
- **Watchdog / civil society organizations** (Monitor Ciudadano, Transparencia por Colombia) — want ranked lists to prioritize their limited investigation capacity. MAP@k is the right metric for them.
- **Government oversight agencies** (Contraloría, Procuraduría auditors) — want legally defensible, auditable outputs. They need source attribution (which RCAC source flagged this?) and need to trust the model is not leaking future information.

These users cannot install Python. They consume a REST API → future frontend.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these means the product feels incomplete or untrustworthy. In this domain these are non-negotiable because oversight actors need to explain their decisions.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Single composite risk score per contract** | Every corruption tool outputs a risk score. Users need one number to rank/triage. | LOW | CRI = weighted avg of M1-M4 probabilities + IRIC. Formula is defined. The score must be in [0,1] and mapped to a named category (Very Low → Very High). |
| **Risk score breakdown by component** | Users need to know which signal is driving the score — otherwise it's a black box. | LOW | Show P(M1), P(M2), P(M3), P(M4), and IRIC individually alongside their weights. Required for trust and auditability. |
| **Provider corruption background check (RCAC)** | Before investigating a contract, the first question is always "who is this provider?" If they have prior sanctions, that's immediately relevant. | HIGH | Must cover at minimum: Comptroller bulletins (fiscal liability), SIRI disciplinary/criminal sanctions, SECOP fines, SIC collusion. Multi-source deduplication is the hard part. |
| **Red flag checklist (IRIC components)** | Oversight actors are trained to look for specific warning signs (single bidder, direct contracting, missing data). An itemized checklist maps to their existing mental model. | MEDIUM | 11 binary IRIC flags across 3 dimensions. Each flag must be independently interpretable. Calibration by contract type is the complexity driver. |
| **Contract summary header** | Users need to confirm they analyzed the right contract before acting on the score. | LOW | Entity name, provider name+ID, contract value, type, modality, signing date, department. All available from contratos_SECOP.csv. |
| **Explainability per model (SHAP values)** | Without knowing WHY the model scored a contract high, users cannot write a story or open a case. A number without explanation is not actionable. | MEDIUM | TreeSHAP top-N features per model. This is the difference between a score and intelligence. Dependency: requires trained XGBoost models. |
| **Early detection (pre-execution features only)** | The system must be useful BEFORE the contract is executed — not after the damage is done. Post-execution signals are not available at signing time. | MEDIUM | Disciplined feature exclusion: no execution dates, no payment data, no actual quantities delivered. This constraint must be enforced in the pipeline, not just documented. |
| **Batch analysis capability** | Watchdog organizations and auditors do not analyze one contract at a time — they run sweeps over hundreds or thousands. | MEDIUM | POST /analyze/batch with up to 1000 contract IDs. Performance requirement: must not hang indefinitely. |
| **Health endpoint** | Any production system consumed by a frontend or integration must expose liveness. | LOW | GET /health returning model versions, RCAC last-updated date, SECOP API status. |
| **Evaluation metrics reported on training** | Academic origin means methodology must be documented and reported. AUC alone is not sufficient for imbalanced datasets. | LOW | AUC-ROC (primary), MAP@100, MAP@1000, NDCG@k, Precision, Recall, Brier Score. These are in the PRD and must be generated as artifacts by the training pipeline. |
| **Temporal leak prevention in RCAC features** | Any system trained on historical data must not use future information to featurize past events. If this is violated, reported metrics are fabricated. | HIGH | At training time, RCAC features must be filtered to `fecha_sancion < fecha_firma_contrato`. This requires an `as_of_date` parameter in `rcac_lookup.py`. Dependency: RCAC records must store sanction dates. |
| **Provider history pre-computation index** | Online features like `num_contratos_previos` cannot be computed in real-time via multiple SECOP API calls without unacceptable latency. | HIGH | `provider_history_index.pkl` generated offline alongside `rcac.pkl`. Dependency: offline pipeline must run before online pipeline is usable. |

---

### Differentiators (Competitive Advantage)

Features that set SIP apart from generic procurement monitoring or simple red-flag checklists. These are where SIP competes.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **4 separate outcome models (M1-M4) instead of one "corruption" model** | Different types of procurement failure have different causal structures. A single binary "corrupt/not-corrupt" label conflates cost overruns (often systemic), delays (often capacity-related), Comptroller findings (active fraud), and SECOP fines (procedural). Separate models give oversight actors intelligence on the TYPE of risk, not just its magnitude. | HIGH | Requires 4 training runs, 4 SHAP explainers, 4 label construction pipelines. The composite CRI is then interpretable at the component level. |
| **IRIC as both descriptive checklist AND ML input feature** | Most systems use either a rules index OR a machine learning model — not both. The dual role of IRIC (expert-coded red flag checklist + input feature for XGBoost) means the ML model receives structured domain expertise, not just raw data. This is the core methodological innovation from VigIA. | HIGH | Requires IRIC to be computed before model inference (ordering constraint). IRIC thresholds must be calibrated at national level by contract type — not just Bogotá as in VigIA. |
| **National-level IRIC threshold calibration (not Bogotá-only)** | VigIA calibrated IRIC thresholds on Bogotá data only. Colombian public procurement varies enormously by region and contract type. National calibration makes the tool applicable to contracts in Amazonas or Chocó, not just the capital. | MEDIUM | Requires percentile computation across 341K contracts segmented by `tipo_contrato`. Output is `iric_thresholds.json` keyed by contract type. |
| **Legal representative cross-referencing in RCAC** | Shell companies are a classic corruption evasion technique: the NIT (company ID) is clean but the legal representative has sanctions. Checking both the entity AND its legal representative catches this pattern. No Colombian procurement tool in the academic literature does this at scale. | HIGH | Requires `proveedores_registrados.csv` to have legal representative document data. Two-pass RCAC lookup per legal entity contract. |
| **Multi-source RCAC (7+ independent sources)** | Single-source sanction registries have coverage gaps — a sanctioned provider simply waits to be removed from one list. Requiring a match across 7 independent sources (Comptroller, SIRI, SIC, FGN, SECOP, Monitor Ciudadano, organized people) creates a much harder evasion problem. The `num_fuentes_distintas` feature captures independent corroboration. | HIGH | Each source has a different format, identifier scheme, and update cadence. Normalization and deduplication across sources is the engineering challenge. |
| **Bid distribution anomaly detection (kurtosis + normalized relative difference)** | Collusion between bidders leaves statistical fingerprints in the distribution of submitted bids. The Imhof (2018) bid-rigging detection statistics (curtosis_licitacion, diferencia_relativa_norm) are not present in standard procurement monitoring tools. | MEDIUM | Requires `ofertas_proceso_SECOP.csv` with at least 4 bids per process to compute kurtosis. Many processes have 0-1 bids (direct contracting) so these features will be NaN-heavy — imputation strategy required. |
| **Election-cycle proximity feature (`dias_a_proxima_eleccion`)** | Gallego et al. (2021) found this to be a specific predictor for M3 (Comptroller findings). Public procurement corruption peaks near election cycles in Colombia. No other tool incorporates this temporal signal. | LOW | Requires hardcoded list of Colombian presidential and congressional election dates. Simple computation once the date list exists. |
| **SHAP waterfall explanation per model** | Most ML-based procurement tools give a score and feature importances at the global level. Per-contract, per-model SHAP values enable sentence-level explanations: "This contract scored high for cost overruns BECAUSE: direct contracting (+0.15), provider registered 45 days before signing (+0.12), contract value above 99th percentile (+0.10)." This is the difference between a score and a lead. | MEDIUM | TreeSHAP is computationally cheap at inference time. The API must return raw SHAP values (not just text) so the frontend can build waterfall visualizations. |
| **Configurable CRI weights without retraining** | Different oversight contexts warrant different emphasis. A Comptroller audit team cares most about M3 (fiscal findings). A journalist covering delays cares most about M2. Configurable weights in `model_weights.json` allow context-specific risk profiles without rebuilding models. | LOW | Already specified in the PRD. The constraint: weights must sum to 1. Future work: empirical weight calibration using feedback from actual investigations. |
| **Immutable report anchoring via IPFS + Ethereum (post-v1)** | Corruption risk assessments are politically sensitive. A government actor can suppress or retroactively deny a risk report. Anchoring the SHA hash of each report on a public blockchain makes tampering detectable. No academic or NGO tool in this domain currently does this. | HIGH | Out of scope for v1 but architecture must not block it. Reports must be serializable (JSON) and deterministic (same input → same output). |

---

### Anti-Features (Deliberately NOT Building)

Features that seem good but create specific problems for SIP's context.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Entity-level aggregate risk scores** | Users naturally want to know "which government entities are most corrupt overall?" | Aggregating contract-level scores to entity level conflates legitimate procurement volume with corruption risk. A large entity (INVIAS, Min. Salud) will appear risky simply because it signs thousands of contracts. The unit of analysis is the individual contract — this is a deliberate design decision backed by Gallego et al. | Produce ranked lists of HIGH-risk contracts filtered by entity. Let the user aggregate manually with full visibility into the denominator. |
| **Real-time model retraining on new contracts** | Users want the model to "learn" as new corruption cases emerge. | Retraining without rigorous validation, temporal split discipline, and threshold recalibration will degrade model performance and introduce new temporal leakage. Academic models require offline validation before deployment. | Scheduled offline retraining (e.g., quarterly) with full evaluation pipeline run, human review of metric shifts, and versioned model artifacts. |
| **Binary "corrupt / not corrupt" label** | Simpler to explain: "this contract IS corrupt." | No contract in SECOP II is labeled as corrupt by ground truth. The labels available are proxies (amendments, Comptroller records, SECOP fines). A binary "corrupt" output overstates certainty and creates legal liability. Oversight actors need probability, not verdict. | Output P(outcome) per model type + CRI as a risk signal, not a classification. The system flags, it does not adjudicate. |
| **Natural language generation (LLM) for report narratives** | "Generate a paragraph explaining the risk" sounds powerful. | LLMs hallucinate. In an investigative journalism or legal context, a fabricated detail in a generated corruption narrative is catastrophic. The system's credibility rests on every claim being traceable to a specific data point. | Return structured SHAP values + RCAC flags as JSON. Let the frontend render them as human-readable text using deterministic templates. |
| **Frontend / UI in v1** | Users want to see results visually immediately. | Building UI before validating that the model outputs are useful and the API contract is stable leads to expensive rework. The OpenAPI docs at `/docs` serve as specification for the future frontend team. | FastAPI auto-docs at `/docs`. REST API with complete JSON responses is sufficient for v1 academic validation. |
| **OAuth / user authentication in v1 API** | Security concern: who can query the risk of any contract? | OAuth adds significant integration complexity (token management, refresh flows). v1 is an academic deliverable consumed by the research team and a small set of partner organizations. | API Key authentication (X-API-Key header) is sufficient for v1 access control. Add OAuth when the frontend is built and user management becomes necessary. |
| **SMOTE for class imbalance** | Common technique for handling imbalanced datasets in ML. | The VigIA and Gallego et al. literature has validated that scale_pos_weight + upsampling outperforms SMOTE on this specific domain with this class distribution. Introducing SMOTE without re-running the academic comparison would be a methodological deviation from the established baseline. | scale_pos_weight (XGBoost native) + minority class upsampling, as specified in the PRD. |
| **Alternative ML algorithms (Random Forest, LightGBM, Neural Nets)** | Other algorithms might perform better. | XGBoost is the academically established choice for this domain (Gallego et al. 2021, VigIA 2024, Mojica 2021). Switching algorithms breaks the comparison baseline. The SHAP TreeExplainer is optimized for XGBoost. | Stick with XGBoost. If academic publication requires comparison, add a single comparison run as an appendix artifact, not as a production model path. |
| **Post-execution features in the models** | More data = better predictions. Execution dates, payment records, and actual quantities delivered are powerful predictors. | The explicit goal is EARLY DETECTION — flagging a contract BEFORE problems manifest. Including post-execution variables means the model can only be run after the contract closes, which defeats the purpose. | Strict enforcement of Category A/B/C/D feature list. All features must be available at contract signing time. Execution variables explicitly listed as excluded in the feature engineering pipeline. |
| **Mobile application** | Reach for journalists on the go. | Separate platform, separate build/maintenance, separate UX requirements. Out of scope until the web frontend is validated. | REST API is mobile-consumable. A future mobile app would be a thin client consuming the same API. |

---

## Feature Dependencies

```
[RCAC Registry (7 sources)]
    └──required by──> [Provider background check]
    └──required by──> [Legal representative cross-reference]
    └──required by──> [RCAC features in model input (Category C)]
    └──required by──> [Temporal leak guard (as_of_date filter)]

[IRIC Threshold Calibration (offline)]
    └──required by──> [IRIC Score computation]
                          └──required by──> [IRIC as model feature (Category D)]
                          └──required by──> [IRIC in CRI formula]
                          └──required by──> [IRIC red flag checklist in API response]

[Provider History Index (offline, pre-computed)]
    └──required by──> [num_contratos_previos feature]
    └──required by──> [num_sobrecostos_previos feature]
    └──required by──> [historial_proveedor_alto IRIC component]
    └──required by──> [Online pipeline latency SLA]

[4 Trained XGBoost Models (M1-M4)]
    └──required by──> [P(M1), P(M2), P(M3), P(M4) probabilities]
    └──required by──> [SHAP values per model]
    └──required by──> [CRI composite score]
    └──required by──> [REST API /analyze endpoint]

[Feature Engineering Pipeline]
    └──required by──> [Model training (offline)]
    └──required by──> [Online inference (must be identical code)]
    └──requires──> [RCAC Registry]
    └──requires──> [Provider History Index]
    └──requires──> [IRIC Thresholds]

[IRIC Score computation]
    └──enhances──> [M1-M4 predictions] (IRIC is an input feature)

[Temporal leak guard]
    └──required by──> [Training validity] (without this, metrics are inflated and the system does not work as reported)

[Bid distribution anomaly stats (kurtosis, DRN)]
    └──depends on──> [ofertas_proceso_SECOP.csv with ≥4 bids]
    └──many NaN for direct contracting contracts]
```

### Dependency Notes

- **RCAC requires temporal leak guard:** The RCAC must support an `as_of_date` parameter from day one. Retrofitting this after training will require full retraining.
- **Provider History Index is a parallel artifact to RCAC:** Both are built offline, serialized to `.pkl`, and loaded at API startup. They follow the same O(1) lookup pattern.
- **IRIC must be computed before model inference:** In the pipeline, IRIC is an input feature to XGBoost models. Order of operations in `pipeline.py` is a correctness requirement, not a preference.
- **Feature engineering code must be shared between offline and online:** Any divergence between batch training features and online inference features creates a training-serving skew. `pipeline.py` is the single source of truth — data source changes, not code.
- **Bid anomaly features conflict with direct contracting:** kurtosis and DRN require multiple bids. Direct contracting (60%+ of Colombian contracts) produces NaN for these features. Imputation strategy (zero, median, indicator variable) must be consistent between offline and online pipelines.

---

## MVP Definition

### Launch With (v1)

The academic deliverable: a working ML pipeline that can score a contract and explain the score.

- [x] **RCAC from 4+ confirmed sources** (Comptroller bulletins, SIRI sanctions, SECOP fines, fiscal responsibilities) — why essential: provider background is the most immediately actionable signal. Legal representative cross-reference and Monitor Ciudadano can be added in v1.x.
- [x] **IRIC calculation with national calibration** — why essential: it is both a user-facing checklist and a model input feature. Cannot train models without it.
- [x] **4 XGBoost models trained on pre-execution features** — why essential: the system's core value proposition is ML-based risk prediction, not just red flag counting.
- [x] **SHAP explainability per model** — why essential: a risk score without explanation is not actionable for oversight actors. This is what makes SIP different from a simple IRIC score.
- [x] **CRI composite index** — why essential: users need one number to triage, not 5 separate scores.
- [x] **REST API: POST /analyze, GET /health** — why essential: the frontend team and partner organizations cannot consume Python objects. The API is the delivery mechanism.
- [x] **Temporal leak guard in RCAC lookup** — why essential: without this, the system's reported metrics are wrong and it will underperform in production.
- [x] **Provider History Index** — why essential: without it, the online pipeline cannot compute provider history features in acceptable latency.

### Add After Validation (v1.x)

- [ ] **POST /analyze/batch** — add when partner organizations demonstrate need for sweep analysis over 100+ contracts at once.
- [ ] **Monitor Ciudadano integration into RCAC** — add when Excel parsing and entity identification is complete. Currently requires structure analysis.
- [ ] **organized_people_data.csv RCAC integration** — add after column structure analysis confirms identifiers are compatible with CC/NIT normalization.
- [ ] **Legal representative cross-reference** — add when `proveedores_registrados.csv` legal rep column mapping is confirmed.
- [ ] **API Key authentication** — add before any external partner gets API access.
- [ ] **Bid anomaly features (kurtosis, DRN)** — add after confirming `ofertas_proceso_SECOP.csv` has sufficient multi-bid processes to make these features informative. Currently flagged as NaN-heavy.
- [ ] **CORS configuration** — add when frontend development begins.

### Future Consideration (v2+)

- [ ] **IPFS + Ethereum report anchoring** — defer until report format is stable and a partner organization has a use case for tamper-proof provenance. Architecture must not block it, but the integration adds operational complexity (IPFS node, Ethereum wallet/gas).
- [ ] **Configurable CRI weights per use case** — defer until empirical calibration data exists (actual investigation outcomes matched to model scores). Equal weights are a defensible default.
- [ ] **Frontend (React/Next.js)** — defer until API is validated with real oversight actors. FastAPI `/docs` serves as spec.
- [ ] **Cloud deployment** — defer until the system is validated locally and partner demand justifies infrastructure investment.
- [ ] **Model retraining pipeline (scheduled)** — defer until v1 training pipeline is stable. Premature automation of a not-yet-validated pipeline creates compounding errors.
- [ ] **Entity-level risk profiling** — defer until the contract-level model is validated. Aggregate scoring requires a principled normalization approach that accounts for entity size and contract volume.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| RCAC registry (core 4 sources) | HIGH | HIGH | P1 |
| Temporal leak guard (as_of_date) | HIGH (correctness) | MEDIUM | P1 |
| IRIC with national calibration | HIGH | MEDIUM | P1 |
| Provider History Index | HIGH (latency) | MEDIUM | P1 |
| 4 XGBoost models (M1-M4) | HIGH | HIGH | P1 |
| SHAP explainability | HIGH | LOW | P1 |
| CRI composite score | HIGH | LOW | P1 |
| REST API /analyze endpoint | HIGH | MEDIUM | P1 |
| Risk score breakdown by component | HIGH | LOW | P1 |
| Contract summary header | HIGH | LOW | P1 |
| Red flag checklist (IRIC flags) | HIGH | LOW | P1 |
| POST /analyze/batch | MEDIUM | MEDIUM | P2 |
| Legal representative cross-reference | HIGH | MEDIUM | P2 |
| Monitor Ciudadano RCAC integration | MEDIUM | MEDIUM | P2 |
| API Key authentication | HIGH (security) | LOW | P2 |
| Bid anomaly features (kurtosis/DRN) | MEDIUM | MEDIUM | P2 |
| Election-cycle proximity feature | MEDIUM | LOW | P2 |
| CORS configuration | LOW (needed for frontend) | LOW | P2 |
| Configurable CRI weights | MEDIUM | LOW | P3 |
| IPFS + Ethereum anchoring | HIGH (for provenance use case) | HIGH | P3 |
| Frontend UI | HIGH (for non-technical users) | HIGH | P3 |
| Cloud deployment | MEDIUM | HIGH | P3 |
| Scheduled model retraining | MEDIUM | HIGH | P3 |
| Entity-level aggregate risk | MEDIUM | MEDIUM | P3 |
| Mobile application | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for v1 academic launch
- P2: Should have, add in v1.x after core is validated
- P3: Future consideration, v2+

---

## Competitor / Prior Work Feature Analysis

| Feature | VigIA / Salazar et al. (2024) | Gallego et al. (2021) | SIP (our approach) |
|---------|------|------|------|
| **Scope** | Bogotá contracts only | National but older dataset | National, SECOP II, current data |
| **ML algorithm** | Random Forest | Random Forest | XGBoost (literature-motivated upgrade) |
| **Outcome models** | M1 (cost overruns), M2 (delays) | M3 (Comptroller), extensions | All four: M1+M2+M3+M4 |
| **IRIC** | Yes — Bogotá calibrated | No | Yes — nationally calibrated |
| **IRIC as ML feature** | Yes | No | Yes |
| **SHAP explainability** | Yes (global + per-contract) | No | Yes (per-contract, per model) |
| **Sanction registry (RCAC)** | Not described | Comptroller bulletins only | 7+ sources with deduplication |
| **Legal representative check** | No | No | Yes (planned v1.x) |
| **Temporal leak guard** | Not documented | Not documented | Explicit `as_of_date` parameter |
| **Provider history pre-computation** | Not documented (offline notebooks) | Not applicable | `provider_history_index.pkl` |
| **REST API** | No — Jupyter notebooks | No — research code | Yes — FastAPI |
| **Bid anomaly stats** | kurtosis + DRN (IRIC) | No | Yes (as IRIC components) |
| **Election cycle feature** | No | Yes | Yes |
| **Composite index** | No | No | CRI = weighted avg of 5 signals |
| **Report immutability** | No | No | Planned post-v1 (IPFS/ETH) |
| **National contract type calibration** | No (Bogotá only) | No | Yes — by tipo_contrato |

---

## Sources

- **Gallego, Rivero & Martínez (2021)** — "Preventing Rather than Punishing: An Early Warning Model of Malfeasance in Public Procurement." Feature importance rankings, class imbalance strategies (scale_pos_weight=25 for Comptroller), MAP@k and NDCG@k as metrics, election-cycle proximity feature.
- **Salazar, Pérez & Gallego (2024) — VigIA** — IRIC methodology (11 components, 3 dimensions), SHAP explainability per contract, dual role of IRIC, label construction from SECOP II amendments. VigIA codebase at `data/Vigia/`.
- **Mojica (2021)** — Hyperparameter tuning at scale (136K combinations), RandomizedSearchCV justification for 200-iteration random search.
- **Imhof (2018)** — Bid rigging detection statistics: kurtosis formula and normalized relative difference (DRN) for collusion detection.
- **Fazekas & Kocsis (2020)** — Single-bidder indicator, direct contracting as red flag, decision period extremes.
- **Baltrunaite et al. (2020)** — Single-bidder as competition deficit signal.
- **SIP PRD v1.0 (prd.md)** — Full feature specification, API contract, RCAC schema, IRIC component definitions, evaluation metrics.
- **SIP PRD v2.0 Refinado (ignore/PRD_SIP_Backend_v2.0_Refinado.md)** — Critical issue analysis: temporal leakage, provider history index gap, Python version, authentication.
- **VigIA codebase analysis** — `data/Vigia/created_data/trained_models/models_features.txt` for confirmed feature sets used in VigIA production models.

---
*Feature research for: Corruption Detection / Public Procurement Risk Analysis (SIP)*
*Researched: 2026-02-27*
