# PRD: SIP — Intelligent Prediction System for Corruption in Public Procurement

## Backend — Project Requirements Document v1.0

---

## Meta

| Field | Value |
|---|---|
| Project | SIP (Intelligent Prediction System) |
| Version | 1.0 |
| Date | February 2026 |
| Scope of this document | **Backend only** |
| Language | Python 3.12 |
| Methodological advisor | Jorge Gallego (IDB; co-author of VigIA and Gallego et al. 2021) |
| Academic foundations | Gallego, Rivero & Martínez (2021); Salazar, Pérez & Gallego (2024) — VigIA; Mojica (2021) |

---

## 1. Executive Summary

SIP is a Python backend system that receives the identifier of a Colombian public contract from SECOP II, queries the open data API, runs 4 pre-trained XGBoost models and a rules index (IRIC), and returns a **Composite Risk Index (CRI)** with feature-by-feature SHAP explanations.

**Fundamental design decisions:**

- **Unit of analysis:** individual contract.
- **Temporal mode:** real-time inference on offline-trained models.
- **Algorithm:** XGBoost for all 4 models, with SHAP (TreeSHAP) for explainability.
- **Approach:** early detection (only pre-execution variables).
- **Segmentation:** a single model per outcome.
- **Composite index:** simple weighted average of the probabilities from the 4 models + the IRIC. Initial equal weights (1/5 each).
- **IRIC (Contractual Irregularity Risk Index):** serves a dual role: (a) it is presented as a descriptive statistic to the user, and (b) it is included as an input feature for the ML models.
- **Frontend:** will be developed in a later phase. This backend exposes a REST API (FastAPI) that the frontend will consume. Section 10 defines the interface contract.

---

## 2. Objectives

### 2.1 General Objective

Build a backend that, given a SECOP II contract ID, calculates a composite corruption risk index based on multiple ML models and a rules index, exposing the results via REST API.

### 2.2 Specific Objectives

1. Build a **Consolidated Corruption Background Registry (RCAC)** that unifies 6+ sanction sources at the person level (CC/NIT), including legal representatives.
2. Calculate an **IRIC** (11 binary red flags) adapted to the national level, calibrated by contract type.
3. Train **4 XGBoost binary classification models** for: cost overruns (M1), delays (M2), appearance in Comptroller records (M3), SECOP fines (M4).
4. Generate **SHAP values** per prediction to explain each result.
5. Combine into a **Composite Risk Index (CRI)** with a weighted average.
6. Expose everything via **REST API** (FastAPI) ready to be consumed by a future frontend.


## 3. Architecture

### 3.1 Two Pipelines

```
OFFLINE PIPELINE
════════════════════════════════════
  Bulk download        Feature         Training
  SECOP II API    ───► Engineering ───► XGBoost × 4
  + RCAC Sources       + RCAC build     models
                       + IRIC calibrate
                              │
                              ▼
                       Artifacts: models .pkl, RCAC .pkl,
                       iric_thresholds.json, metadata.json


ONLINE PIPELINE (real-time, per contract)
════════════════════════════════════════════
  POST /api/v1/analyze    Query SECOP      Feature
  { contract_id }    ───► II API + RCAC ───► Engineering
                          lookup              (same code)
                                                  │
                                                  ▼
                                            IRIC Calculation
                                                  │
                                                  ▼
                                            XGBoost Inference × 4
                                            + SHAP values
                                                  │
                                                  ▼
                                            CRI (weighted average)
                                                  │
                                                  ▼
                                            JSON Response
```

**Key principle:** the feature engineering, IRIC calculation, and inference code is **exactly the same** in both pipelines. The only difference is the data source (batch vs. individual API).

### 3.2 Project Structure

```
sip/
├── config/
│   ├── settings.py                # Constants, API URLs, paths, feature lists
│   ├── iric_thresholds.json       # Calibrated IRIC thresholds (generated offline)
│   └── model_weights.json         # CRI weights: {"M1": 0.20, "M2": 0.20, ...}
│
├── data/
│   ├── secop_client.py            # Async client for Socrata API (datos.gov.co)
│   ├── rcac_builder.py            # Builds the RCAC from 6+ sources
│   ├── rcac_lookup.py             # In-memory dict for O(1) lookup
│   └── batch_downloader.py        # Bulk download for training
│
├── features/
│   ├── contract_features.py       # Contract features (value, modality, type, etc.)
│   ├── provider_features.py       # Provider features (seniority, history, RCAC)
│   ├── process_features.py        # Process features (bids, publicity, decision)
│   ├── temporal_features.py       # Temporal features (durations, sign-to-start, month)
│   ├── iric.py                    # Calculation of the 11 IRIC components
│   └── pipeline.py                # Orchestrator: raw data → complete feature vector
│
├── models/
│   ├── trainer.py                 # Training: XGBoost + RandomSearch + StratifiedKFold
│   ├── predictor.py               # Inference: load .pkl → predict_proba + SHAP
│   ├── composite_index.py         # CRI = Σ(wi × Pi)
│   ├── class_balance.py           # Imbalance strategies (scale_pos_weight, upsample)
│   └── evaluation.py              # Metrics: AUC, MAP@k, NDCG@k, Brier, Precision, Recall
│
├── api/
│   ├── app.py                     # FastAPI application
│   ├── routes.py                  # POST /analyze, GET /health, POST /analyze/batch
│   └── schemas.py                 # Pydantic models (request/response)
│
├── training/
│   ├── train_pipeline.py          # Complete pipeline: download → features → train → evaluate
│   └── calibrate_iric.py          # Calculates percentiles for iric_thresholds.json
│
├── artifacts/                     # Generated by the offline pipeline
│   ├── models/                    # M1.pkl, M2.pkl, M3.pkl, M4.pkl
│   ├── rcac.pkl                   # Serialized RCAC
│   ├── iric_thresholds.json       # Calibrated thresholds
│   └── training_metadata.json     # Dates, metrics, versions
│
|---secopDatabases/                #this folder already exists
    heders.csv                      #a list of the headers for the files in this folder. IMPORTANT to know what information is contained without opening them. 
    boletines.csv                   #Contraloria bulletins
    contratos_secop.csv             # contract information 
    ofertas_proceso_SECOP.csv       #offers per awarded process
    procesos_SECOP.csv              # csv of contracting processes
    proponentes_proceso_SECOP.csv   # proponents per contracting process
    proveedores_registrados.csv     # list of all registered contractors
    suspensiones_contratos.csv      # suspended contracts
    
    |
    
    |
    |
└── tests/
    ├── test_rcac.py
    ├── test_features.py
    ├── test_iric.py
    ├── test_models.py
    └── test_api.py
```

