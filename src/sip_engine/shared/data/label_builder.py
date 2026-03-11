"""Label construction for SIP models M1-M4.

Builds binary target labels for all 4 models from their respective sources:
- M1 (cost overruns): adiciones.csv value amendments
- M2 (delays): adiciones.csv time extensions
- M3 (Comptroller records): boletines.csv fiscal liability
- M4 (RCAC sanctions): RCAC lookup

Usage:
    from sip_engine.shared.data.label_builder import build_labels
    path = build_labels()           # uses cached parquet if present
    path = build_labels(force=True)  # always rebuilds
"""

from __future__ import annotations

import gc
import logging
from pathlib import Path

import pandas as pd

from sip_engine.shared.config import get_settings
from sip_engine.shared.data.loaders import load_adiciones, load_boletines, load_contratos
from sip_engine.shared.data.rcac_builder import (
    is_malformed,
    normalize_numero,
    normalize_tipo,
)
from sip_engine.shared.data.rcac_lookup import rcac_lookup
from sip_engine.shared.memory import (
    MemoryMonitor,
    adaptive_chunk_size,
    cleanup,
    create_worker_pool,
    get_shared_lookups,
    load_checkpoint,
    remove_checkpoint,
    save_checkpoint,
)

logger = logging.getLogger(__name__)

# Chunk size for M3/M4 processing loop (rows per iteration)
_M3M4_CHUNK_SIZE = 5_000

# ============================================================
# Constants
# ============================================================

M1_TIPOS: set[str] = {"ADICION EN EL VALOR", "REDUCCION EN EL VALOR"}
M2_TIPOS: set[str] = {"EXTENSION"}


# ============================================================
# Internal helpers
# ============================================================

def _load_contratos_base(
    monitor: MemoryMonitor | None = None,
    checkpoint_path: Path | None = None,
) -> pd.DataFrame:
    """Load the contratos base DataFrame with deduplication by ID Contrato.

    Streams all contratos chunks and selects the columns needed for label
    construction. Duplicate rows sharing the same ID Contrato are collapsed
    to a single row (keep first occurrence).

    When *monitor* is provided, memory pressure is checked before each chunk:
    - ``'warning'``: run ``gc.collect()`` to free unreachable objects.
    - ``'critical'``: retry after aggressive GC; abort with an empty checkpoint
      if pressure remains.

    Args:
        monitor: Optional :class:`~sip_engine.shared.memory.MemoryMonitor`.
        checkpoint_path: Checkpoint file path (used only when aborting on
            critical memory to signal that the run started).

    Returns:
        DataFrame with columns: ID Contrato, TipoDocProveedor, Documento Proveedor.
        One row per unique contract ID.
    """
    needed_cols = ["ID Contrato", "TipoDocProveedor", "Documento Proveedor", "Dias adicionados"]
    chunks: list[pd.DataFrame] = []

    for chunk in load_contratos():
        if monitor:
            status = monitor.check()
            if status == "warning":
                gc.collect()
                logger.warning(
                    "Memory warning during contratos load: RSS=%.2fGB / budget=%.2fGB — "
                    "running GC",
                    monitor.current_usage_bytes() / (1024 ** 3),
                    monitor.budget_bytes / (1024 ** 3),
                )
            elif status == "critical":
                gc.collect()
                if monitor.check() == "critical":
                    rss_gb = monitor.current_usage_bytes() / (1024 ** 3)
                    budget_gb = monitor.budget_bytes / (1024 ** 3)
                    if checkpoint_path is not None:
                        save_checkpoint([], checkpoint_path)
                    raise MemoryError(
                        f"RAM budget exceeded during contratos load: "
                        f"{rss_gb:.2f}GB used / {budget_gb:.2f}GB budget. "
                        f"Increase max_ram_gb to >{budget_gb:.0f}GB and retry."
                    )
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
# Multiprocessing worker (module-level for picklability)
# ============================================================

# Output columns produced by the M3/M4 pass
_LABELS_OUTPUT_COLS: list[str] = [
    "ID Contrato",
    "M1", "M2", "M3", "M4",
    "TipoDocProveedor_norm",
    "DocProveedor_norm",
]


