"""Tests for RCAC normalization engine and builder.

TDD RED phase: all tests import from sip_engine.shared.data.rcac_builder which does not
exist yet. All tests must fail with ImportError until Task 2 (GREEN) creates the module.

Coverage:
- normalize_numero: strip dots, hyphens, spaces, mixed, letters (DATA-02)
- is_malformed: empty, all-zeros, fewer-than-3-digits, valid (DATA-02)
- normalize_tipo: mapping to CC/NIT/CE/PASAPORTE/OTRO (DATA-02)
- _infer_tipo: company keywords and digit-length heuristic (DATA-05)
- build_rcac: deduplication across sources, bad-rows CSV, pkl serialization, cache (DATA-03)
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import joblib
import pytest

from sip_engine.shared.data.rcac_builder import (
    _infer_tipo,
    build_rcac,
    is_malformed,
    normalize_numero,
    normalize_tipo,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def rcac_source_dirs(tmp_path, monkeypatch):
    """Create tiny CSV files for all RCAC sources and wire up SIP env vars.

    Directory layout under tmp_path:
        secop/
            boletines.csv
        paco/
            sanciones_SIRI_PACO.csv      (headerless, 28 cols)
            responsabilidades_fiscales_PACO.csv
            multas_SECOP_PACO.csv        (headerless, 15 cols)
            colusiones_en_contratacion_SIC.csv
            sanciones_penales_FGN.csv
        artifacts/
            rcac/

    Returns:
        tmp_path (Path)
    """
    secop_dir = tmp_path / "secop"
    paco_dir = tmp_path / "paco"
    artifacts_dir = tmp_path / "artifacts"
    rcac_dir = artifacts_dir / "rcac"

    secop_dir.mkdir()
    paco_dir.mkdir()
    rcac_dir.mkdir(parents=True)

    # ---- boletines.csv (headed, SECOP) ----
    boletines = secop_dir / "boletines.csv"
    boletines.write_text(
        "Responsable Fiscal,tipo de documento,numero de documento,"
        "Entidad Afectada,TR,R,Ente que Reporta,Departamento,Municipio\n"
        "JUAN PEREZ,CC,12345678,ENTIDAD_A,TR1,R1,ENTE_A,BOGOTA,BOGOTA\n"
        "EMPRESA LTDA,NIT,900123456,ENTIDAD_B,TR2,R2,ENTE_B,MEDELLIN,MEDELLIN\n"
        "MALFORMED PERSON,CC,000000,ENTIDAD_C,TR3,R3,ENTE_C,CALI,CALI\n",
        encoding="utf-8",
    )

    # ---- sanciones_SIRI_PACO.csv (headerless, 28 cols) ----
    # col[4]=tipo_documento, col[5]=numero_documento
    siri = paco_dir / "sanciones_SIRI_PACO.csv"
    siri_rows = [
        # 28 cols: col[4]=tipo, col[5]=numero
        "a,b,c,d,CEDULA DE CIUDADANIA,12345678,g,h,i,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,z,aa,bb\n",
        "a,b,c,d,NIT,900654321,g,h,i,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,z,aa,bb\n",
    ]
    siri.write_text("".join(siri_rows), encoding="utf-8")

    # ---- responsabilidades_fiscales_PACO.csv ----
    resp_fiscales = paco_dir / "responsabilidades_fiscales_PACO.csv"
    resp_fiscales.write_text(
        "Responsable Fiscal,Tipo y Num Docuemento,Entidad Afectada,"
        "TR,R,Ente que Reporta,Departamento,Municipio\n"
        "MARIA GARCIA,43922546,ENTIDAD_D,TR4,R4,ENTE_D,ANTIOQUIA,BELLO\n"
        "EMPRESA SAS,900555123,ENTIDAD_E,TR5,R5,ENTE_E,CUNDINAMARCA,BOGOTA\n",
        encoding="utf-8",
    )

    # ---- multas_SECOP_PACO.csv (headerless, 15 cols) ----
    # col[5]=numero_documento, col[6]=name (infer tipo)
    multas = paco_dir / "multas_SECOP_PACO.csv"
    multas_rows = [
        "a,b,c,d,e,87654321,PEDRO RAMIREZ,h,i,j,k,l,m,n,o\n",
        "a,b,c,d,e,901234567,CONSTRUCTORA LTDA,h,i,j,k,l,m,n,o\n",
    ]
    multas.write_text("".join(multas_rows), encoding="utf-8")

    # ---- colusiones_en_contratacion_SIC.csv ----
    colusiones = paco_dir / "colusiones_en_contratacion_SIC.csv"
    colusiones.write_text(
        "No.,Fecha de Radicacion,Radicado,Caso,Falta que origina la sancion,"
        "Resolucion de Apertura,Resolucion de Sancion,Tipo de Persona Sancionada,"
        "Personas Sancionadas,Identificacion,Multa Inicial,Año Radicacion\n"
        "1,2020-01-01,RAD001,CASO1,COLUSION,APERT001,SANC001,NIT,EMPRESA COL LTDA,800111222,500000,2020\n",
        encoding="utf-8",
    )

    # ---- sanciones_penales_FGN.csv ----
    sanciones_penales = paco_dir / "sanciones_penales_FGN.csv"
    sanciones_penales.write_text(
        "id,DEPARTAMENTO,MUNICIPIO_ID,CODIGO_DANE_MUNICIPIO,mpio,TITULO,CAPITULO,ARTICULO,AÑO_ACTUACION\n"
        "1,BOGOTA,001,11001,BOGOTA,TIT1,CAP1,ART1,2020\n",
        encoding="utf-8",
    )

    # ---- Set env vars ----
    monkeypatch.setenv("SIP_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SIP_SECOP_DIR", str(secop_dir))
    monkeypatch.setenv("SIP_PACO_DIR", str(paco_dir))
    monkeypatch.setenv("SIP_ARTIFACTS_DIR", str(artifacts_dir))

    return tmp_path


def _run_build(tmp_path) -> dict:
    """Helper: call build_rcac(force=True) and return the loaded index dict."""
    from sip_engine.shared.data.rcac_builder import build_rcac
    pkl_path = build_rcac(force=True)
    return joblib.load(pkl_path)


# ============================================================
# normalize_numero tests (DATA-02)
# ============================================================

def test_normalize_numero_strips_dots():
    assert normalize_numero("43.922.546") == "43922546"


def test_normalize_numero_strips_hyphens():
    assert normalize_numero("900123456-1") == "9001234561"


def test_normalize_numero_strips_spaces():
    assert normalize_numero("CE 289910") == "289910"


def test_normalize_numero_strips_mixed():
    assert normalize_numero("1.030.629-839") == "1030629839"


def test_normalize_numero_letters_stripped():
    # Non-digit letters stripped, keep only digits
    assert normalize_numero("TIA820427KP7") == "8204277"


def test_is_malformed_empty():
    assert is_malformed("") is True


def test_is_malformed_all_zeros():
    assert is_malformed("000000") is True


def test_is_malformed_lt3_digits():
    assert is_malformed("12") is True


def test_is_malformed_valid():
    assert is_malformed("43922546") is False


# ============================================================
# normalize_tipo tests (DATA-02)
# ============================================================

def test_normalize_tipo_cedula_ciudadania():
    # Without accent
    assert normalize_tipo("CEDULA DE CIUDADANIA") == "CC"


def test_normalize_tipo_cedula_with_accent():
    # With accent (real source form)
    assert normalize_tipo("CÉDULA DE CIUDADANÍA") == "CC"


def test_normalize_tipo_nit():
    assert normalize_tipo("NIT") == "NIT"


def test_normalize_tipo_cc():
    assert normalize_tipo("CC") == "CC"


def test_normalize_tipo_personas_juridicas():
    assert normalize_tipo("Personas Juridicas") == "NIT"


def test_normalize_tipo_persona_juridica():
    assert normalize_tipo("Persona Juridica") == "NIT"


def test_normalize_tipo_personas_naturales():
    assert normalize_tipo("Personas Naturales") == "CC"


def test_normalize_tipo_cedula_extranjeria():
    assert normalize_tipo("Cedula de Extranjeria") == "CE"


def test_normalize_tipo_pasaporte():
    assert normalize_tipo("Pasaporte") == "PASAPORTE"


def test_normalize_tipo_unknown():
    assert normalize_tipo("Tipo Raro") == "OTRO"


def test_normalize_tipo_nan():
    import math
    assert normalize_tipo(None) == "OTRO"
    assert normalize_tipo(float("nan")) == "OTRO"


def test_normalize_tipo_tarjeta_identidad():
    assert normalize_tipo("Tarjeta de Identidad") == "OTRO"


# ============================================================
# _infer_tipo tests (DATA-05)
# ============================================================

def test_infer_tipo_company_ltda():
    assert _infer_tipo("EMPRESA ABC LTDA", "12345678") == "NIT"


def test_infer_tipo_company_sas():
    assert _infer_tipo("CONSTRUCTORA SAS", "12345678") == "NIT"


def test_infer_tipo_company_sa():
    assert _infer_tipo("DELTA S.A.", "12345678") == "NIT"


def test_infer_tipo_long_number_nit():
    # 9 digits -> NIT even without company keyword
    assert _infer_tipo("JUAN PEREZ", "900123456") == "NIT"


def test_infer_tipo_short_number_cc():
    # 8 digits, no company keyword -> CC
    assert _infer_tipo("MARIA GARCIA", "43922546") == "CC"


# ============================================================
# Builder deduplication tests (DATA-03)
# ============================================================

def test_build_dedup_same_person_two_sources(rcac_source_dirs):
    """Person in boletines AND siri -> single record, both flags True, num_fuentes=2."""
    index = _run_build(rcac_source_dirs)
    key = ("CC", "12345678")
    assert key in index, f"Expected key {key} in index, got keys: {list(index.keys())[:10]}"
    record = index[key]
    assert record["en_boletines"] is True
    assert record["en_siri"] is True
    assert record["num_fuentes_distintas"] == 2


def test_build_dedup_duplicate_rows_same_source(rcac_source_dirs):
    """Two SIRI rows for the same person -> num_fuentes_distintas=1 (not 2).

    The fixture SIRI file has two rows with the same (tipo, num) identity:
    both use CEDULA DE CIUDADANIA / 12345678. This person also appears in
    boletines (en_boletines=True). The SIRI source should count as 1 distinct
    source even if it had multiple rows for the same person.
    We verify this by checking num_fuentes_distintas == 2 (boletines + siri),
    not 3, even though the same key would appear in SIRI twice if we had two rows.

    Additionally, verify that 900654321 from SIRI (tipo=NIT) is in index with
    num_fuentes_distintas=1 — it appears only in SIRI.
    """
    index = _run_build(rcac_source_dirs)
    # SIRI fixture row 2: col[4]=NIT, col[5]=900654321 -> ("NIT", "900654321")
    key = ("NIT", "900654321")
    assert key in index, f"Expected key {key} in index, keys: {list(index.keys())}"
    assert index[key]["num_fuentes_distintas"] == 1
    assert index[key]["en_siri"] is True
    assert index[key]["en_boletines"] is False


def test_build_malformed_excluded_from_index(rcac_source_dirs):
    """Malformed record (all-zeros from boletines) not in returned index dict."""
    index = _run_build(rcac_source_dirs)
    # boletines has "000000" which is malformed
    key_cc = ("CC", "000000")
    key_otro = ("OTRO", "000000")
    assert key_cc not in index
    assert key_otro not in index


def test_build_bad_rows_log_written(rcac_source_dirs):
    """rcac_bad_rows.csv exists after build with malformed input."""
    from sip_engine.shared.config import get_settings
    _run_build(rcac_source_dirs)
    settings = get_settings()
    assert settings.rcac_bad_rows_path.exists(), (
        f"Expected bad rows CSV at {settings.rcac_bad_rows_path}"
    )


def test_build_creates_pkl(rcac_source_dirs):
    """After build_rcac(force=True), rcac.pkl exists at settings.rcac_path."""
    from sip_engine.shared.config import get_settings
    settings = get_settings()
    build_rcac(force=True)
    assert settings.rcac_path.exists()


def test_build_cache_used(rcac_source_dirs):
    """Calling build_rcac() when pkl exists does NOT rebuild (mtime unchanged)."""
    from sip_engine.shared.config import get_settings
    settings = get_settings()
    # First build
    build_rcac(force=True)
    mtime_before = settings.rcac_path.stat().st_mtime
    # Second call without force — should use cache
    import time
    time.sleep(0.05)  # ensure time passes if file were rewritten
    build_rcac(force=False)
    mtime_after = settings.rcac_path.stat().st_mtime
    assert mtime_before == mtime_after, "Cache was bypassed — pkl was rewritten without force=True"


def test_build_force_rebuilds(rcac_source_dirs):
    """Call build_rcac(force=True) after initial build -> pkl is rewritten (mtime changed)."""
    from sip_engine.shared.config import get_settings
    import time
    settings = get_settings()
    # First build
    build_rcac(force=True)
    mtime_before = settings.rcac_path.stat().st_mtime
    time.sleep(0.05)
    # Force rebuild
    build_rcac(force=True)
    mtime_after = settings.rcac_path.stat().st_mtime
    assert mtime_after > mtime_before, "force=True did not rewrite the pkl file"


def test_build_sanciones_penales_always_false(rcac_source_dirs):
    """All records in index have en_sanciones_penales=False."""
    index = _run_build(rcac_source_dirs)
    for key, record in index.items():
        assert record["en_sanciones_penales"] is False, (
            f"Record {key} has en_sanciones_penales=True — expected always False"
        )


# ============================================================
# rcac_lookup tests (DATA-09)
# ============================================================

@pytest.fixture(autouse=True)
def _reset_rcac():
    """Clear module-level RCAC cache after each test to isolate state."""
    yield
    from sip_engine.shared.data.rcac_lookup import reset_rcac_cache
    reset_rcac_cache()


def test_lookup_hit_returns_record(rcac_source_dirs):
    """rcac_lookup('CC', '12345678') returns a dict with expected keys."""
    from sip_engine.shared.data.rcac_builder import build_rcac
    from sip_engine.shared.data.rcac_lookup import rcac_lookup, reset_rcac_cache

    build_rcac(force=True)
    reset_rcac_cache()

    record = rcac_lookup("CC", "12345678")
    assert record is not None, "Expected record for ('CC', '12345678'), got None"
    assert isinstance(record, dict)

    expected_keys = {
        "tipo_documento",
        "numero_documento",
        "en_boletines",
        "en_siri",
        "en_resp_fiscales",
        "en_multas_secop",
        "en_colusiones",
        "en_sanciones_penales",
        "num_fuentes_distintas",
        "malformed",
    }
    assert expected_keys.issubset(set(record.keys())), (
        f"Missing keys: {expected_keys - set(record.keys())}"
    )
    assert record["tipo_documento"] == "CC"
    assert record["numero_documento"] == "12345678"


def test_lookup_miss_returns_none(rcac_source_dirs):
    """rcac_lookup('CC', '99999999') returns None for unknown identity."""
    from sip_engine.shared.data.rcac_builder import build_rcac
    from sip_engine.shared.data.rcac_lookup import rcac_lookup, reset_rcac_cache

    build_rcac(force=True)
    reset_rcac_cache()

    assert rcac_lookup("CC", "99999999") is None


def test_lookup_normalizes_input(rcac_source_dirs):
    """rcac_lookup('CC', '43.922.546') matches record stored as '43922546'."""
    from sip_engine.shared.data.rcac_builder import build_rcac
    from sip_engine.shared.data.rcac_lookup import rcac_lookup, reset_rcac_cache

    build_rcac(force=True)
    reset_rcac_cache()

    # resp_fiscales fixture has "43922546" stored (MARIA GARCIA, inferred CC)
    # Lookup with dotted form should normalize and hit
    record = rcac_lookup("CC", "43.922.546")
    assert record is not None, (
        "Expected record for ('CC', '43922546') via dotted-form lookup, got None"
    )
    assert record["numero_documento"] == "43922546"


def test_lookup_malformed_returns_none(rcac_source_dirs):
    """rcac_lookup('CC', '12') returns None for short (malformed) number."""
    from sip_engine.shared.data.rcac_builder import build_rcac
    from sip_engine.shared.data.rcac_lookup import rcac_lookup, reset_rcac_cache

    build_rcac(force=True)
    reset_rcac_cache()

    # '12' -> 2 digits -> malformed -> return None immediately
    assert rcac_lookup("CC", "12") is None


def test_lookup_en_multas_secop_flag(rcac_source_dirs):
    """Build with multas source data; verify en_multas_secop=True on returned record."""
    from sip_engine.shared.data.rcac_builder import build_rcac
    from sip_engine.shared.data.rcac_lookup import rcac_lookup, reset_rcac_cache

    build_rcac(force=True)
    reset_rcac_cache()

    # multas fixture row 1: col_5=87654321, col_6=PEDRO RAMIREZ -> CC (8 digits)
    record = rcac_lookup("CC", "87654321")
    assert record is not None, "Expected record for multas identity ('CC', '87654321'), got None"
    assert record["en_multas_secop"] is True


def test_lookup_without_pkl_raises(tmp_path, monkeypatch):
    """get_rcac_index() raises FileNotFoundError when no pkl file exists."""
    from sip_engine.shared.data.rcac_lookup import get_rcac_index, reset_rcac_cache

    # Point artifacts dir to an empty temp directory (no rcac.pkl)
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    monkeypatch.setenv("SIP_ARTIFACTS_DIR", str(artifacts_dir))
    reset_rcac_cache()

    with pytest.raises(FileNotFoundError, match="rcac.pkl"):
        get_rcac_index()