---

## 4. Data Sources

### 4.1 SECOP II Data (explanatory variables)

All accessible via Socrata API at datos.gov.co. Dataset IDs are included for direct access.

#### 4.1.1 Electronic Contracts

- **Dataset:** `jbjy-vk9h`
- **Local file:** `secopDatabases/contratos_SECOP.csv`
- **Dimensions:** 341,727 × 87 | 570 MB
- **Unit:** Individual contract
- **Role:** Main table. Core contract variables.
- **Key columns used:**

```
ID Contrato                              → Primary key
Codigo Entidad, Nombre Entidad           → Contracting entity
Codigo Proveedor, Nombre Proveedor       → Awarded provider
Tipo de Documento Proveedor              → "CC" or "NIT" (RCAC key)
Documento Proveedor                      → Document number (RCAC key)
Valor del Contrato                       → Amount in COP
Modalidad de Contratacion                → Direct, bidding, etc.
Tipo de Contrato                         → Professional services, construction, etc.
Fecha de Firma                           → Signing date
Fecha de Inicio del Contrato             → Planned start date
Fecha de Fin del Contrato                → Planned end date
Fecha de Inicio de Ejecucion             → (EXCLUDED: post-execution)
Fecha de Fin de Ejecucion                → (EXCLUDED: post-execution)
Departamento, Ciudad                     → Geographic location
Codigo UNSPSC                            → Product/service classification
Justificacion Modalidad de Contratacion  → Justification for the mechanism
Origen de los Recursos                   → Source of funding
```

#### 4.1.2 Procurement Processes

- **Dataset:** `p6dx-8zbt`
- **Local file:** `secopDatabases/procesos_SECOP.csv`
- **Dimensions:** 5,106,527 × 59 | 5.3 GB
- **Role:** Pre-contractual phase variables.
- **Key columns:**

```
ID Proceso                          → Cross-reference key with contracts
Fecha de Publicacion del Proceso    → Publicity start
Fecha de Ultima Publicacion         → Publicity end
Fecha de Adjudicacion               → Award date
Numero de Ofertas Recibidas         → Competition
Duracion del Proceso                → Total duration
Tipo de Proceso                     → Classification
```

#### 4.1.3 Bids per Process

- **Local file:** `secopDatabases/ofertas_proceso_SECOP.csv`
- **Dimensions:** 6,454,843 × 163 | 3.4 GB
- **Role:** Actual competition: how many bidders, bid dispersion.

#### 4.1.4 Bidders per Process

- **Local file:** `secopDatabases/proponentes_proceso_SECOP.csv`
- **Dimensions:** 3,310,267 × 9 | 841 MB
- **Role:** Bidder details (document type, role in consortium). Provider history.
- **Key columns:**

```
ID Proceso          → Cross-reference with processes
ID Proponente       → Identifier
Nombre Proponente   → Name/business name
Tipo de Documento   → CC/NIT
Numero de Documento → RCAC key
Rol                 → Individual, consortium, etc.
```

#### 4.1.5 Registered Providers

- **Local file:** `secopDatabases/proveedores_registrados.csv`
- **Dimensions:** 1,555,059 × 55 | 564 MB
- **Role:** Master provider registry. Cross-reference table between contracts and RCAC. Contains legal representative data.
- **Key columns:**

```
ID Proveedor                → Identifier
Nombre / Razon Social       → Name
Tipo de Persona             → Natural / Legal entity
Tipo de Documento           → CC / NIT / CE / Passport
Numero de Documento         → RCAC key (primary cross-reference)
Fecha de Registro           → Provider seniority
[Legal rep. columns]        → Name, document of legal representative
                               (secondary cross-reference against RCAC)
```

#### 4.1.6 Contract Execution

- **Local file:** `secopDatabases/ejecucion_contratos.csv`
- **Dimensions:** 4,211,724 × 16 | 682 MB
- **Role:** Planned vs. awarded vs. received quantities. Enables construction of cost overrun and delay labels.
- **Key columns:**

