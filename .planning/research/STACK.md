# Stack Research

**Domain:** Python ML pipeline for corruption risk prediction in Colombian public procurement
**Researched:** 2026-02-27
**Confidence:** MEDIUM-HIGH (versions confirmed from live venv; XGBoost/SHAP/FastAPI versions from training knowledge cross-referenced against installed packages; WebSearch/WebFetch unavailable in this session)

---

## Critical Pre-Note: Python Version Discrepancy

PROJECT.md states Python 3.12. The actual `.venv` was created with **Python 3.14.3** (`/opt/homebrew/opt/python@3.14/bin`). This research targets 3.14 as the live environment. Package compatibility must be verified against 3.14, which as of February 2026 is recently-released or late-beta. XGBoost and SHAP wheels for 3.14 may require building from source or may not yet be on PyPI. This is the single highest-risk compatibility concern in the stack.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.14.3 (active venv) | Runtime | Already in venv; 3.14 is latest stable. If XGBoost/SHAP wheels aren't available, consider pinning to 3.12 (LTS-stable, universally supported by all ML packages). |
| pandas | 3.0.1 (installed) | Data loading, feature engineering, RCAC registry | Already installed. pandas 3.x enforces Copy-on-Write (CoW) semantics, which eliminates the silent mutation bugs that plagued 1.x/2.x — aligns with multi-pass feature engineering pipelines. Use chunked `read_csv()` for the 5.3 GB `procesos_SECOP.csv`. |
| numpy | 2.4.2 (installed) | Numerical computation, kurtosis, IRIC arithmetic | Already installed. NumPy 2.x drops legacy C-API compatibility but provides better performance. Needed for IRIC kurtosis and normalized-relative-difference calculations. |
| xgboost | >=2.0, recommend 2.1.x | 4 binary classifiers (M1-M4) | Academic literature (Gallego et al., VigIA) mandates XGBoost. XGBoost 2.x provides native `device="cpu"` parameter, improved `scale_pos_weight`, and `HistGradientBoosting`-style `tree_method="hist"` (default, fast for tabular data). `RandomizedSearchCV` from sklearn wraps it natively. **Confidence: MEDIUM** — confirm 3.14 wheel availability on PyPI before committing. |
| scikit-learn | >=1.5, recommend 1.6.x | `RandomizedSearchCV`, `StratifiedKFold`, metrics (AUC-ROC, Precision, Recall), preprocessing | XGBoost's sklearn API is a drop-in estimator. sklearn 1.5+ has a stable `RandomizedSearchCV` with `n_iter=200` and `StratifiedKFold(5)`. Used in VigIA reference implementation. |
| shap | >=0.46, recommend 0.46.x | TreeSHAP values per prediction; top-N feature explanations in CRI response | TreeSHAP is the only correct explainability approach for XGBoost (exact, not approximate). SHAP 0.45+ includes `shap.Explanation` objects that serialize cleanly to JSON for FastAPI responses. `shap.TreeExplainer(model).shap_values(X)` is O(TLD) — fast at inference. **Confidence: MEDIUM** — SHAP has historically lagged Python version support. |
| FastAPI | >=0.115, recommend 0.115.x | REST API: `POST /analyze`, `POST /analyze/batch`, `GET /health` | FastAPI is the 2025 standard for Python ML serving: async-first, Pydantic v2 validation, auto OpenAPI docs at `/docs`, native `JSONResponse` for complex nested responses. Superior to Flask (synchronous, no type hints) and Django (too heavy for pure API). |
| uvicorn | >=0.32, recommend 0.32.x | ASGI server for FastAPI | Standard production ASGI server for FastAPI. `uvicorn[standard]` includes `httptools` and `uvloop` for performance. Use `--workers 1` in v1 (models loaded once at startup). |
| pydantic | v2 (>=2.9) | Request/response schema validation | FastAPI 0.115+ ships with Pydantic v2. Use `BaseModel` for the CRI response schema (contract summary, IRIC breakdown, SHAP values, metadata). Pydantic v2 is 5-50x faster than v1 for validation. |
| joblib | >=1.4 | Model serialization (`.pkl` + compression) | Standard sklearn/XGBoost serialization. VigIA reference uses `joblib.dump()` for both models and scalers. `joblib.dump(model, path, compress=3)` reduces file size ~40%. Use for RCAC dict serialization too. Do NOT use raw `pickle` (no compression, security risk if loading untrusted files). |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| openpyxl | >=3.1 | Read Monitor Ciudadano Excel files (4 .xlsx files, 2016-2022) | Required for `pd.read_excel()`. Use for RCAC source ingestion only. Not needed at inference time. |
| sodapy | >=2.2 | Socrata API client for SECOP II bulk downloads | Used for the SECOP II data client (7 datasets from Socrata). Already in VigIA requirements.txt. Provides authentication + pagination. |
| scipy | >=1.14 | Kurtosis calculation for IRIC anomaly component | `scipy.stats.kurtosis()` for IRIC's anomaly detection sub-component. Also used for statistical thresholds in IRIC calibration. |
| Unidecode | >=1.3 | Text normalization for entity/person name matching in RCAC | Critical for deduplication across RCAC sources — Spanish names have accents; normalize before string comparison. Also in VigIA requirements. |
| python-dotenv | >=1.0 | Environment-based config (no hardcoded paths) | Required for cloud-ready design. Load `DATA_DIR`, `MODEL_DIR`, `SECOP_API_TOKEN` from `.env`. Never hardcode paths in business logic. |
| structlog | >=24.x | Structured JSON logging for API and pipeline | Better than Python's stdlib `logging` for production use. Outputs JSON by default, compatible with log aggregators (CloudWatch, Datadog) when deployed. |
| pytest | >=8.x | Test suite | Standard test runner. Use with `pytest-cov` for coverage. |
| httpx | >=0.27 | FastAPI test client (async-compatible) | `from httpx import AsyncClient` — used with `pytest-asyncio` for testing FastAPI endpoints. Replaces `requests` for async test scenarios. |
| pdfplumber | 0.11.9 (installed) | Parse Boletín PDFs from Comptroller | Already in venv. Used in `extract_boletines.py`. Retain for RCAC ingestion pipeline. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| venv (stdlib) | Virtual environment | Already initialized with Python 3.14.3. Use `pip install -r requirements.txt`. |
| pip | Package management | pip 26.0.1 in venv. Use `pip install --upgrade pip` first. |
| JupyterLab | Exploratory analysis and IRIC calibration | Use for EDA and calibration notebooks (matching VigIA workflow). Do not couple to production pipeline code. |
| black | Code formatting | Standard Python formatter. `black --line-length 100`. |
| ruff | Linting | Replaces flake8 + isort in 2025. Fast Rust-based linter. `ruff check --fix`. |
| mypy | Static typing | Use strict mode for API layer. ML pipeline can be less strict (numpy arrays are hard to type fully). |

