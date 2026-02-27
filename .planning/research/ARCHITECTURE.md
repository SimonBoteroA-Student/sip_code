# Architecture Research

**Domain:** ML-based public procurement corruption risk detection (dual-pipeline: offline training + online inference)
**Researched:** 2026-02-27
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          OFFLINE PIPELINE                               │
│  (runs once / periodically; processes ~12 GB of local CSVs)             │
│                                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                │
│  │  Data        │   │  RCAC        │   │  Label       │                │
│  │  Ingestion   │──▶│  Builder     │   │  Constructor │                │
│  │  (SECOP +    │   │  (7+ sanction│   │  (adiciones  │                │
│  │  RCAC CSVs)  │   │  sources)    │   │  → M1/M2)    │                │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘                │
│         │                  │                  │                        │
│         ▼                  ▼                  ▼                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │              Shared Feature Engineering Layer                    │   │
│  │  (Category A: contract, B: temporal, C: provider, D: IRIC)      │   │
│  └─────────────────────────────┬───────────────────────────────────┘   │
│                                │                                       │
│                                ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     Model Training                               │  │
│  │  M1: cost overruns | M2: delays | M3: comptroller | M4: fines   │  │
│  │  XGBoost + scale_pos_weight + RandomizedSearchCV + StratifiedKFold│  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                │                                       │
│                                ▼                                       │
│                    ┌────────────────────┐                              │
│                    │  Artifact Store    │                              │
│                    │  (4 .joblib models │                              │
│                    │  + IRIC thresholds │                              │
│                    │  + RCAC index)     │                              │
│                    └────────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          ONLINE PIPELINE                                │
│  (per-request; contract_id → JSON response)                             │
│                                                                         │
│  [Client] ──POST /analyze──▶  ┌─────────────────────────────────────┐  │
│                               │        FastAPI Application           │  │
│                               │  ┌─────────────────────────────────┐│  │
│                               │  │     SECOP API Client            ││  │
│                               │  │   (Socrata — contract query)    ││  │
│                               │  └───────────────┬─────────────────┘│  │
│                               │                  │                   │  │
│                               │                  ▼                   │  │
│                               │  ┌─────────────────────────────────┐│  │
│                               │  │  Shared Feature Engineering     ││  │
│                               │  │  (same code, single contract)   ││  │
│                               │  └───────────────┬─────────────────┘│  │
│                               │                  │                   │  │
│                               │                  ▼                   │  │
│                               │  ┌─────────────────────────────────┐│  │
│                               │  │  Inference Engine               ││  │
│                               │  │  RCAC lookup + IRIC calc +      ││  │
│                               │  │  4x XGBoost predict + SHAP +    ││  │
│                               │  │  CRI composite score            ││  │
│                               │  └───────────────┬─────────────────┘│  │
│                               │                  │                   │  │
│                               │                  ▼                   │  │
│                               │         JSON Risk Report             │  │
│                               └─────────────────────────────────────┘  │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                     Data Stores (runtime)                          │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │ │
│  │  │ RCAC Index   │  │ Model Files  │  │ IRIC Threshold Tables    │ │ │
│  │  │ (dict/SQLite)│  │ (4x .joblib) │  │ (by contract type)       │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Data Ingestion (offline) | Load all SECOP CSVs + RCAC source files; handle schema quirks (no-header SIRI, Excel Monitor Ciudadano) | `pandas` with chunked reads; `openpyxl` for Excel; custom positional parser for SIRI |
| RCAC Builder | Parse 7+ sanction sources, normalize entity names/document numbers, deduplicate, produce O(1) lookup index keyed by `(doc_type, doc_number)` | In-memory dict or SQLite; built once, serialized to disk |
| Label Constructor | Join contracts with `adiciones.csv` to produce binary M1 (value amendment) and M2 (time amendment) labels per contract | Pandas join/merge on contract ID |
| Shared Feature Engineering | Produce the 30+ feature matrix (Categories A–D including IRIC) from raw contract data; identical logic path for batch and single-contract modes | Pure Python/pandas functions taking a DataFrame row or full DataFrame; IRIC sub-module |
| IRIC Calculator | Compute 11 binary component flags (3 dimensions: competition, transparency, anomalies) + kurtosis + normalized relative difference; calibrate thresholds at national level by contract type | Pandas vectorized ops; threshold tables loaded from disk |
| Model Training | 4x XGBoost binary classifiers with class imbalance handling, RandomizedSearchCV (200 iter), StratifiedKFold(5), evaluation metrics suite | `xgboost`, `scikit-learn`, `joblib` for artifact serialization |
| Inference Engine | Load 4 serialized models + RCAC index + IRIC thresholds on startup; for each request: RCAC lookup, IRIC calc, feature vector, 4x predict_proba, SHAP values, CRI aggregation | `xgboost`, `shap` (TreeSHAP), in-memory model cache |
| SECOP API Client | Query Socrata API for a single contract_id across 7 datasets; normalize response to the same schema as local CSVs | `requests` or `sodapy`; retry/timeout logic |
| FastAPI Application | HTTP routing, request validation, response serialization, startup model loading, health endpoint | `fastapi`, `pydantic` v2 for request/response schemas |
| Artifact Store | Persist trained models, RCAC index, IRIC threshold tables between offline and online phases | Local filesystem; `.joblib` for models, `.json` or `.sqlite` for RCAC/thresholds |

