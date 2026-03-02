"""IRIC component calculator — all 11 binary components and 4 aggregate scores.

Implements the Indice de Riesgo Integrado de Corrupcion (IRIC) as defined in
VigIA/Salazar et al. (2024), Gallego et al. (2021), and Imhof (2018).

11 binary components across 3 dimensions:
  Competition (6): unico_proponente, proveedor_multiproposito,
    historial_proveedor_alto, contratacion_directa, regimen_especial,
    periodo_publicidad_extremo
  Transparency (2): datos_faltantes, periodo_decision_extremo
  Anomaly (3): proveedor_sobrecostos_previos, proveedor_retrasos_previos,
    ausencia_proceso

4 aggregate scores: iric_score, iric_competencia, iric_transparencia, iric_anomalias

NaN handling (VigIA pattern):
  - Components 9/10 return 0 (not None) for new providers with no history
  - Components 1/6/8 return None when procesos_data is None (no process match)
  - Component 11 fires as 1 when procesos_data is None
  - None values are treated as 0 in aggregate score computation

IRIC-01, IRIC-02, IRIC-03, IRIC-06

Usage:
    from sip_engine.iric.calculator import compute_iric_components, compute_iric_scores

    components = compute_iric_components(
        row=contract_row,
        procesos_data=procesos_data,
        provider_history=provider_history,
        thresholds=thresholds,
        num_actividades=num_actividades,
    )
    scores = compute_iric_scores(components)
"""

from __future__ import annotations

import logging
import unicodedata

import pandas as pd

from sip_engine.data.rcac_builder import normalize_numero
from sip_engine.iric.thresholds import get_threshold

logger = logging.getLogger(__name__)

# ============================================================
# Modality strings that trigger competition components
# ============================================================

# Component 4: contratacion_directa
# Handles accent variants (Contratacion / Contratación)
_CONTRATACION_DIRECTA_MODALITIES: frozenset[str] = frozenset(
    [
        "contratacion directa",
        "contratación directa",
        "contratacion directa (con ofertas)",
        "contratación directa (con ofertas)",
    ]
)

# Component 5: regimen_especial
# Handles accent variants
_REGIMEN_ESPECIAL_MODALITIES: frozenset[str] = frozenset(
    [
        "contratacion regimen especial",
        "contratación régimen especial",
        "contratacion regimen especial (con ofertas)",
        "contratación régimen especial (con ofertas)",
    ]
)


def _strip_accents(text: str) -> str:
    """Remove diacritical marks (accents) from a string."""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _normalize_modalidad(raw: str | None) -> str:
    """Normalize modalidad string: lowercase, strip, remove accents."""
    if raw is None:
        return ""
    s = str(raw).strip().lower()
    return _strip_accents(s)


# ============================================================
# Component helpers
# ============================================================


def _compute_datos_faltantes(
    row: dict,
    tipo_contrato: str,
    thresholds: dict,
) -> int:
    """Compute datos_faltantes: 1 if ANY of 3 sub-checks fires.

    Sub-checks (VigIA: presencia_errores):
    1. error_documento: TipoDocProveedor == 'No Definido' OR
       normalized doc < 6 digits OR doc has no digits at all
    2. error_justificacion: Justificacion is None/NaN/empty OR
       equals 'no especificado' (case-insensitive)
    3. error_valor: Valor del Contrato > P99 for tipo_contrato
    """
    # --- Sub-check 1: error_documento ---
    tipo_doc = row.get("TipoDocProveedor")
    doc = row.get("Documento Proveedor")

    error_documento = False

    if str(tipo_doc).strip() == "No Definido":
        error_documento = True
    else:
        doc_str = str(doc) if doc is not None else ""
        try:
            if pd.isna(doc):
                doc_str = ""
        except (TypeError, ValueError):
            pass

        normalized_doc = normalize_numero(doc_str)

        if len(normalized_doc) < 6:
            error_documento = True
        elif not any(c.isdigit() for c in doc_str):
            error_documento = True

    # --- Sub-check 2: error_justificacion ---
    justificacion = row.get("Justificacion Modalidad de Contratacion")

    error_justificacion = False
    if justificacion is None:
        error_justificacion = True
    else:
        try:
            if pd.isna(justificacion):
                error_justificacion = True
        except (TypeError, ValueError):
            pass

    if not error_justificacion:
        just_str = str(justificacion).strip()
        if not just_str or just_str.lower() == "no especificado":
            error_justificacion = True

    # --- Sub-check 3: error_valor ---
    valor = row.get("Valor del Contrato")

    error_valor = False
    p99_valor = get_threshold(thresholds, tipo_contrato, "valor_contrato", "p99")

    if p99_valor is not None and valor is not None:
        try:
            if not pd.isna(valor) and float(valor) > p99_valor:
                error_valor = True
        except (TypeError, ValueError):
            pass

    return 1 if (error_documento or error_justificacion or error_valor) else 0


