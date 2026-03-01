# Phase 3: RCAC Builder - Context

**Gathered:** 2026-03-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the Consolidated Corruption Background Registry (RCAC) from 6 sanction sources: Comptroller bulletins (boletines), SIRI sanctions, fiscal responsibilities (resp. fiscales), SECOP fines (multas), SIC collusion (colusiones), and FGN criminal sanctions. Normalize all document identifiers, deduplicate across sources, serialize to `artifacts/rcac.pkl`, and expose an O(1) lookup interface via `rcac_lookup.py`. RCAC is a build artifact — no model training, no label construction, no feature engineering in this phase.

</domain>

<decisions>
## Implementation Decisions

### Deduplication structure
- One flat row per unique (tipo_doc, num_doc) identity
- Source presence stored as boolean flags: `en_boletines`, `en_siri`, `en_resp_fiscales`, `en_multas_secop`, `en_colusiones`, `en_sanciones_penales`
- `num_fuentes_distintas` = count of distinct sources (not raw rows) — two SIRI entries for the same person counts as 1
- No per-source dates or amounts — boolean flags only
- The `responsabilidades_fiscales_PACO.csv` "Tipo y Num Documento" combined field split failures fall into the malformed path (consistent handling, no special-casing)

### Malformed / invalid identity fields
- Records with unparseable, empty, all-zeros, or structurally invalid document numbers are kept with `tipo_documento = OTRO` and `malformed = True`
- Malformed records are **excluded from the lookup index** — callers querying a bad ID get `None`
- Malformed records are written to a separate bad-rows log file for audit
- Claude defines normalization rules: strip all non-digit characters, reject if result is empty, all-zeros, or fewer than 3 digits in length

### Lookup interface
- `rcac_lookup(tipo_doc, num_doc)` — strict keyed lookup, both arguments required
- Returns `None` for no match (including malformed records)
- Returns the full flat record dict on match, including all source boolean flags (`en_multas_secop`, `en_siri`, etc.) so callers (e.g., Phase 4 M4 label construction) can filter by specific source
- O(1) — backed by a Python dict keyed on (tipo_doc, num_doc)

### Rebuild behavior
- `artifacts/rcac.pkl` is cached — not rebuilt on every pipeline run
- Rebuild triggered via CLI subcommand: `python -m sip_engine build-rcac`
- Default: uses existing `rcac.pkl` if present
- Force rebuild: `python -m sip_engine build-rcac --force`

### Claude's Discretion
- Exact normalization rules for "malformed" threshold (empty, all-zeros, length < 3 after stripping non-digits)
- Bad-rows log file location and format
- Internal merge/concat order across the 6 sources
- SIRI positional column parsing details (cols 5 and 6, no headers — already documented in requirements)

</decisions>

<specifics>
## Specific Ideas

- Phase 4 M4 label construction will filter specifically on `en_multas_secop` — the full record must expose that flag directly
- SIRI file has no headers — must parse by positional columns 5 and 6 (known constraint, already in requirements)
- `responsabilidades_fiscales_PACO.csv` has a combined "Tipo y Num Documento" field that requires splitting before normalization

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-rcac-builder*
*Context gathered: 2026-03-01*