```
ID Contrato            → Cross-reference
Cantidad planeada      → Baseline
Cantidad adjudicada    → Awarded value
Cantidad Recibida      → Actual value
Valor planeado         → Monetary baseline
Valor adjudicado       → Actual monetary value
```

#### 4.1.7 Amendments (source of target variables M1 and M2)

- **Local File:** secopDatabases/adiciones.csv
- **Dataset:** `cb9c-h8sn` (SECOP II Amendments)
- **Role:** **Target variables for M1 and M2.** Record of contractual modifications.
- **Label construction:**
  - **M1 (Cost Overruns):** binary (0/1). Equals 1 if the contract has ≥ 1 amendment in value.
  - **M2 (Delays):** binary (0/1). Equals 1 if the contract has ≥ 1 amendment in time.
  - Same strategy used in VigIA (Salazar et al., 2024, section 4.4).

### 4.2 Data for the RCAC (Consolidated Corruption Background Registry)

These sources identify natural and legal persons with corruption backgrounds. They are cross-referenced with SECOP providers to generate features.

#### Source 1: Comptroller Bulletins

- **File:** `Contraloria Data Merger/boletines.csv`
- **Dimensions:** 10,817 × 9 | 1.3 MB
- **Identifier:** `document type` + `document number`
- **Captures:** Fiscal liability holders declared by the Comptroller General. Used for the RCAC and XGBoost Model 3 (M3).
- **Columns:** `Fiscal Liability Holder`, `document type`, `document number`, `Affected Entity`, `Fiscal Damage Amount`, `Process Status`.

#### Source 2: SIRI Sanctions (Attorney General's Office)

- **File:** `PACO/sanciones_SIRI_PACO.csv`
- **Dimensions:** 46,583 × 28 | 18.2 MB
- **Identifier:** Positional columns 5 (`Document type`) and 6 (`Document number`)
- **Captures:** Disciplinary and criminal sanctions. Public servants and private individuals. **Largest RCAC source.**
- **Note:** File without explicit headers. Interpret by position.


#### Source 3: People Data

- **File:** `organized_people_data.csv`
- **Size:** 12 MB
- **Captures:** People involved in corruption according to PACO.
- **Status:** Separate input, not integrated. Requires structure analysis.
- **Action:** Analyze identification columns and integrate into rcac_builder.py.

#### Source 4: People Data

- **File:** `SIP Code/Data/Propia/Monitor`
- **Size:** 
- **Captures:** People involved in corruption according to Monitor Ciudadano.
- **Status:** Separate input, not integrated. Requires structure analysis.
- **Action:** Extract names of people or companies with CC or NIT identifier. Analyze degree of crime. 
---

## 5. Consolidated Corruption Background Registry (RCAC)

### 5.1 Purpose

Unified table indexed by `(document_type, document_number)` that consolidates all backgrounds from the 7 sources in section 4.2. It is cross-referenced against `proveedores_registrados.csv` to enrich each contract.

### 5.2 Registry Schema

```python
@dataclass
class RCACRecord:
    tipo_documento: str             # "CC" | "NIT" | "CE" | "PASAPORTE" | "OTRO"
    numero_documento: str           # Normalized: digits only, no dots/dashes/check digit
    nombre: str
    tipo_persona: str               # "NATURAL" | "JURIDICA"

    # Binary flags per source (0/1)
    tiene_responsabilidad_fiscal_contraloria: int
    tiene_sancion_disciplinaria_siri: int
    tiene_sancion_penal_siri: int
    tiene_multa_secop: int
    tiene_antecedente_colusion_sic: int
    tiene_registro_monitor_ciudadano: int

    # Cumulative counts
    num_responsabilidades_fiscales: int
    num_sanciones_disciplinarias: int
    num_sanciones_penales: int
    num_multas_secop: int
    cuantia_total_dano_fiscal: float  # Sum of amounts (Comptroller)

    # Temporality
    fecha_primera_sancion: Optional[date]
    fecha_ultima_sancion: Optional[date]

    # Meta
    fuentes: List[str]              # Names of reporting sources
    num_fuentes_distintas: int      # How many independent sources report it
```

### 5.3 Construction Pipeline (`rcac_builder.py`)

```
Step 1: DOCUMENT NORMALIZATION
  - Each source has different formats (CC, C.C., cédula, NIT with check digit...)
  - Normalize tipo_documento → controlled catalog: CC, NIT, CE, PASAPORTE, OTRO
  - Normalize numero_documento → pure numeric string (strip dots, dashes, spaces)
  - For responsabilidades_fiscales_PACO.csv: parse combined field "Tipo y Num Documento"
  - For sanciones_SIRI_PACO.csv: use positional columns 5 and 6

Step 2: DEDUPLICATION
  - Group by (tipo_documento, numero_documento)
  - One individual in multiple sources = valuable information → num_fuentes_distintas
  - For duplicates within the same source: aggregate counts, keep oldest/most recent date

Step 3: CROSS-REFERENCE WITH PROVIDERS
  - Inner join with proveedores_registrados.csv by (tipo_documento, numero_documento)
  - This generates features for the direct provider

Step 4: LEGAL REPRESENTATIVE CROSS-REFERENCE
  - For providers with tipo_persona == "JURIDICA":
    - Extract tipo_documento and numero_documento of the legal representative
    - Second cross-reference against RCAC
  - This detects shell companies: clean NIT but legal representative with background records

Step 5: SERIALIZATION
  - Dict indexed by (tipo_doc, num_doc) → RCACRecord
  - Serialize with joblib for fast loading in the online pipeline
```

