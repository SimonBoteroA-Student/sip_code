"""Shared feature engineering pipeline for SIP.

Single code path for both offline batch processing and online per-contract
inference (FEAT-07 train-serve parity). Enforces exclusions for post-execution
variables (FEAT-08) and RCAC-derived features (FEAT-09).

Feature column order: alphabetical within each category (A → B → C).
Total: 30 features. Category D (IRIC, 4 features) added in Phase 6.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from sip_engine.config import get_settings
from sip_engine.data.rcac_builder import is_malformed, normalize_numero, normalize_tipo
from sip_engine.features.category_a import compute_category_a
from sip_engine.features.category_b import compute_category_b
from sip_engine.features.category_c import compute_category_c
from sip_engine.features.encoding import (
    apply_encoding,
    build_encoding_mappings,
    load_encoding_mappings,
)
from sip_engine.features.provider_history import (
    build_provider_history_index,
    lookup_provider_history,
)

logger = logging.getLogger(__name__)

# =============================================================================
# EXPLICITLY EXCLUDED — POST-EXECUTION VARIABLES (FEAT-08)
# These columns exist in the source data but MUST NOT appear in feature vectors:
# - Fecha de Inicio de Ejecucion (from contratos)
# - Fecha de Fin de Ejecucion (from contratos)
# - Valor Facturado, Valor Pagado, Valor Pendiente de Pago (payment data)
# - ALL columns from ejecucion_contratos.csv
# Rationale: SIP is an early-detection system. Post-execution data defeats
# the purpose by using information unavailable at contract signing time.
# =============================================================================

# =============================================================================
# EXPLICITLY EXCLUDED — RCAC-DERIVED FEATURES (FEAT-09)
# These features are NOT included in the XGBoost feature vector:
# - proveedor_en_rcac
# - proveedor_responsable_fiscal
# - en_siri
# - en_multas_secop
# - en_colusiones
# Rationale: RCAC is used for labels (M3/M4), background checks, and API
# response only. Including RCAC in model inputs risks circular leakage.
# =============================================================================

FEATURE_COLUMNS: list[str] = [
    # Category A (10 features) — contract characteristics
    "departamento_cat", "es_contratacion_directa", "es_regimen_especial",
    "es_servicios_profesionales", "modalidad_contratacion_cat", "origen_recursos_cat",
    "tiene_justificacion_modalidad", "tipo_contrato_cat", "unspsc_categoria",
    "valor_contrato",
    # Category B (9 features) — temporal
    "dias_a_proxima_eleccion", "dias_decision", "dias_firma_a_inicio",
    "dias_proveedor_registrado", "dias_publicidad", "duracion_contrato_dias",
    "firma_posterior_a_inicio", "mes_firma", "trimestre_firma",
    # Category C (11 features) — provider/competition
    "num_actividades_economicas", "num_contratos_previos_depto",
    "num_contratos_previos_nacional", "num_ofertas_recibidas", "num_proponentes",
    "num_retrasos_previos", "num_sobrecostos_previos", "proponente_unico",
    "tipo_persona_proveedor", "valor_total_contratos_previos_depto",
    "valor_total_contratos_previos_nacional",
    # Category D (4 features) — IRIC aggregate scores (Phase 6, FEAT-04)
    # Note: kurtosis (curtosis_licitacion) and DRN (diferencia_relativa_norm) from
    # bid_stats are NOT included here — they are NaN-heavy (~60% of contracts have
    # 0 or 1 bids via direct contracting). They are stored in iric_scores.parquet
    # artifact but excluded from XGBoost feature vectors.
    "iric_anomalias", "iric_competencia", "iric_score", "iric_transparencia",
]

# Critical fields — rows missing ANY of these are dropped (CONTEXT.md decision)
REQUIRED_FIELDS: list[str] = [
    "Fecha de Firma",
    "Valor del Contrato",
    "Tipo de Contrato",
    "Modalidad de Contratacion",
]


# =============================================================================
# Private helpers
# =============================================================================


def _parse_proveedor_date(date_str: str | None) -> datetime.date | None:
    """Parse proveedores_registrados Fecha Creación in MM/DD/YYYY format."""
    if date_str is None:
        return None
    s = str(date_str).strip()
    if not s:
        return None
    # Try MM/DD/YYYY first (proveedores format), then ISO
    parts = s.split("/")
    if len(parts) == 3:
        try:
            month, day, year = int(parts[0]), int(parts[1]), int(parts[2][:4])
            return datetime.date(year, month, day)
        except (ValueError, IndexError):
            pass
    # Fall back to ISO format
    try:
        return datetime.date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _to_date(value: Any) -> datetime.date | None:
    """Coerce a value to datetime.date, returning None on failure."""
    if value is None:
        return None
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.datetime):
        return value.date()
    import math
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


def _build_procesos_lookup() -> dict[str, dict]:
    """Stream procesos_SECOP.csv and build a dict keyed on ID del Portafolio.

    Returns:
        Dict mapping portafolio_id (str) -> row dict with procesos fields.
    """
    from sip_engine.data.loaders import load_procesos

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
            # Build row dict with available columns only
            row_dict = {col: row.get(col) for col in available if col != "ID del Portafolio"}
            lookup[portafolio_id] = row_dict

    logger.info("Procesos lookup built: %d entries from %d rows", len(lookup), rows_loaded)
    return lookup


def _build_proveedores_lookup() -> dict[str, datetime.date | None]:
    """Stream proveedores_registrados.csv and build a dict keyed on normalized NIT.

    Returns:
        Dict mapping normalized_nit (str) -> Fecha Creación as datetime.date (or None).
    """
    from sip_engine.data.loaders import load_proveedores

    lookup: dict[str, datetime.date | None] = {}
    rows_loaded = 0

    for chunk in load_proveedores():
        for _, row in chunk.iterrows():
            rows_loaded += 1
            raw_nit = row.get("NIT")
            if raw_nit is None or str(raw_nit).strip() in ("nan", "None", ""):
                continue
            norm_nit = normalize_numero(str(raw_nit))
            if is_malformed(norm_nit):
                continue
            fecha_creacion_raw = row.get("Fecha Creación")
            fecha_creacion = _parse_proveedor_date(
                None if pd.isna(fecha_creacion_raw) else str(fecha_creacion_raw)
            )
            # Only store if not already present (first registration wins)
            if norm_nit not in lookup:
                lookup[norm_nit] = fecha_creacion

    logger.info("Proveedores lookup built: %d entries from %d rows", len(lookup), rows_loaded)
    return lookup


def _build_num_actividades_lookup() -> dict[tuple[str, str], int]:
    """Build a dict of distinct UNSPSC segments per provider from full contratos.

    This is a static attribute (not as-of-date filtered) — represents the
    breadth of economic activities across a provider's total history.

    Returns:
        Dict mapping (tipo_norm, num_norm) -> count of distinct UNSPSC segments.
    """
    from sip_engine.data.loaders import load_contratos

    # Accumulate sets of segments per provider key
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

            # Extract segment (first 2 chars after "V1." prefix)
            code_str = str(categoria_raw).strip()
            if code_str.upper().startswith("V1."):
                numeric_part = code_str[3:]
            else:
                numeric_part = code_str
            segment = numeric_part[:2] if len(numeric_part) >= 2 else ""

            if segment and segment.isdigit():
                provider_segments.setdefault(key, set()).add(segment)

    result = {key: len(segments) for key, segments in provider_segments.items()}
    logger.info("Num actividades lookup built: %d providers", len(result))
    return result


def _is_missing_required(row: dict, reason_counts: dict[str, int]) -> bool:
    """Return True if the row is missing any REQUIRED_FIELDS. Update reason_counts."""
    for field in REQUIRED_FIELDS:
        val = row.get(field)
        if val is None or (isinstance(val, float) and pd.isna(val)) or str(val).strip() == "":
            reason_counts[field] = reason_counts.get(field, 0) + 1
            return True
    return False


# =============================================================================
# Public API
# =============================================================================


def build_features(force: bool = False) -> Path:
    """Build features.parquet from all source data.

    Offline batch path — processes all contratos and writes features.parquet
    for model training. Enforces post-execution (FEAT-08) and RCAC (FEAT-09)
    exclusions. Drops rows missing critical fields with INFO-level logging.

    Args:
        force: If True, rebuild even if features.parquet already exists.

    Returns:
        Path to the written features.parquet file.

    Raises:
        FileNotFoundError: If labels.parquet does not exist (required for
            provider history M1/M2 label integration).
    """
    settings = get_settings()
    features_path = settings.features_path

    # Check labels.parquet exists — required for provider history M1/M2
    labels_path = settings.labels_path
    if not labels_path.exists():
        raise FileNotFoundError(
            f"labels.parquet not found at {labels_path}. "
            "Run build_labels() first — provider history requires M1/M2 labels."
        )

    if features_path.exists() and not force:
        logger.info("Using cached features.parquet at %s", features_path)
        return features_path

    logger.info("Building feature matrix...")

    # ---- Step 1: Build provider history index ----
    build_provider_history_index(force=force)

    # ---- Step 2: Build lookup dicts from procesos and proveedores ----
    logger.info("Building procesos lookup...")
    procesos_lookup = _build_procesos_lookup()

    logger.info("Building proveedores lookup...")
    proveedores_lookup = _build_proveedores_lookup()

    # ---- Step 3: Build num_actividades_economicas dict ----
    logger.info("Building num_actividades lookup...")
    num_actividades_lookup = _build_num_actividades_lookup()

    # ---- Step 3b: Load IRIC thresholds and bid stats for Category D ----
    # Lazy import to avoid circular dependency at module level
    from sip_engine.iric.pipeline import compute_iric as _compute_iric
    from sip_engine.iric.thresholds import (
        load_iric_thresholds as _load_iric_thresholds,
        reset_iric_thresholds_cache as _reset_iric_cache,
    )
    from sip_engine.iric.bid_stats import build_bid_stats_lookup as _build_bid_stats_lookup

    _iric_thresholds: dict | None = None
    _bid_stats_lookup: dict = {}

    # Check path directly to avoid stale module-level cache from prior test/run
    _iric_thresholds_path = settings.iric_thresholds_path
    if _iric_thresholds_path.exists():
        try:
            _reset_iric_cache()  # Ensure we load from the correct path for this settings instance
            _iric_thresholds = _load_iric_thresholds(_iric_thresholds_path)
            logger.info("IRIC thresholds loaded for Category D computation")
        except Exception as exc:
            logger.warning("IRIC thresholds could not be loaded (%s) — Category D will be NaN", exc)
    else:
        logger.warning(
            "IRIC thresholds not found at %s — Category D features will be NaN in features.parquet. "
            "Run build_iric() first to compute IRIC thresholds.",
            _iric_thresholds_path,
        )

    if _iric_thresholds is not None:
        logger.info("Building bid stats lookup for Category D...")
        _bid_stats_lookup = _build_bid_stats_lookup()

    # ---- Step 4: Stream contratos and compute all 34 features ----
    from sip_engine.data.loaders import load_contratos

    all_rows: list[dict] = []
    reason_counts: dict[str, int] = {}
    rows_processed = 0
    rows_dropped = 0

    for chunk in load_contratos():
        for _, row in chunk.iterrows():
            rows_processed += 1

            # Drop if missing required fields
            row_dict = row.to_dict()
            if _is_missing_required(row_dict, reason_counts):
                rows_dropped += 1
                continue

            # --- Contract signing date ---
            firma_date = _to_date(row_dict.get("Fecha de Firma"))
            if firma_date is None:
                reason_counts["Fecha de Firma (parse error)"] = (
                    reason_counts.get("Fecha de Firma (parse error)", 0) + 1
                )
                rows_dropped += 1
                continue

            # --- Procesos data lookup via Proceso de Compra -> ID del Portafolio ---
            proceso_id = str(row_dict.get("Proceso de Compra", "")).strip()
            procesos_data: dict | None = procesos_lookup.get(proceso_id)

            # Inject the contract's Fecha de Firma into procesos_data for dias_decision
            if procesos_data is not None:
                procesos_data = dict(procesos_data)  # shallow copy
                procesos_data["Fecha de Firma"] = firma_date

            # --- Proveedor registration date lookup ---
            raw_tipo = row_dict.get("TipoDocProveedor")
            raw_num = row_dict.get("Documento Proveedor")
            num_norm = normalize_numero(raw_num)
            proveedor_fecha_creacion: datetime.date | None = (
                proveedores_lookup.get(num_norm) if not is_malformed(num_norm) else None
            )

            # --- Category A: 10 contract features ---
            cat_a = compute_category_a(row_dict)

            # --- Category B: 9 temporal features ---
            cat_b = compute_category_b(row_dict, procesos_data, proveedor_fecha_creacion)

            # --- Category C: 11 provider/competition features ---
            tipo_norm = normalize_tipo(raw_tipo)
            provider_history = lookup_provider_history(
                tipo_doc=raw_tipo,
                num_doc=raw_num,
                as_of_date=firma_date,
                departamento=str(row_dict.get("Departamento", "") or "").strip(),
            )
            provider_key = (tipo_norm, num_norm)
            num_actividades = num_actividades_lookup.get(provider_key, 0)
            cat_c = compute_category_c(row_dict, procesos_data, provider_history, num_actividades)

            # --- Category D: 4 IRIC aggregate scores ---
            if _iric_thresholds is not None:
                _bid_stats = _bid_stats_lookup.get(proceso_id)
                _bid_values = None
                if _bid_stats is not None:
                    # Pass bid values indirectly — bid_stats already computed;
                    # use compute_iric with pre-computed result by calling without bid_values
                    pass  # scores computed below without raw bid_values (already in lookup)
                iric_result = _compute_iric(
                    contract_row=row_dict,
                    procesos_data=procesos_data,
                    provider_history=provider_history,
                    thresholds=_iric_thresholds,
                    num_actividades=num_actividades,
                    bid_values=None,  # bid stats stored separately in iric_scores.parquet
                )
                cat_d = {
                    "iric_anomalias": iric_result["iric_anomalias"],
                    "iric_competencia": iric_result["iric_competencia"],
                    "iric_score": iric_result["iric_score"],
                    "iric_transparencia": iric_result["iric_transparencia"],
                }
            else:
                cat_d = {
                    "iric_anomalias": float("nan"),
                    "iric_competencia": float("nan"),
                    "iric_score": float("nan"),
                    "iric_transparencia": float("nan"),
                }

            # --- Merge all 34 features + id_contrato ---
            feature_row = {
                "id_contrato": str(row_dict.get("ID Contrato", "")),
                **cat_a,
                **cat_b,
                **cat_c,
                **cat_d,
            }
            all_rows.append(feature_row)

    logger.info(
        "Feature extraction complete: %d rows processed, %d kept, %d dropped",
        rows_processed,
        len(all_rows),
        rows_dropped,
    )
    if reason_counts:
        for reason, count in sorted(reason_counts.items()):
            logger.info("  Dropped %d rows due to missing: %s", count, reason)

    # ---- Step 5: Build DataFrame and encoding mappings ----
    df = pd.DataFrame(all_rows)
    if df.empty:
        raise ValueError(
            f"No feature rows produced: {rows_processed} rows processed, "
            f"{rows_dropped} dropped. Check date formats and required fields."
        )
    df = df.set_index("id_contrato")

    # Build encoding mappings from the full feature DataFrame (batch training mode)
    mappings = build_encoding_mappings(df, force=force)

    # Apply encoding to categorical columns
    df = apply_encoding(df, mappings)

    # ---- Step 6: Select canonical FEATURE_COLUMNS in order ----
    # Only keep columns that are in FEATURE_COLUMNS; add missing ones as NaN
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = float("nan")

    df_out = df[FEATURE_COLUMNS]

    # ---- Step 7: Write to features.parquet via pyarrow ----
    features_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df_out, preserve_index=True)
    pq.write_table(table, features_path)

    logger.info(
        "features.parquet written to %s (%d rows, %d columns)",
        features_path,
        len(df_out),
        len(df_out.columns),
    )
    return features_path


def compute_features(
    contract_row: dict,
    as_of_date: datetime.date,
    procesos_data: dict | None = None,
    proveedor_fecha_creacion: datetime.date | None = None,
    num_actividades: int = 0,
    iric_thresholds: dict | None = None,
    bid_values: list[float] | None = None,
) -> dict:
    """Compute a complete 34-feature vector for a single contract (online inference).

    Uses the same Category A/B/C/D extraction functions as build_features() for
    train-serve parity (FEAT-07). Loads encoding mappings from JSON for consistent
    categorical encoding. Loads provider history index for lookup_provider_history.

    Category D (IRIC): 4 aggregate scores injected after Cat A/B/C. If
    iric_thresholds is not provided, attempts to load from disk via
    load_iric_thresholds(). If thresholds file does not exist, Cat D features
    are set to NaN.

    Args:
        contract_row: Dict with raw contratos column values.
        as_of_date: Date of the contract being evaluated (used as temporal cutoff
            for provider history lookup — typically Fecha de Firma).
        procesos_data: Procesos row dict for this contract's process, or None.
            If provided, "Fecha de Firma" key will be set to as_of_date if absent.
        proveedor_fecha_creacion: Provider registration date, or None.
        num_actividades: Count of distinct UNSPSC segments for this provider
            (static attribute — precomputed from full history).
        iric_thresholds: Pre-loaded IRIC thresholds dict, or None to load from disk.
            Pass explicitly for performance when computing many contracts at once.
        bid_values: Optional list of bid amounts for this process (for kurtosis/DRN).
            The 4 IRIC scores injected into FEATURE_COLUMNS do NOT include
            kurtosis/DRN — those are only in the iric_scores.parquet artifact.

    Returns:
        Dict with exactly FEATURE_COLUMNS keys (34 total), values encoded as
        integers/floats. Category D values are NaN if thresholds unavailable.
    """
    # Inject signing date into procesos_data for dias_decision calculation
    if procesos_data is not None and "Fecha de Firma" not in procesos_data:
        procesos_data = dict(procesos_data)
        procesos_data["Fecha de Firma"] = as_of_date

    # Load encoding mappings (inference-time)
    mappings = load_encoding_mappings()

    # Category A: 10 contract features
    cat_a = compute_category_a(contract_row)

    # Category B: 9 temporal features
    cat_b = compute_category_b(contract_row, procesos_data, proveedor_fecha_creacion)

    # Category C: 11 provider/competition features
    raw_tipo = contract_row.get("TipoDocProveedor")
    raw_num = contract_row.get("Documento Proveedor")
    departamento = str(contract_row.get("Departamento", "") or "").strip()

    provider_history = lookup_provider_history(
        tipo_doc=raw_tipo,
        num_doc=raw_num,
        as_of_date=as_of_date,
        departamento=departamento,
    )
    cat_c = compute_category_c(contract_row, procesos_data, provider_history, num_actividades)

    # Category D: 4 IRIC aggregate scores
    # Lazy import to avoid circular dependency (iric.pipeline imports features.provider_history)
    try:
        from sip_engine.iric.pipeline import compute_iric
        from sip_engine.iric.thresholds import load_iric_thresholds

        thresholds = iric_thresholds
        if thresholds is None:
            # Check path directly to avoid stale module-level cache
            _thresh_path = get_settings().iric_thresholds_path
            if not _thresh_path.exists():
                raise FileNotFoundError(f"IRIC thresholds not found at {_thresh_path}")
            thresholds = load_iric_thresholds(_thresh_path)

        iric_result = compute_iric(
            contract_row=contract_row,
            procesos_data=procesos_data,
            provider_history=provider_history,
            thresholds=thresholds,
            num_actividades=num_actividades,
            bid_values=bid_values,
        )
        cat_d = {
            "iric_anomalias": iric_result["iric_anomalias"],
            "iric_competencia": iric_result["iric_competencia"],
            "iric_score": iric_result["iric_score"],
            "iric_transparencia": iric_result["iric_transparencia"],
        }
    except FileNotFoundError:
        # Thresholds file not yet built — return NaN for Cat D
        logger.warning(
            "IRIC thresholds not found — Category D features will be NaN. "
            "Run build_iric() to generate thresholds."
        )
        cat_d = {
            "iric_anomalias": float("nan"),
            "iric_competencia": float("nan"),
            "iric_score": float("nan"),
            "iric_transparencia": float("nan"),
        }

    # Merge all 34 features
    features = {**cat_a, **cat_b, **cat_c}

    # Apply encoding via single-row DataFrame, then extract back to dict
    df_single = pd.DataFrame([features])
    df_encoded = apply_encoding(df_single, mappings)

    result: dict = {}
    for col in FEATURE_COLUMNS:
        if col in cat_d:
            result[col] = cat_d[col]
        else:
            val = df_encoded.iloc[0].get(col, float("nan")) if col in df_encoded.columns else float("nan")
            result[col] = val

    return result