---

## Installation

```bash
# Activate existing venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Core ML stack
pip install xgboost>=2.0 scikit-learn>=1.5 shap>=0.46

# API layer
pip install fastapi>=0.115 "uvicorn[standard]>=0.32" pydantic>=2.9

# Data processing
pip install openpyxl>=3.1 sodapy>=2.2 scipy>=1.14 Unidecode>=1.3

# Configuration & observability
pip install python-dotenv>=1.0 structlog>=24.0

# Dev dependencies
pip install pytest>=8.0 httpx>=0.27 pytest-asyncio pytest-cov black ruff mypy

# Serialization (joblib already a sklearn dependency, but pin it)
pip install joblib>=1.4
```

> **Warning:** Before running the above, verify that xgboost and shap publish wheels for Python 3.14 on PyPI. As of February 2026, this may require `pip install --pre` or building from source. If wheels are unavailable, recreate the venv with Python 3.12: `python3.12 -m venv .venv`. Python 3.12 is universally supported by all packages in this stack.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| pandas 3.x (chunked CSV) | Polars | Polars is 3-10x faster for bulk transformations and handles 12 GB comfortably with lazy evaluation. **Use Polars if** pandas chunked processing proves too slow or memory-constrained during feature engineering on `procesos_SECOP.csv` (5.3 GB). Polars is a drop-in replacement for batch processing but requires minor API adjustments. |
| pandas 3.x (chunked CSV) | Dask | Dask adds distributed computing overhead not needed for single-machine 12 GB workloads. Avoid — the complexity cost is not worth it at this scale on a single node. |
| joblib | MLflow model registry | MLflow is appropriate when teams need experiment tracking, model versioning, and a model server. For a single researcher with 4 fixed models in v1, MLflow adds complexity with no benefit. Use plain joblib files in a `models/` directory with a JSON registry manifest. |
| FastAPI | Flask | Flask is synchronous and lacks automatic OpenAPI docs generation. FastAPI is strictly superior for this use case with zero additional complexity. |
| FastAPI | Django REST Framework | Django's ORM, admin, and session management are irrelevant for a stateless ML API. Avoid — excessive boilerplate. |
| uvicorn | gunicorn | gunicorn is WSGI (synchronous). FastAPI is ASGI. Use uvicorn directly for v1. If scaling is needed post-v1, run `gunicorn -k uvicorn.workers.UvicornWorker`. |
| joblib | pickle | pickle has no compression, is not thread-safe for parallel loads, and is a security risk if loading files from untrusted sources. Always use joblib with `compress=3`. |
| structlog | stdlib logging | stdlib logging produces unstructured text; hard to parse in production. structlog adds zero performance overhead and produces JSON by default. |
| scipy.stats.kurtosis | numpy manual | scipy provides the exact formula with bias correction options; don't reimplement. |
| Unidecode | unicodedata | Unidecode handles Spanish-specific transliterations more completely (e.g., "ñ" → "n", accented vowels). Critical for name matching across RCAC sources. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| LightGBM / CatBoost | Academic literature (Gallego et al., VigIA, Mojica) mandates XGBoost. Switching algorithms breaks reproducibility and the methodological claim. | XGBoost 2.x |
| scikit-learn RandomForest (as primary model) | VigIA used RandomForest; SIP replaces this with XGBoost per PROJECT.md requirements. Mixing model types across M1-M4 violates the stated architecture. | XGBoost for all 4 models |
| LIME | LIME provides approximate local explanations via perturbation; TreeSHAP provides exact game-theoretic explanations. For XGBoost, TreeSHAP is always faster and more faithful. LIME is only needed when model is opaque (neural nets). | shap.TreeExplainer |
| Dask | 12 GB on a single machine is well within pandas chunked read capacity. Dask adds distributed orchestration overhead with no single-node benefit. | pandas chunked reads |
| pickle (raw) | No compression; insecure if loading arbitrary files; not thread-safe. | joblib.dump with compress=3 |
| Flask | Synchronous WSGI; no native OpenAPI; no Pydantic validation. FastAPI is strictly superior. | FastAPI |
| MLflow (in v1) | MLflow is for teams needing experiment tracking dashboards and a centralized model registry. Overkill for a solo academic project with 4 fixed models. | joblib files + JSON manifest |
| Polars as primary (v1) | Polars has an excellent API but uses different conventions than pandas (no index, different groupby syntax). The VigIA reference code is all pandas. Using Polars as primary would require rewriting reference logic with no benefit at 12 GB. | pandas 3.x + chunked reads. Adopt Polars only if performance profiling proves pandas inadequate. |
| TensorFlow / PyTorch | The architecture mandates XGBoost for all 4 classifiers — no neural networks. Deep learning frameworks are irrelevant overhead. | XGBoost 2.x |
| Celery / Redis (in v1) | The API spec (`POST /analyze/batch`) is for small batch inference, not job queueing. Celery adds a worker + broker infrastructure not needed at v1 scale. If batch jobs become long-running, add Celery in v2. | Synchronous FastAPI endpoint with response_model streaming |

