"""Memory monitoring, adaptive chunk sizing, checkpoint utilities, and lifecycle helpers.

HW-01: RAM budget enforcement — MemoryMonitor enforces max_ram_gb as hard ceiling.
HW-02: Adaptive chunk sizing — dynamic chunk reduction at memory pressure thresholds.
HW-08: Multiprocessing support — pool initializer pattern for cross-platform worker pools.
"""

from __future__ import annotations

import gc
import logging
import os
import pickle
import tempfile
from multiprocessing import Pool
from pathlib import Path

import pandas as pd
import psutil

from sip_engine.compat import safe_rename

logger = logging.getLogger(__name__)


# ============================================================
# MemoryMonitor
# ============================================================


class MemoryMonitor:
    """Track process RSS memory usage against a configurable RAM budget.

    Args:
        max_ram_gb: The RAM budget in gigabytes (hard ceiling).
    """

    def __init__(self, max_ram_gb: int) -> None:
        self.budget_bytes = max_ram_gb * (1024 ** 3)

    def current_usage_bytes(self) -> int:
        """Return current process RSS in bytes via psutil."""
        return psutil.Process().memory_info().rss

    def usage_ratio(self) -> float:
        """Return current RSS / budget as a ratio (1.0 = 100% of budget)."""
        return self.current_usage_bytes() / self.budget_bytes

    def check(self) -> str:
        """Return memory pressure status.

        Returns:
            ``'ok'`` if usage < 90% of budget,
            ``'warning'`` if 90% <= usage < 100%,
            ``'critical'`` if usage >= 100%.
        """
        ratio = self.usage_ratio()
        if ratio >= 1.0:
            return "critical"
        if ratio >= 0.9:
            return "warning"
        return "ok"


# ============================================================
# Adaptive chunk sizing
# ============================================================


