"""Label construction for SIP models M1-M4.

Builds binary target labels for all 4 models from their respective sources:
- M1 (cost overruns): adiciones.csv value amendments
- M2 (delays): adiciones.csv time extensions
- M3 (Comptroller records): boletines.csv fiscal liability
- M4 (RCAC sanctions): RCAC lookup

Usage:
    from sip_engine.data.label_builder import build_labels
    path = build_labels()           # uses cached parquet if present
    path = build_labels(force=True)  # always rebuilds
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from sip_engine.config import get_settings
from sip_engine.data.loaders import load_adiciones, load_boletines, load_contratos
from sip_engine.data.rcac_builder import (
    is_malformed,
    normalize_numero,
    normalize_tipo,
)
from sip_engine.data.rcac_lookup import rcac_lookup

logger = logging.getLogger(__name__)

# ============================================================
# Constants
# ============================================================

M1_TIPOS: set[str] = {"ADICION EN EL VALOR", "REDUCCION EN EL VALOR"}
M2_TIPOS: set[str] = {"EXTENSION"}


# ============================================================
# Internal helpers
# ============================================================

def _load_contratos_base() -> pd.DataFrame:
    """Load the contratos base DataFrame with deduplication by ID Contrato.

    Streams all contratos chunks and selects the columns needed for label
    construction. Duplicate rows sharing the same ID Contrato are collapsed
    to a single row (keep first occurrence).

    Returns:
        DataFrame with columns: ID Contrato, TipoDocProveedor, Documento Proveedor.
        One row per unique contract ID.
    """
    needed_cols = ["ID Contrato", "TipoDocProveedor", "Documento Proveedor"]
    chunks: list[pd.DataFrame] = []

    for chunk in load_contratos():
        chunks.append(chunk[needed_cols])

    df = pd.concat(chunks, ignore_index=True)
    total = len(df)
    df = df.drop_duplicates(subset=["ID Contrato"], keep="first")
    unique = len(df)

    logger.info("Contratos loaded: %d rows (%d unique)", total, unique)
    return df


def _build_m1_m2_sets(
    contratos_ids: set[str],
) -> tuple[set[str], set[str]]:
    """Stream adiciones.csv and build contract ID sets for M1 and M2 labels.

    For each chunk of adiciones:
    - Rows whose id_contrato is NOT in contratos_ids are counted as orphans and ignored.
    - Matched rows are classified by tipo (case-insensitive, stripped):
        * M1_TIPOS -> add id_contrato to m1_contracts
        * M2_TIPOS -> add id_contrato to m2_contracts

    Args:
        contratos_ids: Set of valid contract IDs from the contratos base table.

    Returns:
        Tuple (m1_contracts, m2_contracts) — sets of contract IDs with positive labels.
    """
    m1_contracts: set[str] = set()
    m2_contracts: set[str] = set()
    total_rows = 0
    orphan_count = 0

    for chunk in load_adiciones():
        total_rows += len(chunk)

        # Identify matched vs orphan rows
        is_matched = chunk["id_contrato"].isin(contratos_ids)
        orphan_count += (~is_matched).sum()

        matched = chunk[is_matched].copy()
        if matched.empty:
            continue

        # Normalise tipo to uppercase stripped string for comparison
        tipo_upper = matched["tipo"].str.strip().str.upper()

        # Collect M1 contract IDs
        m1_mask = tipo_upper.isin(M1_TIPOS)
        m1_contracts.update(matched.loc[m1_mask, "id_contrato"].tolist())

        # Collect M2 contract IDs
        m2_mask = tipo_upper.isin(M2_TIPOS)
        m2_contracts.update(matched.loc[m2_mask, "id_contrato"].tolist())

    matched_count = total_rows - orphan_count
    orphan_pct = (orphan_count / total_rows * 100) if total_rows > 0 else 0.0
    logger.info(
        "Adiciones processed: %d total, %d matched, %d orphans (%.1f%%)",
        total_rows,
        matched_count,
        orphan_count,
        orphan_pct,
    )

    return m1_contracts, m2_contracts


def _build_boletines_set() -> set[tuple[str, str]]:
    """Load boletines.csv and return normalized (tipo, num) set for M3 lookup.

    Returns a set of (normalized_tipo, normalized_num) tuples. Each tuple
    represents a known fiscal liability holder from Comptroller bulletins.

    Returns:
        Set of (tipo_norm, num_norm) tuples for O(1) M3 membership tests.
    """
    result: set[tuple[str, str]] = set()

    for chunk in load_boletines():
        for _, row in chunk.iterrows():
            tipo_raw = row.get("tipo de documento", "")
            num_raw = row.get("numero de documento", "")

            tipo_norm = normalize_tipo(str(tipo_raw) if pd.notna(tipo_raw) else "")
            num_norm = normalize_numero(str(num_raw) if pd.notna(num_raw) else "")

            if is_malformed(num_norm):
                continue

            result.add((tipo_norm, num_norm))

    logger.info("Boletines set: %d unique (tipo, num) pairs", len(result))
    logger.warning(
        "boletines.csv is incomplete — M3 labels not suitable for production training"
    )
    return result


def _compute_m3_m4(
    df: pd.DataFrame,
    boletines_set: set[tuple[str, str]],
) -> pd.DataFrame:
    """Compute M3 and M4 labels on the contratos DataFrame.

    M3: provider in boletines_set (direct query, not via RCAC).
    M4: provider found in RCAC via rcac_lookup().

    Null handling: M3=null and M4=null when provider ID is missing or malformed.

    Args:
        df: Contratos DataFrame with TipoDocProveedor and Documento Proveedor columns.
        boletines_set: Set of (tipo_norm, num_norm) tuples from _build_boletines_set().

    Returns:
        DataFrame with M3, M4, TipoDocProveedor_norm, DocProveedor_norm columns added.
    """
    df = df.copy()

    # Compute normalized provider columns (fill NaN before normalization)
    tipo_series = df["TipoDocProveedor"].fillna("").apply(normalize_tipo)
    num_series = df["Documento Proveedor"].fillna("").apply(normalize_numero)

    # Determine malformed mask: malformed num OR originally missing provider doc
    malformed_mask = (
        num_series.apply(is_malformed)
        | df["Documento Proveedor"].isna()
    )

    # ---- M3: boletines set membership ----
    m3_values: list[int | None] = []
    for i in range(len(df)):
        if malformed_mask.iloc[i]:
            m3_values.append(None)
        else:
            key = (tipo_series.iloc[i], num_series.iloc[i])
            m3_values.append(1 if key in boletines_set else 0)

    # ---- M4: RCAC lookup (passes raw values; rcac_lookup normalizes internally) ----
    m4_values: list[int | None] = []
    tipo_raw_series = df["TipoDocProveedor"].fillna("")
    num_raw_series = df["Documento Proveedor"].fillna("")

    for i in range(len(df)):
        if malformed_mask.iloc[i]:
            m4_values.append(None)
        else:
            record = rcac_lookup(
                str(tipo_raw_series.iloc[i]),
                str(num_raw_series.iloc[i]),
            )
            m4_values.append(1 if record is not None else 0)

    # Assign nullable Int8 columns
    df["M3"] = pd.array(m3_values, dtype="Int8")
    df["M4"] = pd.array(m4_values, dtype="Int8")

    # Add normalized provider audit columns
    df["TipoDocProveedor_norm"] = tipo_series
    df["DocProveedor_norm"] = num_series

    # Log M3 summary
    m3_pos = int(df["M3"].sum(skipna=True))
    m3_null = int(df["M3"].isna().sum())
    total = len(df)
    m3_pct = m3_pos / (total - m3_null) * 100 if (total - m3_null) > 0 else 0.0
    logger.info(
        "M3: %d positive (%.2f%%), %d null (malformed provider ID)",
        m3_pos,
        m3_pct,
        m3_null,
    )

    # Log M4 summary
    m4_pos = int(df["M4"].sum(skipna=True))
    m4_null = int(df["M4"].isna().sum())
    m4_pct = m4_pos / (total - m4_null) * 100 if (total - m4_null) > 0 else 0.0
    logger.info(
        "M4: %d positive (%.2f%%), %d null (malformed provider ID)",
        m4_pos,
        m4_pct,
        m4_null,
    )

    return df


# ============================================================
# Public API
# ============================================================

def build_labels(force: bool = False) -> Path:
    """Build M1/M2/M3/M4 binary labels from source data and save to parquet.

    M1 = 1 if contract has at least one value amendment (ADICION EN EL VALOR
         or REDUCCION EN EL VALOR) in adiciones.csv.
    M2 = 1 if contract has at least one time extension (EXTENSION) in adiciones.csv.
    M3 = 1 if contract provider is in boletines.csv (Comptroller fiscal liability).
    M4 = 1 if contract provider is found in the RCAC index (corruption antecedents).
    Null for M3/M4 when provider document ID is missing or malformed.

    Args:
        force: If True, rebuild even if labels.parquet already exists.

    Returns:
        Path to the labels.parquet file.

    Raises:
        FileNotFoundError: If the RCAC index has not been built yet.
    """
    settings = get_settings()

    if settings.labels_path.exists() and not force:
        logger.info("Using cached labels at %s", settings.labels_path)
        return settings.labels_path

    if not settings.rcac_path.exists():
        raise FileNotFoundError(
            "RCAC index not found. Run 'python -m sip_engine build-rcac' first."
        )

    # ---- Prepare output directory ----
    settings.artifacts_labels_dir.mkdir(parents=True, exist_ok=True)

    # ---- Load contratos base ----
    df = _load_contratos_base()
    contratos_ids: set[str] = set(df["ID Contrato"].dropna().tolist())

    # ---- Build M1/M2 sets from adiciones ----
    m1_contracts, m2_contracts = _build_m1_m2_sets(contratos_ids)

    # ---- Assign M1/M2 columns ----
    df["M1"] = df["ID Contrato"].isin(m1_contracts).astype("Int8")
    df["M2"] = df["ID Contrato"].isin(m2_contracts).astype("Int8")

    # ---- Log M1/M2 summary ----
    m1_count = int(df["M1"].sum())
    m2_count = int(df["M2"].sum())
    total = len(df)
    logger.info(
        "M1: %d positive (%.1f%%) | M2: %d positive (%.1f%%)",
        m1_count,
        m1_count / total * 100 if total > 0 else 0.0,
        m2_count,
        m2_count / total * 100 if total > 0 else 0.0,
    )

    if m2_count < 50:
        logger.warning(
            "M2 has only %d positive examples — model may not be trainable", m2_count
        )

    # ---- Build boletines set and compute M3/M4 ----
    boletines_set = _build_boletines_set()
    df = _compute_m3_m4(df, boletines_set)

    # ---- Select and rename output columns ----
    output_cols = [
        "ID Contrato",
        "M1", "M2", "M3", "M4",
        "TipoDocProveedor_norm",
        "DocProveedor_norm",
    ]
    out = df[output_cols].rename(columns={"ID Contrato": "id_contrato"})

    # ---- Write to parquet ----
    out.to_parquet(settings.labels_path, index=False, engine="pyarrow")

    # ---- Final summary ----
    total_out = len(out)
    logger.info(
        "Labels written: %d rows -> %s",
        total_out,
        settings.labels_path,
    )
    for col in ["M1", "M2", "M3", "M4"]:
        pos = int(out[col].sum(skipna=True))
        null = int(out[col].isna().sum())
        zero = total_out - pos - null
        logger.info(
            "%s: %d positive, %d zero, %d null",
            col, pos, zero, null,
        )

    return settings.labels_path
