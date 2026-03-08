"""Tests for model selector: TUI picker, CLI nargs, PipelineConfig type."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch

import pytest

from sip_engine.classifiers.ui.config_screen import show_model_picker, _CheckboxWidget
from sip_engine.pipeline import PipelineConfig


# ---- CheckboxWidget unit tests ----

class TestCheckboxWidget:
    def test_default_all_selected(self):
        w = _CheckboxWidget(["M1", "M2", "M3", "M4"])
        assert w.selected == {"M1", "M2", "M3", "M4"}

    def test_toggle_deselects(self):
        w = _CheckboxWidget(["M1", "M2"])
        w.toggle()  # cursor at 0 = M1
        assert "M1" not in w.selected
        assert "M2" in w.selected

    def test_toggle_reselects(self):
        w = _CheckboxWidget(["M1", "M2"], selected=set())
        w.toggle()  # cursor at 0 = M1
        assert "M1" in w.selected

    def test_move_and_toggle(self):
        w = _CheckboxWidget(["M1", "M2", "M3"])
        w.move_down()
        w.toggle()  # toggles M2
        assert "M1" in w.selected
        assert "M2" not in w.selected
        assert "M3" in w.selected

    def test_move_up_at_top(self):
        w = _CheckboxWidget(["M1", "M2"])
        w.move_up()  # already at 0
        assert w._cursor == 0

    def test_move_down_at_bottom(self):
        w = _CheckboxWidget(["M1", "M2"])
        w.move_down()
        w.move_down()  # can't go past 1
        assert w._cursor == 1

    def test_render_returns_text(self):
        from rich.text import Text
        w = _CheckboxWidget(["M1", "M2"])
        result = w.render()
        assert isinstance(result, Text)


# ---- show_model_picker non-interactive fallback ----

class TestShowModelPickerFallback:
    def test_non_tty_returns_all_models(self):
        """When stdin is not a TTY, returns all 4 models."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = show_model_picker()
            assert result == ["M1", "M2", "M3", "M4"]

    def test_non_tty_custom_ids(self):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = show_model_picker(["M1", "M3"])
            assert result == ["M1", "M3"]


# ---- PipelineConfig type tests ----

class TestPipelineConfigModel:
    def test_model_accepts_list(self):
        cfg = PipelineConfig(
            n_jobs=1, n_iter=10, cv_folds=3, max_ram_gb=4,
            device="cpu", model=["M1", "M3"]
        )
        assert cfg.model == ["M1", "M3"]
        assert isinstance(cfg.model, list)

    def test_model_default_none(self):
        cfg = PipelineConfig(
            n_jobs=1, n_iter=10, cv_folds=3, max_ram_gb=4, device="cpu"
        )
        assert cfg.model is None

    def test_model_single_item_list(self):
        cfg = PipelineConfig(
            n_jobs=1, n_iter=10, cv_folds=3, max_ram_gb=4,
            device="cpu", model=["M2"]
        )
        assert cfg.model == ["M2"]


# ---- CLI nargs='+' integration test ----

class TestCLINargs:
    def test_train_help_shows_model_nargs(self):
        result = subprocess.run(
            [sys.executable, "-m", "sip_engine", "train", "--help"],
            capture_output=True, text=True
        )
        assert "MODEL" in result.stdout  # metavar
        assert "--model" in result.stdout

    def test_evaluate_help_shows_model_nargs(self):
        result = subprocess.run(
            [sys.executable, "-m", "sip_engine", "evaluate", "--help"],
            capture_output=True, text=True
        )
        assert "MODEL" in result.stdout
        assert "--model" in result.stdout

    def test_run_pipeline_help_shows_model_nargs(self):
        result = subprocess.run(
            [sys.executable, "-m", "sip_engine", "run-pipeline", "--help"],
            capture_output=True, text=True
        )
        assert "MODEL" in result.stdout
        assert "--model" in result.stdout
