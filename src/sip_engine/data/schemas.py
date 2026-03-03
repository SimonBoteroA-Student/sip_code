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

from pathlib import Path

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


# ============================================================
# SODA API COLUMN RENAMES  (soda snake_case → original mixed-case)
# ============================================================
# The SODA endpoint returns lowercase/snake_case field names that differ
# from the original portal export column names used throughout the codebase.
# These mappings allow transparent loading of either format.

CONTRATOS_SODA_RENAMES: dict[str, str] = {
    "proceso_de_compra": "Proceso de Compra",
    "id_contrato": "ID Contrato",
    "referencia_del_contrato": "Referencia del Contrato",
    "estado_contrato": "Estado Contrato",
    "tipo_de_contrato": "Tipo de Contrato",
    "modalidad_de_contratacion": "Modalidad de Contratacion",
    "justificacion_modalidad_de": "Justificacion Modalidad de Contratacion",
    "tipodocproveedor": "TipoDocProveedor",
    "documento_proveedor": "Documento Proveedor",
    "proveedor_adjudicado": "Proveedor Adjudicado",
    "origen_de_los_recursos": "Origen de los Recursos",
    "valor_del_contrato": "Valor del Contrato",
    "nombre_entidad": "Nombre Entidad",
    "nit_entidad": "Nit Entidad",
    "departamento": "Departamento",
    "codigo_de_categoria_principal": "Codigo de Categoria Principal",
    "ciudad": "Ciudad",
    "objeto_del_contrato": "Objeto del Contrato",
    "fecha_de_firma": "Fecha de Firma",
    "fecha_de_inicio_del_contrato": "Fecha de Inicio del Contrato",
    "duraci_n_del_contrato": "Duración del contrato",
    "dias_adicionados": "Dias adicionados",
}

PROCESOS_SODA_RENAMES: dict[str, str] = {
    "id_del_proceso": "ID del Proceso",
    "referencia_del_proceso": "Referencia del Proceso",
    "nit_entidad": "Nit Entidad",
    "entidad": "Entidad",
    "codigo_pci": "PCI",
    "departamento_entidad": "Departamento Entidad",
    "ciudad_entidad": "Ciudad Entidad",
    "precio_base": "Precio Base",
    "modalidad_de_contratacion": "Modalidad de Contratacion",
    "justificaci_n_modalidad_de": "Justificación Modalidad de Contratación",
    "tipo_de_contrato": "Tipo de Contrato",
    "fecha_de_publicacion_del": "Fecha de Publicacion del Proceso",
    "fecha_de_ultima_publicaci": "Fecha de Ultima Publicación",
    "estado_del_procedimiento": "Estado del Procedimiento",
    "valor_total_adjudicacion": "Valor Total Adjudicacion",
    "nit_del_proveedor_adjudicado": "NIT del Proveedor Adjudicado",
    "nombre_del_proveedor": "Nombre del Proveedor Adjudicado",
    "adjudicado": "Adjudicado",
    "respuestas_al_procedimiento": "Respuestas al Procedimiento",
    "proveedores_unicos_con": "Proveedores Unicos con Respuestas",
    "id_del_portafolio": "ID del Portafolio",
    "fecha_de_recepcion_de": "Fecha de Recepcion de Respuestas",
    "fecha_adjudicacion": "Fecha Adjudicacion",
}

OFERTAS_SODA_RENAMES: dict[str, str] = {
    "id_del_proceso_de_compra": "ID del Proceso de Compra",
    "referencia_del_proceso": "Referencia del Proceso",
    "nombre_proveedor": "Nombre Proveedor",
    "nit_del_proveedor": "NIT del Proveedor",
    "valor_de_la_oferta": "Valor de la Oferta",
    "modalidad": "Modalidad",
    "invitacion_directa": "Invitacion Directa",
}

PROPONENTES_SODA_RENAMES: dict[str, str] = {
    "id_procedimiento": "ID Procedimiento",
    "fecha_publicaci_n": "Fecha Publicación",
    "nombre_procedimiento": "Nombre Procedimiento",
    "nit_entidad": "NIT Entidad",
    "codigo_entidad": "Codigo Entidad",
    "entidad_compradora": "Entidad Compradora",
    "proveedor": "Proveedor",
    "nit_proveedor": "NIT Proveedor",
    "codigo_proveedor": "Codigo Proveedor",
}

PROVEEDORES_SODA_RENAMES: dict[str, str] = {
    "codigo": "Codigo",
    "nombre": "Nombre",
    "nit": "NIT",
    "es_entidad": "Es Entidad",
    "es_grupo": "Es grupo",
    "esta_activa": "Esta Activa",
    "fecha_creacion": "Fecha Creación",
    "codigo_categoria_principal": "Codigo Categoria Principal",
    "descripcion_categoria_principal": "Descripcion Categoria Principal",
    "telefono": "Telefono",
    "fax": "Fax",
    "correo": "Correo",
    "direccion": "Direccion",
    "pais": "Pais",
    "departamento": "Departamento",
    "municipio": "Municipio",
    "sitio_web": "Sitio web",
    "tipo_empresa": "Tipo Empresa",
    "nombre_representante_legal": "Nombre representante legal",
    "tipo_doc_representante_legal": "Tipo doc representante legal",
    "n_mero_doc_representante_legal": "Número doc representante legal",
    "telefono_representante_legal": "Telefono representante legal",
    "correo_representante_legal": "Correo representante legal",
    "espyme": "EsPyme",
    "ubicacion": "Ubicación",
}

