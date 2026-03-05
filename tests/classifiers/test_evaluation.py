"""Unit tests for evaluation metrics and report generation.

Tests use synthetic data only — no real model artifacts required.
All tests complete in under 15 seconds total.
"""

from __future__ import annotations

import sys
import csv
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import ndcg_score

from sip_engine.classifiers.evaluation.evaluator import (
    _compute_calibration_metrics,
    _compute_discrimination_metrics,
    _compute_ranking_metrics,
    _compute_threshold_analysis,
    _get_output_path,
    _write_csv_report,
    _write_json_report,
    _write_markdown_report,
    map_at_k,
)
from sip_engine.classifiers.evaluation.visualizer import (
    generate_all_charts,
    plot_calibration_summary,
    plot_confusion_matrix,
    plot_precision_recall_f1,
    plot_ranking_metrics,
    plot_roc_curve,
    plot_score_distribution,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def synthetic_data():
    """Synthetic binary classification data with controlled ranking (20% positive)."""
    rng = np.random.RandomState(42)
    n = 200
    y_true = np.array([1] * 40 + [0] * 160)  # 20% positive
    y_scores = rng.rand(n)
    y_scores[:40] += 0.3  # Make positives higher scoring on average
    y_scores = np.clip(y_scores, 0, 1)
    return y_true, y_scores


@pytest.fixture
def perfect_ranking_data():
    """Perfect classifier: all positives scored higher than negatives."""
    y_true = np.array([1, 1, 1, 0, 0, 0, 0, 0])
    y_scores = np.array([0.9, 0.8, 0.7, 0.4, 0.3, 0.2, 0.1, 0.05])
    return y_true, y_scores


@pytest.fixture
def minimal_eval_dict(synthetic_data):
    """A minimal eval_dict assembled from real computations on synthetic_data."""
    from sip_engine.classifiers.evaluation.evaluator import _compute_recall_precision_at_k
    y_true, y_scores = synthetic_data
    disc = _compute_discrimination_metrics(y_true, y_scores)
    ranking = _compute_ranking_metrics(y_true, y_scores)
    calib = _compute_calibration_metrics(y_true, y_scores)
    ta = _compute_threshold_analysis(y_true, y_scores)
    rp = _compute_recall_precision_at_k(y_true, y_scores)
    opt = ta["optimal_threshold"]
    n = len(y_true)
    positive_rate = float(y_true.mean())
    return {
        "model_id": "M1",
        "evaluation_date": "2026-03-02T00:00:00+00:00",
        "test_set_size": n,
        "label_distribution": {
            "n_positive": int(y_true.sum()),
            "n_negative": int((y_true == 0).sum()),
            "positive_rate": positive_rate,
        },
        "discrimination": disc,
        "ranking": ranking,
        "recall_precision_at_k": rp,
        "calibration": calib,
        "threshold_analysis": ta,
        "optimal_threshold": opt,
        "training_context": {
            "best_params": {"n_estimators": 100, "max_depth": 4},
            "imbalance_strategy": "scale_pos_weight",
            "best_cv_scores": {"scores": [0.75, 0.80], "mean": 0.775, "std": 0.025},
            "hp_search_history": [],
        },
    }


# =============================================================================
# MAP@k tests
# =============================================================================


def test_map_at_k_perfect_ranking(perfect_ranking_data):
    """Perfect ranking: all positives in top-3 → MAP@3 and MAP@8 == 1.0."""
    y_true, y_scores = perfect_ranking_data
    # Top-3 are all positives: precision at pos 1=1/1, 2=2/2, 3=3/3 → mean=1.0
    result = map_at_k(y_true, y_scores, k=3)
    assert result == pytest.approx(1.0, abs=1e-6), f"Expected MAP@3=1.0, got {result}"

    result_full = map_at_k(y_true, y_scores, k=8)
    assert result_full == pytest.approx(1.0, abs=1e-6), f"Expected MAP@8=1.0, got {result_full}"


def test_map_at_k_worst_ranking():
    """All positives at bottom → MAP@3 should be 0.0 (no positives in top-3)."""
    y_true = np.array([0, 0, 0, 1, 1])
    y_scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5])
    result = map_at_k(y_true, y_scores, k=3)
    assert result == pytest.approx(0.0, abs=1e-6), f"Expected MAP@3=0.0, got {result}"


