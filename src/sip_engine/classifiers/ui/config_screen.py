"""Interactive pre-training configuration screen with hardware display and sliders.

Shows detected hardware in a rich Panel, then presents interactive sliders for
training parameters (CPU cores, HP iterations, CV folds, device).  Falls back
to defaults in non-interactive environments (piped stdin / CI).
"""

from __future__ import annotations

import logging
import platform
import sys
from typing import Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from sip_engine.shared.hardware import HardwareConfig
from sip_engine.compat import supports_unicode_blocks

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slider widget
# ---------------------------------------------------------------------------

# Unicode block chars and ASCII fallbacks for slider rendering
_FILLED_UNICODE = "█"
_EMPTY_UNICODE = "░"
_FILLED_ASCII = "#"
_EMPTY_ASCII = "."


def _get_bar_chars() -> tuple[str, str]:
    """Return (filled, empty) bar characters based on terminal support."""
    if supports_unicode_blocks():
        return _FILLED_UNICODE, _EMPTY_UNICODE
    return _FILLED_ASCII, _EMPTY_ASCII


_BAR_WIDTH = 20


class _SliderWidget:
    """Simple terminal slider: ``param: [████████░░░░] 6 / 12``."""

    def __init__(
        self,
        name: str,
        min_val: int,
        max_val: int,
        current: int,
        step: int = 1,
    ) -> None:
        self.name = name
        self.min_val = min_val
        self.max_val = max_val
        self.current = self._clamp(current)
        self.step = step
        # Buffer for direct-number entry
        self._number_buf: str = ""
        # Resolve bar characters once at creation time
        self._filled, self._empty = _get_bar_chars()

    # -- value helpers -------------------------------------------------------

    def _clamp(self, v: int) -> int:
        return max(self.min_val, min(self.max_val, v))

    def increment(self) -> None:
        self._number_buf = ""
        self.current = self._clamp(self.current + self.step)

    def decrement(self) -> None:
        self._number_buf = ""
        self.current = self._clamp(self.current - self.step)

    def add_digit(self, digit: str) -> None:
        """Append a digit to the direct-entry buffer and update value."""
        self._number_buf += digit
        try:
            self.current = self._clamp(int(self._number_buf))
        except ValueError:
            self._number_buf = ""

    def clear_number_buf(self) -> None:
        self._number_buf = ""

    # -- rendering -----------------------------------------------------------

    def render(self, selected: bool = False) -> Text:
        ratio = (
            (self.current - self.min_val) / max(1, self.max_val - self.min_val)
        )
        filled = int(ratio * _BAR_WIDTH)
        empty = _BAR_WIDTH - filled
        bar = f"[{self._filled * filled}{self._empty * empty}]"
        label = f"  {self.name + ':':<16s} {bar} {self.current} / {self.max_val}"
        style = "bold cyan" if selected else ""
        prefix = "▸ " if selected else "  "
        return Text(prefix + label, style=style)


class _DeviceSelector:
    """Cycle selector for device strings (cpu / cuda / rocm)."""

    def __init__(self, options: list[str], current: str) -> None:
        self.options = options
        self._idx = options.index(current) if current in options else 0

    @property
    def current(self) -> str:
        return self.options[self._idx]

    def next_option(self) -> None:
        self._idx = (self._idx + 1) % len(self.options)

    def prev_option(self) -> None:
        self._idx = (self._idx - 1) % len(self.options)

    def render(self, selected: bool = False) -> Text:
        display = " | ".join(
            f"[{o}]" if o == self.current else o for o in self.options
        )
        label = f"  {'Device:':<16s} {display}"
        style = "bold cyan" if selected else ""
        prefix = "▸ " if selected else "  "
        return Text(prefix + label, style=style)


# ---------------------------------------------------------------------------
# Keyboard input helpers (cross-platform)
# ---------------------------------------------------------------------------

_KEY_UP = "UP"
_KEY_DOWN = "DOWN"
_KEY_LEFT = "LEFT"
_KEY_RIGHT = "RIGHT"
_KEY_ENTER = "ENTER"
_KEY_QUIT = "QUIT"


