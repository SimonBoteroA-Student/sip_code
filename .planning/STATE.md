# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-27)

**Core value:** Given any Colombian public contract, reliably flag corruption risk using multiple evidence-backed signals — so oversight actors can prioritize where to investigate.
**Current focus:** Phase 11 — Bug Fixes and Test Cleanup

## Current Position

Phase: 11 of 11 (Bug Fixes and Test Cleanup) — **Complete**
Plan: 1/1 plans complete
Status: IRIC key mismatches fixed (components 3/9/10), test isolation fixed. 375 tests passing.
Last activity: 2026-03-02 — 11-01 (IRIC calculator key fixes + test_models.py isolation)

Progress: [████████████████████] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 10
- Average duration: 3.8 min
- Total execution time: 0.6 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-project-foundation | 2 | 7 min | 3.5 min |
| 02-data-loaders | 2 | 8 min | 4 min |
| 03-rcac-builder | 2 | 6 min | 3 min |
| 04-label-construction | 2 | 7 min | 3.5 min |
| 05-feature-engineering | 3 | 14 min | 4.7 min |
| 06-iric | 3 | 16 min | 5.3 min |

**Recent Trend:**
- Last 5 plans: 4 min, 5 min, 2 min, 5 min, 12 min
- Trend: Stable

*Updated after each plan completion*
| Phase 06-iric P01 | 5 | 2 tasks | 3 files |
| Phase 06-iric P02 | 2 | 1 task | 2 files |
| Phase 06-iric P03 | 12 | 2 tasks | 7 files |
| Phase 07-model-training P02 | 4 | 2 tasks | 4 files |
| Phase 08-evaluation P02 | 3 | 2 tasks | 4 files |
| Phase 09-explainability-cri-and-testing P01 | 9 | 2 tasks | 6 files |
| Phase 09-explainability-cri-and-testing P02 | 7 | 2 tasks | 5 files |
| Phase 11-bug-fixes-and-test-cleanup P01 | 5 | 2 tasks | 3 files |

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
- [04-01]: label_builder imports rcac_builder utilities now — establishes M3/M4 dependency for Plan 04-02
- [04-01]: _build_m1_m2_sets uses set membership isin() for orphan filtering — O(1) lookup per row
- [04-01]: Parquet write deferred to Plan 04-02 — skeleton returns labels_path but doesn't write until M3/M4 columns added
- [04-02]: _build_boletines_set uses iterrows() for per-row normalization — clarity over vectorization (boletines is small)
- [04-02]: M4 passes raw values to rcac_lookup() which normalizes internally — avoids double normalization
- [04-02]: Null trigger is is_malformed(normalized_num) OR original isna() — covers empty string and NaN provider doc inputs
- [05-01]: Parallel sorted arrays per provider (dates/valores/deptos/m1/m2) chosen over list-of-dicts — enables bisect_left on plain list
- [05-01]: bisect_left enforces strict < as_of_date — same-day contracts placed at or after cutoff index, no extra comparison needed
- [05-01]: pd.NA from nullable Int8 labels treated as 0 for M1/M2 counting — pd.isna() check before int() cast prevents TypeError
- [05-01]: Null Fecha de Firma rows logged and skipped (not raised as error) — 7.2% null rate in contratos is expected
- [Phase 05-02]: compute_category_c receives pre-fetched provider_history dict — caller controls lookup, enabling test injection without mocking module-level index cache
- [Phase 05-02]: RARE_THRESHOLD uses strictly-greater-than (freq > threshold) — values at exactly 0.1% treated as rare and grouped into Other
- [05-03]: Procesos lookup built as complete in-memory dict — O(1) per-contract join replaces expensive per-row streaming of 6.4M-row file
- [05-03]: Fecha de Firma injected into procesos_data dict — category_b.compute_category_b uses procesos_data.get("Fecha de Firma") for dias_decision; contract signing date is correct proxy
- [05-03]: category_a NaN-safe coercion — pandas loader returns float NaN for empty CSV fields; (val or '') pattern fails since NaN is truthy
- [06-02]: Zero bids filtered by v > 0 guard before DRN — DRN division-by-zero guard is defensive only; [0, 100, 200, 300] becomes [100, 200, 300] -> DRN=1.0 (not NaN)
- [06-02]: tests written to test_bid_stats.py (not test_iric.py) due to parallel execution — 06-01 owns test_iric.py; no merge conflicts
- [Phase 06-iric]: IRIC components 9/10 return 0 for new providers (not None) — VigIA pattern avoids penalizing new entrants without prior history
- [Phase 06-iric]: calibrate_iric_thresholds accepts arbitrary DataFrame — Phase 7 must recalibrate on train-only data for IRIC-08 leakage prevention
- [Phase 06-iric]: Accent normalization via unicodedata NFD for modality matching — handles Contratacion/Contratación directa variants correctly
- [06-03]: Path existence check before load_iric_thresholds() in build_features() — prevents stale module-level cache hitting wrong path in test isolation
- [06-03]: kurtosis/DRN excluded from FEATURE_COLUMNS — NaN-heavy (~60% direct contracting), stored only in iric_scores.parquet artifact
- [06-03]: Lazy import of iric.pipeline inside features.pipeline function bodies — avoids circular import at module level
- [07-01]: Both imbalance strategies (scale_pos_weight and 25% upsampling) use the same manual ParameterSampler CV loop — consistent comparison; both inject equivalent logic
- [07-01]: Upsampling target: n_target = int(n_maj * 0.25 / 0.75) — achieves 25% minority ratio in upsampled fold training set
- [07-01]: n_jobs parameter reserved but unused in _hp_search — manual loops with upsampling don't parallelize cleanly with joblib
- [07-01]: Strategy tie goes to scale_pos_weight (simpler model, no synthetic data creation)
- [Phase 07-02]: train_model wraps IRIC/encoding recalibration in try/except to prevent training failure in edge-case environments
- [Phase 07-02]: n_splits auto-reduced to max(2, n_pos_train) when M3/M4 positive examples < n_splits to avoid StratifiedKFold error
- [Phase 07-02]: test_data.parquet uses pyarrow preserve_index=True to maintain id_contrato as named index for Phase 8 evaluation
- [08-01]: map_at_k() is public (not private) for direct testability — enables edge case unit tests without mocking
- [08-01]: evaluate_all() recomputes metrics from scratch rather than parsing JSON — avoids report format coupling
- [08-01]: stdlib csv.writer used in _write_csv_report (not pandas) — avoids overhead for simple tabular output
- [Phase 08-evaluation]: feature_columns key in feature_registry.json fixtures — must match evaluator._load_artifacts() lookup
- [Phase 08-evaluation]: XGBoost fixtures trained on pd.DataFrame — preserves feature names for predict_proba compatibility
- [Phase 09-explainability-cri-and-testing]: XGBoost 3.x stores base_score as bracket notation '[2.5E-1]' in UBJSON — fixed via module-level float monkey-patch in shap_explainer.py (_apply_shap_xgboost_compat_patch)
- [Phase 09-explainability-cri-and-testing]: risk_thresholds added to model_weights.json alongside existing 5 weight keys — backward compatible, CRI band tuning requires no code change
- [Phase 09-explainability-cri-and-testing]: compute_features imported at module level in analyzer.py — enables monkeypatch.setattr in tests; safe (no circular imports)
- [Phase 09-explainability-cri-and-testing]: timestamp parameter defaults to UTC now if None — caller freezes it for deterministic JSON output
- [Phase 09-explainability-cri-and-testing]: PROJ-04 gap audit: all 4 criteria covered by existing tests — no new gap tests needed
- [Phase 11]: Use _ZERO_RESULT from provider_history.py as schema template for integration tests — real schema, not synthetic
- [Phase 11]: Patch artifacts_models_dir to tmp_path in test_models.py to prevent early return at model.pkl existence check

### Pending Todos

None yet.

### Blockers/Concerns

- **adiciones.csv status**: RESOLVED — file confirmed available (~4GB). M1/M2 labels complete.
- **SIRI positional columns**: RESOLVED in 02-01 — col[4]=tipo_documento, col[5]=numero_documento verified empirically. usecols=[4,5] is correct.
- **Python 3.14 wheel risk**: RESOLVED — switched to Python 3.12.12 via pyenv (01-01 complete).

## Session Continuity

Last session: 2026-03-02
Stopped at: Completed 11-01 — IRIC key mismatch fix + test isolation. 375 tests passing. Phase 11 complete (v1 milestone).