def test_map_at_k_k_larger_than_n():
    """k > n should clamp to n and not crash."""
    rng = np.random.RandomState(0)
    n = 10
    y_true = np.array([1, 0, 1, 0, 1, 0, 0, 0, 0, 0])
    y_scores = rng.rand(n)
    # k=1000 >> n=10 — should run fine
    result = map_at_k(y_true, y_scores, k=1000)
    assert 0.0 <= result <= 1.0, f"MAP@1000 out of range: {result}"


def test_map_at_k_no_positives():
    """All-zero y_true → MAP@k should be 0.0."""
    y_true = np.zeros(20, dtype=int)
    y_scores = np.random.rand(20)
    for k in [5, 10, 20, 100]:
        result = map_at_k(y_true, y_scores, k=k)
        assert result == pytest.approx(0.0, abs=1e-6), f"MAP@{k} should be 0.0 for all-zero labels"


# =============================================================================
# Metric computation tests
# =============================================================================


def test_ndcg_computation(synthetic_data):
    """NDCG@100 and NDCG@200 should both be in [0, 1]."""
    y_true, y_scores = synthetic_data
    ndcg_100 = float(ndcg_score(y_true.reshape(1, -1), y_scores.reshape(1, -1), k=100))
    ndcg_200 = float(ndcg_score(y_true.reshape(1, -1), y_scores.reshape(1, -1), k=200))
    assert 0.0 <= ndcg_100 <= 1.0, f"NDCG@100 out of range: {ndcg_100}"
    assert 0.0 <= ndcg_200 <= 1.0, f"NDCG@200 out of range: {ndcg_200}"


def test_discrimination_metrics(synthetic_data):
    """_compute_discrimination_metrics returns correct keys and reasonable AUC."""
    y_true, y_scores = synthetic_data
    result = _compute_discrimination_metrics(y_true, y_scores)

    assert "auc_roc" in result, "Missing key: auc_roc"
    assert "roc_curve" in result, "Missing key: roc_curve"

    auc = result["auc_roc"]
    assert 0.5 < auc < 1.0, f"AUC-ROC should be > 0.5 for biased positives, got {auc}"

    roc = result["roc_curve"]
    assert "fpr" in roc and "tpr" in roc and "thresholds" in roc
    assert len(roc["fpr"]) == len(roc["tpr"]) == len(roc["thresholds"])
    assert len(roc["fpr"]) >= 2, "ROC curve should have at least 2 points"


def test_ranking_metrics(synthetic_data):
    """_compute_ranking_metrics returns all 6 keys with values in [0, 1]."""
    y_true, y_scores = synthetic_data
    result = _compute_ranking_metrics(y_true, y_scores)

    expected_keys = ["map_100", "map_500", "map_1000", "ndcg_100", "ndcg_500", "ndcg_1000"]
    for key in expected_keys:
        assert key in result, f"Missing key: {key}"
        assert 0.0 <= result[key] <= 1.0, f"{key}={result[key]} out of [0, 1]"


def test_calibration_metrics(synthetic_data):
    """_compute_calibration_metrics returns correct Brier Score and baseline."""
    y_true, y_scores = synthetic_data
    result = _compute_calibration_metrics(y_true, y_scores)

    assert "brier_score" in result
    assert "brier_baseline" in result
    assert result["brier_score"] > 0, "Brier score should be positive"
    # 20% positive rate: baseline = 0.2 * 0.8 = 0.16
    expected_baseline = 0.20 * 0.80
    assert result["brier_baseline"] == pytest.approx(expected_baseline, abs=0.001), (
        f"Brier baseline expected ~{expected_baseline:.3f}, got {result['brier_baseline']:.4f}"
    )


