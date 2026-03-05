"""O(1) RCAC lookup by (document_type, document_number).

The RCAC index is loaded lazily on first call to rcac_lookup() and cached
in module-level state. Subsequent calls use the in-memory dict.

Both arguments to rcac_lookup() are normalized internally using the same
normalization functions from rcac_builder — callers do NOT need to
pre-normalize inputs.

Usage:
    from sip_engine.shared.data.rcac_lookup import rcac_lookup
    record = rcac_lookup('CC', '12345678')   # dict or None
    record = rcac_lookup('CC', '12.345.678') # normalizes dots internally
"""

from __future__ import annotations

import logging

import joblib

from sip_engine.shared.config import get_settings
from sip_engine.shared.data.rcac_builder import is_malformed, normalize_numero, normalize_tipo

logger = logging.getLogger(__name__)

# ============================================================
# Module-level state: loaded lazily on first lookup
# ============================================================

_rcac_index: dict | None = None


# ============================================================
# Internal loader
# ============================================================

def _load_rcac() -> dict:
    """Load the RCAC index from disk and cache it in module state.

    Reads `settings.rcac_path` via joblib.load(). Raises FileNotFoundError
    if the pkl file does not exist (i.e., build-rcac has not been run yet).

    Returns:
        dict keyed on (tipo_documento, numero_documento) tuples.

    Raises:
        FileNotFoundError: If rcac.pkl does not exist at settings.rcac_path.
    """
    global _rcac_index
    settings = get_settings()
    rcac_path = settings.rcac_path

    if not rcac_path.exists():
        raise FileNotFoundError(
            f"RCAC index not found at {rcac_path}. "
            "Run `python -m sip_engine build-rcac` to build it first."
        )

    logger.info("Loading RCAC index from %s", rcac_path)
    _rcac_index = joblib.load(rcac_path)
    logger.info("RCAC index loaded — %d records", len(_rcac_index))
    return _rcac_index


# ============================================================
# Public API
# ============================================================

def get_rcac_index() -> dict:
    """Return the in-memory RCAC index, loading it from disk if not yet cached.

    Useful for inspection or bulk access. Individual lookups should use
    rcac_lookup() instead.

    Returns:
        dict keyed on (tipo_documento, numero_documento) tuples.

    Raises:
        FileNotFoundError: If rcac.pkl does not exist.
    """
    if _rcac_index is None:
        return _load_rcac()
    return _rcac_index


def reset_rcac_cache() -> None:
    """Clear the in-memory RCAC index cache.

    After calling this, the next call to rcac_lookup() or get_rcac_index()
    will reload the index from disk. Used in tests to isolate module state
    between test runs.
    """
    global _rcac_index
    _rcac_index = None


def rcac_lookup(tipo_doc: str, num_doc: str) -> dict | None:
    """Look up a (document_type, document_number) identity in the RCAC index.

    Inputs are normalized internally — callers do NOT need to pre-normalize.
    Malformed document numbers (empty, all-zeros, fewer than 3 digits) return
    None immediately without touching the index.

    Args:
        tipo_doc: Raw document type string (e.g. 'CC', 'CEDULA DE CIUDADANIA').
        num_doc: Raw document number string (e.g. '12.345.678', '12345678').

    Returns:
        Full record dict for the identity if found in the RCAC index, or None
        if the identity is unknown, malformed, or the index has no entry for it.

    Example:
        >>> record = rcac_lookup('CC', '43.922.546')
        >>> record is None or isinstance(record, dict)
        True
    """
    tipo = normalize_tipo(tipo_doc)
    num = normalize_numero(num_doc)

    if is_malformed(num):
        return None

    index = get_rcac_index()
    return index.get((tipo, num))
