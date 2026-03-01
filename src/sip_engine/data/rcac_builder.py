"""RCAC (Registro Consolidado de Antecedentes de Corrupcion) builder.

Processes 5 sanction data sources into a deduplicated, serialized corruption
background registry keyed on (tipo_documento, numero_documento).

DATA-01: Build the RCAC from 6 sanction sources (sanciones_penales always False).
DATA-02: Normalize document numbers and types to controlled catalog.
DATA-03: Deduplicate across sources into one flat record per identity.
DATA-04: SIRI positional column parsing (cols 4 and 5, 0-indexed).
DATA-05: Infer tipo_documento for sources without an explicit tipo column.
DATA-08: Serialize RCAC to artifacts/rcac.pkl via joblib.

Usage:
    from sip_engine.data.rcac_builder import build_rcac
    pkl_path = build_rcac()          # uses cached pkl if present
    pkl_path = build_rcac(force=True)  # always rebuilds

Rebuild via CLI:
    python -m sip_engine build-rcac [--force]
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import joblib
import pandas as pd

from sip_engine.config import get_settings
from sip_engine.data.loaders import (
    load_boletines,
    load_paco_colusiones,
    load_paco_multas,
    load_paco_resp_fiscales,
    load_paco_siri,
)

logger = logging.getLogger(__name__)

# ============================================================
# Constants
# ============================================================

# All 6 source flags — sanciones_penales is always False (no person-level IDs)
SOURCE_FLAGS: list[str] = [
    "en_boletines",
    "en_siri",
    "en_resp_fiscales",
    "en_multas_secop",
    "en_colusiones",
    "en_sanciones_penales",
]

# Company keywords that signal NIT when found in name (case-insensitive)
_COMPANY_KEYWORDS: tuple[str, ...] = (
    "LTDA",
    "SAS",
    "S.A.S",
    "S.A.",
    "COOPERATIVA",
    "FUNDACION",
    "CORPORACION",
    "ASOCIACION",
    "UNION TEMPORAL",
    "CONSORCIO",
    "E.S.P",
    "E.S.E",
    "E.I.C.E",
    "SOCIEDAD",
)


# ============================================================
# Normalization utilities
# ============================================================

def normalize_numero(raw) -> str:
    """Strip all non-digit characters and return digit-only string.

    Handles NaN, None, and str inputs. Returns empty string for null/NaN.

    Examples:
        normalize_numero("43.922.546")   -> "43922546"
        normalize_numero("900123456-1")  -> "9001234561"
        normalize_numero("CE 289910")    -> "289910"
    """
    if raw is None:
        return ""
    try:
        if pd.isna(raw):
            return ""
    except (TypeError, ValueError):
        pass
    return re.sub(r"[^\d]", "", str(raw))


def is_malformed(numero: str) -> bool:
    """Return True if the normalized document number is structurally invalid.

    A number is malformed if:
    - It is empty (length 0)
    - All characters are '0' (sentinel value)
    - Fewer than 3 digits in length

    Args:
        numero: Already-normalized digit-only string.

    Returns:
        True if malformed, False if valid.
    """
    if not numero:
        return True
    if set(numero) == {"0"}:
        return True
    if len(numero) < 3:
        return True
    return False


def _strip_accents(text: str) -> str:
    """Remove combining diacritical marks from a Unicode string.

    Example: 'CÉDULA' -> 'CEDULA'
    """
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def normalize_tipo(raw) -> str:
    """Map raw document type string to controlled catalog: CC/NIT/CE/PASAPORTE/OTRO.

    Matching is case-insensitive and accent-insensitive. Unknown types map to OTRO.

    Args:
        raw: Raw document type string, or None/NaN.

    Returns:
        One of 'CC', 'NIT', 'CE', 'PASAPORTE', 'OTRO'.
    """
    if raw is None:
        return "OTRO"
    try:
        if pd.isna(raw):
            return "OTRO"
    except (TypeError, ValueError):
        pass

    s = _strip_accents(str(raw).strip().upper())

    if s == "CC":
        return "CC"
    if s == "NIT":
        return "NIT"
    if s == "PASAPORTE":
        return "PASAPORTE"
    if "CEDULA DE CIUDADANIA" in s:
        return "CC"
    if "PERSONA" in s and "JURIDICA" in s:
        return "NIT"
    if "PERSONA" in s and "NATURAL" in s:
        return "CC"
    if "CEDULA" in s and "EXTRANJERIA" in s:
        return "CE"

    return "OTRO"


def _infer_tipo(name, numero: str) -> str:
    """Infer tipo_documento for sources without an explicit tipo column.

    Used for resp_fiscales and multas where no tipo column exists.

    Logic:
    1. If name contains a company keyword -> NIT
    2. Else if len(numero) >= 9 -> NIT (NIT digit count)
    3. Else -> CC

    Args:
        name: Person or company name string (may be None/NaN).
        numero: Already-normalized digit-only number string.

    Returns:
        'NIT' or 'CC'
    """
    if name is not None:
        try:
            name_is_nan = pd.isna(name)
        except (TypeError, ValueError):
            name_is_nan = False
        if not name_is_nan:
            name_upper = str(name).upper()
            for keyword in _COMPANY_KEYWORDS:
                if keyword in name_upper:
                    return "NIT"

    if len(numero) >= 9:
        return "NIT"

    return "CC"


# ============================================================
# Source extraction functions
# ============================================================

def _extract_boletines() -> list[tuple[str, str, str, str, str]]:
    """Extract (tipo_norm, num_norm, source_flag, raw_tipo, raw_num) tuples from boletines.

    DATA-02: Normalize tipo_documento ('tipo de documento') and numero_documento
    ('numero de documento'). Source flag: 'en_boletines'.

    Returns:
        List of (tipo_norm, num_norm, source_flag, raw_tipo, raw_num) tuples.
    """
    results = []
    for chunk in load_boletines():
        for _, row in chunk.iterrows():
            raw_tipo = row.get("tipo de documento", None)
            raw_num = row.get("numero de documento", None)
            tipo_norm = normalize_tipo(raw_tipo)
            num_norm = normalize_numero(raw_num)
            results.append((tipo_norm, num_norm, "en_boletines", str(raw_tipo), str(raw_num)))
    return results


def _extract_siri() -> list[tuple[str, str, str, str, str]]:
    """Extract (tipo_norm, num_norm, source_flag, raw_tipo, raw_num) tuples from SIRI.

    DATA-04: All tipo values from SIRI are mapped via normalize_tipo (e.g.,
    'CEDULA DE CIUDADANIA' -> 'CC'). Source flag: 'en_siri'.

    Returns:
        List of (tipo_norm, num_norm, source_flag, raw_tipo, raw_num) tuples.
    """
    results = []
    for chunk in load_paco_siri():
        for _, row in chunk.iterrows():
            raw_tipo = row.get("tipo_documento", None)
            raw_num = row.get("numero_documento", None)
            tipo_norm = normalize_tipo(raw_tipo)
            num_norm = normalize_numero(raw_num)
            results.append((tipo_norm, num_norm, "en_siri", str(raw_tipo), str(raw_num)))
    return results


def _extract_resp_fiscales() -> list[tuple[str, str, str, str, str]]:
    """Extract tuples from responsabilidades_fiscales.

    DATA-05: 'Tipo y Num Docuemento' is purely numeric — just normalize digits.
    Name from 'Responsable Fiscal' used to infer tipo_documento via _infer_tipo().
    Source flag: 'en_resp_fiscales'.

    Note: The CONTEXT.md confirms the combined field is actually just numeric,
    no splitting required — normalize_numero() extracts digits directly.

    Returns:
        List of (tipo_norm, num_norm, source_flag, raw_tipo, raw_num) tuples.
    """
    results = []
    for chunk in load_paco_resp_fiscales():
        for _, row in chunk.iterrows():
            raw_num = row.get("Tipo y Num Docuemento", None)
            name = row.get("Responsable Fiscal", None)
            num_norm = normalize_numero(raw_num)
            tipo_norm = _infer_tipo(name, num_norm)
            results.append((tipo_norm, num_norm, "en_resp_fiscales", "INFERRED", str(raw_num)))
    return results


def _extract_multas() -> list[tuple[str, str, str, str, str]]:
    """Extract tuples from multas_SECOP_PACO (headerless file).

    col_5 = numero_documento, col_6 = name for tipo inference.
    Source flag: 'en_multas_secop'.

    Returns:
        List of (tipo_norm, num_norm, source_flag, raw_tipo, raw_num) tuples.
    """
    results = []
    for chunk in load_paco_multas():
        for _, row in chunk.iterrows():
            raw_num = row.get("col_5", None)
            name = row.get("col_6", None)
            num_norm = normalize_numero(raw_num)
            tipo_norm = _infer_tipo(name, num_norm)
            results.append((tipo_norm, num_norm, "en_multas_secop", "INFERRED", str(raw_num)))
    return results


def _extract_colusiones() -> list[tuple[str, str, str, str, str]]:
    """Extract tuples from colusiones_en_contratacion_SIC.

    'Tipo de Persona Sancionada' -> tipo, 'Identificacion' -> numero.
    Source flag: 'en_colusiones'.

    Returns:
        List of (tipo_norm, num_norm, source_flag, raw_tipo, raw_num) tuples.
    """
    results = []
    for chunk in load_paco_colusiones():
        for _, row in chunk.iterrows():
            raw_tipo = row.get("Tipo de Persona Sancionada", None)
            raw_num = row.get("Identificacion", None)
            tipo_norm = normalize_tipo(raw_tipo)
            num_norm = normalize_numero(raw_num)
            results.append((tipo_norm, num_norm, "en_colusiones", str(raw_tipo), str(raw_num)))
    return results


# ============================================================
# Builder
# ============================================================

def build_rcac(force: bool = False) -> Path:
    """Build the RCAC index from all 5 usable sources and serialize to rcac.pkl.

    If rcac.pkl already exists and force=False, returns the existing path
    (cached build behavior).

    The RCAC is a dict keyed on (tipo_documento, numero_documento) tuples.
    Each value is a flat record dict with:
        - tipo_documento: str (CC/NIT/CE/PASAPORTE/OTRO)
        - numero_documento: str (digit-only)
        - en_boletines: bool
        - en_siri: bool
        - en_resp_fiscales: bool
        - en_multas_secop: bool
        - en_colusiones: bool
        - en_sanciones_penales: bool (always False — no person-level IDs in FGN)
        - num_fuentes_distintas: int (count of distinct sources, not raw rows)
        - malformed: bool

    Malformed records are excluded from the returned index but written to
    rcac_bad_rows.csv for audit.

    Args:
        force: If True, always rebuild even if pkl exists.

    Returns:
        Path to the serialized rcac.pkl file.
    """
    settings = get_settings()
    rcac_path = settings.rcac_path

    if rcac_path.exists() and not force:
        logger.info("Using cached RCAC at %s", rcac_path)
        return rcac_path

    logger.warning(
        "sanciones_penales_FGN has no person-level IDs -- en_sanciones_penales always False"
    )

    # ---- Collect all (tipo_norm, num_norm, source_flag, raw_tipo, raw_num) tuples ----
    all_tuples: list[tuple[str, str, str, str, str]] = []
    all_tuples.extend(_extract_boletines())
    all_tuples.extend(_extract_siri())
    all_tuples.extend(_extract_resp_fiscales())
    all_tuples.extend(_extract_multas())
    all_tuples.extend(_extract_colusiones())

    # ---- Separate bad rows ----
    bad_rows: list[dict] = []
    good_tuples: list[tuple[str, str, str, str, str]] = []

    for tipo_norm, num_norm, source_flag, raw_tipo, raw_num in all_tuples:
        if is_malformed(num_norm):
            bad_rows.append({
                "source": source_flag,
                "tipo_documento_raw": raw_tipo,
                "numero_documento_raw": raw_num,
                "reason": (
                    "empty" if not num_norm
                    else "all_zeros" if set(num_norm) == {"0"}
                    else "too_short"
                ),
            })
        else:
            good_tuples.append((tipo_norm, num_norm, source_flag, raw_tipo, raw_num))

    # ---- Deduplicate: group by (tipo_norm, num_norm), OR source flags ----
    # key -> set of source flags seen for this identity
    source_sets: dict[tuple[str, str], set[str]] = defaultdict(set)

    for tipo_norm, num_norm, source_flag, _raw_tipo, _raw_num in good_tuples:
        source_sets[(tipo_norm, num_norm)].add(source_flag)

    # ---- Build final index ----
    index: dict[tuple[str, str], dict] = {}
    for (tipo_norm, num_norm), seen_sources in source_sets.items():
        record = {
            "tipo_documento": tipo_norm,
            "numero_documento": num_norm,
            "en_boletines": "en_boletines" in seen_sources,
            "en_siri": "en_siri" in seen_sources,
            "en_resp_fiscales": "en_resp_fiscales" in seen_sources,
            "en_multas_secop": "en_multas_secop" in seen_sources,
            "en_colusiones": "en_colusiones" in seen_sources,
            "en_sanciones_penales": False,  # always False — no person-level IDs in FGN
            "num_fuentes_distintas": len(seen_sources),
            "malformed": False,
        }
        index[(tipo_norm, num_norm)] = record

    # ---- Write bad rows CSV ----
    settings.artifacts_rcac_dir.mkdir(parents=True, exist_ok=True)
    bad_rows_path = settings.rcac_bad_rows_path

    import csv as csv_module
    with bad_rows_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv_module.DictWriter(
            f,
            fieldnames=["source", "tipo_documento_raw", "numero_documento_raw", "reason"],
        )
        writer.writeheader()
        writer.writerows(bad_rows)

    # ---- Serialize index ----
    joblib.dump(index, rcac_path)

    logger.info(
        "RCAC built -- %d records, %d malformed, %d sources",
        len(index),
        len(bad_rows),
        5,  # 5 usable sources (sanciones_penales excluded — no person-level IDs)
    )

    return rcac_path
