"""Hardware detection and benchmarking for cross-platform training."""

from sip_engine.shared.hardware.benchmark import benchmark_device
from sip_engine.shared.hardware.detector import HardwareConfig, detect_hardware
from sip_engine.shared.hardware.device import get_xgb_device_kwargs

__all__ = ["HardwareConfig", "detect_hardware", "benchmark_device", "get_xgb_device_kwargs"]
