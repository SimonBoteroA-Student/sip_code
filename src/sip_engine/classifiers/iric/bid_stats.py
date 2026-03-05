"""Bid distribution anomaly statistics for IRIC (IRIC-04, IRIC-05).

Computes kurtosis and normalized relative difference (DRN) from bid values
at the procurement process level, following Imhof (2018) methodology for
detecting bid-rigging patterns through distribution shape analysis.

These statistics are computed from `ofertas_proceso_SECOP.csv` via streaming
and stored in the IRIC result artifact. They are NOT included in the XGBoost
feature vector (FEATURE_COLUMNS) because they are NaN-heavy due to the ~60%
share of direct contracting contracts which have 0 or 1 bids.
"""

from __future__ import annotations

import logging
import math

from scipy.stats import kurtosis as scipy_kurtosis

from sip_engine.shared.data.loaders import load_ofertas

logger = logging.getLogger(__name__)


def compute_bid_stats(bid_values: list[float]) -> dict:
    """Compute kurtosis and DRN for a single procurement process's bid amounts.

    Filters out NaN and non-positive values before any computation. Both
    statistics have minimum bid count requirements — they return NaN when not
    enough valid bids are present.

    Kurtosis formula (Fisher excess kurtosis, unbiased):
        K = [n(n+1)/((n-1)(n-2)(n-3))] * sum((xi - x_mean)/s)^4
            - 3(n-1)^2/((n-2)(n-3))
        Implemented via scipy.stats.kurtosis(bids, fisher=True, bias=False).
        Requires n >= 4.

    DRN formula (Imhof 2018):
        DRN = (second_lowest - lowest) / lowest
        This measures the relative gap between the two cheapest bids.
        Tight clustering (DRN near 0) suggests bid rigging.
        Requires n >= 3, and lowest bid > 0 (division by zero guard).

    Args:
        bid_values: List of raw bid amounts for a single process.
            NaN and non-positive values are filtered out internally.

    Returns:
        Dict with keys:
            - curtosis_licitacion (float|NaN): Unbiased excess kurtosis.
              NaN if fewer than 4 valid bids.
            - diferencia_relativa_norm (float|NaN): DRN per Imhof (2018).
              NaN if fewer than 3 valid bids or if lowest bid is 0/negative.
            - n_bids (int): Count of valid (positive, non-NaN) bids used.
    """
    # Filter out NaN and non-positive values
    valid_bids = [
        v for v in bid_values
        if v is not None and not (isinstance(v, float) and math.isnan(v)) and v > 0
    ]
    n_bids = len(valid_bids)

    # --- Kurtosis (IRIC-04): requires n >= 4 ---
    if n_bids >= 4:
        k_value = scipy_kurtosis(valid_bids, fisher=True, bias=False)
        # scipy may return nan for degenerate cases (all identical values)
        curtosis = float(k_value)  # converts np.float64 to Python float
    else:
        curtosis = float("nan")

    # --- DRN (IRIC-05): requires n >= 3 ---
    # DRN = (second_lowest - lowest) / lowest per Imhof (2018)
    # Measures relative gap between two cheapest bids;
    # tight clustering near 0 suggests bid rigging collusion.
    if n_bids >= 3:
        sorted_bids = sorted(valid_bids)
        lowest = sorted_bids[0]
        second_lowest = sorted_bids[1]
        if lowest <= 0:
            # Division by zero guard — should not happen after positive filter
            # but included as a defensive check
            drn = float("nan")
        else:
            drn = (second_lowest - lowest) / lowest
    else:
        drn = float("nan")

    return {
        "curtosis_licitacion": curtosis,
        "diferencia_relativa_norm": drn,
        "n_bids": n_bids,
    }


def build_bid_stats_lookup() -> dict[str, dict]:
    """Stream ofertas CSV and compute per-process bid statistics.

    Accumulates bid values per process ID by streaming the full
    `ofertas_proceso_SECOP.csv` file (~9.7M rows, 3.4 GB). Only bid values
    are kept in memory during streaming — raw row dicts are discarded.
    After streaming, `compute_bid_stats()` is called for each unique process.

    Memory strategy: The intermediate structure is a dict mapping process ID
    to a list of float bid values. After stats are computed for a process,
    the raw bid list is discarded. The final result dict (one entry per unique
    process with 3 scalar values) is much smaller than the raw data.

    Rows where `Valor de la Oferta` is NaN or non-positive are skipped during
    accumulation.

    Returns:
        Dict mapping `ID del Proceso de Compra` -> bid stats dict:
            {
                proceso_id: {
                    "curtosis_licitacion": float|NaN,
                    "diferencia_relativa_norm": float|NaN,
                    "n_bids": int,
                }
            }
    """
    # Accumulate bid values per process (streaming — minimal memory footprint)
    proceso_bids: dict[str, list[float]] = {}
    total_rows = 0
    skipped_rows = 0

    logger.info("Building bid stats lookup from ofertas — streaming pass")

    for chunk in load_ofertas():
        for _, row in chunk.iterrows():
            total_rows += 1
            proceso_id = row.get("ID del Proceso de Compra")
            bid_value = row.get("Valor de la Oferta")

            # Skip rows with missing process ID
            if proceso_id is None or (isinstance(proceso_id, float) and math.isnan(proceso_id)):
                skipped_rows += 1
                continue

            # Skip rows with missing or non-positive bid value
            if bid_value is None:
                skipped_rows += 1
                continue
            try:
                bid_float = float(bid_value)
            except (TypeError, ValueError):
                skipped_rows += 1
                continue
            if math.isnan(bid_float) or bid_float <= 0:
                skipped_rows += 1
                continue

            # Accumulate bid value for this process
            if proceso_id not in proceso_bids:
                proceso_bids[proceso_id] = []
            proceso_bids[proceso_id].append(bid_float)

    total_processes = len(proceso_bids)
    total_valid_bids = sum(len(v) for v in proceso_bids.values())

    logger.info(
        "Ofertas streaming complete: %d rows processed, %d rows skipped, "
        "%d unique processes found, %d valid bids accumulated",
        total_rows,
        skipped_rows,
        total_processes,
        total_valid_bids,
    )

    # Compute stats for each process, discard raw bid lists
    lookup: dict[str, dict] = {}
    for proceso_id, bids in proceso_bids.items():
        lookup[proceso_id] = compute_bid_stats(bids)

    logger.info("Bid stats lookup built: %d process entries", len(lookup))

    return lookup
