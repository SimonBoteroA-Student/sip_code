"""Unit tests for TUI components: config screen and training progress display."""

from __future__ import annotations

import inspect
import io
import sys
from unittest.mock import MagicMock, patch

import pytest

from sip_engine.shared.hardware.detector import HardwareConfig
from sip_engine.classifiers.ui.config_screen import (
    _DeviceSelector,
    _SliderWidget,
    show_config_screen,
)
from sip_engine.classifiers.ui.progress import TrainingProgressDisplay


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_hw() -> HardwareConfig:
    """Return a deterministic HardwareConfig for tests."""
    return HardwareConfig(
        os_name="Linux",
        arch="x86_64",
        cpu_cores_physical=4,
        cpu_cores_logical=8,
        ram_total_gb=16.0,
        ram_available_gb=12.0,
        gpu_type="cpu",
        gpu_available=False,
        gpu_name=None,
        gpu_vram_gb=None,
        is_container=False,
    )


# ---------------------------------------------------------------------------
# Config screen tests
# ---------------------------------------------------------------------------


class TestConfigScreenImport:
    """Test that config screen can be imported with correct API."""

    def test_import_and_signature(self) -> None:
        sig = inspect.signature(show_config_screen)
        params = list(sig.parameters.keys())
        assert "hw_config" in params
        assert "defaults" in params

    def test_public_api_exports(self) -> None:
        from sip_engine.classifiers.ui import show_config_screen as sc
        from sip_engine.classifiers.ui import TrainingProgressDisplay as tpd

        assert callable(sc)
        assert tpd is not None


class TestConfigScreenNonInteractive:
    """Test non-interactive (piped stdin) fallback."""

    def test_returns_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = False
        monkeypatch.setattr(sys, "stdin", fake_stdin)

        hw = _fake_hw()
        result = show_config_screen(hw)

        assert isinstance(result, dict)
        assert result["n_jobs"] == 4  # physical cores
        assert result["n_iter"] == 200
        assert result["cv_folds"] == 5
        assert result["device"] == "cpu"

    def test_respects_custom_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = False
        monkeypatch.setattr(sys, "stdin", fake_stdin)

        hw = _fake_hw()
        result = show_config_screen(hw, defaults={"n_iter": 300, "cv_folds": 7})

        assert result["n_iter"] == 300
        assert result["cv_folds"] == 7


class TestSliderWidget:
    """Test _SliderWidget value management."""

    def test_basic_operations(self) -> None:
        s = _SliderWidget("Test", min_val=1, max_val=10, current=5)
        assert s.current == 5
        s.increment()
        assert s.current == 6
        s.decrement()
        assert s.current == 5

    def test_clamp_at_bounds(self) -> None:
        s = _SliderWidget("Test", min_val=1, max_val=10, current=10)
        s.increment()
        assert s.current == 10  # clamped at max
        s2 = _SliderWidget("Test", min_val=1, max_val=10, current=1)
        s2.decrement()
        assert s2.current == 1  # clamped at min

    def test_step_size(self) -> None:
        s = _SliderWidget("Test", min_val=0, max_val=100, current=50, step=10)
        s.increment()
        assert s.current == 60
        s.decrement()
        assert s.current == 50

    def test_digit_entry(self) -> None:
        s = _SliderWidget("Test", min_val=1, max_val=500, current=100)
        s.add_digit("3")
        assert s.current == 3
        s.add_digit("5")
        assert s.current == 35
        s.add_digit("0")
        assert s.current == 350

    def test_render(self) -> None:
        s = _SliderWidget("CPU cores", min_val=1, max_val=10, current=5)
        text = s.render(selected=False)
        assert "CPU cores" in text.plain
        text_sel = s.render(selected=True)
        assert "▸" in text_sel.plain


class TestDeviceSelector:
    """Test _DeviceSelector cycling."""

    def test_cycle_forward(self) -> None:
        ds = _DeviceSelector(["cpu", "cuda"], "cpu")
        assert ds.current == "cpu"
        ds.next_option()
        assert ds.current == "cuda"
        ds.next_option()
        assert ds.current == "cpu"  # wraps around

    def test_cycle_backward(self) -> None:
        ds = _DeviceSelector(["cpu", "cuda", "rocm"], "cuda")
        ds.prev_option()
        assert ds.current == "cpu"
        ds.prev_option()
        assert ds.current == "rocm"  # wraps

    def test_render(self) -> None:
        ds = _DeviceSelector(["cpu", "cuda"], "cpu")
        text = ds.render(selected=True)
        assert "Device" in text.plain


# ---------------------------------------------------------------------------
# Training progress display tests
# ---------------------------------------------------------------------------


class TestTrainingProgressLifecycle:
    """Test start/update/stop lifecycle."""

    def test_basic_lifecycle(self) -> None:
        console = _quiet_console()
        d = TrainingProgressDisplay(
            total_iterations=10, console=console
        )
        d.start()
        for i in range(10):
            d.update(iteration=i, best_score=0.5 + i * 0.01)
        d.stop()
        # No errors = success

    def test_context_manager(self) -> None:
        console = _quiet_console()
        with TrainingProgressDisplay(
            total_iterations=5, console=console
        ) as d:
            for i in range(5):
                d.update(iteration=i)
        # No errors = success


class TestBestScoreTracking:
    """Test best score and trend tracking."""

    def test_tracks_best(self) -> None:
        console = _quiet_console()
        d = TrainingProgressDisplay(total_iterations=10, console=console)
        d.start()
        d.update(iteration=0, best_score=0.7)
        d.update(iteration=1, best_score=0.8)
        d.update(iteration=2, best_score=0.75)  # worse
        d.stop()
        assert d._best_score == 0.8
        assert d._best_iter == 2  # iteration 1, 0-indexed → +1

    def test_no_score_stays_none(self) -> None:
        console = _quiet_console()
        d = TrainingProgressDisplay(total_iterations=3, console=console)
        d.start()
        d.update(iteration=0)
        d.update(iteration=1)
        d.stop()
        assert d._best_score is None


class TestTrendCalculation:
    """Test _calculate_trend with known histories."""

    def test_improving(self) -> None:
        console = _quiet_console()
        d = TrainingProgressDisplay(total_iterations=20, console=console)
        d._score_history = [0.70, 0.72, 0.74, 0.76, 0.78]
        trend = d._calculate_trend()
        assert "↑" in trend
        assert "improving" in trend

    def test_declining(self) -> None:
        console = _quiet_console()
        d = TrainingProgressDisplay(total_iterations=20, console=console)
        d._score_history = [0.80, 0.78, 0.76, 0.74, 0.72]
        trend = d._calculate_trend()
        assert "↓" in trend
        assert "declining" in trend

    def test_stable(self) -> None:
        console = _quiet_console()
        d = TrainingProgressDisplay(total_iterations=20, console=console)
        d._score_history = [0.80, 0.80, 0.80, 0.80]
        trend = d._calculate_trend()
        assert "→" in trend
        assert "stable" in trend

    def test_too_few_scores(self) -> None:
        console = _quiet_console()
        d = TrainingProgressDisplay(total_iterations=20, console=console)
        d._score_history = [0.80]
        trend = d._calculate_trend()
        assert trend == ""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _quiet_console() -> "Console":
    """Return a Console that writes to a StringIO (no terminal output)."""
    from rich.console import Console

    return Console(file=io.StringIO(), force_terminal=True)