## Recommended Project Structure

```
sip/
├── data_ingestion/             # offline only: loading raw source files
│   ├── secop_loader.py         # bulk CSV readers for all 7 SECOP datasets
│   ├── rcac_sources/           # one module per sanction source
│   │   ├── siri_loader.py      # positional-column SIRI parser (no headers)
│   │   ├── fiscalia_loader.py  # Fiscalia CSV loaders
│   │   ├── sic_loader.py       # SIC collusion cases
│   │   ├── monitor_loader.py   # Monitor Ciudadano Excel files
│   │   ├── boletines_loader.py # Comptroller bulletins CSV
│   │   └── multas_loader.py    # SECOP fines + DatosAbiertos
│   └── label_constructor.py    # adiciones.csv → M1/M2 labels
│
├── rcac/                       # RCAC registry: build + query
│   ├── builder.py              # orchestrates all source loaders → unified index
│   ├── normalizer.py           # name/document normalization, dedup logic
│   ├── registry.py             # RCAC index class with O(1) lookup interface
│   └── schemas.py              # data classes: RCACEntry, LookupKey
│
├── features/                   # shared feature engineering (offline + online)
│   ├── pipeline.py             # orchestrator: takes raw contract dict → feature vector
│   ├── category_a.py           # contract variables (value, type, modality, entity)
│   ├── category_b.py           # temporal/duration variables
│   ├── category_c.py           # provider variables (RCAC lookup results)
│   ├── category_d.py           # IRIC as feature
│   └── iric/
│       ├── calculator.py       # 11-component IRIC calculation
│       ├── thresholds.py       # national threshold calibration by contract type
│       └── schemas.py          # IRICResult data class
│
├── models/                     # training only
│   ├── trainer.py              # orchestrates 4-model training loop
│   ├── evaluator.py            # AUC-ROC, MAP@k, NDCG@k, Brier Score
│   ├── imbalance.py            # scale_pos_weight + up-sampling strategies
│   └── hyperparams.py          # RandomizedSearchCV config (200 iter, param grids)
│
├── inference/                  # online prediction
│   ├── engine.py               # loads artifacts, runs predict_proba + SHAP + CRI
│   ├── cri.py                  # CRI weighted average (configurable weights)
│   ├── explainer.py            # TreeSHAP wrapper, top-N feature extraction
│   └── schemas.py              # RiskReport, IRICDetail, SHAPExplanation output types
│
├── secop_client/               # online only: live API queries
│   ├── client.py               # Socrata API wrapper (7 datasets)
│   ├── normalizer.py           # API response → same schema as local CSV
│   └── config.py               # dataset IDs, endpoint, timeout config
│
├── api/                        # FastAPI application
│   ├── main.py                 # app init, lifespan (model loading on startup)
│   ├── routes/
│   │   ├── analyze.py          # POST /analyze, POST /analyze/batch
│   │   └── health.py           # GET /health
│   ├── schemas/
│   │   ├── request.py          # AnalyzeRequest (contract_id, options)
│   │   └── response.py         # AnalyzeResponse (full JSON risk report)
│   └── dependencies.py         # DI: inject engine, RCAC registry, config
│
├── artifacts/                  # serialized outputs from offline pipeline
│   ├── models/
│   │   ├── m1_cost_overruns.joblib
│   │   ├── m2_delays.joblib
│   │   ├── m3_comptroller.joblib
│   │   └── m4_fines.joblib
│   ├── rcac_index.json         # or rcac_index.sqlite
│   └── iric_thresholds.json    # national thresholds by contract type
│
├── scripts/                    # top-level entry points (CLI)
│   ├── build_rcac.py           # python scripts/build_rcac.py
│   ├── train_models.py         # python scripts/train_models.py
│   └── serve.py                # uvicorn launch wrapper
│
├── config/
│   ├── settings.py             # pydantic-settings: paths, weights, API keys via env
│   └── logging.py              # structured logging config
│
└── tests/
    ├── unit/
    │   ├── test_iric.py
    │   ├── test_features.py
    │   └── test_rcac.py
    └── integration/
        ├── test_offline_pipeline.py
        └── test_api.py
```

