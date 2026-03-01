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
