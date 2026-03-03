"""Quick device benchmark for GPU vs CPU comparison.

Trains a tiny XGBClassifier to measure device throughput so the auto-detect
logic can pick the fastest available device.
"""

from __future__ import annotations

import logging
import platform
import signal
import time

import numpy as np
import xgboost as xgb

from sip_engine.hardware.device import get_xgb_device_kwargs

logger = logging.getLogger(__name__)


class _BenchmarkTimeout(Exception):
    """Raised when benchmark exceeds allowed time."""


def benchmark_device(device_type: str, timeout_sec: int = 10) -> float | None:
    """Benchmark a device by training a tiny XGBClassifier.

    Args:
        device_type: One of 'cuda', 'rocm', 'cpu'.
        timeout_sec: Maximum seconds to allow. Default 10.

    Returns:
        Elapsed seconds (lower = better), or None on timeout/error.
    """
    try:
        # Synthetic dataset: 1000 rows, 10 features, binary target
        rng = np.random.RandomState(42)
        X = rng.randn(1000, 10).astype(np.float32)
        y = rng.randint(0, 2, size=1000)

        kwargs = get_xgb_device_kwargs(device_type)
        model = xgb.XGBClassifier(
            n_estimators=10,
            max_depth=3,
            verbosity=0,
            **kwargs,
        )

        # Timeout handling: signal-based on Unix, threading on Windows
        if platform.system() != "Windows":
            def _alarm_handler(signum, frame):
                raise _BenchmarkTimeout

            old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
            signal.alarm(timeout_sec)
            try:
                start = time.perf_counter()
                model.fit(X, y)
                elapsed = time.perf_counter() - start
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Windows: use ThreadPoolExecutor with timeout
            # (threading.Timer was a no-op — it never interrupted model.fit)
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

            def _run_fit():
                model.fit(X, y)

            with ThreadPoolExecutor(max_workers=1) as executor:
                start = time.perf_counter()
                future = executor.submit(_run_fit)
                try:
                    future.result(timeout=timeout_sec)
                    elapsed = time.perf_counter() - start
                except FuturesTimeoutError:
                    raise _BenchmarkTimeout

        logger.info("Benchmark %s: %.3f seconds", device_type, elapsed)
        return elapsed

    except _BenchmarkTimeout:
        logger.warning("Benchmark %s timed out after %ds", device_type, timeout_sec)
        return None
    except Exception as exc:
        logger.warning("Benchmark %s failed: %s", device_type, exc)
        return None


def select_best_device(candidates: list[str]) -> str:
    """Benchmark each candidate and return the fastest.

    If a GPU candidate is >20% faster than CPU, prefer GPU.
    If all benchmarks fail, return 'cpu'.

    Args:
        candidates: List of device types to benchmark (e.g. ['cuda', 'cpu']).

    Returns:
        Best device type string.
    """
    results: dict[str, float] = {}
    for dev in candidates:
        elapsed = benchmark_device(dev)
        if elapsed is not None:
            results[dev] = elapsed
            logger.info("Device %s benchmark: %.3fs", dev, elapsed)

    if not results:
        logger.warning("All benchmarks failed — defaulting to cpu")
        return "cpu"

    # Find fastest
    fastest = min(results, key=results.get)  # type: ignore[arg-type]

    # If fastest is a GPU, verify it's >20% faster than CPU
    cpu_time = results.get("cpu")
    if fastest != "cpu" and cpu_time is not None:
        gpu_time = results[fastest]
        speedup = (cpu_time - gpu_time) / cpu_time
        if speedup < 0.20:
            logger.info(
                "GPU speedup (%.0f%%) < 20%% threshold — preferring CPU",
                speedup * 100,
            )
            return "cpu"

    return fastest
