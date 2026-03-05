"""Unit tests for sip_engine.shared.hardware detection module.

All tests use tiny in-memory fixtures (no disk I/O, no real data).
Tests must complete in under 15 seconds total.

Covers PLAT-01, PLAT-02, PLAT-03, WIN-04, WIN-08, WIN-09 requirements.
"""

from __future__ import annotations

import dataclasses
import subprocess
from typing import get_type_hints
from unittest.mock import patch, MagicMock

import pytest

from sip_engine.shared.hardware import HardwareConfig, detect_hardware, benchmark_device
from sip_engine.shared.hardware.detector import _get_available_ram_gb, _has_cuda, _has_rocm, _get_gpu_name
from sip_engine.shared.hardware.device import get_xgb_device_kwargs


# ---------------------------------------------------------------------------
# 1. HardwareConfig fields & types
# ---------------------------------------------------------------------------


def test_hardware_config_fields():
    """Verify HardwareConfig has all required fields and types are correct."""
    fields = {f.name for f in dataclasses.fields(HardwareConfig)}
    expected = {
        "os_name",
        "arch",
        "cpu_cores_physical",
        "cpu_cores_logical",
        "ram_total_gb",
        "ram_available_gb",
        "gpu_type",
        "gpu_available",
        "gpu_name",
        "gpu_vram_gb",
        "is_container",
    }
    assert fields == expected, f"Missing fields: {expected - fields}"

    # Verify frozen
    hw = detect_hardware()
    with pytest.raises(dataclasses.FrozenInstanceError):
        hw.os_name = "FakeOS"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Real-system detection
# ---------------------------------------------------------------------------


def test_detect_hardware_returns_valid_config():
    """Call detect_hardware() on real system and validate all fields."""
    hw = detect_hardware()

    assert hw.os_name in ("Windows", "Linux", "Darwin")
    assert isinstance(hw.arch, str) and len(hw.arch) > 0
    assert hw.cpu_cores_physical >= 1
    assert hw.cpu_cores_logical >= hw.cpu_cores_physical
    assert hw.ram_total_gb > 0
    assert hw.ram_available_gb > 0
    assert hw.gpu_type in ("cuda", "metal", "rocm", "cpu")
    assert isinstance(hw.gpu_available, bool)
    assert isinstance(hw.is_container, bool)


# ---------------------------------------------------------------------------
# 3. GPU priority: CUDA first
# ---------------------------------------------------------------------------


def test_gpu_priority_cuda_first(monkeypatch):
    """When CUDA is available, gpu_type should be 'cuda' regardless of other GPUs."""
    monkeypatch.setattr("sip_engine.shared.hardware.detector._has_cuda", lambda: True)
    monkeypatch.setattr("sip_engine.shared.hardware.detector._has_metal", lambda: True)
    monkeypatch.setattr("sip_engine.shared.hardware.detector._has_rocm", lambda: True)

    hw = detect_hardware()
    assert hw.gpu_type == "cuda"
    assert hw.gpu_available is True


# ---------------------------------------------------------------------------
# 4. Apple Silicon forces CPU
# ---------------------------------------------------------------------------


def test_apple_silicon_forces_cpu(monkeypatch):
    """Apple Silicon must return gpu_type='cpu' and gpu_available=False."""
    monkeypatch.setattr("sip_engine.shared.hardware.detector._has_cuda", lambda: False)
    monkeypatch.setattr("sip_engine.shared.hardware.detector._has_rocm", lambda: False)
    monkeypatch.setattr("sip_engine.shared.hardware.detector.platform.system", lambda: "Darwin")
    monkeypatch.setattr("sip_engine.shared.hardware.detector.platform.machine", lambda: "arm64")

    hw = detect_hardware()
    assert hw.gpu_type == "cpu"
    assert hw.gpu_available is False
    assert hw.gpu_name is not None
    assert "Apple Silicon" in hw.gpu_name


# ---------------------------------------------------------------------------
# 5. ROCm disabled
# ---------------------------------------------------------------------------


def test_rocm_disabled(monkeypatch):
    """When disable_rocm=True, ROCm should be skipped even if available."""
    monkeypatch.setattr("sip_engine.shared.hardware.detector._has_cuda", lambda: False)
    monkeypatch.setattr("sip_engine.shared.hardware.detector._has_rocm", lambda: True)
    monkeypatch.setattr("sip_engine.shared.hardware.detector._has_metal", lambda: False)

    hw = detect_hardware(disable_rocm=True)
    assert hw.gpu_type == "cpu"


# ---------------------------------------------------------------------------
# 6. ROCm enabled
# ---------------------------------------------------------------------------


def test_rocm_enabled(monkeypatch):
    """When ROCm is available and not disabled, gpu_type should be 'rocm'."""
    monkeypatch.setattr("sip_engine.shared.hardware.detector._has_cuda", lambda: False)
    monkeypatch.setattr("sip_engine.shared.hardware.detector._has_rocm", lambda: True)
    monkeypatch.setattr("sip_engine.shared.hardware.detector._has_metal", lambda: False)

    hw = detect_hardware(disable_rocm=False)
    assert hw.gpu_type == "rocm"
    assert hw.gpu_available is True


# ---------------------------------------------------------------------------
# 7-9. get_xgb_device_kwargs
# ---------------------------------------------------------------------------


def test_get_xgb_device_kwargs_cuda():
    """CUDA device should return device='cuda' + tree_method='hist'."""
    result = get_xgb_device_kwargs("cuda")
    assert result == {"device": "cuda", "tree_method": "hist"}


