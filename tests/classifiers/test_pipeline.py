"""Unit tests for sip_engine.pipeline coordinator."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sip_engine.pipeline import (
    STEP_NAMES,
    PipelineConfig,
    _STEP_FNS,
    _STEP_FN_NAMES,
    _STEP_LABELS,
    run_evaluate,
    run_features,
    run_iric,
    run_labels,
    run_pipeline,
    run_rcac,
    run_train,
)


# ---------------------------------------------------------------------------
# PipelineConfig
# ---------------------------------------------------------------------------


class TestPipelineConfig:
    """Tests for the PipelineConfig frozen dataclass."""

    def test_creation_with_defaults(self):
        cfg = PipelineConfig(n_jobs=4, n_iter=200, cv_folds=5, max_ram_gb=8, device="cpu")
        assert cfg.n_jobs == 4
        assert cfg.n_iter == 200
        assert cfg.cv_folds == 5
        assert cfg.max_ram_gb == 8
        assert cfg.device == "cpu"
        # defaults
        assert cfg.force is False
        assert cfg.model is None
        assert cfg.quick is False
        assert cfg.disable_rocm is False
        assert cfg.show_stats is True

    def test_creation_with_custom_values(self):
        cfg = PipelineConfig(
            n_jobs=8,
            n_iter=50,
            cv_folds=3,
            max_ram_gb=16,
            device="cuda",
            force=True,
            model=["M2"],
            quick=True,
            disable_rocm=True,
            show_stats=False,
        )
        assert cfg.force is True
        assert cfg.model == ["M2"]
        assert cfg.quick is True
        assert cfg.disable_rocm is True
        assert cfg.show_stats is False

    def test_frozen(self):
        cfg = PipelineConfig(n_jobs=4, n_iter=200, cv_folds=5, max_ram_gb=8, device="cpu")
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.n_jobs = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------


class TestStepRegistry:
    """Tests for STEP_NAMES, _STEP_LABELS, and _STEP_FNS."""

    def test_step_names_has_6_entries(self):
        assert len(STEP_NAMES) == 6

    def test_step_names_order(self):
        assert STEP_NAMES == ("rcac", "labels", "iric", "features", "train", "evaluate")

    def test_step_labels_match_step_names(self):
        assert set(_STEP_LABELS.keys()) == set(STEP_NAMES)

    def test_step_fns_match_step_names(self):
        assert set(_STEP_FNS.keys()) == set(STEP_NAMES)

    def test_step_fn_names_match_step_names(self):
        assert set(_STEP_FN_NAMES.keys()) == set(STEP_NAMES)

    def test_all_run_functions_callable(self):
        for name in STEP_NAMES:
            assert callable(_STEP_FNS[name])


# ---------------------------------------------------------------------------
# run_* functions (mocked domain modules)
# ---------------------------------------------------------------------------

_CFG = PipelineConfig(n_jobs=2, n_iter=50, cv_folds=3, max_ram_gb=4, device="cpu", force=True)


class TestRunFunctions:
    """Test that each run_* function delegates correctly."""

    def test_run_rcac(self):
        with patch("sip_engine.shared.data.rcac_builder.build_rcac", return_value=Path("rcac.pkl")) as m:
            result = run_rcac(_CFG)
        m.assert_called_once_with(force=True)
        assert result == Path("rcac.pkl")

    def test_run_labels(self):
        with patch("sip_engine.shared.data.label_builder.build_labels", return_value=Path("labels.parquet")) as m:
            result = run_labels(_CFG)
        m.assert_called_once_with(force=True)
        assert result == Path("labels.parquet")

    def test_run_features(self):
        with patch("sip_engine.classifiers.features.pipeline.build_features", return_value=Path("features.parquet")) as m:
            result = run_features(_CFG)
        m.assert_called_once_with(
            force=True,
            n_jobs=2,
            max_ram_gb=4,
            device="cpu",
            interactive=False,
            show_progress=True,
        )
        assert result == Path("features.parquet")

    def test_run_iric(self):
        with patch("sip_engine.classifiers.iric.pipeline.build_iric", return_value=Path("iric.parquet")) as m:
            result = run_iric(_CFG)
        m.assert_called_once_with(force=True)
        assert result == Path("iric.parquet")

    def test_run_train_all_models(self):
        cfg = PipelineConfig(n_jobs=2, n_iter=50, cv_folds=3, max_ram_gb=4, device="cpu", force=True)
        fake_ids = ["M1", "M2", "M3", "M4"]
        with (
            patch("sip_engine.classifiers.models.trainer.MODEL_IDS", fake_ids),
            patch("sip_engine.classifiers.models.trainer.train_model", return_value=Path("model_dir")) as m,
        ):
            results = run_train(cfg)
        assert m.call_count == 4
        assert len(results) == 4

    def test_run_train_single_model(self):
        cfg = PipelineConfig(n_jobs=2, n_iter=50, cv_folds=3, max_ram_gb=4, device="cpu", model=["M1"])
        with patch("sip_engine.classifiers.models.trainer.train_model", return_value=Path("m1_dir")) as m:
            results = run_train(cfg)
        m.assert_called_once()
        assert results == [Path("m1_dir")]

    def test_run_evaluate_all(self):
        cfg = PipelineConfig(n_jobs=2, n_iter=50, cv_folds=3, max_ram_gb=4, device="cpu")
        with (
            patch("sip_engine.classifiers.evaluation.evaluator.evaluate_all", return_value=Path("eval_dir")) as m,
            patch("sip_engine.classifiers.evaluation.evaluator.MODEL_IDS", ["M1", "M2", "M3", "M4"]),
        ):
            result = run_evaluate(cfg)
        m.assert_called_once()
        assert result == Path("eval_dir")

    def test_run_evaluate_single_model(self):
        cfg = PipelineConfig(n_jobs=2, n_iter=50, cv_folds=3, max_ram_gb=4, device="cpu", model=["M3"])
        with (
            patch("sip_engine.classifiers.evaluation.evaluator.evaluate_model", return_value=Path("m3_eval")) as m,
            patch("sip_engine.classifiers.evaluation.evaluator.MODEL_IDS", ["M1", "M2", "M3", "M4"]),
        ):
            result = run_evaluate(cfg)
        m.assert_called_once_with(model_id="M3")
        assert result == Path("artifacts/evaluation")


# ---------------------------------------------------------------------------
# run_pipeline orchestrator
# ---------------------------------------------------------------------------


class TestRunPipeline:
    """Tests for the run_pipeline orchestrator."""

    def test_invalid_start_from_raises(self):
        cfg = PipelineConfig(n_jobs=2, n_iter=50, cv_folds=3, max_ram_gb=4, device="cpu")
        with pytest.raises(ValueError, match="Unknown step 'bogus'"):
            run_pipeline(cfg, start_from="bogus")

    def test_invalid_start_from_message_lists_valid(self):
        cfg = PipelineConfig(n_jobs=2, n_iter=50, cv_folds=3, max_ram_gb=4, device="cpu")
        with pytest.raises(ValueError, match="rcac, labels, iric, features, train, evaluate"):
            run_pipeline(cfg, start_from="nope")

    @patch("sip_engine.pipeline.run_evaluate")
    @patch("sip_engine.pipeline.run_train", return_value=[Path("m1")])
    @patch("sip_engine.pipeline.run_iric")
    @patch("sip_engine.pipeline.run_features")
    @patch("sip_engine.pipeline.run_labels")
    @patch("sip_engine.pipeline.run_rcac")
    def test_full_pipeline_calls_all_steps(
        self, m_rcac, m_labels, m_feat, m_iric, m_train, m_eval
    ):
        cfg = PipelineConfig(n_jobs=2, n_iter=50, cv_folds=3, max_ram_gb=4, device="cpu")
        run_pipeline(cfg)
        m_rcac.assert_called_once_with(cfg)
        m_labels.assert_called_once_with(cfg)
        m_feat.assert_called_once_with(cfg)
        m_iric.assert_called_once_with(cfg)
        m_train.assert_called_once_with(cfg)
        m_eval.assert_called_once_with(cfg)

    @patch("sip_engine.pipeline.run_evaluate")
    @patch("sip_engine.pipeline.run_train", return_value=[Path("m1")])
    @patch("sip_engine.pipeline.run_iric")
    @patch("sip_engine.pipeline.run_features")
    @patch("sip_engine.pipeline.run_labels")
    @patch("sip_engine.pipeline.run_rcac")
    def test_start_from_skips_earlier_steps(
        self, m_rcac, m_labels, m_feat, m_iric, m_train, m_eval
    ):
        cfg = PipelineConfig(n_jobs=2, n_iter=50, cv_folds=3, max_ram_gb=4, device="cpu")
        run_pipeline(cfg, start_from="train")
        m_rcac.assert_not_called()
        m_labels.assert_not_called()
        m_feat.assert_not_called()
        m_iric.assert_not_called()
        m_train.assert_called_once_with(cfg)
        m_eval.assert_called_once_with(cfg)