# ============================================================
# Public API
# ============================================================


def compute_iric_components(
    row: dict,
    procesos_data: dict | None,
    provider_history: dict | None,
    thresholds: dict,
    num_actividades: int = 0,
) -> dict:
    """Compute all 11 binary IRIC component flags.

    Args:
        row: Contract dict (from contratos CSV row). Must include keys:
            - 'Modalidad de Contratacion'
            - 'TipoDocProveedor'
            - 'Documento Proveedor'
            - 'Valor del Contrato'
            - 'Justificacion Modalidad de Contratacion'
            - 'Tipo de Contrato'
        procesos_data: Dict from procesos lookup for this contract's process.
            Must include 'dias_publicidad' and 'dias_decision' (injected by
            pipeline from Category B). None if no process was found.
        provider_history: Dict from lookup_provider_history(). Keys used:
            - 'num_contratos': total prior contracts
            - 'num_sobrecostos': prior cost overruns
            - 'num_retrasos': prior schedule delays
            None for new providers with no prior history.
        thresholds: Loaded IRIC thresholds dict (from load_iric_thresholds()).
        num_actividades: Count of distinct UNSPSC segments for this provider.
            Used for proveedor_multiproposito (from num_actividades_lookup).

    Returns:
        Dict with 11 keys (component names) -> int (0 or 1) or None.
        None indicates data was unavailable (captured by ausencia_proceso).

    NaN handling:
        - Components 1, 6, 8 return None when procesos_data is None
          (missing-process irregularity already captured by component 11).
        - Components 9, 10 return 0 for new providers (VigIA fills NaN as 0).
        - Component 11 returns 1 when procesos_data is None.
    """
    tipo_contrato = str(row.get("Tipo de Contrato", "") or "").strip()
    modalidad_raw = row.get("Modalidad de Contratacion")
    modalidad_norm = _normalize_modalidad(modalidad_raw)

    # ================================================================
    # Component 11: ausencia_proceso (computed first — gates others)
    # ================================================================
    # Fires when no process record is found (VigIA: ausencia_proceso_contratacion).
    # VigIA: "missing process data IS the irregularity."
    ausencia_proceso = 1 if procesos_data is None else 0

    # ================================================================
    # Competition dimension (6 components)
    # ================================================================

    # Component 1: unico_proponente
    # None if procesos_data is None (captured by ausencia_proceso)
    if procesos_data is None:
        unico_proponente = None
    else:
        num_proveedores = procesos_data.get("Proveedores Unicos con Respuestas", 0)
        try:
            num_prov_int = int(num_proveedores) if num_proveedores is not None else 0
        except (TypeError, ValueError):
            num_prov_int = 0
        unico_proponente = 1 if num_prov_int <= 1 else 0

    # Component 2: proveedor_multiproposito
    # Fires when provider bids across more than 1 distinct UNSPSC segment
    proveedor_multiproposito = 1 if num_actividades > 1 else 0

    # Component 3: historial_proveedor_alto
    # 0 for new providers (no history) — VigIA pattern (not NaN)
    if provider_history is None:
        historial_proveedor_alto = 0
    else:
        num_contratos = provider_history.get("num_contratos", 0) or 0
        p95_contratos = get_threshold(
            thresholds, tipo_contrato, "num_contratos_previos_nacional", "p95"
        )
        if p95_contratos is not None and num_contratos > p95_contratos:
            historial_proveedor_alto = 1
        else:
            historial_proveedor_alto = 0

    # Component 4: contratacion_directa
    contratacion_directa = (
        1 if modalidad_norm in _CONTRATACION_DIRECTA_MODALITIES else 0
    )

    # Component 5: regimen_especial
    regimen_especial = (
        1 if modalidad_norm in _REGIMEN_ESPECIAL_MODALITIES else 0
    )

    # Component 6: periodo_publicidad_extremo
    # None when procesos_data is None (captured by ausencia_proceso)
    if procesos_data is None:
        periodo_publicidad_extremo = None
    else:
        dias_pub = procesos_data.get("dias_publicidad")
        if dias_pub is None:
            periodo_publicidad_extremo = None
        else:
            try:
                dias_pub_int = int(float(dias_pub))
            except (TypeError, ValueError):
                dias_pub_int = None

            if dias_pub_int is None:
                periodo_publicidad_extremo = None
            else:
                p99_pub = get_threshold(thresholds, tipo_contrato, "dias_publicidad", "p99")
                if dias_pub_int == 0:
                    periodo_publicidad_extremo = 1
                elif p99_pub is not None and dias_pub_int > p99_pub:
                    periodo_publicidad_extremo = 1
                else:
                    periodo_publicidad_extremo = 0

    # ================================================================
    # Transparency dimension (2 components)
    # ================================================================

    # Component 7: datos_faltantes
    # Combines 3 sub-checks: error_documento, error_justificacion, error_valor
    datos_faltantes = _compute_datos_faltantes(row, tipo_contrato, thresholds)

    # Component 8: periodo_decision_extremo
    # None when procesos_data is None (captured by ausencia_proceso)
    if procesos_data is None:
        periodo_decision_extremo = None
    else:
        dias_dec = procesos_data.get("dias_decision")
        if dias_dec is None:
            periodo_decision_extremo = None
        else:
            try:
                dias_dec_int = int(float(dias_dec))
            except (TypeError, ValueError):
                dias_dec_int = None

            if dias_dec_int is None:
                periodo_decision_extremo = None
            else:
                p95_dec = get_threshold(thresholds, tipo_contrato, "dias_decision", "p95")
                if dias_dec_int == 0:
                    periodo_decision_extremo = 1
                elif p95_dec is not None and dias_dec_int > p95_dec:
                    periodo_decision_extremo = 1
                else:
                    periodo_decision_extremo = 0

    # ================================================================
    # Anomaly dimension (3 components)
    # ================================================================

    # Component 9: proveedor_sobrecostos_previos
    # 0 for new providers (VigIA: "en caso de NaN al ser proveedor nuevo lo suma como 0")
    if provider_history is None:
        proveedor_sobrecostos_previos = 0
    else:
        num_sobrecostos = provider_history.get("num_sobrecostos", 0) or 0
        proveedor_sobrecostos_previos = 1 if num_sobrecostos > 0 else 0

    # Component 10: proveedor_retrasos_previos
    # 0 for new providers (same VigIA pattern as component 9)
    if provider_history is None:
        proveedor_retrasos_previos = 0
    else:
        num_retrasos = provider_history.get("num_retrasos", 0) or 0
        proveedor_retrasos_previos = 1 if num_retrasos > 0 else 0

    # Component 11 already computed above

    return {
        # Competition (6)
        "unico_proponente": unico_proponente,
        "proveedor_multiproposito": proveedor_multiproposito,
        "historial_proveedor_alto": historial_proveedor_alto,
        "contratacion_directa": contratacion_directa,
        "regimen_especial": regimen_especial,
        "periodo_publicidad_extremo": periodo_publicidad_extremo,
        # Transparency (2)
        "datos_faltantes": datos_faltantes,
        "periodo_decision_extremo": periodo_decision_extremo,
        # Anomaly (3)
        "proveedor_sobrecostos_previos": proveedor_sobrecostos_previos,
        "proveedor_retrasos_previos": proveedor_retrasos_previos,
        "ausencia_proceso": ausencia_proceso,
    }


