"""Tests for IRIC calculator and threshold calibration.

Plan 06-01: TDD tests for:
- thresholds.py: calibrate_iric_thresholds, get_threshold, load/save roundtrip, cache reset
- calculator.py: all 11 components, 4 aggregate scores, edge cases
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# ============================================================
# Threshold tests
# ============================================================


@pytest.fixture()
def simple_df():
    """5-row DataFrame with 2 contract types for calibration tests."""
    return pd.DataFrame(
        {
            "tipo_contrato": [
                "Prestacion de servicios",
                "Prestacion de servicios",
                "Prestacion de servicios",
                "Compraventa",
                "Compraventa",
            ],
            "num_contratos_previos_nacional": [1, 3, 5, 2, 4],
            "dias_publicidad": [0, 5, 10, 2, 8],
            "dias_decision": [10, 20, 30, 15, 45],
            "valor_contrato": [1_000_000, 5_000_000, 10_000_000, 2_000_000, 8_000_000],
        }
    )


@pytest.fixture()
def rare_type_df():
    """DataFrame where one type has < 30 rows (should be merged into Otro)."""
    # "Prestacion de servicios" gets 50 rows (above threshold)
    # "Obra" gets 5 rows (below threshold of 30 — should merge into Otro)
    rows = []
    for i in range(50):
        rows.append(
            {
                "tipo_contrato": "Prestacion de servicios",
                "num_contratos_previos_nacional": i,
                "dias_publicidad": i % 10,
                "dias_decision": i % 30,
                "valor_contrato": (i + 1) * 1_000_000,
            }
        )
    for i in range(5):
        rows.append(
            {
                "tipo_contrato": "Obra",
                "num_contratos_previos_nacional": i * 2,
                "dias_publicidad": i,
                "dias_decision": i * 5,
                "valor_contrato": i * 2_000_000,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture()
def sample_thresholds():
    """Pre-built threshold dict for testing get_threshold."""
    return {
        "tipo_contrato": {
            "Prestacion de servicios": {
                "num_contratos_previos_nacional": {"p1": 1, "p5": 1, "p95": 3, "p99": 7},
                "dias_publicidad": {"p1": 0, "p5": 0, "p95": 10, "p99": 14},
                "dias_decision": {"p1": 0, "p5": 0, "p95": 43, "p99": 125},
                "valor_contrato": {"p1": 0, "p5": 0, "p95": 120_000_000, "p99": 221_053_429},
            },
            "Otro": {
                "num_contratos_previos_nacional": {"p1": 1, "p5": 1, "p95": 5, "p99": 9},
                "dias_publicidad": {"p1": 0, "p5": 0, "p95": 12, "p99": 20},
                "dias_decision": {"p1": 0, "p5": 0, "p95": 55, "p99": 150},
                "valor_contrato": {"p1": 0, "p5": 0, "p95": 200_000_000, "p99": 500_000_000},
            },
        },
        "calibration_date": "2026-03-01T00:00:00Z",
        "n_contracts": 55,
        "min_group_size": 30,
    }


class TestCalibrateThresholds:
    def test_calibrate_basic(self, simple_df):
        """5-row DataFrame with 2 contract types — verify percentiles computed."""
        from sip_engine.iric.thresholds import calibrate_iric_thresholds

        result = calibrate_iric_thresholds(simple_df, min_group_size=1)

        # Both types should be present (both have >= 1 row)
        assert "tipo_contrato" in result
        tipo_keys = set(result["tipo_contrato"].keys())
        assert "Prestacion de servicios" in tipo_keys or "Otro" in tipo_keys

        # Metadata fields
        assert "calibration_date" in result
        assert "n_contracts" in result
        assert result["n_contracts"] == 5
        assert result["min_group_size"] == 1

    def test_calibrate_percentile_structure(self, simple_df):
        """Each type+variable entry has p1, p5, p95, p99 keys."""
        from sip_engine.iric.thresholds import calibrate_iric_thresholds

        result = calibrate_iric_thresholds(simple_df, min_group_size=1)

        for tipo, variables in result["tipo_contrato"].items():
            for var_name, percentiles in variables.items():
                assert "p1" in percentiles, f"Missing p1 for {tipo}/{var_name}"
                assert "p5" in percentiles, f"Missing p5 for {tipo}/{var_name}"
                assert "p95" in percentiles, f"Missing p95 for {tipo}/{var_name}"
                assert "p99" in percentiles, f"Missing p99 for {tipo}/{var_name}"

    def test_calibrate_rare_types_merged(self, rare_type_df):
        """Types with < 30 rows are merged into Otro."""
        from sip_engine.iric.thresholds import calibrate_iric_thresholds

        result = calibrate_iric_thresholds(rare_type_df, min_group_size=30)

        tipo_keys = set(result["tipo_contrato"].keys())
        # "Obra" has only 5 rows — should be merged into Otro, not present as its own key
        assert "Obra" not in tipo_keys
        # "Prestacion de servicios" has 50 rows — should be present
        assert "Prestacion de servicios" in tipo_keys
        # "Otro" should exist (collected rare types)
        assert "Otro" in tipo_keys

    def test_calibrate_all_rare_merged_into_otro(self):
        """When all types are rare, all merge into Otro."""
        from sip_engine.iric.thresholds import calibrate_iric_thresholds

        df = pd.DataFrame(
            {
                "tipo_contrato": ["TypeA", "TypeA", "TypeB"],
                "num_contratos_previos_nacional": [1, 2, 3],
                "dias_publicidad": [0, 5, 10],
                "dias_decision": [10, 20, 30],
                "valor_contrato": [1_000_000, 2_000_000, 3_000_000],
            }
        )

        result = calibrate_iric_thresholds(df, min_group_size=5)

        tipo_keys = set(result["tipo_contrato"].keys())
        assert "TypeA" not in tipo_keys
        assert "TypeB" not in tipo_keys
        assert "Otro" in tipo_keys

    def test_calibrate_handles_nan_values(self):
        """NaN values in continuous columns should be ignored (nanpercentile)."""
        from sip_engine.iric.thresholds import calibrate_iric_thresholds

        import numpy as np

        df = pd.DataFrame(
            {
                "tipo_contrato": ["PS", "PS", "PS", "PS", "PS"],
                "num_contratos_previos_nacional": [1.0, 2.0, float("nan"), 4.0, 5.0],
                "dias_publicidad": [0, 5, 10, float("nan"), 20],
                "dias_decision": [10, float("nan"), 30, 40, 50],
                "valor_contrato": [1_000_000, 2_000_000, 3_000_000, 4_000_000, float("nan")],
            }
        )

        # Should not raise
        result = calibrate_iric_thresholds(df, min_group_size=1)
        assert result is not None


class TestGetThreshold:
    def test_get_threshold_exact_match(self, sample_thresholds):
        """Known tipo_contrato returns correct percentile."""
        from sip_engine.iric.thresholds import get_threshold

        val = get_threshold(sample_thresholds, "Prestacion de servicios", "dias_publicidad", "p99")
        assert val == 14

    def test_get_threshold_exact_match_p95(self, sample_thresholds):
        """P95 for dias_decision."""
        from sip_engine.iric.thresholds import get_threshold

        val = get_threshold(sample_thresholds, "Prestacion de servicios", "dias_decision", "p95")
        assert val == 43

    def test_get_threshold_fallback_otro(self, sample_thresholds):
        """Unknown tipo_contrato falls back to Otro."""
        from sip_engine.iric.thresholds import get_threshold

        val = get_threshold(sample_thresholds, "Concesion Obra Publica", "dias_publicidad", "p99")
        # Should fall back to Otro's p99 = 20
        assert val == 20

    def test_get_threshold_fallback_hardcoded(self):
        """When Otro is also missing, falls back to VigIA hardcoded defaults."""
        from sip_engine.iric.thresholds import get_threshold

        empty_thresholds = {
            "tipo_contrato": {},
            "calibration_date": "2026-03-01T00:00:00Z",
            "n_contracts": 0,
            "min_group_size": 30,
        }

        # VigIA default for dias_publicidad p99 = 14
        val = get_threshold(empty_thresholds, "Desconocido", "dias_publicidad", "p99")
        assert val == 14

        # VigIA default for dias_decision p95 = 43
        val = get_threshold(empty_thresholds, "Desconocido", "dias_decision", "p95")
        assert val == 43

        # VigIA default for num_contratos_previos_nacional p95 = 3
        val = get_threshold(empty_thresholds, "Desconocido", "num_contratos_previos_nacional", "p95")
        assert val == 3

        # VigIA default for valor_contrato p99 = 500_000_000
        val = get_threshold(empty_thresholds, "Desconocido", "valor_contrato", "p99")
        assert val == 500_000_000

    def test_get_threshold_returns_none_for_unknown_combo(self):
        """Returns None when variable/percentile combo is unknown everywhere."""
        from sip_engine.iric.thresholds import get_threshold

        empty_thresholds = {"tipo_contrato": {}}

        val = get_threshold(empty_thresholds, "Desconocido", "mystery_variable", "p42")
        assert val is None


class TestLoadSaveThresholds:
    def test_load_save_roundtrip(self, sample_thresholds):
        """Save then load returns identical dict."""
        from sip_engine.iric.thresholds import (
            load_iric_thresholds,
            reset_iric_thresholds_cache,
            save_iric_thresholds,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "thresholds.json"
            saved_path = save_iric_thresholds(sample_thresholds, path)
            assert saved_path == path

            reset_iric_thresholds_cache()
            loaded = load_iric_thresholds(path)

        assert loaded["n_contracts"] == sample_thresholds["n_contracts"]
        assert loaded["calibration_date"] == sample_thresholds["calibration_date"]
        assert (
            loaded["tipo_contrato"]["Prestacion de servicios"]["dias_publicidad"]["p99"]
            == sample_thresholds["tipo_contrato"]["Prestacion de servicios"]["dias_publicidad"][
                "p99"
            ]
        )

    def test_cache_reset(self, sample_thresholds):
        """After reset, next load re-reads from disk."""
        from sip_engine.iric.thresholds import (
            load_iric_thresholds,
            reset_iric_thresholds_cache,
            save_iric_thresholds,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "thresholds.json"
            save_iric_thresholds(sample_thresholds, path)

            reset_iric_thresholds_cache()
            loaded1 = load_iric_thresholds(path)

            # Modify the file to something different
            modified = dict(sample_thresholds)
            modified["n_contracts"] = 9999
            with open(path, "w") as f:
                json.dump(modified, f)

            # Without reset, should still return cached value
            loaded_cached = load_iric_thresholds(path)
            assert loaded_cached["n_contracts"] == sample_thresholds["n_contracts"]

            # After reset, should read fresh value
            reset_iric_thresholds_cache()
            loaded_fresh = load_iric_thresholds(path)
            assert loaded_fresh["n_contracts"] == 9999

    def test_save_creates_parent_dir(self, sample_thresholds):
        """save_iric_thresholds creates parent directory if it doesn't exist."""
        from sip_engine.iric.thresholds import save_iric_thresholds

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "dir" / "thresholds.json"
            saved_path = save_iric_thresholds(sample_thresholds, path)
            assert saved_path.exists()


