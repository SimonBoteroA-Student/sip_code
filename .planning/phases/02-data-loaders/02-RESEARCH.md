# Phase 2: Data Loaders — Research

**Researched:** 2026-03-01
**Domain:** Pandas chunked CSV I/O, encoding detection, generator patterns, tqdm progress
**Confidence:** HIGH — all findings verified against actual project files and live pandas 3.0.1

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Loader interface**
- Generator/iterator pattern — each loader `yield`s DataFrame chunks; callers iterate with `for chunk in load_contratos(): ...`
- `chunk_size` is fixed as a single global default in `Settings` (not configurable per call)
- One dedicated function per source file: `load_contratos()`, `load_ofertas()`, `load_paco_siri()`, etc.
- All loader functions live in a single module: `src/sip_engine/data/loaders.py`

**Column selection**
- Each loader hard-codes a narrow `usecols` list — only columns strictly needed by downstream phases
- Column lists are defined in a separate constants/schema file (e.g., `src/sip_engine/data/schemas.py`), not inline in the loader
- Critical dtypes are hard-coded (document IDs as `str`, amounts as `float`, dates as appropriate); pandas infers the rest
- When a downstream phase needs a new column: extend the schema file and update the loader — deliberate, reviewable change

**Error handling**
- Bad/unparseable rows: skip the row and log a warning with the file name and row number; pipeline continues
- Missing file (path does not exist): raise `FileNotFoundError` immediately with a clear message
- Missing required column in a file: raise a descriptive error listing the absent column(s) — fail fast
- Encoding errors in PACO/Latin-1 files: `errors='replace'` — undecodable bytes become `\ufffd` placeholder rather than crashing

**Observability**
- tqdm progress bar showing chunk count, always on by default (no verbose flag needed)
- After each file finishes: log a one-line summary at `logging.INFO` — rows loaded, bad rows skipped, elapsed time
- Example: `contratos.csv: 12,435,201 rows loaded, 3 rows skipped, 47.2s`

### Claude's Discretion
- Exact tqdm bar format and description string
- Logger name / module hierarchy
- How to compute total chunk count for tqdm (may require a row count pre-scan or just show iteration count)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DATA-06 | System processes CSV files up to 5.3 GB without memory crashes using chunked reading strategies | Verified: `pd.read_csv(..., chunksize=50_000)` returns a `TextFileReader` iterable; 50k chunks of `procesos_SECOP.csv` (59 cols, 5.3 GB) use ~170 MB unoptimized or ~26 MB with `usecols` applied. No crash risk at chunk_size=50,000. |
| DATA-07 | System loads all local SECOP CSV files with correct dtypes and column selection to minimize memory footprint | Verified: `usecols` + explicit `dtype` dict in read_csv. Savings: procesos 87 MB → 26 MB per chunk (70% reduction). Currency columns (`$10,979,236,356` format) must be read as `str` and cleaned post-load. `on_bad_lines='warn'` skips malformed rows without crash. |
| DATA-10 | System handles encoding differences across sources without silent data corruption | FINDING: All PACO files are actually UTF-8 (verified full-file decode). Settings has `paco_encoding='latin-1'` which is wrong. All source files are UTF-8. `encoding_errors='replace'` is still correct as a safety net for any future files. |
</phase_requirements>

---

## Summary

Phase 2 implements reusable generator-based CSV loaders for all SECOP and RCAC source files. The core stack is `pandas 3.0.1` (already installed) with `tqdm 4.67.3` (already installed). All files are verified as UTF-8 — including the PACO files, which contradicts the `paco_encoding='latin-1'` setting established in Phase 1. The loaders split into two modules: `schemas.py` (column lists, dtype maps, post-load cleaning specs) and `loaders.py` (generator functions calling pd.read_csv with those specs).