### 5.4 Features Derived from the RCAC (for each contract)

```python
# Direct provider features
proveedor_en_rcac: bool                   # Has any background record?
proveedor_responsable_fiscal: bool
proveedor_sancion_disciplinaria: bool
proveedor_sancion_penal: bool
proveedor_multa_secop_previa: bool
proveedor_colusion_sic: bool
proveedor_monitor_ciudadano: bool
proveedor_num_antecedentes_total: int
proveedor_num_fuentes_distintas: int
proveedor_cuantia_dano_fiscal: float
proveedor_dias_desde_ultima_sancion: int | None

# Legal representative features (legal entities only)
representante_en_rcac: bool
representante_num_antecedentes: int
```

---

## 6. IRIC — Contractual Irregularity Risk Index

### 6.1 Foundation

Adapted from VigIA (Salazar et al., 2024), based on Zuleta et al. (2019) and IMCO (2018). Originally calibrated for Bogotá; this system recalibrates it at the national level.

### 6.2 Dual Role

1. **ML model feature:** it is calculated BEFORE inference and included as an explanatory variable for M1-M4. This gives the models a "coded expert opinion" as input.
2. **Descriptive statistic:** it is shown to the user broken down by component, allowing them to see which red flags are active.

### 6.3 Components (11 binary variables, 2 anomaly calculations)

#### Dimension 1: Lack of Competition (6 variables)

| # | Code | Equals 1 when... | Reference |
|---|---|---|---|
| 1 | `unico_proponente` | The process received ≤ 1 bid | Baltrunaite et al. (2020); Szucs (2023) |
| 2 | `proveedor_multiproposito` | Provider with > 1 distinct economic activity in UNSPSC | Open Contracting Partnership (2020) |
| 3 | `historial_proveedor_alto` | Provider with > P95 previous contracts won (by contract type) | Fazekas & Kocsis (2020) |
| 4 | `contratacion_directa` | Modality = direct contracting | Fazekas & Kocsis (2020); Bosio et al. (2020) |
| 5 | `regimen_especial` | Modality = special regime | Zuleta et al. (2019) |
| 6 | `periodo_publicidad_extremo` | Publicity duration < P1 or > P99 (by contract type) | Decarolis & Giorgiantonio (2022) |

#### Dimension 2: Lack of Transparency (2 variables)

| # | Code | Equals 1 when... | Reference |
|---|---|---|---|
| 7 | `datos_faltantes` | Missing mandatory fields: provider ID, modality justification, or contract value missing/> P99 by type | Fazekas et al. (2016) |
| 8 | `periodo_decision_extremo` | Days between bid closing and signing < P5 or > P95 (by type) | Fazekas & Kocsis (2020) |

#### Dimension 3: Anomalies (3 variables)

| # | Code | Equals 1 when... | Reference |
|---|---|---|---|
| 9 | `proveedor_sobrecostos_previos` | Provider has previous contracts with value amendments | VigIA (Salazar et al., 2024) |
| 10 | `proveedor_retrasos_previos` | Provider has previous contracts with time amendments | VigIA (Salazar et al., 2024) |
| 11 | `ausencia_proceso` | No associated procurement process found in SECOP | Zuleta et al. (2019) |


#### Anomaly Calculation 1: Kurtosis

| Field | Detail |
|---|---|
| **Code** | `curtosis_licitacion` |
| **Formula** | `Kurt(bₜ) = [n(n+1)/(n-1)(n-2)(n-3)] × Σ((bᵢₜ - μₜ)/σₜ)⁴ − [3(n-1)²/(n-2)(n-3)]` |
| **Parameters** | `n` = total bids; `bᵢₜ` = bid `i`; `σₜ` = standard deviation; `μₜ` = arithmetic mean |
| **Signal** | Smart scaling with common factor → few variations between highest and lowest bid |
| **Reference** | Imhof (2018) |

#### Anomaly Calculation 2: Normalized Relative Difference

| Field | Detail |
|---|---|
| **Code** | `diferencia_relativa_norm` |
| **Formula** | `DRN = (b₂ₜ − b₁ₜ) / [(Σᵢ₌₁ⁿ⁻¹ bⱼₜ − bᵢₜ) / (n − 1)]` |
| **Parameters** | `b₁ₜ`, `b₂ₜ` = adjacent lowest bids; bids sorted in ascending order |
| **Signal** | Value > 1 indicates that the gap between the two lowest bids exceeds the average of adjacent differences |
| **Interpretation** | Distance between losing bids (coverage) significantly lower than that of the winning bid |
| **Reference** | Imhof (2018) |

### 6.4 Formula

```
IRIC = (1/11) × Σ(component_i)     for i = 1,...,11
Each component_i ∈ {0, 1}
Result: IRIC ∈ [0, 1]

Sub-scores by dimension:
  iric_competencia    = (1/6) × Σ(components 1-6)
  iric_transparencia  = (1/2) × Σ(components 7-8)
  iric_anomalias      = (1/3) × Σ(components 9-11)
```

### 6.5 National Threshold Calibration (`calibrate_iric.py`)

Percentile thresholds are calculated offline on national data, differentiating by contract type. They are stored in `iric_thresholds.json`:

