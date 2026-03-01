"""Tests for M1/M2 label construction in label_builder.py.

Tests cover:
- M1_TIPOS and M2_TIPOS constants
- _load_contratos_base() column selection and deduplication
- _build_m1_m2_sets() tipo matching (case-insensitive), orphan handling
- build_labels() RCAC existence check and M2 sparsity warning
"""

from __future__ import annotations

import joblib
import pandas as pd
import pytest

from sip_engine.data.label_builder import (
    M1_TIPOS,
    M2_TIPOS,
    _build_m1_m2_sets,
    _load_contratos_base,
    build_labels,
)


# ============================================================
# Fixtures
# ============================================================

# Header for contratos_SECOP.csv (must match CONTRATOS_USECOLS exactly)
_CONTRATOS_HEADER = (
    "Proceso de Compra,ID Contrato,Referencia del Contrato,Estado Contrato,"
    "Tipo de Contrato,Modalidad de Contratacion,Justificacion Modalidad de Contratacion,"
    "TipoDocProveedor,Documento Proveedor,Proveedor Adjudicado,Origen de los Recursos,"
    "Valor del Contrato,Nombre Entidad,Nit Entidad,Departamento,Ciudad,"
    "Objeto del Contrato,Fecha de Firma,Fecha de Inicio del Contrato,Fecha de Fin del Contrato"
)

# Header for adiciones.csv (must match ADICIONES_USECOLS exactly)
_ADICIONES_HEADER = "identificador,id_contrato,tipo,descripcion,fecharegistro"

# Header for boletines.csv (must match BOLETINES_USECOLS exactly)
_BOLETINES_HEADER = (
    "Responsable Fiscal,tipo de documento,numero de documento,"
    "Entidad Afectada,TR,R,Ente que Reporta,Departamento,Municipio"
)


def _make_contrato_row(proceso, id_contrato, tipo_doc, doc_num):
    """Create a minimal contratos CSV row with required columns populated."""
    return (
        f"{proceso},{id_contrato},REF-{id_contrato},Liquidado,"
        f"Prestacion de Servicios,Contratacion Directa,N/A,"
        f"{tipo_doc},{doc_num},EMPRESA TEST,Recursos Propios,"
        f"$1000000,ENTIDAD TEST,899999999,Cundinamarca,Bogota,"
        f"Servicios,2023-01-01,2023-01-10,2023-12-31"
    )


@pytest.fixture
def label_test_env(tmp_path, monkeypatch):
    """Set up a minimal test environment for label builder tests.

    Creates:
    - tmp_path/secop/contratos_SECOP.csv with 5 rows (3 unique contracts + 1 duplicate)
    - tmp_path/secop/adiciones.csv with rows covering M1, M2, discarded types, orphan
    - tmp_path/secop/boletines.csv with 1 row (prevents FileNotFoundError)
    - tmp_path/artifacts/rcac/rcac.pkl (minimal dict, prevents RCAC check failure)

    Returns:
        tmp_path (pathlib.Path)
    """
    secop_dir = tmp_path / "secop"
    secop_dir.mkdir()
    artifacts_dir = tmp_path / "artifacts"
    rcac_dir = artifacts_dir / "rcac"
    rcac_dir.mkdir(parents=True)

    monkeypatch.setenv("SIP_SECOP_DIR", str(secop_dir))
    monkeypatch.setenv("SIP_ARTIFACTS_DIR", str(artifacts_dir))

    # --- contratos_SECOP.csv ---
    # CO1.PCCNTR.1111 (duplicate row for dedup test), .2222, .3333
    contratos_rows = "\n".join([
        _CONTRATOS_HEADER,
        _make_contrato_row("PROC-001", "CO1.PCCNTR.1111", "NIT", "900111111"),
        _make_contrato_row("PROC-001", "CO1.PCCNTR.1111", "NIT", "900111111"),  # duplicate
        _make_contrato_row("PROC-002", "CO1.PCCNTR.2222", "Cedula de Ciudadania", "12345678"),
        _make_contrato_row("PROC-003", "CO1.PCCNTR.3333", "NIT", "800333333"),
        "",
    ])
    (secop_dir / "contratos_SECOP.csv").write_text(contratos_rows, encoding="utf-8")

    # --- adiciones.csv ---
    # CO1.PCCNTR.1111 -> ADICION EN EL VALOR (M1=1)
    # CO1.PCCNTR.2222 -> EXTENSION (M2=1)
    # CO1.PCCNTR.1111 -> MODIFICACION GENERAL (discarded — no M1/M2)
    # CO1.PCCNTR.9999 -> orphan (not in contratos)
    # CO1.PCCNTR.3333 -> no row -> M1=0, M2=0
    adiciones_rows = "\n".join([
        _ADICIONES_HEADER,
        "ADICION-001,CO1.PCCNTR.1111,ADICION EN EL VALOR,Incremento de costo,2023-03-01",
        "ADICION-002,CO1.PCCNTR.2222,EXTENSION,Prorroga plazo,2023-04-01",
        "ADICION-003,CO1.PCCNTR.1111,MODIFICACION GENERAL,Otro cambio,2023-05-01",
        "ADICION-004,CO1.PCCNTR.9999,ADICION EN EL VALOR,Orphan contract,2023-06-01",
        "",
    ])
    (secop_dir / "adiciones.csv").write_text(adiciones_rows, encoding="utf-8")

    # --- boletines.csv (minimal, prevents FileNotFoundError) ---
    boletines_rows = "\n".join([
        _BOLETINES_HEADER,
        "PERSONA DUMMY,CC,12345678,ENTIDAD X,TR1,R1,CGR,Bogota,Bogota",
        "",
    ])
    (secop_dir / "boletines.csv").write_text(boletines_rows, encoding="utf-8")

    # --- rcac.pkl (minimal index — satisfies RCAC existence check) ---
    minimal_rcac = {("CC", "12345678"): {"en_boletines": True, "num_fuentes_distintas": 1}}
    joblib.dump(minimal_rcac, rcac_dir / "rcac.pkl")

    return tmp_path


