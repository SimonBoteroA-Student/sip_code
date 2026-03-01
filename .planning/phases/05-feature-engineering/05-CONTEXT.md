# Phase 5: Feature Engineering - Context

**Gathered:** 2026-03-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Shared feature pipeline (`features/pipeline.py`) producing a complete, correctly ordered feature vector for any contract. Categories A (contract), B (temporal), and C (provider/competition) features. Enforces temporal leak guard (FEAT-05), excludes post-execution variables (FEAT-08) and RCAC-derived inputs (FEAT-09). Train-serve parity (FEAT-07). Provider History Index precomputed offline (FEAT-06). Low-frequency categorical grouping (FEAT-10).

IRIC features (Category D / FEAT-04) are Phase 6 — not in scope here.

</domain>

<decisions>
## Implementation Decisions

### Missing data strategy
- Drop rows missing ANY of: signing date, contract value, tipo_contrato, modalidad_contratacion — these are critical fields
- Non-critical missing fields (department, num_ofertas, etc.) remain as NaN — XGBoost handles NaN natively and learns optimal split direction
- Log a summary of dropped rows at INFO level: counts per reason (e.g., "missing signing date: N, missing value: M")
- No imputation, no sentinel values

### Election calendar for temporal features
- Hardcoded constant list of Colombian election dates covering 2010–2026
- Claude's discretion on which election types to include (presidential, congressional, local/regional) — research Gallego et al. and Colombian political cycles
- Feature measures distance to NEXT election only (dias_a_proxima_eleccion) — no backward-looking "days since last election"
- Calendar is a static Python constant, not an external file

### Provider history scope
- **Two scopes as separate features**: national history (all SECOP) AND departmental history (same department as the contract)
- This doubles the provider history features: `num_contratos_previos_nacional`, `num_contratos_previos_depto`, `valor_total_contratos_previos_nacional`, `valor_total_contratos_previos_depto`, etc.
- First-time providers (no prior contracts) get all zeros — explicitly "no history", not null
- `num_sobrecostos_previos` and `num_retrasos_previos` are derived from M1/M2 labels (Phase 4 output) — a prior contract with M1=1 counts as one sobrecosto
- Full temporal Provider History Index precomputed: cumulative counts stored at each contract date, enabling exact as-of lookups for any signing date

### Categorical encoding
- Label encoding (integer codes) — XGBoost handles this natively, no feature explosion
- Alphabetical ordering for deterministic mapping (category → integer)
- 0.1% frequency threshold (FEAT-10) computed from **training data only** — prevents test-set leakage
- Encoding mappings serialized to `artifacts/features/encoding_mappings.json` for train-serve parity (FEAT-07)
- At inference time, unseen categories map to "Other"

### Claude's Discretion
- Which Colombian election types to include in the calendar (after researching Gallego et al. approach)
- Exact Provider History Index data structure and serialization format
- Pipeline internal architecture (how categories A/B/C are organized in code)
- Feature column ordering convention

</decisions>

<specifics>
## Specific Ideas

- Provider history at both national and departmental level is a deliberate enrichment over the base requirements — model gets both macro and local signals
- M1/M2 labels reused for sobrecostos/retrasos history keeps the system internally consistent — no separate counting logic
- Training-only threshold for rare categories aligns with the project's strict anti-leakage philosophy (same as IRIC thresholds in Phase 6)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-feature-engineering*
*Context gathered: 2026-03-01*