Three structural surprises were confirmed by direct file inspection: (1) `multas_SECOP_PACO.csv` is headerless like `sanciones_SIRI_PACO.csv`, requiring positional column access; (2) currency-formatted amount columns (e.g., `$10,979,236,356`) cannot be cast to float at read time and must be cleaned post-read with `str.replace`; (3) `procesos_SECOP.csv` has mixed-type columns (`Nit Entidad`, `PCI`, one date column) that require explicit `dtype=str` to suppress `DtypeWarning`.

**Primary recommendation:** Two modules, `schemas.py` + `loaders.py`. Each loader: `pd.read_csv(path, chunksize=settings.chunk_size, usecols=SCHEMA_USECOLS, dtype=SCHEMA_DTYPE, encoding='utf-8', encoding_errors='replace', on_bad_lines='warn')` wrapped in a tqdm bar. Patch `Settings.paco_encoding` from `'latin-1'` to `'utf-8'` — all PACO files are UTF-8 in actuality.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 3.0.1 (installed) | Chunked CSV reading, DataFrame ops | Already in venv, `read_csv(chunksize=N)` is the canonical chunked I/O API |
| tqdm | 4.67.3 (installed) | Progress bars for chunk loops | Already in venv, zero-config wrapping of iterators |
| logging | stdlib | Structured warning/info output | No new dependency, integrates with `logging.captureWarnings(True)` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| subprocess / wc -l | stdlib/system | Pre-scan row counts for tqdm `total=` | macOS/Linux; enables ETA display on large files |
| pathlib.Path | stdlib | Path validation before open | Already used in Settings |
| time | stdlib | Elapsed time for summary log | stdlib, no install needed |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pd.read_csv(chunksize=N)` | Dask, Polars | Dask/Polars add complexity + new deps; pandas chunked is sufficient for this write-once batch pipeline |
| `wc -l` for row count | Full pre-scan with pandas | `wc -l` is instantaneous; pandas pre-scan would double I/O time |
| `encoding_errors='replace'` | `errors='ignore'` | `'replace'` preserves byte position with `\ufffd` marker; `'ignore'` silently drops bytes — harder to debug |

**Installation:** No new packages needed. pandas and tqdm are already installed.

---

## Architecture Patterns

### Recommended Project Structure

```
src/sip_engine/data/
├── __init__.py          # (exists, empty docstring)
├── schemas.py           # NEW: usecols lists, dtype dicts, currency column lists
└── loaders.py           # NEW: generator functions, one per source file
```

### Pattern 1: Standard SECOP Loader (has headers, UTF-8)

**What:** Generator function yielding DataFrame chunks from a single CSV.
**When to use:** All SECOP files and PACO files that have proper headers.

```python
# src/sip_engine/data/loaders.py
import logging
import time
from collections.abc import Generator

import pandas as pd
import tqdm

from sip_engine.config import get_settings
from sip_engine.data.schemas import CONTRATOS_USECOLS, CONTRATOS_DTYPE

logger = logging.getLogger(__name__)