```json
{
  "servicios_profesionales": {
    "historial_proveedor_p95": 42,
    "periodo_publicidad_p1": 1,
    "periodo_publicidad_p99": 45,
    "valor_contrato_p99": 980000000,
    "periodo_decision_p5": 2,
    "periodo_decision_p95": 120
  },
  "otros": {
    "historial_proveedor_p95": 28,
    "periodo_publicidad_p1": 3,
    "periodo_publicidad_p99": 90,
    "valor_contrato_p99": 2500000000,
    "periodo_decision_p5": 5,
    "periodo_decision_p95": 180
  }
}
```

---

## 7. Predictive Models

### 7.1 The 4 Models

| ID | Target Variable | Type of Waste | Label Source | Estimated % positives |
|---|---|---|---|---|
| **M1** | Cost overruns (value amendment) | Passive | SECOP II Amendments (`cb9c-h8sn`) | ~16% (VigIA) |
| **M2** | Delays (time amendment) | Passive | SECOP II Amendments (`cb9c-h8sn`) | ~18% (VigIA) |
| **M3** | Provider appears as fiscal liability holder | Active | Comptroller Bulletins (.csv file) | ~1-2% (Gallego et al. 2021) |
| **M4** | Provider with SECOP fine/sanction | Mixed | RCAC (SECOP fines) | ~1% (estimated) |

### 7.2 Algorithm: XGBoost

### 7.3 Features by Category

All models share the same feature vector. Fine selection is done via XGBoost's own feature importance. An **early detection approach is used: only pre-execution variables**.

#### Category A: Contract Variables

| Feature | Source Table | Transformation | Evidence in the Literature |
|---|---|---|---|
| `valor_contrato` | contratos_SECOP → `Valor del Contrato` | value | Gallego et al. (2021): top predictor for Comptroller, Confecámaras, and extensions. VigIA: top predictor for cost overruns. |
| `tipo_contrato_cat` | contratos_SECOP → `Tipo de Contrato` | Categorical (group < 0.1% into "Other") |
| `modalidad_contratacion_cat` | contratos_SECOP → `Modalidad de Contratacion` | Categorical: Direct, Bidding, Abbreviated Selection, Minimum Amount, Special Regime, Other | Gallego et al. (2021): direct type H was top predictor. |
| `es_contratacion_directa` | Derived from modality | Binary (1 if direct) | Fazekas & Kocsis (2020): fundamental red flag. |
| `es_regimen_especial` | Derived from modality | Binary | Zuleta et al. (2019). |
| `es_servicios_profesionales` | Derived from type | Binary | VigIA: behave differently from the rest. |
| `unspsc_categoria` | contratos_SECOP → `Codigo UNSPSC` | First 2 digits (category) | VigIA: Culture sector predictive. Gallego et al.: transportation, public services. |
| `departamento_cat` | contratos_SECOP → `Departamento` | Categorical (32 departments + Bogotá D.C.) | Gallego et al. (2021): Antioquia, Bogotá, Cundinamarca, Valle. |
| `origen_recursos_cat` | contratos_SECOP → `Origen de los Recursos` | Categorical | Mojica (2021): SGP as predictor. |
| `tiene_justificacion_modalidad` | contratos_SECOP → `Justificacion Modalidad de Contratacion` | Binary: 1 if not null/empty | Fazekas et al. (2016). |

#### Category B: Temporal and Duration Variables

| Feature | Calculation | Evidence |
|---|---|---|
| `dias_firma_a_inicio` | `Contract Start Date` − `Signing Date` | VigIA: top predictor. Negative values (signing after start) = red flag. |
| `duracion_contrato_dias` | `Contract End Date` − `Contract Start Date` | Gallego et al. (2021): top predictor for extensions. |
| `dias_publicidad` | `Bid Closing Date` − `Process Publication Date` | VigIA: predictor for non-professionals. Fazekas & Kocsis (2020). |
| `dias_decision` | `Signing Date` − `Bid Closing Date` | Gallego et al. (2021): "waiting period" as top predictor. |
| `dias_proveedor_registrado` | `Signing Date` − `Provider Registration Date` | VigIA: top predictor. Providers < 228 days = higher risk. |
| `firma_posterior_a_inicio` | Binary: 1 if `dias_firma_a_inicio` < 0 | VigIA: process anomaly. |
| `mes_firma` | month(Signing Date) | Gallego et al. (2021): proximity to elections as predictor. |
| `trimestre_firma` | quarter(Signing Date) | Budget cycle. |
| `dias_a_proxima_eleccion` | Signing Date → days until next presidential election | Gallego et al. (2021): specific predictor for M3. |

**Temporal variables EXCLUDED (only available post-execution):**

```
Fecha de Inicio de Ejecucion
Fecha de Fin de Ejecucion
Pagos de anticipos
Variables derived from execution (start-to-end execution days)
```

#### Category C: Provider Variables

