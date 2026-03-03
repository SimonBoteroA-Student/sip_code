"""Live training progress display with resource monitoring.

Provides :class:`TrainingProgressDisplay` — a Rich-based live display that
shows an HP search progress bar with ETA, real-time CPU/RAM/GPU stats, and
best-so-far score with trend arrows.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import psutil
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.text import Text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GPU utilization helper
# ---------------------------------------------------------------------------


def _gpu_utilization(device: str) -> str:
    """Return a GPU utilization string, or 'N/A' if unavailable."""
    if device == "cpu":
        return "N/A"
    try:
        import pynvml  # type: ignore[import-untyped]

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        pynvml.nvmlShutdown()
        mem_used_gb = mem.used / (1024**3)
        mem_total_gb = mem.total / (1024**3)
        return f"{util.gpu}%  Mem: {mem_used_gb:.1f}/{mem_total_gb:.1f} GB"
    except Exception:
        return "N/A (pynvml unavailable)"


# ---------------------------------------------------------------------------
# TrainingProgressDisplay
# ---------------------------------------------------------------------------


class TrainingProgressDisplay:
    """Live training progress with resource monitoring.

    Usage::

        display = TrainingProgressDisplay(total_iterations=200)
        display.start()
        for i in range(200):
            # ... training iteration ...
            display.update(iteration=i, best_score=0.85)
        display.stop()

    Also works as context manager::

        with TrainingProgressDisplay(total_iterations=200) as display:
            for i in range(200):
                display.update(iteration=i, best_score=0.85)
    """

    def __init__(
        self,
        total_iterations: int,
        model_id: str = "",
        device: str = "cpu",
        console: Console | None = None,
    ) -> None:
        self.total = total_iterations
        self.model_id = model_id
        self.device = device

        self._best_score: float | None = None
        self._best_iter: int = 0
        self._score_history: list[float] = []
        self._current_iter = 0
        self._start_time: float | None = None

        # Rich components
        self._console = console or Console()
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]HP Search"),
            BarColumn(bar_width=30),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=self._console,
        )
        self._task_id = self._progress.add_task("search", total=total_iterations)
        self._live: Live | None = None

    # -- Lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Start the live display."""
        self._start_time = time.monotonic()
        # Prime psutil's cpu_percent so first non-blocking call has data
        psutil.cpu_percent(interval=None)
        self._live = Live(
            self._build_display(),
            console=self._console,
            refresh_per_second=4,
            screen=False,
        )
        self._live.start()

    def stop(self) -> None:
        """Stop the live display and print final summary."""
        if self._live is not None:
            self._live.stop()
            self._live = None

        elapsed = (
            time.monotonic() - self._start_time if self._start_time else 0
        )
        mins, secs = divmod(int(elapsed), 60)

        self._console.print()
        self._console.print(
            Panel(
                f"  Completed {self._current_iter}/{self.total} iterations in {mins}m{secs:02d}s\n"
                f"  Best score: {self._best_score if self._best_score is not None else 'N/A'}"
                f" (iter {self._best_iter})",
                title="Training Complete",
                border_style="green",
            )
        )

    def update(
        self,
        iteration: int,
        best_score: float | None = None,
    ) -> None:
        """Update progress and resource stats.

        Args:
            iteration: Current iteration index (0-based).
            best_score: Best score found so far. Updated only if higher
                        than the current best.
        """
        self._current_iter = iteration + 1
        self._progress.update(self._task_id, completed=self._current_iter)

        if best_score is not None:
            self._score_history.append(best_score)
            if self._best_score is None or best_score > self._best_score:
                self._best_score = best_score
                self._best_iter = self._current_iter

        if self._live is not None:
            self._live.update(self._build_display())

    # -- Context manager -----------------------------------------------------

    def __enter__(self) -> "TrainingProgressDisplay":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    # -- Trend calculation ---------------------------------------------------

    def _calculate_trend(self) -> str:
        """Calculate score trend from recent history."""
        if len(self._score_history) < 2:
            return ""
        recent = self._score_history[-10:]
        if len(recent) >= 2:
            diff = recent[-1] - recent[0]
            if diff > 0.001:
                return f"↑ improving (+{diff:.4f} last {len(recent)} iters)"
            elif diff < -0.001:
                return f"↓ declining ({diff:.4f} last {len(recent)} iters)"
        return "→ stable"

    # -- Display building ----------------------------------------------------

    def _build_display(self) -> Group:
        """Build the complete live display layout."""
        # Progress panel
        progress_panel = Panel(
            self._progress,
            title="HP Search Progress",
            border_style="blue",
        )

        # Resource panel
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        mem_used_gb = mem.used / (1024**3)
        mem_total_gb = mem.total / (1024**3)
        gpu_line = _gpu_utilization(self.device)

        resource_text = (
            f"  CPU:  {cpu:.1f}%\n"
            f"  RAM:  {mem_used_gb:.1f} GB / {mem_total_gb:.1f} GB ({mem.percent:.1f}%)\n"
            f"  GPU:  {gpu_line}"
        )
        resource_panel = Panel(
            resource_text, title="Resources", border_style="yellow"
        )

        # Best score panel
        if self._best_score is not None:
            trend = self._calculate_trend()
            score_text = (
                f"  Best AUC-ROC: {self._best_score:.4f}  (iter {self._best_iter}/{self.total})"
            )
            if trend:
                score_text += f"\n  Trend: {trend}"
        else:
            score_text = "  Awaiting first score..."

        score_panel = Panel(
            score_text, title="Best Score", border_style="magenta"
        )

        return Group(progress_panel, resource_panel, score_panel)
