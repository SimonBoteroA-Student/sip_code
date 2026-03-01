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
from sip_engine.data.loaders import load_adiciones, load_contratos
from sip_engine.data.rcac_builder import (  # noqa: F401 — imported for M3/M4 use in Plan 04-02
    is_malformed,
    normalize_numero,
    normalize_tipo,
)

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


# ============================================================
# Public API
# ============================================================

def build_labels(force: bool = False) -> Path:
    """Build M1/M2/M3/M4 binary labels from source data and save to parquet.

    M1 = 1 if contract has at least one value amendment (ADICION EN EL VALOR
         or REDUCCION EN EL VALOR) in adiciones.csv.
    M2 = 1 if contract has at least one time extension (EXTENSION) in adiciones.csv.
    M3 and M4 are computed in _compute_m3_m4() (Plan 04-02).

    Args:
        force: If True, rebuild even if labels.parquet already exists.

    Returns:
        Path to the labels.parquet file (may not yet be written in plan 04-01 skeleton).

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

    # M3 and M4 computed in _compute_m3_m4()

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

    # Parquet write deferred to Plan 04-02 (after M3/M4 are added)
    return settings.labels_path
