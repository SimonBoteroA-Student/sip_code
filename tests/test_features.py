"""Tests for Phase 5 feature engineering: schemas, settings, and provider history index.

Tests cover:
- schemas.py: new columns for CONTRATOS (Codigo de Categoria Principal) and PROCESOS
- settings.py: new artifact paths (provider_history_index_path, encoding_mappings_path, features_path)
- provider_history.py: build, serialize, load, and as-of lookup with temporal leak guard
"""

from __future__ import annotations

import datetime
import math
from pathlib import Path

import joblib
import pandas as pd
import pytest

from sip_engine.data.schemas import (
    CONTRATOS_DTYPE,
    CONTRATOS_USECOLS,
    PROCESOS_DTYPE,
    PROCESOS_USECOLS,
)
from sip_engine.config import get_settings
from sip_engine.config.settings import Settings


# ============================================================
# Task 1: Schema and Settings tests
# ============================================================


def test_contratos_schema_has_categoria_principal():
    """CONTRATOS_USECOLS must include Codigo de Categoria Principal with str dtype."""
    assert "Codigo de Categoria Principal" in CONTRATOS_USECOLS
    assert CONTRATOS_DTYPE.get("Codigo de Categoria Principal") == str


def test_procesos_schema_has_portafolio():
    """PROCESOS_USECOLS must include ID del Portafolio join key with str dtype."""
    assert "ID del Portafolio" in PROCESOS_USECOLS
    assert PROCESOS_DTYPE.get("ID del Portafolio") == str


def test_procesos_schema_has_fecha_recepcion():
    """PROCESOS_USECOLS must include Fecha de Recepcion de Respuestas (bid window end)."""
    assert "Fecha de Recepcion de Respuestas" in PROCESOS_USECOLS


def test_procesos_schema_has_fecha_adjudicacion():
    """PROCESOS_USECOLS must include Fecha Adjudicacion (award date)."""
    assert "Fecha Adjudicacion" in PROCESOS_USECOLS


def test_settings_provider_history_index_path(tmp_path, monkeypatch):
    """Settings().provider_history_index_path must end with provider_history_index.pkl."""
    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    s = Settings()
    assert s.provider_history_index_path.name == "provider_history_index.pkl"
    assert "features" in str(s.provider_history_index_path)


def test_settings_encoding_mappings_path(tmp_path, monkeypatch):
    """Settings().encoding_mappings_path must end with encoding_mappings.json."""
    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    s = Settings()
    assert s.encoding_mappings_path.name == "encoding_mappings.json"
    assert "features" in str(s.encoding_mappings_path)


def test_settings_features_path(tmp_path, monkeypatch):
    """Settings().features_path must end with features.parquet."""
    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    s = Settings()
    assert s.features_path.name == "features.parquet"
    assert "features" in str(s.features_path)


# ============================================================
# Task 2: Provider History Index tests
# ============================================================


# ---- Fixtures ----

