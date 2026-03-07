"""Live training and feature-build progress displays with resource monitoring.

Provides:
- :class:`TrainingProgressDisplay` — Rich live display for HP search with ETA,
  CPU/RAM/GPU stats, and best-so-far score with trend arrows.
- :class:`FeatureBuildProgressDisplay` — Rich live display for the feature
  engineering pipeline with stage tracking, row throughput, and resource stats.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import psutil
from rich.console import Console, ConsoleOptions, Group, RenderResult
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
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom ETA column
# ---------------------------------------------------------------------------


class _ETAColumn(ProgressColumn):
    """ETA column that freezes between iterations to avoid misleading increases.

    Recalculates only when a new iteration completes: avg_time_per_iter * remaining.
    Between iterations the last computed value is held constant.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._last_completed: int = -1
        self._frozen_eta_sec: int | None = None
        self._frozen_at: float = time.monotonic()

    def render(self, task: Any) -> Text:  # type: ignore[override]
        completed = int(task.completed)
        total = task.total
        if total is None or total <= 0 or completed <= 0:
            return Text("eta: --:--", style="progress.remaining")
        if completed >= total:
            return Text("eta: 0:00", style="progress.remaining")
        # Only recompute when a new iteration finishes
        if completed != self._last_completed:
            elapsed: float = task.elapsed or 0.0
            if elapsed > 0:
                avg_sec = elapsed / completed
                self._frozen_eta_sec = int(avg_sec * (total - completed))
            self._last_completed = completed
            self._frozen_at = time.monotonic()
        if self._frozen_eta_sec is None:
            return Text("eta: --:--", style="progress.remaining")
        # Tick down between iterations by subtracting seconds elapsed since freeze
        display_sec = max(0, self._frozen_eta_sec - int(time.monotonic() - self._frozen_at))
        h, rem = divmod(display_sec, 3600)
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
        self._iter_start_time: float = time.monotonic()

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

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Called by Rich on every auto-refresh tick so the timer updates live."""
        yield self._build_display()

    def start(self) -> None:
        """Start the live display."""
        self._start_time = time.monotonic()
        self._iter_start_time = time.monotonic()
        # Prime psutil's cpu_percent so first non-blocking call has data
        psutil.cpu_percent(interval=None)
        self._live = Live(
            self,
            console=self._console,
            refresh_per_second=4,
            screen=True,
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

        self._iter_start_time = time.monotonic()
        if self._live is not None:
            self._live.refresh()

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
            self._live.refresh()

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
        iter_elapsed = time.monotonic() - self._iter_start_time
        iter_mins, iter_secs = divmod(int(iter_elapsed), 60)
        iter_time_str = f"{iter_mins}:{iter_secs:02d}" if iter_mins else f"{iter_secs}s"
        iter_line = Text(f"  Current iter: {iter_time_str} elapsed", style="dim")
        progress_panel = Panel(
            Group(self._progress, iter_line),
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
        resource_panel = Panel(resource_text, title="Resources", border_style="yellow")

        # Best score panel
        if self._best_score is None:
            score_panel = Panel("  Awaiting first score...", title="Best Score", border_style="magenta")
            return Group(progress_panel, resource_panel, score_panel)

        auc = self._best_score
        color = self._auc_color(auc)
        label = self._auc_label(auc)
        trend = self._calculate_trend()

        # --- Left column: CV scores + test-set metrics ---
        left = Text()
        left.append("Best AUC-ROC: ", style="bold")
        left.append(f"{auc:.4f}", style=color)
        left.append(f"  ({label})", style=color)
        left.append(f"  iter {self._best_iter}/{self.total}\n", style="dim")

        if self._best_score_std is not None:
            std_color = self._auc_color(max(0, auc - self._best_score_std))
            left.append("±Std Dev:     ", style="bold")
            left.append(f"{self._best_score_std:.4f}", style=std_color)
            left.append("  (lower = more stable)\n", style="dim")
            lo = max(0.0, auc - self._best_score_std)
            hi = min(1.0, auc + self._best_score_std)
            left.append("CV Range:     ", style="bold")
            left.append(f"{lo:.4f}", style=self._auc_color(lo))
            left.append(" – ")
            left.append(f"{hi:.4f}\n", style=self._auc_color(hi))

        if trend:
            left.append(f"Trend: {trend}\n")

        spark = self._sparkline(self._score_history)
        if spark:
            left.append("History: ", style="bold")
            left.append(spark, style=color)
            left.append("\n")

        # Test-set metrics section (shown when show_stats + data available)
        has_test_stats = self.show_stats and self._stats_map100 is not None
        if has_test_stats:
            left.append("─" * 36 + "\n", style="dim")
            left.append("Test Set Metrics\n", style="bold cyan")

            m100c = self._auc_color(self._stats_map100)
            m500c = self._auc_color(self._stats_map500)
            left.append("MAP@100: ", style="bold")
            left.append(f"{self._stats_map100:.4f}", style=m100c)
            left.append(f" ({self._auc_label(self._stats_map100)})", style=m100c)
            left.append("  MAP@500: ", style="bold")
            left.append(f"{self._stats_map500:.4f}", style=m500c)
            left.append(f" ({self._auc_label(self._stats_map500)})\n", style=m500c)

            brier_color = (
                "green" if (self._stats_brier or 1) < 0.05
                else ("dark_orange" if (self._stats_brier or 1) < 0.1 else "red")
            )
            left.append("Brier Score:  ", style="bold")
            left.append(f"{self._stats_brier:.4f}", style=brier_color)
            left.append(f" ({self._brier_label(self._stats_brier or 1)})\n", style=brier_color)

            prec_c = self._auc_color(self._stats_precision)
            rec_c = self._auc_color(self._stats_recall)
            f1_c = self._auc_color(self._stats_f1)
            left.append(f"P/R/F1 @{self._stats_threshold:.2f}:  ", style="bold")
            left.append(f"{self._stats_precision:.3f}", style=prec_c)
            left.append(" / ", style="dim")
            left.append(f"{self._stats_recall:.3f}", style=rec_c)
            left.append(" / ", style="dim")
            left.append(f"{self._stats_f1:.3f}\n", style=f1_c)

            if self._stats_recall100 is not None:
                r100c = self._auc_color(self._stats_recall100)
                r500c = self._auc_color(self._stats_recall500)
                p100c = self._auc_color(self._stats_prec100)
                p500c = self._auc_color(self._stats_prec500)
                left.append("Recall@100: ", style="bold")
                left.append(f"{self._stats_recall100:.4f}", style=r100c)
                left.append("  Recall@500: ", style="bold")
                left.append(f"{self._stats_recall500:.4f}\n", style=r500c)
                left.append("Prec@100:   ", style="bold")
                left.append(f"{self._stats_prec100:.4f}", style=p100c)
                left.append("  Prec@500:   ", style="bold")
                left.append(f"{self._stats_prec500:.4f}\n", style=p500c)

        # --- Right column: ROC curve (when available) ---
        has_roc = has_test_stats and bool(self._stats_fpr and self._stats_tpr)
        if has_roc:
            roc_art = self._render_ascii_roc(self._stats_fpr, self._stats_tpr, width=32, height=8)
            right = Text()
            right.append("ROC Curve\n", style="bold cyan")
            right.append(roc_art)

            grid = Table.grid(expand=True)
            grid.add_column(ratio=3)
            grid.add_column(ratio=2)
            grid.add_row(left, right)
            score_inner: Any = grid
        else:
            score_inner = left

        score_panel = Panel(score_inner, title="Best Score", border_style="magenta")
        return Group(progress_panel, resource_panel, score_panel)


# ---------------------------------------------------------------------------
# FeatureBuildProgressDisplay
# ---------------------------------------------------------------------------


class FeatureBuildProgressDisplay:
    """Live feature engineering pipeline progress with stage tracking and resource monitoring.

    Usage::

        display = FeatureBuildProgressDisplay(device="cpu", total_rows=9_400_000)
        display.start()
        display.start_stage(0)           # "Provider History Index"
        # ... do work ...
        display.complete_stage(0)
        display.start_stage(5)           # "Feature Extraction"
        for i, row in enumerate(rows):
            # ... process row ...
            if i % 5000 == 0:
                display.update_rows(i, kept, dropped)
        display.complete_stage(5)
        display.stop()

    Also works as a context manager.
    """

    STAGES: list[tuple[str, str]] = [
        ("Provider History", "Indexing provider contract history"),
        ("Procesos Lookup", "Loading procurement process data"),
        ("Proveedores Lookup", "Loading registered providers"),
        ("Actividades Lookup", "Counting economic activities per provider"),
        ("IRIC Setup", "Loading thresholds & bid statistics"),
        ("Feature Extraction", "Computing 34-feature vectors for all contracts"),
        ("Encoding & Output", "Applying encodings and writing features.parquet"),
    ]
    TOTAL_STAGES = 7

    _STAGE_COLORS = [
        "bright_cyan", "blue", "magenta", "yellow",
        "green", "bright_yellow", "bright_green",
    ]

    def __init__(
        self,
        device: str = "cpu",
        total_rows: int | None = None,
        console: Console | None = None,
    ) -> None:
        self.device = device
        self.total_rows = total_rows
        self._console = console or Console()

        self._current_stage: int = 0
        self._stage_start: float = time.monotonic()
        self._start_time: float | None = None
        self._row_start: float | None = None

        self._rows_processed: int = 0
        self._rows_kept: int = 0
        self._rows_dropped: int = 0
        self._rows_per_sec: float = 0.0

        # Stage-level progress (always visible)
        self._stage_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=28),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("elapsed:"),
            TimeElapsedColumn(),
            console=self._console,
        )
        self._stage_task = self._stage_progress.add_task(
            "Initializing...", total=self.TOTAL_STAGES
        )

        # Row-level progress (visible only during Feature Extraction stage)
        self._row_progress = Progress(
            SpinnerColumn(),
            TextColumn("[dim cyan]Rows"),
            BarColumn(bar_width=28),
            TextColumn("{task.completed:>9,}"),
            TextColumn("/"),
            TextColumn("{task.total:>9,}" if total_rows else "  (counting)"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%" if total_rows else ""),
            TimeElapsedColumn(),
            _ETAColumn(),
            console=self._console,
        )
        row_total = total_rows if total_rows and total_rows > 0 else None
        self._row_task = self._row_progress.add_task(
            "rows", total=row_total, visible=False
        )

        self._live: Live | None = None

    # -- Lifecycle -----------------------------------------------------------

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Called by Rich on every auto-refresh tick so timers update live."""
        yield self._build_display()

    def start(self) -> None:
        """Start the live display."""
        self._start_time = time.monotonic()
        psutil.cpu_percent(interval=None)
        self._live = Live(
            self,
            console=self._console,
            refresh_per_second=4,
            screen=True,
        )
        self._live.start()

    def stop(self) -> None:
        """Stop the live display and print final summary."""
        if self._live is not None:
            self._live.stop()
            self._live = None

        elapsed = time.monotonic() - (self._start_time or time.monotonic())
        mins, secs = divmod(int(elapsed), 60)
        pct_kept = (
            f"{100 * self._rows_kept / self._rows_processed:.1f}%"
            if self._rows_processed > 0 else "N/A"
        )

        self._console.print()
        self._console.print(
            Panel(
                f"  Rows processed: {self._rows_processed:,}  |  "
                f"Kept: {self._rows_kept:,} ({pct_kept})  |  "
                f"Dropped: {self._rows_dropped:,}\n"
                f"  Total time: {mins}m{secs:02d}s  |  "
                f"Output: [bold]features.parquet[/bold]",
                title="[bold bright_green]Feature Build Complete",
                border_style="bright_green",
            )
        )

    def start_stage(self, stage_idx: int) -> None:
        """Signal that stage ``stage_idx`` (0-based) is beginning."""
        self._current_stage = stage_idx
        self._stage_start = time.monotonic()

        name, _ = self.STAGES[stage_idx] if stage_idx < self.TOTAL_STAGES else (f"Stage {stage_idx + 1}", "")
        color = self._STAGE_COLORS[stage_idx % len(self._STAGE_COLORS)]
        self._stage_progress.update(
            self._stage_task,
            description=f"[{color}][{stage_idx + 1}/{self.TOTAL_STAGES}] {name}",
            completed=stage_idx,
        )

        # Show row progress bar when entering Feature Extraction
        if stage_idx == 5:
            self._row_start = time.monotonic()
            self._row_progress.update(self._row_task, visible=True, completed=0)

        self._refresh()

    def complete_stage(self, stage_idx: int) -> None:
        """Signal that stage ``stage_idx`` finished successfully."""
        self._stage_progress.update(self._stage_task, completed=stage_idx + 1)
        if stage_idx == 5:
            self._row_progress.update(self._row_task, visible=False)
        self._refresh()

    def update_rows(
        self,
        rows_processed: int,
        rows_kept: int,
        rows_dropped: int,
    ) -> None:
        """Update row counters during the Feature Extraction stage."""
        self._rows_processed = rows_processed
        self._rows_kept = rows_kept
        self._rows_dropped = rows_dropped

        self._row_progress.update(self._row_task, completed=rows_processed)

        if self._row_start:
            elapsed = time.monotonic() - self._row_start
            if elapsed > 0:
                self._rows_per_sec = rows_processed / elapsed

        self._refresh()

    # -- Context manager -----------------------------------------------------

    def __enter__(self) -> "FeatureBuildProgressDisplay":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    # -- Internal rendering --------------------------------------------------

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.refresh()

    def _build_display(self) -> Group:
        """Build the complete live display layout."""
        stage_idx = min(self._current_stage, self.TOTAL_STAGES - 1)
        name, desc = self.STAGES[stage_idx] if stage_idx < self.TOTAL_STAGES else (f"Stage {stage_idx + 1}", "")
        color = self._STAGE_COLORS[stage_idx % len(self._STAGE_COLORS)]

        stage_elapsed = time.monotonic() - self._stage_start
        sm, ss = divmod(int(stage_elapsed), 60)
        stage_time_str = f"{sm}:{ss:02d}" if sm else f"{ss}s"

        desc_line = Text(
            f"  [{color}]{name}[/] — {desc}  ({stage_time_str} this stage)",
            style="",
            end="\n",
        )

        # Feature Extraction stage: include row progress bar
        if self._current_stage == 5:
            pipeline_group: Any = Group(self._stage_progress, desc_line, self._row_progress)
        else:
            pipeline_group = Group(self._stage_progress, desc_line)

        progress_panel = Panel(
            pipeline_group,
            title="[bold cyan]Feature Pipeline",
            border_style="cyan",
        )

        # Resource panel
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        mem_used_gb = mem.used / (1024**3)
        mem_total_gb = mem.total / (1024**3)
        gpu_line = _gpu_utilization(self.device)

        ram_pct = mem.percent
        if ram_pct >= 85:
            ram_color = "red"
        elif ram_pct >= 65:
            ram_color = "dark_orange"
        else:
            ram_color = "green"

        resource_text = Text()
        resource_text.append(f"  CPU:  {cpu:.1f}%\n")
        resource_text.append(f"  RAM:  {mem_used_gb:.1f} GB / {mem_total_gb:.1f} GB (")
        resource_text.append(f"{mem.percent:.1f}%", style=ram_color)
        resource_text.append(f")\n  GPU:  {gpu_line}")

        resource_panel = Panel(resource_text, title="[bold yellow]Resources", border_style="yellow")

        # Stats panel
        if self._rows_processed > 0:
            pct_kept = 100 * self._rows_kept / self._rows_processed
            pct_dropped = 100 * self._rows_dropped / self._rows_processed
            stats_content = Text()
            stats_content.append(f"  Processed:  {self._rows_processed:>10,}\n")
            stats_content.append(f"  Kept:       {self._rows_kept:>10,}", style="green")
            stats_content.append(f"  ({pct_kept:.1f}%)\n", style="dim")
            stats_content.append(f"  Dropped:    {self._rows_dropped:>10,}", style="yellow" if pct_dropped < 20 else "red")
            stats_content.append(f"  ({pct_dropped:.1f}%)\n", style="dim")
            tp_text = Text.from_markup(
                f"  Throughput: [bold bright_cyan]{self._rows_per_sec:,.0f}[/] rows/s"
                if self._rows_per_sec > 0 else "  Throughput: [dim]calculating...[/]"
            )
            stats_content.append_text(tp_text)
        else:
            stats_content = Text("  Awaiting feature extraction...", style="dim")

        stats_panel = Panel(stats_content, title="[bold magenta]Extraction Stats", border_style="magenta")

        return Group(progress_panel, resource_panel, stats_panel)
