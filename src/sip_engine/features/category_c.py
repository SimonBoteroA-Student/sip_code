"""Category C feature extractor: provider and competition features (FEAT-03).

Produces 11 features from provider document type, procesos bidding data,
pre-computed provider history, and number of economic activities.

Provider history fields are provided externally from lookup_provider_history()
— this module does NOT call the index directly (allows test injection).

Usage:
    from sip_engine.features.category_c import compute_category_c
    from sip_engine.features.provider_history import lookup_provider_history

    provider_history = lookup_provider_history(tipo_doc, num_doc, as_of_date, departamento)
    features = compute_category_c(row, procesos_data, provider_history, num_actividades)
"""

from __future__ import annotations

import math
from typing import Any

from sip_engine.data.rcac_builder import normalize_tipo


def compute_category_c(
    row: dict[str, Any],
    procesos_data: dict[str, Any] | None,
    provider_history: dict[str, Any],
    num_actividades: int,
) -> dict[str, Any]:
    """Compute all 11 Category C provider/competition features.

    Args:
        row: Dict with raw contratos column values. Required keys:
            - "TipoDocProveedor" — raw document type string
            - "Departamento"     — contract department (for reference; history already scoped)
        procesos_data: Dict with procesos row values for this contract's process.
            May be None if no procesos match. Expected keys:
            - "Respuestas al Procedimiento"      — total bid count (int or None)
            - "Proveedores Unicos con Respuestas" — unique bidder count (int or None)
        provider_history: Pre-computed lookup result from lookup_provider_history().
            Must contain all 6 standard keys. Use {} for first-time providers.
        num_actividades: Precomputed count of distinct UNSPSC segments the provider
            has operated in across their full contratos history (static attribute).

    Returns:
        Dict with exactly 11 feature keys.
    """
    # ---- 1. tipo_persona_proveedor — 1=juridica (NIT), 0=natural person ----
    raw_tipo = row.get("TipoDocProveedor")
    tipo_norm = normalize_tipo(raw_tipo)
    tipo_persona_proveedor = 1 if tipo_norm == "NIT" else 0

    # ---- 2 & 3. num_proponentes, num_ofertas_recibidas (from procesos) ----
    if procesos_data is not None:
        raw_proponentes = procesos_data.get("Proveedores Unicos con Respuestas")
        raw_ofertas = procesos_data.get("Respuestas al Procedimiento")

        try:
            num_proponentes = int(raw_proponentes) if raw_proponentes is not None else float("nan")
        except (TypeError, ValueError):
            num_proponentes = float("nan")

        try:
            num_ofertas_recibidas = int(raw_ofertas) if raw_ofertas is not None else float("nan")
        except (TypeError, ValueError):
            num_ofertas_recibidas = float("nan")
    else:
        num_proponentes = float("nan")
        num_ofertas_recibidas = float("nan")

    # ---- 4. proponente_unico — 1 if num_proponentes==1, NaN if no procesos match ----
    if isinstance(num_proponentes, float) and math.isnan(num_proponentes):
        proponente_unico = float("nan")
    else:
        proponente_unico = 1 if num_proponentes == 1 else 0

    # ---- 5–10. Provider history fields (passed in from lookup_provider_history) ----
    num_contratos_previos_nacional = provider_history.get("num_contratos_previos_nacional", 0)
    num_contratos_previos_depto = provider_history.get("num_contratos_previos_depto", 0)
    valor_total_contratos_previos_nacional = provider_history.get(
        "valor_total_contratos_previos_nacional", 0.0
    )
    valor_total_contratos_previos_depto = provider_history.get(
        "valor_total_contratos_previos_depto", 0.0
    )
    num_sobrecostos_previos = provider_history.get("num_sobrecostos_previos", 0)
    num_retrasos_previos = provider_history.get("num_retrasos_previos", 0)

    # ---- 11. num_actividades_economicas (precomputed static attribute) ----
    num_actividades_economicas = num_actividades

    return {
        "tipo_persona_proveedor": tipo_persona_proveedor,
        "num_proponentes": num_proponentes,
        "num_ofertas_recibidas": num_ofertas_recibidas,
        "proponente_unico": proponente_unico,
        "num_contratos_previos_nacional": num_contratos_previos_nacional,
        "num_contratos_previos_depto": num_contratos_previos_depto,
        "valor_total_contratos_previos_nacional": valor_total_contratos_previos_nacional,
        "valor_total_contratos_previos_depto": valor_total_contratos_previos_depto,
        "num_sobrecostos_previos": num_sobrecostos_previos,
        "num_retrasos_previos": num_retrasos_previos,
        "num_actividades_economicas": num_actividades_economicas,
    }
