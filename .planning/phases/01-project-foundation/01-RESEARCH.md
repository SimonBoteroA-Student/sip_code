# Phase 1: Project Foundation — Research

**Phase:** 01-project-foundation
**Researched:** 2026-03-01
**Requirements covered:** PROJ-01, PROJ-02
**Confidence:** HIGH — based on direct inspection of live environment, existing codebase, planning artifacts, and VigIA reference implementation

---

## What This Phase Must Deliver

Python 3.12 environment with XGBoost and SHAP verified working, project directory scaffold in place, and all configuration centralized in `config/settings.py`. Nothing else. No data loading, no business logic, no model code.

Success criteria (hard constraints):
1. `import xgboost; import shap` succeeds in the project venv without errors
2. `config/settings.py` exists with all file paths, API URLs, and encoding constants — no hardcoded paths in business logic
3. `config/model_weights.json` exists with equal CRI weights (0.20 each)
4. Running from any working directory produces the same paths (env-var-based resolution)

---

## Current State of the Environment

### What already exists

**Project root:** `/Users/simonb/SIP Code/`
- No source package yet — greenfield
- Two utility scripts exist in `data/`: `flat_text_to_csv.py`, `extract_boletines.py` (can reference these for path patterns)
- `.venv/` exists but is Python 3.14.3 (wrong version — must be replaced)
- `.gitignore` already present (ignores `.venv/`, `secopDatabases/**`, `Data/**` with code whitelists)
- `.planning/` and `.claude/` are whitelisted in `.gitignore`

**Installed packages in current `.venv` (Python 3.14.3):**
- pandas 3.0.1, numpy 2.4.2, pdfplumber 0.11.9 — these are working
- XGBoost: NOT installed
- SHAP: NOT installed
- scikit-learn: NOT installed
- Everything else needed is absent

**Data files confirmed present (relevant to settings.py paths):**
- `secopDatabases/contratos_SECOP.csv` (570 MB)
- `secopDatabases/procesos_SECOP.csv` (5.3 GB)
- `secopDatabases/ofertas_proceso_SECOP.csv` (3.4 GB)
- `secopDatabases/proponentes_proceso_SECOP.csv` (842 MB)
- `secopDatabases/proveedores_registrados.csv` (564 MB)
- `secopDatabases/ejecucion_contratos.csv` (682 MB)
- `secopDatabases/adiciones.csv` (3.9 GB) — **already downloaded** (blocker resolved)
- `secopDatabases/suspensiones_contratos.csv` (87 MB)
- `secopDatabases/boletines.csv` (1.3 MB)
- `data/Propia/PACO/sanciones_SIRI_PACO.csv` (18 MB)
- `data/Propia/PACO/responsabilidades_fiscales_PACO.csv` (719 KB)
- `data/Propia/PACO/multas_SECOP_PACO.csv` (567 KB)
- `data/Propia/PACO/colusiones_en_contratacion_SIC.csv` (43 KB)
- `data/Propia/PACO/sanciones_penales_FGN.csv` (528 KB)
- `data/organized_people_data.csv` (12 MB)

**RCAC note:** `sanciones_penales_FGN.csv` is in `data/Propia/PACO/` (not `Data/Propia/` — lowercase `data`). Verify exact paths before hardcoding in settings.

### Python version situation

**Problem:** The existing `.venv` was created with Python 3.14.3. XGBoost and SHAP do NOT yet publish cp314 wheels for Python 3.14. This is confirmed by the research files and the fact that neither package is installed. The `.venv` must be deleted and recreated.

**Solution:** Install Python 3.12 via pyenv, then recreate `.venv`.

**pyenv status:**
- pyenv IS available on this machine (confirmed via `pyenv install --list`)
- Python 3.12.x versions available to install: 3.12.10, 3.12.11, 3.12.12
- No Python 3.12 version is currently installed in pyenv (only system Python and Python 3.14 via Homebrew are present)
- `~/.pyenv/versions/` is empty

**Action required:** `pyenv install 3.12.12` (latest stable 3.12), then create `.venv` with it. Add `.python-version` file to lock the project.

---

## Directory Structure Decision

From `01-CONTEXT.md`, the user has decided on a `src/` layout:

```
/Users/simonb/SIP Code/
├── src/
│   └── sip_engine/              # main package
│       ├── __init__.py
│       ├── __main__.py          # entry point: python -m sip_engine <subcommand>
│       ├── config/
│       │   ├── __init__.py
│       │   ├── settings.py      # @dataclass config, SIP_ env vars, all paths
│       │   └── model_weights.json  # CRI weights (committed, user-editable)
│       ├── data/                # loaders (Phases 2-4)
│       │   └── __init__.py
│       ├── features/            # feature engineering (Phase 5)
│       │   └── __init__.py
│       ├── models/              # training (Phase 7)
│       │   └── __init__.py
│       └── iric/               # IRIC calculator (Phase 6)
│           └── __init__.py
├── tests/                       # at project root, not inside src/
│   └── __init__.py
├── artifacts/                   # gitignored, generated outputs
│   ├── models/
│   ├── evaluation/
│   ├── rcac/
│   ├── features/
│   └── iric/
├── pyproject.toml               # single dependency file
├── requirements.lock            # pip freeze output, committed
└── .python-version              # "3.12.12" — pyenv lock
```

**What is NOT created in Phase 1:**
- No submodule implementation files (only `__init__.py` stubs)
- No data loader code
- No feature code
- No test content beyond `__init__.py`

---

## Configuration Design (settings.py)

The user decided: Python `@dataclass` in `config/settings.py`, no Pydantic, `SIP_` prefix for env var overrides, path resolution relative to `PROJECT_ROOT`.

### Key design pattern

```python
import os
from dataclasses import dataclass, field
from pathlib import Path

def _project_root() -> Path:
    """Resolve project root regardless of working directory."""
    return Path(os.environ.get("SIP_PROJECT_ROOT", Path(__file__).parent.parent.parent.parent))
    # __file__ = src/sip_engine/config/settings.py
    # .parent.parent.parent.parent = project root

PROJECT_ROOT = _project_root()

@dataclass
class Settings:
    # Project root
    project_root: Path = field(default_factory=_project_root)

    # Data directories
    secop_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "secopDatabases")
    paco_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "Propia" / "PACO")
    artifacts_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "artifacts")

    # SECOP CSV paths
    contratos_path: Path = ...
    procesos_path: Path = ...
    # ... etc for each file

    # Encodings — per source
    secop_encoding: str = "utf-8"
    paco_encoding: str = "latin-1"

    # Processing
    chunk_size: int = 50_000

    # CRI weights (loaded from model_weights.json at runtime)
    model_weights_path: Path = ...
```

**Critical implementation detail:** `PROJECT_ROOT` must be resolved at import time using `Path(__file__)` — not via `os.getcwd()`, which changes with working directory. The exact file depth from project root depends on the chosen package layout:
- `src/sip_engine/config/settings.py` → 4 `.parent` calls to reach project root
- `SIP_PROJECT_ROOT` env var overrides this for cloud/container deployments

### Env var pattern

Every path that matters should have a corresponding `SIP_*` env var override. The dataclass `__post_init__` method reads env vars and overrides defaults. Example:

```python
def __post_init__(self):
    if env_val := os.environ.get("SIP_SECOP_DIR"):
        self.secop_dir = Path(env_val)
    if env_val := os.environ.get("SIP_ARTIFACTS_DIR"):
        self.artifacts_dir = Path(env_val)
    # etc.
    # Derive file paths from directory paths AFTER env overrides
    self.contratos_path = self.secop_dir / "contratos_SECOP.csv"
    # etc.
```

This means individual file paths don't need their own env vars — only directory roots do.

### What goes in settings.py (complete inventory for Phase 1)

**Paths:**
- `secop_dir`, `paco_dir`, `artifacts_dir`
- Per-file paths for all 9 SECOP CSVs and all 5 PACO CSVs
- `organized_people_path`, `model_weights_path`
- Artifact subdirs: `artifacts_models_dir`, `artifacts_rcac_dir`, `artifacts_features_dir`, `artifacts_iric_dir`, `artifacts_evaluation_dir`

**Encodings (per file):**
- SECOP files: UTF-8
- PACO files: Latin-1 (ISO-8859-1)
- `organized_people_data.csv`: verify encoding (likely UTF-8 but confirm)

**Processing constants:**
- `chunk_size: int = 50_000` (for chunked CSV reading)
- `iric_thresholds_path: Path` (will point to artifacts dir)
- `feature_registry_path: Path` (will point to artifacts dir)

**CRI weights (not in settings.py, in model_weights.json):**
```json
{
  "m1_cost_overruns": 0.20,
  "m2_delays": 0.20,
  "m3_comptroller": 0.20,
  "m4_fines": 0.20,
  "iric": 0.20
}
```

**What is NOT in settings.py in Phase 1 (deferred to later phases):**
- Column name schemas (DATA-07 — Phase 2)
- Dtype specifications (Phase 2)
- IRIC threshold values (Phase 6)
- Socrata API config (v2)
- Model hyperparameter grids (Phase 7)

---

## Dependency Management

### pyproject.toml structure