### Structure Rationale

- **features/:** The critical shared boundary. Both pipelines import from here; it must have zero dependency on either `models/` (offline) or `secop_client/` (online). This is what makes offline and online predictions numerically identical.
- **rcac/:** Separated from `data_ingestion/` because the registry is a runtime artifact queried during inference, not just an intermediate ETL step. The `registry.py` class is loaded by the inference engine at startup.
- **inference/:** Owns everything that happens at prediction time after features exist: model loading, SHAP, CRI. Depends on `features/` and `artifacts/` but not on `models/` (training code).
- **secop_client/:** Isolated so the online pipeline's data source is swappable without touching feature logic.
- **api/:** Thin routing layer only. Business logic lives in `inference/` and `features/`. Routes call engine methods and return pydantic-serialized responses.
- **artifacts/:** The hand-off point between offline and online. Offline writes here; online reads from here at startup. In cloud deployment this becomes an S3 path or model registry URL.
- **scripts/:** Top-level CLI entry points kept separate from library code. Makes it obvious how to run each pipeline phase.

## Architectural Patterns

### Pattern 1: Shared Feature Transform (Train-Serve Parity)

**What:** A single Python module (or class) is imported by both the offline training pipeline and the online inference engine. It accepts either a full DataFrame (batch) or a single-row dict (online) and returns a feature vector in identical format.

**When to use:** Any system where training data and inference data come from different physical sources (local CSV vs. live API) but must produce the same numerical representation. This is the most important pattern for preventing training-serving skew.

**Trade-offs:** Requires disciplined abstraction of the feature layer. The feature module must not import from training-only or serving-only modules. Adds upfront design cost; eliminates a whole class of production bugs.

**Example:**
```python
# features/pipeline.py
def build_feature_vector(contract: dict, rcac: RCACRegistry, thresholds: IRICThresholds) -> pd.Series:
    """
    Works for both batch (called once per row) and online (called per request).
    Inputs are always normalized to dict format before calling this.
    """
    cat_a = compute_category_a(contract)
    cat_b = compute_category_b(contract)
    cat_c = compute_category_c(contract, rcac)      # RCAC lookup
    iric  = calculate_iric(contract, thresholds)     # IRIC
    cat_d = {"iric_score": iric.score}
    return pd.Series({**cat_a, **cat_b, **cat_c, **cat_d})

# Offline: called inside a df.apply() or chunked loop
# Online:  called with the normalized Socrata API response dict
```

### Pattern 2: Registry-as-Artifact (Build Once, Query at Runtime)