EJECUCION_SODA_RENAMES: dict[str, str] = {
    "identificadorcontrato": "Identificador del Contrato",
    "tipoejecucion": "Tipo de Ejecucion",
    "nombreplan": "Nombre del Plan",
    "fechadeentregaesperada": "Fecha de Entrega Esperada",
    "porcentajedeavanceesperado": "Porcentaje de Avance Esperado",
    "fechadeentregareal": "Fecha de Entrega Real",
    "porcentaje_de_avance_real": "Porcentaje de avance real",
    "estado_del_contrato": "Estado del contrato",
    "referencia_de_articulos": "Referencia de articulos",
    "descripci_n": "Descripción",
    "unidad": "Unidad",
    "cantidad_adjudicada": "Cantidad adjudicada",
    "cantidad_planeada": "Cantidad planeada",
    "cantidadrecibida": "Cantidad Recibida",
    "cantidadporrecibir": "Cantidad por Recibir",
    "fechacreacion": "Fecha Creacion",
}

SUSPENSIONES_SODA_RENAMES: dict[str, str] = {
    "id_contrato": "ID Contrato",
    "tipo": "Tipo",
    "fecha_de_creacion": "Fecha de Creacion",
    "fecha_de_aprobacion": "Fecha de Aprobacion",
    "proposito_de_la_modificacion": "Proposito de la modificacion",
    "fecha_de_inicio_del_contrato": "Fecha de Inicio del Contrato",
    "fecha_de_fin_del_contrato": "Fecha de Fin del Contrato",
}

# Lookup by filename for auto-detection in loaders/validators
SODA_COLUMN_RENAMES: dict[str, dict[str, str]] = {
    "contratos_SECOP.csv": CONTRATOS_SODA_RENAMES,
    "procesos_SECOP.csv": PROCESOS_SODA_RENAMES,
    "ofertas_proceso_SECOP.csv": OFERTAS_SODA_RENAMES,
    "proponentes_proceso_SECOP.csv": PROPONENTES_SODA_RENAMES,
    "proveedores_registrados.csv": PROVEEDORES_SODA_RENAMES,
    "ejecucion_contratos.csv": EJECUCION_SODA_RENAMES,
    "suspensiones_contratos.csv": SUSPENSIONES_SODA_RENAMES,
}


# ============================================================
# VALIDATION & SODA-RESOLUTION UTILITIES
# ============================================================

def resolve_soda_columns(
    path: str,
    usecols: list[str] | list[int],
    dtype: dict,
    encoding: str = "utf-8",
) -> tuple[list[str] | list[int], dict, dict[str, str]]:
    """Auto-detect SODA headers and return adapted usecols/dtype + rename map.

    If the file already has original headers, returns inputs unchanged.
    If the file has SODA snake_case headers, returns SODA-mapped usecols/dtype
    and a rename dict to apply after reading each chunk.

    Returns:
        (resolved_usecols, resolved_dtype, rename_map)
        rename_map: {soda_name: original_name} — empty if no remapping needed.
    """
    if usecols and isinstance(usecols[0], int):
        return usecols, dtype, {}

    header = pd.read_csv(path, nrows=0, encoding=encoding, encoding_errors="replace")
    actual = set(header.columns)

    # Already in original format — no remapping needed
    if all(c in actual for c in usecols):
        return usecols, dtype, {}

    # Look up SODA renames for this file
    filename = Path(path).name
    soda_map = SODA_COLUMN_RENAMES.get(filename, {})
    if not soda_map:
        return usecols, dtype, {}

    # Build reverse: original_name → soda_name
    reverse = {v: k for k, v in soda_map.items()}

    resolved_usecols = [reverse.get(c, c) for c in usecols]
    rename_map = {reverse[c]: c for c in usecols if c in reverse}

    resolved_dtype = {}
    for k, v in dtype.items():
        resolved_dtype[reverse.get(k, k)] = v

    return resolved_usecols, resolved_dtype, rename_map


def validate_columns(path: str, expected: list[str] | list[int], encoding: str = "utf-8") -> None:
    """Read only the header row and check that all expected columns exist.

    Raises ValueError listing missing columns if any are absent.
    For headerless files (expected is a list of int), validation is skipped —
    integer usecols are positional and always valid.

    Transparently accepts SODA API snake_case headers when a rename mapping
    exists for the file.

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
    if not missing:
        return

    # Check if SODA renames can resolve missing columns
    filename = Path(path).name
    soda_map = SODA_COLUMN_RENAMES.get(filename, {})
    if soda_map:
        reverse = {v: k for k, v in soda_map.items()}
        still_missing = [c for c in missing if reverse.get(c, c) not in header.columns]
        if not still_missing:
            return  # SODA renames cover all missing columns
        missing = still_missing

    raise ValueError(
        f"Missing required columns in {path}: {missing}. "
        f"Available columns: {list(header.columns)}"
    )
