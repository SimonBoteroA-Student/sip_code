# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-27)

**Core value:** Given any Colombian public contract, reliably flag corruption risk using multiple evidence-backed signals — so oversight actors can prioritize where to investigate.
**Current focus:** Phase 3 — RCAC Builder

## Current Position

Phase: 3 of 9 (RCAC Builder) — COMPLETE
Plan: 2 of 2 completed in current phase
Status: Phase 3 complete — RCAC lookup interface, CLI wiring, and package exports implemented. 65 tests passing.
Last activity: 2026-03-01 — Plan 03-02 complete: rcac_lookup.py, build-rcac CLI dispatch, data/__init__.py exports

Progress: [██████░░░░] 33%

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: 3.8 min
- Total execution time: 0.3 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-project-foundation | 2 | 7 min | 3.5 min |
| 02-data-loaders | 2 | 8 min | 4 min |
| 03-rcac-builder | 2 | 6 min | 3 min |

**Recent Trend:**
- Last 5 plans: 5 min, 2 min, 4 min, 4 min, 4 min
- Trend: Fast

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: v1 scope = Models + RCAC (no REST API). REST API is deferred to v2.
- Roadmap: RCAC-derived features explicitly excluded from XGBoost model inputs (FEAT-09).
- Roadmap: IRIC thresholds calibrated on training set only (Phase 6) to prevent test-set leakage.
- Roadmap: Provider History Index precomputed offline (Phase 5) — required before training can begin.
- 01-01: Python 3.12.12 chosen via pyenv (3.14.3 incompatible with XGBoost/SHAP wheels).
- 01-01: XGBoost on macOS ARM requires libomp — installed via `brew install libomp` (system dep, not in pyproject.toml).
- 01-01: Artifact dirs gitignored but .gitkeep files force-tracked to persist scaffold in git.
- 01-02: Path(__file__).resolve() used (not os.getcwd()) — ensures Settings works from any working directory.
- 01-02: SIP_* env var overrides applied in __post_init__ after defaults — partial override supported.
- 01-02: model_weights.json is a committed, user-editable file — CRI weight tuning requires no code change.
- 02-01: Column names verified against actual file headers before writing schema constants (plan had approximate names).
- 02-01: Settings.paco_encoding corrected to 'utf-8' — all 5 PACO files are UTF-8, not Latin-1 (empirically confirmed).
- 02-01: PROCESOS schema includes Respuestas/Proveedores count cols (N_BIDS signal) proactively added for Phase 5.
- [Phase 02-data-loaders]: _load_csv() private helper eliminates code duplication across 14 loaders — each public function is a 3-line wrapper
- [Phase 02-data-loaders]: autouse clear_settings_cache fixture in conftest.py isolates lru_cache singleton per test — enables monkeypatch.setenv(SIP_*) overrides
- [03-01]: normalize_numero uses re.sub(r'[^\d]', '') — strips ALL non-digits including letters (handles "TIA820427KP7" -> "8204277")
- [03-01]: resp_fiscales "Tipo y Num Docuemento" is purely numeric — no type+number splitting needed, just normalize_numero()
- [03-01]: en_sanciones_penales always False in v1 — FGN source has no person-level document IDs
- [03-01]: build_rcac() uses defaultdict(set) keyed on (tipo, num) — set membership ensures duplicate-source rows count as 1 distinct source
- [03-02]: rcac_lookup() normalizes inputs at lookup boundary — callers pass raw strings, normalize_tipo/numero called internally
- [03-02]: Module-level _rcac_index cache with reset_rcac_cache() — lazy loading pattern mirroring get_settings() lru_cache
- [03-02]: is_malformed() checked before index access — short-circuits for empty/all-zero/short numbers without touching index

### Pending Todos

None yet.

### Blockers/Concerns

- **adiciones.csv status**: PROJECT.md notes this file is "(downloading)". M1 and M2 labels (Phase 4) are blocked until this file is available. Confirm download before planning Phase 4.
- **SIRI positional columns**: RESOLVED in 02-01 — col[4]=tipo_documento, col[5]=numero_documento verified empirically. usecols=[4,5] is correct.
- **Python 3.14 wheel risk**: RESOLVED — switched to Python 3.12.12 via pyenv (01-01 complete).

## Session Continuity

Last session: 2026-03-01
Stopped at: Phase 4 context gathered
Resume file: .planning/phases/04-label-construction/04-CONTEXT.md