def test_threshold_analysis(synthetic_data):
    """_compute_threshold_analysis returns 19 thresholds and valid optimal threshold."""
    y_true, y_scores = synthetic_data
    result = _compute_threshold_analysis(y_true, y_scores)

    assert len(result["thresholds"]) == 19, f"Expected 19 thresholds, got {len(result['thresholds'])}"
    assert len(result["precision"]) == 19
    assert len(result["recall"]) == 19
    assert len(result["f1"]) == 19
    assert len(result["confusion_matrices"]) == 19

    opt = result["optimal_threshold"]
    assert isinstance(opt, dict), "optimal_threshold should be a dict"
    for key in ["value", "precision", "recall", "f1"]:
        assert key in opt, f"optimal_threshold missing key: {key}"

    # Optimal threshold value should be within the sweep range
    assert 0.05 <= opt["value"] <= 0.95, f"Optimal threshold {opt['value']} out of sweep range"


def test_threshold_analysis_confusion_matrices(synthetic_data):
    """Confusion matrices at each threshold sum to total samples."""
    y_true, y_scores = synthetic_data
    result = _compute_threshold_analysis(y_true, y_scores)
    n = len(y_true)

    for i, cm in enumerate(result["confusion_matrices"]):
        total = cm["tn"] + cm["fp"] + cm["fn"] + cm["tp"]
        assert total == n, f"Threshold {result['thresholds'][i]}: CM sum={total}, expected {n}"

    # At very low threshold (0.05), recall should be high (most predicted positive)
    idx_low = result["thresholds"].index(0.05)
    assert result["recall"][idx_low] > 0.7, (
        f"At threshold 0.05, recall should be high, got {result['recall'][idx_low]:.4f}"
    )

    # At very high threshold (0.95), precision should be high or zero (few positives predicted)
    idx_high = result["thresholds"].index(0.95)
    prec_high = result["precision"][idx_high]
    assert prec_high >= 0.0, f"Precision at 0.95 should be >= 0, got {prec_high}"
    # If anything is predicted at 0.95, precision should be high for a biased classifier
    cm_high = result["confusion_matrices"][idx_high]
    n_predicted_positive = cm_high["tp"] + cm_high["fp"]
    if n_predicted_positive > 0:
        assert prec_high > 0.3, (
            f"At threshold 0.95, precision should be high if any predicted, got {prec_high:.4f}"
        )


# =============================================================================
# Report generation tests
# =============================================================================


def test_json_report_schema(minimal_eval_dict, tmp_path):
    """_write_json_report produces valid JSON with required top-level keys."""
    output_path = tmp_path / "M1_eval.json"
    _write_json_report(minimal_eval_dict, output_path)

    assert output_path.exists(), "JSON report file should exist"
    content = json.loads(output_path.read_text())

    required_keys = [
        "model_id", "evaluation_date", "discrimination", "ranking",
        "calibration", "threshold_analysis", "optimal_threshold",
    ]
    for key in required_keys:
        assert key in content, f"JSON report missing required key: {key}"

    assert content["model_id"] == "M1"
    assert "auc_roc" in content["discrimination"]
    assert "roc_curve" in content["discrimination"]


def test_csv_report_parseable(minimal_eval_dict, tmp_path):
    """_write_csv_report produces a parseable CSV with correct structure."""
    output_path = tmp_path / "M1_eval.csv"
    _write_csv_report(minimal_eval_dict, output_path)

    assert output_path.exists(), "CSV report file should exist"

    with output_path.open() as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Header + 19 threshold rows + 13 summary rows = 33 total
    assert len(rows) >= 20, f"Expected at least 20 rows (header + thresholds), got {len(rows)}"

    header = rows[0]
    assert "metric_type" in header, f"Header missing 'metric_type': {header}"
    assert "threshold" in header, f"Header missing 'threshold': {header}"

    # Count threshold rows
    threshold_rows = [r for r in rows[1:] if r[0] == "threshold"]
    assert len(threshold_rows) == 19, f"Expected 19 threshold rows, got {len(threshold_rows)}"

    # Count summary rows
    summary_rows = [r for r in rows[1:] if r[0] == "summary"]
    assert len(summary_rows) >= 1, "Expected at least 1 summary row"


