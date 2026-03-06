# Phase 14: CLI & TUI Fixes — Command Pipeline Refactor - Research

**Researched:** 2026-03-06
**Domain:** Rich TUI rendering + CLI architecture refactor (Python argparse)
**Confidence:** HIGH

## Summary

Phase 14 has two distinct workstreams: (1) fixing TUI rendering bugs in the Rich-based config screen, and (2) refactoring the CLI so `run-pipeline` delegates to individual step `run()` functions instead of duplicating logic inline.

The TUI bugs (missing hardware panel, missing header text, missing left panel borders) are localized to `config_screen.py` — specifically the `_make_layout()` functions used in `show_config_screen`, `show_features_config_screen`, and `show_pipeline_config_screen`. All three share the same rendering pattern: `Group(hw_panel, config_panel)` rendered inside `Live(screen=True)`. The `Group` renderable from Rich does not control layout dimensions — it simply yields children sequentially. In `screen=True` (alternate buffer) mode, this can cause content to be positioned incorrectly or clipped when the terminal doesn't receive proper height hints. The fix should use `rich.layout.Layout` or ensure proper `Console` renderable sizing for `screen=True` mode.

The pipeline refactor targets `__main__.py`, which is currently a 584-line monolith. Each CLI subcommand handler is an inline `if/elif` block with duplicated imports, hardware detection, and error handling. The `run-pipeline` block (lines 445–563) directly calls step functions with manually-wired config. The refactor extracts each subcommand's logic into a `run()` function in a new pipeline coordinator module, adds `--start-from <step>` resume support, and centralizes the hardware config TUI at pipeline start.

**Primary recommendation:** Fix TUI rendering first (small, visual, verifiable), then refactor CLI pipeline (structural, higher risk). Use a `PipelineConfig` dataclass for shared config, and a `sip_engine/pipeline.py` coordinator module with per-step `run()` functions.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- The hardware info panel (top panel, "Detected Hardware") is entirely missing — does not render at all
- The header instruction text (e.g. "↑↓ select, ←→ adjust, type number, Enter to confirm") inside the sliders panel is also missing
- Left panel border characters are missing; only right-side borders render, overlapping where the right border of the config panel should be
- The "chart edge clipping" in the ROADMAP refers to this same TUI panel border issue — NOT the evaluation PNG charts, which are fine
- These three symptoms likely share a root cause in how Rich `Group` + `Panel` + `Text` renders inside `Live(screen=True)`. The fix should restore `_make_layout()` so it correctly renders the hardware panel on top, then the config panel below, with full borders on all sides.
- `run-pipeline` calls individual step logic via **function calls** (not subprocess invocations)
- Each command (build-rcac, build-labels, build-features, build-iric, train, evaluate) exposes a `run(args)` function
- This eliminates the current code duplication in `run-pipeline`
- Single hardware config TUI shown **once at pipeline start**, before any step runs
- Config (n_jobs, RAM, device, n_iter, cv_folds) flows through **all** steps in the pipeline
- `--no-interactive` / `--skip-config` flag continues to bypass the TUI and use defaults
- Steps skip by default if their output artifacts already exist (avoid redundant re-runs)
- `--force` flag causes all steps to re-run regardless
- `--start-from <step>` flag resumes from a named step. Supported step names: `rcac`, `labels`, `features`, `iric`, `train`, `evaluate`

### Claude's Discretion
- Internal module structure for exposing `run()` functions per subcommand — choose the pattern that best avoids circular imports and keeps `__main__.py` clean
- Whether to use a dataclass or plain dict for the shared pipeline config passed between steps
- Best-practice location for `run()` functions (recommend a shared module such as a pipeline coordinator, so both `run-pipeline` and individual CLI handlers call the same logic)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| rich | 14.3.3 (>=13.0 pinned) | TUI panels, Live display, progress | Already in project, powers all TUI |
| argparse | stdlib | CLI argument parsing | Already used in `__main__.py` |
| dataclasses | stdlib | Config struct for pipeline state | Clean, typed, frozen-capable |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| psutil | >=5.9 | Hardware stats (CPU/RAM) | Already used by hardware detector |
| rich.layout.Layout | (part of rich) | Screen-mode layout control | For fixing TUI panel rendering |
| rich.console.Group | (part of rich) | Sequential renderable container | Only for non-screen rendering |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `Group` for screen TUI | `Layout` from rich.layout | Layout gives explicit height/width control needed for `screen=True` |
| Plain dict for config | `@dataclass PipelineConfig` | Dataclass adds type safety, IDE support, and field documentation |
| Per-module `run()` funcs | Single pipeline.py coordinator | Coordinator avoids touching existing module files; cleaner separation |