def load_contratos() -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of contratos_SECOP.csv with critical dtypes enforced."""
    settings = get_settings()
    path = settings.contratos_path
    if not path.exists():
        raise FileNotFoundError(f"contratos not found: {path}")

    # Optional: pre-scan for tqdm total (wc -l approach)
    import subprocess
    result = subprocess.run(["wc", "-l", str(path)], capture_output=True, text=True)
    total_lines = int(result.stdout.strip().split()[0]) - 1  # subtract header
    total_chunks = (total_lines + settings.chunk_size - 1) // settings.chunk_size

    rows_loaded = 0
    rows_skipped = 0
    t0 = time.time()

    reader = pd.read_csv(
        path,
        chunksize=settings.chunk_size,
        usecols=CONTRATOS_USECOLS,
        dtype=CONTRATOS_DTYPE,
        encoding="utf-8",
        encoding_errors="replace",
        on_bad_lines="warn",   # skips bad rows, emits ParserWarning
    )

    with tqdm.tqdm(reader, total=total_chunks, desc="contratos", unit="chunk") as pbar:
        for chunk in pbar:
            rows_loaded += len(chunk)
            yield chunk

    elapsed = time.time() - t0
    logger.info(
        "contratos_SECOP.csv: %d rows loaded, %d rows skipped, %.1fs",
        rows_loaded, rows_skipped, elapsed,
    )
```

### Pattern 2: Headerless PACO Loader (SIRI / multas)

**What:** Loader for files without a header row — uses positional `usecols` (integers) and assigns column names explicitly.
**When to use:** `sanciones_SIRI_PACO.csv` (28 cols, no header) and `multas_SECOP_PACO.csv` (15 cols, no header).

```python
# src/sip_engine/data/loaders.py
from sip_engine.data.schemas import SIRI_USECOLS, SIRI_DTYPE, SIRI_COLNAMES

def load_paco_siri() -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of sanciones_SIRI_PACO.csv (no header, positional columns)."""
    settings = get_settings()
    path = settings.siri_path
    if not path.exists():
        raise FileNotFoundError(f"SIRI not found: {path}")

    reader = pd.read_csv(
        path,
        header=None,              # file has NO header row
        usecols=SIRI_USECOLS,     # [4, 5] — integer indices (0-based)
        dtype=SIRI_DTYPE,         # {4: str, 5: str}
        encoding="utf-8",
        encoding_errors="replace",
        on_bad_lines="warn",
        chunksize=settings.chunk_size,
    )

    for chunk in tqdm.tqdm(reader, desc="paco_siri", unit="chunk"):
        chunk.columns = SIRI_COLNAMES  # rename: ["tipo_documento", "numero_documento"]
        yield chunk
```

### Pattern 3: Currency Column Cleaning (schemas responsibility)

**What:** Amount columns in SECOP files are formatted as `$10,979,236,356` (string) and must be cleaned to float.
**When to use:** All `Valor del Contrato`, `Precio Base`, `Valor Total Adjudicacion` columns.

```python
# src/sip_engine/data/schemas.py

# Columns that contain currency strings and need cleaning to float
CONTRATOS_CURRENCY_COLS = ["Valor del Contrato"]
PROCESOS_CURRENCY_COLS = ["Precio Base", "Valor Total Adjudicacion"]

def clean_currency(series: pd.Series) -> pd.Series:
    """Convert '$10,979,236,356' to 10979236356.0. NaN-safe."""
    return series.str.replace(r"[\$,]", "", regex=True).astype("Float64")

# Callers should apply after yield:
# chunk["Valor del Contrato"] = clean_currency(chunk["Valor del Contrato"])
```

### Pattern 4: Bad-Row Count Capture

**What:** Counting `ParserWarning` events to report in the summary log.
**When to use:** All loaders, as the CONTEXT requires "rows skipped" in the INFO summary.

```python
# Standard pattern: capture warnings via logging
import warnings
import logging

logging.captureWarnings(True)  # routes warnings.warn() -> logging

class _BadRowCounter(logging.Handler):
    def __init__(self):
        super().__init__()
        self.count = 0
    def emit(self, record):
        if "Skipping line" in record.getMessage():
            self.count += 1