def test_markdown_report_generated(minimal_eval_dict, tmp_path):
    """_write_markdown_report produces a valid Markdown file."""
    output_path = tmp_path / "M1_eval.md"
    _write_markdown_report(minimal_eval_dict, output_path)

    assert output_path.exists(), "Markdown report file should exist"
    content = output_path.read_text(encoding='utf-8')

    assert content.startswith("# Evaluation Report"), (
        f"Markdown should start with '# Evaluation Report', got: {content[:50]!r}"
    )
    assert "AUC-ROC" in content, "Markdown should contain 'AUC-ROC'"
    assert "MAP@" in content, "Markdown should contain 'MAP@'"
    assert "Brier" in content, "Markdown should contain 'Brier'"
    assert "Threshold" in content, "Markdown should contain 'Threshold'"


def test_timestamped_output_no_overwrite(tmp_path):
    """_get_output_path returns timestamped path when base path already exists."""
    output_dir = tmp_path / "evaluation"
    model_id = "M1"
    extension = ".json"

    # First call: base path doesn't exist → return base path
    first_path = _get_output_path(output_dir, model_id, extension)
    assert first_path == output_dir / model_id / f"{model_id}_eval{extension}"

    # Simulate the file existing
    first_path.parent.mkdir(parents=True, exist_ok=True)
    first_path.touch()

    # Second call: base path exists → return timestamped path
    second_path = _get_output_path(output_dir, model_id, extension)
    assert second_path != first_path, "Second path should differ from first (timestamped)"
    assert second_path.name.startswith(f"{model_id}_eval_"), (
        f"Timestamped path should start with '{model_id}_eval_', got: {second_path.name}"
    )
    assert second_path.suffix == extension, f"Extension should be {extension}"


# =============================================================================
# Integration fixtures and helpers
# =============================================================================


def _create_mock_model_artifacts(tmp_models_dir: Path, model_id: str) -> None:
    """Create minimal model artifacts for a given model_id.

    Creates model.pkl, test_data.parquet, feature_registry.json, and
    training_report.json in tmp_models_dir / model_id.
    """
    import joblib
    from xgboost import XGBClassifier

    model_dir = tmp_models_dir / model_id
    model_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.RandomState(42)
    feature_names = ["f1", "f2", "f3", "f4", "f5"]

    # Train a tiny XGBoost model on synthetic data using DataFrame for feature names
    X_train = pd.DataFrame(rng.rand(100, 5), columns=feature_names)
    y_train = np.array([1] * 20 + [0] * 80)

    clf = XGBClassifier(n_estimators=5, max_depth=2, random_state=42)
    clf.fit(X_train, y_train)

    # Save model.pkl
    joblib.dump(clf, model_dir / "model.pkl")

    # Save test_data.parquet with label column named after model_id
    X_test = pd.DataFrame(rng.rand(50, 5), columns=feature_names)
    y_test = np.array([1] * 10 + [0] * 40)
    test_df = X_test.copy()
    test_df[model_id] = y_test
    test_df.to_parquet(model_dir / "test_data.parquet", index=False)

    # Save feature_registry.json (key must be "feature_columns" to match evaluator)
    (model_dir / "feature_registry.json").write_text(
        json.dumps({"feature_columns": feature_names})
    )

    # Save training_report.json (matches trainer.py output structure)
    (model_dir / "training_report.json").write_text(json.dumps({
        "model_id": model_id,
        "best_params": {"n_estimators": 5, "max_depth": 2},
        "strategy_comparison": {
            "scale_pos_weight": {"mean_cv_auc": 0.75, "best_cv_auc": 0.76},
            "upsampling_25pct": {"mean_cv_auc": 0.73, "best_cv_auc": 0.74},
            "winner": "scale_pos_weight",
        },
        "label_distribution": {"0": 80, "1": 20},
    }))


@pytest.fixture
def mock_model_artifacts(tmp_path):
    """Create minimal model artifacts for M1 to test single-model pipeline."""
    models_dir = tmp_path / "models"
    output_dir = tmp_path / "evaluation"
    _create_mock_model_artifacts(models_dir, "M1")
    return models_dir, output_dir


# =============================================================================
# Integration tests
# =============================================================================