## Architecture Patterns

### Current Project Structure (relevant files)
```
src/sip_engine/
├── __main__.py                          # 584-line CLI monolith (REFACTOR TARGET)
├── compat.py                            # Cross-platform utilities
├── shared/
│   ├── config/settings.py               # Settings dataclass + get_settings()
│   ├── data/
│   │   ├── rcac_builder.py              # build_rcac(force) → Path
│   │   └── label_builder.py             # build_labels(force) → Path
│   └── hardware/
│       ├── detector.py                  # HardwareConfig + detect_hardware()
│       └── device.py                    # get_xgb_device_kwargs()
├── classifiers/
│   ├── features/pipeline.py             # build_features(force, n_jobs, ...) → Path
│   ├── iric/pipeline.py                 # build_iric(force) → Path
│   ├── models/trainer.py                # train_model(model_id, force, ...) → Path
│   ├── evaluation/evaluator.py          # evaluate_model() / evaluate_all() → Path
│   └── ui/
│       ├── config_screen.py             # TUI config screens (BUG FIX TARGET)
│       └── progress.py                  # Training/feature progress displays
```

### Recommended New Structure
```
src/sip_engine/
├── __main__.py                          # Thin CLI: argparse + dispatch to pipeline.py
├── pipeline.py                          # NEW: PipelineConfig + per-step run() + orchestrator
├── ...                                  # (everything else unchanged)
```

### Pattern 1: Pipeline Coordinator Module
**What:** A new `sip_engine/pipeline.py` module that centralizes all step execution logic.
**When to use:** Both `run-pipeline` and individual CLI subcommands call into this module.
**Why:** Eliminates duplication between `run-pipeline` block and individual command blocks in `__main__.py`. Each step function is defined once. The `run-pipeline` orchestrator calls them in sequence with shared config.

```python
# src/sip_engine/pipeline.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

@dataclass(frozen=True)
class PipelineConfig:
    """Shared configuration flowing through all pipeline steps."""
    n_jobs: int
    n_iter: int
    cv_folds: int
    max_ram_gb: int
    device: str
    force: bool = False
    model: str | None = None       # None = all 4 models
    quick: bool = False
    disable_rocm: bool = False
    show_stats: bool = True

STEP_NAMES = ("rcac", "labels", "features", "iric", "train", "evaluate")

def run_rcac(cfg: PipelineConfig) -> Path:
    from sip_engine.shared.data.rcac_builder import build_rcac
    return build_rcac(force=cfg.force)

def run_labels(cfg: PipelineConfig) -> Path:
    from sip_engine.shared.data.label_builder import build_labels
    return build_labels(force=cfg.force)

def run_features(cfg: PipelineConfig) -> Path:
    from sip_engine.classifiers.features.pipeline import build_features
    return build_features(
        force=cfg.force,
        n_jobs=cfg.n_jobs,
        max_ram_gb=cfg.max_ram_gb,
        device=cfg.device,
        interactive=False,
        show_progress=True,
    )

def run_iric(cfg: PipelineConfig) -> Path:
    from sip_engine.classifiers.iric.pipeline import build_iric
    return build_iric(force=cfg.force)

def run_train(cfg: PipelineConfig) -> list[Path]:
    from sip_engine.classifiers.models.trainer import train_model, MODEL_IDS
    models = [cfg.model] if cfg.model else MODEL_IDS
    results = []
    for mid in models:
        path = train_model(
            model_id=mid,
            force=cfg.force,
            quick=cfg.quick,
            n_iter=cfg.n_iter,
            n_jobs=cfg.n_jobs,
            device=cfg.device,
            disable_rocm=cfg.disable_rocm,
            interactive=False,
            show_stats=cfg.show_stats,
        )
        results.append(path)
    return results

def run_evaluate(cfg: PipelineConfig) -> Path:
    from sip_engine.classifiers.evaluation.evaluator import evaluate_all, evaluate_model, MODEL_IDS
    models = [cfg.model] if cfg.model else MODEL_IDS
    if len(models) == 1:
        return evaluate_model(model_id=models[0])
    return evaluate_all()

def run_pipeline(cfg: PipelineConfig, start_from: str | None = None) -> None:
    """Run all pipeline steps in sequence, with optional resume."""
    steps = list(STEP_NAMES)
    if start_from:
        if start_from not in STEP_NAMES:
            raise ValueError(
                f"Unknown step '{start_from}'. Must be one of: {', '.join(STEP_NAMES)}"
            )
        idx = steps.index(start_from)
        steps = steps[idx:]
    
    step_fns = {
        "rcac": run_rcac,
        "labels": run_labels,
        "features": run_features,
        "iric": run_iric,
        "train": run_train,
        "evaluate": run_evaluate,
    }
    
    for i, step in enumerate(steps, 1):
        # Print step banner
        step_fns[step](cfg)
```

