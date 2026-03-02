"""Master system test for the full SIP analysis pipeline.

Validates the complete path from synthetic data → model artifacts →
analyze_contract() → deterministic JSON output.

Two test modes:
    fixture-based  — uses synthetic data + toy models, CI-friendly (default)
    real-data      — loads artifacts/models/ and real contratos data
                     (triggered via --real-data flag, skipped when absent)

PROJ-04 audit (confirmed coverage):
------------------------------------
1. RCAC normalization round-trips:
   - test_rcac.py::test_lookup_normalizes_input  ✓ (raw dotted NIT → normalised → hit)
   - test_rcac.py::test_lookup_hit_returns_record ✓ (build_rcac → rcac_lookup round-trip)
   - test_rcac.py::test_build_creates_pkl ✓ (pkl persistence)

2. Provider history as-of-date temporal guard:
   - test_features.py::test_lookup_future_contracts_excluded ✓
   - test_features.py::test_lookup_same_day_excluded ✓
   - Both confirm strict < as_of_date cutoff (bisect_left pattern)

3. IRIC component tests (≥4):
   - test_iric.py covers 7+ IRIC calculator tests (TestUnicoProponente,
     TestProvedorMultiproposito, TestHistorialProveedor, TestContratacionDirecta,
     TestRegimenEspecial, TestPeriodoPublicidad, TestBidStats) = 15+ component tests ✓

4. predict_proba in [0, 1]:
   - test_models.py::test_train_model_end_to_end_quick (parametrized M1–M4)
   - Explicitly asserts: (proba >= 0).all() and (proba <= 1).all() ✓
   - Also covered by test_analyze_contract_shap_top10_per_model in
     test_explainability.py (0 ≤ probability ≤ 1 for all 4 models) ✓

Gap assessment: no new tests required — all 4 PROJ-04 criteria are covered.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

import sip_engine.explainability.analyzer as _analyzer_mod
from sip_engine.explainability import analyze_contract, serialize_to_json
from sip_engine.features.pipeline import FEATURE_COLUMNS


# =============================================================================
# pytest option registration
# =============================================================================


def pytest_addoption(parser):
    """Add --real-data flag to pytest CLI."""
    try:
        parser.addoption(
            "--real-data",
            action="store_true",
            default=False,
            help="Run real-data system tests (requires artifacts/models/ to be built).",
        )
    except ValueError:
        # pytest_addoption may be called multiple times; ignore duplicate
        pass


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def synthetic_feature_dict():
    """Return a deterministic 34-feature dict matching FEATURE_COLUMNS."""
    rng = np.random.RandomState(7)
    result: dict = {}
    for col in FEATURE_COLUMNS:
        if col.startswith("es_") or col.startswith("firma_") or col.startswith("proponente_"):
            result[col] = float(rng.randint(0, 2))
        elif col in ("tipo_persona_proveedor",):
            result[col] = float(rng.randint(0, 2))
        else:
            result[col] = float(round(rng.uniform(0.0, 1.0), 6))
    return result


@pytest.fixture(scope="module")
def toy_models_dir(tmp_path_factory):
    """Create M1–M4 model dirs each with a toy XGBClassifier for 34 features."""
    base = tmp_path_factory.mktemp("sys_models")
    models_root = base / "models"

    rng = np.random.RandomState(42)
    n_train = 50
    X_data = rng.rand(n_train, len(FEATURE_COLUMNS)).astype(np.float32)
    y_data = np.array([0] * 40 + [1] * 10, dtype=np.int32)
    X_df = pd.DataFrame(X_data, columns=FEATURE_COLUMNS)

    for model_id in ["M1", "M2", "M3", "M4"]:
        model_dir = models_root / model_id
        model_dir.mkdir(parents=True, exist_ok=True)

        clf = xgb.XGBClassifier(n_estimators=5, max_depth=2, random_state=42, eval_metric="logloss")
        clf.fit(X_df, y_data)

        joblib.dump(clf, model_dir / "model.pkl")

        registry = {
            "model_id": model_id,
            "feature_columns": FEATURE_COLUMNS,
            "n_features": len(FEATURE_COLUMNS),
            "training_date": "2026-03-02T00:00:00+00:00",
        }
        (model_dir / "feature_registry.json").write_text(json.dumps(registry), encoding="utf-8")
        (model_dir / "training_report.json").write_text(
            json.dumps({"model_id": model_id, "training_date": "2026-03-02T00:00:00+00:00"}),
            encoding="utf-8",
        )

    return models_root


# =============================================================================
# Fixture-mode system test (CI-friendly)
# =============================================================================


@pytest.mark.system
def test_full_pipeline_fixture_mode(toy_models_dir, synthetic_feature_dict, monkeypatch):
    """Full pipeline from synthetic feature dict → analyze_contract → JSON output.

    Validates:
    - Result schema (all required top-level keys present)
    - CRI score in [0, 1], level one of 5 valid strings
    - Per-model probability in [0, 1] and shap_top10 non-empty
    - raw_features has 34 keys
    - serialize_to_json produces valid JSON
    - Determinism: same inputs + frozen timestamp → byte-identical output
    """
    # Patch compute_features so the test doesn't need real source files
    feats = dict(synthetic_feature_dict)
    monkeypatch.setattr(_analyzer_mod, "compute_features", lambda *args, **kwargs: feats)

    contract_row = {
        "ID Contrato": "SYS-TEST-001",
        "Tipo de Contrato": "Prestación de Servicios",
        "Modalidad de Contratacion": "Contratación Directa",
        "Valor del Contrato": "$10,000,000",
        "Fecha de Firma": "2023-01-15",
        "TipoDocProveedor": "NIT",
        "Documento Proveedor": "900123456",
        "Departamento": "Cundinamarca",
    }
    as_of_date = datetime.date(2023, 1, 15)
    frozen_ts = "2026-03-02T12:00:00+00:00"

    # First call
    result = analyze_contract(
        contract_row=contract_row,
        as_of_date=as_of_date,
        models_dir=toy_models_dir,
        timestamp=frozen_ts,
    )

    # ---- Schema assertions ----
    required_keys = {"contract_id", "cri", "models", "iric_score", "raw_features", "metadata"}
    assert required_keys == set(result.keys()), (
        f"Missing keys: {required_keys - set(result.keys())}"
    )

    # ---- CRI assertions ----
    cri = result["cri"]
    assert isinstance(cri["score"], float), f"cri.score not float: {type(cri['score'])}"
    assert 0.0 <= cri["score"] <= 1.0, f"cri.score out of [0,1]: {cri['score']}"
    valid_levels = {"Very Low", "Low", "Medium", "High", "Very High"}
    assert cri["level"] in valid_levels, f"cri.level invalid: {cri['level']!r}"
    assert len(cri["weights_used"]) == 5, f"weights_used must have 5 keys"

    # ---- Per-model assertions ----
    assert len(result["models"]) == 4, f"Expected 4 models, got {len(result['models'])}"
    for mid, mdata in result["models"].items():
        p = mdata["probability"]
        assert 0.0 <= p <= 1.0, f"{mid}.probability {p} out of [0, 1]"
        s10 = mdata["shap_top10"]
        assert isinstance(s10, list) and len(s10) > 0, f"{mid}.shap_top10 is empty"

    # ---- raw_features has 34 keys ----
    assert len(result["raw_features"]) == 34, (
        f"raw_features has {len(result['raw_features'])} keys, expected 34"
    )

    # ---- JSON validity ----
    json_str = serialize_to_json(result)
    parsed = json.loads(json_str)
    assert isinstance(parsed, dict), "serialize_to_json result must parse to dict"

    # ---- Determinism ----
    result2 = analyze_contract(
        contract_row=contract_row,
        as_of_date=as_of_date,
        models_dir=toy_models_dir,
        timestamp=frozen_ts,
    )
    json2 = serialize_to_json(result2)
    assert json_str == json2, "Same inputs with frozen timestamp must be byte-identical"

    # ---- contract_id preserved ----
    assert result["contract_id"] == "SYS-TEST-001"

    # ---- metadata structure ----
    meta = result["metadata"]
    assert "model_versions" in meta, "metadata must have model_versions"
    assert "timestamp" in meta, "metadata must have timestamp"
    assert meta["timestamp"] == frozen_ts, "metadata.timestamp must match input"
    assert set(meta["model_versions"].keys()) == {"M1", "M2", "M3", "M4"}


# =============================================================================
# Real-data mode test (skipped unless --real-data flag given)
# =============================================================================


@pytest.mark.system
def test_full_pipeline_real_data(request):
    """Full pipeline with real trained model artifacts and a synthetic contract row.

    Requires:
        - artifacts/models/M1/model.pkl (and M2, M3, M4)
        - model_weights.json (already committed)

    Skip conditions:
        - --real-data flag not passed
        - artifacts/models/M1/model.pkl does not exist
    """
    if not request.config.getoption("--real-data", default=False):
        pytest.skip("Pass --real-data to run real-data system tests")

    from sip_engine.config import get_settings
    settings = get_settings()
    models_dir = settings.artifacts_models_dir
    m1_pkl = models_dir / "M1" / "model.pkl"

    if not m1_pkl.exists():
        pytest.skip(f"Real models not found at {models_dir} — run train_model() first")

    # Use a minimal synthetic contract row (no real PII)
    contract_row = {
        "ID Contrato": "REAL-DATA-TEST",
        "Tipo de Contrato": "Prestación de Servicios",
        "Modalidad de Contratacion": "Contratación Directa",
        "Valor del Contrato": "$10,000,000",
        "Fecha de Firma": "2023-06-01",
        "TipoDocProveedor": "NIT",
        "Documento Proveedor": "900123456",
        "Departamento": "Cundinamarca",
    }
    as_of_date = datetime.date(2023, 6, 1)
    frozen_ts = "2026-03-02T00:00:00+00:00"

    result = analyze_contract(
        contract_row=contract_row,
        as_of_date=as_of_date,
        models_dir=models_dir,
        timestamp=frozen_ts,
    )

    # Same schema assertions as fixture mode
    required_keys = {"contract_id", "cri", "models", "iric_score", "raw_features", "metadata"}
    assert required_keys == set(result.keys())

    cri = result["cri"]
    assert 0.0 <= cri["score"] <= 1.0
    valid_levels = {"Very Low", "Low", "Medium", "High", "Very High"}
    assert cri["level"] in valid_levels

    for mid, mdata in result["models"].items():
        assert 0.0 <= mdata["probability"] <= 1.0
        assert len(mdata["shap_top10"]) > 0

    json_str = serialize_to_json(result)
    assert json.loads(json_str) is not None
