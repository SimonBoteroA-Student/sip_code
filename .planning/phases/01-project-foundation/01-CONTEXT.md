# Phase 1: Project Foundation - Context

**Gathered:** 2026-03-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Python 3.12 environment with XGBoost and SHAP confirmed working, project directory scaffold created, and all configuration (paths, API endpoints, encoding constants) centralized in `config/settings.py`. This phase delivers the foundation — no data loading, no business logic, no model code.

</domain>

<decisions>
## Implementation Decisions

### Directory Structure
- **src/ layout**: `src/sip_engine/` package inside `src/` directory
- Package name: `sip_engine` (avoids conflict with Python's Qt `sip` module)
- Submodules: `config/`, `data/`, `features/`, `models/`, `iric/`
- `tests/` at project root (not inside src/)
- Single `artifacts/` directory at project root with subdirs: `models/`, `evaluation/`, `rcac/`, `features/`, `iric/` — gitignored since all contents are generated
- `secopDatabases/` and `Data/` remain at their current locations
- Module entry point: `python -m sip_engine <subcommand>` for running pipeline steps independently

### Configuration Approach
- Python `@dataclass` in `config/settings.py` — no extra dependencies (no Pydantic)
- Environment variable overrides with `SIP_` prefix for cloud deployment
- Path resolution: relative to `PROJECT_ROOT` by default, overridable via `SIP_*` env vars
- `config/model_weights.json` lives in `config/` (committed to git, user-editable CRI weights)
- **Centralized file schemas**: all CSV column names, dtypes, and per-file encoding defined in `settings.py` (not scattered across loaders)

### Python Version Strategy
- Install Python 3.12 via `pyenv`, create new venv with `python -m venv .venv`
- Remove the existing project 3.14.3 venv (`.venv` only — **never touch global Python installations**)
- `.python-version` file locks pyenv to 3.12

### Dependency Management
- `pyproject.toml` as the single dependency declaration file
- `pip install -e .` for development
- Lock file (`requirements.lock` via `pip freeze`) committed to git for exact reproducibility
- `[project.optional-dependencies]` for dev tools (pytest, ruff)

### Claude's Discretion
- Exact submodule `__init__.py` contents
- `.gitignore` structure for artifacts and data directories
- Specific ruff configuration
- Whether to include a `py.typed` marker

</decisions>

<specifics>
## Specific Ideas

- Entry point should support subcommands like `build-rcac`, `train --model M1`, `evaluate --all`, `run-pipeline`
- Settings dataclass should have sensible defaults that work on the developer's machine without any env vars set
- CHUNK_SIZE default of 50,000 rows for chunked CSV processing

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-project-foundation*
*Context gathered: 2026-03-01*