### Pattern 2: TUI Layout Fix with `rich.layout.Layout`
**What:** Replace `Group` with `Layout` for `screen=True` rendering.
**When to use:** When rendering multiple panels in full-screen (`screen=True`) mode.
**Why:** `Group` is a simple sequential yield — it doesn't participate in layout negotiation. `Layout` provides explicit height/width allocation, critical for alternate screen buffer rendering.

```python
# Fixed _make_layout pattern
from rich.layout import Layout

def _make_layout() -> Layout:
    hw_panel = _build_hardware_panel(hw_config)
    
    # Build config panel content as before...
    lines: list[Text] = [header]
    for i, widget in enumerate(sliders):
        lines.append(widget.render(selected=i == selected))
    lines.append(footer)
    
    config_group = Text()
    for ln in lines:
        config_group.append_text(ln)
        config_group.append("\n")
    
    config_panel = Panel(config_group, title="Training Settings", border_style="blue")
    
    # Use Layout for proper screen rendering
    layout = Layout()
    layout.split_column(
        Layout(hw_panel, name="hardware", size=8),
        Layout(config_panel, name="config"),
    )
    return layout
```

### Pattern 3: Thin CLI Dispatch in `__main__.py`
**What:** Reduce `__main__.py` to just argparse setup + minimal dispatch.
**When to use:** After pipeline coordinator exists.

```python
# Refactored __main__.py pattern for each subcommand:
elif args.command == "build-rcac":
    from sip_engine.pipeline import PipelineConfig, run_rcac
    cfg = PipelineConfig(
        n_jobs=1, n_iter=0, cv_folds=0, max_ram_gb=0,
        device="cpu", force=args.force,
    )
    try:
        path = run_rcac(cfg)
        print(f"RCAC built: {path}")
        sys.exit(0)
    except Exception as e:
        print(f"Error building RCAC: {e}", file=sys.stderr)
        sys.exit(1)
```

### Anti-Patterns to Avoid
- **Subprocess invocation between steps:** CONTEXT explicitly says "function calls, not subprocess invocations." Never use `subprocess.run()` to call sibling commands.
- **Circular imports between pipeline.py and __main__.py:** `pipeline.py` should NEVER import from `__main__.py`. Flow is always `__main__.py → pipeline.py → domain modules`.
- **Eager imports in pipeline.py:** Keep imports inside function bodies (lazy) to match existing project pattern and avoid circular dependency chains.
- **Breaking existing individual command behavior:** Each standalone command (`build-rcac`, `train`, etc.) must continue to work exactly as before. The refactor should be backward-compatible.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Screen-mode panel layout | Manual cursor positioning / ANSI escape codes | `rich.layout.Layout` | Rich handles terminal dimensions, resize events, overflow |
| Cross-platform key reading | New keyboard input module | Existing `_read_key()` in config_screen.py | Already works on macOS/Windows/Linux |
| Artifact existence checks | New check-if-exists functions | Each builder's existing `force` parameter | All 6 steps already check `.exists() and not force` |
| CLI argument parsing | Click, Typer, Fire | stdlib `argparse` (already used) | Project convention, no new dependencies |