| Feature | Calculation | Evidence |
|---|---|---|
| `tipo_persona_proveedor` | proveedores_registrados → `Tipo de Persona` | Gallego et al. (2021): direct type H (natural persons). |
| `num_contratos_previos` | Count of provider's contracts with earlier signing date | VigIA: base for historial_proveedor_alto in IRIC. |
| `num_ofertas_recibidas` | procesos_SECOP → `Numero de Ofertas Recibidas` | VigIA: predictor for non-professionals. |
| `num_proponentes` | Count in proponentes_proceso_SECOP per process | Actual competition. |
| `proponente_unico` | Binary: 1 if num_proponentes ≤ 1 | Baltrunaite et al. (2020). |
| `num_actividades_economicas` | Count of distinct UNSPSC codes in provider's previous contracts | Base for multipurpose IRIC. |
| `valor_total_contratos_previos` | Sum of values from provider's previous contracts | Volume history. |
| `num_sobrecostos_previos` | Count of previous contracts with value amendments | VigIA: IRIC component + feature. |
| `num_retrasos_previos` | Count of previous contracts with time amendments | VigIA: IRIC component + feature. |


#### Category D: IRIC as Feature

| Feature | Description |
|---|---|
| `iric_score` | Total IRIC (0-1) |
| `iric_competencia` | Competition dimension sub-score (0-1) |
| `iric_transparencia` | Transparency dimension sub-score (0-1) |
| `iric_anomalias` | Anomalies dimension sub-score (0-1) |

### 7.4 Class Imbalance Handling

Each model has a different level of imbalance. **3 strategies per model** are evaluated and the best one is selected based on cross-validation performance:

**Strategy 1: XGBoost's `scale_pos_weight` (first choice)**

Native parameter. Configured as `n_negatives / n_positives`. In Gallego et al. (2021): weight of 25 for Comptroller/Confecámaras, 10 for extensions. Does not modify the data, only the loss function.

**Strategy 2: Up-sampling of the minority class**

Duplicate positive class observations up to target proportion (e.g., 25%). In Gallego et al. (2021): produced slightly better results in MAP@k and NDCG@k than weights.

**Strategy 3: Stratified cross-validation (always mandatory)**

All cross-validation must be stratified. Critical for M3 and M4 where positive class < 2%.

Implementation in `class_balance.py`:

```python
def get_balance_strategies(y_train):
    """Returns list of configurations to evaluate."""
    pos_ratio = y_train.mean()
    strategies = []

    # Strategy 1: scale_pos_weight
    strategies.append({
        "name": "scale_pos_weight",
        "xgb_params": {"scale_pos_weight": (1 - pos_ratio) / pos_ratio},
        "X_train": None,  # use original data
        "y_train": None
    })

    # Strategy 2: up-sampling
    X_up, y_up = upsample_minority(X_train, y_train, target_ratio=0.25)
    strategies.append({
        "name": "upsample_25pct",
        "xgb_params": {},
        "X_train": X_up,
        "y_train": y_up
    })

    return strategies
```

### 7.5 Training and Validation

#### Data Split

- **Train:** 70% of historical contracts with completed execution.
- **Test (hold-out):** Remaining 30%.
- **Cross-validation:** 5-fold stratified on train for hyperparameter optimization.

#### Hyperparameters to Optimize (Random Search)

```python
PARAM_GRID = {
    "max_depth": [3, 5, 7, 9, 11],
    "learning_rate": [0.01, 0.05, 0.1, 0.3],
    "n_estimators": [100, 300, 500, 800, 1000],
    "min_child_weight": [1, 5, 13, 30],
    "colsample_bytree": [0.5, 0.7, 0.85, 1.0],
    "gamma": [0, 1, 5, 10],
    "scale_pos_weight": [calculated_per_model],
}
# Random search: 200 iterations per model (Mojica 2021 evaluated 136K combinations)
```

#### Evaluation Metrics

| Metric | Description | Reference | Role |
|---|---|---|---|
| **AUC-ROC** | Area under ROC curve | VigIA | Primary metric |
| **MAP@100** | Mean average precision at top-100 | Gallego et al. (2021) | "If they investigate the 100 riskiest, how many actually are?" |
| **MAP@1000** | Mean average precision at top-1000 | Gallego et al. (2021) | Larger scale |
| **NDCG@k** | Normalized discounted cumulative gain | Gallego et al. (2021) | Ranking quality |
| **Precision** | TP / (TP + FP) | VigIA | How many flagged are real? |
| **Recall** | TP / (TP + FN) | VigIA | How many real ones were detected? |
| **Brier Score** | Probability calibration | Gallego et al. (2021) | Are the probabilities reliable? |


### 7.6 Explainability: SHAP Values

Each prediction includes SHAP values calculated with TreeSHAP:

```python
import shap

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_contrato)

# For the response: top-N features with highest |SHAP value|
top_features = sorted(
    zip(feature_names, shap_values[0]),
    key=lambda x: abs(x[1]),
    reverse=True
)[:N]
# Example: [("contratacion_directa", +0.15), ("proveedor_responsable_fiscal", +0.12), ...]
```

Interpretation for the user: "This contract has high risk *because*: direct contracting (+0.15), provider with fiscal background records (+0.12), signing after start (+0.10)..."

---

## 8. Composite Risk Index (CRI)

### 8.1 Formula

```
CRI = w1 × P(M1) + w2 × P(M2) + w3 × P(M3) + w4 × P(M4) + w5 × IRIC

Where:
  P(Mi) = predicted probability by model i ∈ [0, 1]
  IRIC  = irregularity index ∈ [0, 1]
  Σ(wi) = 1
  CRI ∈ [0, 1]
```

### 8.2 Initial Weights

```json
{
  "M1_sobrecostos": 0.20,
  "M2_retrasos": 0.20,
  "M3_contraloria": 0.20,
  "M4_multas": 0.20,
  "IRIC": 0.20
}
```