def test_evaluate_model_end_to_end(mock_model_artifacts):
    """evaluate_model() loads real artifacts, runs metrics, writes 3 reports."""
    from sip_engine.classifiers.evaluation.evaluator import evaluate_model

    models_dir, output_dir = mock_model_artifacts
    result_dir = evaluate_model("M1", models_dir=models_dir, output_dir=output_dir)

    # All 3 report files exist
    assert (output_dir / "M1" / "M1_eval.json").exists(), "JSON report missing"
    assert (output_dir / "M1" / "M1_eval.csv").exists(), "CSV report missing"
    assert (output_dir / "M1" / "M1_eval.md").exists(), "Markdown report missing"

    # JSON report loads and has required keys
    report = json.loads((output_dir / "M1" / "M1_eval.json").read_text())
    required_keys = [
        "model_id", "evaluation_date", "test_set_size",
        "discrimination", "ranking", "calibration",
        "threshold_analysis", "optimal_threshold",
    ]
    for key in required_keys:
        assert key in report, f"JSON report missing key: {key}"

    # Metrics are in valid ranges
    assert 0.0 <= report["discrimination"]["auc_roc"] <= 1.0, "AUC-ROC out of range"
    assert 0.0 <= report["ranking"]["map_100"] <= 1.0, "MAP@100 out of range"
    assert 0.0 <= report["ranking"]["map_1000"] <= 1.0, "MAP@1000 out of range"
    assert 0.0 <= report["calibration"]["brier_score"] <= 1.0, "Brier score out of range"

    # 19 thresholds in threshold_analysis
    assert len(report["threshold_analysis"]["thresholds"]) == 19, "Expected 19 thresholds"

    # optimal_threshold has required keys
    opt = report["optimal_threshold"]
    for key in ["value", "precision", "recall", "f1"]:
        assert key in opt, f"optimal_threshold missing key: {key}"

    # Return value is the model output directory
    assert result_dir == output_dir / "M1"


def test_evaluate_model_rerun_no_overwrite(mock_model_artifacts):
    """Second evaluate_model() call archives old files to old/ subfolder."""
    from sip_engine.classifiers.evaluation.evaluator import evaluate_model

    models_dir, output_dir = mock_model_artifacts

    # First run: creates base files
    evaluate_model("M1", models_dir=models_dir, output_dir=output_dir)

    # Second run: archives first run to old/, then creates new base files
    evaluate_model("M1", models_dir=models_dir, output_dir=output_dir)

    # The base files still exist (freshly written by the second run)
    assert (output_dir / "M1" / "M1_eval.json").exists(), "Base JSON missing after re-run"

    # Old evaluation was archived
    old_dir = output_dir / "M1" / "old"
    assert old_dir.exists(), "old/ directory missing after re-run"
    archive_dirs = list(old_dir.iterdir())
    assert len(archive_dirs) >= 1, "Expected at least one archive folder in old/"
    # Archived folder should contain the previous evaluation files
    archived_files = list(archive_dirs[0].iterdir())
    assert any("M1_eval" in f.name for f in archived_files), "Archived M1_eval file missing"


def test_evaluate_model_missing_model(tmp_path):
    """evaluate_model() raises FileNotFoundError when artifacts are missing."""
    from sip_engine.classifiers.evaluation.evaluator import evaluate_model

    nonexistent_dir = tmp_path / "nonexistent_models"
    with pytest.raises(FileNotFoundError, match="M1"):
        evaluate_model("M1", models_dir=nonexistent_dir, output_dir=tmp_path / "eval")


def test_evaluate_all_summary_files(tmp_path):
    """evaluate_all() produces summary.json and summary.csv for all 4 models."""
    from sip_engine.classifiers.evaluation.evaluator import evaluate_all

    models_dir = tmp_path / "models"
    output_dir = tmp_path / "evaluation"

    # Create mock artifacts for all 4 models
    for mid in ["M1", "M2", "M3", "M4"]:
        _create_mock_model_artifacts(models_dir, mid)

    result_dir = evaluate_all(models_dir=models_dir, output_dir=output_dir)

    # Summary files exist
    assert (output_dir / "summary.json").exists(), "summary.json missing"
    assert (output_dir / "summary.csv").exists(), "summary.csv missing"

    # summary.json has entries for all 4 models
    summary = json.loads((output_dir / "summary.json").read_text())
    for mid in ["M1", "M2", "M3", "M4"]:
        assert mid in summary, f"summary.json missing entry for {mid}"

    # Return value is the evaluation output directory
    assert result_dir == output_dir