**What:** The RCAC is built offline from 7+ sources into a serialized lookup structure (dict keyed by `(doc_type, doc_number)`) that is loaded into memory at API startup. Lookups are O(1) during inference.

**When to use:** When reference data (sanctions lists, entity records) changes infrequently (e.g., daily/weekly batch refresh) but must be queried on every prediction request. Avoids database round-trips per prediction.

**Trade-offs:** Full registry must fit in memory (acceptable here: 7 sources totaling < 100 MB normalized). Stale data between refreshes — acceptable for v1 where offline rebuild is triggered manually. In production would add a scheduled rebuild + hot-swap.

**Example:**
```python
# rcac/registry.py
class RCACRegistry:
    def __init__(self, index: dict[tuple[str, str], list[RCACEntry]]):
        self._index = index  # key: (doc_type, doc_number)

    def lookup(self, doc_type: str, doc_number: str) -> list[RCACEntry]:
        return self._index.get((doc_type.upper(), doc_number.strip()), [])

    @classmethod
    def from_file(cls, path: Path) -> "RCACRegistry":
        with open(path) as f:
            raw = json.load(f)
        return cls({tuple(k.split("|")): v for k, v in raw.items()})
```

### Pattern 3: Lifespan-Loaded Model Cache (FastAPI Startup)

**What:** Models, RCAC registry, and IRIC thresholds are loaded once at application startup using FastAPI's `lifespan` context manager and injected as dependencies. Per-request inference touches only in-memory objects.

**When to use:** Any ML inference API where model loading is expensive (seconds) but predictions must be fast (milliseconds). Standard pattern for FastAPI + scikit-learn/XGBoost deployments.

**Trade-offs:** Increases startup time; uses steady-state RAM. For 4 XGBoost models the artifact footprint is typically 10–100 MB total — trivially acceptable. Cannot hot-reload models without restart (acceptable for v1).

**Example:**
```python
# api/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load all artifacts once
    app.state.engine = InferenceEngine.from_artifacts(settings.artifacts_dir)
    yield
    # Shutdown: cleanup if needed

app = FastAPI(lifespan=lifespan)
```

### Pattern 4: Chunked Batch Processing for Large CSVs

**What:** SECOP datasets (up to 5.3 GB, 5.1M rows) are never loaded entirely into memory. They are processed in chunks using `pd.read_csv(chunksize=N)` or Polars lazy evaluation, with intermediate results aggregated or written to disk.

**When to use:** Any dataset that exceeds ~2 GB or would cause memory pressure on a development machine. Critical for the offline pipeline on the `procesos_SECOP.csv` (5.3 GB) and `ofertas_proceso_SECOP.csv` (3.4 GB) files.

**Trade-offs:** Increases code complexity for operations that require cross-chunk state (e.g., aggregations). Polars is faster than pandas for this use case but adds a dependency; pandas chunking is simpler to reason about.

**Example:**
```python
# data_ingestion/secop_loader.py
def iter_procesos(path: Path, chunksize: int = 50_000):
    for chunk in pd.read_csv(path, chunksize=chunksize, dtype=SCHEMA_PROCESOS):
        yield preprocess_chunk(chunk)
```

## Data Flow

### Offline Pipeline Flow

```
SECOP CSVs (local, ~12 GB)
    │
    ▼
Data Ingestion (chunked reads, schema normalization)
    │
    ├──────────────────────────────────────────────────┐
    ▼                                                  ▼
RCAC Builder                                   Label Constructor
(7 source loaders → normalize → dedup)        (adiciones.csv → M1, M2 bool per contract)
    │                                                  │
    ▼                                                  │
RCAC Index (serialized)                               │
    │                                                  │
    └─────────────────────┬────────────────────────────┘
                          ▼
              Shared Feature Engineering
              (Category A + B + C [RCAC lookup] + D [IRIC])
                          │
                          ▼
              Training Feature Matrix + Labels (M1/M2/M3/M4)
                          │
                          ▼
              Model Training (4x XGBoost, RandomizedSearchCV)
                          │
                          ▼
              Evaluation (AUC-ROC, MAP@k, NDCG@k, Brier)
                          │
                          ▼
              Artifact Store
              (4x .joblib models + rcac_index + iric_thresholds)
```

