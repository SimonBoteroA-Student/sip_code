"""Tests for sip_engine.classifiers.iric.bid_stats — kurtosis and DRN formulas (IRIC-04, IRIC-05).

Note: Per parallel execution protocol, these tests live in test_bid_stats.py
(not test_iric.py, which is owned by the 06-01 plan's calculator tests).

Tests cover:
- compute_bid_stats for various bid count scenarios
- kurtosis: requires n >= 4, NaN for fewer
- DRN: requires n >= 3 and lowest > 0, NaN otherwise
- Filtering of NaN and non-positive values
- build_bid_stats_lookup with mocked load_ofertas
"""

from __future__ import annotations

import math
from unittest.mock import patch

import pandas as pd
import pytest
from scipy.stats import kurtosis as scipy_kurtosis

from sip_engine.classifiers.iric.bid_stats import build_bid_stats_lookup, compute_bid_stats


class TestComputeBidStats4Bids:
    """compute_bid_stats returns correct kurtosis and DRN for 4 bids."""

    def test_kurtosis_value(self):
        """Kurtosis matches scipy reference for [100, 200, 300, 400]."""
        result = compute_bid_stats([100, 200, 300, 400])
        expected_kurtosis = scipy_kurtosis([100, 200, 300, 400], fisher=True, bias=False)
        assert not math.isnan(result["curtosis_licitacion"])
        assert abs(result["curtosis_licitacion"] - expected_kurtosis) < 1e-9

    def test_kurtosis_approx_value(self):
        """Kurtosis for uniform [100, 200, 300, 400] is approximately -1.2."""
        result = compute_bid_stats([100, 200, 300, 400])
        assert abs(result["curtosis_licitacion"] - (-1.2)) < 1e-9

    def test_drn_value(self):
        """DRN for [100, 200, 300, 400] = (200-100)/100 = 1.0."""
        result = compute_bid_stats([100, 200, 300, 400])
        assert abs(result["diferencia_relativa_norm"] - 1.0) < 1e-9

    def test_n_bids(self):
        """n_bids is 4 for 4 valid bids."""
        result = compute_bid_stats([100, 200, 300, 400])
        assert result["n_bids"] == 4

    def test_returns_dict_with_required_keys(self):
        """Result dict has all 3 required keys."""
        result = compute_bid_stats([100, 200, 300, 400])
        assert set(result.keys()) == {"curtosis_licitacion", "diferencia_relativa_norm", "n_bids"}


class TestComputeBidStats3Bids:
    """compute_bid_stats with 3 bids: kurtosis=NaN, DRN computed."""

    def test_kurtosis_is_nan(self):
        """Kurtosis is NaN when fewer than 4 bids."""
        result = compute_bid_stats([100, 150, 500])
        assert math.isnan(result["curtosis_licitacion"])

    def test_drn_value(self):
        """DRN for [100, 150, 500] = (150-100)/100 = 0.5."""
        result = compute_bid_stats([100, 150, 500])
        assert abs(result["diferencia_relativa_norm"] - 0.5) < 1e-9

    def test_n_bids(self):
        """n_bids is 3 for 3 valid bids."""
        result = compute_bid_stats([100, 150, 500])
        assert result["n_bids"] == 3


class TestComputeBidStats2Bids:
    """compute_bid_stats with 2 bids: both NaN."""

    def test_kurtosis_is_nan(self):
        result = compute_bid_stats([100, 200])
        assert math.isnan(result["curtosis_licitacion"])

    def test_drn_is_nan(self):
        result = compute_bid_stats([100, 200])
        assert math.isnan(result["diferencia_relativa_norm"])

    def test_n_bids(self):
        result = compute_bid_stats([100, 200])
        assert result["n_bids"] == 2


class TestComputeBidStats1Bid:
    """compute_bid_stats with 1 bid: both NaN, n_bids=1."""

    def test_kurtosis_is_nan(self):
        result = compute_bid_stats([100])
        assert math.isnan(result["curtosis_licitacion"])

    def test_drn_is_nan(self):
        result = compute_bid_stats([100])
        assert math.isnan(result["diferencia_relativa_norm"])

    def test_n_bids(self):
        result = compute_bid_stats([100])
        assert result["n_bids"] == 1


class TestComputeBidStats0Bids:
    """compute_bid_stats with empty list: both NaN, n_bids=0."""

    def test_kurtosis_is_nan(self):
        result = compute_bid_stats([])
        assert math.isnan(result["curtosis_licitacion"])

    def test_drn_is_nan(self):
        result = compute_bid_stats([])
        assert math.isnan(result["diferencia_relativa_norm"])

    def test_n_bids(self):
        result = compute_bid_stats([])
        assert result["n_bids"] == 0


