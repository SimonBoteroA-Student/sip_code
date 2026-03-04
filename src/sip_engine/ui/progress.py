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
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom ETA column
# ---------------------------------------------------------------------------


class _ETAColumn(ProgressColumn):
    """ETA column using elapsed/progress linear interpolation.

    More stable than speed-based ETA because it uses total elapsed time
    divided by fraction done to project remaining time.
    """

    def render(self, task: Any) -> Text:  # type: ignore[override]
        completed = task.completed
        total = task.total
        elapsed: float = task.elapsed or 0.0
        if elapsed <= 0.0 or completed <= 0 or total is None or total <= 0:
            return Text("eta: --:--", style="progress.remaining")
        pct = completed / total
        if pct >= 1.0:
            return Text("eta: 0:00", style="progress.remaining")
        eta_sec = int((elapsed / pct) * (1.0 - pct))
        h, rem = divmod(eta_sec, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return Text(f"eta: {h}:{m:02d}:{s:02d}", style="progress.remaining")
        return Text(f"eta: {m}:{s:02d}", style="progress.remaining")
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
        show_stats: bool = False,
    ) -> None:
        self.total = total_iterations
        self.model_id = model_id
        self.device = device
        self.show_stats = show_stats

        self._best_score: float | None = None
        self._best_iter: int = 0
        self._score_history: list[float] = []
        self._current_iter = 0
        self._start_time: float | None = None

        self._best_score_std: float | None = None

        # Extra test-set stats (show_stats mode)
        self._stats_map100: float | None = None
        self._stats_map500: float | None = None
        self._stats_brier: float | None = None
        self._stats_precision: float | None = None
        self._stats_recall: float | None = None
        self._stats_f1: float | None = None
        self._stats_threshold: float | None = None
        self._stats_fpr: list[float] | None = None
        self._stats_tpr: list[float] | None = None
        self._stats_recall100: float | None = None
        self._stats_recall500: float | None = None
        self._stats_prec100: float | None = None
        self._stats_prec500: float | None = None

        # Rich components
        self._console = console or Console()
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]HP Search"),
            BarColumn(bar_width=30),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("elapsed:"),
            TimeElapsedColumn(),
            _ETAColumn(),
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
        best_score_std: float | None = None,
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
                self._best_score_std = best_score_std

        if self._live is not None:
            self._live.update(self._build_display())

    # -- Context manager -----------------------------------------------------

    def __enter__(self) -> "TrainingProgressDisplay":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    # -- Extra stats update (show_stats mode) --------------------------------

    def update_stats(
        self,
        map100: float,
        map500: float,
        brier: float,
        precision: float,
        recall: float,
        f1: float,
        threshold: float,
        fpr: list[float],
        tpr: list[float],
        recall100: float = 0.0,
        recall500: float = 0.0,
        prec100: float = 0.0,
        prec500: float = 0.0,
    ) -> None:
        """Update live test-set evaluation stats (only used when show_stats=True)."""
        self._stats_map100 = map100
        self._stats_map500 = map500
        self._stats_brier = brier
        self._stats_precision = precision
        self._stats_recall = recall
        self._stats_f1 = f1
        self._stats_threshold = threshold
        self._stats_fpr = fpr
        self._stats_tpr = tpr
        self._stats_recall100 = recall100
        self._stats_recall500 = recall500
        self._stats_prec100 = prec100
        self._stats_prec500 = prec500
        if self._live is not None:
            self._live.update(self._build_display())

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

    # -- AUC quality helpers -------------------------------------------------

    @staticmethod
    def _auc_color(auc: float) -> str:
        """Return Rich color for AUC quality band."""
        if auc >= 0.92:
            return "bold bright_green"
        elif auc >= 0.83:
            return "green"
        elif auc >= 0.7:
            return "dark_orange"
        return "red"

    @staticmethod
    def _auc_label(auc: float) -> str:
        """Return quality label for AUC band."""
        if auc >= 0.85:
            return "Excellent"
        elif auc >= 0.75:
            return "Good"
        elif auc >= 0.65:
            return "Fair"
        return "Poor"

    @staticmethod
    def _brier_label(brier: float) -> str:
        """Return quality label for Brier score band (lower is better)."""
        if brier < 0.05:
            return "Excellent"
        elif brier < 0.1:
            return "Good"
        return "Poor"

    @staticmethod
    def _sparkline(values: list[float], width: int = 30) -> str:
        """Build a Unicode sparkline from a list of float values."""
        blocks = "▁▂▃▄▅▆▇█"
        if not values:
            return ""
        sample = values[-width:] if len(values) > width else values
        lo, hi = min(sample), max(sample)
        span = hi - lo or 1e-9
        return "".join(blocks[min(7, int((v - lo) / span * 8))] for v in sample)

    @staticmethod
    def _render_ascii_roc(
        fpr_list: list[float],
        tpr_list: list[float],
        width: int = 36,
        height: int = 7,
    ) -> str:
        """Render a compact ASCII ROC curve. Returns a multi-line string."""
        grid: list[list[str]] = [[" "] * width for _ in range(height)]
        # Downsample so we don't draw too many overlapping dots
        step = max(1, len(fpr_list) // (width * height))
        for f, t in zip(fpr_list[::step], tpr_list[::step]):
            col = min(width - 1, round(f * (width - 1)))
            row = height - 1 - min(height - 1, round(t * (height - 1)))
            grid[row][col] = "●"
        lines: list[str] = []
        for i, row in enumerate(grid):
            tpr_val = 1.0 - i / max(height - 1, 1)
            lines.append(f"  {tpr_val:.1f}│{''.join(row)}")
        lines.append("     └" + "─" * width)
        mid = width // 2 - 1
        lines.append(
            f"      0.0{' ' * (mid - 3)}0.5{' ' * (width - mid - 4)}1.0 FPR"
        )
        return "\n".join(lines)

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
            auc = self._best_score
            color = self._auc_color(auc)
            label = self._auc_label(auc)
            trend = self._calculate_trend()

            score_line = Text()
            score_line.append("  Best AUC-ROC: ", style="bold")
            score_line.append(f"{auc:.4f}", style=color)
            score_line.append(f"  ({label})", style=color)
            score_line.append(f"  iter {self._best_iter}/{self.total}", style="dim")

            content = Text.assemble(score_line)

            if self._best_score_std is not None:
                std_color = self._auc_color(max(0, auc - self._best_score_std))
                std_line = Text()
                std_line.append("  ±Std Dev:     ", style="bold")
                std_line.append(f"{self._best_score_std:.4f}", style=std_color)
                std_line.append("  (lower = more stable)", style="dim")
                content = Text.assemble(content, "\n", std_line)

            # CV range line
            if self._best_score_std is not None:
                lo = max(0.0, auc - self._best_score_std)
                hi = min(1.0, auc + self._best_score_std)
                range_line = Text()
                range_line.append("  CV Range:     ", style="bold")
                range_line.append(f"{lo:.4f}", style=self._auc_color(lo))
                range_line.append(" – ")
                range_line.append(f"{hi:.4f}", style=self._auc_color(hi))
                content = Text.assemble(content, "\n", range_line)

            if trend:
                content = Text.assemble(content, f"\n  Trend: {trend}")

            # Sparkline
            spark = self._sparkline(self._score_history)
            if spark:
                spark_line = Text()
                spark_line.append("  History: ", style="bold")
                spark_line.append(spark, style=color)
                content = Text.assemble(content, "\n", spark_line)

            # Extra test-set stats (show_stats mode)
            if self.show_stats and self._stats_map100 is not None:
                sep = "\n  " + "─" * 38
                header = Text("\n  Test Set Metrics (best HP so far)", style="bold cyan")
                content = Text.assemble(content, sep, header)

                map100_color = self._auc_color(self._stats_map100)
                map100_label = self._auc_label(self._stats_map100)
                map500_color = self._auc_color(self._stats_map500)
                map500_label = self._auc_label(self._stats_map500)
                map_line = Text()
                map_line.append("\n  MAP@100:     ", style="bold")
                map_line.append(f"{self._stats_map100:.4f}", style=map100_color)
                map_line.append(f"  ({map100_label})", style=map100_color)
                map_line.append("   MAP@500:  ", style="bold")
                map_line.append(f"{self._stats_map500:.4f}", style=map500_color)
                map_line.append(f"  ({map500_label})", style=map500_color)
                content = Text.assemble(content, map_line)

                brier_color = (
                    "green" if (self._stats_brier or 1) < 0.05
                    else ("dark_orange" if (self._stats_brier or 1) < 0.1 else "red")
                )
                brier_label = self._brier_label(self._stats_brier or 1)
                brier_line = Text()
                brier_line.append("\n  Brier Score: ", style="bold")
                brier_line.append(f"{self._stats_brier:.4f}", style=brier_color)
                brier_line.append(f"  ({brier_label})", style=brier_color)
                content = Text.assemble(content, brier_line)

                prec_color = self._auc_color(self._stats_precision)
                prec_label = self._auc_label(self._stats_precision)
                recall_color = self._auc_color(self._stats_recall)
                recall_label = self._auc_label(self._stats_recall)
                f1_color = self._auc_color(self._stats_f1)
                f1_label = self._auc_label(self._stats_f1)
                prf_line = Text()
                prf_line.append(
                    f"\n  P/R/F1 @{self._stats_threshold:.2f}: ", style="bold"
                )
                prf_line.append(f"{self._stats_precision:.3f}", style=prec_color)
                prf_line.append(f" ({prec_label})", style=prec_color)
                prf_line.append(" / ", style="dim")
                prf_line.append(f"{self._stats_recall:.3f}", style=recall_color)
                prf_line.append(f" ({recall_label})", style=recall_color)
                prf_line.append(" / ", style="dim")
                prf_line.append(f"{self._stats_f1:.3f}", style=f1_color)
                prf_line.append(f" ({f1_label})", style=f1_color)
                content = Text.assemble(content, prf_line)

                if self._stats_recall100 is not None:
                    r100_color = self._auc_color(self._stats_recall100)
                    r500_color = self._auc_color(self._stats_recall500)
                    p100_color = self._auc_color(self._stats_prec100)
                    p500_color = self._auc_color(self._stats_prec500)
                    rk_line = Text()
                    rk_line.append("\n  Recall@100:  ", style="bold")
                    rk_line.append(f"{self._stats_recall100:.4f}", style=r100_color)
                    rk_line.append(f"  ({self._auc_label(self._stats_recall100)})", style=r100_color)
                    rk_line.append("   Recall@500: ", style="bold")
                    rk_line.append(f"{self._stats_recall500:.4f}", style=r500_color)
                    rk_line.append(f"  ({self._auc_label(self._stats_recall500)})", style=r500_color)
                    pk_line = Text()
                    pk_line.append("\n  Prec@100:    ", style="bold")
                    pk_line.append(f"{self._stats_prec100:.4f}", style=p100_color)
                    pk_line.append(f"  ({self._auc_label(self._stats_prec100)})", style=p100_color)
                    pk_line.append("   Prec@500:   ", style="bold")
                    pk_line.append(f"{self._stats_prec500:.4f}", style=p500_color)
                    pk_line.append(f"  ({self._auc_label(self._stats_prec500)})", style=p500_color)
                    content = Text.assemble(content, rk_line, pk_line)

                if self._stats_fpr and self._stats_tpr:
                    roc_header = Text("\n\n  ROC Curve:", style="bold")
                    roc_art = self._render_ascii_roc(self._stats_fpr, self._stats_tpr)
                    content = Text.assemble(content, roc_header, f"\n{roc_art}")
        else:
            content = "  Awaiting first score..."

        score_panel = Panel(
            content, title="Best Score", border_style="magenta"
        )

        return Group(progress_panel, resource_panel, score_panel)
