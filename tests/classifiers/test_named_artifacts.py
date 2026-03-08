"""Tests for named model artifacts: run numbering, flat archiving, artifact resolution."""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from sip_engine.classifiers.models.trainer import _next_run_number, _archive_existing_model_flat


class TestNextRunNumber:
    def test_empty_dir(self, tmp_path):
        assert _next_run_number(tmp_path) == 1

    def test_sequential(self, tmp_path):
        (tmp_path / "model_run001_auc_roc.pkl").touch()
        (tmp_path / "model_run002_auc_roc.pkl").touch()
        assert _next_run_number(tmp_path) == 3

    def test_gap_in_sequence(self, tmp_path):
        (tmp_path / "model_run001_auc_roc.pkl").touch()
        (tmp_path / "model_run005_f1.pkl").touch()
        assert _next_run_number(tmp_path) == 6

    def test_scans_old_subdir(self, tmp_path):
        old = tmp_path / "old"
        old.mkdir()
        (old / "model_run003_auc_roc.pkl").touch()
        assert _next_run_number(tmp_path) == 4

    def test_ignores_non_matching_files(self, tmp_path):
        (tmp_path / "model.pkl").touch()
        (tmp_path / "training_report.json").touch()
        assert _next_run_number(tmp_path) == 1

    def test_ignores_directories(self, tmp_path):
        (tmp_path / "old" / "2026-03-04").mkdir(parents=True)
        assert _next_run_number(tmp_path) == 1


class TestArchiveFlat:
    def test_moves_canonical_files(self, tmp_path):
        (tmp_path / "model.pkl").write_text("model")
        (tmp_path / "training_report.json").write_text("{}")
        (tmp_path / "feature_registry.json").write_text("{}")
        _archive_existing_model_flat(tmp_path)
        assert not (tmp_path / "model.pkl").exists()
        assert (tmp_path / "old" / "model.pkl").exists()

    def test_preserves_date_keyed_dirs(self, tmp_path):
        date_dir = tmp_path / "old" / "2026-03-04"
        date_dir.mkdir(parents=True)
        (date_dir / "model.pkl").write_text("old model")
        (tmp_path / "model.pkl").write_text("current")
        _archive_existing_model_flat(tmp_path)
        assert date_dir.exists()
        assert (date_dir / "model.pkl").read_text() == "old model"

    def test_handles_no_existing_model(self, tmp_path):
        # Should not raise even if dir is empty
        _archive_existing_model_flat(tmp_path)

    def test_overwrites_old_canonical(self, tmp_path):
        old = tmp_path / "old"
        old.mkdir()
        (old / "model.pkl").write_text("stale")
        (tmp_path / "model.pkl").write_text("current")
        _archive_existing_model_flat(tmp_path)
        assert (old / "model.pkl").read_text() == "current"
