# SIP — Intelligent Prediction System for Corruption in Public Procurement

> *Sistema Inteligente de Predicción de Corrupción en Contratación Pública*

A Python machine learning pipeline that detects corruption risk in Colombian public procurement contracts. Given SECOP II contract data, SIP builds a Consolidated Corruption Background Registry (RCAC) from 6 sanction sources, calculates an 11-component Contractual Irregularity Risk Index (IRIC), trains 4 XGBoost classifiers for different corruption indicators, and produces a Composite Risk Index (CRI) with feature-by-feature SHAP explanations.

---

## Table of Contents

- [High-Level Overview](#high-level-overview)
- [Technical Architecture](#technical-architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Windows 10 Support](#windows-10-support)
- [Data Setup](#data-setup)
- [CLI Commands Reference](#cli-commands-reference)
  - [download-data](#0-download-data)
  - [build-rcac](#1-build-rcac)
  - [build-labels](#2-build-labels)
  - [build-features](#3-build-features)
  - [build-iric](#4-build-iric)
  - [train](#5-train)
  - [evaluate](#6-evaluate)
  - [run-pipeline](#7-run-pipeline)
- [End-to-End Workflow](#end-to-end-workflow)
- [Per-Contract Analysis (Python API)](#per-contract-analysis-python-api)
- [Configuration](#configuration)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Models & Methodology](#models--methodology)

---

## High-Level Overview

SIP answers one question: **"How likely is this public contract to involve corruption?"**

It does this by combining five signals into a single Composite Risk Index (CRI):

| Signal | Model | What it detects |
|--------|-------|-----------------|
| **M1** | XGBoost | Probability of cost overruns (value amendments) |
| **M2** | XGBoost | Probability of delays (time amendments) |
| **M3** | XGBoost | Probability the provider appears in Comptroller bulletins (fiscal liability) |
| **M4** | XGBoost | Probability the provider has SECOP fines or sanctions |
| **IRIC** | Rules-based | Contractual Irregularity Risk Index — 11 red-flag binary components |

The CRI is a weighted average of these 5 scores, producing a final value between 0 and 1, classified into risk levels: **Very Low**, **Low**, **Medium**, **High**, or **Very High**.

### Key Design Principles

- **Early detection** — Only pre-execution variables are used as features. No execution dates, payments, or outcomes. This means contracts can be flagged *before* problems manifest.
- **Train-serve parity** — The exact same feature engineering code runs for both offline batch training and per-contract inference.
- **Explainability** — Every prediction comes with TreeSHAP values showing which features contributed most to the risk score.
- **Determinism** — Given the same input, the pipeline produces byte-identical JSON output.

---

## Technical Architecture

```
┌─────────────────── OFFLINE PIPELINE (run once) ───────────────────┐
│                                                                    │
│  CSV Data   →  RCAC Builder  →  Label Builder  →  Feature Pipeline │
│  (33 GB)       (6 sources)      (M1-M4 labels)   (34 features)    │
│                                                                    │
│              →  IRIC Calibration  →  Model Training  →  Evaluation │
│                 (thresholds.json)    (4 XGBoost)       (metrics)   │
└────────────────────────────────────────────────────────────────────┘

┌─────────────────── ONLINE INFERENCE (per contract) ───────────────┐
│                                                                    │
│  Contract  →  compute_features()  →  4x predict_proba()           │
│  (dict)       (same code as        →  TreeSHAP values              │
│               offline pipeline)    →  CRI computation              │
│                                    →  Deterministic JSON output    │
└────────────────────────────────────────────────────────────────────┘
```

### Pipeline Stages (in order)

1. **RCAC Builder** — Reads 6 sanction source CSV files, normalizes document types/numbers, deduplicates, serializes to `rcac.pkl`
2. **Label Builder** — Creates binary labels: M1 from value amendments, M2 from time amendments, M3 from Comptroller bulletins, M4 from RCAC sanctions
3. **Feature Pipeline** — Extracts 34 features across 4 categories (A: contract, B: temporal, C: provider, D: IRIC) with temporal leak prevention
4. **IRIC Calibration** — Computes 11 binary components + kurtosis + DRN anomaly scores; calibrates percentile thresholds by contract type
5. **Model Training** — Trains 4 XGBoost classifiers with hyperparameter optimization (RandomizedSearchCV, 200 iterations, StratifiedKFold-5)
6. **Evaluation** — Computes AUC-ROC, MAP@k, NDCG@k, Precision/Recall at 19 thresholds, Brier Score
7. **Explainability** — TreeSHAP values per prediction, CRI aggregation, risk level classification

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | 3.12.x | 3.14 is incompatible with XGBoost/SHAP wheels |
| **pyenv** | Any | Recommended for managing Python 3.12 |
| **libomp** | Any | Required for XGBoost on macOS ARM (`brew install libomp`) |
| **RAM** | ≥16 GB | Large CSV files processed via chunked reading |
| **Disk** | ~50 GB | ~33 GB SECOP data + ~3 GB RCAC sources + ~14 GB for artifacts |

---

## Installation

```bash
# 1. Clone the repository
git clone <repo-url> "SIP Code"
cd "SIP Code"

# 2. Ensure Python 3.12 is active
pyenv install 3.12.12   # if not installed
pyenv local 3.12.12
python --version         # should show 3.12.x

# 3. Create virtual environment
python -m venv .venv
source .venv/bin/activate

# 4. Install libomp (macOS ARM only — required for XGBoost)
brew install libomp

# 5. Install the project in editable mode with dev dependencies
pip install -e ".[dev]"

# 6. Verify core imports
python -c "import xgboost; import shap; print('OK')"
```

### Windows 10 Support

SIP is fully supported on Windows 10 with Windows Terminal + PowerShell 7.

**Installation:**

```bash
# Install uv (if not already installed)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Clone and install
git clone <repo-url> "SIP Code"
cd "SIP Code"
uv sync --dev
```

**Running:**

```bash
# All commands use uv run
uv run sip-engine --help
uv run sip-engine train --quick
uv run sip-engine run-pipeline --quick
uv run sip-engine download-data --dry-run
```

**Notes:**
- UTF-8 console encoding is configured automatically at startup
- Unicode block characters degrade to ASCII in terminals without UTF-8 support
- CUDA GPU acceleration works with NVIDIA drivers installed
- All tests: `uv run pytest tests/ -v`

---

## Data Setup

SIP expects data in two directories:

### SECOP II Data (`secopDatabases/`)

Download these CSV files automatically from datos.gov.co:

```bash
python -m sip_engine download-data
```

Or place them manually in the `secopDatabases/` directory at the project root:

| File | Description | Approx. Size |
|------|-------------|-------------|
| `contratos_SECOP.csv` | Main contracts table | 9.4 GB |
| `procesos_SECOP.csv` | Procurement processes | 9.8 GB |
| `ofertas_proceso_SECOP.csv` | Bids per process | 7.5 GB |
| `proponentes_proceso_SECOP.csv` | Bidders | 586 MB |
| `proveedores_registrados.csv` | Provider registry | 585 MB |
| `ejecucion_contratos.csv` | Execution data | 926 MB |
| `adiciones.csv` | Amendments (for M1/M2 labels) | 3.9 GB |
| `suspensiones_contratos.csv` | Suspended contracts | 114 MB |
| `rues_personas.csv` | RUES – Personas Naturales, Jurídicas y ESADL (CONFECAMARAS) | 197 MB |
| `boletines.csv` | Comptroller bulletins | 1.3 MB |

### RCAC Sources (`Data/Propia/PACO/`)

Place these CSV files in `Data/Propia/PACO/`:

| File | Description | Size |
|------|-------------|------|
| `sanciones_SIRI_PACO.csv` | SIRI disciplinary/criminal sanctions (46.6K rows, **no headers**) | 19 MB |
| `responsabilidades_fiscales_PACO.csv` | Fiscal responsibilities | 737 KB |
| `multas_SECOP_PACO.csv` | SECOP fines | 580 KB |
| `colusiones_en_contratacion_SIC.csv` | SIC collusion cases | 44 KB |
| `sanciones_penales_FGN.csv` | Criminal sanctions (Attorney General) | 541 KB |

And in `Data/`:

| File | Description | Size |
|------|-------------|------|
| `organized_people_data.csv` | People involved in corruption (PACO) | 12 MB |

### Overriding Data Locations

If your data lives elsewhere, set environment variables **before** running any command:

```bash
export SIP_PROJECT_ROOT="/path/to/project"
export SIP_SECOP_DIR="/path/to/secop/csvs"
export SIP_PACO_DIR="/path/to/paco/csvs"
export SIP_ARTIFACTS_DIR="/path/to/output/artifacts"
```

---

## CLI Commands Reference

All commands are run via:

```bash
python -m sip_engine <command> [options]
```

### 0. `download-data`

**Downloads SECOP II databases from the datos.gov.co open data API.**

```bash
python -m sip_engine download-data [options]
```

| Option | Description |
|--------|-------------|
| `--dataset NAME [...]` | Download specific dataset(s) only (default: all 9). Choices: `contratos`, `procesos`, `ofertas`, `proponentes`, `proveedores`, `ejecucion`, `adiciones`, `suspensiones`, `rues` |
| `--output-dir PATH` | Override output directory (default: `secopDatabases/`) |
| `--parallel N` | Max concurrent downloads (default: 4) |
| `--dry-run` | Show download URLs and file sizes without downloading |
| `--skip-existing` | Skip datasets whose target CSV already exists |
| `--resume` | Resume interrupted downloads from `.part` files |
| `--validate-only` | Only validate existing CSVs against expected column schemas |

**What it does:**
- Downloads 9 SECOP II CSV datasets via the datos.gov.co full export API (total ~33 GB)
- Runs up to 4 parallel curl processes, scheduling largest files first
- Shows live progress with per-file speed, percentage, and ETA
- Uses HTTP/2, compression, and TCP keepalive for throughput
- Includes stall detection (auto-aborts if < 1 KB/s for 60 seconds)
- Writes to `.csv.part` temp files with atomic rename on completion
- On interruption (Ctrl+C), preserves `.part` files — resume with `--resume`
- After download, validates that all required columns from `schemas.py` are present

**datasets and their datos.gov.co identifiers:**

| Dataset | API ID | Approx. Size |
|---------|--------|-------------|
| `contratos` | `jbjy-vk9h` | 9.4 GB |
| `procesos` | `p6dx-8zbt` | 9.8 GB |
| `ofertas` | `wi7w-2nvm` | 7.5 GB |
| `proponentes` | `hgi6-6wh3` | 586 MB |
| `proveedores` | `qmzu-gj57` | 585 MB |
| `ejecucion` | `mfmm-jqmq` | 926 MB |
| `adiciones` | `cb9c-h8sn` | 3.9 GB |
| `suspensiones` | `u99c-7mfm` | 114 MB |
| `rues` | `c82u-588k` | 197 MB |

> **Note:** `boletines.csv` (Comptroller fiscal responsibility bulletins) is not available via the datos.gov.co API — it is manually curated from quarterly PDF bulletins in the `Boletines/` directory.

**Examples:**

```bash
# Download all 9 datasets
python -m sip_engine download-data

# Download only contracts and processes
python -m sip_engine download-data --dataset contratos procesos

# Preview what would be downloaded
python -m sip_engine download-data --dry-run

# Resume after an interrupted download
python -m sip_engine download-data --resume

# Download missing files only, with 2 connections
python -m sip_engine download-data --skip-existing --parallel 2

# Validate column schemas of existing downloads
python -m sip_engine download-data --validate-only
```

---

### 1. `build-rcac`

**Builds the Consolidated Corruption Background Registry from 6 sanction sources.**

```bash
python -m sip_engine build-rcac [--force]
```

| Option | Description |
|--------|-------------|
| `--force` | Rebuild even if `artifacts/rcac/rcac.pkl` already exists |

**What it does:**
- Reads 6 PACO/SECOP source files (Comptroller bulletins, SIRI, fiscal responsibilities, SECOP fines, SIC collusion, FGN criminal sanctions)
- Normalizes document types to `CC`, `NIT`, `CE`, `PASAPORTE`, or `OTRO`
- Normalizes document numbers to digits-only (strips dots, dashes, spaces, NIT check digits)
- Deduplicates records by `(tipo_documento, numero_documento)` with per-source counting
- Serializes to `artifacts/rcac/rcac.pkl`
- Logs malformed/unprocessable rows to `artifacts/rcac/rcac_bad_rows.csv`

**Output:** `artifacts/rcac/rcac.pkl`

---

### 2. `build-labels`

**Constructs binary target labels (M1–M4) for training.**

```bash
python -m sip_engine build-labels [--force]
```

| Option | Description |
|--------|-------------|
| `--force` | Rebuild even if `artifacts/labels/labels.parquet` already exists |

**What it does:**
- **M1** (cost overruns): 1 if contract has ≥1 value amendment in `adiciones.csv`, 0 otherwise
- **M2** (delays): 1 if contract has ≥1 time amendment in `adiciones.csv`, 0 otherwise
- **M3** (Comptroller): 1 if provider appears in Comptroller bulletins as fiscal liability holder
- **M4** (fines): 1 if provider has SECOP fine/sanction in the RCAC

**Requires:** `build-rcac` must have been run first (RCAC is needed for M4).

**Output:** `artifacts/labels/labels.parquet`

---

### 3. `build-features`

**Builds the 34-column feature matrix from contract/process/provider data.**

```bash
python -m sip_engine build-features [--force]
```

| Option | Description |
|--------|-------------|
| `--force` | Rebuild even if `artifacts/features/features.parquet` already exists |

**What it does:**
- Builds the Provider History Index (precomputed per-provider contract history at each point in time)
- Extracts Category A features (contract characteristics: value, type, modality, department, etc.)
- Extracts Category B features (temporal: days to start, duration, publicity period, decision time, etc.)
- Extracts Category C features (provider/competition: prior contracts, bid counts, historical overruns/delays)
- Applies categorical encoding with rare-category grouping (< 0.1% → "Other")
- Enforces temporal leak guard (provider history computed as-of signing date only)
- Excludes all post-execution variables and RCAC-derived features

**Requires:** `build-labels` must have been run first.

**Output:**
- `artifacts/features/features.parquet` — Full feature matrix
- `artifacts/features/provider_history_index.pkl` — Serialized provider history
- `artifacts/features/encoding_mappings.json` — Categorical encoding maps

---

### 4. `build-iric`

**Computes IRIC irregularity risk index scores and calibrates thresholds.**

```bash
python -m sip_engine build-iric [--force]
```

| Option | Description |
|--------|-------------|
| `--force` | Rebuild even if `artifacts/iric/iric_scores.parquet` already exists |

**What it does:**
- Calculates 11 binary red-flag components per contract:
  - **Competition** (6): sole bidder, multipurpose provider, high provider history, direct contracting, special regime, extreme publicity period
  - **Transparency** (2): missing data, extreme decision period
  - **Anomalies** (3): provider prior overruns, provider prior delays, absent process
- Computes bid kurtosis (≥4 bids) and normalized relative difference (≥3 bids)
- Aggregates into `iric_score`, `iric_competencia`, `iric_transparencia`, `iric_anomalias`
- Calibrates national-level percentile thresholds (P1, P5, P95, P99) by contract type using training data only
- Injects IRIC scores as Category D features into the feature matrix

**Requires:** `build-features` must have been run first.

**Output:**
- `artifacts/iric/iric_scores.parquet` — Per-contract IRIC details
- `artifacts/iric/iric_thresholds.json` — Calibrated percentile thresholds

---

### 5. `train`

**Trains XGBoost binary classifiers with hyperparameter optimization.**

```bash
python -m sip_engine train [options]
```

| Option | Description |
|--------|-------------|
| `--model {M1,M2,M3,M4}` | Train a single model (default: all 4) |
| `--force` | Retrain even if model artifacts already exist |
| `--quick` | Fast mode: ~20 HP iterations, 3-fold CV (for testing) |
| `--n-iter N` | Number of HP search iterations (default: 200) |
| `--n-jobs N` | Parallelism level (default: -1 = all cores) |
| `--build-features` | Run the full feature pipeline (rcac → labels → features → iric) before training |
| `--device {cpu,cuda,rocm}` | Force training device (default: auto-detect) |
| `--disable-rocm` | Skip ROCm GPU even if detected |
| `--no-interactive` | Skip interactive config screen, use defaults/CLI args |
| `--no-stats` | Disable live test-set metrics display (MAP@k, Brier, P/R/F1, ROC curve shown by default) |

**What it does:**
- Splits data 70/30 with stratified random sampling (seed=42)
- Evaluates two class imbalance strategies per model:
  1. `scale_pos_weight` (n_neg / n_pos)
  2. 25% minority upsampling
- Runs hyperparameter search: `ParameterSampler` × `StratifiedKFold(5)` for each strategy
- Selects the best strategy and hyperparameters per model
- Refits the final model on the full training set
- Serializes model + feature registry

**Requires:** `build-iric` must have been run first (or use `--build-features` to run the entire upstream pipeline automatically).

**Output per model (M1, M2, M3, M4):**
- `artifacts/models/{M}/model.pkl` — Trained XGBoost classifier
- `artifacts/models/{M}/feature_registry.json` — Exact column names and ordering

**Examples:**

```bash
# Train all 4 models (assumes features already built)
python -m sip_engine train

# Train only M1 in quick mode for testing
python -m sip_engine train --model M1 --quick

# Full pipeline from scratch: build all data, then train
python -m sip_engine train --build-features --force

# Custom HP search with 500 iterations
python -m sip_engine train --n-iter 500 --n-jobs 4

# Force CUDA GPU training, skip interactive config
python -m sip_engine train --device cuda --no-interactive

# Disable live metrics panel (faster refresh, less screen space)
python -m sip_engine train --no-stats
```

---

### 6. `evaluate`

**Evaluates trained models with the full academic metrics suite.**

```bash
python -m sip_engine evaluate [options]
```

| Option | Description |
|--------|-------------|
| `--model {M1,M2,M3,M4}` | Evaluate a single model (default: all 4) |
| `--models-dir PATH` | Override model artifacts directory (default: `artifacts/models`) |
| `--output-dir PATH` | Override evaluation output directory (default: `artifacts/evaluation`) |

**What it does:**
- Computes on the 30% held-out test set:
  - **AUC-ROC** — Primary ranking metric
  - **MAP@100, MAP@500, MAP@1000** — Mean Average Precision at k
  - **NDCG@100, NDCG@500, NDCG@1000** — Normalized Discounted Cumulative Gain
  - **Precision / Recall / F1** at 19 thresholds (0.05 to 0.95)
  - **Brier Score** — Calibration quality
- Generates structured reports per model

**Requires:** `train` must have been run first.

**Output per model:**
- `artifacts/evaluation/{M}_eval.json` — Full metrics, strategy, hyperparameters
- `artifacts/evaluation/{M}_eval.csv` — Tabular metrics
- `artifacts/evaluation/{M}_eval.md` — Human-readable Markdown report
- `artifacts/evaluation/summary.json` — Cross-model comparison (when evaluating all)

---

### 7. `run-pipeline`

**Runs the full SIP pipeline end to end:** `build-rcac` → `build-labels` → `build-features` → `build-iric` → `train` → `evaluate`.

```bash
python -m sip_engine run-pipeline [options]
```

| Option | Description |
|--------|-------------|
| `--model {M1,M2,M3,M4}` | Train and evaluate only this model (features are always built for all) |
| `--quick` | Quick mode: reduced HP search (20 iters, 3-fold CV) |
| `--force` | Rebuild all stages from scratch even if artifacts exist |
| `--n-iter N` | HP search iterations per model (default: 200) |
| `--n-jobs N` | Parallelism level (default: -1 = all cores) |
| `--no-stats` | Disable live test-set metrics display (MAP@k, Brier, P/R/F1, ROC curve shown by default) |

**Examples:**

```bash
# Full pipeline, all models
python -m sip_engine run-pipeline --force

# Quick training for M1 only
python -m sip_engine run-pipeline --model M1 --quick --force
```

---

## End-to-End Workflow

### Quick Start (one command)

The fastest way to go from raw data to trained and evaluated models:

```bash
source .venv/bin/activate
python -m sip_engine run-pipeline --force
```

This runs: `build-rcac` → `build-labels` → `build-features` → `build-iric` → `train` → `evaluate` (all 4 models).

For a single model with quick HP search:

```bash
python -m sip_engine run-pipeline --model M1 --quick --force
```

### Step-by-Step (recommended for first run)

Run each stage separately to monitor progress and catch issues early:

```bash
source .venv/bin/activate

# Step 0: Download SECOP data from datos.gov.co (~15 GB)
python -m sip_engine download-data
# Output: secopDatabases/*.csv

# Step 1: Build the corruption background registry
python -m sip_engine build-rcac
# Output: artifacts/rcac/rcac.pkl

# Step 2: Construct training labels
python -m sip_engine build-labels
# Output: artifacts/labels/labels.parquet

# Step 3: Engineer features
python -m sip_engine build-features
# Output: artifacts/features/features.parquet

# Step 4: Compute IRIC scores and calibrate thresholds
python -m sip_engine build-iric
# Output: artifacts/iric/iric_scores.parquet, iric_thresholds.json

# Step 5: Train all 4 models
python -m sip_engine train
# Output: artifacts/models/{M1,M2,M3,M4}/model.pkl

# Step 6: Evaluate models
python -m sip_engine evaluate
# Output: artifacts/evaluation/{M1,M2,M3,M4}_eval.json
```

### Quick Test Run

To verify everything works without the full 200-iteration HP search:

```bash
python -m sip_engine train --build-features --quick
```

This uses ~20 HP iterations and 3-fold CV instead of 200 iterations and 5-fold CV.

---

## Per-Contract Analysis (Python API)

After training, you can analyze individual contracts programmatically:

```python
import datetime
from sip_engine.classifiers.explainability.analyzer import analyze_contract, serialize_to_json

result = analyze_contract(
    contract_row={
        "Valor del Contrato": 500_000_000,
        "Tipo de Contrato": "Prestación de servicios",
        "Modalidad de Contratacion": "Contratación directa",
        "Departamento": "Bogotá D.C.",
        # ... other contratos columns
    },
    as_of_date=datetime.date(2024, 6, 15),
    procesos_data={"Fecha de Firma": "2024-06-15", ...},
    timestamp="2024-06-15T12:00:00Z",  # frozen for determinism
)

# Result contains:
# - result["cri"]["score"]         → 0.0 – 1.0
# - result["cri"]["level"]         → "Very Low" / "Low" / "Medium" / "High" / "Very High"
# - result["models"]["M1"]["probability"]
# - result["models"]["M1"]["shap_top_features"]
# - result["iric"]["score"]
# - result["iric"]["components"]   → 11 binary flags
# - result["metadata"]["timestamp"]

# Deterministic JSON serialization
json_str = serialize_to_json(result)
```

---

## Configuration

### CRI Weights (`src/sip_engine/config/model_weights.json`)

Controls how the 5 signals are combined into the final CRI score. **Modify this file to tune risk weighting without retraining models:**

```json
{
  "m1_cost_overruns": 0.20,
  "m2_delays": 0.20,
  "m3_comptroller": 0.20,
  "m4_fines": 0.20,
  "iric": 0.20,
  "risk_thresholds": {
    "very_low":  [0.00, 0.20],
    "low":       [0.20, 0.40],
    "medium":    [0.40, 0.60],
    "high":      [0.60, 0.80],
    "very_high": [0.80, 1.00]
  }
}
```

Weights must sum to 1.0. Risk threshold ranges must cover [0, 1] without gaps.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SIP_PROJECT_ROOT` | Auto-detected from source | Project root directory |
| `SIP_SECOP_DIR` | `{project_root}/secopDatabases` | SECOP CSV directory |
| `SIP_PACO_DIR` | `{project_root}/Data/Propia/PACO` | PACO CSV directory |
| `SIP_ARTIFACTS_DIR` | `{project_root}/artifacts` | Output artifacts directory |

### Processing Constants

- **Chunk size**: 50,000 rows per chunk for large CSV reading (configurable in `settings.py`)
- **Encoding**: UTF-8 for all files (with `errors="replace"` fallback)

---

## Docker

```bash
# CPU-only (slim image)
docker build -t sip-engine .
docker run -v $(pwd)/secopDatabases:/app/secopDatabases -v $(pwd)/artifacts:/app/artifacts sip-engine run-pipeline --quick --no-interactive

# CUDA GPU (requires nvidia-docker)
docker build -f Dockerfile.cuda -t sip-engine-cuda .
docker run --gpus all -v $(pwd)/secopDatabases:/app/secopDatabases -v $(pwd)/artifacts:/app/artifacts sip-engine-cuda train --device cuda --no-interactive
```

---

## Testing

```bash
source .venv/bin/activate

# Run all unit tests (349 tests, ~21 seconds)
python -m pytest tests/ -v

# Run tests for a specific module
python -m pytest tests/test_rcac.py -v        # RCAC normalization & lookup
python -m pytest tests/test_labels.py -v      # Label construction
python -m pytest tests/test_features.py -v    # Feature engineering
python -m pytest tests/test_iric.py -v        # IRIC components
python -m pytest tests/test_bid_stats.py -v   # Bid anomaly statistics
python -m pytest tests/test_models.py -v      # Model training
python -m pytest tests/test_evaluation.py -v  # Evaluation metrics
python -m pytest tests/test_explainability.py -v  # SHAP + CRI
python -m pytest tests/test_system.py -v      # Full pipeline system test

# Run with coverage report
python -m pytest tests/ --cov=sip_engine --cov-report=term-missing

# Run the full system test against real data (requires trained models)
python -m pytest tests/test_system.py -v --run-system

# Lint the codebase
python -m ruff check src/ tests/

# Auto-fix lint issues
python -m ruff check src/ tests/ --fix
```

### Test Markers

| Marker | Description |
|--------|-------------|
| `@pytest.mark.system` | Full end-to-end system tests requiring real data artifacts |

---

## Project Structure

```
SIP Code/
├── src/sip_engine/                    # Main package
│   ├── __main__.py                    # CLI entry point
│   ├── compat.py                      # UTF-8 / cross-platform utilities
│   ├── shared/                        # Shared infrastructure (used by all modules)
│   │   ├── config/
│   │   │   ├── settings.py            # Centralized path/encoding configuration
│   │   │   └── model_weights.json     # CRI weights & risk thresholds
│   │   ├── data/
│   │   │   ├── schemas.py             # Column schemas for all 14 CSV files
│   │   │   ├── loaders.py             # Chunked CSV loading (14 generators)
│   │   │   ├── downloader.py          # datos.gov.co parallel download with resume
│   │   │   ├── rcac_builder.py        # RCAC construction & normalization
│   │   │   ├── rcac_lookup.py         # O(1) RCAC lookup by (tipo, numero)
│   │   │   └── label_builder.py       # M1/M2/M3/M4 label construction
│   │   └── hardware/
│   │       ├── detector.py            # GPU/CPU hardware detection
│   │       ├── benchmark.py           # Device benchmarking
│   │       └── device.py              # XGBoost device configuration
│   └── classifiers/                   # XGBoost-based classification models
│       ├── features/
│       │   ├── pipeline.py            # Feature pipeline (batch + per-contract)
│       │   ├── category_a.py          # Contract features
│       │   ├── category_b.py          # Temporal features
│       │   ├── category_c.py          # Provider/competition features
│       │   ├── encoding.py            # Categorical encoding
│       │   └── provider_history.py    # As-of-date provider history index
│       ├── iric/
│       │   ├── calculator.py          # 11 IRIC components + scores
│       │   ├── bid_stats.py           # Kurtosis & DRN anomaly measures
│       │   ├── thresholds.py          # IRIC threshold calibration
│       │   └── pipeline.py            # IRIC calibration & pipeline integration
│       ├── models/
│       │   └── trainer.py             # XGBoost training, HP search, strategy comparison
│       ├── evaluation/
│       │   ├── evaluator.py           # Full metrics suite + report generation
│       │   ├── visualizer.py          # Chart generation (confusion matrix, ROC, etc.)
│       │   └── comparison.py          # V1 vs V2 comparison reports
│       ├── explainability/
│       │   ├── shap_explainer.py      # TreeSHAP value extraction
│       │   ├── cri.py                 # Composite Risk Index computation
│       │   └── analyzer.py            # Per-contract analysis entry point
│       └── ui/
│           ├── config_screen.py       # Interactive training configuration
│           └── progress.py            # Training progress display
├── tests/                             # 433 unit/integration tests
│   ├── classifiers/                   # XGBoost-specific tests
│   └── shared/                        # Shared infrastructure tests
├── artifacts/                         # Generated artifacts (gitignored contents)
│   ├── rcac/                          # rcac.pkl, rcac_bad_rows.csv
│   ├── labels/                        # labels.parquet
│   ├── features/                      # features.parquet, provider_history_index.pkl
│   ├── iric/                          # iric_scores.parquet, iric_thresholds.json
│   ├── models/                        # M1-M4 model.pkl + feature_registry.json
│   ├── evaluation/                    # Per-model eval reports (JSON/CSV/MD)
│   └── shap/                          # SHAP output artifacts
├── secopDatabases/                    # SECOP II CSV data (not committed)
├── data/                              # RCAC source CSVs and reference data
├── pyproject.toml                     # Project metadata & dependencies
└── .planning/                         # GSD planning artifacts
```

---

## Models & Methodology

### Academic Foundation

Based on three key academic works:

- **Gallego, Rivero & Martínez (2021)** — ML models for corruption detection in Colombian procurement. Established feature importance, class imbalance strategies, and evaluation metrics (MAP@k, NDCG@k).
- **VigIA / Salazar, Pérez & Gallego (2024)** — Extended with IRIC, SHAP explainability, and the dual role of IRIC as both descriptive statistic and model feature.
- **Mojica (2021)** — Additional hyperparameter tuning insights.

### The 4 Models

| Model | Target | Label Source | Positive Rate |
|-------|--------|-------------|---------------|
| **M1** | Cost overruns | Value amendments in `adiciones.csv` | Varies |
| **M2** | Delays | Time amendments in `adiciones.csv` | Varies |
| **M3** | Comptroller records | Fiscal liability in Comptroller bulletins | Sparse |
| **M4** | SECOP fines | Sanctions/fines in RCAC | Sparse |

### Feature Categories (34 total)

- **Category A** (10): Contract value, type, modality, department, resource origin, UNSPSC category, etc.
- **Category B** (9): Days to start, duration, publicity period, decision time, provider registration age, election proximity, etc.
- **Category C** (11): Prior contracts, bid counts, bidder uniqueness, provider activities, historical overruns/delays, etc.
- **Category D** (4): IRIC total score + 3 dimension sub-scores (competition, transparency, anomalies)

### IRIC Components (11 binary flags)

| # | Component | Dimension | Rule |
|---|-----------|-----------|------|
| 1 | `unico_proponente` | Competition | Only 1 bidder |
| 2 | `proveedor_multiproposito` | Competition | Provider has diverse UNSPSC segments |
| 3 | `historial_proveedor_alto` | Competition | Provider has abnormally many prior contracts |
| 4 | `contratacion_directa` | Competition | Direct contracting modality |
| 5 | `regimen_especial` | Competition | Special regime contracting |
| 6 | `periodo_publicidad_extremo` | Competition | Extreme publicity period (too short/long) |
| 7 | `datos_faltantes` | Transparency | Missing required data fields |
| 8 | `periodo_decision_extremo` | Transparency | Extreme decision period |
| 9 | `proveedor_sobrecostos_previos` | Anomalies | Provider has prior cost overruns |
| 10 | `proveedor_retrasos_previos` | Anomalies | Provider has prior delays |
| 11 | `ausencia_proceso` | Anomalies | No associated procurement process |

### Bid Anomaly Statistics (Kurtosis & DRN)

In addition to the 11 binary IRIC flags, SIP computes two continuous bid-distribution statistics per procurement process, following the **Imhof (2018)** methodology for detecting bid-rigging patterns. These are stored in `iric_scores.parquet` alongside the IRIC components but are **not** included in the XGBoost feature vector (they are NaN-heavy due to ~60% of contracts using direct contracting with 0–1 bids).

| Statistic | Column Name | Min. Bids | Formula | Interpretation |
|-----------|-------------|-----------|---------|----------------|
| **Kurtosis** | `curtosis_licitacion` | ≥ 4 | Fisher excess kurtosis (unbiased), via `scipy.stats.kurtosis(bids, fisher=True, bias=False)` | Measures "tailedness" of bid distribution. High kurtosis → outlier bids; low/negative kurtosis → uniform clustering (potential coordination). |
| **Normalized Relative Difference (DRN)** | `diferencia_relativa_norm` | ≥ 3 | `(second_lowest - lowest) / lowest` | Measures the relative gap between the two cheapest bids. DRN near 0 → suspiciously tight clustering (bid-rigging signal). Large DRN → healthy price spread. |

**Data pipeline:**
1. `build_bid_stats_lookup()` streams `ofertas_proceso_SECOP.csv` (~6.5M rows), accumulates bid values per process ID, then calls `compute_bid_stats()` for each unique process.
2. NaN and non-positive bid values are filtered out before computation.
3. Results are joined to contracts during `build_iric` and written to `iric_scores.parquet` with columns: `curtosis_licitacion`, `diferencia_relativa_norm`, `n_bids`.

**When values are NaN:**
- Kurtosis: fewer than 4 valid bids, or all bids are identical (zero variance).
- DRN: fewer than 3 valid bids.
- Both: no matching process in `ofertas_proceso_SECOP.csv` (common for direct contracting).

### Class Imbalance Strategy

For each model, both strategies are evaluated via stratified cross-validation:
1. **scale_pos_weight** — XGBoost's built-in class weighting (n_neg / n_pos)
2. **25% minority upsampling** — Resamples minority class to achieve 25% ratio in training folds

The strategy with better CV performance is selected. Ties go to `scale_pos_weight` (simpler).

### Evaluation Metrics

| Metric | Purpose |
|--------|---------|
| AUC-ROC | Overall ranking quality |
| MAP@100, @500, @1000 | Precision in top-k ranked contracts |
| NDCG@100, @500, @1000 | Graded ranking quality |
| Precision/Recall/F1 | At 19 decision thresholds (0.05–0.95) |
| Brier Score | Probability calibration quality |

---

## License

This project is an academic research tool. See repository for license terms.