# ============================================================
# Constant tests
# ============================================================

def test_m1_tipos_constant():
    """M1_TIPOS must contain exactly the two value-amendment tipo strings."""
    assert M1_TIPOS == {"ADICION EN EL VALOR", "REDUCCION EN EL VALOR"}


def test_m2_tipos_constant():
    """M2_TIPOS must contain exactly the EXTENSION tipo string."""
    assert M2_TIPOS == {"EXTENSION"}


# ============================================================
# _load_contratos_base() tests
# ============================================================

def test_load_contratos_base_columns(label_test_env, monkeypatch):
    """_load_contratos_base() must return at least the 3 required columns."""
    df = _load_contratos_base()
    assert "ID Contrato" in df.columns
    assert "TipoDocProveedor" in df.columns
    assert "Documento Proveedor" in df.columns


def test_duplicate_contratos_rows_deduped(label_test_env, monkeypatch):
    """Duplicate rows with the same ID Contrato must be collapsed to one row."""
    df = _load_contratos_base()
    # fixture has 4 data rows: CO1.PCCNTR.1111 (×2), .2222, .3333 → 3 unique
    assert len(df) == 3, f"Expected 3 unique contracts, got {len(df)}"
    assert df["ID Contrato"].nunique() == 3


# ============================================================
# _build_m1_m2_sets() tests
# ============================================================

def test_build_m1_m2_sets_returns_sets(label_test_env, monkeypatch):
    """_build_m1_m2_sets() must return a tuple of two sets."""
    valid_ids = {"CO1.PCCNTR.1111", "CO1.PCCNTR.2222", "CO1.PCCNTR.3333"}
    result = _build_m1_m2_sets(valid_ids)
    assert isinstance(result, tuple)
    assert len(result) == 2
    m1, m2 = result
    assert isinstance(m1, set)
    assert isinstance(m2, set)


def test_m1_adicion_en_el_valor(label_test_env, monkeypatch):
    """Contract with 'ADICION EN EL VALOR' tipo must appear in m1_contracts."""
    valid_ids = {"CO1.PCCNTR.1111", "CO1.PCCNTR.2222", "CO1.PCCNTR.3333"}
    m1, _ = _build_m1_m2_sets(valid_ids)
    assert "CO1.PCCNTR.1111" in m1