# ============================================================
# Calculator tests
# ============================================================


@pytest.fixture()
def minimal_thresholds():
    """Minimal thresholds dict for calculator tests."""
    return {
        "tipo_contrato": {
            "Prestacion de servicios": {
                "num_contratos_previos_nacional": {"p1": 1, "p5": 1, "p95": 3, "p99": 7},
                "dias_publicidad": {"p1": 0, "p5": 0, "p95": 10, "p99": 14},
                "dias_decision": {"p1": 0, "p5": 0, "p95": 43, "p99": 125},
                "valor_contrato": {"p1": 0, "p5": 0, "p95": 120_000_000, "p99": 500_000_000},
            },
            "Otro": {
                "num_contratos_previos_nacional": {"p1": 1, "p5": 1, "p95": 3, "p99": 7},
                "dias_publicidad": {"p1": 0, "p5": 0, "p95": 10, "p99": 14},
                "dias_decision": {"p1": 0, "p5": 0, "p95": 43, "p99": 125},
                "valor_contrato": {"p1": 0, "p5": 0, "p95": 120_000_000, "p99": 500_000_000},
            },
        },
        "calibration_date": "2026-03-01T00:00:00Z",
        "n_contracts": 100,
        "min_group_size": 30,
    }


@pytest.fixture()
def base_row():
    """Minimal valid contract row for testing."""
    return {
        "Modalidad de Contratacion": "Licitacion publica",
        "TipoDocProveedor": "NIT",
        "Documento Proveedor": "900123456",
        "Valor del Contrato": 10_000_000.0,
        "Justificacion Modalidad de Contratacion": "Por necesidad institucional",
        "Tipo de Contrato": "Prestacion de servicios",
    }


