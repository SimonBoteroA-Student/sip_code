"""Platform compatibility utilities for Windows/Linux/macOS.

Centralises all platform-specific logic so the rest of the codebase never
needs ``if sys.platform == "win32"`` guards.

Exports:
    safe_rename      – Path.rename with retry for Windows file-locking
    count_lines      – wc -l on Unix, pure-Python fallback on Windows
    ensure_utf8_console – Reconfigure stdout/stderr to UTF-8 on Windows
    supports_unicode_blocks – Detect terminal Unicode block char support
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def safe_rename(src: Path, dest: Path, retries: int = 3, delay: float = 0.5) -> None:
    """Rename *src* to *dest* with Windows file-locking retry.

    On Windows, ``Path.rename()`` raises ``FileExistsError`` when the target
    already exists (unlike Unix where it atomically overwrites).  This helper
    deletes the target first, and retries with exponential back-off on
    ``PermissionError`` (caused by antivirus / file-indexer locks).

    On Unix the call is a simple ``src.rename(dest)`` — no extra logic.
    """
    for attempt in range(retries):
        try:
            if sys.platform == "win32" and dest.exists():
                dest.unlink()
            src.rename(dest)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                raise


def count_lines(path: Path) -> int:
    """Count lines in a file.

    On non-Windows systems the fast ``wc -l`` utility is tried first.
    On Windows (or if ``wc`` fails) a pure-Python binary-mode fallback is used.

    Returns 0 on any ``OSError`` so callers (tqdm progress bars) degrade
    gracefully to a spinner.
    """
    if sys.platform != "win32":
        try:
            result = subprocess.run(
                ["wc", "-l", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return int(result.stdout.strip().split()[0])
        except (subprocess.TimeoutExpired, ValueError, IndexError, OSError):
            pass
    # Pure-Python fallback (always used on Windows)
    try:
        with path.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def ensure_utf8_console() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows if needed.

    On non-Windows platforms this is a no-op.  On Windows the default console
    encoding can be cp1252 which breaks Spanish characters and Unicode
    progress symbols.
    """
    if sys.platform != "win32":
        return
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        enc = getattr(stream, "encoding", "") or ""
        if "utf" not in enc.lower():
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, OSError):
                pass


def supports_unicode_blocks() -> bool:
    """Check if the terminal supports Unicode block characters (█/░).

    Returns ``True`` for Windows Terminal (``WT_SESSION`` env var) and any
    terminal whose stdout encoding contains "utf".  Returns ``False``
    otherwise, signalling that callers should use ASCII fallback chars.
    """
    # Windows Terminal always supports Unicode
    if os.environ.get("WT_SESSION"):
        return True
    # Check stdout encoding
    enc = getattr(sys.stdout, "encoding", "") or ""
    if "utf" in enc.lower():
        return True
    return False
