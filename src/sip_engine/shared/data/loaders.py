"""Generator-based CSV loader functions for all SIP data sources.

Each public loader function:
- Yields pd.DataFrame chunks (generator protocol)
- Displays a tqdm progress bar (chunk count)
- Logs an INFO summary after completion (rows loaded, skipped, elapsed)
- Raises FileNotFoundError if the file does not exist
- Raises ValueError (via validate_columns) if a required column is absent
- Handles bad rows with on_bad_lines='warn' (skips, not crash)
- Handles encoding errors with encoding_errors='replace' (U+FFFD, not crash)

DATA-06: chunked reading — callers never hold the whole file in memory
DATA-07: dtypes enforced from schemas constants, currency cols cleaned to Float64
DATA-10: UTF-8 encoding with replacement fallback for all sources

Pattern: all loaders delegate to the private _load_csv() helper.
POST-EXECUTION NOTE: load_ejecucion() is for RCAC use only (FEAT-08 exclusion).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator

import pandas as pd
import tqdm

from sip_engine.shared.config import get_settings
from sip_engine.compat import count_lines
from sip_engine.shared.data.schemas import (
    ADICIONES_DTYPE,
    ADICIONES_USECOLS,
    BOLETINES_DTYPE,
    BOLETINES_USECOLS,
    COLUSIONES_DTYPE,
    COLUSIONES_USECOLS,
    CONTRATOS_CURRENCY_COLS,
    CONTRATOS_DTYPE,
    CONTRATOS_USECOLS,
    EJECUCION_DTYPE,
    EJECUCION_USECOLS,
    MULTAS_COLNAMES,
    MULTAS_USECOLS,
    OFERTAS_CURRENCY_COLS,
    OFERTAS_DTYPE,
    OFERTAS_USECOLS,
    PROCESOS_CURRENCY_COLS,
    PROCESOS_DTYPE,
    PROCESOS_USECOLS,
    PROPONENTES_DTYPE,
    PROPONENTES_USECOLS,
    PROVEEDORES_DTYPE,
    PROVEEDORES_USECOLS,
    RESP_FISCALES_DTYPE,
    RESP_FISCALES_USECOLS,
    SANCIONES_PENALES_DTYPE,
    SANCIONES_PENALES_USECOLS,
    SIRI_COLNAMES,
    SIRI_DTYPE,
    SIRI_USECOLS,
    SUSPENSIONES_DTYPE,
    SUSPENSIONES_USECOLS,
    clean_currency,
    resolve_soda_columns,
    validate_columns,
)

logger = logging.getLogger(__name__)


# ============================================================
# Private helpers
# ============================================================


def _total_chunks(path, chunk_size: int, has_header: bool = True) -> int:
    """Estimate number of chunks for the tqdm total parameter.

    Args:
        path: Path to the CSV file.
        chunk_size: Rows per chunk.
        has_header: If True, subtract 1 from line count (header row).

    Returns:
        Estimated chunk count, or 0 if line count is unavailable.
    """
    line_count = count_lines(path)
    if line_count == 0:
        return 0
    data_rows = line_count - 1 if has_header else line_count
    return max(1, (data_rows + chunk_size - 1) // chunk_size)


class _BadRowCounter(logging.Handler):
    """Logging handler that counts 'Skipping line' ParserWarning messages."""

    def __init__(self):
        super().__init__()
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        if "Skipping line" in msg or "ParserWarning" in msg:
            self.count += 1


def _load_csv(
    path,
    desc: str,
    usecols,
    dtype: dict,
    encoding: str,
    currency_cols: list[str] | None = None,
    has_header: bool = True,
    colnames: list[str] | None = None,
    validate: bool = True,
    chunk_size: int | None = None,
) -> Generator[pd.DataFrame, None, None]:
    """Core generator implementing the shared CSV loading pattern.

    Args:
        path: Path object to the CSV file.
        desc: Label shown in tqdm progress bar.
        usecols: Column selector (list of str or list of int for headerless).
        dtype: Dict mapping column names/indices to dtype.
        encoding: File encoding (always 'utf-8' for SIP sources).
        currency_cols: Columns to clean with clean_currency() after each chunk.
        has_header: If False, use header=None (headerless file).
        colnames: Rename columns to these names after reading (headerless files).
        validate: Whether to run validate_columns() before reading.
        chunk_size: Override ``settings.chunk_size`` when provided.  When
            ``None`` (default), the global setting is used.

    Yields:
        pd.DataFrame chunks with dtypes enforced and currency cols cleaned.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If a required named column is absent (via validate_columns).
    """
    if not path.exists():
        raise FileNotFoundError(f"{desc} not found: {path}")

    if validate:
        validate_columns(str(path), usecols if usecols is not None else [], encoding=encoding)

    # Auto-detect SODA headers and resolve usecols/dtype if needed
    soda_rename_map: dict[str, str] = {}
    resolved_usecols = usecols
    resolved_dtype = dtype
    if usecols is not None and usecols and isinstance(usecols[0], str):
        resolved_usecols, resolved_dtype, soda_rename_map = resolve_soda_columns(
            str(path), usecols, dtype, encoding
        )

    settings = get_settings()
    effective_chunk_size = chunk_size if chunk_size is not None else settings.chunk_size
    total = _total_chunks(path, effective_chunk_size, has_header=has_header)
    rows_loaded = 0

    # Set up bad-row counter via py.warnings logger
    logging.captureWarnings(True)
    counter = _BadRowCounter()
    py_warnings_logger = logging.getLogger("py.warnings")
    py_warnings_logger.addHandler(counter)

    t0 = time.time()

    read_kwargs: dict = dict(
        chunksize=effective_chunk_size,
        dtype=resolved_dtype,
        encoding=encoding,
        encoding_errors="replace",
        on_bad_lines="warn",
        low_memory=False,
    )
    if resolved_usecols is not None:
        read_kwargs["usecols"] = resolved_usecols
    if not has_header:
        read_kwargs["header"] = None

    reader = pd.read_csv(path, **read_kwargs)

    pbar = tqdm.tqdm(total=total or None, desc=desc, unit="chunk")
    try:
        for chunk in reader:
            if colnames is not None:
                chunk.columns = colnames
            if soda_rename_map:
                chunk.rename(columns=soda_rename_map, inplace=True)
            if currency_cols:
                for col in currency_cols:
                    if col in chunk.columns:
                        chunk[col] = clean_currency(chunk[col])
            rows_loaded += len(chunk)
            pbar.update(1)
            yield chunk
    finally:
        # Correct the total so the bar shows 100% on completion
        if pbar.n > 0 and (pbar.total is None or pbar.total != pbar.n):
            pbar.total = pbar.n
            pbar.refresh()
        pbar.close()
        py_warnings_logger.removeHandler(counter)
        elapsed = time.time() - t0
        logger.info(
            "%s: %d rows loaded, %d rows skipped, %.1fs",
            path.name,
            rows_loaded,
            counter.count,
            elapsed,
        )


# ============================================================
# SECOP loaders — 9 headed UTF-8 files
# ============================================================

def load_contratos(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of contratos_SECOP.csv with currency columns cleaned to Float64.

    DATA-06: chunked, never holds full file in memory.
    DATA-07: currency 'Valor del Contrato' cleaned from '$X,XXX' to Float64.

    Args:
        chunk_size: Override the global ``settings.chunk_size``.  When
            ``None`` (default), the global setting is used.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.contratos_path,
        desc="contratos",
        usecols=CONTRATOS_USECOLS,
        dtype=CONTRATOS_DTYPE,
        encoding="utf-8",
        currency_cols=CONTRATOS_CURRENCY_COLS,
        chunk_size=chunk_size,
    )


def load_procesos(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of procesos_SECOP.csv (~6.4M rows, 5.3 GB).

    Mixed-type columns (Nit Entidad, PCI) forced to str to suppress DtypeWarning.
    Currency columns 'Precio Base' and 'Valor Total Adjudicacion' cleaned to Float64.

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.procesos_path,
        desc="procesos",
        usecols=PROCESOS_USECOLS,
        dtype=PROCESOS_DTYPE,
        encoding="utf-8",
        currency_cols=PROCESOS_CURRENCY_COLS,
        chunk_size=chunk_size,
    )


def load_ofertas(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of ofertas_proceso_SECOP.csv (~9.7M rows, 3.4 GB).

    Currency column 'Valor de la Oferta' cleaned to Float64.

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.ofertas_path,
        desc="ofertas",
        usecols=OFERTAS_USECOLS,
        dtype=OFERTAS_DTYPE,
        encoding="utf-8",
        currency_cols=OFERTAS_CURRENCY_COLS,
        chunk_size=chunk_size,
    )


def load_proponentes(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of proponentes_proceso_SECOP.csv (small file, 9 columns).

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.proponentes_path,
        desc="proponentes",
        usecols=PROPONENTES_USECOLS,
        dtype=PROPONENTES_DTYPE,
        encoding="utf-8",
        chunk_size=chunk_size,
    )


def load_proveedores(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of proveedores_registrados.csv (small file, 25 columns).

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.proveedores_path,
        desc="proveedores",
        usecols=PROVEEDORES_USECOLS,
        dtype=PROVEEDORES_DTYPE,
        encoding="utf-8",
        chunk_size=chunk_size,
    )


def load_boletines(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of boletines.csv (small file). Document ID columns kept as str.

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.boletines_path,
        desc="boletines",
        usecols=BOLETINES_USECOLS,
        dtype=BOLETINES_DTYPE,
        encoding="utf-8",
        chunk_size=chunk_size,
    )


def load_ejecucion(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of ejecucion_contratos.csv.

    POST-EXECUTION DATA — excluded from feature vectors (FEAT-08).
    Loader exists for RCAC builder use only (cross-referencing execution status).

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.ejecucion_path,
        desc="ejecucion",
        usecols=EJECUCION_USECOLS,
        dtype=EJECUCION_DTYPE,
        encoding="utf-8",
        chunk_size=chunk_size,
    )


def load_suspensiones(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of suspensiones_contratos.csv (small file, 7 columns).

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.suspensiones_path,
        desc="suspensiones",
        usecols=SUSPENSIONES_USECOLS,
        dtype=SUSPENSIONES_DTYPE,
        encoding="utf-8",
        chunk_size=chunk_size,
    )


def load_adiciones(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of adiciones.csv (tiny file, ~1.3k rows). Used for M1/M2 labels.

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.adiciones_path,
        desc="adiciones",
        usecols=ADICIONES_USECOLS,
        dtype=ADICIONES_DTYPE,
        encoding="utf-8",
        chunk_size=chunk_size,
    )


# ============================================================
# PACO loaders — 3 headed UTF-8 files
# ============================================================

def load_paco_resp_fiscales(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of responsabilidades_fiscales_PACO.csv (~6.6k rows).

    'Tipo y Num Docuemento' is a combined type+number field (Phase 3 parses it).
    Note: typo 'Docuemento' is in the source file, preserved here.

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.responsabilidades_fiscales_path,
        desc="paco_resp_fiscales",
        usecols=RESP_FISCALES_USECOLS,
        dtype=RESP_FISCALES_DTYPE,
        encoding="utf-8",
        chunk_size=chunk_size,
    )


def load_paco_colusiones(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of colusiones_en_contratacion_SIC.csv (~103 rows, tiny).

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.colusiones_sic_path,
        desc="paco_colusiones",
        usecols=COLUSIONES_USECOLS,
        dtype=COLUSIONES_DTYPE,
        encoding="utf-8",
        chunk_size=chunk_size,
    )


def load_paco_sanciones_penales(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of sanciones_penales_FGN.csv (~3.9k rows, 9 geographic columns).

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.sanciones_penales_path,
        desc="paco_sanciones_penales",
        usecols=SANCIONES_PENALES_USECOLS,
        dtype=SANCIONES_PENALES_DTYPE,
        encoding="utf-8",
        chunk_size=chunk_size,
    )


# ============================================================
# PACO headerless loaders — 2 files with no header row
# ============================================================

def load_paco_siri(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of sanciones_SIRI_PACO.csv (no header, positional columns).

    Only cols 4 and 5 (0-indexed) are loaded — tipo_documento and numero_documento.
    DATA-04: cols 5 and 6 per 1-indexed spec; [4, 5] in 0-indexed pandas.
    Spanish characters (CÉDULA DE CIUDADANÍA) preserved via UTF-8 encoding.

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.siri_path,
        desc="paco_siri",
        usecols=SIRI_USECOLS,
        dtype=SIRI_DTYPE,
        encoding="utf-8",
        has_header=False,
        colnames=SIRI_COLNAMES,
        validate=False,  # headerless — no column names to validate
        chunk_size=chunk_size,
    )


def load_paco_multas(chunk_size: int | None = None) -> Generator[pd.DataFrame, None, None]:
    """Yield chunks of multas_SECOP_PACO.csv (no header, all 15 columns).

    Columns renamed to col_0 through col_14.
    col[5] = NIT of sanctioned provider (Phase 3 refines column usage).

    Args:
        chunk_size: Override the global ``settings.chunk_size``.
    """
    settings = get_settings()
    yield from _load_csv(
        path=settings.multas_secop_path,
        desc="paco_multas",
        usecols=MULTAS_USECOLS,
        dtype={},
        encoding="utf-8",
        has_header=False,
        colnames=MULTAS_COLNAMES,
        validate=False,  # headerless — no column names to validate
        chunk_size=chunk_size,
    )