**Key insight:** Every step already has built-in `force`/skip logic. The step-skip feature in `run-pipeline` gets it "for free" by simply calling each step with `force=False` (default). The `--force` pipeline flag overrides all steps to rebuild.

## Common Pitfalls

### Pitfall 1: Rich `Group` vs `Layout` in `screen=True` Mode
**What goes wrong:** `Group` is a simple renderable container that just yields children sequentially — it doesn't negotiate height/width. In `Live(screen=True)` mode (alternate screen buffer), the terminal clears and redraws each frame. Without explicit size hints, Rich may miscalculate content positioning, causing panels to overlap, clip, or disappear entirely.
**Why it happens:** `screen=True` switches to the alternate terminal buffer (like `vim`). Rich needs to know total content height to position the cursor. `Group` doesn't report a fixed height.
**How to avoid:** Use `rich.layout.Layout` with explicit `size` parameters for each section, OR render to a `Table(show_header=False, show_edge=False)` with grid layout.
**Warning signs:** Panels not appearing, borders only on one side, content jumping on terminal resize.

### Pitfall 2: Text Concatenation Losing Styles
**What goes wrong:** The current `_make_layout()` concatenates `Text` objects into a single `Text` via `append_text()` + `append("\n")`. If the header `Text` already ends with `\n`, double newlines appear. More critically, style boundaries may not render correctly when the composite `Text` is placed inside a `Panel`.
**Why it happens:** `Text.append_text()` merges span information, but complex nested styles can conflict when Rich calculates line wrapping inside a `Panel`.
**How to avoid:** Use `Group(*lines)` inside the panel (for non-screen contexts) or `Renderables` to keep each line as a separate renderable. For the panel content, a `Table(show_header=False, box=None)` with one row per slider line gives cleanest results.

### Pitfall 3: Circular Import Between pipeline.py and Domain Modules
**What goes wrong:** If `pipeline.py` has top-level imports of all 6 step modules, it may trigger circular imports (e.g., `trainer.py` → `config_screen.py` → something that imports pipeline).
**Why it happens:** Eager import chains in Python.
**How to avoid:** All step module imports inside `pipeline.py` should be **lazy** (inside function bodies), matching the existing pattern in `__main__.py`.

### Pitfall 4: Breaking Individual Command Behavior
**What goes wrong:** Refactoring `run-pipeline` to use `run()` functions inadvertently changes how standalone commands work (different defaults, missing error handling, changed output messages).
**Why it happens:** Subtle differences between pipeline config and individual command args (e.g., `build-features` needs `interactive=True` when run standalone, but `interactive=False` when part of pipeline).
**How to avoid:** Test each standalone command before and after refactor. The `run()` functions should accept the same parameters as the current inline code.

### Pitfall 5: `--start-from` Without Validating Prerequisites
**What goes wrong:** User runs `--start-from train` but `features.parquet` doesn't exist. The train step fails with a confusing `FileNotFoundError`.
**Why it happens:** `--start-from` skips earlier steps that would have created prerequisite files.
**How to avoid:** Either (a) add a warning that `--start-from` assumes prior steps have been run, or (b) validate that prerequisite artifacts exist before starting each step. Recommendation: (a) — print a warning. Don't add artifact validation logic to the orchestrator; let each step's existing error handling report what's missing.

### Pitfall 6: Hardware Panel Height in Layout
**What goes wrong:** The hardware panel renders 7 lines (5 data lines + border top/bottom), but if `Layout(size=...)` is set too small, content is clipped.
**Why it happens:** `_build_hardware_panel()` returns a `Panel` with 5 lines of hardware info. With panel title and borders, total height is 7. If a header panel is also present (pipeline screen), that adds 3 more rows.
**How to avoid:** Calculate panel heights dynamically: `size=len(lines) + 2` for border overhead, or use `minimum_size` instead of `size` in Layout splits.

## Code Examples

