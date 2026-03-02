"""Column schema definitions, dtype maps, and cleaning utilities for all SIP data sources.

Design contract:
- Each source file has a *_USECOLS list (or None) and a *_DTYPE dict.
- Currency columns are always read as str and cleaned post-load via clean_currency().
- Headerless files (SIRI, multas) use integer usecols and *_COLNAMES for renaming.
- Loaders import these constants — do NOT hardcode column lists inline.

When a downstream phase needs a new column: extend this file and update the loader.
That keeps changes deliberate and reviewable.
"""

from __future__ import annotations

import pandas as pd

# ============================================================
# SECOP FILES — all have headers, all UTF-8
# ============================================================

# ---- contratos_SECOP.csv (87 cols, ~537k rows, 0.57 GB) ----
# Note: SECOP export uses "Proceso de Compra" (not "ID del Proceso") in this file.
# "ID Contrato" is the contract-level identifier here.
CONTRATOS_USECOLS: list[str] = [
    "Proceso de Compra",           # process ID linking to procesos
    "ID Contrato",                 # internal contract identifier
    "Referencia del Contrato",     # human-readable contract ref
    "Estado Contrato",             # contract status
    "Tipo de Contrato",            # contract type
    "Modalidad de Contratacion",   # procurement modality
    "Justificacion Modalidad de Contratacion",
    "TipoDocProveedor",            # provider doc type
    "Documento Proveedor",         # provider document ID (NIT/CC) — kept as str
    "Proveedor Adjudicado",        # provider name
    "Origen de los Recursos",      # funding source
    "Valor del Contrato",          # contract value — currency str, clean post-load
    "Nombre Entidad",              # contracting entity name
    "Nit Entidad",                 # entity NIT — str (mixed format)
    "Departamento",                # geographic dept
    "Codigo de Categoria Principal",  # procurement category code (Phase 5, Cat-A feature)
    "Ciudad",                      # city
    "Objeto del Contrato",         # contract description
    "Fecha de Firma",              # signature date
    "Fecha de Inicio del Contrato",
    "Duración del contrato",       # pre-amendment duration text (e.g. "143 Dia(s)")
    "Dias adicionados",            # days added by amendments (M2 label source)
]

CONTRATOS_DTYPE: dict[str, str] = {
    "Proceso de Compra": str,
    "ID Contrato": str,
    "Referencia del Contrato": str,
    "TipoDocProveedor": str,
    "Documento Proveedor": str,     # NIT/CC — never cast to int
    "Nit Entidad": str,             # mixed format (with/without hyphens)
    "Valor del Contrato": str,      # "$10,979,236,356" format — clean post-load
    "Codigo de Categoria Principal": str,  # category code — keep as str
    "Duración del contrato": str,          # text like "143 Dia(s)" — parsed to days
    "Dias adicionados": str,               # has comma thousands like "1,826" — needs pre-processing
}

CONTRATOS_CURRENCY_COLS: list[str] = ["Valor del Contrato"]


# ---- procesos_SECOP.csv (59 cols, ~6.4M rows, 5.3 GB) ----
# DtypeWarning risk: Nit Entidad, PCI, and one date col have mixed types — explicit str.
PROCESOS_USECOLS: list[str] = [
    "ID del Proceso",              # process ID (links to contratos "Proceso de Compra")
    "Referencia del Proceso",      # human-readable process ref
    "Nit Entidad",                 # entity NIT — str (mixed format)
    "Entidad",                     # entity name
    "PCI",                         # presupuesto clasificacion — mixed type, str
    "Departamento Entidad",
    "Ciudad Entidad",
    "Precio Base",                 # base price — currency str, clean post-load
    "Modalidad de Contratacion",
    "Justificación Modalidad de Contratación",
    "Tipo de Contrato",
    "Fecha de Publicacion del Proceso",
    "Fecha de Ultima Publicación",
    "Estado del Procedimiento",
    "Valor Total Adjudicacion",    # adjudication value — currency str
    "NIT del Proveedor Adjudicado",
    "Nombre del Proveedor Adjudicado",
    "Adjudicado",
    "Respuestas al Procedimiento", # bidder count (N_BIDS signal)
    "Proveedores Unicos con Respuestas",
    "ID del Portafolio",           # join key: links to contratos "Proceso de Compra" (~60.9% match)
    "Fecha de Recepcion de Respuestas",  # bid window end date (Phase 5, Cat-B feature)
    "Fecha Adjudicacion",          # award date (Phase 5, Cat-B feature)
]

PROCESOS_DTYPE: dict[str, str] = {
    "ID del Proceso": str,
    "Referencia del Proceso": str,
    "Nit Entidad": str,             # mixed: "900123456" vs "900.123.456-1"
    "PCI": str,                     # mixed-type column — suppress DtypeWarning
    "NIT del Proveedor Adjudicado": str,
    "Precio Base": str,             # "$X,XXX" format — clean post-load
    "Valor Total Adjudicacion": str,  # "$X,XXX" format — clean post-load
    "ID del Portafolio": str,       # join key — keep as str (mixed format)
}