def adaptive_chunk_size(
    monitor: MemoryMonitor,
    base_chunk_size: int,
    min_chunk_size: int = 1000,
) -> int:
    """Return an adjusted chunk size based on current memory pressure.

    - ``ok``: return ``base_chunk_size`` unchanged.
    - ``warning``: return ``max(base_chunk_size // 2, min_chunk_size)``.
    - ``critical``: return ``min_chunk_size``.

    Args:
        monitor: A :class:`MemoryMonitor` instance.
        base_chunk_size: The nominal chunk size to start from.
        min_chunk_size: The absolute minimum chunk size allowed.

    Returns:
        Adjusted chunk size (integer).
    """
    status = monitor.check()
    if status == "critical":
        return min_chunk_size
    if status == "warning":
        return max(base_chunk_size // 2, min_chunk_size)
    return base_chunk_size


# ============================================================
# Checkpoint utilities
# ============================================================


def save_checkpoint(rows: list[dict], checkpoint_path: Path) -> None:
    """Write *rows* to a temp Parquet file, then atomically rename to *checkpoint_path*.

    Uses :func:`~sip_engine.compat.safe_rename` for Windows-safe atomic replace.

    Args:
        rows: List of dicts to persist as a Parquet checkpoint.
        checkpoint_path: Final destination path for the checkpoint file.
    """
    tmp_path = checkpoint_path.with_suffix(".tmp.parquet")
    df = pd.DataFrame(rows)
    df.to_parquet(tmp_path, index=False)
    safe_rename(tmp_path, checkpoint_path)
    logger.debug("Checkpoint saved: %s (%d rows)", checkpoint_path, len(rows))


def load_checkpoint(checkpoint_path: Path) -> tuple[pd.DataFrame, set]:
    """Load a checkpoint Parquet file.

    Args:
        checkpoint_path: Path to the checkpoint Parquet file.

    Returns:
        A tuple of ``(df, processed_ids)`` where ``processed_ids`` is the
        ``set`` of values from the ``'id_contrato'`` column for skip-based
        resume.  Returns ``(empty_df, empty_set)`` if the file does not exist.
    """
    if not checkpoint_path.exists():
        return pd.DataFrame(), set()

    df = pd.read_parquet(checkpoint_path)
    processed_ids: set = set()
    if "id_contrato" in df.columns:
        processed_ids = set(df["id_contrato"].dropna().tolist())
    logger.debug("Checkpoint loaded: %s (%d rows)", checkpoint_path, len(df))
    return df, processed_ids


def remove_checkpoint(checkpoint_path: Path) -> None:
    """Delete *checkpoint_path* if it exists.

    Args:
        checkpoint_path: Path to the checkpoint file to remove.
    """
    if checkpoint_path.exists():
        checkpoint_path.unlink()
        logger.debug("Checkpoint removed: %s", checkpoint_path)


# ============================================================
# Lifecycle cleanup helper
# ============================================================


def cleanup(*objects) -> None:  # noqa: ANN002
    """Delete each object reference and force a garbage collection pass.

    Usage::

        cleanup(large_df, another_df)

    Args:
        *objects: Objects to dereference.  The names passed here are local
            variable references; callers should also ``del`` their own
            bindings if needed.
    """
    for obj in objects:
        del obj
    gc.collect()


# ============================================================
# Multiprocessing pool utilities (HW-08)
# ============================================================

# Module-level dict populated by _init_worker in each worker process.
_shared_lookups: dict = {}


def _init_worker(lookups_path: str) -> None:
    """Pool initializer: load serialized lookups into module-global dict.

    Called once per worker process at pool creation time.  Works on both
    *fork* (macOS/Linux) and *spawn* (Windows) start methods because the
    data is always deserialized from the temp pickle file.

    Args:
        lookups_path: Path to the temp pickle file written by
            :func:`serialize_lookups`.
    """
    global _shared_lookups
    with open(lookups_path, "rb") as f:
        _shared_lookups = pickle.load(f)


def serialize_lookups(lookups: dict, tmp_dir: str | None = None) -> str:
    """Serialize lookup dicts to a temp pickle file and return the file path.

    The caller is responsible for cleanup (delete the file after the pool
    is done).

    Args:
        lookups: Dict of lookup structures to serialize.
        tmp_dir: Optional directory for the temp file.  Defaults to the
            system temp directory.

    Returns:
        Absolute path to the temp pickle file (str).
    """
    fd, path = tempfile.mkstemp(suffix=".pkl", dir=tmp_dir)
    with os.fdopen(fd, "wb") as f:
        pickle.dump(lookups, f, protocol=pickle.HIGHEST_PROTOCOL)
    return path


def get_shared_lookups() -> dict:
    """Return the module-global shared lookups dict (populated by pool initializer).

    Returns:
        The ``_shared_lookups`` dict set by :func:`_init_worker`, or an empty
        dict if called outside a worker context.
    """
    return _shared_lookups


def create_worker_pool(n_jobs: int, lookups: dict) -> tuple[Pool | None, str]:
    """Create a multiprocessing Pool with shared lookups.

    Serializes *lookups* to a temp pickle file and creates a
    :class:`multiprocessing.Pool` with :func:`_init_worker` as the
    initializer so each worker loads the lookups once at startup.

    Cross-platform: works identically on fork (macOS/Linux) and spawn
    (Windows) because workers always deserialize from the pickle file.

    Args:
        n_jobs: Number of worker processes.  If ``<= 1``, returns
            ``(None, '')`` — caller should use the single-process path.
        lookups: Dict of lookup structures to share with workers.

    Returns:
        Tuple of ``(pool, temp_pickle_path)``.  Caller must call
        ``pool.close()`` / ``pool.join()`` and delete the temp file when done.
        Returns ``(None, '')`` when ``n_jobs <= 1``.
    """
    if n_jobs <= 1:
        return None, ""
    lookups_path = serialize_lookups(lookups)
    pool = Pool(n_jobs, initializer=_init_worker, initargs=(lookups_path,))
    return pool, lookups_path