Equal weights (1/5) as baseline configuration. Empirical weight calibration is defined as a future research task. Weights are configurable in `config/model_weights.json` and can be adjusted without retraining models.

### 8.3 Risk Categories

| CRI Range | Category | Color (for frontend) |
|---|---|---|
| 0.00 – 0.20 | Very Low | Green |
| 0.20 – 0.40 | Low | Light Green |
| 0.40 – 0.60 | Medium | Yellow |
| 0.60 – 0.80 | High | Orange |
| 0.80 – 1.00 | Very High | Red |

---


## 9. REST API — Interface Contract with Frontend

### 9.1 Framework

FastAPI. Auto-generated OpenAPI documentation at `/docs`. This documentation serves as the complete specification for the frontend team.

### 9.2 Endpoints

#### `POST /api/v1/analyze` — Individual Contract Analysis

**Request:**
```json
{
  "contract_id": "CO1.PCCNTR.12345"
}
```

**Response:**
```json
{
  "contract_id": "CO1.PCCNTR.12345",

  "contract_summary": {
    "entity_name": "Alcaldía de Bogotá",
    "provider_name": "Empresa XYZ S.A.S",
    "provider_document_type": "NIT",
    "provider_document_number": "900123456",
    "value_cop": 150000000,
    "contract_type": "Servicios profesionales",
    "procurement_method": "Contratación directa",
    "sign_date": "2025-03-15",
    "department": "Bogotá D.C."
  },

  "composite_risk_index": {
    "score": 0.72,
    "category": "Alto",
    "components": {
      "M1_sobrecostos": { "probability": 0.65, "weight": 0.20 },
      "M2_retrasos": { "probability": 0.58, "weight": 0.20 },
      "M3_contraloria": { "probability": 0.82, "weight": 0.20 },
      "M4_multas": { "probability": 0.91, "weight": 0.20 },
      "IRIC": { "score": 0.636, "weight": 0.20 }
    }
  },

  "iric_detail": {
    "score": 0.636,
    "dimensions": {
      "competencia": 0.667,
      "transparencia": 0.500,
      "anomalias": 0.667
    },
    "flags": {
      "unico_proponente": true,
      "proveedor_multiproposito": false,
      "historial_proveedor_alto": true,
      "contratacion_directa": true,
      "regimen_especial": false,
      "periodo_publicidad_extremo": true,
      "datos_faltantes": false,
      "periodo_decision_extremo": true,
      "proveedor_sobrecostos_previos": true,
      "proveedor_retrasos_previos": true,
      "ausencia_proceso": false
    }
  },

  "provider_background": {
    "in_rcac": true,
    "document_type": "NIT",
    "document_number": "900123456",
    "flags": {
      "responsable_fiscal_contraloria": true,
      "sancion_disciplinaria_siri": false,
      "sancion_penal_siri": false,
      "multa_secop_previa": true,
      "colusion_sic": false,
      "monitor_ciudadano": false
    },
    "total_antecedentes": 3,
    "fuentes_distintas": 2,
    "cuantia_dano_fiscal_cop": 45000000,
    "representante_legal": {
      "in_rcac": false,
      "document_type": "CC",
      "num_antecedentes": 0
    }
  },

  "shap_explanation": {
    "M1_sobrecostos": {
      "top_features": [
        { "feature": "log_valor_contrato", "shap_value": 0.18, "actual_value": 18.83 },
        { "feature": "es_contratacion_directa", "shap_value": 0.12, "actual_value": 1 },
        { "feature": "dias_proveedor_registrado", "shap_value": -0.08, "actual_value": 540 },
        { "feature": "iric_score", "shap_value": 0.06, "actual_value": 0.636 },
        { "feature": "proveedor_responsable_fiscal", "shap_value": 0.05, "actual_value": 1 }
      ]
    },
    "M2_retrasos": { "top_features": [] },
    "M3_contraloria": { "top_features": [] },
    "M4_multas": { "top_features": [] }
  },

  "metadata": {
    "model_version": "2025-Q4",
    "rcac_last_updated": "2025-12-01",
    "iric_thresholds_version": "2025-Q4",
    "analysis_timestamp": "2026-02-26T14:30:00Z"
  }
}
```

#### `GET /api/v1/health` — System Status

```json
{
  "status": "healthy",
  "model_version": "2025-Q4",
  "last_training_date": "2025-12-15",
  "rcac_last_updated": "2025-12-01",
  "rcac_total_records": 58432,
  "secop_api_status": "connected",
  "models_loaded": ["M1", "M2", "M3", "M4"]
}
```

#### `POST /api/v1/analyze/batch` — Batch Analysis

**Request:**
```json
{
  "contract_ids": ["id1", "id2", "..."],
  "max_contracts": 1000
}
```

**Response:** Array of objects with the same structure as the individual endpoint.

### 9.3 Frontend Specification (later phase)

The frontend must consume this API. The following are the expected visualizations (as guidance for the frontend team, not part of this backend):

- CRI as main metric (gauge or large number with color).
- Breakdown by model (M1-M4 + IRIC) as radial or bar chart.
- IRIC flags as visual checklist (11 components red/green).
- Provider background (RCAC) as detail section.
- SHAP values as waterfall chart or textual explanation per model.
- Contract data as summary in the header.