PROCESOS_CURRENCY_COLS: list[str] = ["Precio Base", "Valor Total Adjudicacion"]


# ---- ofertas_proceso_SECOP.csv (16 cols, ~9.7M rows, 3.4 GB) ----
OFERTAS_USECOLS: list[str] = [
    "ID del Proceso de Compra",    # process ID (FK to procesos)
    "Referencia del Proceso",
    "Nombre Proveedor",
    "NIT del Proveedor",
    "Valor de la Oferta",          # offer value — currency str
    "Modalidad",
    "Invitacion Directa",
]

OFERTAS_DTYPE: dict[str, str] = {
    "ID del Proceso de Compra": str,
    "Referencia del Proceso": str,
    "NIT del Proveedor": str,       # NIT — never cast to int
    "Valor de la Oferta": str,      # "$X,XXX" format — clean post-load
}

OFERTAS_CURRENCY_COLS: list[str] = ["Valor de la Oferta"]


# ---- proponentes_proceso_SECOP.csv (9 cols, small) ----
# Load all columns (small file).
PROPONENTES_USECOLS: list[str] = [
    "ID Procedimiento",
    "Fecha Publicación",
    "Nombre Procedimiento",
    "NIT Entidad",
    "Codigo Entidad",
    "Entidad Compradora",
    "Proveedor",
    "NIT Proveedor",
    "Codigo Proveedor",
]

PROPONENTES_DTYPE: dict[str, str] = {
    "ID Procedimiento": str,
    "NIT Entidad": str,
    "NIT Proveedor": str,
}


# ---- proveedores_registrados.csv (25 cols, small) ----
# Load all columns (small file).
PROVEEDORES_USECOLS: list[str] = [
    "Codigo",
    "Nombre",
    "NIT",
    "Es Entidad",
    "Es grupo",
    "Esta Activa",
    "Fecha Creación",
    "Codigo Categoria Principal",
    "Descripcion Categoria Principal",
    "Telefono",
    "Fax",
    "Correo",
    "Direccion",
    "Pais",
    "Departamento",
    "Municipio",
    "Sitio web",
    "Tipo Empresa",
    "Nombre representante legal",
    "Tipo doc representante legal",
    "Número doc representante legal",
    "Telefono representante legal",
    "Correo representante legal",
    "EsPyme",
    "Ubicación",
]

PROVEEDORES_DTYPE: dict[str, str] = {
    "Codigo": str,
    "NIT": str,
    "Número doc representante legal": str,
}


# ---- boletines.csv (9 cols, small) ----
# Load all columns. tipo/numero de documento are document IDs — always str.
BOLETINES_USECOLS: list[str] = [
    "Responsable Fiscal",
    "tipo de documento",
    "numero de documento",
    "Entidad Afectada",
    "TR",
    "R",
    "Ente que Reporta",
    "Departamento",
    "Municipio",
]

BOLETINES_DTYPE: dict[str, str] = {
    "tipo de documento": str,
    "numero de documento": str,    # document ID — never cast to int
}


# ---- ejecucion_contratos.csv (16 cols, small) ----
# POST-EXECUTION DATA — excluded from model feature vectors (FEAT-08).
# Loader exists for RCAC builder use only (cross-referencing execution status).
EJECUCION_USECOLS: list[str] = [
    "Identificador del Contrato",
    "Tipo de Ejecucion",
    "Nombre del Plan",
    "Fecha de Entrega Esperada",
    "Porcentaje de Avance Esperado",
    "Fecha de Entrega Real",
    "Porcentaje de avance real",
    "Estado del contrato",
    "Referencia de articulos",
    "Descripción",
    "Unidad",
    "Cantidad adjudicada",
    "Cantidad planeada",
    "Cantidad Recibida",
    "Cantidad por Recibir",
    "Fecha Creacion",
]

EJECUCION_DTYPE: dict[str, str] = {
    "Identificador del Contrato": str,
}


# ---- suspensiones_contratos.csv (7 cols, small) ----
SUSPENSIONES_USECOLS: list[str] = [
    "ID Contrato",
    "Tipo",
    "Fecha de Creacion",
    "Fecha de Aprobacion",
    "Proposito de la modificacion",
    "Fecha de Inicio del Contrato",
    "Fecha de Fin del Contrato",
]

SUSPENSIONES_DTYPE: dict[str, str] = {
    "ID Contrato": str,
}


# ---- adiciones.csv (5 cols, ~14.4M rows, ~4 GB) ----
# Used for M1/M2 label construction (Phase 4). All columns needed.
ADICIONES_USECOLS: list[str] = [
    "identificador",
    "id_contrato",
    "tipo",
    "descripcion",
    "fecharegistro",
]