def _read_key_unix() -> str:
    """Read a single keypress on Unix using termios/tty."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            mapping = {"[A": _KEY_UP, "[B": _KEY_DOWN, "[C": _KEY_RIGHT, "[D": _KEY_LEFT}
            return mapping.get(seq, "")
        if ch in ("\r", "\n"):
            return _KEY_ENTER
        if ch in ("q", "\x03"):  # q or Ctrl-C
            return _KEY_QUIT
        if ch.isdigit():
            return ch
        return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_key_win() -> str:
    """Read a single keypress on Windows using msvcrt."""
    import msvcrt  # type: ignore[import-not-found]

    ch = msvcrt.getwch()
    if ch in ("\r", "\n"):
        return _KEY_ENTER
    if ch in ("q", "\x03"):
        return _KEY_QUIT
    if ch == "\xe0" or ch == "\x00":
        ch2 = msvcrt.getwch()
        mapping = {"H": _KEY_UP, "P": _KEY_DOWN, "M": _KEY_RIGHT, "K": _KEY_LEFT}
        return mapping.get(ch2, "")
    if ch.isdigit():
        return ch
    return ""


def _read_key() -> str:
    if sys.platform == "win32":
        return _read_key_win()
    return _read_key_unix()


# ---------------------------------------------------------------------------
# Hardware info panel
# ---------------------------------------------------------------------------

def _build_hardware_panel(hw: HardwareConfig) -> Panel:
    """Build the read-only hardware info panel."""
    os_display = {
        "Darwin": "macOS",
        "Linux": "Linux",
        "Windows": "Windows",
    }.get(hw.os_name, hw.os_name)

    gpu_line = hw.gpu_type
    if hw.gpu_name:
        gpu_line = f"{hw.gpu_type} ({hw.gpu_name})"

    lines = [
        f"  OS:          {os_display} ({hw.arch})",
        f"  CPU:         {hw.cpu_cores_physical} physical / {hw.cpu_cores_logical} logical cores",
        f"  RAM:         {hw.ram_total_gb:.1f} GB ({hw.ram_available_gb:.1f} GB available)",
        f"  GPU:         {gpu_line}",
        f"  Container:   {'Yes' if hw.is_container else 'No'}",
    ]
    return Panel("\n".join(lines), title="Detected Hardware", border_style="green")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def show_config_screen(
    hw_config: HardwareConfig,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Display interactive pre-training configuration screen.

    Args:
        hw_config: Detected hardware configuration.
        defaults: Optional overrides for default slider values.

    Returns:
        Dict with keys ``n_jobs``, ``n_iter``, ``cv_folds``, ``device``.
    """
    # Determine available devices
    available_devices: list[str] = ["cpu"]
    if hw_config.gpu_type == "cuda":
        available_devices.append("cuda")
    if hw_config.gpu_type == "rocm":
        available_devices.append("rocm")

    default_device = hw_config.gpu_type if hw_config.gpu_available else "cpu"

    # Merge with caller-supplied defaults
    ram_max_gb = max(1, int(hw_config.ram_available_gb))
    d = {
        "n_jobs": hw_config.cpu_cores_physical,
        "n_iter": 200,
        "cv_folds": 5,
        "device": default_device,
        "max_ram_gb": ram_max_gb,
    }
    if defaults:
        d.update(defaults)

    # Non-interactive fallback (piped stdin / CI)
    if not sys.stdin.isatty():
        logger.info("Non-interactive terminal — using default settings")
        return {
            "n_jobs": d["n_jobs"],
            "n_iter": d["n_iter"],
            "cv_folds": d["cv_folds"],
            "device": d["device"],
            "max_ram_gb": d["max_ram_gb"],
        }

    # Build widgets
    sliders: list[_SliderWidget | _DeviceSelector] = [
        _SliderWidget("CPU cores", 1, hw_config.cpu_cores_logical, d["n_jobs"]),
        _SliderWidget("HP iterations", 20, 500, d["n_iter"], step=10),
        _SliderWidget("CV folds", 3, 10, d["cv_folds"]),
        _SliderWidget("RAM limit (GB)", 1, max(1, int(hw_config.ram_total_gb)), d["max_ram_gb"]),
        _DeviceSelector(available_devices, d["device"]),
    ]

    selected = 0
    console = Console()

    def _make_layout() -> Layout:
        hw_panel = _build_hardware_panel(hw_config)

        lines: list[Text] = []
        header = Text(
            "  Training Configuration (↑↓ select, ←→ adjust, type number, Enter to confirm)\n",
            style="bold",
        )
        lines.append(header)
        for i, widget in enumerate(sliders):
            lines.append(widget.render(selected=i == selected))

        footer = Text("\n  [Enter] Start training    [q] Quit")
        lines.append(footer)

        config_group = Text()
        for ln in lines:
            config_group.append_text(ln)
            config_group.append("\n")

        config_panel = Panel(config_group, title="Training Settings", border_style="blue")

        layout = Layout()
        layout.split_column(
            Layout(hw_panel, name="hardware", size=8),
            Layout(config_panel, name="config", size=13),
        )
        return layout

    try:
        with Live(_make_layout(), console=console, refresh_per_second=10, screen=False) as live:
            while True:
                key = _read_key()
                if key == _KEY_ENTER:
                    break
                if key == _KEY_QUIT:
                    raise KeyboardInterrupt("User quit config screen")
                if key == _KEY_UP:
                    selected = max(0, selected - 1)
                elif key == _KEY_DOWN:
                    selected = min(len(sliders) - 1, selected + 1)
                elif key == _KEY_RIGHT:
                    w = sliders[selected]
                    if isinstance(w, _SliderWidget):
                        w.increment()
                    else:
                        w.next_option()
                elif key == _KEY_LEFT:
                    w = sliders[selected]
                    if isinstance(w, _SliderWidget):
                        w.decrement()
                    else:
                        w.prev_option()
                elif key.isdigit():
                    w = sliders[selected]
                    if isinstance(w, _SliderWidget):
                        w.add_digit(key)

                live.update(_make_layout())
    except KeyboardInterrupt:
        console.print("[yellow]Training cancelled.[/yellow]")
        raise

    # Collect results
    cores_slider: _SliderWidget = sliders[0]  # type: ignore[assignment]
    iter_slider: _SliderWidget = sliders[1]  # type: ignore[assignment]
    cv_slider: _SliderWidget = sliders[2]  # type: ignore[assignment]
    ram_slider: _SliderWidget = sliders[3]  # type: ignore[assignment]
    device_sel: _DeviceSelector = sliders[4]  # type: ignore[assignment]

    return {
        "n_jobs": cores_slider.current,
        "n_iter": iter_slider.current,
        "cv_folds": cv_slider.current,
        "max_ram_gb": ram_slider.current,
        "device": device_sel.current,
    }