def compute_iric_scores(components: dict) -> dict:
    """Compute the 4 IRIC aggregate scores from 11 binary components.

    Follows VigIA formula: iric = sum(vars_indice) / len(vars_indice)
    None values are treated as 0 (VigIA: sum(axis=1) skips NaN; new providers
    get 0 for history components).

    Components by dimension:
    - Competition (6): unico_proponente, proveedor_multiproposito,
      historial_proveedor_alto, contratacion_directa, regimen_especial,
      periodo_publicidad_extremo
    - Transparency (2): datos_faltantes, periodo_decision_extremo
    - Anomaly (3): proveedor_sobrecostos_previos, proveedor_retrasos_previos,
      ausencia_proceso

    Args:
        components: Dict returned by compute_iric_components().

    Returns:
        Dict with 4 keys:
        - 'iric_score': (1/11) * sum(all 11, None→0)
        - 'iric_competencia': (1/6) * sum(competition 6, None→0)
        - 'iric_transparencia': (1/2) * sum(transparency 2, None→0)
        - 'iric_anomalias': (1/3) * sum(anomaly 3, None→0)
    """

    def _val(v: int | None) -> float:
        """Convert None to 0.0 (VigIA pattern), otherwise float."""
        return 0.0 if v is None else float(v)

    # Competition dimension (indices 1-6)
    competition_keys = [
        "unico_proponente",
        "proveedor_multiproposito",
        "historial_proveedor_alto",
        "contratacion_directa",
        "regimen_especial",
        "periodo_publicidad_extremo",
    ]
    competition_sum = sum(_val(components.get(k)) for k in competition_keys)

    # Transparency dimension (indices 7-8)
    transparency_keys = [
        "datos_faltantes",
        "periodo_decision_extremo",
    ]
    transparency_sum = sum(_val(components.get(k)) for k in transparency_keys)

    # Anomaly dimension (indices 9-11)
    anomaly_keys = [
        "proveedor_sobrecostos_previos",
        "proveedor_retrasos_previos",
        "ausencia_proceso",
    ]
    anomaly_sum = sum(_val(components.get(k)) for k in anomaly_keys)

    total_sum = competition_sum + transparency_sum + anomaly_sum

    return {
        "iric_score": total_sum / 11.0,
        "iric_competencia": competition_sum / 6.0,
        "iric_transparencia": transparency_sum / 2.0,
        "iric_anomalias": anomaly_sum / 3.0,
    }