counter = _BadRowCounter()
logging.getLogger("py.warnings").addHandler(counter)
# ... run reader ...
rows_skipped = counter.count
```

### Anti-Patterns to Avoid

- **`dtype={'Valor del Contrato': float}`**: Fails immediately — SECOP amount columns use `$10,979,236,356` format. Always read as `str`, clean post-load.
- **`encoding='latin-1'` for PACO files**: All PACO files are verified UTF-8. Latin-1 produces garbled text (e.g., `CÃ\x89DULA` instead of `CÉDULA`). Use `encoding='utf-8'`.
- **`for chunk in pd.read_csv(..., chunksize=N)`**: Works but loses the reference to close the file. Better: assign to variable and iterate, or use as context manager.
- **`low_memory=False`**: Works around `DtypeWarning` but doubles RAM usage by loading all data before type inference. Prefer explicit `dtype` dict for known mixed columns.
- **Global `warnings.filterwarnings('ignore')`**: Silences ALL warnings; masks real data problems. Capture selectively via `logging.captureWarnings`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Chunked reading | Custom file byte-splitter | `pd.read_csv(chunksize=N)` | pandas handles quote escaping, line endings, encoding correctly |
| Progress display | Custom print-based counter | `tqdm.tqdm(reader, total=N)` | ETA, speed, nested bars all built in |
| Bad row skip | Try/except per row | `on_bad_lines='warn'` | C-level parser handles malformed lines; Python loop is 100x slower |
| Encoding detection | `chardet` / heuristics | Verified constants in schemas.py | All files empirically verified — detection adds latency and can be wrong |
| Currency parsing | Custom regex per column | `str.replace(r'[\$,]', '', regex=True).astype('Float64')` | One-liner, NaN-safe with nullable Float64 |

**Key insight:** pandas `read_csv` with `chunksize` is the correct and only tool here. Adding Dask or Polars would be over-engineering for a batch pipeline that runs once per training cycle.

---

## Common Pitfalls

### Pitfall 1: Currency String Format in Amount Columns
**What goes wrong:** `dtype={'Valor del Contrato': float}` raises `ValueError: Unable to parse string "$10,979,236,356"` immediately.
**Why it happens:** SECOP exports dollar sign + thousands comma — not a parseable float literal.
**How to avoid:** Always read these columns as `str` in the `dtype` dict. Apply `clean_currency()` inside the loader after yield (or document it in the schema so callers know to clean). The CONTEXT says "amounts as float" — this means the caller receives floats after cleaning, not that `dtype=float` is used at read time.
**Warning signs:** `ValueError: Unable to parse string "$..."` on any amount column.

### Pitfall 2: PACO Files Are UTF-8, Not Latin-1
**What goes wrong:** Reading with `encoding='latin-1'` produces garbled text for Spanish characters: `CÃ\x89DULA DE CIUDADANÃ\x8dA` instead of `CÉDULA DE CIUDADANÍA`. Downstream normalization silently corrupts document type strings, causing RCAC match failures.
**Why it happens:** `Settings.paco_encoding = 'latin-1'` was a planning assumption. Empirical verification (full file decode test) proves all five PACO files are UTF-8.
**How to avoid:** Use `encoding='utf-8'` for all files. Keep `encoding_errors='replace'` as a safety net. Update `Settings.paco_encoding` from `'latin-1'` to `'utf-8'` as part of this phase.
**Warning signs:** `\xc3\x89` style sequences or `Ã` characters in Spanish text output.

### Pitfall 3: Headerless Files — SIRI and Multas
**What goes wrong:** `pd.read_csv('sanciones_SIRI_PACO.csv')` treats the first data row as headers, producing garbage column names like `"100002597"` and `"DISCIPLINARIO"`. Subsequent `usecols=['tipo_documento']` raises `ValueError`.
**Why it happens:** Two PACO files have no header row: `sanciones_SIRI_PACO.csv` (28 cols) and `multas_SECOP_PACO.csv` (15 cols).
**How to avoid:** Use `header=None` and integer `usecols` (e.g., `[4, 5]`) for these two files. Rename columns immediately after loading in the loader function.
**Warning signs:** Column name `"100002597"` or a data value appearing as a column label.

### Pitfall 4: DtypeWarning from Mixed-Type Columns
**What goes wrong:** `procesos_SECOP.csv` columns `Nit Entidad`, `PCI`, and `Fecha de Publicacion (Fase Seleccion Precalificacion)` have mixed types — some numeric-looking strings, some not. Pandas emits `DtypeWarning` and may infer the wrong type.
**Why it happens:** Different rows have different value formats (NIT with/without hyphens, empty cells, etc.).
**How to avoid:** Add these three columns to the `PROCESOS_DTYPE` dict with `str` as the type. This suppresses the warning and guarantees consistent string output.
**Warning signs:** `DtypeWarning: Columns (...) have mixed types` in logs.

### Pitfall 5: Missing usecols Column Raises ValueError
**What goes wrong:** If a column in `usecols` does not exist in the file, pandas raises `ValueError: Usecols do not match columns, columns expected but not found: ['X']`. This is hard to debug in a batch pipeline.
**Why it happens:** Column names change in SECOP export versions, or typos in the schema.
**How to avoid:** The CONTEXT specifies "fail fast" on missing required columns — this behavior is actually correct. Add a pre-flight header check helper in `schemas.py` that reads only the header row and validates presence of all `usecols` before opening a chunked reader.
**Warning signs:** `ValueError: Usecols do not match` on pipeline start.

### Pitfall 6: Chunk Count Estimation for tqdm total
**What goes wrong:** Without `total=`, tqdm shows a spinning counter with no ETA, which is less useful. Using `pd.read_csv` with `nrows` just for counting wastes I/O.
**Why it happens:** File row counts aren't known without scanning.
**How to avoid:** Use `subprocess.run(["wc", "-l", str(path)])` for instant line count (macOS/Linux). Total chunks = `(lines - 1 + chunk_size - 1) // chunk_size`. This is the CONTEXT discretion area — `wc -l` is the recommended approach.
**Warning signs:** tqdm shows `0%|` indefinitely with `?it/s`.

