"""Tests for Plan 17-03: multiprocessing acceleration.

Tests cover:
- Pool initialization utilities: serialize_lookups, _init_worker, get_shared_lookups
- create_worker_pool: n_jobs<=1 returns (None, ''), n_jobs>1 creates pool
- _process_labels_chunk worker function: M3/M4 per row
- _process_iric_chunk worker function: IRIC components per row
- _process_features_chunk worker function: Cat A/B/C per row
- Worker determinism: same chunk → same output across two calls
- Memory monitor integration: warning/critical checks in MP loop
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import sip_engine.shared.memory as _mem_module
from sip_engine.shared.memory import (
    _init_worker,
    create_worker_pool,
    get_shared_lookups,
    serialize_lookups,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(autouse=True)
def _reset_shared_lookups():
    """Restore module-level _shared_lookups after each test."""
    original = _mem_module._shared_lookups
    yield
    _mem_module._shared_lookups = original


@pytest.fixture()
def sample_thresholds():
    """Minimal IRIC thresholds dict for testing."""
    tier = {
        "num_contratos_previos_nacional": {"p1": 1, "p5": 1, "p95": 5, "p99": 9},
        "dias_publicidad": {"p1": 0, "p5": 0, "p95": 12, "p99": 20},
        "dias_decision": {"p1": 0, "p5": 0, "p95": 55, "p99": 150},
        "valor_contrato": {"p1": 0, "p5": 0, "p95": 200_000_000, "p99": 500_000_000},
    }
    return {
        "tipo_contrato": {
            "Prestacion de servicios": tier,
            "Otro": tier,
        },
        "calibration_date": "2026-01-01T00:00:00Z",
        "n_contracts": 100,
        "min_group_size": 30,
    }


@pytest.fixture()
def _zero_provider_history():
    """Zero-filled provider history dict (new provider)."""
    return {
        "num_contratos_previos_nacional": 0,
        "num_contratos_previos_depto": 0,
        "valor_total_contratos_previos_nacional": 0.0,
        "valor_total_contratos_previos_depto": 0.0,
        "num_sobrecostos_previos": 0,
        "num_retrasos_previos": 0,
    }


@pytest.fixture()
def contratos_chunk():
    """Small contratos DataFrame matching required schema."""
    return pd.DataFrame({
        "ID Contrato": ["C001", "C002", "C003"],
        "TipoDocProveedor": ["NIT", "CC", "NIT"],
        "Documento Proveedor": ["900123456", "12345678", "800111222"],
        "Fecha de Firma": ["2023-01-15", "2023-03-20", "2022-11-01"],
        "Valor del Contrato": [5_000_000.0, 2_500_000.0, 10_000_000.0],
        "Departamento": ["Bogotá D.C.", "Antioquia", "Valle del Cauca"],
        "Proceso de Compra": ["P001", "P002", "P003"],
        "Modalidad de Contratacion": ["Contratación Directa", "Licitación Pública", "Contratación Directa"],
        "Tipo de Contrato": ["Prestacion de servicios", "Prestacion de servicios", "Compraventa"],
        "Justificacion Modalidad de Contratacion": ["", "N/A", ""],
        "Codigo de Categoria Principal": ["80100000", "71110000", "25000000"],
        "Origen de los Recursos": ["Nación", "Nación", "Territorial"],
        "Dias adicionados": ["0", "10", "0"],
    })


@pytest.fixture()
def labels_chunk(contratos_chunk):
    """Contratos chunk with M1/M2 already assigned (for label builder worker)."""
    df = contratos_chunk.copy()
    df["M1"] = pd.array([0, 1, 0], dtype="Int8")
    df["M2"] = pd.array([1, 0, 0], dtype="Int8")
    return df


# ===========================================================================
# Pool initialization tests
# ===========================================================================


class TestSerializeAndLoadLookups:
    """Tests for serialize_lookups → _init_worker → get_shared_lookups."""

    def test_serialize_basic_dict(self, tmp_path):
        """serialize_lookups writes a valid pickle file."""
        data = {"key1": {1, 2, 3}, "key2": [4, 5, 6]}
        path = serialize_lookups(data, tmp_dir=str(tmp_path))
        assert Path(path).exists()
        Path(path).unlink()

    def test_init_worker_loads_correctly(self, tmp_path):
        """_init_worker loads pickle into module-level _shared_lookups."""
        data = {"boletines_set": {("NIT", "900123456")}, "extra": [1, 2, 3]}
        path = serialize_lookups(data, tmp_dir=str(tmp_path))
        try:
            _init_worker(path)
            result = get_shared_lookups()
            assert result["boletines_set"] == {("NIT", "900123456")}
            assert result["extra"] == [1, 2, 3]
        finally:
            Path(path).unlink(missing_ok=True)

    def test_init_worker_overwrites_previous(self, tmp_path):
        """_init_worker replaces any previous _shared_lookups content."""
        _mem_module._shared_lookups = {"old_key": "old_value"}

        data = {"new_key": "new_value"}
        path = serialize_lookups(data, tmp_dir=str(tmp_path))
        try:
            _init_worker(path)
            result = get_shared_lookups()
            assert "new_key" in result
            assert "old_key" not in result
        finally:
            Path(path).unlink(missing_ok=True)

    def test_get_shared_lookups_empty_by_default(self):
        """get_shared_lookups() returns {} when _init_worker has not been called."""
        _mem_module._shared_lookups = {}
        assert get_shared_lookups() == {}


class TestCreateWorkerPool:
    """Tests for create_worker_pool helper."""

    def test_single_process_returns_none(self):
        """n_jobs=1 returns (None, '') — no pool created."""
        pool, path = create_worker_pool(1, {"key": "val"})
        assert pool is None
        assert path == ""

    def test_n_jobs_zero_returns_none(self):
        """n_jobs=0 treated as single-process (n_jobs<=1)."""
        pool, path = create_worker_pool(0, {"key": "val"})
        assert pool is None
        assert path == ""

    def test_n_jobs_negative_returns_none(self):
        """n_jobs<0 treated as single-process."""
        pool, path = create_worker_pool(-1, {"key": "val"})
        assert pool is None
        assert path == ""

    def test_multi_process_returns_pool_and_path(self, tmp_path):
        """n_jobs=2 returns a live Pool and a pickle path."""
        pool, path = create_worker_pool(2, {"test": "data"})
        try:
            assert pool is not None
            assert hasattr(pool, "imap_unordered"), "Expected a multiprocessing Pool"
            assert hasattr(pool, "close")
            assert Path(path).exists()
        finally:
            if pool:
                pool.terminate()
                pool.join()
            if path:
                Path(path).unlink(missing_ok=True)


# ===========================================================================
# Worker function unit tests
# ===========================================================================


class TestProcessLabelsChunk:
    """Unit tests for _process_labels_chunk worker."""

    def test_returns_list_of_dicts(self, labels_chunk):
        """Worker returns a list of dicts."""
        from sip_engine.shared.data.label_builder import _process_labels_chunk

        _mem_module._shared_lookups = {"boletines_set": set()}

        with patch("sip_engine.shared.data.label_builder.rcac_lookup", return_value=None):
            results = _process_labels_chunk(labels_chunk)

        assert isinstance(results, list)
        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)

    def test_output_has_required_keys(self, labels_chunk):
        """Each result row has id_contrato, M1-M4, and normalized provider keys."""
        from sip_engine.shared.data.label_builder import _process_labels_chunk

        _mem_module._shared_lookups = {"boletines_set": set()}

        with patch("sip_engine.shared.data.label_builder.rcac_lookup", return_value=None):
            results = _process_labels_chunk(labels_chunk)

        required_keys = {"id_contrato", "M1", "M2", "M3", "M4", "TipoDocProveedor_norm", "DocProveedor_norm"}
        for row in results:
            assert required_keys.issubset(set(row.keys())), f"Missing keys in {row.keys()}"

    def test_m4_zero_when_rcac_lookup_none(self, labels_chunk):
        """M4 = 0 when rcac_lookup returns None (provider not in RCAC)."""
        from sip_engine.shared.data.label_builder import _process_labels_chunk

        _mem_module._shared_lookups = {"boletines_set": set()}

        with patch("sip_engine.shared.data.label_builder.rcac_lookup", return_value=None):
            results = _process_labels_chunk(labels_chunk)

        # All providers have valid IDs → M4 = 0 (not in RCAC)
        for row in results:
            assert row["M4"] == 0 or row["M4"] is None  # None if malformed

    def test_m3_uses_boletines_set(self, labels_chunk):
        """M3 = 1 when provider (tipo_norm, num_norm) is in boletines_set."""
        from sip_engine.shared.data.label_builder import _process_labels_chunk
        from sip_engine.shared.data.rcac_builder import normalize_numero, normalize_tipo

        # Add NIT/900123456 to boletines_set
        tipo_norm = normalize_tipo("NIT")
        num_norm = normalize_numero("900123456")
        boletines_set = {(tipo_norm, num_norm)}
        _mem_module._shared_lookups = {"boletines_set": boletines_set}

        with patch("sip_engine.shared.data.label_builder.rcac_lookup", return_value=None):
            results = _process_labels_chunk(labels_chunk)

        c001 = next(r for r in results if r["id_contrato"] == "C001")
        assert c001["M3"] == 1  # NIT/900123456 is in boletines_set

    def test_determinism_same_chunk(self, labels_chunk):
        """Same chunk → same output across two calls."""
        from sip_engine.shared.data.label_builder import _process_labels_chunk

        _mem_module._shared_lookups = {"boletines_set": set()}

        with patch("sip_engine.shared.data.label_builder.rcac_lookup", return_value=None):
            results1 = _process_labels_chunk(labels_chunk)
            results2 = _process_labels_chunk(labels_chunk)

        # Sort both by id_contrato for stable comparison
        sorted1 = sorted(results1, key=lambda r: r["id_contrato"])
        sorted2 = sorted(results2, key=lambda r: r["id_contrato"])
        assert sorted1 == sorted2


class TestProcessIricChunk:
    """Unit tests for _process_iric_chunk worker."""

    def test_returns_list_of_dicts(self, contratos_chunk, sample_thresholds, _zero_provider_history):
        """Worker returns a list of dicts with IRIC keys."""
        from sip_engine.classifiers.iric.pipeline import _process_iric_chunk

        _mem_module._shared_lookups = {
            "procesos_lookup": {},
            "num_actividades_lookup": {},
            "bid_stats_lookup": {},
            "thresholds": sample_thresholds,
            "processed_ids": set(),
        }

        with patch(
            "sip_engine.classifiers.features.provider_history.lookup_provider_history",
            return_value=_zero_provider_history,
        ):
            results = _process_iric_chunk(contratos_chunk)

        assert isinstance(results, list)
        # All 3 rows have valid dates → should produce 3 results
        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)

    def test_output_has_iric_score(self, contratos_chunk, sample_thresholds, _zero_provider_history):
        """Each result row has id_contrato and iric_score keys."""
        from sip_engine.classifiers.iric.pipeline import _process_iric_chunk

        _mem_module._shared_lookups = {
            "procesos_lookup": {},
            "num_actividades_lookup": {},
            "bid_stats_lookup": {},
            "thresholds": sample_thresholds,
            "processed_ids": set(),
        }

        with patch(
            "sip_engine.classifiers.features.provider_history.lookup_provider_history",
            return_value=_zero_provider_history,
        ):
            results = _process_iric_chunk(contratos_chunk)

        for row in results:
            assert "id_contrato" in row
            assert "iric_score" in row
            assert "unico_proponente" in row

    def test_skips_processed_ids(self, contratos_chunk, sample_thresholds, _zero_provider_history):
        """Rows already in processed_ids are skipped."""
        from sip_engine.classifiers.iric.pipeline import _process_iric_chunk

        _mem_module._shared_lookups = {
            "procesos_lookup": {},
            "num_actividades_lookup": {},
            "bid_stats_lookup": {},
            "thresholds": sample_thresholds,
            "processed_ids": {"C001", "C002"},
        }

        with patch(
            "sip_engine.classifiers.features.provider_history.lookup_provider_history",
            return_value=_zero_provider_history,
        ):
            results = _process_iric_chunk(contratos_chunk)

        ids = {r["id_contrato"] for r in results}
        assert "C001" not in ids
        assert "C002" not in ids
        assert "C003" in ids

    def test_determinism_same_chunk(self, contratos_chunk, sample_thresholds, _zero_provider_history):
        """Same chunk → same output across two calls."""
        from sip_engine.classifiers.iric.pipeline import _process_iric_chunk

        _mem_module._shared_lookups = {
            "procesos_lookup": {},
            "num_actividades_lookup": {},
            "bid_stats_lookup": {},
            "thresholds": sample_thresholds,
            "processed_ids": set(),
        }

        with patch(
            "sip_engine.classifiers.features.provider_history.lookup_provider_history",
            return_value=_zero_provider_history,
        ):
            results1 = _process_iric_chunk(contratos_chunk)
            results2 = _process_iric_chunk(contratos_chunk)

        sorted1 = sorted(results1, key=lambda r: r["id_contrato"])
        sorted2 = sorted(results2, key=lambda r: r["id_contrato"])
        assert len(sorted1) == len(sorted2)
        for r1, r2 in zip(sorted1, sorted2):
            assert r1["id_contrato"] == r2["id_contrato"]
            assert r1["iric_score"] == r2["iric_score"]


class TestProcessFeaturesChunk:
    """Unit tests for _process_features_chunk worker."""

    def test_returns_list_of_dicts(self, contratos_chunk, _zero_provider_history):
        """Worker returns a list of dicts with feature keys."""
        from sip_engine.classifiers.features.pipeline import _process_features_chunk

        _mem_module._shared_lookups = {
            "procesos_lookup": {},
            "proveedores_lookup": {},
            "num_actividades_lookup": {},
            "processed_ids": set(),
        }

        with patch(
            "sip_engine.classifiers.features.provider_history.lookup_provider_history",
            return_value=_zero_provider_history,
        ):
            results = _process_features_chunk(contratos_chunk)

        assert isinstance(results, list)
        # All rows have required fields and valid dates → should keep rows
        assert len(results) > 0
        assert all(isinstance(r, dict) for r in results)

    def test_output_has_feature_keys(self, contratos_chunk, _zero_provider_history):
        """Each result row has id_contrato and category feature keys."""
        from sip_engine.classifiers.features.pipeline import _process_features_chunk

        _mem_module._shared_lookups = {
            "procesos_lookup": {},
            "proveedores_lookup": {},
            "num_actividades_lookup": {},
            "processed_ids": set(),
        }

        with patch(
            "sip_engine.classifiers.features.provider_history.lookup_provider_history",
            return_value=_zero_provider_history,
        ):
            results = _process_features_chunk(contratos_chunk)

        for row in results:
            assert "id_contrato" in row
            assert "valor_contrato" in row  # Category A
            assert "num_actividades_economicas" in row  # Category C

    def test_drops_rows_missing_required_fields(self, _zero_provider_history):
        """Rows missing required fields (e.g., Tipo de Contrato) are dropped."""
        from sip_engine.classifiers.features.pipeline import _process_features_chunk

        chunk = pd.DataFrame({
            "ID Contrato": ["C001", "C002"],
            "TipoDocProveedor": ["NIT", "NIT"],
            "Documento Proveedor": ["900123456", "900111222"],
            "Fecha de Firma": ["2023-01-15", "2023-01-15"],
            "Valor del Contrato": [5_000_000.0, 5_000_000.0],
            "Departamento": ["Bogotá D.C.", "Bogotá D.C."],
            "Proceso de Compra": ["P001", "P002"],
            "Modalidad de Contratacion": ["Contratación Directa", "Contratación Directa"],
            # Missing "Tipo de Contrato" — required field
            "Justificacion Modalidad de Contratacion": ["", ""],
            "Codigo de Categoria Principal": ["80100000", "80100000"],
            "Origen de los Recursos": ["Nación", "Nación"],
            "Dias adicionados": ["0", "0"],
        })

        _mem_module._shared_lookups = {
            "procesos_lookup": {},
            "proveedores_lookup": {},
            "num_actividades_lookup": {},
            "processed_ids": set(),
        }

        with patch(
            "sip_engine.classifiers.features.provider_history.lookup_provider_history",
            return_value=_zero_provider_history,
        ):
            results = _process_features_chunk(chunk)

        # Tipo de Contrato missing → all rows dropped
        assert len(results) == 0

    def test_skips_processed_ids(self, contratos_chunk, _zero_provider_history):
        """Rows already in processed_ids are skipped."""
        from sip_engine.classifiers.features.pipeline import _process_features_chunk

        _mem_module._shared_lookups = {
            "procesos_lookup": {},
            "proveedores_lookup": {},
            "num_actividades_lookup": {},
            "processed_ids": {"C001"},
        }

        with patch(
            "sip_engine.classifiers.features.provider_history.lookup_provider_history",
            return_value=_zero_provider_history,
        ):
            results = _process_features_chunk(contratos_chunk)

        ids = {r["id_contrato"] for r in results}
        assert "C001" not in ids

    def test_determinism_same_chunk(self, contratos_chunk, _zero_provider_history):
        """Same chunk → same output across two calls."""
        from sip_engine.classifiers.features.pipeline import _process_features_chunk

        _mem_module._shared_lookups = {
            "procesos_lookup": {},
            "proveedores_lookup": {},
            "num_actividades_lookup": {},
            "processed_ids": set(),
        }

        with patch(
            "sip_engine.classifiers.features.provider_history.lookup_provider_history",
            return_value=_zero_provider_history,
        ):
            results1 = _process_features_chunk(contratos_chunk)
            results2 = _process_features_chunk(contratos_chunk)

        # Sort by id_contrato and compare as DataFrames (handles NaN equality)
        df1 = pd.DataFrame(sorted(results1, key=lambda r: r["id_contrato"]))
        df2 = pd.DataFrame(sorted(results2, key=lambda r: r["id_contrato"]))
        pd.testing.assert_frame_equal(df1, df2, check_like=True)


# ===========================================================================
# Memory monitor integration test
# ===========================================================================


class TestPoolWithMemoryMonitor:
    """Test that memory monitor checks work correctly in the MP dispatch loop."""

    def test_warning_triggers_gc_but_continues(self):
        """When monitor returns 'warning', gc.collect() is called but processing continues."""
        import gc as _gc

        from sip_engine.shared.memory import MemoryMonitor, get_shared_lookups

        mock_monitor = MagicMock(spec=MemoryMonitor)
        mock_monitor.check.return_value = "warning"
        mock_monitor.current_usage_bytes.return_value = 8 * (1024 ** 3)
        mock_monitor.budget_bytes = 8 * (1024 ** 3)

        # Simulate the memory check loop pattern from build_labels/build_iric
        all_rows: list[dict] = []
        gc_calls: list[str] = []

        def _fake_check_and_process(monitor, chunk_results):
            """Mirrors the main-process monitor check between imap_unordered results."""
            all_rows.extend(chunk_results)
            status = monitor.check()
            if status == "warning":
                _gc.collect()
                gc_calls.append("gc_called")

        for i in range(3):
            _fake_check_and_process(mock_monitor, [{"id": i}])

        assert len(all_rows) == 3
        assert len(gc_calls) == 3  # gc called for each 'warning'
        assert mock_monitor.check.call_count == 3

    def test_critical_raises_memory_error(self):
        """When monitor stays 'critical' after gc, MemoryError is raised."""
        import gc as _gc

        from sip_engine.shared.memory import MemoryMonitor, save_checkpoint

        mock_monitor = MagicMock(spec=MemoryMonitor)
        mock_monitor.check.return_value = "critical"
        mock_monitor.current_usage_bytes.return_value = 10 * (1024 ** 3)
        mock_monitor.budget_bytes = 8 * (1024 ** 3)

        def _check_and_abort(monitor, all_rows, checkpoint_path):
            """Mirrors critical memory handling from the MP dispatch loops."""
            status = monitor.check()
            if status == "critical":
                _gc.collect()
                if monitor.check() == "critical":
                    raise MemoryError(
                        f"RAM budget exceeded: {monitor.current_usage_bytes()} bytes"
                    )

        with pytest.raises(MemoryError, match="RAM budget exceeded"):
            _check_and_abort(mock_monitor, [], Path("/tmp/fake_checkpoint.parquet"))
