"""Shared pytest fixtures for sip_engine loader tests.

Fixtures create tiny in-memory CSV files via tmp_path so tests run without
access to the real 5-12 GB source files. Each fixture reflects the structural
characteristics of the real source file (headers, encoding, column count).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear the get_settings() LRU cache before each test.

    This ensures monkeypatch.setenv() changes to SIP_* env vars take effect
    when loaders call get_settings() — without this, the cached singleton
    would return the first Settings() instance regardless of env overrides.
    """
    from sip_engine.shared.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def tiny_contratos_csv(tmp_path):
    """CSV matching contratos_SECOP.csv structure (headers, UTF-8, currency cols).

    Includes 5 rows with realistic values:
    - currency amounts in "$X,XXX,XXX" format (Valor del Contrato)
    - document IDs as strings (Documento Proveedor, Nit Entidad)
    - standard contract fields used by downstream phases

    Returns:
        pathlib.Path: Path to the temp CSV file.
    """
    content = (
        "Proceso de Compra,ID Contrato,Referencia del Contrato,Estado Contrato,"
        "Tipo de Contrato,Modalidad de Contratacion,Justificacion Modalidad de Contratacion,"
        "TipoDocProveedor,Documento Proveedor,Proveedor Adjudicado,Origen de los Recursos,"
        "Valor del Contrato,Nombre Entidad,Nit Entidad,Departamento,Codigo de Categoria Principal,"
        "Ciudad,Objeto del Contrato,Fecha de Firma,Fecha de Inicio del Contrato,"
        "Duración del contrato,Dias adicionados\n"
        "CO1.BDOS.567890,CON-001,REF-001,Liquidado,Prestación de Servicios,"
        "Contratación Directa,Urgencia Manifiesta,NIT,900123456,EMPRESA ABC SAS,"
        "Recursos Propios,$10,979,236,356,MUNICIPIO DE BOGOTA,899999061,Cundinamarca,A1,"
        "Bogotá,Servicios de consultoría,2023-01-15,2023-01-20,350 Dia(s),0\n"
        "CO1.BDOS.567891,CON-002,REF-002,En ejecucion,Obra,Licitación Pública,"
        "N/A,NIT,800456789,CONSTRUCTORA XYZ LTDA,Recursos Propios,"
        "$2,500,000,000,GOBERNACION ANTIOQUIA,890982091,Antioquia,B2,"
        "Medellín,Construcción de vía,2023-02-01,2023-02-15,12 Mes(es),0\n"
        "CO1.BDOS.567892,CON-003,REF-003,Terminado,Suministro,"
        "Selección Abreviada,Cuantía Menor,CC,12345678,PERSONA NATURAL,"
        "Recursos Propios,$450,000,SECRETARIA EDUCACION,800000001,Valle del Cauca,C3,"
        "Cali,Suministro de papelería,2023-03-01,2023-03-10,112 Dia(s),0\n"
        "CO1.BDOS.567893,CON-004,REF-004,Liquidado,Consultoría,"
        "Concurso de Méritos,N/A,NIT,901234567,CONSULTORA DELTA SA,"
        "Sistema General de Regalías,$75,800,000,ALCALDIA CARTAGENA,806006813,"
        "Bolívar,A1,Cartagena,Diseño arquitectónico,2022-11-01,2022-11-15,6 Mes(es),0\n"
        "CO1.BDOS.567894,CON-005,REF-005,En ejecucion,Servicios,"
        "Contratación Directa,Entidad Sin Ánimo de Lucro,NIT,123456789-1,FUNDACION OMEGA,"
        "Recursos de Credito,$1,200,000,HOSPITAL CENTRAL,812000140,Córdoba,D5,"
        "Montería,Capacitación personal,2023-05-01,2023-05-10,174 Dia(s),0\n"
    )
    p = tmp_path / "contratos_SECOP.csv"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def tiny_siri_csv(tmp_path):
    """Headerless CSV matching sanciones_SIRI_PACO.csv structure (28 cols, no header).

    Columns 4 and 5 (0-indexed) contain tipo_documento and numero_documento.
    Includes Spanish characters (CÉDULA DE CIUDADANÍA) to verify UTF-8 correctness.

    Returns:
        pathlib.Path: Path to the temp CSV file.
    """
    # 28 columns, no header; col[4]=tipo_doc, col[5]=numero_doc
    rows = [
        "SIRI_RES_001,2023-01-15,SUSPENDIDO,DISCIPLINARIO,"
        "CÉDULA DE CIUDADANÍA,24626226,COLOMBIA,BOGOTA,REF001,ENTIDAD_A,"
        "SANCION,2022-12-01,2023-01-01,ART_1,DECRETO_001,RESOL_001,"
        "CONFIRMADO,EJECUTORIADO,2023-01-15,SIGEP,N/A,N/A,N/A,N/A,N/A,N/A,N/A,N/A\n",
        "SIRI_RES_002,2023-02-20,ACTIVO,DISCIPLINARIO,"
        "NIT,900123456,COLOMBIA,MEDELLIN,REF002,ENTIDAD_B,"
        "SANCION,2023-01-01,2023-02-01,ART_2,DECRETO_002,RESOL_002,"
        "CONFIRMADO,EJECUTORIADO,2023-02-20,SIGEP,N/A,N/A,N/A,N/A,N/A,N/A,N/A,N/A\n",
        "SIRI_RES_003,2023-03-10,SUSPENDIDO,FISCAL,"
        "CÉDULA DE CIUDADANÍA,98765432,COLOMBIA,CALI,REF003,ENTIDAD_C,"
        "SANCION,2022-06-01,2022-12-01,ART_3,DECRETO_003,RESOL_003,"
        "CONFIRMADO,EJECUTORIADO,2023-03-10,SIGEP,N/A,N/A,N/A,N/A,N/A,N/A,N/A,N/A\n",
    ]
    p = tmp_path / "sanciones_SIRI_PACO.csv"
    p.write_text("".join(rows), encoding="utf-8")
    return p