---

## Code Examples

### Verified: Chunked read with usecols + dtype (pandas 3.0.1)

```python
# Source: empirically verified in project venv
import pandas as pd

reader = pd.read_csv(
    path,
    chunksize=50_000,
    usecols=["ID Contrato", "Valor del Contrato", "Documento Proveedor"],
    dtype={"ID Contrato": str, "Documento Proveedor": str, "Valor del Contrato": str},
    encoding="utf-8",
    encoding_errors="replace",
    on_bad_lines="warn",
)
for chunk in reader:
    # chunk is a DataFrame with exactly 3 columns
    chunk["Valor del Contrato"] = (
        chunk["Valor del Contrato"]
        .str.replace(r"[\$,]", "", regex=True)
        .astype("Float64")
    )
    yield chunk
```

### Verified: Headerless positional read (SIRI/multas)

```python
# Source: empirically verified; col[4]=tipo_doc, col[5]=numero_doc in SIRI
reader = pd.read_csv(
    siri_path,
    header=None,
    usecols=[4, 5],
    dtype={4: str, 5: str},
    encoding="utf-8",
    encoding_errors="replace",
    on_bad_lines="warn",
    chunksize=50_000,
)
for chunk in reader:
    chunk.columns = ["tipo_documento", "numero_documento"]
    yield chunk
```

### Verified: tqdm wrapping with total from wc -l

```python
# Source: empirically verified
import subprocess, tqdm

def _count_lines(path) -> int:
    r = subprocess.run(["wc", "-l", str(path)], capture_output=True, text=True)
    return int(r.stdout.strip().split()[0])

def _total_chunks(path, chunk_size) -> int:
    return (_count_lines(path) - 1 + chunk_size - 1) // chunk_size

# In loader:
reader = pd.read_csv(path, chunksize=chunk_size, ...)
total = _total_chunks(path, chunk_size)
for chunk in tqdm.tqdm(reader, total=total, desc="contratos", unit="chunk"):
    yield chunk
```

### Verified: on_bad_lines='warn' behavior

```python
# Source: empirically verified — bad rows are skipped, ParserWarning emitted
# The warning goes to py.warnings logger when logging.captureWarnings(True) is active
import logging, warnings
logging.captureWarnings(True)
# ParserWarning: "Skipping line N: expected K fields, saw M"
# Appears in logging output; row is omitted from DataFrame
```

---

## Critical File Inventory

All files verified by direct inspection on 2026-03-01.

### SECOP Files — All UTF-8, All Have Headers