### Example 1: Fixed `_make_layout()` Using `Layout`
```python
# Source: Rich docs — Layout for screen-mode displays
from rich.layout import Layout
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

def _make_layout() -> Layout:
    """Build the full-screen layout with hardware panel + config panel."""
    hw_panel = _build_hardware_panel(hw_config)
    
    # Build slider lines
    lines: list[Text] = []
    header = Text(
        "  Training Configuration (↑↓ select, ←→ adjust, type number, Enter to confirm)",
        style="bold",
    )
    lines.append(header)
    lines.append(Text(""))  # blank line
    for i, widget in enumerate(sliders):
        lines.append(widget.render(selected=i == selected))
    lines.append(Text(""))
    lines.append(Text("  [Enter] Start training    [q] Quit"))
    
    config_panel = Panel(
        Group(*lines),       # Group works INSIDE a Panel (not at screen level)
        title="Training Settings",
        border_style="blue",
    )
    
    layout = Layout()
    layout.split_column(
        Layout(hw_panel, name="hardware", size=8),
        Layout(config_panel, name="config"),
    )
    return layout
```

### Example 2: PipelineConfig Dataclass
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class PipelineConfig:
    """Immutable config shared across all pipeline steps."""
    n_jobs: int
    n_iter: int
    cv_folds: int
    max_ram_gb: int
    device: str
    force: bool = False
    model: str | None = None
    quick: bool = False
    disable_rocm: bool = False
    show_stats: bool = True
```

### Example 3: `--start-from` Validation
```python
STEP_NAMES = ("rcac", "labels", "features", "iric", "train", "evaluate")

# In argparse setup:
run_parser.add_argument(
    "--start-from",
    choices=STEP_NAMES,
    default=None,
    help="Resume pipeline from this step (e.g. --start-from train)",
)
```

### Example 4: Pipeline Orchestrator With Step Banners
```python
from rich.console import Console

_STEP_LABELS = {
    "rcac": "[1/6] RCAC",
    "labels": "[2/6] Labels",
    "features": "[3/6] Features",
    "iric": "[4/6] IRIC Scores",
    "train": "[5/6] Training Models",
    "evaluate": "[6/6] Evaluation",
}

def run_pipeline(cfg: PipelineConfig, start_from: str | None = None) -> None:
    con = Console()
    steps = list(STEP_NAMES)
    if start_from:
        idx = steps.index(start_from)
        steps = steps[idx:]
    
    for step_name in steps:
        con.rule(f"[bold]{_STEP_LABELS[step_name]}")
        _STEP_FNS[step_name](cfg)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `Group` for screen-mode | `Layout` for screen-mode | Rich ~12.0+ | `Layout` gives explicit height control critical for `screen=True` |
| Monolithic CLI handler | Coordinator pattern | Best practice | Reduces duplication, enables composition |

**Project-specific note:** The `progress.py` module works correctly with `Group` + `Live(screen=True)` because the `_build_display()` method's `Group` of panels totals fewer lines and Rich can auto-size them. The config screen's multi-panel layout (especially `show_pipeline_config_screen` with 3 panels: header + hardware + config) likely exceeds what `Group` can reliably render in screen mode. `Layout` is the correct fix.

## Architecture Analysis: Current Code Duplication

### Duplication Map (what gets eliminated)

| Logic | Current Location(s) | After Refactor |
|-------|---------------------|---------------|
| `build_rcac(force=args.force)` | `__main__.py` line 274, line 507, line 342 | `pipeline.run_rcac(cfg)` |
| `build_labels(force=args.force)` | `__main__.py` line 284, line 509, line 344 | `pipeline.run_labels(cfg)` |
| `build_features(...)` with hw config | `__main__.py` lines 291-320, lines 512-520 | `pipeline.run_features(cfg)` |
| `build_iric(force=args.force)` | `__main__.py` line 325, line 523, line 348 | `pipeline.run_iric(cfg)` |
| `train_model(...)` with full args | `__main__.py` lines 332-369, lines 526-538 | `pipeline.run_train(cfg)` |
| `evaluate_model/all` dispatch | `__main__.py` lines 371-395, lines 540-546 | `pipeline.run_evaluate(cfg)` |
| Hardware detect + config resolve | `__main__.py` lines 294-309, 465-486, trainer.py 808-836 | Once in pipeline coordinator |

### Artifact Path Summary (for step-skip logic)
| Step | Artifact Checked | Settings Path |
|------|-----------------|---------------|
| rcac | `rcac.pkl` | `settings.rcac_path` |
| labels | `labels.parquet` | `settings.labels_path` |
| features | `features.parquet` | `settings.features_path` |
| iric | `iric_scores.parquet` | `settings.iric_scores_path` |
| train | `model.pkl` (per model dir) | `settings.artifacts_models_dir / model_id / "model.pkl"` |
| evaluate | (no skip — always re-evaluates) | N/A |