### Online Request Flow

```
POST /analyze {"contract_id": "..."}
    │
    ▼
FastAPI route handler
    │
    ▼
SECOP API Client (Socrata query → 7 datasets for this contract_id)
    │
    ▼
Response normalization (same schema as local CSV rows)
    │
    ▼
Shared Feature Engineering (same code as offline; single-row mode)
    │
    ├── RCAC Registry lookup (in-memory, O(1)) → provider background
    └── IRIC Calculator (loaded thresholds) → 11 flags + score
    │
    ▼
Inference Engine
    ├── M1.predict_proba(features) → P(cost overrun)
    ├── M2.predict_proba(features) → P(delay)
    ├── M3.predict_proba(features) → P(comptroller record)
    ├── M4.predict_proba(features) → P(fine)
    └── CRI = weighted_avg(P_M1, P_M2, P_M3, P_M4, IRIC_score)
    │
    ▼
TreeSHAP explainer → top-N features with |SHAP value|
    │
    ▼
JSON Risk Report assembly (contract summary + CRI + IRIC detail + RCAC + SHAP)
    │
    ▼
HTTP 200 JSON response to client
```

### Key Data Flows

1. **RCAC propagation:** Built offline → serialized to `artifacts/rcac_index.json` → loaded at API startup into `RCACRegistry` → queried by `category_c.py` during every feature vector construction (both offline and online). The same registry object serves both pipelines.

2. **IRIC threshold propagation:** Calibrated offline from the full SECOP corpus by contract type → serialized to `artifacts/iric_thresholds.json` → loaded at startup → used by IRIC Calculator in both pipelines. Thresholds must be recalibrated if the training corpus changes significantly.

3. **Feature schema contract:** The output column order of `build_feature_vector()` is fixed at training time (stored in model metadata or a schema file). Online inference must produce features in the identical column order or prediction results will be silently wrong. The shared feature module enforces this.

4. **Label flow (offline only):** `adiciones.csv` is the sole source of M1/M2 labels. M3 labels derive from the `boletines.csv` RCAC source. M4 labels derive from `multas_SECOP_PACO.csv`. Label construction happens after feature engineering so that post-execution label columns cannot leak into the feature matrix.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single researcher (current) | All local; chunked pandas; artifacts on local filesystem; uvicorn single process |
| Small org deployment (< 50 RPS) | Docker container; artifacts in S3 or mounted volume; gunicorn + uvicorn workers |
| Medium org / public API (50–500 RPS) | Horizontally scale FastAPI replicas; shared artifact store (S3/GCS); async SECOP client; Redis cache for recently analyzed contracts |
| High throughput batch | Replace per-request Socrata queries with pre-cached contract store; Celery/Ray for async batch analysis |

### Scaling Priorities

1. **First bottleneck:** Socrata API latency. Each online request requires 7 API calls to SECOP. Mitigation: async HTTP with `httpx` + `asyncio.gather`, contract-level Redis cache (TTL 1 hour), batch endpoint for bulk analysis.
2. **Second bottleneck:** Offline pipeline memory. At 12 GB of source data, `procesos_SECOP.csv` (5.3 GB) will OOM if loaded naively. Mitigation: chunked processing from day one; only join the columns needed for features (column projection at read time).
3. **Third bottleneck (future):** Model staleness. v1 uses static models; as new contracts arrive, model quality drifts. Future: scheduled offline retraining triggered by data freshness thresholds.

## Anti-Patterns

### Anti-Pattern 1: Duplicated Feature Logic (Training-Serving Skew)

**What people do:** Write feature engineering inline in the training notebook, then rewrite it again "more efficiently" in the API handler. The two implementations drift over time.

**Why it's wrong:** Model predictions at inference time will differ from what the model was trained on. This is silent — no error is thrown, but predictions are wrong. Particularly dangerous with IRIC (11 binary flags computed from thresholds) where even a single flag computed differently corrupts the entire feature.

