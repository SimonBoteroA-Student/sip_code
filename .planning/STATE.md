# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-27)

**Core value:** Given any Colombian public contract, reliably flag corruption risk using multiple evidence-backed signals — so oversight actors can prioritize where to investigate.
**Current focus:** Phase 3 — RCAC Builder

## Current Position

Phase: 3 of 9 (RCAC Builder) — IN PROGRESS
Plan: 1 of 2 completed in current phase
Status: Phase 3 Plan 01 complete — RCAC normalization engine + builder implemented, 34 tests passing.
Last activity: 2026-03-01 — Plan 03-01 complete: rcac_builder.py, normalize_numero/tipo/_infer_tipo, build_rcac()

Progress: [█████░░░░░] 27%

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: 4.3 min
- Total execution time: 0.3 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-project-foundation | 2 | 7 min | 3.5 min |
| 02-data-loaders | 2 | 8 min | 4 min |
| 03-rcac-builder | 1 | 4 min | 4 min |

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

### Pending Todos

None yet.

### Blockers/Concerns

- **adiciones.csv status**: PROJECT.md notes this file is "(downloading)". M1 and M2 labels (Phase 4) are blocked until this file is available. Confirm download before planning Phase 4.
- **SIRI positional columns**: RESOLVED in 02-01 — col[4]=tipo_documento, col[5]=numero_documento verified empirically. usecols=[4,5] is correct.
- **Python 3.14 wheel risk**: RESOLVED — switched to Python 3.12.12 via pyenv (01-01 complete).

## Session Continuity

Last session: 2026-03-01
Stopped at: Completed 03-01-PLAN.md — RCAC normalization engine + build_rcac() implemented, 34 new tests, 59 total passing.
Resume file: .planning/phases/03-rcac-builder/03-01-SUMMARY.md