def test_m1_reduccion_en_el_valor(tmp_path, monkeypatch):
    """Contract with 'REDUCCION EN EL VALOR' tipo must appear in m1_contracts."""
    secop_dir = tmp_path / "secop"
    secop_dir.mkdir()
    monkeypatch.setenv("SIP_SECOP_DIR", str(secop_dir))

    adiciones_rows = "\n".join([
        _ADICIONES_HEADER,
        "ADICION-001,CO1.PCCNTR.5555,REDUCCION EN EL VALOR,Reduccion costo,2023-03-01",
        "",
    ])
    (secop_dir / "adiciones.csv").write_text(adiciones_rows, encoding="utf-8")

    valid_ids = {"CO1.PCCNTR.5555"}
    m1, _ = _build_m1_m2_sets(valid_ids)
    assert "CO1.PCCNTR.5555" in m1


def test_m2_extension(label_test_env, monkeypatch):
    """Contract with 'EXTENSION' tipo must appear in m2_contracts."""
    valid_ids = {"CO1.PCCNTR.1111", "CO1.PCCNTR.2222", "CO1.PCCNTR.3333"}
    _, m2 = _build_m1_m2_sets(valid_ids)
    assert "CO1.PCCNTR.2222" in m2


def test_m1_tipo_matching_case_insensitive(tmp_path, monkeypatch):
    """Lowercase or mixed-case tipo values must still match (strip().upper())."""
    secop_dir = tmp_path / "secop"
    secop_dir.mkdir()
    monkeypatch.setenv("SIP_SECOP_DIR", str(secop_dir))

    adiciones_rows = "\n".join([
        _ADICIONES_HEADER,
        "ADICION-001,CO1.PCCNTR.6666,adicion en el valor,lowercase tipo,2023-03-01",
        "ADICION-002,CO1.PCCNTR.7777,  EXTENSION  ,leading/trailing spaces,2023-03-01",
        "",
    ])
    (secop_dir / "adiciones.csv").write_text(adiciones_rows, encoding="utf-8")

    valid_ids = {"CO1.PCCNTR.6666", "CO1.PCCNTR.7777"}
    m1, m2 = _build_m1_m2_sets(valid_ids)
    assert "CO1.PCCNTR.6666" in m1, "Lowercase 'adicion en el valor' should match M1"
    assert "CO1.PCCNTR.7777" in m2, "Padded ' EXTENSION ' should match M2"


def test_m1_m2_both_for_same_contract(tmp_path, monkeypatch):
    """A contract with both a value and time amendment gets M1=1 AND M2=1."""
    secop_dir = tmp_path / "secop"
    secop_dir.mkdir()
    monkeypatch.setenv("SIP_SECOP_DIR", str(secop_dir))

    adiciones_rows = "\n".join([
        _ADICIONES_HEADER,
        "ADICION-001,CO1.PCCNTR.8888,ADICION EN EL VALOR,Costo,2023-03-01",
        "ADICION-002,CO1.PCCNTR.8888,EXTENSION,Tiempo,2023-04-01",
        "",
    ])
    (secop_dir / "adiciones.csv").write_text(adiciones_rows, encoding="utf-8")

    valid_ids = {"CO1.PCCNTR.8888"}
    m1, m2 = _build_m1_m2_sets(valid_ids)
    assert "CO1.PCCNTR.8888" in m1, "Contract should be in M1 set"
    assert "CO1.PCCNTR.8888" in m2, "Contract should be in M2 set"


def test_discard_tipos_no_label(tmp_path, monkeypatch):
    """Non-M1/M2 tipo values must NOT produce positive labels."""
    secop_dir = tmp_path / "secop"
    secop_dir.mkdir()
    monkeypatch.setenv("SIP_SECOP_DIR", str(secop_dir))

    adiciones_rows = "\n".join([
        _ADICIONES_HEADER,
        "ADICION-001,CO1.PCCNTR.AAAA,MODIFICACION GENERAL,test,2023-03-01",
        "ADICION-002,CO1.PCCNTR.AAAA,CONCLUSION,test,2023-03-01",
        "ADICION-003,CO1.PCCNTR.AAAA,SUSPENSIoN,test,2023-03-01",
        "ADICION-004,CO1.PCCNTR.AAAA,No definido,test,2023-03-01",
        "",
    ])
    (secop_dir / "adiciones.csv").write_text(adiciones_rows, encoding="utf-8")

    valid_ids = {"CO1.PCCNTR.AAAA"}
    m1, m2 = _build_m1_m2_sets(valid_ids)
    assert "CO1.PCCNTR.AAAA" not in m1, "Discarded tipos should NOT appear in M1"
    assert "CO1.PCCNTR.AAAA" not in m2, "Discarded tipos should NOT appear in M2"