The FastAPI OpenAPI documentation (at `/docs`) is the canonical specification.

---

## 10. Tech Stack

### Core Dependencies

| Component | Package | Minimum Version | Purpose |
|---|---|---|---|
| ML | `xgboost` | 2.0+ | Main algorithm × 4 models |
| Explainability | `shap` | 0.43+ | TreeSHAP for SHAP values |
| Data | `pandas` | 2.0+ | Data processing |
| Data | `numpy` | 1.24+ | Numerical operations |
| ML Utils | `scikit-learn` | 1.3+ | StratifiedKFold, RandomizedSearchCV, metrics |
| API | `fastapi` | 0.100+ | REST server |
| API | `uvicorn` | 0.23+ | ASGI server |
| Serialization | `pydantic` | 2.0+ | Request/response schemas |
| HTTP | `httpx` | 0.25+ | Async client for SECOP API |
| ML Serialization | `joblib` | 1.3+ | Save/load .pkl models |
| Testing | `pytest` | 7.0+ | Unit and integration tests |

### Optional Dependencies (offline pipeline)

| Component | Package | Purpose |
|---|---|---|
| Storage | `pyarrow` | Parquet files for batch data |
| Logging | `structlog` | Structured logging |

### RCAC in Production

- **V1 (initial):** 4 trained models, consolidated RCAC, risk index calculations done and .csv document with provider contract history.
- **V2 (frontend-ready):** In-memory Python dict loaded from `rcac.pkl` at server startup.
- **V2 (if it scales):** Redis for distributed lookup. Same `rcac_lookup.py` interface.

---

## 12. Implementation Roadmap

### Phase 1: Data Infrastructure (weeks 1-3)

**Deliverable:** RCAC built and validated. SECOP data downloaded.

| Task | Module | Acceptance Criteria |
|---|---|---|
| SECOP II API Client (Socrata) | `secop_client.py` | Can download all 7 SECOP tables via API. Handles pagination and rate limits. |
| RCAC builder | `rcac_builder.py` | Consolidates 7 sources. Normalizes documents. Deduplicates. Generates `rcac.pkl`. |
| RCAC lookup | `rcac_lookup.py` | Loads `rcac.pkl`. O(1) lookup by (doc_type, doc_number). Legal representative cross-reference. |
| Data tests | `test_rcac.py` | Normalization, deduplication, cross-reference tests. |

### Phase 2: Feature Engineering + IRIC (weeks 4-5)

**Deliverable:** Functional feature pipeline. IRIC calibrated for all historical contracts.

| Task | Module | Acceptance Criteria |
|---|---|---|
| Contract features | `contract_features.py` | Generates all Category A features. |
| Provider features | `provider_features.py` | Generates Category C + D (RCAC) features. |
| Process features | `process_features.py` | Generates competition features (bids, bidders). |
| Temporal features | `temporal_features.py` | Generates Category B features. Calculates dias_a_proxima_eleccion. |
| IRIC | `iric.py` | Calculates 11 components + total score + sub-scores. Uses thresholds from `iric_thresholds.json`. |
| IRIC calibration | `calibrate_iric.py` | Calculates national percentiles by contract type. Generates `iric_thresholds.json`. |
| Orchestrator pipeline | `pipeline.py` | Raw data → complete feature vector (including IRIC as feature). Same code for batch and online. |
| Tests | `test_features.py`, `test_iric.py` | Unit tests for each feature and each IRIC component. |

### Phase 3: Model Training (weeks 6-8)

**Deliverable:** 4 models trained, evaluated, and documented.

| Task | Module | Acceptance Criteria |
|---|---|---|
| Balance strategies | `class_balance.py` | Implements scale_pos_weight and up-sampling. Returns configs to evaluate. |
| Training | `trainer.py` | XGBoost + RandomizedSearchCV + StratifiedKFold(5). 200 iterations. Saves best model .pkl. |
| Evaluation | `evaluation.py` | Calculates AUC, MAP@100, MAP@1000, NDCG@k, Precision, Recall, Brier. Generates JSON report. |
| SHAP | `predictor.py` | TreeExplainer. Returns top-N features with SHAP values. |
| Train M1-M4 | `train_pipeline.py` | 4 models trained. All surpass minimum AUC. Metrics report in .csv file |
| Tests | `test_models.py` | Training, prediction, SHAP tests. |

### Phase 4: Composite Index + API (weeks 9-10)

**Deliverable:** Functional end-to-end API.

| Task | Module | Acceptance Criteria |
|---|---|---|
| Composite index | `composite_index.py` | CRI = Σ(wi × Pi). Categorization by range. Configurable weights. |
| Online inference | `predictor.py` | Loads 4 .pkl models. Receives feature vector. Returns probabilities + SHAP. |
| REST API | `app.py`, `routes.py`, `schemas.py` | POST /analyze returns complete JSON. GET /health functional. POST /analyze/batch functional. |
| API tests | `test_api.py` | End-to-end tests with known contracts. |

### Phase 5: Testing + Validation (weeks 11-12)

**Deliverable:** System tested, documented, ready for frontend.

| Task | Acceptance Criteria |
|---|---|
| Integration tests | Complete pipeline: contract ID → JSON response. |
| Validation with known contracts | Set of contracts with known outcomes produces coherent results. |
| API documentation | Complete OpenAPI docs at /docs. |
| Project README | Setup, training, and deployment instructions. |

--