@pytest.fixture
def tiny_multas_csv(tmp_path):
    """Headerless CSV matching multas_SECOP_PACO.csv structure (15 cols, no header).

    Column 5 (0-indexed) contains the NIT of the sanctioned provider.

    Returns:
        pathlib.Path: Path to the temp CSV file.
    """
    # 15 columns, no header; col[5]=NIT_sancionado, col[0]=entity
    rows = [
        "ENTIDAD_CONTRATANTE_A,MULTA_001,2023-01-10,500000,INCUMPLIMIENTO,"
        "1067811412,EMPRESA_MULTADA_A,CONTRATO_001,RESOL_001,2022-12-01,"
        "ANTIOQUIA,MEDELLIN,INACTIVO,PAGADO,2023-06-01\n",
        "ENTIDAD_CONTRATANTE_B,MULTA_002,2023-02-15,1200000,DEFICIENCIA,"
        "800456789,EMPRESA_MULTADA_B,CONTRATO_002,RESOL_002,2023-01-15,"
        "CUNDINAMARCA,BOGOTA,ACTIVO,PENDIENTE,N/A\n",
    ]
    p = tmp_path / "multas_SECOP_PACO.csv"
    p.write_text("".join(rows), encoding="utf-8")
    return p


@pytest.fixture
def bad_byte_csv(tmp_path):
    """UTF-8 CSV with one injected invalid byte sequence (\\xff).

    Tests that encoding_errors='replace' causes undecodable bytes to become
    the replacement character (\\ufffd) rather than raising UnicodeDecodeError.

    Returns:
        pathlib.Path: Path to the temp CSV file (written as raw bytes).
    """
    from sip_engine.shared.data.schemas import CONTRATOS_USECOLS

    # Write a valid header + one row with an invalid byte injected
    header = ",".join(CONTRATOS_USECOLS) + "\n"
    good_row = (
        "CO1.BDOS.999999,CON-BAD,REF-BAD,Liquidado,Servicios,"
        "Contratación Directa,N/A,NIT,900000001,EMPRESA BAD,"
        "Recursos Propios,$100,000,ENTIDAD TEST,899000001,Bogotá,Bogotá,"
        "Servicio con byte malo,2023-01-01,2023-01-05,90 Dia(s),0\n"
    )
    # Inject \xff (invalid in UTF-8) into the middle of the row
    bad_bytes = good_row.encode("utf-8")[:20] + b"\xff" + good_row.encode("utf-8")[20:]

    p = tmp_path / "contratos_SECOP.csv"
    p.write_bytes(header.encode("utf-8") + bad_bytes)
    return p


@pytest.fixture
def missing_column_csv(tmp_path):
    """CSV with headers but one column from CONTRATOS_USECOLS deliberately missing.

    Used to test that validate_columns() raises ValueError with a clear message
    listing the absent column.

    Returns:
        pathlib.Path: Path to the temp CSV file.
    """
    from sip_engine.shared.data.schemas import CONTRATOS_USECOLS

    # Drop the last column from the usecols list
    present_cols = CONTRATOS_USECOLS[:-1]  # all except "Dias adicionados"
    header = ",".join(present_cols) + "\n"
    row = ",".join(["DUMMY_VALUE"] * len(present_cols)) + "\n"

    p = tmp_path / "contratos_missing_col.csv"
    p.write_text(header + row, encoding="utf-8")
    return p