**Do this instead:** A single `features/pipeline.py` module imported by both `scripts/train_models.py` and `api/routes/analyze.py`. The offline trainer calls it on a DataFrame; the API calls it on a single dict. Same code path, zero divergence.

### Anti-Pattern 2: Loading Full CSVs Into Memory

**What people do:** `df = pd.read_csv("procesos_SECOP.csv")` — a 5.3 GB file, causing an OOM crash or extreme slowdown on a development laptop.

**Why it's wrong:** Python + pandas will use 2–5x the raw file size in memory during processing. The full `procesos_SECOP.csv` would require 10–25 GB RAM.

**Do this instead:** `pd.read_csv(path, chunksize=50_000, usecols=REQUIRED_COLS)`. Project only the columns needed for features at read time. Process in chunks. Consider Polars for the larger files (zero-copy, lazy evaluation, column projection at the query level).

### Anti-Pattern 3: Hardcoded Data Paths in Business Logic

**What people do:** `pd.read_csv("/Users/simonb/SIP Code/secopDatabases/contratos_SECOP.csv")` scattered throughout feature and model code.

**Why it's wrong:** Breaks portability — the same code cannot run in Docker, on another machine, or in a future cloud environment without manual edits. Also blocks testability (cannot substitute test fixtures).

**Do this instead:** All paths flow from a `settings.py` (pydantic-settings, reads from environment variables with sensible defaults). Business logic receives paths as arguments or reads from the settings object. Data ingestion modules accept path parameters.

### Anti-Pattern 4: Monolithic Training Script

**What people do:** A single 500-line `train.py` that ingests data, builds RCAC, engineers features, trains all 4 models, evaluates, and saves artifacts in sequence with no modularity.

**Why it's wrong:** Cannot rerun individual steps (e.g., retrain only M3 after fixing a label bug). Cannot test components in isolation. Impossible to parallelize. RCAC rebuild (expensive) happens every training run even when sanction sources haven't changed.

**Do this instead:** Each pipeline stage is an independently runnable script (`build_rcac.py`, `build_features.py`, `train_models.py`) that reads from and writes to the artifact store. Stages are idempotent and can be skipped if their outputs are fresh.

### Anti-Pattern 5: IRIC Thresholds Hardcoded (Bogota-Only)

**What people do:** Copy VigIA's IRIC threshold values directly (calibrated for Bogota contracts) without recalibration on the national SECOP corpus.

**Why it's wrong:** Threshold calibration is corpus-dependent. Bogota contracts skew toward higher values and certain contract types; national thresholds will differ. Using Bogota thresholds on national data will produce systematically biased IRIC scores (and corrupted Category D features).

**Do this instead:** Calibrate thresholds as an explicit offline step from the full `contratos_SECOP.csv` corpus, grouped by contract type. Store calibrated thresholds in `artifacts/iric_thresholds.json`. Both pipelines load from this file.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| SECOP II Socrata API | REST client (requests/sodapy); 7 dataset IDs; per-contract filter query | Rate limits apply; use async HTTP for online pipeline; dataset IDs: contracts (cb9c-h8sn for amendments + primary contract dataset) |
| Boletines PDFs (Comptroller) | Already handled by `extract_boletines.py` → CSV; offline only | pdfplumber extraction already implemented |
| SIRI PACO (no-header CSV) | Positional column parser (already prototyped in `flat_text_to_csv.py`) | 46.6K rows, 19 MB; parse by position, not column names |
| Monitor Ciudadano Excel | `pd.read_excel()` with `openpyxl`; 4 files, 2016–2022 | Offline only; may need sheet-specific parsing |
| IPFS (future) | Report serialization → CID pin; deterministic JSON serialization required | v1 architecture must not block: keep reports as plain serializable dicts |
| Ethereum (future) | CID → on-chain anchor via Web3.py | No v1 dependency; design reports to be deterministic |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `data_ingestion/` → `rcac/` | Direct function call; returns normalized DataFrame | Ingestion modules know nothing about the registry format; builder assembles |
| `rcac/` → `features/` | `RCACRegistry` object passed as dependency | Registry is read-only at feature time; never mutated during inference |
| `features/` → `models/` (offline) | Feature matrix as `pd.DataFrame`; column schema must be pinned | Column order is the contract; store it in `artifacts/feature_schema.json` |
| `features/` → `inference/` (online) | Same `build_feature_vector()` call; returns `pd.Series` matching training schema | This is the critical parity boundary |
| `inference/` → `api/` | `InferenceEngine.analyze(contract_id) -> RiskReport` | Engine encapsulates all ML; API layer only handles HTTP concerns |
| Offline artifact store → Online (startup) | Filesystem read; models + registry + thresholds loaded once | In cloud: S3 path via env var; same interface |