def test_no_adicion_zero_labels(label_test_env, monkeypatch):
    """Contract with no matching adiciones rows gets M1=0 and M2=0."""
    valid_ids = {"CO1.PCCNTR.1111", "CO1.PCCNTR.2222", "CO1.PCCNTR.3333"}
    m1, m2 = _build_m1_m2_sets(valid_ids)
    # CO1.PCCNTR.3333 has no adiciones entry
    assert "CO1.PCCNTR.3333" not in m1, "No-adicion contract should NOT be in M1"
    assert "CO1.PCCNTR.3333" not in m2, "No-adicion contract should NOT be in M2"


def test_orphan_adiciones_ignored(label_test_env, monkeypatch):
    """Adicion with unknown id_contrato must be excluded from M1/M2 sets."""
    # CO1.PCCNTR.9999 is in adiciones.csv but NOT in valid_ids
    valid_ids = {"CO1.PCCNTR.1111", "CO1.PCCNTR.2222", "CO1.PCCNTR.3333"}
    m1, _ = _build_m1_m2_sets(valid_ids)
    assert "CO1.PCCNTR.9999" not in m1, "Orphan id_contrato should NOT appear in M1"


# ============================================================
# build_labels() tests
# ============================================================

def test_build_labels_checks_rcac_exists(tmp_path, monkeypatch):
    """build_labels() must raise FileNotFoundError if rcac.pkl is missing."""
    secop_dir = tmp_path / "secop"
    secop_dir.mkdir()
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    monkeypatch.setenv("SIP_SECOP_DIR", str(secop_dir))
    monkeypatch.setenv("SIP_ARTIFACTS_DIR", str(artifacts_dir))

    # Create minimal required CSVs so loaders don't fail before RCAC check
    contratos_rows = "\n".join([
        _CONTRATOS_HEADER,
        _make_contrato_row("PROC-001", "CO1.PCCNTR.0001", "NIT", "900000001"),
        "",
    ])
    (secop_dir / "contratos_SECOP.csv").write_text(contratos_rows, encoding="utf-8")
    adiciones_rows = "\n".join([_ADICIONES_HEADER, ""])
    (secop_dir / "adiciones.csv").write_text(adiciones_rows, encoding="utf-8")

    # rcac.pkl deliberately NOT created
    with pytest.raises(FileNotFoundError, match="RCAC index not found"):
        build_labels()


def test_m2_sparsity_warning(tmp_path, monkeypatch, caplog):
    """When M2 has fewer than 50 positive examples, a warning must be logged."""
    import logging

    secop_dir = tmp_path / "secop"
    secop_dir.mkdir()
    artifacts_dir = tmp_path / "artifacts"
    rcac_dir = artifacts_dir / "rcac"
    rcac_dir.mkdir(parents=True)
    monkeypatch.setenv("SIP_SECOP_DIR", str(secop_dir))
    monkeypatch.setenv("SIP_ARTIFACTS_DIR", str(artifacts_dir))

    # 3 contracts, none with EXTENSION — M2 positives = 0 (< 50)
    contratos_rows = "\n".join([
        _CONTRATOS_HEADER,
        _make_contrato_row("PROC-001", "CO1.PCCNTR.A001", "NIT", "900000001"),
        _make_contrato_row("PROC-002", "CO1.PCCNTR.A002", "NIT", "900000002"),
        _make_contrato_row("PROC-003", "CO1.PCCNTR.A003", "NIT", "900000003"),
        "",
    ])
    (secop_dir / "contratos_SECOP.csv").write_text(contratos_rows, encoding="utf-8")

    adiciones_rows = "\n".join([
        _ADICIONES_HEADER,
        # Only M1 amendment — no EXTENSION rows
        "ADICION-001,CO1.PCCNTR.A001,ADICION EN EL VALOR,Costo,2023-03-01",
        "",
    ])
    (secop_dir / "adiciones.csv").write_text(adiciones_rows, encoding="utf-8")

    # rcac.pkl present
    minimal_rcac = {("NIT", "900000001"): {"en_boletines": True, "num_fuentes_distintas": 1}}
    joblib.dump(minimal_rcac, rcac_dir / "rcac.pkl")

    with caplog.at_level(logging.WARNING, logger="sip_engine.data.label_builder"):
        build_labels()

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("M2 has only" in msg for msg in warning_messages), (
        f"Expected M2 sparsity warning. Got warnings: {warning_messages}"
    )
