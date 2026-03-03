"""Cross-platform hardware detection: OS, CPU, RAM, GPU.

Provides HardwareConfig dataclass and detect_hardware() entry point used by
the TUI config screen and training pipeline.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import psutil

logger = logging.getLogger(__name__)

GPU_TYPES = Literal["cuda", "metal", "rocm", "cpu"]


@dataclass(frozen=True)
class HardwareConfig:
    """Immutable snapshot of detected hardware capabilities."""

    os_name: Literal["Windows", "Linux", "Darwin"]
    arch: str
    cpu_cores_physical: int
    cpu_cores_logical: int
    ram_total_gb: float
    ram_available_gb: float
    gpu_type: GPU_TYPES
    gpu_available: bool
    gpu_name: str | None
    gpu_vram_gb: float | None
    is_container: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_container() -> bool:
    """Detect if running inside a container (Docker, Podman, etc.)."""
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
        if "docker" in cgroup or "kubepods" in cgroup or "containerd" in cgroup:
            return True
    except (FileNotFoundError, PermissionError):
        pass
    return False


def _get_available_ram_gb() -> float:
    """Return total RAM in GB, respecting container cgroup limits."""
    # cgroup v2
    cgroup_v2 = Path("/sys/fs/cgroup/memory.max")
    if cgroup_v2.exists():
        try:
            val = cgroup_v2.read_text().strip()
            if val != "max":
                return int(val) / (1024**3)
        except (ValueError, PermissionError):
            pass

    # cgroup v1
    cgroup_v1 = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    if cgroup_v1.exists():
        try:
            val = int(cgroup_v1.read_text().strip())
            # Kernel sets limit to a very large number when uncapped
            host_ram = psutil.virtual_memory().total
            if val < host_ram:
                return val / (1024**3)
        except (ValueError, PermissionError):
            pass

    # Fallback: host RAM via psutil
    return psutil.virtual_memory().total / (1024**3)


def _has_cuda() -> bool:
    """Check for CUDA GPU via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _has_metal() -> bool:
    """Check for Apple Silicon (Metal-capable hardware)."""
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _has_rocm() -> bool:
    """Check for AMD ROCm availability."""
    if os.environ.get("ROCM_HOME"):
        return True
    return Path("/opt/rocm").is_dir()


def _get_gpu_name() -> str | None:
    """Try to get GPU name via pynvml, else nvidia-smi parsing, else None."""
    # Try pynvml first
    try:
        import pynvml  # type: ignore[import-untyped]

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        pynvml.nvmlShutdown()
        return name if isinstance(name, str) else name.decode()
    except Exception:
        pass

    # Fallback: parse nvidia-smi output
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _get_gpu_vram_gb() -> float | None:
    """Try to get GPU VRAM in GB via pynvml, else None."""
    try:
        import pynvml  # type: ignore[import-untyped]

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        pynvml.nvmlShutdown()
        return info.total / (1024**3)
    except Exception:
        return None


def _detect_gpu_type(disable_rocm: bool = False) -> GPU_TYPES:
    """Detect best available GPU type following CUDA > Metal awareness > ROCm > CPU.

    IMPORTANT: Apple Silicon returns 'cpu' because XGBoost has NO Metal/MPS support.
    """
    # 1. CUDA — highest priority
    if _has_cuda():
        logger.info("CUDA GPU detected via nvidia-smi")
        return "cuda"

    # 2. Metal awareness — detect but force CPU for XGBoost
    if _has_metal():
        logger.info(
            "Apple Silicon detected, using CPU (XGBoost has no MPS support)"
        )
        return "cpu"

    # 3. ROCm
    if not disable_rocm and _has_rocm():
        logger.warning(
            "ROCm detected. If training is unstable, use --disable-rocm"
        )
        return "rocm"

    # 4. CPU fallback
    return "cpu"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_hardware(disable_rocm: bool = False) -> HardwareConfig:
    """Auto-detect OS, CPU, RAM, and GPU for the current system.

    Args:
        disable_rocm: If True, skip ROCm detection and fall back to CPU.

    Returns:
        Frozen HardwareConfig with all detected capabilities.
    """
    os_name: Literal["Windows", "Linux", "Darwin"] = platform.system()  # type: ignore[assignment]
    arch = platform.machine()
    physical = psutil.cpu_count(logical=False) or 1
    logical = psutil.cpu_count(logical=True) or physical
    ram_total = _get_available_ram_gb()
    ram_avail = psutil.virtual_memory().available / (1024**3)
    container = _is_container()

    gpu_type = _detect_gpu_type(disable_rocm)

    # Determine GPU metadata
    gpu_available: bool
    gpu_name: str | None
    gpu_vram_gb: float | None

    if gpu_type == "cuda":
        gpu_available = True
        gpu_name = _get_gpu_name()
        gpu_vram_gb = _get_gpu_vram_gb()
    elif gpu_type == "rocm":
        gpu_available = True
        gpu_name = "AMD ROCm GPU"
        gpu_vram_gb = None
    else:
        # cpu — includes Apple Silicon case
        gpu_available = False
        if _has_metal():
            gpu_name = "Apple Silicon (M-series) — XGBoost CPU only"
        else:
            gpu_name = None
        gpu_vram_gb = None

    config = HardwareConfig(
        os_name=os_name,
        arch=arch,
        cpu_cores_physical=physical,
        cpu_cores_logical=logical,
        ram_total_gb=round(ram_total, 2),
        ram_available_gb=round(ram_avail, 2),
        gpu_type=gpu_type,
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram_gb,
        is_container=container,
    )
    logger.info("Hardware detected: %s", config)
    return config
