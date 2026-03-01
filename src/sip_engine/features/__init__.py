"""Feature engineering module for sip_engine."""

from sip_engine.features.provider_history import (
    build_provider_history_index,
    load_provider_history_index,
    lookup_provider_history,
)
from sip_engine.features.category_a import compute_category_a
from sip_engine.features.category_b import compute_category_b, COLOMBIAN_ELECTION_DATES
from sip_engine.features.category_c import compute_category_c
from sip_engine.features.encoding import (
    build_encoding_mappings,
    apply_encoding,
    load_encoding_mappings,
)

__all__ = [
    "build_provider_history_index",
    "load_provider_history_index",
    "lookup_provider_history",
    "compute_category_a",
    "compute_category_b",
    "COLOMBIAN_ELECTION_DATES",
    "compute_category_c",
    "build_encoding_mappings",
    "apply_encoding",
    "load_encoding_mappings",
]