@pytest.fixture()
def procesos_normal():
    """Normal procesos_data with 3 providers and reasonable days."""
    return {
        "Proveedores Unicos con Respuestas": 3,
        "dias_publicidad": 5,
        "dias_decision": 10,
    }


@pytest.fixture()
def provider_history_normal():
    """Normal provider history — no overruns or delays."""
    return {
        "num_contratos": 2,
        "num_sobrecostos": 0,
        "num_retrasos": 0,
        "num_contratos_depto": 1,
        "valor_total_contratos_nacional": 20_000_000.0,
        "valor_total_contratos_depto": 10_000_000.0,
    }


class TestUnicoProponente:
    def test_unico_proponente_fires_on_single_bidder(self, base_row, minimal_thresholds):
        """1 unique provider -> unico_proponente = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        procesos = {"Proveedores Unicos con Respuestas": 1, "dias_publicidad": 5, "dias_decision": 10}
        components = compute_iric_components(base_row, procesos, None, minimal_thresholds, 1)
        assert components["unico_proponente"] == 1

    def test_unico_proponente_no_fire_on_multiple(self, base_row, minimal_thresholds):
        """3 unique providers -> unico_proponente = 0."""
        from sip_engine.iric.calculator import compute_iric_components

        procesos = {"Proveedores Unicos con Respuestas": 3, "dias_publicidad": 5, "dias_decision": 10}
        components = compute_iric_components(base_row, procesos, None, minimal_thresholds, 1)
        assert components["unico_proponente"] == 0

    def test_unico_proponente_none_when_no_procesos(self, base_row, minimal_thresholds):
        """No procesos_data -> unico_proponente = None."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, None, None, minimal_thresholds, 1)
        assert components["unico_proponente"] is None

    def test_unico_proponente_fires_on_zero(self, base_row, minimal_thresholds):
        """0 unique providers -> unico_proponente = 1 (0 <= 1)."""
        from sip_engine.iric.calculator import compute_iric_components

        procesos = {"Proveedores Unicos con Respuestas": 0, "dias_publicidad": 5, "dias_decision": 10}
        components = compute_iric_components(base_row, procesos, None, minimal_thresholds, 1)
        assert components["unico_proponente"] == 1


