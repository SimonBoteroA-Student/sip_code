# Phase 2: Data Loaders - Context

**Gathered:** 2026-03-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Reusable chunked CSV reader functions for all local SECOP and RCAC source files — handling encoding, dtype casting, column selection, and memory limits. Each downstream phase (RCAC builder, label construction, feature engineering) calls these loaders without worrying about I/O details.

Files in scope: all SECOP CSVs (contratos, procesos, ofertas, proponentes, proveedores, ejecucion, boletines, suspensiones, adiciones) and PACO/RCAC source files (SIRI, responsabilidades_fiscales, fines, SIC, FGN).

</domain>

<decisions>
## Implementation Decisions

### Loader interface
- Generator/iterator pattern — each loader `yield`s DataFrame chunks; callers iterate with `for chunk in load_contratos(): ...`
- `chunk_size` is fixed as a single global default in `Settings` (not configurable per call)
- One dedicated function per source file: `load_contratos()`, `load_ofertas()`, `load_paco_siri()`, etc.
- All loader functions live in a single module: `src/sip_engine/data/loaders.py`

### Column selection
- Each loader hard-codes a narrow `usecols` list — only columns strictly needed by downstream phases
- Column lists are defined in a separate constants/schema file (e.g., `src/sip_engine/data/schemas.py`), not inline in the loader
- Critical dtypes are hard-coded (document IDs as `str`, amounts as `float`, dates as appropriate); pandas infers the rest
- When a downstream phase needs a new column: extend the schema file and update the loader — deliberate, reviewable change

### Error handling
- Bad/unparseable rows: skip the row and log a warning with the file name and row number; pipeline continues
- Missing file (path does not exist): raise `FileNotFoundError` immediately with a clear message
- Missing required column in a file: raise a descriptive error listing the absent column(s) — fail fast
- Encoding errors in PACO/Latin-1 files: `errors='replace'` — undecodable bytes become `\ufffd` placeholder rather than crashing

### Observability
- tqdm progress bar showing chunk count, always on by default (no verbose flag needed)
- After each file finishes: log a one-line summary at `logging.INFO` — rows loaded, bad rows skipped, elapsed time
- Example: `contratos.csv: 12,435,201 rows loaded, 3 rows skipped, 47.2s`

### Claude's Discretion
- Exact tqdm bar format and description string
- Logger name / module hierarchy
- How to compute total chunk count for tqdm (may require a row count pre-scan or just show iteration count)

</decisions>

<specifics>
## Specific Ideas

- SIRI file has no headers — positional column parsing required (columns 5 and 6 by index, not name)
- PACO files use Latin-1 encoding; SECOP files use UTF-8
- ~12 GB total data — chunked processing is mandatory throughout

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-data-loaders*
*Context gathered: 2026-03-01*