class TestComputeBidStatsLowestZero:
    """Zero and non-positive bids are filtered out before computation.

    Design note: The plan spec says "if lowest bid is 0 or negative: NaN".
    Since the filter step removes all non-positive values (v > 0) before any
    computation, zero values never reach the DRN formula. The division-by-zero
    guard in the code handles an edge case that cannot be triggered by the
    filter — it's a defensive safety net for callers who pass pre-filtered data.

    With the full filter applied:
        [0, 100, 200, 300] -> filters to [100, 200, 300] -> DRN=(200-100)/100=1.0
    """

    def test_zero_bid_is_excluded_from_n_bids(self):
        """Zero bid is filtered out and not counted in n_bids."""
        result = compute_bid_stats([0, 100, 200, 300])
        # 0 is non-positive, filtered; 3 remaining
        assert result["n_bids"] == 3

    def test_drn_uses_remaining_bids_after_zero_filtered(self):
        """DRN is computed from remaining bids after filtering zeros."""
        result = compute_bid_stats([0, 100, 200, 300])
        # After filtering: [100, 200, 300] -> DRN=(200-100)/100 = 1.0
        assert not math.isnan(result["diferencia_relativa_norm"])
        assert abs(result["diferencia_relativa_norm"] - 1.0) < 1e-9

    def test_kurtosis_uses_valid_bids_only_after_zero_filtered(self):
        """Kurtosis uses only positive bids after filtering zero."""
        result = compute_bid_stats([0, 100, 200, 300, 400])
        # 0 filtered; [100, 200, 300, 400] remain — kurtosis is computable
        assert not math.isnan(result["curtosis_licitacion"])
        assert result["n_bids"] == 4

    def test_all_zero_bids_gives_empty_result(self):
        """All-zero bid list results in n_bids=0 and NaN for both stats."""
        result = compute_bid_stats([0, 0, 0, 0])
        assert result["n_bids"] == 0
        assert math.isnan(result["curtosis_licitacion"])
        assert math.isnan(result["diferencia_relativa_norm"])

    def test_negative_bids_are_also_filtered(self):
        """Negative bids (data errors) are excluded from computation."""
        result = compute_bid_stats([-500, 100, 200, 300])
        # -500 filtered; 3 remaining
        assert result["n_bids"] == 3
        assert abs(result["diferencia_relativa_norm"] - 1.0) < 1e-9


class TestComputeBidStatsFiltersNaN:
    """NaN values in bid_values are filtered out before computation."""

    def test_nan_filtered_n_bids(self):
        """n_bids counts only non-NaN bids."""
        result = compute_bid_stats([100, float("nan"), 200, 300, 400])
        assert result["n_bids"] == 4

    def test_kurtosis_computed_without_nan(self):
        """Kurtosis uses only non-NaN bids."""
        result_with_nan = compute_bid_stats([100, float("nan"), 200, 300, 400])
        result_clean = compute_bid_stats([100, 200, 300, 400])
        assert abs(result_with_nan["curtosis_licitacion"] - result_clean["curtosis_licitacion"]) < 1e-9

    def test_drn_computed_without_nan(self):
        """DRN uses only non-NaN bids."""
        result_with_nan = compute_bid_stats([100, float("nan"), 200, 300, 400])
        result_clean = compute_bid_stats([100, 200, 300, 400])
        assert abs(result_with_nan["diferencia_relativa_norm"] - result_clean["diferencia_relativa_norm"]) < 1e-9


class TestComputeBidStatsIdenticalBids:
    """All identical bids: kurtosis=NaN (degenerate), DRN=0.0."""

    def test_kurtosis_is_nan_for_identical(self):
        """scipy.stats.kurtosis returns NaN for identical values (zero variance)."""
        result = compute_bid_stats([100, 100, 100, 100])
        assert math.isnan(result["curtosis_licitacion"])

    def test_drn_is_zero_for_identical(self):
        """DRN = (100-100)/100 = 0.0 for identical bids."""
        result = compute_bid_stats([100, 100, 100, 100])
        assert abs(result["diferencia_relativa_norm"] - 0.0) < 1e-9

    def test_n_bids_for_identical(self):
        """n_bids is 4 for 4 identical bids."""
        result = compute_bid_stats([100, 100, 100, 100])
        assert result["n_bids"] == 4


