"""Provider History Index: temporal, leak-proof provider contract history.

The index enables O(1) as-of-date lookup for any provider's prior contract
counts, values, and label-derived statistics. Used for FEAT-05 (temporal leak
guard) and FEAT-06 (offline precomputation).

Data structure:
    {
        (tipo_norm, num_norm): {
            "dates":  [date, ...],      # sorted ascending (datetime.date objects)
            "valores": [float, ...],    # parallel array of contract values
            "deptos":  [str, ...],      # parallel array of department names
            "m1":      [int, ...],      # parallel array of M1 flags (0 or 1)
            "m2":      [int, ...],      # parallel array of M2 flags (0 or 1)
        },
        ...
    }

The parallel arrays are all sorted by date, enabling bisect_left for O(log n)
cutoff without needing to re-sort on every lookup.

Usage:
    from sip_engine.features.provider_history import (
        build_provider_history_index,
        lookup_provider_history,
        load_provider_history_index,
    )

    # Build offline (typically once, at pipeline start)
    build_provider_history_index()

    # Lookup as-of-date per contract
    result = lookup_provider_history("NIT", "900123456", datetime.date(2023, 6, 1))
"""

from __future__ import annotations

import bisect
import datetime
import logging
from pathlib import Path

import joblib
import pandas as pd

from sip_engine.config import get_settings
from sip_engine.data.rcac_builder import is_malformed, normalize_numero, normalize_tipo

logger = logging.getLogger(__name__)

# Module-level cache (same lazy-load pattern as rcac_lookup)
_provider_index: dict | None = None

# Keys returned by lookup_provider_history when provider not found
_ZERO_RESULT: dict = {
    "num_contratos_previos_nacional": 0,
    "num_contratos_previos_depto": 0,
    "valor_total_contratos_previos_nacional": 0.0,
    "valor_total_contratos_previos_depto": 0.0,
    "num_sobrecostos_previos": 0,
    "num_retrasos_previos": 0,
}


# ============================================================
# Builder
# ============================================================


def build_provider_history_index(force: bool = False) -> Path:
    """Build and serialize provider_history_index.pkl.

    If the pkl already exists and force=False, returns the existing path
    (cached build behavior — same pattern as build_rcac()).

    Steps:
    1. Stream contratos via load_contratos() — extract provider ID, date, value, dept
    2. Drop rows with null Fecha de Firma (cannot be ordered temporally)
    3. Load labels.parquet — join M1/M2 on id_contrato
    4. Normalize provider IDs via normalize_tipo/normalize_numero
    5. Group by (tipo_norm, num_norm), sort ascending by fecha_firma
    6. Serialize with joblib.dump()

    Args:
        force: If True, always rebuild even if pkl exists.

    Returns:
        Path to the serialized provider_history_index.pkl file.
    """
    global _provider_index

    settings = get_settings()
    pkl_path = settings.provider_history_index_path

    if pkl_path.exists() and not force:
        logger.info("Using cached provider history index at %s", pkl_path)
        return pkl_path

    # ---- Load labels for M1/M2 join ----
    labels_path = settings.labels_path
    if labels_path.exists():
        labels_df = pd.read_parquet(labels_path, columns=["id_contrato", "M1", "M2"])
        # Build fast O(1) lookup dict: id_contrato -> (m1, m2)
        labels_lookup: dict[str, tuple[int, int]] = {}
        for _, row in labels_df.iterrows():
            m1 = 0 if pd.isna(row["M1"]) else int(row["M1"])
            m2 = 0 if pd.isna(row["M2"]) else int(row["M2"])
            labels_lookup[str(row["id_contrato"])] = (m1, m2)
    else:
        logger.warning("labels.parquet not found at %s — M1/M2 counts will be zero", labels_path)
        labels_lookup = {}

    # ---- Stream contratos and accumulate per-provider records ----
    # raw_index: {(tipo_norm, num_norm): list of (date, valor, departamento, m1, m2)}
    from sip_engine.data.loaders import load_contratos

    raw_index: dict[tuple[str, str], list[tuple[datetime.date, float, str, int, int]]] = {}

    required_cols = {
        "ID Contrato", "TipoDocProveedor", "Documento Proveedor",
        "Fecha de Firma", "Valor del Contrato", "Departamento",
    }

    rows_loaded = 0
    rows_dropped_null_date = 0

    for chunk in load_contratos():
        # Verify required columns are present in this chunk
        missing = required_cols - set(chunk.columns)
        if missing:
            logger.warning("Contratos chunk missing columns: %s — skipping chunk", missing)
            continue

        for _, row in chunk.iterrows():
            rows_loaded += 1

            # --- Parse signing date (strict exclusion of null dates) ---
            raw_date = row.get("Fecha de Firma")
            if pd.isna(raw_date) or str(raw_date).strip() == "":
                rows_dropped_null_date += 1
                continue

            try:
                # Parse date — handle both "2023-01-15" and "2023-01-15 00:00:00" formats
                date_str = str(raw_date).strip()[:10]  # take YYYY-MM-DD prefix
                fecha_firma = datetime.date.fromisoformat(date_str)
            except (ValueError, TypeError):
                # Handle MM/DD/YYYY format common in SECOP CSVs
                try:
                    fecha_firma = datetime.datetime.strptime(date_str, "%m/%d/%Y").date()
                except (ValueError, TypeError):
                    rows_dropped_null_date += 1
                    continue

            # --- Normalize provider ID ---
            raw_tipo = row.get("TipoDocProveedor")
            raw_num = row.get("Documento Proveedor")
            tipo_norm = normalize_tipo(raw_tipo)
            num_norm = normalize_numero(raw_num)

            if is_malformed(num_norm):
                continue  # skip malformed provider IDs

            key = (tipo_norm, num_norm)

            # --- Contract value (already cleaned to Float64 by loader) ---
            raw_valor = row.get("Valor del Contrato", 0)
            try:
                valor = 0.0 if pd.isna(raw_valor) else float(raw_valor)
            except (TypeError, ValueError):
                valor = 0.0

            # --- Department ---
            raw_dept = row.get("Departamento", "")
            departamento = "" if pd.isna(raw_dept) else str(raw_dept).strip()

            # --- M1/M2 from labels ---
            id_contrato = str(row.get("ID Contrato", ""))
            m1, m2 = labels_lookup.get(id_contrato, (0, 0))

            raw_index.setdefault(key, []).append(
                (fecha_firma, valor, departamento, m1, m2)
            )

    logger.info(
        "Provider history: %d rows loaded, %d dropped (null date), %d unique providers",
        rows_loaded,
        rows_dropped_null_date,
        len(raw_index),
    )

    # ---- Sort each provider's list by date (ascending) and build parallel arrays ----
    index: dict[tuple[str, str], dict] = {}
    for key, records in raw_index.items():
        records.sort(key=lambda r: r[0])  # sort by fecha_firma ascending
        index[key] = {
            "dates":   [r[0] for r in records],
            "valores": [r[1] for r in records],
            "deptos":  [r[2] for r in records],
            "m1":      [r[3] for r in records],
            "m2":      [r[4] for r in records],
        }

    # ---- Serialize ----
    pkl_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(index, pkl_path)

    # Invalidate module cache so next load_provider_history_index() picks up fresh data
    _provider_index = None

    logger.info("Provider history index serialized to %s (%d providers)", pkl_path, len(index))
    return pkl_path


