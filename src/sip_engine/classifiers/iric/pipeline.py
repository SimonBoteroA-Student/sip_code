"""IRIC pipeline — batch orchestrator and online inference function.

Connects the IRIC calculator (calculator.py) and bid statistics (bid_stats.py)
into a production pipeline. This module is the entry point for computing IRIC
scores for all contracts (batch) or a single contract (online inference).

Batch path (build_iric):
  1. Calibrate/load thresholds from features data
  2. Build bid stats lookup from ofertas (streaming)
  3. Build procesos lookup (streaming)
  4. Build provider history index
  5. Build num_actividades lookup from contratos
  6. Stream contratos, compute all 11 components + 4 scores per row
  7. Write iric_scores.parquet with 11 components + 4 scores + kurtosis + DRN

Online path (compute_iric):
  Single-contract function with identical logic for train-serve parity (FEAT-07).

FEAT-04, IRIC-01 through IRIC-08
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from sip_engine.shared.config import get_settings
from sip_engine.classifiers.iric.bid_stats import build_bid_stats_lookup, compute_bid_stats
from sip_engine.classifiers.iric.calculator import compute_iric_components, compute_iric_scores
from sip_engine.classifiers.iric.thresholds import (
    calibrate_iric_thresholds,
    load_iric_thresholds,
    save_iric_thresholds,
)

logger = logging.getLogger(__name__)

# Columns included in the iric_scores.parquet artifact
# 11 components + 4 aggregate scores + 2 bid anomaly stats + 1 count
_IRIC_ARTIFACT_COLUMNS: list[str] = [
    "id_contrato",
    # Competition components (6)
    "unico_proponente",
    "proveedor_multiproposito",
    "historial_proveedor_alto",
    "contratacion_directa",
    "regimen_especial",
    "periodo_publicidad_extremo",
    # Transparency components (2)
    "datos_faltantes",
    "periodo_decision_extremo",
    # Anomaly components (3)
    "proveedor_sobrecostos_previos",
    "proveedor_retrasos_previos",
    "ausencia_proceso",
    # Aggregate scores (4)
    "iric_score",
    "iric_competencia",
    "iric_transparencia",
    "iric_anomalias",
    # Bid anomaly stats — NOT in FEATURE_COLUMNS (NaN-heavy) but stored in artifact
    "curtosis_licitacion",
    "diferencia_relativa_norm",
    "n_bids",
]

# Default bid stats returned when a process has no ofertas entry
_DEFAULT_BID_STATS: dict[str, Any] = {
    "curtosis_licitacion": float("nan"),
    "diferencia_relativa_norm": float("nan"),
    "n_bids": 0,
}


# =============================================================================
# Private helpers
# =============================================================================


def _build_iric_procesos_lookup() -> dict[str, dict]:
    """Stream procesos_SECOP.csv and build a dict keyed on ID del Portafolio.

    Mirrors features/pipeline.py _build_procesos_lookup() — same fields, same
    pattern. Factoring into a shared helper would require a cross-module
    dependency that is not needed since this is called once per batch run.

    Returns:
        Dict mapping portafolio_id (str) -> row dict with procesos fields.
    """
    from sip_engine.shared.data.loaders import load_procesos

    procesos_needed = {
        "ID del Portafolio",
        "Fecha de Publicacion del Proceso",
        "Fecha de Recepcion de Respuestas",
        "Fecha de Ultima Publicación",
        "Respuestas al Procedimiento",
        "Proveedores Unicos con Respuestas",
        "Fecha Adjudicacion",
    }

    lookup: dict[str, dict] = {}
    rows_loaded = 0

    for chunk in load_procesos():
        available = procesos_needed & set(chunk.columns)
        for _, row in chunk.iterrows():
            rows_loaded += 1
            portafolio_id = str(row.get("ID del Portafolio", "")).strip()
            if not portafolio_id or portafolio_id in ("nan", "None", ""):
                continue
            row_dict = {col: row.get(col) for col in available if col != "ID del Portafolio"}
            lookup[portafolio_id] = row_dict

    logger.info("IRIC procesos lookup built: %d entries from %d rows", len(lookup), rows_loaded)
    return lookup


def _build_iric_num_actividades_lookup() -> dict[tuple[str, str], int]:
    """Build distinct UNSPSC segments per provider.

    Mirrors features/pipeline.py _build_num_actividades_lookup().

    Returns:
        Dict mapping (tipo_norm, num_norm) -> count of distinct UNSPSC segments.
    """
    from sip_engine.shared.data.loaders import load_contratos
    from sip_engine.shared.data.rcac_builder import is_malformed, normalize_numero, normalize_tipo

    provider_segments: dict[tuple[str, str], set[str]] = {}

    for chunk in load_contratos():
        for _, row in chunk.iterrows():
            raw_tipo = row.get("TipoDocProveedor")
            raw_num = row.get("Documento Proveedor")
            tipo_norm = normalize_tipo(raw_tipo)
            num_norm = normalize_numero(raw_num)

            if is_malformed(num_norm):
                continue

            key = (tipo_norm, num_norm)

            categoria_raw = row.get("Codigo de Categoria Principal")
            if categoria_raw is None or str(categoria_raw).strip() in ("nan", "None", ""):
                continue

            code_str = str(categoria_raw).strip()
            if code_str.upper().startswith("V1."):
                numeric_part = code_str[3:]
            else:
                numeric_part = code_str
            segment = numeric_part[:2] if len(numeric_part) >= 2 else ""

            if segment and segment.isdigit():
                provider_segments.setdefault(key, set()).add(segment)

    result = {key: len(segments) for key, segments in provider_segments.items()}
    logger.info("IRIC num_actividades lookup built: %d providers", len(result))
    return result


def _to_date_iric(value: Any):
    """Coerce a value to datetime.date, returning None on failure."""
    import datetime
    if value is None:
        return None
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        date_str = str(value).strip()[:10]
        return datetime.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass
    # Handle MM/DD/YYYY format common in SECOP CSVs
    try:
        return datetime.datetime.strptime(str(value).strip()[:10], "%m/%d/%Y").date()
    except (ValueError, TypeError):
        return None


# =============================================================================
# Public API
# =============================================================================


def build_iric(force: bool = False, n_jobs: int = 1, max_ram_gb: int | None = None) -> Path:
    """Build iric_scores.parquet from all source data.

    Offline batch path — processes all contratos and writes iric_scores.parquet
    with 11 IRIC components, 4 aggregate scores, kurtosis, DRN, and n_bids
    per contract.

    Args:
        force: If True, rebuild even if iric_scores.parquet already exists.
            Also forces threshold recalibration if thresholds JSON is absent.
        n_jobs: Number of parallel jobs (reserved for Plan 17-02 implementation).
        max_ram_gb: RAM budget in GB (reserved for Plan 17-02 implementation).

    Returns:
        Path to the written iric_scores.parquet file.
    """
    import pandas as pd

    settings = get_settings()
    iric_scores_path = settings.iric_scores_path

    if iric_scores_path.exists() and not force:
        logger.info("Using cached iric_scores.parquet at %s", iric_scores_path)
        return iric_scores_path

    logger.info("Building IRIC scores...")

    # ---- Step 1: Load or calibrate thresholds ----
    if settings.iric_thresholds_path.exists() and not force:
        logger.info("Loading existing IRIC thresholds from %s", settings.iric_thresholds_path)
        thresholds = load_iric_thresholds()
    else:
        logger.info("Calibrating IRIC thresholds from features.parquet...")
        features_path = settings.features_path
        if not features_path.exists():
            raise FileNotFoundError(
                f"features.parquet not found at {features_path}. "
                "Run build_features() first — IRIC threshold calibration requires features."
            )
        df_features = pd.read_parquet(features_path)
        # features.parquet has tipo_contrato_cat (integer-encoded);
        # calibrate_iric_thresholds needs tipo_contrato (raw string).
        # Reverse-decode using encoding mappings.
        if "tipo_contrato" not in df_features.columns and "tipo_contrato_cat" in df_features.columns:
            from sip_engine.classifiers.features.encoding import load_encoding_mappings
            try:
                enc_mappings = load_encoding_mappings()
                tc_mapping = enc_mappings.get("tipo_contrato_cat", {})
                reverse_tc = {v: k for k, v in tc_mapping.items()}
                df_features["tipo_contrato"] = df_features["tipo_contrato_cat"].map(
                    lambda x: reverse_tc.get(int(x), "Otro") if pd.notna(x) else "Otro"
                )
            except FileNotFoundError:
                logger.warning(
                    "Encoding mappings not found — using 'Otro' for all tipo_contrato"
                )
                df_features["tipo_contrato"] = "Otro"
        thresholds = calibrate_iric_thresholds(df_features)
        save_iric_thresholds(thresholds)

    # ---- Step 2: Build bid stats lookup (streaming pass over ofertas) ----
    logger.info("Building bid stats lookup...")
    bid_stats_lookup = build_bid_stats_lookup()

    # ---- Step 3: Build procesos lookup ----
    logger.info("Building procesos lookup...")
    procesos_lookup = _build_iric_procesos_lookup()

    # ---- Step 4: Build provider history index ----
    from sip_engine.classifiers.features.provider_history import (
        build_provider_history_index,
        lookup_provider_history,
    )
    from sip_engine.shared.data.rcac_builder import is_malformed, normalize_numero, normalize_tipo

    logger.info("Loading provider history index...")
    build_provider_history_index(force=False)  # Only build if not cached

    # ---- Step 5: Build num_actividades lookup ----
    logger.info("Building num_actividades lookup...")
    num_actividades_lookup = _build_iric_num_actividades_lookup()

    # ---- Step 6: Stream contratos and compute IRIC per row ----
    from sip_engine.shared.data.loaders import load_contratos

    all_rows: list[dict] = []
    rows_processed = 0

    for chunk in load_contratos():
        for _, row in chunk.iterrows():
            rows_processed += 1
            row_dict = row.to_dict()

            id_contrato = str(row_dict.get("ID Contrato", ""))

            # Contract signing date
            firma_date = _to_date_iric(row_dict.get("Fecha de Firma"))
            if firma_date is None:
                continue  # Skip rows with no valid signing date

            # Procesos data lookup
            proceso_id = str(row_dict.get("Proceso de Compra", "")).strip()
            procesos_data: dict | None = procesos_lookup.get(proceso_id)

            # Inject signing date + compute dias_publicidad / dias_decision
            if procesos_data is not None:
                procesos_data = dict(procesos_data)  # shallow copy
                procesos_data["Fecha de Firma"] = firma_date

                # Compute dias_publicidad if not already present
                if "dias_publicidad" not in procesos_data:
                    import datetime
                    fecha_pub_raw = procesos_data.get("Fecha de Publicacion del Proceso")
                    fecha_recep_raw = procesos_data.get("Fecha de Recepcion de Respuestas")
                    fecha_pub = _to_date_iric(fecha_pub_raw)
                    fecha_recep = _to_date_iric(fecha_recep_raw)
                    if fecha_pub is not None and fecha_recep is not None:
                        procesos_data["dias_publicidad"] = (fecha_recep - fecha_pub).days
                    else:
                        procesos_data["dias_publicidad"] = None

                # Compute dias_decision if not already present
                if "dias_decision" not in procesos_data:
                    fecha_adj_raw = procesos_data.get("Fecha Adjudicacion")
                    fecha_adj = _to_date_iric(fecha_adj_raw)
                    if fecha_adj is not None and firma_date is not None:
                        procesos_data["dias_decision"] = (firma_date - fecha_adj).days
                    else:
                        procesos_data["dias_decision"] = None

            # Provider lookup
            raw_tipo = row_dict.get("TipoDocProveedor")
            raw_num = row_dict.get("Documento Proveedor")
            num_norm = normalize_numero(raw_num)
            tipo_norm = normalize_tipo(raw_tipo)

            departamento = str(row_dict.get("Departamento", "") or "").strip()
            provider_history = lookup_provider_history(
                tipo_doc=raw_tipo,
                num_doc=raw_num,
                as_of_date=firma_date,
                departamento=departamento,
            )

            provider_key = (tipo_norm, num_norm)
            num_actividades = num_actividades_lookup.get(provider_key, 0)

            # Bid stats lookup
            bid_stats = bid_stats_lookup.get(proceso_id, dict(_DEFAULT_BID_STATS))

            # Compute IRIC components + scores
            components = compute_iric_components(
                row=row_dict,
                procesos_data=procesos_data,
                provider_history=provider_history,
                thresholds=thresholds,
                num_actividades=num_actividades,
            )
            scores = compute_iric_scores(components)

            # Collect row
            result_row = {
                "id_contrato": id_contrato,
                **components,
                **scores,
                **bid_stats,
            }
            all_rows.append(result_row)

    logger.info(
        "IRIC computation complete: %d rows processed, %d IRIC rows produced",
        rows_processed,
        len(all_rows),
    )

    # ---- Step 7: Write to iric_scores.parquet via pyarrow ----
    df_out = pd.DataFrame(all_rows)

    # Ensure column ordering and presence
    for col in _IRIC_ARTIFACT_COLUMNS:
        if col not in df_out.columns:
            df_out[col] = float("nan")

    # Set id_contrato as index
    df_out = df_out.set_index("id_contrato")

    iric_scores_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df_out, preserve_index=True)
    pq.write_table(table, iric_scores_path)

    logger.info(
        "iric_scores.parquet written to %s (%d rows, %d columns)",
        iric_scores_path,
        len(df_out),
        len(df_out.columns),
    )
    return iric_scores_path


def compute_iric(
    contract_row: dict,
    procesos_data: dict | None,
    provider_history: dict | None,
    thresholds: dict,
    num_actividades: int = 0,
    bid_values: list[float] | None = None,
) -> dict:
    """Compute IRIC components, scores, and bid stats for a single contract.

    Online inference function — provides train-serve parity (FEAT-07) with the
    batch path in build_iric(). Uses the same compute_iric_components() and
    compute_iric_scores() functions.

    Args:
        contract_row: Dict with raw contratos column values.
        procesos_data: Procesos row dict for this contract's process, or None.
            Should include 'dias_publicidad' and 'dias_decision' (computed by
            Category B in features/pipeline.py and injected before calling here).
        provider_history: Dict from lookup_provider_history(), or None.
        thresholds: Loaded IRIC thresholds dict (from load_iric_thresholds()).
        num_actividades: Count of distinct UNSPSC segments for this provider.
        bid_values: Optional list of bid amounts for this process.
            If provided, kurtosis and DRN are computed.
            If None, curtosis_licitacion and diferencia_relativa_norm are NaN.

    Returns:
        Dict with all 11 components + 4 aggregate scores + bid stats:
        {
            "unico_proponente": int|None,
            ... (11 components total),
            "iric_score": float,
            "iric_competencia": float,
            "iric_transparencia": float,
            "iric_anomalias": float,
            "curtosis_licitacion": float|NaN,
            "diferencia_relativa_norm": float|NaN,
            "n_bids": int,
        }
    """
    components = compute_iric_components(
        row=contract_row,
        procesos_data=procesos_data,
        provider_history=provider_history,
        thresholds=thresholds,
        num_actividades=num_actividades,
    )
    scores = compute_iric_scores(components)

    if bid_values is not None:
        bid_stats = compute_bid_stats(bid_values)
    else:
        bid_stats = dict(_DEFAULT_BID_STATS)

    return {**components, **scores, **bid_stats}
