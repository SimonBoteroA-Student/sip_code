# Phase 10: Data Leakage Fix - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 10 fixes data correctness issues in the SIP Engine pipeline: (1) `duracion_contrato_dias` leakage from post-amendment end dates, (2) M2 label construction bug (19 positives instead of ~39K), and backs up v1 artifacts. Code fixes only — user runs the full training pipeline afterward.

</domain>

<decisions>
## Implementation Decisions

### Duration Leakage Fix
- **Source change**: Replace `Fecha de Fin del Contrato` minus `Fecha de Inicio del Contrato` with parsed "Duración del contrato" (col 70) text field
- **Parsing**: Convert all formats to days — Dia(s)→days, Mes(es)→×30, Año(s)→×365, Semana(s)→×7, Hora(s)→÷24
- **Month precision**: Use Mes×30 (approximation acceptable for ML features)
- **"No definido" (5.2%)**: Return NaN — XGBoost handles missing values natively
- **Unknown formats**: Log warning + return NaN (don't crash pipeline)
- **Schema change**: Add "Duración del contrato" to CONTRATOS_USECOLS in schemas.py
- **Remove**: Drop "Fecha de Fin del Contrato" from CONTRATOS_USECOLS entirely (prevent accidental re-use)
- **Keep**: "Fecha de Inicio del Contrato" stays — used for non-leaky category_b features (dias_desde_firma_hasta_inicio, es_inicio_rapido)
- **Feature name**: Keep `duracion_contrato_dias` unchanged — downstream consumers (FEATURE_COLUMNS, model training) unaffected
- **Parse location**: category_b.py (which already owns duracion_contrato_dias computation)

### M2 Label Fix (Critical Bug — Absorbed from comparison.md)
- **Bug**: label_builder.py M2_TIPOS only captures "EXTENSION" from adiciones.csv → 19 positives
- **Fix**: Add "Dias adicionados" column from contratos_SECOP.csv as PRIMARY M2 source (OR with existing EXTENSION)
- **Expected result**: ~39,153 M2 positives (11.5%) matching Vigia reference
- **Schema change**: Add "Dias adicionados" to CONTRATOS_USECOLS
- **Provider history cascade**: num_retrasos_previos was always ~0 due to broken M2 labels. After fix, Provider History Index must be rebuilt from scratch. Log as known dependency.

### Contract Value ("Valor del Contrato")
- **Status**: Likely NOT leaky — notebook label logic only makes sense if it's the at-signing value
- **Decision**: Researcher should empirically verify (compare Valor del Contrato for contracts with vs. without value amendments)
- **Contingency**: If confirmed leaky, decide replacement strategy during planning based on research results

### Artifact Versioning
- **Strategy**: Move old artifacts to `artifacts/v1_baseline/` BEFORE running pipeline
- **Scope**: Full snapshot — models + evaluation reports + feature data
- **Git**: Commit v1_baseline to git (permanent record, not gitignored)
- **Timing**: Backup is part of Phase 10 code changes, before user runs pipeline

### Comparison Reporting
- **Format**: Both comparison.md and comparison.json
- **Location**: `artifacts/evaluation/` (alongside new evaluation reports)
- **Metrics**: All Phase 8 metrics (AUC-ROC, MAP@k, NDCG@k, Brier, Precision/Recall) per model
- **Feature importance**: Include top-10 feature importance shift per model (v1 vs v2)
- **Note**: Comparison report will be a template/script — populated after user runs the pipeline

### Pipeline Re-execution Scope
- **Phase 10 does NOT run the pipeline** — code fixes only
- **User runs**: Full pipeline from labels → features → IRIC → train → evaluate → SHAP/CRI
- **HP search**: Same config as v1 (200 iterations, StratifiedKFold 5) for fair comparison
- **Rebuild**: Full from-scratch rebuild (not incremental) due to cascading label→feature→model dependencies

### Claude's Discretion
- Duration parser implementation details (regex patterns, edge case handling)
- Exact structure of comparison report template
- Test updates needed for changed behavior
- Git commit granularity within the phase

</decisions>

<specifics>
## Specific Ideas

### From comparison.md (Critical Reference Document)
- Vigia M2 label: `1 * ((Dias Adicionados != 0) | (Numero_adiciones_extension != 0))` — the OR of two sources
- "Dias Adicionados" is the PRIMARY source (~39K positives); EXTENSION from adiciones is secondary (~391 rows)
- M2 AUC of 0.996 is an artifact of extreme imbalance with 6 test positives — statistically meaningless
- `duracion_contrato_dias` was #1 feature by importance splits — confirms leakage inflated M1 AUC
- Gallego et al. achieved ~0.78 max AUC — current M1 AUC of 0.851 inflated by ~7-15pp from leakage
- P3: `num_retrasos_previos` has circular dependency with M2 labels (was always 0, will become meaningful after fix)
- IRIC key mismatch (Phase 11 scope) NOT absorbed — separate phase

### Duration Column Format Distribution (from empirical analysis)
- "143 Dia(s)": 57.0%
- "3 Mes(es)": 37.3%
- "No definido": 5.2%
- "5 Año(s)": 0.4%
- "6 Semana(s)" / "4 Hora(s)": 0.1%
- Empty: ~0%

</specifics>

<deferred>
## Deferred Ideas

### Missing Vigia Features (Future Phase)
These features were present and important in the Vigia reference notebooks but absent in SIP. Should be considered for a future "Feature Expansion" phase:
- **Es Pyme** — provider attribute, moderately important in Vigia
- **Sector** (entity sector) — `Sector_Cultura` was consistently selected in both M1 and M2 Vigia models
- **Entidad Centralizada** — entity attribute
- **EsPostConflicto** — contract attribute
- **Habilita Pago Adelantado** — contract attribute
- **Es Grupo** — provider attribute (consortium indicator)
- **Mes de Publicacion del Proceso** — temporal (one-hot month of process publication)

### Per-Contract-Type Model Split
Vigia trained separate models for "prestación de servicios" vs. other contract types, showing significant performance differences. SIP uses a single model. Could be a future enhancement.

### IRIC Key Mismatch (Phase 11)
- `calculator.py:332` uses "num_sobrecostos" but provider_history returns "num_sobrecostos_previos"
- `calculator.py:340` uses "num_retrasos" but provider_history returns "num_retrasos_previos"
- Components 9/10 always return 0 — kept in Phase 11 per user decision

</deferred>

---

*Phase: 10-data-leakage-fix*
*Context gathered: 2026-03-02*