def test_cli_evaluate_help():
    """CLI 'python -m sip_engine evaluate --help' exits 0 and shows all flags."""
    result = subprocess.run(
        [sys.executable, "-m", "sip_engine", "evaluate", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, f"evaluate --help exit code: {result.returncode}\nSTDERR:\n{result.stderr}"
    assert "--model" in result.stdout, "--model flag missing from help output"
    assert "--models-dir" in result.stdout, "--models-dir flag missing from help output"
    assert "--output-dir" in result.stdout, "--output-dir flag missing from help output"


# =============================================================================
# Visualizer tests
# =============================================================================


def test_plot_confusion_matrix(minimal_eval_dict, tmp_path):
    """plot_confusion_matrix creates a PNG file."""
    img_dir = tmp_path / "images"
    path = plot_confusion_matrix(minimal_eval_dict, img_dir)
    assert path.exists(), "Confusion matrix image should exist"
    assert path.suffix == ".png"
    assert path.stat().st_size > 1000, "Image file should have content"


def test_plot_roc_curve(minimal_eval_dict, tmp_path):
    """plot_roc_curve creates a PNG file."""
    img_dir = tmp_path / "images"
    path = plot_roc_curve(minimal_eval_dict, img_dir)
    assert path.exists(), "ROC curve image should exist"
    assert path.suffix == ".png"
    assert path.stat().st_size > 1000


def test_plot_precision_recall_f1(minimal_eval_dict, tmp_path):
    """plot_precision_recall_f1 creates a PNG file."""
    img_dir = tmp_path / "images"
    path = plot_precision_recall_f1(minimal_eval_dict, img_dir)
    assert path.exists(), "P/R/F1 image should exist"
    assert path.suffix == ".png"


def test_plot_ranking_metrics(minimal_eval_dict, tmp_path):
    """plot_ranking_metrics creates a PNG file."""
    img_dir = tmp_path / "images"
    path = plot_ranking_metrics(minimal_eval_dict, img_dir)
    assert path.exists(), "Ranking metrics image should exist"
    assert path.suffix == ".png"


def test_plot_score_distribution(synthetic_data, minimal_eval_dict, tmp_path):
    """plot_score_distribution creates a PNG file."""
    y_true, y_scores = synthetic_data
    img_dir = tmp_path / "images"
    path = plot_score_distribution(y_true, y_scores, minimal_eval_dict, img_dir)
    assert path.exists(), "Score distribution image should exist"
    assert path.suffix == ".png"


def test_plot_calibration_summary(minimal_eval_dict, tmp_path):
    """plot_calibration_summary creates a PNG file."""
    img_dir = tmp_path / "images"
    path = plot_calibration_summary(minimal_eval_dict, img_dir)
    assert path.exists(), "Calibration image should exist"
    assert path.suffix == ".png"


def test_generate_all_charts(synthetic_data, minimal_eval_dict, tmp_path):
    """generate_all_charts creates all 7 chart files."""
    y_true, y_scores = synthetic_data
    img_dir = tmp_path / "images"
    paths = generate_all_charts(minimal_eval_dict, y_true, y_scores, img_dir)
    assert len(paths) == 7, f"Expected 7 charts, got {len(paths)}"
    for p in paths:
        assert p.exists(), f"Chart file missing: {p.name}"
        assert p.stat().st_size > 1000, f"Chart file too small: {p.name}"


def test_markdown_report_contains_images(minimal_eval_dict, tmp_path):
    """Updated _write_markdown_report embeds image references."""
    output_path = tmp_path / "M1_eval.md"
    _write_markdown_report(minimal_eval_dict, output_path)

    content = output_path.read_text(encoding='utf-8')
    assert "![ROC Curve]" in content, "Markdown should embed ROC curve image"
    assert "![Confusion Matrix]" in content, "Markdown should embed confusion matrix image"
    assert "![Precision-Recall-F1]" in content, "Markdown should embed P/R/F1 image"
    assert "![Ranking Metrics]" in content, "Markdown should embed ranking image"
    assert "![Score Distribution]" in content, "Markdown should embed score distribution image"
    assert "![Calibration]" in content, "Markdown should embed calibration image"
    assert "images/" in content, "Image paths should reference images/ directory"