## Build Order (Dependency Graph)

The components must be built in the following order to respect data and code dependencies:

```
Phase 1 — Foundation (no dependencies)
  ├── config/settings.py            (env-based config; everything else imports this)
  ├── rcac/schemas.py               (data classes only)
  └── inference/schemas.py          (response data classes only)

Phase 2 — Data Ingestion
  ├── data_ingestion/secop_loader.py
  └── data_ingestion/rcac_sources/* (one per sanction source)

Phase 3 — RCAC Registry (depends on: ingestion schemas)
  ├── rcac/normalizer.py
  ├── rcac/builder.py
  └── rcac/registry.py             ← serializable artifact produced here

Phase 4 — Feature Engineering (depends on: RCAC registry, IRIC thresholds)
  ├── features/iric/thresholds.py  (calibration from corpus; produces artifact)
  ├── features/iric/calculator.py  (uses thresholds)
  ├── features/category_a.py
  ├── features/category_b.py
  ├── features/category_c.py       (uses RCAC registry)
  ├── features/category_d.py       (uses IRIC calculator)
  └── features/pipeline.py         ← orchestrator; all downstream uses this

Phase 5 — Label Construction (depends on: data ingestion)
  └── data_ingestion/label_constructor.py

Phase 6 — Model Training (depends on: features, labels)
  ├── models/imbalance.py
  ├── models/hyperparams.py
  ├── models/evaluator.py
  └── models/trainer.py            ← produces 4x .joblib model artifacts

Phase 7 — Inference Engine (depends on: features, artifacts)
  ├── inference/cri.py
  ├── inference/explainer.py
  └── inference/engine.py          ← loads artifacts; provides analyze() method

Phase 8 — API (depends on: inference engine, secop client)
  ├── secop_client/client.py
  ├── secop_client/normalizer.py
  ├── api/schemas/*
  ├── api/routes/*
  └── api/main.py                  ← runnable service
```

**Critical path implication:** Feature engineering (Phase 4) must be stable before training (Phase 6), because changing any feature definition after training invalidates all saved models. RCAC (Phase 3) must be complete before Phase 4 because Category C features require the registry. Freeze the feature schema after Phase 6 completes and do not modify `features/` without retraining.

## Sources

- Gallego, Rivero & Martinez (2021) — "Preventing Rather than Punishing: An Early Warning Model of Malfeasance in Public Procurement" — established XGBoost baseline, MAP@k metric, scale_pos_weight=25, feature importance ranking for Colombian SECOP data
- Salazar, Perez & Gallego / VigIA (2024) — extended framework with IRIC (11 components, 3 dimensions), SHAP explainability, IRIC-as-feature dual role; Bogota-calibrated thresholds
- Mojica (2021) — hyperparameter search methodology (136K combinations; RandomizedSearchCV guidance)
- FastAPI documentation — lifespan context manager for startup model loading
- Standard MLOps patterns: train-serve feature parity, registry-as-artifact, artifact store separation (Chip Huyen "Designing Machine Learning Systems", O'Reilly 2022)
- Socrata Open Data API / SECOP II documentation — dataset IDs and query patterns

---
*Architecture research for: ML-based public procurement corruption risk detection (SIP — Sistema Inteligente de Prediccion)*
*Researched: 2026-02-27*