From `01-CONTEXT.md`: `pyproject.toml` as single dependency file, `pip install -e .`, lock file via `pip freeze`.

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "sip-engine"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pandas>=2.2",
    "numpy>=1.26",
    "xgboost>=2.0",
    "scikit-learn>=1.5",
    "shap>=0.46",
    "scipy>=1.13",
    "joblib>=1.4",
    "Unidecode>=1.3",
    "openpyxl>=3.1",
    "pdfplumber>=0.11",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
    "pytest-cov>=5.0",
]

[project.scripts]
sip-engine = "sip_engine.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
```

**Version guidance:**
- `pandas>=2.2` — pandas 3.x has Copy-on-Write semantics. Research confirmed pandas 3.0.1 was working in the old venv. For Python 3.12, any pandas >=2.2 will install.
- `numpy>=1.26` — NumPy 2.x is fine and will install for 3.12
- `xgboost>=2.0` — XGBoost 2.x confirmed to publish cp312 wheels
- `shap>=0.46` — SHAP 0.45+ works with XGBoost 2.x. For Python 3.12, wheels are available
- Do NOT pin exact versions in pyproject.toml — that is what `requirements.lock` is for

### Lock file

After `pip install -e ".[dev]"`, run `pip freeze > requirements.lock`. This file is committed to git. This gives exact reproducibility without constraining future dependency updates.

### Pitfall: pdfplumber

The current venv has pdfplumber 0.11.9 installed (for `extract_boletines.py`). This should be listed as a dependency in pyproject.toml to ensure it is preserved. It is a runtime dependency (used by the RCAC builder for Boletines PDF parsing, Phase 3).

---

## __main__.py Entry Point Design

From `01-CONTEXT.md`: `python -m sip_engine <subcommand>` pattern. Subcommands are:
- `build-rcac` — Phase 3
- `train --model M1` — Phase 7
- `evaluate --all` — Phase 8
- `run-pipeline` — orchestrates everything

For Phase 1, create a stub `__main__.py` that prints help and shows available subcommands. Actual subcommand implementations come in later phases. Use Python's `argparse` (stdlib — no extra dependencies).

```python
# src/sip_engine/__main__.py
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(
        prog="python -m sip_engine",
        description="SIP — Sistema Inteligente de Prediccion"
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("build-rcac", help="Build RCAC registry from source files")
    subparsers.add_parser("train", help="Train XGBoost models")
    subparsers.add_parser("evaluate", help="Evaluate trained models")
    subparsers.add_parser("run-pipeline", help="Run full pipeline end-to-end")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    print(f"Command '{args.command}' not yet implemented.")

if __name__ == "__main__":
    main()
```

---

## .gitignore Additions Needed

The current `.gitignore` already handles `.venv/`, `secopDatabases/**`, and `Data/**`. Phase 1 must add:

```gitignore
# Generated artifacts (all contents are computed outputs)
artifacts/

# Python build artifacts
*.egg-info/
dist/
build/
__pycache__/
*.pyc
*.pyo
*.pyo

# Lock file is committed — do not ignore
# requirements.lock is tracked

# Environment files (never commit secrets)
.env
.env.*
```

**Note:** `.python-version` must be committed (it locks the pyenv Python version for collaborators). Do NOT add it to `.gitignore`.

---

## Verification Steps (what "done" looks like)

The planner must include explicit verification steps as the final plan step:

1. **Python version check:**
   ```bash
   python --version  # must show Python 3.12.x
   ```

2. **XGBoost and SHAP import:**
   ```bash
   python -c "import xgboost; import shap; print('xgboost', xgboost.__version__, 'shap', shap.__version__)"
   ```

3. **Settings import and path resolution:**
   ```bash
   python -c "from sip_engine.config.settings import Settings; s = Settings(); print(s.contratos_path); assert s.contratos_path.exists()"
   ```
   This test verifies both that settings.py is importable AND that it resolves to a real file.

4. **model_weights.json loads correctly:**
   ```bash
   python -c "import json; from sip_engine.config.settings import Settings; s = Settings(); w = json.loads(s.model_weights_path.read_text()); assert abs(sum(w.values()) - 1.0) < 1e-9, 'weights must sum to 1'"
   ```

5. **Entry point works:**
   ```bash
   python -m sip_engine --help
   ```

6. **Editable install works:**
   ```bash
   pip show sip-engine  # must show package metadata
   ```

---

## Key Risks and Mitigations

### Risk 1: pyenv install time
Installing Python 3.12 via pyenv compiles from source on macOS. This can take 5-10 minutes. Plan step should warn this is expected.

**Mitigation:** Check if Python 3.12 is available from Homebrew as an alternative (`brew install python@3.12`) — this is faster and produces a pre-compiled binary that pyenv can find. Either approach works; pyenv is preferred for future version management.

### Risk 2: XGBoost/SHAP wheel availability for 3.12
This is well-established — Python 3.12 has been out since October 2023 and both packages publish cp312 wheels on PyPI. Confidence HIGH that `pip install xgboost shap` works immediately for 3.12.

**Verification:** `pip install xgboost shap` should complete without any "building from source" warning. If it attempts to build from source, something is wrong.

### Risk 3: Old pdfplumber version compatibility
The current venv has pdfplumber 0.11.9. When reinstalling for Python 3.12, pip will install the latest compatible version. If the API has changed since 0.11.9, `extract_boletines.py` may break.

**Mitigation:** Pin `pdfplumber>=0.11` in pyproject.toml. The existing script is not part of the `sip_engine` package yet, so breakage there does not affect Phase 1 success criteria.

### Risk 4: settings.py path resolution when run from different working directories
If `PROJECT_ROOT` uses `os.getcwd()` instead of `Path(__file__)`, running `python -m sip_engine` from `/tmp/` would break all paths.

**Mitigation:** The `_project_root()` function MUST use `Path(__file__).resolve()` as the anchor, not `os.getcwd()`. The verification step (above) explicitly tests this by checking that `contratos_path.exists()`.

### Risk 5: artifacts/ directory needs to exist before later phases write to it
Creating the directory scaffold in Phase 1 means `artifacts/` must be created. But since it is gitignored (contents only), the directories themselves need to be committed via `.gitkeep` files or created at runtime.

**Mitigation:** Use `.gitkeep` files in each `artifacts/` subdirectory OR create directories in a setup script / via `settings.py`'s `__post_init__` using `mkdir(parents=True, exist_ok=True)`.

---

## What the Planner Needs to Decide

The following questions are left for the planning phase (not answered by research):

1. **pyenv vs. Homebrew for Python 3.12 installation?** Research suggests pyenv (per CONTEXT.md decision), but Homebrew is faster. Either works. The `.python-version` file approach only works with pyenv.

2. **Should `settings.py` call `mkdir()` on artifact directories at import time?** Pros: prevents "directory not found" errors in later phases. Cons: imports have side effects. Alternative: create dirs explicitly in a setup/init script or in each phase's entry point.

3. **`py.typed` marker?** The user left this to Claude's discretion. Recommendation: include it (zero cost, signals the package is typed, enables mypy for consumers).

4. **ruff configuration details?** User left to Claude's discretion. Minimal config: `line-length = 100`, `select = ["E", "F", "I"]` (errors, pyflakes, import sorting). Avoid enabling too many rules in Phase 1 — keep the linting surface small while the codebase is sparse.

5. **Exact `__init__.py` contents for submodules?** User left to Claude's discretion. Recommendation: empty (or single-line docstring) for all except `sip_engine/__init__.py` which should export `__version__ = "0.1.0"`.

---

## Reference: VigIA Stack (for compatibility context)

VigIA (the reference implementation) used Python 3.7 with:
- pandas, numpy, scikit-learn, scipy
- shap, joblib, sodapy, openpyxl, Unidecode
- Flask (not FastAPI — SIP uses a different architecture)
- chardet (useful for encoding detection)

SIP's Phase 1 stack replaces Flask with nothing (API is deferred), upgrades all packages, and uses Python 3.12. The VigIA requirements confirm shap and scikit-learn are core dependencies that must be installed and verified.

---

## Summary: What a Good Plan Must Include

For the planner to produce a solid Phase 1 plan, it must cover these tasks (roughly in order):

1. Install Python 3.12 via pyenv (`pyenv install 3.12.12`)
2. Create `.python-version` file
3. Delete old `.venv` and create new one with Python 3.12
4. Create `pyproject.toml` with all dependencies
5. Install the package in editable mode (`pip install -e ".[dev]"`)
6. Verify XGBoost and SHAP import successfully
7. Create directory scaffold (`src/sip_engine/` with all submodule stubs, `tests/`, `artifacts/` with `.gitkeep`)
8. Create `src/sip_engine/__init__.py` (version), `__main__.py` (entry point stub)
9. Create `src/sip_engine/config/__init__.py` and `settings.py` with full path/encoding/constant inventory
10. Create `config/model_weights.json` with equal 0.20 weights
11. Update `.gitignore` for `artifacts/` and Python build artifacts
12. Generate `requirements.lock` via `pip freeze`
13. Run all 6 verification checks listed above
14. Commit everything to git

---

*Phase: 01-project-foundation*
*Research completed: 2026-03-01*