ADICIONES_DTYPE: dict[str, str] = {
    "identificador": str,
    "id_contrato": str,
    "tipo": str,
}


# ============================================================
# PACO FILES — all UTF-8 (verified empirically, DATA-10)
# ============================================================

# ---- sanciones_SIRI_PACO.csv (28 cols, ~46k rows, 19 MB) ----
# NO HEADER ROW — use integer usecols (0-indexed).
# cols 5 and 6 per DATA-04 (1-indexed); [4, 5] in 0-indexed pandas.
SIRI_USECOLS: list[int] = [4, 5]
SIRI_DTYPE: dict[int, str] = {4: str, 5: str}
SIRI_COLNAMES: list[str] = ["tipo_documento", "numero_documento"]


# ---- multas_SECOP_PACO.csv (15 cols, ~1.7k rows, 0.6 MB) ----
# NO HEADER ROW — load all columns with generic names.
# col[5] = NIT of sanctioned provider (verified: "1067811412").
# Phase 3 (RCAC builder) will refine which columns to use.
MULTAS_USECOLS: None = None  # load all 15 columns
MULTAS_COLNAMES: list[str] = [f"col_{i}" for i in range(15)]


# ---- responsabilidades_fiscales_PACO.csv (8 cols, ~6.6k rows, 0.7 MB) ----
# Has headers. "Tipo y Num Docuemento" is a combined field — Phase 3 parses it.
RESP_FISCALES_USECOLS: list[str] = [
    "Responsable Fiscal",
    "Tipo y Num Docuemento",       # combined type+number (note: typo in source file)
    "Entidad Afectada",
    "TR",
    "R",
    "Ente que Reporta",
    "Departamento",
    "Municipio",
]

RESP_FISCALES_DTYPE: dict[str, str] = {
    "Tipo y Num Docuemento": str,
}


# ---- colusiones_en_contratacion_SIC.csv (12 cols, ~103 rows, tiny) ----
# Has headers. "Identificacion" is the provider document field.
COLUSIONES_USECOLS: list[str] = [
    "No.",
    "Fecha de Radicacion",
    "Radicado",
    "Caso",
    "Falta que origina la sancion",
    "Resolucion de Apertura",
    "Resolucion de Sancion",
    "Tipo de Persona Sancionada",
    "Personas Sancionadas",
    "Identificacion",
    "Multa Inicial",
    "Año Radicacion",
]

COLUSIONES_DTYPE: dict[str, str] = {
    "Identificacion": str,
    "No.": str,
}


# ---- sanciones_penales_FGN.csv (9 cols, ~3.9k rows, 0.5 MB) ----
# Has headers. Geographic + crime type data. No direct document ID column.
# Phase 3 (RCAC) will define join logic to providers.
SANCIONES_PENALES_USECOLS: list[str] = [
    "id",
    "DEPARTAMENTO",
    "MUNICIPIO_ID",
    "CODIGO_DANE_MUNICIPIO",
    "mpio",
    "TITULO",
    "CAPITULO",
    "ARTICULO",
    "AÑO_ACTUACION",
]

SANCIONES_PENALES_DTYPE: dict[str, str] = {
    "id": str,
    "MUNICIPIO_ID": str,
    "CODIGO_DANE_MUNICIPIO": str,
}


# ============================================================
# CLEANING UTILITIES
# ============================================================

def clean_currency(series: pd.Series) -> pd.Series:
    """Convert '$10,979,236,356' to 10979236356.0. NaN-safe.

    Uses pandas nullable Float64 so that missing values are pd.NA (not NaN),
    keeping downstream code consistent.

    Example:
        >>> import pandas as pd
        >>> clean_currency(pd.Series(["$1,234", "$5,678"]))
        0    1234.0
        1    5678.0
        dtype: Float64
    """
    return series.str.replace(r"[\$,]", "", regex=True).astype("Float64")


def validate_columns(path: str, expected: list[str] | list[int], encoding: str = "utf-8") -> None:
    """Read only the header row and check that all expected columns exist.

    Raises ValueError listing missing columns if any are absent.
    For headerless files (expected is a list of int), validation is skipped —
    integer usecols are positional and always valid.

    Args:
        path: Absolute or relative path to the CSV file.
        expected: List of column name strings to require, OR list of integer
            positional indices (headerless file — skips validation).
        encoding: File encoding (default 'utf-8').

    Raises:
        ValueError: If any expected column names are absent from the file header.
        FileNotFoundError: If the file does not exist (propagated from pd.read_csv).
    """
    if expected and isinstance(expected[0], int):
        return  # headerless file, positional indices — nothing to validate

    header = pd.read_csv(path, nrows=0, encoding=encoding, encoding_errors="replace")
    missing = [c for c in expected if c not in header.columns]
    if missing:
        raise ValueError(
            f"Missing required columns in {path}: {missing}. "
            f"Available columns: {list(header.columns)}"
        )
