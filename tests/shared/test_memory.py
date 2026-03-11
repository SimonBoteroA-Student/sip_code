"""Unit tests for shared/memory.py.

Tests cover:
- MemoryMonitor.check() thresholds: ok (<90%), warning (90-100%), critical (>=100%)
- MemoryMonitor.usage_ratio() calculation
- adaptive_chunk_size() behaviour for ok / warning / critical states
- adaptive_chunk_size() minimum floor enforcement
- Checkpoint round-trip: save → load → verify DataFrame and processed_ids set
- remove_checkpoint() deletes the file
- load_checkpoint() on non-existent path returns empty DataFrame + empty set
- cleanup() calls gc.collect()
"""

from __future__ import annotations

import gc
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from sip_engine.shared.memory import (
    MemoryMonitor,
    adaptive_chunk_size,
    cleanup,
    load_checkpoint,
    remove_checkpoint,
    save_checkpoint,
)


# ============================================================
# MemoryMonitor tests
# ============================================================


def _make_monitor(max_ram_gb: int = 8) -> MemoryMonitor:
    return MemoryMonitor(max_ram_gb=max_ram_gb)


def _mock_rss(monitor: MemoryMonitor, ratio: float) -> int:
    """Return RSS bytes that produce *ratio* of the monitor's budget."""
    return int(monitor.budget_bytes * ratio)


class TestMemoryMonitorCheck:
    def test_check_ok(self):
        """RSS below 90% of budget → 'ok'."""
        monitor = _make_monitor(max_ram_gb=8)
        mock_rss = _mock_rss(monitor, 0.85)
        with patch("psutil.Process") as mock_proc:
            mock_proc.return_value.memory_info.return_value.rss = mock_rss
            assert monitor.check() == "ok"

    def test_check_warning(self):
        """RSS at 92% of budget → 'warning'."""
        monitor = _make_monitor(max_ram_gb=8)
        mock_rss = _mock_rss(monitor, 0.92)
        with patch("psutil.Process") as mock_proc:
            mock_proc.return_value.memory_info.return_value.rss = mock_rss
            assert monitor.check() == "warning"

    def test_check_critical(self):
        """RSS at 105% of budget → 'critical'."""
        monitor = _make_monitor(max_ram_gb=8)
        mock_rss = _mock_rss(monitor, 1.05)
        with patch("psutil.Process") as mock_proc:
            mock_proc.return_value.memory_info.return_value.rss = mock_rss
            assert monitor.check() == "critical"

    def test_check_at_90_percent_boundary(self):
        """RSS exactly at 90% → 'warning' (boundary is inclusive).

        Note: we add 1 byte to ensure integer truncation from int() doesn't
        push the value just below the 90% threshold.
        """
        monitor = _make_monitor(max_ram_gb=8)
        mock_rss = _mock_rss(monitor, 0.90) + 1  # +1 byte ensures >= 90%
        with patch("psutil.Process") as mock_proc:
            mock_proc.return_value.memory_info.return_value.rss = mock_rss
            assert monitor.check() == "warning"

    def test_check_at_100_percent_boundary(self):
        """RSS exactly at 100% → 'critical' (boundary is inclusive)."""
        monitor = _make_monitor(max_ram_gb=8)
        mock_rss = _mock_rss(monitor, 1.00)
        with patch("psutil.Process") as mock_proc:
            mock_proc.return_value.memory_info.return_value.rss = mock_rss
            assert monitor.check() == "critical"


class TestMemoryMonitorUsageRatio:
    def test_usage_ratio(self):
        """usage_ratio() returns RSS / budget_bytes."""
        monitor = _make_monitor(max_ram_gb=4)
        expected_ratio = 0.5
        mock_rss = int(monitor.budget_bytes * expected_ratio)
        with patch("psutil.Process") as mock_proc:
            mock_proc.return_value.memory_info.return_value.rss = mock_rss
            ratio = monitor.usage_ratio()
        assert abs(ratio - expected_ratio) < 1e-9

    def test_budget_bytes_calculation(self):
        """budget_bytes is exactly max_ram_gb * 1024^3."""
        monitor = _make_monitor(max_ram_gb=16)
        assert monitor.budget_bytes == 16 * (1024 ** 3)


# ============================================================
# adaptive_chunk_size tests
# ============================================================


def _monitor_with_status(status: str) -> MemoryMonitor:
    """Return a MemoryMonitor whose check() is stubbed to *status*."""
    monitor = _make_monitor()
    monitor.check = MagicMock(return_value=status)
    return monitor


