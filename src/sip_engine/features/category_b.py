"""Category B feature extractor: temporal features (FEAT-02).

Produces 9 temporal features from contract signing date, procesos data,
and provider registration date. Includes the hardcoded Colombian election
calendar for the dias_a_proxima_eleccion feature.

Election calendar covers 2015-2026 presidential, congressional, and
local/regional elections (source: Colombian electoral authority records).

Usage:
    from sip_engine.features.category_b import compute_category_b, COLOMBIAN_ELECTION_DATES

    features = compute_category_b(row, procesos_data, proveedor_fecha_creacion)
"""

from __future__ import annotations

import datetime
import logging
import math
import re
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# Colombian Election Calendar
# ============================================================

COLOMBIAN_ELECTION_DATES: list[datetime.date] = [
    datetime.date(2015, 10, 25),  # Local/Regional
    datetime.date(2018, 3, 11),   # Congressional
    datetime.date(2018, 5, 27),   # Presidential first round
    datetime.date(2018, 6, 17),   # Presidential second round
    datetime.date(2019, 10, 27),  # Local/Regional
    datetime.date(2022, 3, 13),   # Congressional
    datetime.date(2022, 5, 29),   # Presidential first round
    datetime.date(2022, 6, 19),   # Presidential second round
    datetime.date(2023, 10, 29),  # Local/Regional
    datetime.date(2026, 3, 8),    # Congressional (est.)
    datetime.date(2026, 5, 31),   # Presidential first round (est.)
]


# ============================================================
# Feature extractor
# ============================================================


def compute_category_b(
    row: dict[str, Any],
    procesos_data: dict[str, Any] | None,
    proveedor_fecha_creacion: datetime.date | None,
) -> dict[str, Any]:
    """Compute all 9 Category B temporal features.

    Args:
        row: Dict with raw contratos column values. Required keys:
            - "Fecha de Firma"                — datetime.date (contract signing date)
            - "Fecha de Inicio del Contrato"  — datetime.date (contract start date)
            - "Duración del contrato"         — str, text like "143 Dia(s)" (pre-amendment duration)
        procesos_data: Dict with procesos row values for this contract's process
            (may be None if no procesos record matches). Expected keys:
            - "Fecha de Publicacion del Proceso"
            - "Fecha de Recepcion de Respuestas"
            - "Fecha de Ultima Publicación"
            - "Fecha de Firma"  (procesos-level signing date)
        proveedor_fecha_creacion: Provider registration date from proveedores_registrados.
            None if no matching provider record found (NaN result, no imputation).

    Returns:
        Dict with exactly 9 feature keys.
    """
    # ---- Parse contract dates ----
    firma_date = _to_date(row.get("Fecha de Firma"))
    inicio_date = _to_date(row.get("Fecha de Inicio del Contrato"))

    # ---- 1. dias_firma_a_inicio ----
    if firma_date is not None and inicio_date is not None:
        dias_firma_a_inicio = (inicio_date - firma_date).days
    else:
        dias_firma_a_inicio = float("nan")

    # ---- 2. firma_posterior_a_inicio — 1 if signed AFTER contract start ----
    if isinstance(dias_firma_a_inicio, float) and math.isnan(dias_firma_a_inicio):
        firma_posterior_a_inicio = float("nan")
    else:
        firma_posterior_a_inicio = 1 if dias_firma_a_inicio < 0 else 0

    # ---- 3. duracion_contrato_dias ----
    duracion_contrato_dias = _parse_duracion_contrato(row.get("Duración del contrato"))

    # ---- 4. mes_firma ----
    mes_firma = firma_date.month if firma_date is not None else float("nan")

    # ---- 5. trimestre_firma ----
    if firma_date is not None:
        trimestre_firma = (firma_date.month - 1) // 3 + 1
    else:
        trimestre_firma = float("nan")

    # ---- 6. dias_a_proxima_eleccion ----
    dias_a_proxima_eleccion = _dias_to_next_election(firma_date)

    # ---- 7 & 8. dias_publicidad, dias_decision (from procesos) ----
    if procesos_data is not None:
        pub_date = _to_date(procesos_data.get("Fecha de Publicacion del Proceso"))
        rec_date = _to_date(procesos_data.get("Fecha de Recepcion de Respuestas"))
        ultima_pub_date = _to_date(procesos_data.get("Fecha de Ultima Publicación"))
        proc_firma_date = _to_date(procesos_data.get("Fecha de Firma"))

        if pub_date is not None and rec_date is not None:
            raw_publicidad = (rec_date - pub_date).days
            dias_publicidad = max(0, raw_publicidad)
        else:
            dias_publicidad = float("nan")

        if ultima_pub_date is not None and proc_firma_date is not None:
            raw_decision = (proc_firma_date - ultima_pub_date).days
            dias_decision = max(0, raw_decision)
        else:
            dias_decision = float("nan")
    else:
        dias_publicidad = float("nan")
        dias_decision = float("nan")

    # ---- 9. dias_proveedor_registrado ----
    if proveedor_fecha_creacion is not None and firma_date is not None:
        raw_reg = (firma_date - proveedor_fecha_creacion).days
        dias_proveedor_registrado = max(0, raw_reg)
    else:
        dias_proveedor_registrado = float("nan")

    return {
        "dias_firma_a_inicio": dias_firma_a_inicio,
        "firma_posterior_a_inicio": firma_posterior_a_inicio,
        "duracion_contrato_dias": duracion_contrato_dias,
        "mes_firma": mes_firma,
        "trimestre_firma": trimestre_firma,
        "dias_a_proxima_eleccion": dias_a_proxima_eleccion,
        "dias_publicidad": dias_publicidad,
        "dias_decision": dias_decision,
        "dias_proveedor_registrado": dias_proveedor_registrado,
    }


# ============================================================
# Private helpers
# ============================================================

_DURACION_RE = re.compile(
    r"^(\d+)\s+(Dia|Mes|Año|Semana|Hora)\((?:s|es)\)$", re.IGNORECASE
)
_UNIT_TO_DAYS: dict[str, float] = {
    "dia": 1,
    "mes": 30,
    "año": 365,
    "semana": 7,
    "hora": 1 / 24,
}


def _parse_duracion_contrato(raw_value: Any) -> float:
    """Parse SECOP duration text like '143 Dia(s)' to days as float.

    Handles all 6 empirical formats: Dia(s), Mes(es), Año(s), Semana(s),
    Hora(s), and "No definido". Returns NaN for None, empty, "No definido",
    bare unit without number, and unrecognised formats.
    """
    if raw_value is None:
        return float("nan")
    text = str(raw_value).strip()
    if not text or text.lower() == "no definido":
        return float("nan")

    m = _DURACION_RE.match(text)
    if m is None:
        # Bare unit like "Dia(s)" without a number
        if re.match(r"^(Dia|Mes|Año|Semana|Hora)\(", text, re.IGNORECASE):
            return float("nan")
        logger.warning("Unknown duration format: %r", text)
        return float("nan")

    number = int(m.group(1))
    unit = m.group(2).lower()
    days = number * _UNIT_TO_DAYS[unit]
    return round(days)


def _to_date(value: Any) -> datetime.date | None:
    """Coerce a value to datetime.date, returning None on failure."""
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


def _dias_to_next_election(firma_date: datetime.date | None) -> float:
    """Return days until the next Colombian election on or after firma_date.

    Returns float('nan') if firma_date is None or after the last known election.
    """
    if firma_date is None:
        return float("nan")

    for election in COLOMBIAN_ELECTION_DATES:
        if election >= firma_date:
            return (election - firma_date).days

    # After last known election → no future election in calendar
    return float("nan")