| File | Size | Rows | Cols | Key Structural Notes |
|------|------|------|------|----------------------|
| `contratos_SECOP.csv` | 0.57 GB | ~537k | 87 | Currency cols: `Valor del Contrato` and 13 others |
| `procesos_SECOP.csv` | 5.3 GB | ~6.4M | 59 | Mixed-type cols: `Nit Entidad`, `PCI`, one date col |
| `ofertas_proceso_SECOP.csv` | 3.4 GB | ~9.7M | 16 | All cols clean, no mixed types |
| `proponentes_proceso_SECOP.csv` | small | unknown | 9 | Clean headers |
| `proveedores_registrados.csv` | small | unknown | 25 | Clean headers |
| `boletines.csv` | small | unknown | 9 | `tipo de documento` + `numero de documento` — explicit str dtype |
| `ejecucion_contratos.csv` | small | unknown | 16 | POST-EXECUTION — loader exists but downstream phases exclude |
| `suspensiones_contratos.csv` | small | unknown | 7 | Clean headers |
| `adiciones.csv` | tiny | ~1.3k | 5 | `identificador, id_contrato, tipo, descripcion, fecharegistro` |

### PACO Files — All UTF-8 (Settings paco_encoding must be corrected to 'utf-8')

| File | Size | Rows | Cols | Key Structural Notes |
|------|------|------|------|----------------------|
| `sanciones_SIRI_PACO.csv` | 19 MB | ~46k | 28 | NO HEADER — positional: col[4]=tipo_doc, col[5]=num_doc (0-indexed) |
| `responsabilidades_fiscales_PACO.csv` | 0.7 MB | ~6.6k | 8 | Combined `Tipo y Num Docuemento` field (parsing is Phase 3 concern) |
| `multas_SECOP_PACO.csv` | 0.6 MB | ~1.7k | 15 | NO HEADER — positional: col[5]=NIT_sancionado, col[0]=entidad |
| `colusiones_en_contratacion_SIC.csv` | tiny | ~103 | 12 | Has headers; `Identificacion` (str) is the document field |
| `sanciones_penales_FGN.csv` | 0.5 MB | ~3.9k | 9 | Has headers; geographic + crime type data, no direct doc ID |

### Settings Correction Required

`Settings.paco_encoding` is currently `'latin-1'`. Empirical full-file decode confirms all PACO files are UTF-8. This field must be patched to `'utf-8'` as part of Phase 2 Wave 0.

---

## Open Questions

1. **SIRI column index convention (0-based or 1-based)**
   - What we know: CONTEXT.md says "columns 5 and 6". File data confirms col[4] (0-indexed) = tipo_documento, col[5] (0-indexed) = numero_documento.
   - What's unclear: Was the CONTEXT using 1-indexed convention? Verified empirically: `usecols=[4, 5]` with `header=None` gives `CÉDULA DE CIUDADANÍA` and `24626226`. This is correct.
   - Recommendation: Use `usecols=[4, 5]` (0-indexed) in code. Add a comment: `# cols 5 and 6 per DATA-04 (1-indexed); [4, 5] in 0-indexed pandas`.

2. **multas_SECOP_PACO.csv column semantics**
   - What we know: 15 cols, no header, col[5] = NIT of the sanctioned provider (verified: `1067811412`), col[0] = contracting entity name.
   - What's unclear: Which column is the document type? The file appears to store only NIT (no tipo_documento). Phase 3 (RCAC builder) may need all columns or just col[5].
   - Recommendation: Load all columns for now (`usecols=None`), name them `[f"col_{i}" for i in range(15)]`, let Phase 3 define which it needs.

3. **sanciones_penales_FGN.csv — no direct document ID column**
   - What we know: 9 columns are geographic + crime type. No individual document number visible.
   - What's unclear: How does Phase 3 match FGN records to providers? There may be a secondary lookup join.
   - Recommendation: Load all 9 columns as-is (file is only 0.5 MB). Phase 3 will define the join logic.