class TestBuildBidStatsLookupIntegration:
    """build_bid_stats_lookup integrates with mocked load_ofertas."""

    def _make_chunk(self, rows: list[dict]) -> pd.DataFrame:
        """Create a DataFrame chunk from a list of row dicts."""
        return pd.DataFrame(rows)

    def test_basic_lookup_structure(self):
        """Lookup dict has correct keys and stats for mocked ofertas data."""
        chunks = [
            self._make_chunk([
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 100.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 200.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 300.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 400.0},
                {"ID del Proceso de Compra": "PROC-002", "Valor de la Oferta": 500.0},
                {"ID del Proceso de Compra": "PROC-002", "Valor de la Oferta": 600.0},
                {"ID del Proceso de Compra": "PROC-002", "Valor de la Oferta": 700.0},
            ])
        ]

        with patch("sip_engine.classifiers.iric.bid_stats.load_ofertas", return_value=iter(chunks)):
            result = build_bid_stats_lookup()

        assert "PROC-001" in result
        assert "PROC-002" in result
        assert set(result["PROC-001"].keys()) == {
            "curtosis_licitacion", "diferencia_relativa_norm", "n_bids"
        }

    def test_lookup_kurtosis_correct(self):
        """PROC-001 with 4 bids gets correct kurtosis."""
        chunks = [
            self._make_chunk([
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 100.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 200.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 300.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 400.0},
            ])
        ]

        with patch("sip_engine.classifiers.iric.bid_stats.load_ofertas", return_value=iter(chunks)):
            result = build_bid_stats_lookup()

        expected_k = scipy_kurtosis([100, 200, 300, 400], fisher=True, bias=False)
        assert not math.isnan(result["PROC-001"]["curtosis_licitacion"])
        assert abs(result["PROC-001"]["curtosis_licitacion"] - expected_k) < 1e-9

    def test_lookup_drn_correct(self):
        """PROC-001 with bids [100, 150, 500] gets DRN = 0.5."""
        chunks = [
            self._make_chunk([
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 100.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 150.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 500.0},
            ])
        ]

        with patch("sip_engine.classifiers.iric.bid_stats.load_ofertas", return_value=iter(chunks)):
            result = build_bid_stats_lookup()

        assert abs(result["PROC-001"]["diferencia_relativa_norm"] - 0.5) < 1e-9

    def test_process_with_2_bids_gets_nan(self):
        """Process with only 2 bids gets NaN for both stats."""
        chunks = [
            self._make_chunk([
                {"ID del Proceso de Compra": "PROC-TWO", "Valor de la Oferta": 100.0},
                {"ID del Proceso de Compra": "PROC-TWO", "Valor de la Oferta": 200.0},
            ])
        ]

        with patch("sip_engine.classifiers.iric.bid_stats.load_ofertas", return_value=iter(chunks)):
            result = build_bid_stats_lookup()

        assert math.isnan(result["PROC-TWO"]["curtosis_licitacion"])
        assert math.isnan(result["PROC-TWO"]["diferencia_relativa_norm"])
        assert result["PROC-TWO"]["n_bids"] == 2

    def test_skips_nan_bid_values(self):
        """Rows with NaN bid values are not counted in n_bids."""
        chunks = [
            self._make_chunk([
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": float("nan")},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 200.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 300.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 400.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 500.0},
            ])
        ]

        with patch("sip_engine.classifiers.iric.bid_stats.load_ofertas", return_value=iter(chunks)):
            result = build_bid_stats_lookup()

        # NaN bid filtered; 4 valid bids remain
        assert result["PROC-001"]["n_bids"] == 4

    def test_skips_negative_bid_values(self):
        """Rows with non-positive bid values are excluded."""
        chunks = [
            self._make_chunk([
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": -50.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 100.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 200.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 300.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 400.0},
            ])
        ]

        with patch("sip_engine.classifiers.iric.bid_stats.load_ofertas", return_value=iter(chunks)):
            result = build_bid_stats_lookup()

        # -50 filtered; 4 valid bids remain
        assert result["PROC-001"]["n_bids"] == 4

    def test_multiple_chunks_accumulated_correctly(self):
        """Bids across multiple chunks for the same process are merged."""
        chunks = [
            self._make_chunk([
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 100.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 200.0},
            ]),
            self._make_chunk([
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 300.0},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": 400.0},
            ]),
        ]

        with patch("sip_engine.classifiers.iric.bid_stats.load_ofertas", return_value=iter(chunks)):
            result = build_bid_stats_lookup()

        assert result["PROC-001"]["n_bids"] == 4
        # kurtosis should not be NaN (4 bids)
        assert not math.isnan(result["PROC-001"]["curtosis_licitacion"])

    def test_returns_empty_for_no_valid_data(self):
        """Returns empty dict when all bids are NaN/non-positive."""
        chunks = [
            self._make_chunk([
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": float("nan")},
                {"ID del Proceso de Compra": "PROC-001", "Valor de la Oferta": -100.0},
            ])
        ]

        with patch("sip_engine.classifiers.iric.bid_stats.load_ofertas", return_value=iter(chunks)):
            result = build_bid_stats_lookup()

        # No valid bids accumulated — process not in lookup
        assert "PROC-001" not in result
