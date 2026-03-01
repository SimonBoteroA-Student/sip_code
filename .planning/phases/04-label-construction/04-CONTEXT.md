# Phase 4: Label Construction - Context

**Gathered:** 2026-03-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Construct binary target labels (M1, M2, M3, M4) for each contract in the training dataset. Each label uses a specific, independent source. No RCAC-derived features enter the model — RCAC is used only for M4 label lookup. The output is a labeled dataset ready for feature engineering and model training.

</domain>

<decisions>
## Implementation Decisions

### Amendment classification (M1/M2)
- **Explicit tipo only** — no text parsing of `descripcion` column
- M1 (value amendments): tipo in {"Adición en el valor", "Reducción en el valor"}
- M2 (time amendments): tipo in {"Extensión"}
- Combined tipos (e.g., if a tipo mentions both value and time): trigger both M1=1 AND M2=1
- **Discarded tipos**: "Modificación General", "Conclusión", "Suspensión", "No definido", and all others
- Join key: `id_contrato` in adiciones.csv matches CO1.PCCNTR identifier in contratos.csv
- Orphan adiciones rows (id_contrato not in contratos): log count, then ignore
- No amendment match in adiciones → M1=0, M2=0

### M3 source (Comptroller bulletins)
- **Query boletines.csv directly** — RCAC is NOT used for M3 (prevents any data leakage concern)
- Match by provider document number (NIT/CC) from contratos.csv against boletines.csv
- Reuse normalize_tipo() and normalize_numero() from Phase 3 rcac_builder for consistent normalization
- **Blocker**: boletines.csv is currently incomplete — build the full pipeline so it's ready, but document that M3 is not ready for training until the file is updated. Schema will remain the same.
- Static snapshot: all boletines records used regardless of bulletin date (no temporal filtering)

### M4 source (RCAC sanctions)
- Use existing rcac_lookup() from Phase 3 — if it returns a record, M4=1; if None, M4=0
- M4=1 if provider appears in RCAC for ANY reason (any of the 6 sources, not just SECOP fines)
- Static snapshot: full RCAC used as-is, no temporal filtering by sanction date

### Unmatched/missing providers
- Missing provider document number (null/empty) → label = null/NaN (excluded from training for that model)
- Malformed provider ID after normalization (all zeros, too short per is_malformed()) → label = null/NaN
- Missing contract ID (no valid id_contrato to join on) → M1/M2 labels = null/NaN
- Valid provider ID but no match in boletines/RCAC → label = 0 (no evidence of sanctions)

### Diagnostics and logging
- Log summary statistics after building each label: counts of 0, 1, null per model
- Log count of orphan adiciones rows (unmatched id_contrato)
- Log count of null labels due to missing/malformed provider IDs

### Claude's Discretion
- Exact column name mapping between contratos.csv provider fields and boletines.csv document fields (researcher investigates)
- Internal data structures for label storage (DataFrame columns, separate series, etc.)
- How to handle duplicate adiciones rows for the same contract (count once or multiple)
- Schema definition for adiciones.csv loader (if not already in schemas.py)

</decisions>

<specifics>
## Specific Ideas

- Static labels (no temporal cutoff) follow the Gallego et al. (2021) approach — document this explicitly as a known limitation
- Future model versions could explore temporally-filtered labels (only sanctions/amendments before contract signing date) as a refinement
- boletines.csv incomplete status should be clearly logged at runtime (not just in docs) so M3 training doesn't silently produce bad results

</specifics>

<deferred>
## Deferred Ideas

- **Phase 7 train/test split change**: User wants RANDOM 70/30 split, NOT temporal ordering. ROADMAP.md currently says "earliest 70% train, latest 30% test — no shuffling" — this must be updated when planning Phase 7.
- **Temporally-filtered label variants**: Future model versions could filter sanctions/amendments to only those existing before contract signing date. This would create multiple label versions per model for comparison.

</deferred>

---

*Phase: 04-label-construction*
*Context gathered: 2026-03-01*