---

## Stack Patterns by Variant

**If XGBoost wheels are unavailable for Python 3.14:**
- Recreate venv with Python 3.12: `python3.12 -m venv .venv && pip install -r requirements.txt`
- Python 3.12 has universal package support and matches PROJECT.md specification
- No functional difference for this workload

**If 12 GB processing hits memory limits during feature engineering:**
- Switch `pd.read_csv()` to chunked reads: `pd.read_csv(path, chunksize=100_000)`
- Process chunks, aggregate, then join — never load all 7 datasets simultaneously
- If still constrained, adopt Polars lazy API for the heaviest joins (`procesos_SECOP.csv` × `contratos_SECOP.csv`)

**For the RCAC lookup (O(1) access requirement):**
- Build a Python dict keyed by `(doc_type, doc_number)` tuples
- Serialize with `joblib.dump(rcac_dict, "models/rcac_registry.pkl", compress=3)`
- Load once at FastAPI startup via `lifespan` context manager
- Do NOT rebuild RCAC on each request — it's an offline-computed static asset

**For model inference at API time:**
- Load all 4 XGBoost models + RCAC dict at startup (FastAPI `lifespan`)
- Use `xgboost.Booster.predict()` or the sklearn API `.predict_proba()`
- SHAP: create `shap.TreeExplainer` per model at startup — cache explainers as app state
- Return raw float probabilities; compute CRI in the endpoint handler