# ============================================================
# Loader (lazy, cached)
# ============================================================


def load_provider_history_index() -> dict:
    """Lazy-load and cache the provider history index from pkl.

    Returns the module-level cached dict on subsequent calls.
    Call reset_provider_history_cache() for test isolation.

    Returns:
        Provider history index dict.

    Raises:
        FileNotFoundError: If provider_history_index.pkl has not been built yet.
    """
    global _provider_index

    if _provider_index is not None:
        return _provider_index

    settings = get_settings()
    pkl_path = settings.provider_history_index_path

    if not pkl_path.exists():
        raise FileNotFoundError(
            f"Provider history index not found at {pkl_path}. "
            "Run build_provider_history_index() first."
        )

    _provider_index = joblib.load(pkl_path)
    logger.info("Provider history index loaded from %s (%d providers)", pkl_path, len(_provider_index))
    return _provider_index


def reset_provider_history_cache() -> None:
    """Reset module-level cache.

    Ensures test isolation — call after each test that uses the index,
    matching the pattern of reset_rcac_cache() in rcac_lookup.py.
    """
    global _provider_index
    _provider_index = None


# ============================================================
# Lookup
# ============================================================


def lookup_provider_history(
    tipo_doc: str,
    num_doc: str,
    as_of_date: datetime.date,
    departamento: str | None = None,
) -> dict:
    """Look up a provider's historical contract statistics as of a given date.

    Returns only contracts signed STRICTLY BEFORE as_of_date (same-day excluded).
    This enforces the temporal leak guard required by FEAT-05.

    Normalizes provider ID inputs at the lookup boundary (caller passes raw strings).

    Args:
        tipo_doc: Raw document type string (e.g., "NIT", "CC", "Persona Juridica").
        num_doc: Raw document number string (e.g., "900.123.456-1").
        as_of_date: Date of the contract being evaluated. Prior contracts must be
            strictly before this date.
        departamento: Optional department name for departmental scope. If None,
            departmental counts are 0.

    Returns:
        Dict with keys:
            - num_contratos_previos_nacional (int)
            - num_contratos_previos_depto (int)
            - valor_total_contratos_previos_nacional (float)
            - valor_total_contratos_previos_depto (float)
            - num_sobrecostos_previos (int) — prior contracts with M1=1
            - num_retrasos_previos (int) — prior contracts with M2=1
    """
    # Normalize at lookup boundary (same pattern as rcac_lookup)
    tipo_norm = normalize_tipo(tipo_doc)
    num_norm = normalize_numero(num_doc)

    if is_malformed(num_norm):
        return dict(_ZERO_RESULT)

    index = load_provider_history_index()
    key = (tipo_norm, num_norm)

    if key not in index:
        return dict(_ZERO_RESULT)

    provider = index[key]
    dates = provider["dates"]
    valores = provider["valores"]
    deptos = provider["deptos"]
    m1_flags = provider["m1"]
    m2_flags = provider["m2"]

    # Use bisect_left to find cutoff: all entries before index are strictly < as_of_date
    cutoff = bisect.bisect_left(dates, as_of_date)

    if cutoff == 0:
        return dict(_ZERO_RESULT)

    # National aggregation (all prior contracts)
    num_nacional = cutoff
    valor_nacional = sum(valores[:cutoff])
    num_sobrecostos = sum(m1_flags[:cutoff])
    num_retrasos = sum(m2_flags[:cutoff])

    # Departmental aggregation (prior contracts in the same department)
    num_depto = 0
    valor_depto = 0.0
    if departamento is not None:
        dept_norm = str(departamento).strip()
        for i in range(cutoff):
            if deptos[i] == dept_norm:
                num_depto += 1
                valor_depto += valores[i]

    return {
        "num_contratos_previos_nacional": num_nacional,
        "num_contratos_previos_depto": num_depto,
        "valor_total_contratos_previos_nacional": float(valor_nacional),
        "valor_total_contratos_previos_depto": float(valor_depto),
        "num_sobrecostos_previos": num_sobrecostos,
        "num_retrasos_previos": num_retrasos,
    }
