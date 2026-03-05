"""Category A feature extractor: contract-level features (FEAT-01).

Produces 10 features from raw contratos row values:
  1. valor_contrato           — contract value (float passthrough)
  2. tipo_contrato_cat        — contract type (categorical, encoded downstream)
  3. modalidad_contratacion_cat — procurement modality (categorical)
  4. departamento_cat         — department (categorical)
  5. origen_recursos_cat      — funding source (categorical)
  6. es_contratacion_directa  — 1 if modality is "contratacion directa"
  7. es_regimen_especial      — 1 if modality contains "regimen especial"
  8. es_servicios_profesionales — 1 if justification contains "servicios profesionales"
  9. unspsc_categoria         — UNSPSC segment code (integer from "V1.SSFFCCXX")
 10. tiene_justificacion_modalidad — 1 if justification is non-null and meaningful

Usage:
    from sip_engine.classifiers.features.category_a import compute_category_a

    features = compute_category_a(row_dict)
"""

from __future__ import annotations

import math
from typing import Any


def _to_str_or_none(val: Any) -> str | None:
    """Return None if val is None or NaN float, else str(val)."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return str(val)


def compute_category_a(row: dict[str, Any]) -> dict[str, Any]:
    """Compute all 10 Category A features from a single contract row dict.

    Args:
        row: Dict with raw contratos column values. Expected keys:
            - "Valor del Contrato"           — float or None
            - "Tipo de Contrato"             — str or None
            - "Modalidad de Contratacion"    — str or None
            - "Justificacion Modalidad de Contratacion" — str or None
            - "Origen de los Recursos"       — str or None
            - "TipoDocProveedor"             — str or None (unused in Cat-A, passed for consistency)
            - "Departamento"                 — str or None
            - "Codigo de Categoria Principal" — str or None

    Returns:
        Dict with exactly 10 feature keys.
    """
    # ---- Raw values ----
    valor_raw = row.get("Valor del Contrato")
    tipo_contrato_raw = _to_str_or_none(row.get("Tipo de Contrato"))
    modalidad_raw = _to_str_or_none(row.get("Modalidad de Contratacion"))
    justificacion_raw = _to_str_or_none(row.get("Justificacion Modalidad de Contratacion"))
    origen_raw = _to_str_or_none(row.get("Origen de los Recursos"))
    departamento_raw = _to_str_or_none(row.get("Departamento"))
    categoria_raw = row.get("Codigo de Categoria Principal")

    # ---- 1. valor_contrato — float passthrough ----
    try:
        valor_contrato = float(valor_raw) if valor_raw is not None else float("nan")
    except (TypeError, ValueError):
        valor_contrato = float("nan")

    # ---- 2–5. Categorical columns (pass through; encoding happens in encoding.py) ----
    tipo_contrato_cat = tipo_contrato_raw
    modalidad_contratacion_cat = modalidad_raw
    departamento_cat = departamento_raw
    origen_recursos_cat = origen_raw

    # ---- 6. es_contratacion_directa ----
    modalidad_lower = (modalidad_raw or "").lower().strip()
    es_contratacion_directa = 1 if "contrataci" in modalidad_lower and "directa" in modalidad_lower else 0

    # ---- 7. es_regimen_especial ----
    es_regimen_especial = 1 if "r" in modalidad_lower and "gimen especial" in modalidad_lower else 0

    # ---- 8. es_servicios_profesionales ----
    justificacion_lower = (justificacion_raw or "").lower().strip()
    es_servicios_profesionales = 1 if "servicios profesionales" in justificacion_lower else 0

    # ---- 9. unspsc_categoria — extract segment (chars 3:5 after "V1.") ----
    unspsc_categoria = _extract_unspsc_segment(categoria_raw)

    # ---- 10. tiene_justificacion_modalidad ----
    tiene_justificacion_modalidad = _has_justificacion(justificacion_raw)

    return {
        "valor_contrato": valor_contrato,
        "tipo_contrato_cat": tipo_contrato_cat,
        "modalidad_contratacion_cat": modalidad_contratacion_cat,
        "departamento_cat": departamento_cat,
        "origen_recursos_cat": origen_recursos_cat,
        "es_contratacion_directa": es_contratacion_directa,
        "es_regimen_especial": es_regimen_especial,
        "es_servicios_profesionales": es_servicios_profesionales,
        "unspsc_categoria": unspsc_categoria,
        "tiene_justificacion_modalidad": tiene_justificacion_modalidad,
    }


# ============================================================
# Private helpers
# ============================================================


def _extract_unspsc_segment(code: str | None) -> float | None:
    """Extract the UNSPSC segment (2-digit int) from a code like 'V1.80111600'.

    UNSPSC hierarchy: Segment (2) + Family (2) + Class (2) + Commodity (2)
    After stripping the 'V1.' prefix: positions [0:2] = segment digits.

    Returns:
        Integer segment code (e.g., 80), or float("nan") for null/malformed.
    """
    if code is None or (isinstance(code, float) and math.isnan(code)):
        return float("nan")

    code_str = str(code).strip()
    if not code_str:
        return float("nan")

    # Strip optional "V1." prefix
    if code_str.upper().startswith("V1."):
        numeric_part = code_str[3:]
    else:
        numeric_part = code_str

    # Need at least 2 digits for the segment
    if len(numeric_part) < 2:
        return float("nan")

    segment_str = numeric_part[:2]
    try:
        return int(segment_str)
    except (ValueError, TypeError):
        return float("nan")


def _has_justificacion(justificacion: str | None) -> int:
    """Return 1 if justificacion is a meaningful value, 0 otherwise.

    Null, NaN, "N/A", "No definido", or empty string → 0.
    Any other non-empty string → 1.
    """
    if justificacion is None:
        return 0
    if isinstance(justificacion, float) and math.isnan(justificacion):
        return 0
    val = str(justificacion).strip()
    if val == "" or val.upper() == "N/A" or val.lower() == "no definido":
        return 0
    return 1