def _process_labels_chunk(chunk: pd.DataFrame) -> list[dict]:
    """Process a contratos chunk: compute M3/M4 labels per row.

    Accesses ``boletines_set`` from the module-global shared lookups dict
    (populated by the pool initializer via :func:`~sip_engine.shared.memory._init_worker`).

    Args:
        chunk: Sub-DataFrame of the contratos base with M1/M2 already assigned,
            columns include: ID Contrato, M1, M2, TipoDocProveedor, Documento Proveedor.

    Returns:
        List of dicts, each representing one output row with M3/M4 computed.
    """
    shared = get_shared_lookups()
    boletines_set: set[tuple[str, str]] = shared["boletines_set"]

    chunk_result = _compute_m3_m4(chunk, boletines_set)
    chunk_out = chunk_result[_LABELS_OUTPUT_COLS].rename(columns={"ID Contrato": "id_contrato"})
    return chunk_out.to_dict("records")


# ============================================================
# Public API
# ============================================================

def build_labels(force: bool = False, n_jobs: int = 1, max_ram_gb: int | None = None) -> Path:
    """Build M1/M2/M3/M4 binary labels from source data and save to parquet.

    M1 = 1 if contract has at least one value amendment (ADICION EN EL VALOR
         or REDUCCION EN EL VALOR) in adiciones.csv.
    M2 = 1 if contract has at least one time extension (EXTENSION) in adiciones.csv
         OR has non-zero "Dias adicionados" in contratos_SECOP.csv.
    M3 = 1 if contract provider is in boletines.csv (Comptroller fiscal liability).
    M4 = 1 if contract provider is found in the RCAC index (corruption antecedents).
    Null for M3/M4 when provider document ID is missing or malformed.

    When *max_ram_gb* is provided, a :class:`~sip_engine.shared.memory.MemoryMonitor`
    enforces the budget:
    - At 90% (warning): ``gc.collect()`` is called between processing chunks.
    - At 100% (critical): processed rows are saved as a checkpoint and execution
      aborts with an actionable message.  Restarting with ``force=False`` resumes
      from the last saved row.

    Args:
        force: If True, rebuild even if labels.parquet already exists.
        n_jobs: Number of parallel jobs (reserved for future use).
        max_ram_gb: RAM budget in GB.  ``None`` disables monitoring (default
            behaviour identical to pre-Phase 17).

    Returns:
        Path to the labels.parquet file.

    Raises:
        FileNotFoundError: If the RCAC index has not been built yet.
        MemoryError: If RAM budget is exceeded and the checkpoint has been saved.
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

    # ---- MemoryMonitor setup ----
    monitor: MemoryMonitor | None = MemoryMonitor(max_ram_gb) if max_ram_gb is not None else None

    # ---- Checkpoint support ----
    checkpoint_path: Path = settings.artifacts_labels_dir / "_checkpoint.parquet"
    checkpoint_df, processed_ids = load_checkpoint(checkpoint_path)
    prior_rows: list[dict] = checkpoint_df.to_dict("records") if not checkpoint_df.empty else []
    if processed_ids:
        logger.info(
            "Resuming from checkpoint: %d rows already processed", len(processed_ids)
        )

    # ---- Load contratos base (memory-checked per chunk) ----
    df = _load_contratos_base(monitor=monitor, checkpoint_path=checkpoint_path)
    contratos_ids: set[str] = set(df["ID Contrato"].dropna().tolist())

    # ---- Build M1/M2 sets from adiciones ----
    m1_contracts, m2_contracts = _build_m1_m2_sets(contratos_ids)

    # ---- Augment M2 from "Dias adicionados" column (primary M2 source) ----
    m2_before = len(m2_contracts)
    dias_col = df["Dias adicionados"].astype(str).str.replace(",", "", regex=False)
    dias_numeric = pd.to_numeric(dias_col, errors="coerce").fillna(0)
    dias_m2_ids = set(df.loc[dias_numeric != 0, "ID Contrato"].tolist())
    m2_contracts = m2_contracts | dias_m2_ids
    logger.info(
        "M2 from Dias adicionados: %d contracts (%d new beyond EXTENSION)",
        len(dias_m2_ids),
        len(m2_contracts) - m2_before,
    )

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

    # ---- Lifecycle cleanup: M1/M2 sets no longer needed ----
    del m1_contracts, m2_contracts, dias_m2_ids
    cleanup()

    # ---- Build boletines set ----
    boletines_set = _build_boletines_set()

    # ---- Compute M3/M4 in chunks with memory monitoring ----
    # Filter to rows that have not been processed by a prior (checkpointed) run
    df_unprocessed = df[~df["ID Contrato"].isin(processed_ids)] if processed_ids else df

    current_chunk_size = _M3M4_CHUNK_SIZE
    all_rows: list[dict] = list(prior_rows)

    if n_jobs > 1:
        # ---- Multiprocessing path (n_jobs > 1) ----
        lookups = {"boletines_set": boletines_set}
        pool, lookups_path = create_worker_pool(n_jobs, lookups)
        try:
            def _label_chunk_gen():  # type: ignore[return]
                for i in range(0, len(df_unprocessed), _M3M4_CHUNK_SIZE):
                    yield df_unprocessed.iloc[i : i + _M3M4_CHUNK_SIZE].copy()

            for chunk_results in pool.imap_unordered(_process_labels_chunk, _label_chunk_gen()):
                all_rows.extend(chunk_results)
                if monitor:
                    status = monitor.check()
                    if status == "warning":
                        gc.collect()
                        logger.warning(
                            "Memory warning (M3/M4 MP loop): RSS=%.2fGB / budget=%.2fGB — GC",
                            monitor.current_usage_bytes() / (1024 ** 3),
                            monitor.budget_bytes / (1024 ** 3),
                        )
                    elif status == "critical":
                        gc.collect()
                        if monitor.check() == "critical":
                            pool.terminate()
                            save_checkpoint(all_rows, checkpoint_path)
                            rss_gb = monitor.current_usage_bytes() / (1024 ** 3)
                            budget_gb = monitor.budget_bytes / (1024 ** 3)
                            raise MemoryError(
                                f"RAM budget exceeded during M3/M4 computation (MP): "
                                f"{rss_gb:.2f}GB used / {budget_gb:.2f}GB budget. "
                                f"Checkpoint saved ({len(all_rows)} rows). "
                                f"Increase max_ram_gb to >{budget_gb:.0f}GB and retry."
                            )
        finally:
            pool.close()
            pool.join()
            if lookups_path:
                try:
                    Path(lookups_path).unlink()
                except FileNotFoundError:
                    pass
    else:
        # ---- Single-process path (n_jobs <= 1) ----
        for start in range(0, len(df_unprocessed), current_chunk_size):
            if monitor:
                status = monitor.check()
                if status == "warning":
                    current_chunk_size = adaptive_chunk_size(monitor, current_chunk_size)
                    gc.collect()
                    logger.warning(
                        "Memory warning (M3/M4 loop): RSS=%.2fGB / budget=%.2fGB — "
                        "adaptive chunk_size=%d",
                        monitor.current_usage_bytes() / (1024 ** 3),
                        monitor.budget_bytes / (1024 ** 3),
                        current_chunk_size,
                    )
                elif status == "critical":
                    gc.collect()
                    if monitor.check() == "critical":
                        save_checkpoint(all_rows, checkpoint_path)
                        rss_gb = monitor.current_usage_bytes() / (1024 ** 3)
                        budget_gb = monitor.budget_bytes / (1024 ** 3)
                        raise MemoryError(
                            f"RAM budget exceeded during M3/M4 computation: "
                            f"{rss_gb:.2f}GB used / {budget_gb:.2f}GB budget. "
                            f"Checkpoint saved ({len(all_rows)} rows). "
                            f"Increase max_ram_gb to >{budget_gb:.0f}GB and retry."
                        )

            chunk_df = df_unprocessed.iloc[start : start + current_chunk_size].copy()
            chunk_result = _compute_m3_m4(chunk_df, boletines_set)
            chunk_out = chunk_result[_LABELS_OUTPUT_COLS].rename(columns={"ID Contrato": "id_contrato"})
            all_rows.extend(chunk_out.to_dict("records"))

    # ---- Lifecycle cleanup: boletines_set no longer needed ----
    del boletines_set
    cleanup()

    # ---- Build output DataFrame from accumulated rows ----
    out = pd.DataFrame(all_rows)
    del all_rows
    cleanup()

    # Restore nullable Int8 dtypes lost by dict round-trip
    for col in ["M1", "M2", "M3", "M4"]:
        if col in out.columns:
            out[col] = out[col].astype("Int8")

    # ---- Write to parquet ----
    out.to_parquet(settings.labels_path, index=False, engine="pyarrow")

    # ---- Remove checkpoint on successful completion ----
    remove_checkpoint(checkpoint_path)

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