class TestAdaptiveChunkSize:
    def test_adaptive_ok(self):
        """Status 'ok' → chunk size unchanged."""
        monitor = _monitor_with_status("ok")
        assert adaptive_chunk_size(monitor, 50_000) == 50_000

    def test_adaptive_warning(self):
        """Status 'warning' → chunk size halved."""
        monitor = _monitor_with_status("warning")
        assert adaptive_chunk_size(monitor, 50_000) == 25_000

    def test_adaptive_critical(self):
        """Status 'critical' → chunk size at minimum floor."""
        monitor = _monitor_with_status("critical")
        assert adaptive_chunk_size(monitor, 50_000, min_chunk_size=1000) == 1000

    def test_adaptive_min_floor_at_warning(self):
        """Even at 'warning', chunk_size cannot go below min_chunk_size."""
        monitor = _monitor_with_status("warning")
        # base=1500, halved=750 → clamped to min 1000
        assert adaptive_chunk_size(monitor, 1500, min_chunk_size=1000) == 1000

    def test_adaptive_custom_min_floor(self):
        """Custom min_chunk_size is respected."""
        monitor = _monitor_with_status("critical")
        assert adaptive_chunk_size(monitor, 50_000, min_chunk_size=500) == 500

    def test_adaptive_default_min_floor(self):
        """Default min_chunk_size is 1000."""
        monitor = _monitor_with_status("critical")
        assert adaptive_chunk_size(monitor, 50_000) == 1000


# ============================================================
# Checkpoint tests
# ============================================================


class TestCheckpointRoundtrip:
    def test_checkpoint_roundtrip(self, tmp_path: Path):
        """save_checkpoint → load_checkpoint returns matching DataFrame and IDs."""
        rows = [
            {"id_contrato": "C-001", "value": 100},
            {"id_contrato": "C-002", "value": 200},
            {"id_contrato": "C-003", "value": 300},
        ]
        checkpoint_path = tmp_path / "test.parquet"

        save_checkpoint(rows, checkpoint_path)

        assert checkpoint_path.exists()

        df, processed_ids = load_checkpoint(checkpoint_path)

        assert len(df) == 3
        assert set(df["id_contrato"].tolist()) == {"C-001", "C-002", "C-003"}
        assert processed_ids == {"C-001", "C-002", "C-003"}
        assert list(df["value"]) == [100, 200, 300]

    def test_checkpoint_roundtrip_no_id_contrato(self, tmp_path: Path):
        """load_checkpoint works even if 'id_contrato' column is absent (empty set)."""
        rows = [{"foo": 1}, {"foo": 2}]
        checkpoint_path = tmp_path / "no_id.parquet"

        save_checkpoint(rows, checkpoint_path)
        df, processed_ids = load_checkpoint(checkpoint_path)

        assert len(df) == 2
        assert processed_ids == set()

    def test_checkpoint_empty_rows(self, tmp_path: Path):
        """save_checkpoint with empty list creates file, load returns empty DataFrame."""
        checkpoint_path = tmp_path / "empty.parquet"
        save_checkpoint([], checkpoint_path)
        df, processed_ids = load_checkpoint(checkpoint_path)
        assert len(df) == 0
        assert processed_ids == set()


class TestRemoveCheckpoint:
    def test_remove_checkpoint(self, tmp_path: Path):
        """remove_checkpoint deletes the file."""
        checkpoint_path = tmp_path / "to_remove.parquet"
        checkpoint_path.write_bytes(b"dummy")
        assert checkpoint_path.exists()

        remove_checkpoint(checkpoint_path)

        assert not checkpoint_path.exists()

    def test_remove_checkpoint_nonexistent(self, tmp_path: Path):
        """remove_checkpoint on a missing file does not raise."""
        checkpoint_path = tmp_path / "nonexistent.parquet"
        remove_checkpoint(checkpoint_path)  # should not raise


class TestLoadNonexistentCheckpoint:
    def test_load_nonexistent_checkpoint(self, tmp_path: Path):
        """load_checkpoint on a missing file returns empty DataFrame + empty set."""
        checkpoint_path = tmp_path / "does_not_exist.parquet"
        df, processed_ids = load_checkpoint(checkpoint_path)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert isinstance(processed_ids, set)
        assert len(processed_ids) == 0


# ============================================================
# cleanup tests
# ============================================================


class TestCleanup:
    def test_cleanup_calls_gc(self):
        """cleanup() calls gc.collect() exactly once."""
        with patch.object(gc, "collect") as mock_gc:
            cleanup()
            mock_gc.assert_called_once()

    def test_cleanup_with_objects_calls_gc(self):
        """cleanup() with objects also calls gc.collect() once."""
        df = pd.DataFrame({"a": [1, 2, 3]})
        with patch.object(gc, "collect") as mock_gc:
            cleanup(df)
            mock_gc.assert_called_once()

    def test_cleanup_multiple_objects(self):
        """cleanup() with multiple objects calls gc.collect() once."""
        obj1 = [1, 2, 3]
        obj2 = {"key": "value"}
        with patch.object(gc, "collect") as mock_gc:
            cleanup(obj1, obj2)
            mock_gc.assert_called_once()