**For IRIC calibration:**
- Calibration requires national-level histograms by contract type
- Run calibration as a one-time offline script; save thresholds to JSON
- Load threshold JSON at startup; do not recalibrate at inference time

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| xgboost 2.x | scikit-learn 1.5+ | XGBoost 2.x dropped support for sklearn < 1.0 params. Use `n_estimators` not `num_boost_round` in sklearn API. |
| shap 0.46.x | xgboost 2.x | `shap.TreeExplainer` works with both `xgboost.XGBClassifier` (sklearn API) and `xgboost.Booster`. Use sklearn API for `RandomizedSearchCV` training, then extract `.get_booster()` for SHAP if needed. |
| pandas 3.0.x | numpy 2.x | Fully compatible. pandas 3.x requires numpy >= 1.23; numpy 2.x is fully supported. |
| FastAPI 0.115.x | pydantic 2.x | FastAPI 0.100+ requires Pydantic v2. Do NOT use Pydantic v1 — it will conflict with FastAPI internals. |
| Python 3.14 | all above | **UNVERIFIED** — Python 3.14 is very recent. All packages above must publish cp314 wheels or have pure-Python fallbacks. **MEDIUM risk** — test with `pip install xgboost shap` before committing to 3.14. |
| Python 3.12 | all above | **HIGH confidence** — Python 3.12 is universally supported by every package in this stack. Safe fallback. |

---

## Model Serialization Strategy

Use `joblib` for all persistent artifacts. Avoid `pickle` directly. Structure:

```
models/
  m1_cost_overrun.pkl        # XGBClassifier
  m2_delay.pkl               # XGBClassifier
  m3_comptroller.pkl         # XGBClassifier
  m4_secop_fines.pkl         # XGBClassifier
  rcac_registry.pkl          # dict: {(doc_type, doc_num): RCACRecord}
  iric_thresholds.json       # calibration thresholds by contract type
  feature_registry.json      # ordered feature names per model (critical for inference)
```

The `feature_registry.json` is critical: XGBoost predictions are position-sensitive. If the feature column order at inference differs from training, predictions will be silently wrong. Store and enforce column order explicitly.

---

## Sources

- `/Users/simonb/SIP Code/.venv/pyvenv.cfg` — Python 3.14.3 confirmed (live environment)
- `/Users/simonb/SIP Code/.venv/lib/python3.14/site-packages/pandas-3.0.1.dist-info/METADATA` — pandas 3.0.1 confirmed
- `/Users/simonb/SIP Code/.venv/lib/python3.14/site-packages/numpy-2.4.2.dist-info/METADATA` — numpy 2.4.2 confirmed
- `/Users/simonb/SIP Code/data/Vigia/requirements.txt` — VigIA reference stack (shap, joblib, sodapy, openpyxl, Unidecode, scikit-learn, pandas, scipy)
- `/Users/simonb/SIP Code/.planning/PROJECT.md` — project constraints, algorithm mandates, data sizes
- `/Users/simonb/SIP Code/data/Vigia/SECOP_II_models.txt` — VigIA model training patterns (sklearn API, joblib serialization, SHAP TreeExplainer usage)
- Training knowledge (MEDIUM confidence): FastAPI 0.115.x, XGBoost 2.x, SHAP 0.46.x, uvicorn 0.32.x — **unverified against PyPI at research time due to tool restrictions**

---

*Stack research for: SIP — Intelligent Prediction System for Corruption in Colombian Public Procurement*
*Researched: 2026-02-27*