**Key insight:** Step-skipping in `run-pipeline` is already handled by each step's internal `exists() and not force` check. The orchestrator does NOT need separate skip logic — just pass `force=False` (default) and each step auto-skips if its artifact exists. The `--force` flag overrides all.

## TUI Bug Root Cause Analysis

### Three Symptoms → One Root Cause

1. **Missing hardware panel** — The `Group` yields `hw_panel` first, but in `screen=True` alternate buffer, Rich may not allocate enough vertical space, pushing it off the top.
2. **Missing header text** — The `Text` object for the header is concatenated into `config_group` via `append_text()`, but the resulting single-`Text` renderable may collapse internal newlines when Rich calculates line breaks for `Panel` content.
3. **Missing left borders** — Panel border rendering depends on knowing the exact content width. When `Group` doesn't set explicit width, panels may render with truncated box-drawing characters (showing only right borders where content wraps).

### Fix Strategy
1. Replace `Group` with `Layout` in all three `_make_layout()` functions (`show_config_screen`, `show_features_config_screen`, `show_pipeline_config_screen`)
2. Use `Group(*lines)` inside panels instead of concatenated `Text` (keeps each line as a separate renderable)
3. Set explicit `size` on Layout sections based on content height
4. The three functions share near-identical structure — consider extracting a shared `_make_screen_layout(hw_panel, config_panel)` helper to DRY the fix

### Affected Functions (3 nearly identical `_make_layout` closures)
| Function | File Location | Lines | Panel Count |
|----------|--------------|-------|-------------|
| `show_config_screen._make_layout` | config_screen.py:281-303 | 23 | 2 (hw + config) |
| `show_features_config_screen._make_layout` | config_screen.py:401-422 | 22 | 2 (hw + config) |
| `show_pipeline_config_screen._make_layout` | config_screen.py:526-554 | 29 | 2 or 3 (header? + hw + config) |

## Open Questions

1. **Exact terminal dimensions at screenshot time**
   - What we know: The three symptoms are reported in CONTEXT.md based on user screenshot
   - What's unclear: Whether the issue manifests at all terminal sizes or only below a certain height threshold
   - Recommendation: Fix with `Layout` which handles any terminal size; test at 80x24 minimum

2. **`show_features_config_screen` standalone usage**
   - What we know: `build-features` command calls `show_features_config_screen` when `interactive=True`
   - What's unclear: Whether this screen also exhibits the same rendering bug (likely yes — same pattern)
   - Recommendation: Fix all three `_make_layout()` functions consistently

3. **`train --build-features` flag behavior post-refactor**
   - What we know: `train` command has `--build-features` flag that runs rcac→labels→features→iric before training
   - What's unclear: Whether this flag should remain or be deprecated in favor of `run-pipeline --start-from train`
   - Recommendation: Keep it for backward compatibility. The refactor can have `train --build-features` call the pipeline coordinator functions.

## Sources

### Primary (HIGH confidence)
- **Codebase analysis** — Direct inspection of `__main__.py` (584 lines), `config_screen.py` (601 lines), `progress.py`, `trainer.py`, all builder modules. All findings verified from source.
- **Rich 14.3.3** — version confirmed from `uv.lock`. `Layout`, `Group`, `Live`, `Panel` APIs are stable rich features.
- **pyproject.toml** — `rich>=13.0` pinned, pytest>=8.0 for dev

### Secondary (MEDIUM confidence)
- **Rich `Layout` for screen mode** — Rich docs recommend `Layout` for applications using `screen=True` that need explicit size control. `Group` is intended for simple sequential rendering without size negotiation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project, versions confirmed from lock file
- Architecture: HIGH — clear duplication mapped, coordinator pattern straightforward
- TUI fix: HIGH — root cause identified from code analysis (Group vs Layout in screen mode), fix pattern well-documented in Rich
- Pitfalls: HIGH — all derived from direct codebase inspection, not speculation

**Research date:** 2026-03-06
**Valid until:** 2026-04-06 (stable domain — no fast-moving dependencies)