class TestProveedorMultiproposito:
    def test_proveedor_multiproposito_fires(self, base_row, minimal_thresholds, procesos_normal):
        """num_actividades=3 -> proveedor_multiproposito = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, procesos_normal, None, minimal_thresholds, 3)
        assert components["proveedor_multiproposito"] == 1

    def test_proveedor_multiproposito_no_fire(self, base_row, minimal_thresholds, procesos_normal):
        """num_actividades=1 -> proveedor_multiproposito = 0."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, procesos_normal, None, minimal_thresholds, 1)
        assert components["proveedor_multiproposito"] == 0

    def test_proveedor_multiproposito_zero_actividades(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """num_actividades=0 -> proveedor_multiproposito = 0."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, procesos_normal, None, minimal_thresholds, 0)
        assert components["proveedor_multiproposito"] == 0


class TestHistorialProveedorAlto:
    def test_historial_proveedor_alto_fires_above_p95(self, base_row, minimal_thresholds, procesos_normal):
        """num_contratos=10, threshold=3 -> historial_proveedor_alto = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        provider_history = {"num_contratos": 10, "num_sobrecostos": 0, "num_retrasos": 0}
        components = compute_iric_components(
            base_row, procesos_normal, provider_history, minimal_thresholds, 1
        )
        assert components["historial_proveedor_alto"] == 1

    def test_historial_proveedor_alto_no_fire_below(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """num_contratos=2, threshold=3 -> historial_proveedor_alto = 0."""
        from sip_engine.iric.calculator import compute_iric_components

        provider_history = {"num_contratos": 2, "num_sobrecostos": 0, "num_retrasos": 0}
        components = compute_iric_components(
            base_row, procesos_normal, provider_history, minimal_thresholds, 1
        )
        assert components["historial_proveedor_alto"] == 0

    def test_historial_proveedor_alto_no_history_is_zero(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """provider_history=None -> historial_proveedor_alto = 0 (new provider)."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, procesos_normal, None, minimal_thresholds, 1)
        assert components["historial_proveedor_alto"] == 0


class TestContratacionDirecta:
    def test_contratacion_directa_fires(self, base_row, minimal_thresholds, procesos_normal):
        """Both 'Contratacion directa' modality strings -> 1."""
        from sip_engine.iric.calculator import compute_iric_components

        for modalidad in [
            "Contratacion directa",
            "Contratacion Directa (con ofertas)",
            "Contratación directa",
            "Contratación Directa (con ofertas)",
        ]:
            row = dict(base_row)
            row["Modalidad de Contratacion"] = modalidad
            components = compute_iric_components(row, procesos_normal, None, minimal_thresholds, 1)
            assert components["contratacion_directa"] == 1, f"Should fire for: {modalidad}"

    def test_contratacion_directa_no_fire(self, base_row, minimal_thresholds, procesos_normal):
        """Licitacion publica -> contratacion_directa = 0."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, procesos_normal, None, minimal_thresholds, 1)
        assert components["contratacion_directa"] == 0


class TestRegimenEspecial:
    def test_regimen_especial_fires(self, base_row, minimal_thresholds, procesos_normal):
        """Both 'regimen especial' modality strings -> 1."""
        from sip_engine.iric.calculator import compute_iric_components

        for modalidad in [
            "Contratacion regimen especial",
            "Contratacion regimen especial (con ofertas)",
            "Contratación régimen especial",
            "Contratación régimen especial (con ofertas)",
        ]:
            row = dict(base_row)
            row["Modalidad de Contratacion"] = modalidad
            components = compute_iric_components(row, procesos_normal, None, minimal_thresholds, 1)
            assert components["regimen_especial"] == 1, f"Should fire for: {modalidad}"

    def test_regimen_especial_no_fire_licitacion(self, base_row, minimal_thresholds, procesos_normal):
        """Licitacion publica -> regimen_especial = 0."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, procesos_normal, None, minimal_thresholds, 1)
        assert components["regimen_especial"] == 0


class TestPeriodoPublicidadExtremo:
    def test_periodo_publicidad_extremo_fires_on_zero(
        self, base_row, minimal_thresholds
    ):
        """dias_publicidad=0 -> periodo_publicidad_extremo = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        procesos = {"Proveedores Unicos con Respuestas": 3, "dias_publicidad": 0, "dias_decision": 10}
        components = compute_iric_components(base_row, procesos, None, minimal_thresholds, 1)
        assert components["periodo_publicidad_extremo"] == 1

    def test_periodo_publicidad_extremo_fires_above_p99(self, base_row, minimal_thresholds):
        """dias_publicidad=50, p99=14 -> periodo_publicidad_extremo = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        procesos = {
            "Proveedores Unicos con Respuestas": 3,
            "dias_publicidad": 50,
            "dias_decision": 10,
        }
        components = compute_iric_components(base_row, procesos, None, minimal_thresholds, 1)
        assert components["periodo_publicidad_extremo"] == 1

    def test_periodo_publicidad_extremo_no_fire_normal(self, base_row, minimal_thresholds):
        """dias_publicidad=5, p99=14 -> periodo_publicidad_extremo = 0."""
        from sip_engine.iric.calculator import compute_iric_components

        procesos = {"Proveedores Unicos con Respuestas": 3, "dias_publicidad": 5, "dias_decision": 10}
        components = compute_iric_components(base_row, procesos, None, minimal_thresholds, 1)
        assert components["periodo_publicidad_extremo"] == 0

    def test_periodo_publicidad_extremo_none_when_no_procesos(self, base_row, minimal_thresholds):
        """procesos_data=None -> periodo_publicidad_extremo = None."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, None, None, minimal_thresholds, 1)
        assert components["periodo_publicidad_extremo"] is None


class TestDatosFaltantes:
    def test_datos_faltantes_error_documento_no_definido(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """TipoDocProveedor='No Definido' -> datos_faltantes = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        row = dict(base_row)
        row["TipoDocProveedor"] = "No Definido"
        components = compute_iric_components(row, procesos_normal, None, minimal_thresholds, 1)
        assert components["datos_faltantes"] == 1

    def test_datos_faltantes_error_documento_short_number(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """Short document number (< 6 digits) -> datos_faltantes = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        row = dict(base_row)
        row["Documento Proveedor"] = "123"  # Only 3 digits
        components = compute_iric_components(row, procesos_normal, None, minimal_thresholds, 1)
        assert components["datos_faltantes"] == 1

    def test_datos_faltantes_error_documento_no_digits(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """Document with no digits -> datos_faltantes = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        row = dict(base_row)
        row["Documento Proveedor"] = "ABCDEF"  # No digits
        components = compute_iric_components(row, procesos_normal, None, minimal_thresholds, 1)
        assert components["datos_faltantes"] == 1

    def test_datos_faltantes_error_justificacion_none(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """Justificacion=None -> datos_faltantes = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        row = dict(base_row)
        row["Justificacion Modalidad de Contratacion"] = None
        components = compute_iric_components(row, procesos_normal, None, minimal_thresholds, 1)
        assert components["datos_faltantes"] == 1

    def test_datos_faltantes_error_justificacion_no_especificado(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """Justificacion='no especificado' -> datos_faltantes = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        row = dict(base_row)
        row["Justificacion Modalidad de Contratacion"] = "no especificado"
        components = compute_iric_components(row, procesos_normal, None, minimal_thresholds, 1)
        assert components["datos_faltantes"] == 1

    def test_datos_faltantes_error_valor(self, base_row, minimal_thresholds, procesos_normal):
        """Valor > P99 threshold -> datos_faltantes = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        row = dict(base_row)
        row["Valor del Contrato"] = 600_000_000.0  # Above P99 = 500_000_000
        components = compute_iric_components(row, procesos_normal, None, minimal_thresholds, 1)
        assert components["datos_faltantes"] == 1

    def test_datos_faltantes_all_clean(self, base_row, minimal_thresholds, procesos_normal):
        """All 3 sub-checks pass -> datos_faltantes = 0."""
        from sip_engine.iric.calculator import compute_iric_components

        # base_row has valid NIT, valid justificacion, normal valor
        components = compute_iric_components(base_row, procesos_normal, None, minimal_thresholds, 1)
        assert components["datos_faltantes"] == 0


class TestPeriodoDecisionExtremo:
    def test_periodo_decision_extremo_fires_on_zero(self, base_row, minimal_thresholds):
        """dias_decision=0 -> periodo_decision_extremo = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        procesos = {"Proveedores Unicos con Respuestas": 3, "dias_publicidad": 5, "dias_decision": 0}
        components = compute_iric_components(base_row, procesos, None, minimal_thresholds, 1)
        assert components["periodo_decision_extremo"] == 1

    def test_periodo_decision_extremo_fires_above_p95(self, base_row, minimal_thresholds):
        """dias_decision=100, p95=43 -> periodo_decision_extremo = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        procesos = {
            "Proveedores Unicos con Respuestas": 3,
            "dias_publicidad": 5,
            "dias_decision": 100,
        }
        components = compute_iric_components(base_row, procesos, None, minimal_thresholds, 1)
        assert components["periodo_decision_extremo"] == 1

    def test_periodo_decision_extremo_no_fire_normal(self, base_row, minimal_thresholds):
        """dias_decision=10, p95=43 -> periodo_decision_extremo = 0."""
        from sip_engine.iric.calculator import compute_iric_components

        procesos = {"Proveedores Unicos con Respuestas": 3, "dias_publicidad": 5, "dias_decision": 10}
        components = compute_iric_components(base_row, procesos, None, minimal_thresholds, 1)
        assert components["periodo_decision_extremo"] == 0

    def test_periodo_decision_extremo_none_when_no_procesos(self, base_row, minimal_thresholds):
        """procesos_data=None -> periodo_decision_extremo = None."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, None, None, minimal_thresholds, 1)
        assert components["periodo_decision_extremo"] is None


class TestProveedorSobrecostosPrevios:
    def test_proveedor_sobrecostos_previos_new_provider(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """provider_history=None -> proveedor_sobrecostos_previos = 0 (new provider rule)."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, procesos_normal, None, minimal_thresholds, 1)
        assert components["proveedor_sobrecostos_previos"] == 0

    def test_proveedor_sobrecostos_previos_with_history(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """num_sobrecostos=2 -> proveedor_sobrecostos_previos = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        provider_history = {"num_contratos": 5, "num_sobrecostos": 2, "num_retrasos": 0}
        components = compute_iric_components(
            base_row, procesos_normal, provider_history, minimal_thresholds, 1
        )
        assert components["proveedor_sobrecostos_previos"] == 1

    def test_proveedor_sobrecostos_previos_zero_sobrecostos(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """num_sobrecostos=0, has history -> proveedor_sobrecostos_previos = 0."""
        from sip_engine.iric.calculator import compute_iric_components

        provider_history = {"num_contratos": 5, "num_sobrecostos": 0, "num_retrasos": 0}
        components = compute_iric_components(
            base_row, procesos_normal, provider_history, minimal_thresholds, 1
        )
        assert components["proveedor_sobrecostos_previos"] == 0


class TestProveedorRetrasosPrevios:
    def test_proveedor_retrasos_previos_new_provider(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """provider_history=None -> proveedor_retrasos_previos = 0 (new provider rule)."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, procesos_normal, None, minimal_thresholds, 1)
        assert components["proveedor_retrasos_previos"] == 0

    def test_proveedor_retrasos_previos_with_history(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """num_retrasos=3 -> proveedor_retrasos_previos = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        provider_history = {"num_contratos": 5, "num_sobrecostos": 0, "num_retrasos": 3}
        components = compute_iric_components(
            base_row, procesos_normal, provider_history, minimal_thresholds, 1
        )
        assert components["proveedor_retrasos_previos"] == 1


class TestAusenciaProceso:
    def test_ausencia_proceso_fires(self, base_row, minimal_thresholds):
        """procesos_data=None -> ausencia_proceso = 1."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, None, None, minimal_thresholds, 1)
        assert components["ausencia_proceso"] == 1

    def test_ausencia_proceso_no_fire(self, base_row, minimal_thresholds, procesos_normal):
        """procesos_data={} (non-None) -> ausencia_proceso = 0."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, procesos_normal, None, minimal_thresholds, 1)
        assert components["ausencia_proceso"] == 0

    def test_ausencia_proceso_no_fire_empty_dict(self, base_row, minimal_thresholds):
        """procesos_data={} (empty dict) -> ausencia_proceso = 0 (present but empty)."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, {}, None, minimal_thresholds, 1)
        assert components["ausencia_proceso"] == 0


class TestIricScores:
    def test_iric_score_formula(self, minimal_thresholds):
        """Known 11 components -> verify (1/11)*sum."""
        from sip_engine.iric.calculator import compute_iric_scores

        # All 1s: score = 1.0
        components_all_one = {
            "unico_proponente": 1,
            "proveedor_multiproposito": 1,
            "historial_proveedor_alto": 1,
            "contratacion_directa": 1,
            "regimen_especial": 1,
            "periodo_publicidad_extremo": 1,
            "datos_faltantes": 1,
            "periodo_decision_extremo": 1,
            "proveedor_sobrecostos_previos": 1,
            "proveedor_retrasos_previos": 1,
            "ausencia_proceso": 1,
        }
        scores = compute_iric_scores(components_all_one)
        assert abs(scores["iric_score"] - 1.0) < 1e-9

    def test_iric_score_partial(self, minimal_thresholds):
        """Some 1s: score = count / 11."""
        from sip_engine.iric.calculator import compute_iric_scores

        # 5 ones out of 11
        components = {
            "unico_proponente": 1,
            "proveedor_multiproposito": 1,
            "historial_proveedor_alto": 0,
            "contratacion_directa": 1,
            "regimen_especial": 0,
            "periodo_publicidad_extremo": 1,
            "datos_faltantes": 0,
            "periodo_decision_extremo": 1,
            "proveedor_sobrecostos_previos": 0,
            "proveedor_retrasos_previos": 0,
            "ausencia_proceso": 0,
        }
        scores = compute_iric_scores(components)
        expected = 5 / 11
        assert abs(scores["iric_score"] - expected) < 1e-9

    def test_iric_dimension_scores(self):
        """Verify competencia/transparencia/anomalias sub-sums are correct."""
        from sip_engine.iric.calculator import compute_iric_scores

        components = {
            # Competition (6): all 1 -> iric_competencia = 1.0
            "unico_proponente": 1,
            "proveedor_multiproposito": 1,
            "historial_proveedor_alto": 1,
            "contratacion_directa": 1,
            "regimen_especial": 1,
            "periodo_publicidad_extremo": 1,
            # Transparency (2): 1 of 2 -> iric_transparencia = 0.5
            "datos_faltantes": 1,
            "periodo_decision_extremo": 0,
            # Anomaly (3): 2 of 3 -> iric_anomalias = 2/3
            "proveedor_sobrecostos_previos": 1,
            "proveedor_retrasos_previos": 1,
            "ausencia_proceso": 0,
        }
        scores = compute_iric_scores(components)

        assert abs(scores["iric_competencia"] - 1.0) < 1e-9
        assert abs(scores["iric_transparencia"] - 0.5) < 1e-9
        assert abs(scores["iric_anomalias"] - 2 / 3) < 1e-9

    def test_iric_scores_none_as_zero(self):
        """Components with None values are treated as 0 in sums (VigIA pattern)."""
        from sip_engine.iric.calculator import compute_iric_scores

        components = {
            "unico_proponente": None,  # Missing: procesos_data was None
            "proveedor_multiproposito": 1,
            "historial_proveedor_alto": 0,
            "contratacion_directa": 0,
            "regimen_especial": 0,
            "periodo_publicidad_extremo": None,  # Missing: procesos_data was None
            "datos_faltantes": 0,
            "periodo_decision_extremo": None,  # Missing: procesos_data was None
            "proveedor_sobrecostos_previos": 0,
            "proveedor_retrasos_previos": 0,
            "ausencia_proceso": 1,  # Fires because procesos was None
        }
        scores = compute_iric_scores(components)

        # None -> 0: so sum = 0 + 1 + 0 + 0 + 0 + 0 + 0 + 0 + 0 + 0 + 1 = 2
        expected_iric = 2 / 11
        assert abs(scores["iric_score"] - expected_iric) < 1e-9

        # iric_competencia: [None, 1, 0, 0, 0, None] -> [0, 1, 0, 0, 0, 0] -> sum=1 -> 1/6
        expected_competencia = 1 / 6
        assert abs(scores["iric_competencia"] - expected_competencia) < 1e-9

    def test_iric_scores_all_zeros(self):
        """All-zero components -> all scores = 0."""
        from sip_engine.iric.calculator import compute_iric_scores

        components = {
            "unico_proponente": 0,
            "proveedor_multiproposito": 0,
            "historial_proveedor_alto": 0,
            "contratacion_directa": 0,
            "regimen_especial": 0,
            "periodo_publicidad_extremo": 0,
            "datos_faltantes": 0,
            "periodo_decision_extremo": 0,
            "proveedor_sobrecostos_previos": 0,
            "proveedor_retrasos_previos": 0,
            "ausencia_proceso": 0,
        }
        scores = compute_iric_scores(components)

        assert scores["iric_score"] == 0.0
        assert scores["iric_competencia"] == 0.0
        assert scores["iric_transparencia"] == 0.0
        assert scores["iric_anomalias"] == 0.0

    def test_iric_scores_returns_four_keys(self):
        """compute_iric_scores returns exactly 4 keys."""
        from sip_engine.iric.calculator import compute_iric_scores

        components = {k: 0 for k in [
            "unico_proponente", "proveedor_multiproposito", "historial_proveedor_alto",
            "contratacion_directa", "regimen_especial", "periodo_publicidad_extremo",
            "datos_faltantes", "periodo_decision_extremo",
            "proveedor_sobrecostos_previos", "proveedor_retrasos_previos", "ausencia_proceso",
        ]}
        scores = compute_iric_scores(components)

        assert set(scores.keys()) == {
            "iric_score", "iric_competencia", "iric_transparencia", "iric_anomalias"
        }

    def test_iric_components_returns_eleven_keys(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """compute_iric_components returns exactly 11 component keys."""
        from sip_engine.iric.calculator import compute_iric_components

        components = compute_iric_components(base_row, procesos_normal, None, minimal_thresholds, 1)
        expected_keys = {
            "unico_proponente", "proveedor_multiproposito", "historial_proveedor_alto",
            "contratacion_directa", "regimen_especial", "periodo_publicidad_extremo",
            "datos_faltantes", "periodo_decision_extremo",
            "proveedor_sobrecostos_previos", "proveedor_retrasos_previos", "ausencia_proceso",
        }
        assert set(components.keys()) == expected_keys


# ============================================================
# Plan 06-03: pipeline.py tests (compute_iric + build_iric)
# ============================================================


class TestComputeIricOnline:
    """Tests for compute_iric() online function."""

    def test_compute_iric_online_returns_all_keys(self, base_row, minimal_thresholds, procesos_normal):
        """compute_iric returns all 11 components + 4 scores + 3 bid stat keys."""
        from sip_engine.iric.pipeline import compute_iric

        result = compute_iric(
            contract_row=base_row,
            procesos_data=procesos_normal,
            provider_history=None,
            thresholds=minimal_thresholds,
            num_actividades=1,
        )

        # 11 components
        expected_components = {
            "unico_proponente", "proveedor_multiproposito", "historial_proveedor_alto",
            "contratacion_directa", "regimen_especial", "periodo_publicidad_extremo",
            "datos_faltantes", "periodo_decision_extremo",
            "proveedor_sobrecostos_previos", "proveedor_retrasos_previos", "ausencia_proceso",
        }
        # 4 scores
        expected_scores = {"iric_score", "iric_competencia", "iric_transparencia", "iric_anomalias"}
        # 3 bid stats
        expected_bid_stats = {"curtosis_licitacion", "diferencia_relativa_norm", "n_bids"}

        assert expected_components.issubset(result.keys())
        assert expected_scores.issubset(result.keys())
        assert expected_bid_stats.issubset(result.keys())
        # Total: 11 + 4 + 3 = 18 keys
        assert len(result) == 18

    def test_compute_iric_online_scores_in_range(self, base_row, minimal_thresholds, procesos_normal):
        """All 4 aggregate scores are in [0, 1]."""
        from sip_engine.iric.pipeline import compute_iric

        result = compute_iric(
            contract_row=base_row,
            procesos_data=procesos_normal,
            provider_history=None,
            thresholds=minimal_thresholds,
        )

        for score_key in ("iric_score", "iric_competencia", "iric_transparencia", "iric_anomalias"):
            assert 0.0 <= result[score_key] <= 1.0, f"{score_key} out of range: {result[score_key]}"

    def test_compute_iric_no_bid_values_returns_nan(self, base_row, minimal_thresholds, procesos_normal):
        """bid_values=None -> curtosis_licitacion and diferencia_relativa_norm are NaN."""
        import math
        from sip_engine.iric.pipeline import compute_iric

        result = compute_iric(
            contract_row=base_row,
            procesos_data=procesos_normal,
            provider_history=None,
            thresholds=minimal_thresholds,
            bid_values=None,
        )

        assert math.isnan(result["curtosis_licitacion"])
        assert math.isnan(result["diferencia_relativa_norm"])
        assert result["n_bids"] == 0

    def test_compute_iric_with_bid_values(self, base_row, minimal_thresholds, procesos_normal):
        """bid_values provided -> kurtosis and DRN computed (not NaN for n >= 4/3)."""
        import math
        from sip_engine.iric.pipeline import compute_iric

        # 4 bids: kurtosis defined (n>=4), DRN defined (n>=3)
        result = compute_iric(
            contract_row=base_row,
            procesos_data=procesos_normal,
            provider_history=None,
            thresholds=minimal_thresholds,
            bid_values=[100.0, 200.0, 300.0, 400.0],
        )

        assert not math.isnan(result["curtosis_licitacion"]), "kurtosis should be defined for 4 bids"
        assert not math.isnan(result["diferencia_relativa_norm"]), "DRN should be defined for 4 bids"
        assert result["n_bids"] == 4

    def test_compute_iric_parity_with_components_scores(
        self, base_row, minimal_thresholds, procesos_normal
    ):
        """compute_iric result matches calling compute_iric_components + compute_iric_scores directly."""
        from sip_engine.iric.calculator import compute_iric_components, compute_iric_scores
        from sip_engine.iric.pipeline import compute_iric

        # Direct call
        components = compute_iric_components(
            base_row, procesos_normal, None, minimal_thresholds, 2
        )
        scores = compute_iric_scores(components)

        # Via pipeline
        result = compute_iric(
            contract_row=base_row,
            procesos_data=procesos_normal,
            provider_history=None,
            thresholds=minimal_thresholds,
            num_actividades=2,
        )

        # All component and score values should match
        for key in components:
            assert result[key] == components[key], f"Component mismatch for {key}"
        for key in scores:
            assert abs(result[key] - scores[key]) < 1e-9, f"Score mismatch for {key}"


class TestBuildIricCreatesParquet:
    """Tests for build_iric() batch orchestrator."""

    def test_build_iric_creates_parquet(self, tmp_path, monkeypatch):
        """build_iric() with mocked loaders produces parquet with expected columns."""
        import math
        import pandas as pd
        from unittest.mock import patch
        from sip_engine.config.settings import Settings
        from sip_engine.iric.pipeline import build_iric

        # Set up temp artifact dir
        monkeypatch.setenv("SIP_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

        # Clear settings cache so it picks up new env
        import sip_engine.config
        sip_engine.config.get_settings.cache_clear()

        # Build minimal features parquet for threshold calibration
        features_dir = tmp_path / "artifacts" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        iric_dir = tmp_path / "artifacts" / "iric"
        iric_dir.mkdir(parents=True, exist_ok=True)

        # Create a minimal features.parquet for threshold calibration
        features_df = pd.DataFrame({
            "tipo_contrato": ["Prestacion de servicios"] * 50,
            "num_contratos_previos_nacional": list(range(50)),
            "dias_publicidad": [i % 15 for i in range(50)],
            "dias_decision": [i % 60 for i in range(50)],
            "valor_contrato": [(i + 1) * 1_000_000 for i in range(50)],
        })
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pandas(features_df)
        pq.write_table(table, features_dir / "features.parquet")

        # Mock contratos data
        contrato_row = {
            "ID Contrato": "CONT-001",
            "Fecha de Firma": "2023-01-15",
            "Proceso de Compra": "PROC-001",
            "TipoDocProveedor": "NIT",
            "Documento Proveedor": "900123456",
            "Modalidad de Contratacion": "Licitacion publica",
            "Tipo de Contrato": "Prestacion de servicios",
            "Valor del Contrato": 10_000_000.0,
            "Justificacion Modalidad de Contratacion": "Por necesidad",
            "Departamento": "BOGOTA",
            "Codigo de Categoria Principal": "V1.8010",
        }
        contratos_df = pd.DataFrame([contrato_row])

        def mock_load_contratos():
            yield contratos_df

        def mock_load_procesos():
            yield pd.DataFrame([])

        def mock_load_ofertas():
            yield pd.DataFrame([])

        with patch("sip_engine.iric.pipeline._build_iric_procesos_lookup", return_value={}), \
             patch("sip_engine.iric.pipeline._build_iric_num_actividades_lookup", return_value={}), \
             patch("sip_engine.iric.pipeline.build_bid_stats_lookup", return_value={}), \
             patch("sip_engine.features.provider_history.build_provider_history_index"), \
             patch("sip_engine.features.provider_history.lookup_provider_history", return_value=None), \
             patch("sip_engine.data.loaders.load_contratos", mock_load_contratos):

            path = build_iric(force=True)

        assert path.exists(), f"iric_scores.parquet not created at {path}"

        df_result = pd.read_parquet(path)

        # Check required columns present
        required_cols = {
            "unico_proponente", "proveedor_multiproposito", "historial_proveedor_alto",
            "contratacion_directa", "regimen_especial", "periodo_publicidad_extremo",
            "datos_faltantes", "periodo_decision_extremo",
            "proveedor_sobrecostos_previos", "proveedor_retrasos_previos", "ausencia_proceso",
            "iric_score", "iric_competencia", "iric_transparencia", "iric_anomalias",
            "curtosis_licitacion", "diferencia_relativa_norm", "n_bids",
        }
        assert required_cols.issubset(set(df_result.columns)), (
            f"Missing columns: {required_cols - set(df_result.columns)}"
        )
        # 1 row processed
        assert len(df_result) == 1

        # Clean up settings cache
        sip_engine.config.get_settings.cache_clear()

    def test_build_iric_returns_early_if_exists(self, tmp_path, monkeypatch):
        """build_iric(force=False) returns cached path if parquet already exists."""
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq
        from sip_engine.config.settings import Settings
        from sip_engine.iric.pipeline import build_iric
        import sip_engine.config

        monkeypatch.setenv("SIP_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
        sip_engine.config.get_settings.cache_clear()

        # Create the parquet file ahead of time
        iric_dir = tmp_path / "artifacts" / "iric"
        iric_dir.mkdir(parents=True, exist_ok=True)
        existing = iric_dir / "iric_scores.parquet"
        df_stub = pd.DataFrame({"id_contrato": ["X"], "iric_score": [0.5]})
        pq.write_table(pa.Table.from_pandas(df_stub), existing)

        # Should return early without touching any loaders
        path = build_iric(force=False)
        assert path == existing

        sip_engine.config.get_settings.cache_clear()