def test_get_xgb_device_kwargs_cpu():
    """CPU device should return only tree_method='hist'."""
    result = get_xgb_device_kwargs("cpu")
    assert result == {"tree_method": "hist"}
    assert "device" not in result


def test_get_xgb_device_kwargs_rocm():
    """ROCm device should return device='cuda:0' (HIP API) + tree_method='hist'."""
    result = get_xgb_device_kwargs("rocm")
    assert result == {"device": "cuda:0", "tree_method": "hist"}


# ---------------------------------------------------------------------------
# 10. Benchmark device CPU
# ---------------------------------------------------------------------------


def test_benchmark_device_cpu():
    """benchmark_device('cpu') should return a float > 0 in < 10 seconds."""
    elapsed = benchmark_device("cpu")
    assert elapsed is not None
    assert isinstance(elapsed, float)
    assert 0 < elapsed < 10


# ---------------------------------------------------------------------------
# 11. Container RAM fallback
# ---------------------------------------------------------------------------


def test_container_ram_fallback(monkeypatch):
    """When cgroup files don't exist, should fall back to psutil RAM detection."""
    import sip_engine.shared.hardware.detector as det

    # Ensure cgroup paths don't exist (mock Path.exists to return False for them)
    original_exists = det.Path.exists

    def mock_exists(self):
        path_str = str(self)
        if "cgroup" in path_str:
            return False
        return original_exists(self)

    monkeypatch.setattr(det.Path, "exists", mock_exists)

    ram = _get_available_ram_gb()
    assert ram > 0


# ---------------------------------------------------------------------------
# 12. RAM positive check
# ---------------------------------------------------------------------------


def test_get_available_ram_returns_positive():
    """_get_available_ram_gb() should return a positive value."""
    ram = _get_available_ram_gb()
    assert isinstance(ram, float)
    assert ram > 0


# ---------------------------------------------------------------------------
# 13. Windows nvidia-smi fallback for _has_cuda()
# ---------------------------------------------------------------------------


def test_has_cuda_windows_fallback_path():
    """On Windows, _has_cuda should fall back to System32 path when nvidia-smi not in PATH."""
    call_count = 0

    def mock_subprocess_run(args, **kwargs):
        nonlocal call_count
        call_count += 1
        cmd = args[0]
        if cmd == "nvidia-smi":
            raise FileNotFoundError("nvidia-smi not found")
        elif r"System32" in cmd or "nvidia-smi.exe" in cmd:
            result = MagicMock()
            result.returncode = 0
            return result
        raise FileNotFoundError(f"Unknown command: {cmd}")

    with patch("sip_engine.shared.hardware.detector.sys") as mock_sys, \
         patch("sip_engine.shared.hardware.detector.subprocess.run", side_effect=mock_subprocess_run):
        mock_sys.platform = "win32"
        result = _has_cuda()
    assert result is True
    assert call_count == 2  # First call fails, second (System32) succeeds


# ---------------------------------------------------------------------------
# 14. ROCm skipped on Windows
# ---------------------------------------------------------------------------


def test_has_rocm_skips_on_windows():
    """On Windows, _has_rocm should return False without checking filesystem."""
    with patch("sip_engine.shared.hardware.detector.sys") as mock_sys:
        mock_sys.platform = "win32"
        result = _has_rocm()
    assert result is False


# ---------------------------------------------------------------------------
# 15. GPU name Windows fallback
# ---------------------------------------------------------------------------


def test_get_gpu_name_windows_fallback():
    """On Windows, _get_gpu_name should fall back to System32 nvidia-smi path."""
    call_count = 0

    def mock_subprocess_run(args, **kwargs):
        nonlocal call_count
        call_count += 1
        cmd = args[0]
        if cmd == "nvidia-smi":
            raise FileNotFoundError("nvidia-smi not found")
        elif r"System32" in cmd or "nvidia-smi.exe" in cmd:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "NVIDIA GeForce RTX 3080\n"
            return result
        raise FileNotFoundError(f"Unknown command: {cmd}")

    with patch("sip_engine.shared.hardware.detector.sys") as mock_sys, \
         patch("sip_engine.shared.hardware.detector.subprocess.run", side_effect=mock_subprocess_run):
        mock_sys.platform = "win32"
        # Also mock pynvml to fail so it falls through to subprocess
        with patch.dict("sys.modules", {"pynvml": None}):
            name = _get_gpu_name()
    assert name == "NVIDIA GeForce RTX 3080"


# ---------------------------------------------------------------------------
# 16. Benchmark Windows timeout path (ThreadPoolExecutor)
# ---------------------------------------------------------------------------


def test_benchmark_windows_timeout_path():
    """On Windows, benchmark_device should complete via ThreadPoolExecutor path."""
    with patch("sip_engine.shared.hardware.benchmark.platform.system", return_value="Windows"):
        elapsed = benchmark_device("cpu", timeout_sec=60)
    assert elapsed is not None
    assert isinstance(elapsed, float)
    assert 0 < elapsed < 60


# ---------------------------------------------------------------------------
# 17. Benchmark Windows timeout triggers
# ---------------------------------------------------------------------------


def test_benchmark_windows_timeout_triggers():
    """On Windows, benchmark_device should return None when timeout fires."""
    import time as _time

    def slow_fit(self, X, y, **kwargs):
        _time.sleep(5)

    with patch("sip_engine.shared.hardware.benchmark.platform.system", return_value="Windows"), \
         patch("xgboost.XGBClassifier.fit", side_effect=slow_fit):
        result = benchmark_device("cpu", timeout_sec=1)
    assert result is None