4. **ejecucion_contratos.csv loader scope**
   - What we know: 16 post-execution columns. FEAT-08 and PROJ-02 exclude post-execution data from model features.
   - What's unclear: Does Phase 3 (RCAC) need any ejecucion data? The CONTEXT includes it in scope.
   - Recommendation: Build the loader (it's trivial), mark it with a docstring warning: `# POST-EXECUTION DATA — excluded from feature vectors (FEAT-08). Loader exists for RCAC use only.`

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | none (pyproject.toml has `[project.optional-dependencies].dev`) — no `[tool.pytest]` section |
| Quick run command | `pytest tests/test_loaders.py -x -q` |
| Full suite command | `pytest tests/ -q` |
| Estimated runtime per task | ~5–15 seconds (fixture uses tiny in-memory CSVs, not real 5GB files) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| DATA-06 | 50k-chunk iterator does not raise MemoryError or crash on large file path | integration (with real file, just 1 chunk) | `pytest tests/test_loaders.py::test_chunked_read_does_not_crash -x` | No — Wave 0 gap |
| DATA-07 | usecols reduces columns; dtypes match schema; currency cols cleaned to float | unit (in-memory CSV fixture) | `pytest tests/test_loaders.py::test_contratos_schema -x` | No — Wave 0 gap |
| DATA-10 | UTF-8 decoding produces correct Spanish characters; replacement char on bad byte | unit (in-memory fixture with injected bad byte) | `pytest tests/test_loaders.py::test_encoding_replace -x` | No — Wave 0 gap |

### Nyquist Sampling Rate

- **Minimum sample interval:** After each loader task committed — run `pytest tests/test_loaders.py -x -q`
- **Full suite trigger:** Before closing Phase 2 final wave
- **Phase-complete gate:** All loader tests green before `/gsd:verify-work`
- **Estimated feedback latency per task:** ~5–10 seconds

### Wave 0 Gaps (must be created before implementation)

- [ ] `tests/test_loaders.py` — covers DATA-06, DATA-07, DATA-10 with in-memory CSV fixtures
- [ ] `tests/conftest.py` — shared fixtures: `tiny_contratos_csv`, `tiny_siri_csv` (headerless), `bad_byte_csv`

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `error_bad_lines=False` | `on_bad_lines='warn'` | pandas 1.3.0 | Old param removed; use new one |
| `dtype=object` for strings | `dtype=str` (→ `StringDtype`) | pandas 1.0+ / pandas 3.0 default | pandas 3.x defaults to `StringDtype` for string cols; `str` and `object` both work but `str` produces `StringDtype` |
| `encoding_errors` as `errors=` kwarg | `encoding_errors='replace'` | pandas 1.5+ | Renamed to avoid ambiguity with `on_bad_lines` |

**Deprecated/outdated:**
- `error_bad_lines=False`: Removed in pandas 2.0. Use `on_bad_lines='warn'` or `'skip'`.
- `squeeze=True`: Removed in pandas 2.0. Not relevant here.

---

## Sources

### Primary (HIGH confidence)

- Empirical file inspection (`/Users/simonb/SIP Code/secopDatabases/`, `Data/Propia/PACO/`) — encoding, headers, column count, currency format, row counts verified by running python against actual files
- Live pandas 3.0.1 behavior — `on_bad_lines`, `encoding_errors`, `chunksize`, `usecols` with integer indices — all tested in project venv
- `src/sip_engine/config/settings.py` — verified Settings fields: `chunk_size=50_000`, `secop_encoding='utf-8'`, `paco_encoding='latin-1'` (needs correction)

### Secondary (MEDIUM confidence)

- tqdm 4.67.3 API — `tqdm.tqdm(iterable, total=N, desc=str, unit=str)` — verified working in venv
- `subprocess.run(['wc', '-l', path])` for line count — verified on macOS, returns `"N path\n"` format

### Tertiary (LOW confidence)

- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pandas + tqdm already installed, APIs verified against actual files
- Architecture: HIGH — generator pattern tested end-to-end; all structural surprises (headerless files, currency format, encoding) discovered empirically
- Pitfalls: HIGH — all pitfalls triggered and confirmed in the project venv during research

**Research date:** 2026-03-01
**Valid until:** 2026-04-01 (stable stack — pandas minor updates could affect on_bad_lines behavior)