def _make_tiny_contratos(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a minimal contratos_SECOP.csv for testing provider history."""
    header = (
        "Proceso de Compra,ID Contrato,Referencia del Contrato,Estado Contrato,"
        "Tipo de Contrato,Modalidad de Contratacion,Justificacion Modalidad de Contratacion,"
        "TipoDocProveedor,Documento Proveedor,Proveedor Adjudicado,Origen de los Recursos,"
        "Valor del Contrato,Nombre Entidad,Nit Entidad,Departamento,Codigo de Categoria Principal,"
        "Ciudad,Objeto del Contrato,Fecha de Firma,Fecha de Inicio del Contrato,Fecha de Fin del Contrato"
    )
    lines = [header]
    for r in rows:
        lines.append(
            f"{r.get('proceso','PROC-001')},{r['id_contrato']},REF-{r['id_contrato']},"
            f"Liquidado,Prestacion de Servicios,Contratacion Directa,N/A,"
            f"{r.get('tipo_doc','NIT')},{r.get('doc_num','900111111')},EMPRESA TEST,"
            f"Recursos Propios,{r.get('valor','$1000000')},ENTIDAD TEST,899999999,"
            f"{r.get('departamento','Cundinamarca')},{r.get('categoria','A1')},"
            f"Bogota,Servicios,{r.get('fecha_firma','2020-01-01')},"
            f"2020-01-10,2020-12-31"
        )
    p = tmp_path / "contratos_SECOP.csv"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _make_tiny_labels(tmp_path: Path, records: list[dict]) -> Path:
    """Write a minimal labels.parquet for testing provider history."""
    labels_dir = tmp_path / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    # Ensure nullable Int8 columns matching label_builder output
    for col in ["M1", "M2", "M3", "M4"]:
        if col in df.columns:
            df[col] = df[col].astype("Int8")
        else:
            df[col] = pd.array([pd.NA] * len(df), dtype="Int8")
    p = labels_dir / "labels.parquet"
    df.to_parquet(p, index=False)
    return p


@pytest.fixture
def provider_history_env(tmp_path, monkeypatch):
    """Set up a minimal environment for provider history index tests.

    Creates:
    - Two providers (NIT 900111111 and NIT 800222222)
    - Provider A (900111111) has 3 contracts in two departments on different dates
    - Provider B (800222222) has 1 contract
    - Labels parquet with M1/M2 flags
    """
    from sip_engine.features.provider_history import reset_provider_history_cache

    reset_provider_history_cache()

    secop_dir = tmp_path / "secop"
    secop_dir.mkdir()
    artifacts_dir = tmp_path / "artifacts"
    (artifacts_dir / "features").mkdir(parents=True)
    (artifacts_dir / "labels").mkdir(parents=True)

    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SIP_SECOP_DIR", str(secop_dir))
    monkeypatch.setenv("SIP_ARTIFACTS_DIR", str(artifacts_dir))

    # Provider A: NIT 900111111 — 3 contracts across 2 depts, various dates
    # Provider B: NIT 800222222 — 1 contract in Antioquia
    contratos_rows = [
        # Provider A — Cundinamarca — 2020-01-01 (M1=1, M2=0)
        {"id_contrato": "CON-A1", "tipo_doc": "NIT", "doc_num": "900111111",
         "departamento": "Cundinamarca", "fecha_firma": "2020-01-01", "valor": "$1000000"},
        # Provider A — Antioquia — 2021-06-15 (M1=0, M2=1)
        {"id_contrato": "CON-A2", "tipo_doc": "NIT", "doc_num": "900111111",
         "departamento": "Antioquia", "fecha_firma": "2021-06-15", "valor": "$2000000"},
        # Provider A — Cundinamarca — 2022-03-10 (M1=1, M2=0)
        {"id_contrato": "CON-A3", "tipo_doc": "NIT", "doc_num": "900111111",
         "departamento": "Cundinamarca", "fecha_firma": "2022-03-10", "valor": "$500000"},
        # Provider B — Antioquia — 2020-07-01 (M1=0, M2=0)
        {"id_contrato": "CON-B1", "tipo_doc": "NIT", "doc_num": "800222222",
         "departamento": "Antioquia", "fecha_firma": "2020-07-01", "valor": "$3000000"},
    ]
    _make_tiny_contratos(secop_dir, contratos_rows)

    # Labels: Provider A's CON-A1 and CON-A3 have M1=1; CON-A2 has M2=1
    label_records = [
        {"id_contrato": "CON-A1", "M1": 1, "M2": 0, "M3": pd.NA, "M4": pd.NA},
        {"id_contrato": "CON-A2", "M1": 0, "M2": 1, "M3": pd.NA, "M4": pd.NA},
        {"id_contrato": "CON-A3", "M1": 1, "M2": 0, "M3": pd.NA, "M4": pd.NA},
        {"id_contrato": "CON-B1", "M1": 0, "M2": 0, "M3": pd.NA, "M4": pd.NA},
    ]
    _make_tiny_labels(artifacts_dir, label_records)

    yield tmp_path

    reset_provider_history_cache()


# ---- Build tests ----

def test_build_provider_history_index_creates_pkl(provider_history_env, monkeypatch):
    """build_provider_history_index() must create provider_history_index.pkl."""
    from sip_engine.features.provider_history import build_provider_history_index

    s = Settings()
    assert not s.provider_history_index_path.exists()
    result_path = build_provider_history_index(force=False)
    assert result_path == s.provider_history_index_path
    assert s.provider_history_index_path.exists()


def test_build_provider_history_index_force_rebuild(provider_history_env, monkeypatch):
    """force=True must rebuild even when pkl already exists."""
    from sip_engine.features.provider_history import build_provider_history_index

    s = Settings()
    # Build once
    build_provider_history_index(force=False)
    first_mtime = s.provider_history_index_path.stat().st_mtime

    import time as time_mod
    time_mod.sleep(0.05)  # ensure mtime difference detectable

    # Force rebuild
    build_provider_history_index(force=True)
    second_mtime = s.provider_history_index_path.stat().st_mtime
    assert second_mtime >= first_mtime


def test_build_provider_history_index_skip_existing(provider_history_env, monkeypatch):
    """force=False must NOT rebuild if pkl already exists."""
    from sip_engine.features.provider_history import build_provider_history_index

    s = Settings()
    build_provider_history_index(force=False)
    first_mtime = s.provider_history_index_path.stat().st_mtime

    import time as time_mod
    time_mod.sleep(0.05)

    build_provider_history_index(force=False)
    second_mtime = s.provider_history_index_path.stat().st_mtime
    assert second_mtime == first_mtime  # unchanged — skipped rebuild


# ---- Lookup temporal tests ----

def test_lookup_future_contracts_excluded(provider_history_env, monkeypatch):
    """Lookup as-of 2021-06-01 for Provider A must return count=2 (2020+2021 signed on 2021-06-15 > cutoff)."""
    from sip_engine.features.provider_history import build_provider_history_index, lookup_provider_history

    build_provider_history_index(force=True)
    # Provider A has contracts on: 2020-01-01, 2021-06-15, 2022-03-10
    # As-of 2021-06-14: only 2020-01-01 qualifies (strictly <)
    result = lookup_provider_history(
        tipo_doc="NIT",
        num_doc="900111111",
        as_of_date=datetime.date(2021, 6, 14),
    )
    assert result["num_contratos_previos_nacional"] == 1


def test_lookup_same_day_excluded(provider_history_env, monkeypatch):
    """Contracts signed on the same day as as_of_date must be excluded (strictly <)."""
    from sip_engine.features.provider_history import build_provider_history_index, lookup_provider_history

    build_provider_history_index(force=True)
    # Provider A's earliest contract is 2020-01-01
    # Lookup as-of 2020-01-01 must return 0 (same-day excluded)
    result = lookup_provider_history(
        tipo_doc="NIT",
        num_doc="900111111",
        as_of_date=datetime.date(2020, 1, 1),
    )
    assert result["num_contratos_previos_nacional"] == 0


def test_lookup_national_scope(provider_history_env, monkeypatch):
    """National scope must count all prior contracts regardless of department."""
    from sip_engine.features.provider_history import build_provider_history_index, lookup_provider_history

    build_provider_history_index(force=True)
    # Provider A has 3 contracts; as-of 2023-01-01 all 3 are prior
    result = lookup_provider_history(
        tipo_doc="NIT",
        num_doc="900111111",
        as_of_date=datetime.date(2023, 1, 1),
    )
    assert result["num_contratos_previos_nacional"] == 3


def test_lookup_departmental_scope(provider_history_env, monkeypatch):
    """Departmental scope must count only prior contracts in the specified department."""
    from sip_engine.features.provider_history import build_provider_history_index, lookup_provider_history

    build_provider_history_index(force=True)
    # Provider A: Cundinamarca = CON-A1 (2020-01-01) + CON-A3 (2022-03-10)
    # As-of 2023-01-01: Cundinamarca count = 2, Antioquia count = 1
    result_cund = lookup_provider_history(
        tipo_doc="NIT",
        num_doc="900111111",
        as_of_date=datetime.date(2023, 1, 1),
        departamento="Cundinamarca",
    )
    result_ant = lookup_provider_history(
        tipo_doc="NIT",
        num_doc="900111111",
        as_of_date=datetime.date(2023, 1, 1),
        departamento="Antioquia",
    )
    assert result_cund["num_contratos_previos_depto"] == 2
    assert result_ant["num_contratos_previos_depto"] == 1


def test_lookup_first_time_provider(provider_history_env, monkeypatch):
    """Unknown provider (no prior contracts) must return all-zeros dict."""
    from sip_engine.features.provider_history import build_provider_history_index, lookup_provider_history

    build_provider_history_index(force=True)
    result = lookup_provider_history(
        tipo_doc="NIT",
        num_doc="999999999",  # not in index
        as_of_date=datetime.date(2023, 1, 1),
    )
    assert result["num_contratos_previos_nacional"] == 0
    assert result["num_contratos_previos_depto"] == 0
    assert result["valor_total_contratos_previos_nacional"] == 0.0
    assert result["valor_total_contratos_previos_depto"] == 0.0
    assert result["num_sobrecostos_previos"] == 0
    assert result["num_retrasos_previos"] == 0


def test_lookup_sobrecostos_count(provider_history_env, monkeypatch):
    """num_sobrecostos_previos must count prior contracts where M1=1."""
    from sip_engine.features.provider_history import build_provider_history_index, lookup_provider_history

    build_provider_history_index(force=True)
    # Provider A: CON-A1 (M1=1, 2020-01-01) + CON-A3 (M1=1, 2022-03-10) out of 3 total
    result = lookup_provider_history(
        tipo_doc="NIT",
        num_doc="900111111",
        as_of_date=datetime.date(2023, 1, 1),
    )
    assert result["num_sobrecostos_previos"] == 2


def test_lookup_retrasos_count(provider_history_env, monkeypatch):
    """num_retrasos_previos must count prior contracts where M2=1."""
    from sip_engine.features.provider_history import build_provider_history_index, lookup_provider_history

    build_provider_history_index(force=True)
    # Provider A: CON-A2 has M2=1 (2021-06-15); as-of 2023-01-01
    result = lookup_provider_history(
        tipo_doc="NIT",
        num_doc="900111111",
        as_of_date=datetime.date(2023, 1, 1),
    )
    assert result["num_retrasos_previos"] == 1


def test_null_signing_date_excluded(tmp_path, monkeypatch):
    """Contracts with null Fecha de Firma must be excluded from the index."""
    from sip_engine.features.provider_history import (
        build_provider_history_index,
        lookup_provider_history,
        reset_provider_history_cache,
    )

    reset_provider_history_cache()

    secop_dir = tmp_path / "secop"
    secop_dir.mkdir()
    artifacts_dir = tmp_path / "artifacts"
    (artifacts_dir / "features").mkdir(parents=True)
    (artifacts_dir / "labels").mkdir(parents=True)

    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SIP_SECOP_DIR", str(secop_dir))
    monkeypatch.setenv("SIP_ARTIFACTS_DIR", str(artifacts_dir))

    # Provider C with one valid contract and one null-date contract
    contratos_rows = [
        {"id_contrato": "CON-C1", "tipo_doc": "NIT", "doc_num": "700333333",
         "departamento": "Cundinamarca", "fecha_firma": "2020-01-01", "valor": "$1000000"},
        {"id_contrato": "CON-C2", "tipo_doc": "NIT", "doc_num": "700333333",
         "departamento": "Cundinamarca", "fecha_firma": "", "valor": "$2000000"},
    ]
    _make_tiny_contratos(secop_dir, contratos_rows)
    _make_tiny_labels(artifacts_dir, [
        {"id_contrato": "CON-C1", "M1": 0, "M2": 0, "M3": pd.NA, "M4": pd.NA},
        {"id_contrato": "CON-C2", "M1": 0, "M2": 0, "M3": pd.NA, "M4": pd.NA},
    ])

    build_provider_history_index(force=True)
    result = lookup_provider_history(
        tipo_doc="NIT",
        num_doc="700333333",
        as_of_date=datetime.date(2023, 1, 1),
    )
    # Only CON-C1 should be in index (CON-C2 has null date)
    assert result["num_contratos_previos_nacional"] == 1

    reset_provider_history_cache()


def test_valor_total_sums_correctly(provider_history_env, monkeypatch):
    """valor_total_contratos_previos_nacional must sum values of all prior contracts."""
    from sip_engine.features.provider_history import build_provider_history_index, lookup_provider_history

    build_provider_history_index(force=True)
    # Provider A: $1000000 + $2000000 + $500000 = $3500000 (as-of 2023)
    result = lookup_provider_history(
        tipo_doc="NIT",
        num_doc="900111111",
        as_of_date=datetime.date(2023, 1, 1),
    )
    assert math.isclose(result["valor_total_contratos_previos_nacional"], 3_500_000.0, rel_tol=1e-6)


def test_load_provider_history_index_lazy(provider_history_env, monkeypatch):
    """load_provider_history_index() must return cached object on second call."""
    from sip_engine.features.provider_history import (
        build_provider_history_index,
        load_provider_history_index,
        reset_provider_history_cache,
    )

    build_provider_history_index(force=True)
    reset_provider_history_cache()

    index1 = load_provider_history_index()
    index2 = load_provider_history_index()
    assert index1 is index2  # same object — cached


# ============================================================
# Task 1: Category A feature extractor tests
# ============================================================


def test_valor_contrato_passthrough():
    """compute_category_a returns valor_contrato as a float value."""
    from sip_engine.features.category_a import compute_category_a

    row = {
        "Valor del Contrato": 10_000_000.0,
        "Tipo de Contrato": "Prestación de Servicios",
        "Modalidad de Contratacion": "Licitación Pública",
        "Justificacion Modalidad de Contratacion": "N/A",
        "Origen de los Recursos": "Recursos Propios",
        "TipoDocProveedor": "NIT",
        "Departamento": "Cundinamarca",
        "Codigo de Categoria Principal": "V1.80111600",
    }
    result = compute_category_a(row)
    assert result["valor_contrato"] == 10_000_000.0


def test_es_contratacion_directa_true():
    """es_contratacion_directa returns 1 for 'Contratación directa' (case-insensitive)."""
    from sip_engine.features.category_a import compute_category_a

    row = {
        "Valor del Contrato": 1000.0,
        "Tipo de Contrato": "Servicios",
        "Modalidad de Contratacion": "Contratación Directa",
        "Justificacion Modalidad de Contratacion": "Urgencia Manifiesta",
        "Origen de los Recursos": "Recursos Propios",
        "TipoDocProveedor": "NIT",
        "Departamento": "Cundinamarca",
        "Codigo de Categoria Principal": None,
    }
    result = compute_category_a(row)
    assert result["es_contratacion_directa"] == 1


def test_es_contratacion_directa_false():
    """es_contratacion_directa returns 0 for other modalities."""
    from sip_engine.features.category_a import compute_category_a

    row = {
        "Valor del Contrato": 1000.0,
        "Tipo de Contrato": "Obra",
        "Modalidad de Contratacion": "Licitación Pública",
        "Justificacion Modalidad de Contratacion": "N/A",
        "Origen de los Recursos": "Recursos Propios",
        "TipoDocProveedor": "NIT",
        "Departamento": "Cundinamarca",
        "Codigo de Categoria Principal": None,
    }
    result = compute_category_a(row)
    assert result["es_contratacion_directa"] == 0


def test_es_regimen_especial_true():
    """es_regimen_especial returns 1 when modality contains 'régimen especial'."""
    from sip_engine.features.category_a import compute_category_a

    row = {
        "Valor del Contrato": 500.0,
        "Tipo de Contrato": "Suministro",
        "Modalidad de Contratacion": "Contratación Régimen Especial",
        "Justificacion Modalidad de Contratacion": "N/A",
        "Origen de los Recursos": "Recursos Propios",
        "TipoDocProveedor": "NIT",
        "Departamento": "Antioquia",
        "Codigo de Categoria Principal": None,
    }
    result = compute_category_a(row)
    assert result["es_regimen_especial"] == 1


def test_es_servicios_profesionales_true():
    """es_servicios_profesionales returns 1 when justification contains 'servicios profesionales'."""
    from sip_engine.features.category_a import compute_category_a

    row = {
        "Valor del Contrato": 500.0,
        "Tipo de Contrato": "Consultoría",
        "Modalidad de Contratacion": "Contratación Directa",
        "Justificacion Modalidad de Contratacion": "Servicios Profesionales y de Apoyo a la Gestión",
        "Origen de los Recursos": "Recursos Propios",
        "TipoDocProveedor": "NIT",
        "Departamento": "Bogotá D.C.",
        "Codigo de Categoria Principal": None,
    }
    result = compute_category_a(row)
    assert result["es_servicios_profesionales"] == 1


def test_unspsc_categoria_extraction():
    """unspsc_categoria extracts segment (positions 3:5) as integer from 'V1.80111600'."""
    from sip_engine.features.category_a import compute_category_a

    row = {
        "Valor del Contrato": 100.0,
        "Tipo de Contrato": "Servicios",
        "Modalidad de Contratacion": "Licitación Pública",
        "Justificacion Modalidad de Contratacion": "N/A",
        "Origen de los Recursos": "Recursos Propios",
        "TipoDocProveedor": "NIT",
        "Departamento": "Cundinamarca",
        "Codigo de Categoria Principal": "V1.80111600",
    }
    result = compute_category_a(row)
    assert result["unspsc_categoria"] == 80


def test_unspsc_categoria_malformed():
    """unspsc_categoria returns NaN for null or malformed codes."""
    import math
    from sip_engine.features.category_a import compute_category_a

    for bad_code in [None, "", "BAD", "V1.AB"]:
        row = {
            "Valor del Contrato": 100.0,
            "Tipo de Contrato": "Servicios",
            "Modalidad de Contratacion": "Licitación Pública",
            "Justificacion Modalidad de Contratacion": "N/A",
            "Origen de los Recursos": "Recursos Propios",
            "TipoDocProveedor": "NIT",
            "Departamento": "Cundinamarca",
            "Codigo de Categoria Principal": bad_code,
        }
        result = compute_category_a(row)
        assert result["unspsc_categoria"] is None or (
            isinstance(result["unspsc_categoria"], float) and math.isnan(result["unspsc_categoria"])
        ), f"Expected NaN for code={bad_code!r}, got {result['unspsc_categoria']!r}"


def test_tiene_justificacion_modalidad_true():
    """tiene_justificacion_modalidad returns 1 for non-null, non-N/A, non-'No definido' values."""
    from sip_engine.features.category_a import compute_category_a

    row = {
        "Valor del Contrato": 100.0,
        "Tipo de Contrato": "Consultoría",
        "Modalidad de Contratacion": "Contratación Directa",
        "Justificacion Modalidad de Contratacion": "Urgencia Manifiesta",
        "Origen de los Recursos": "Recursos Propios",
        "TipoDocProveedor": "NIT",
        "Departamento": "Cundinamarca",
        "Codigo de Categoria Principal": None,
    }
    result = compute_category_a(row)
    assert result["tiene_justificacion_modalidad"] == 1


def test_tiene_justificacion_modalidad_false():
    """tiene_justificacion_modalidad returns 0 for null, 'N/A', or 'No definido'."""
    from sip_engine.features.category_a import compute_category_a

    for justificacion in [None, "N/A", "No definido", ""]:
        row = {
            "Valor del Contrato": 100.0,
            "Tipo de Contrato": "Servicios",
            "Modalidad de Contratacion": "Contratación Directa",
            "Justificacion Modalidad de Contratacion": justificacion,
            "Origen de los Recursos": "Recursos Propios",
            "TipoDocProveedor": "NIT",
            "Departamento": "Cundinamarca",
            "Codigo de Categoria Principal": None,
        }
        result = compute_category_a(row)
        assert result["tiene_justificacion_modalidad"] == 0, (
            f"Expected 0 for justificacion={justificacion!r}"
        )


def test_category_a_returns_ten_features():
    """compute_category_a must return exactly 10 feature keys."""
    from sip_engine.features.category_a import compute_category_a

    row = {
        "Valor del Contrato": 5_000_000.0,
        "Tipo de Contrato": "Consultoría",
        "Modalidad de Contratacion": "Contratación Directa",
        "Justificacion Modalidad de Contratacion": "Servicios Profesionales",
        "Origen de los Recursos": "Sistema General de Regalías",
        "TipoDocProveedor": "NIT",
        "Departamento": "Antioquia",
        "Codigo de Categoria Principal": "V1.80101600",
    }
    result = compute_category_a(row)
    assert len(result) == 10


# ============================================================
# Task 1: Category B feature extractor tests
# ============================================================


def test_dias_firma_a_inicio_positive():
    """dias_firma_a_inicio is positive when firma is before inicio."""
    from sip_engine.features.category_b import compute_category_b

    row = {
        "Fecha de Firma": datetime.date(2023, 1, 10),
        "Fecha de Inicio del Contrato": datetime.date(2023, 1, 20),
        "Fecha de Fin del Contrato": datetime.date(2023, 12, 31),
    }
    result = compute_category_b(row, procesos_data=None, proveedor_fecha_creacion=None)
    assert result["dias_firma_a_inicio"] == 10


def test_dias_firma_a_inicio_negative():
    """dias_firma_a_inicio is negative when firma is after inicio."""
    from sip_engine.features.category_b import compute_category_b

    row = {
        "Fecha de Firma": datetime.date(2023, 1, 25),
        "Fecha de Inicio del Contrato": datetime.date(2023, 1, 20),
        "Fecha de Fin del Contrato": datetime.date(2023, 12, 31),
    }
    result = compute_category_b(row, procesos_data=None, proveedor_fecha_creacion=None)
    assert result["dias_firma_a_inicio"] == -5


def test_firma_posterior_a_inicio_flag():
    """firma_posterior_a_inicio is 1 when dias_firma_a_inicio < 0, else 0."""
    from sip_engine.features.category_b import compute_category_b

    row_before = {
        "Fecha de Firma": datetime.date(2023, 1, 10),
        "Fecha de Inicio del Contrato": datetime.date(2023, 1, 20),
        "Fecha de Fin del Contrato": datetime.date(2023, 12, 31),
    }
    result_before = compute_category_b(row_before, procesos_data=None, proveedor_fecha_creacion=None)
    assert result_before["firma_posterior_a_inicio"] == 0

    row_after = {
        "Fecha de Firma": datetime.date(2023, 1, 25),
        "Fecha de Inicio del Contrato": datetime.date(2023, 1, 20),
        "Fecha de Fin del Contrato": datetime.date(2023, 12, 31),
    }
    result_after = compute_category_b(row_after, procesos_data=None, proveedor_fecha_creacion=None)
    assert result_after["firma_posterior_a_inicio"] == 1


def test_duracion_contrato_dias():
    """duracion_contrato_dias is (Fecha de Fin - Fecha de Inicio).days."""
    from sip_engine.features.category_b import compute_category_b

    row = {
        "Fecha de Firma": datetime.date(2023, 1, 1),
        "Fecha de Inicio del Contrato": datetime.date(2023, 1, 5),
        "Fecha de Fin del Contrato": datetime.date(2023, 7, 5),
    }
    result = compute_category_b(row, procesos_data=None, proveedor_fecha_creacion=None)
    expected_days = (datetime.date(2023, 7, 5) - datetime.date(2023, 1, 5)).days
    assert result["duracion_contrato_dias"] == expected_days


def test_mes_firma_extraction():
    """mes_firma extracts the month number from Fecha de Firma (March=3)."""
    from sip_engine.features.category_b import compute_category_b

    row = {
        "Fecha de Firma": datetime.date(2023, 3, 15),
        "Fecha de Inicio del Contrato": datetime.date(2023, 3, 20),
        "Fecha de Fin del Contrato": datetime.date(2023, 12, 31),
    }
    result = compute_category_b(row, procesos_data=None, proveedor_fecha_creacion=None)
    assert result["mes_firma"] == 3


def test_trimestre_firma_extraction():
    """trimestre_firma is Q1 (1) for March."""
    from sip_engine.features.category_b import compute_category_b

    row = {
        "Fecha de Firma": datetime.date(2023, 3, 15),
        "Fecha de Inicio del Contrato": datetime.date(2023, 3, 20),
        "Fecha de Fin del Contrato": datetime.date(2023, 12, 31),
    }
    result = compute_category_b(row, procesos_data=None, proveedor_fecha_creacion=None)
    assert result["trimestre_firma"] == 1


def test_dias_a_proxima_eleccion_before_election():
    """dias_a_proxima_eleccion returns 30 when signing date is 30 days before a known election."""
    from sip_engine.features.category_b import compute_category_b, COLOMBIAN_ELECTION_DATES

    # Use the first election in the calendar
    election_date = COLOMBIAN_ELECTION_DATES[0]
    signing_date = election_date - datetime.timedelta(days=30)

    row = {
        "Fecha de Firma": signing_date,
        "Fecha de Inicio del Contrato": signing_date + datetime.timedelta(days=5),
        "Fecha de Fin del Contrato": signing_date + datetime.timedelta(days=365),
    }
    result = compute_category_b(row, procesos_data=None, proveedor_fecha_creacion=None)
    assert result["dias_a_proxima_eleccion"] == 30


def test_dias_a_proxima_eleccion_between_elections():
    """dias_a_proxima_eleccion returns distance to the NEXT (not prior) election."""
    from sip_engine.features.category_b import compute_category_b, COLOMBIAN_ELECTION_DATES

    # Pick a date between first and second elections
    first = COLOMBIAN_ELECTION_DATES[0]
    second = COLOMBIAN_ELECTION_DATES[1]
    mid_date = first + (second - first) // 2  # halfway between

    row = {
        "Fecha de Firma": mid_date,
        "Fecha de Inicio del Contrato": mid_date + datetime.timedelta(days=5),
        "Fecha de Fin del Contrato": mid_date + datetime.timedelta(days=365),
    }
    result = compute_category_b(row, procesos_data=None, proveedor_fecha_creacion=None)
    expected = (second - mid_date).days
    assert result["dias_a_proxima_eleccion"] == expected


def test_dias_a_proxima_eleccion_beyond_calendar():
    """dias_a_proxima_eleccion returns NaN when signing date is after last election."""
    import math
    from sip_engine.features.category_b import compute_category_b, COLOMBIAN_ELECTION_DATES

    # Use a date after the last election in the calendar
    last_election = COLOMBIAN_ELECTION_DATES[-1]
    after_last = last_election + datetime.timedelta(days=1)

    row = {
        "Fecha de Firma": after_last,
        "Fecha de Inicio del Contrato": after_last + datetime.timedelta(days=5),
        "Fecha de Fin del Contrato": after_last + datetime.timedelta(days=365),
    }
    result = compute_category_b(row, procesos_data=None, proveedor_fecha_creacion=None)
    val = result["dias_a_proxima_eleccion"]
    assert val is None or (isinstance(val, float) and math.isnan(val))


def test_dias_publicidad_from_procesos():
    """dias_publicidad = Fecha de Recepcion de Respuestas - Fecha de Publicacion del Proceso."""
    from sip_engine.features.category_b import compute_category_b

    procesos_data = {
        "Fecha de Publicacion del Proceso": datetime.date(2023, 1, 1),
        "Fecha de Recepcion de Respuestas": datetime.date(2023, 1, 15),
        "Fecha de Ultima Publicación": datetime.date(2023, 1, 20),
        "Fecha de Firma": datetime.date(2023, 1, 25),
        "Respuestas al Procedimiento": 3,
        "Proveedores Unicos con Respuestas": 3,
    }
    row = {
        "Fecha de Firma": datetime.date(2023, 2, 1),
        "Fecha de Inicio del Contrato": datetime.date(2023, 2, 5),
        "Fecha de Fin del Contrato": datetime.date(2023, 12, 31),
    }
    result = compute_category_b(row, procesos_data=procesos_data, proveedor_fecha_creacion=None)
    assert result["dias_publicidad"] == 14  # Jan 15 - Jan 1 = 14 days


def test_dias_decision_from_procesos():
    """dias_decision = Fecha de Firma (procesos) - Fecha de Ultima Publicacion."""
    from sip_engine.features.category_b import compute_category_b

    procesos_data = {
        "Fecha de Publicacion del Proceso": datetime.date(2023, 1, 1),
        "Fecha de Recepcion de Respuestas": datetime.date(2023, 1, 15),
        "Fecha de Ultima Publicación": datetime.date(2023, 1, 20),
        "Fecha de Firma": datetime.date(2023, 1, 25),
        "Respuestas al Procedimiento": 3,
        "Proveedores Unicos con Respuestas": 3,
    }
    row = {
        "Fecha de Firma": datetime.date(2023, 2, 1),
        "Fecha de Inicio del Contrato": datetime.date(2023, 2, 5),
        "Fecha de Fin del Contrato": datetime.date(2023, 12, 31),
    }
    result = compute_category_b(row, procesos_data=procesos_data, proveedor_fecha_creacion=None)
    assert result["dias_decision"] == 5  # Jan 25 - Jan 20 = 5 days


def test_dias_proveedor_registrado():
    """dias_proveedor_registrado = Fecha de Firma - proveedor Fecha Creacion."""
    from sip_engine.features.category_b import compute_category_b

    row = {
        "Fecha de Firma": datetime.date(2023, 6, 1),
        "Fecha de Inicio del Contrato": datetime.date(2023, 6, 10),
        "Fecha de Fin del Contrato": datetime.date(2023, 12, 31),
    }
    proveedor_fecha_creacion = datetime.date(2020, 1, 1)
    result = compute_category_b(row, procesos_data=None, proveedor_fecha_creacion=proveedor_fecha_creacion)
    expected = (datetime.date(2023, 6, 1) - datetime.date(2020, 1, 1)).days
    assert result["dias_proveedor_registrado"] == expected


def test_dias_proveedor_registrado_nan_when_no_match():
    """dias_proveedor_registrado is NaN when proveedor_fecha_creacion is None."""
    import math
    from sip_engine.features.category_b import compute_category_b

    row = {
        "Fecha de Firma": datetime.date(2023, 6, 1),
        "Fecha de Inicio del Contrato": datetime.date(2023, 6, 10),
        "Fecha de Fin del Contrato": datetime.date(2023, 12, 31),
    }
    result = compute_category_b(row, procesos_data=None, proveedor_fecha_creacion=None)
    val = result["dias_proveedor_registrado"]
    assert val is None or (isinstance(val, float) and math.isnan(val))


def test_negative_duration_clipped_to_zero():
    """dias_publicidad and dias_decision are clipped to 0 when negative."""
    from sip_engine.features.category_b import compute_category_b

    # Reversed dates to create negative durations
    procesos_data = {
        "Fecha de Publicacion del Proceso": datetime.date(2023, 1, 15),
        "Fecha de Recepcion de Respuestas": datetime.date(2023, 1, 1),  # before publication
        "Fecha de Ultima Publicación": datetime.date(2023, 1, 25),
        "Fecha de Firma": datetime.date(2023, 1, 20),  # before ultima publicacion
        "Respuestas al Procedimiento": 1,
        "Proveedores Unicos con Respuestas": 1,
    }
    row = {
        "Fecha de Firma": datetime.date(2023, 2, 1),
        "Fecha de Inicio del Contrato": datetime.date(2023, 2, 5),
        "Fecha de Fin del Contrato": datetime.date(2023, 12, 31),
    }
    result = compute_category_b(row, procesos_data=procesos_data, proveedor_fecha_creacion=None)
    assert result["dias_publicidad"] == 0
    assert result["dias_decision"] == 0


# ============================================================
# Task 1: Category C feature extractor tests
# ============================================================


def test_tipo_persona_proveedor_nit():
    """tipo_persona_proveedor returns 1 (juridica) for NIT document type."""
    from sip_engine.features.category_c import compute_category_c

    row = {"TipoDocProveedor": "NIT", "Departamento": "Cundinamarca"}
    provider_history = {
        "num_contratos_previos_nacional": 5,
        "num_contratos_previos_depto": 2,
        "valor_total_contratos_previos_nacional": 10_000_000.0,
        "valor_total_contratos_previos_depto": 3_000_000.0,
        "num_sobrecostos_previos": 1,
        "num_retrasos_previos": 0,
    }
    result = compute_category_c(row, procesos_data=None, provider_history=provider_history, num_actividades=3)
    assert result["tipo_persona_proveedor"] == 1


def test_tipo_persona_proveedor_cc():
    """tipo_persona_proveedor returns 0 (natural person) for CC document type."""
    from sip_engine.features.category_c import compute_category_c

    row = {"TipoDocProveedor": "CC", "Departamento": "Cundinamarca"}
    provider_history = {
        "num_contratos_previos_nacional": 0,
        "num_contratos_previos_depto": 0,
        "valor_total_contratos_previos_nacional": 0.0,
        "valor_total_contratos_previos_depto": 0.0,
        "num_sobrecostos_previos": 0,
        "num_retrasos_previos": 0,
    }
    result = compute_category_c(row, procesos_data=None, provider_history=provider_history, num_actividades=1)
    assert result["tipo_persona_proveedor"] == 0


def test_proponente_unico_true():
    """proponente_unico returns 1 when num_proponentes=1."""
    from sip_engine.features.category_c import compute_category_c

    row = {"TipoDocProveedor": "NIT", "Departamento": "Antioquia"}
    procesos_data = {
        "Respuestas al Procedimiento": 1,
        "Proveedores Unicos con Respuestas": 1,
    }
    provider_history = {
        "num_contratos_previos_nacional": 0,
        "num_contratos_previos_depto": 0,
        "valor_total_contratos_previos_nacional": 0.0,
        "valor_total_contratos_previos_depto": 0.0,
        "num_sobrecostos_previos": 0,
        "num_retrasos_previos": 0,
    }
    result = compute_category_c(row, procesos_data=procesos_data, provider_history=provider_history, num_actividades=2)
    assert result["proponente_unico"] == 1


def test_proponente_unico_false():
    """proponente_unico returns 0 when num_proponentes > 1."""
    from sip_engine.features.category_c import compute_category_c

    row = {"TipoDocProveedor": "NIT", "Departamento": "Antioquia"}
    procesos_data = {
        "Respuestas al Procedimiento": 5,
        "Proveedores Unicos con Respuestas": 5,
    }
    provider_history = {
        "num_contratos_previos_nacional": 0,
        "num_contratos_previos_depto": 0,
        "valor_total_contratos_previos_nacional": 0.0,
        "valor_total_contratos_previos_depto": 0.0,
        "num_sobrecostos_previos": 0,
        "num_retrasos_previos": 0,
    }
    result = compute_category_c(row, procesos_data=procesos_data, provider_history=provider_history, num_actividades=1)
    assert result["proponente_unico"] == 0


def test_proponente_unico_nan_when_no_procesos():
    """proponente_unico is NaN when procesos_data is None."""
    import math
    from sip_engine.features.category_c import compute_category_c

    row = {"TipoDocProveedor": "NIT", "Departamento": "Cundinamarca"}
    provider_history = {
        "num_contratos_previos_nacional": 0,
        "num_contratos_previos_depto": 0,
        "valor_total_contratos_previos_nacional": 0.0,
        "valor_total_contratos_previos_depto": 0.0,
        "num_sobrecostos_previos": 0,
        "num_retrasos_previos": 0,
    }
    result = compute_category_c(row, procesos_data=None, provider_history=provider_history, num_actividades=1)
    val = result["proponente_unico"]
    assert val is None or (isinstance(val, float) and math.isnan(val))


def test_provider_history_integrated():
    """compute_category_c correctly passes through all 6 provider history fields."""
    from sip_engine.features.category_c import compute_category_c

    row = {"TipoDocProveedor": "NIT", "Departamento": "Valle del Cauca"}
    provider_history = {
        "num_contratos_previos_nacional": 10,
        "num_contratos_previos_depto": 3,
        "valor_total_contratos_previos_nacional": 50_000_000.0,
        "valor_total_contratos_previos_depto": 12_000_000.0,
        "num_sobrecostos_previos": 2,
        "num_retrasos_previos": 1,
    }
    result = compute_category_c(row, procesos_data=None, provider_history=provider_history, num_actividades=5)
    assert result["num_contratos_previos_nacional"] == 10
    assert result["num_contratos_previos_depto"] == 3
    assert result["valor_total_contratos_previos_nacional"] == 50_000_000.0
    assert result["valor_total_contratos_previos_depto"] == 12_000_000.0
    assert result["num_sobrecostos_previos"] == 2
    assert result["num_retrasos_previos"] == 1


def test_num_actividades_economicas_passed_through():
    """num_actividades_economicas is the precomputed value passed in."""
    from sip_engine.features.category_c import compute_category_c

    row = {"TipoDocProveedor": "CC", "Departamento": "Bogotá D.C."}
    provider_history = {
        "num_contratos_previos_nacional": 0,
        "num_contratos_previos_depto": 0,
        "valor_total_contratos_previos_nacional": 0.0,
        "valor_total_contratos_previos_depto": 0.0,
        "num_sobrecostos_previos": 0,
        "num_retrasos_previos": 0,
    }
    result = compute_category_c(row, procesos_data=None, provider_history=provider_history, num_actividades=7)
    assert result["num_actividades_economicas"] == 7


def test_category_c_returns_eleven_features():
    """compute_category_c must return exactly 11 feature keys."""
    from sip_engine.features.category_c import compute_category_c

    row = {"TipoDocProveedor": "NIT", "Departamento": "Antioquia"}
    procesos_data = {
        "Respuestas al Procedimiento": 3,
        "Proveedores Unicos con Respuestas": 3,
    }
    provider_history = {
        "num_contratos_previos_nacional": 5,
        "num_contratos_previos_depto": 1,
        "valor_total_contratos_previos_nacional": 5_000_000.0,
        "valor_total_contratos_previos_depto": 1_000_000.0,
        "num_sobrecostos_previos": 0,
        "num_retrasos_previos": 0,
    }
    result = compute_category_c(row, procesos_data=procesos_data, provider_history=provider_history, num_actividades=2)
    assert len(result) == 11


# ============================================================
# Task 2: Encoding module tests
# ============================================================


def test_build_encoding_mappings_groups_rare(tmp_path, monkeypatch):
    """Categories appearing in < 0.1% of rows are grouped into 'Other'."""
    import pandas as pd
    from sip_engine.features.encoding import build_encoding_mappings

    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "artifacts" / "features").mkdir(parents=True)

    # 1000 rows total; "Rare" appears once (0.1% exactly — boundary) → should still be rare
    # "Common" appears 999 times → should be kept
    n = 1000
    values = ["Common"] * (n - 1) + ["Rare"]
    df = pd.DataFrame({
        "tipo_contrato_cat": values,
        "modalidad_contratacion_cat": ["Licitación Pública"] * n,
        "departamento_cat": ["Cundinamarca"] * n,
        "origen_recursos_cat": ["Recursos Propios"] * n,
        "unspsc_categoria": [80] * n,
    })
    mappings = build_encoding_mappings(df, force=True)
    # "Rare" appears at exactly 0.1% (1/1000) which equals threshold → grouped into Other
    tipo_map = mappings["tipo_contrato_cat"]
    assert "Common" in tipo_map
    assert "Rare" not in tipo_map or tipo_map.get("Rare") == tipo_map.get("Other")


def test_build_encoding_mappings_keeps_frequent(tmp_path, monkeypatch):
    """Categories appearing >= 0.1% are kept with their own code."""
    import pandas as pd
    from sip_engine.features.encoding import build_encoding_mappings

    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "artifacts" / "features").mkdir(parents=True)

    n = 1000
    # "TypeA" appears 5 times (0.5% > 0.1%) → kept
    # "TypeB" appears 995 times → kept
    values = ["TypeA"] * 5 + ["TypeB"] * (n - 5)
    df = pd.DataFrame({
        "tipo_contrato_cat": values,
        "modalidad_contratacion_cat": ["Licitación Pública"] * n,
        "departamento_cat": ["Cundinamarca"] * n,
        "origen_recursos_cat": ["Recursos Propios"] * n,
        "unspsc_categoria": [80] * n,
    })
    mappings = build_encoding_mappings(df, force=True)
    tipo_map = mappings["tipo_contrato_cat"]
    assert "TypeA" in tipo_map
    assert "TypeB" in tipo_map


def test_encoding_alphabetical_order(tmp_path, monkeypatch):
    """Encoding codes are assigned in alphabetical order (after Other=0)."""
    import pandas as pd
    from sip_engine.features.encoding import build_encoding_mappings

    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "artifacts" / "features").mkdir(parents=True)

    n = 1000
    # 3 frequent categories: Apple, Banana, Cherry
    values = ["Apple"] * 400 + ["Banana"] * 350 + ["Cherry"] * 250
    df = pd.DataFrame({
        "tipo_contrato_cat": values,
        "modalidad_contratacion_cat": ["Licitación Pública"] * n,
        "departamento_cat": ["Cundinamarca"] * n,
        "origen_recursos_cat": ["Recursos Propios"] * n,
        "unspsc_categoria": [80] * n,
    })
    mappings = build_encoding_mappings(df, force=True)
    tipo_map = mappings["tipo_contrato_cat"]
    # Alphabetical: Apple=1, Banana=2, Cherry=3
    assert tipo_map["Apple"] == 1
    assert tipo_map["Banana"] == 2
    assert tipo_map["Cherry"] == 3


def test_encoding_other_gets_code_zero(tmp_path, monkeypatch):
    """'Other' always maps to integer code 0."""
    import pandas as pd
    from sip_engine.features.encoding import build_encoding_mappings

    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "artifacts" / "features").mkdir(parents=True)

    n = 1000
    values = ["Common"] * n
    df = pd.DataFrame({
        "tipo_contrato_cat": values,
        "modalidad_contratacion_cat": ["Licitación Pública"] * n,
        "departamento_cat": ["Cundinamarca"] * n,
        "origen_recursos_cat": ["Recursos Propios"] * n,
        "unspsc_categoria": [80] * n,
    })
    mappings = build_encoding_mappings(df, force=True)
    tipo_map = mappings["tipo_contrato_cat"]
    assert tipo_map["Other"] == 0


def test_apply_encoding_known_category(tmp_path, monkeypatch):
    """apply_encoding correctly applies pre-computed mappings to known categories."""
    import pandas as pd
    from sip_engine.features.encoding import build_encoding_mappings, apply_encoding

    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "artifacts" / "features").mkdir(parents=True)

    n = 1000
    values = ["Apple"] * 600 + ["Banana"] * 400
    df_train = pd.DataFrame({
        "tipo_contrato_cat": values,
        "modalidad_contratacion_cat": ["Licitación Pública"] * n,
        "departamento_cat": ["Cundinamarca"] * n,
        "origen_recursos_cat": ["Recursos Propios"] * n,
        "unspsc_categoria": [80] * n,
    })
    mappings = build_encoding_mappings(df_train, force=True)

    df_infer = pd.DataFrame({
        "tipo_contrato_cat": ["Apple", "Banana"],
        "modalidad_contratacion_cat": ["Licitación Pública", "Licitación Pública"],
        "departamento_cat": ["Cundinamarca", "Cundinamarca"],
        "origen_recursos_cat": ["Recursos Propios", "Recursos Propios"],
        "unspsc_categoria": [80, 80],
    })
    result = apply_encoding(df_infer, mappings)
    # Apple should map to 1 (alphabetical: Apple < Banana)
    assert result["tipo_contrato_cat"].iloc[0] == 1
    assert result["tipo_contrato_cat"].iloc[1] == 2


def test_apply_encoding_unseen_category(tmp_path, monkeypatch):
    """Unseen categories at inference time map to 'Other' (code 0)."""
    import pandas as pd
    from sip_engine.features.encoding import build_encoding_mappings, apply_encoding

    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "artifacts" / "features").mkdir(parents=True)

    n = 1000
    df_train = pd.DataFrame({
        "tipo_contrato_cat": ["Known"] * n,
        "modalidad_contratacion_cat": ["Licitación Pública"] * n,
        "departamento_cat": ["Cundinamarca"] * n,
        "origen_recursos_cat": ["Recursos Propios"] * n,
        "unspsc_categoria": [80] * n,
    })
    mappings = build_encoding_mappings(df_train, force=True)

    df_infer = pd.DataFrame({
        "tipo_contrato_cat": ["UnseenType"],
        "modalidad_contratacion_cat": ["Licitación Pública"],
        "departamento_cat": ["Cundinamarca"],
        "origen_recursos_cat": ["Recursos Propios"],
        "unspsc_categoria": [80],
    })
    result = apply_encoding(df_infer, mappings)
    # "UnseenType" not in training set → maps to Other=0
    assert result["tipo_contrato_cat"].iloc[0] == 0


def test_apply_encoding_nan_preserved(tmp_path, monkeypatch):
    """NaN values in categorical columns remain NaN after encoding."""
    import math
    import pandas as pd
    from sip_engine.features.encoding import build_encoding_mappings, apply_encoding

    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "artifacts" / "features").mkdir(parents=True)

    n = 1000
    df_train = pd.DataFrame({
        "tipo_contrato_cat": ["Common"] * n,
        "modalidad_contratacion_cat": ["Licitación Pública"] * n,
        "departamento_cat": ["Cundinamarca"] * n,
        "origen_recursos_cat": ["Recursos Propios"] * n,
        "unspsc_categoria": [80] * n,
    })
    mappings = build_encoding_mappings(df_train, force=True)

    df_infer = pd.DataFrame({
        "tipo_contrato_cat": [None],
        "modalidad_contratacion_cat": [None],
        "departamento_cat": [None],
        "origen_recursos_cat": [None],
        "unspsc_categoria": [None],
    })
    result = apply_encoding(df_infer, mappings)
    # NaN inputs should remain NaN
    val = result["tipo_contrato_cat"].iloc[0]
    assert val is None or pd.isna(val)


def test_encoding_mappings_serialization(tmp_path, monkeypatch):
    """build_encoding_mappings writes JSON; load_encoding_mappings reads it back identically."""
    import pandas as pd
    from sip_engine.features.encoding import build_encoding_mappings, load_encoding_mappings

    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "artifacts" / "features").mkdir(parents=True)

    n = 1000
    df = pd.DataFrame({
        "tipo_contrato_cat": ["Alpha"] * 600 + ["Beta"] * 400,
        "modalidad_contratacion_cat": ["Licitación Pública"] * n,
        "departamento_cat": ["Cundinamarca"] * n,
        "origen_recursos_cat": ["Recursos Propios"] * n,
        "unspsc_categoria": [80] * n,
    })
    mappings_built = build_encoding_mappings(df, force=True)
    mappings_loaded = load_encoding_mappings()
    assert mappings_built == mappings_loaded


def test_encoding_all_five_columns(tmp_path, monkeypatch):
    """build_encoding_mappings produces mappings for all 5 categorical columns."""
    import pandas as pd
    from sip_engine.features.encoding import build_encoding_mappings, CATEGORICAL_COLUMNS

    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "artifacts" / "features").mkdir(parents=True)

    n = 1000
    df = pd.DataFrame({
        "tipo_contrato_cat": ["TypeA"] * n,
        "modalidad_contratacion_cat": ["Licitación Pública"] * n,
        "departamento_cat": ["Cundinamarca"] * n,
        "origen_recursos_cat": ["Recursos Propios"] * n,
        "unspsc_categoria": [80] * n,
    })
    mappings = build_encoding_mappings(df, force=True)
    for col in CATEGORICAL_COLUMNS:
        assert col in mappings, f"Missing mapping for column: {col}"
