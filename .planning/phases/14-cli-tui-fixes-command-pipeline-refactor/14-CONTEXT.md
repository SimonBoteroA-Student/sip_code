# Phase 14: CLI & TUI Fixes — Command Pipeline Refactor - Context

**Gathered:** 2026-03-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix TUI panel rendering bugs (missing hardware panel, missing header text, missing left border
characters), and refactor the CLI so `run-pipeline` is a clean orchestrator that delegates to
individual subcommand logic via `run()` functions — with a single upfront hardware config TUI and
step-skipping support.

Evaluation charts are working correctly and require NO changes this phase.

</domain>

<decisions>
## Implementation Decisions

### TUI Bug Fixes
- The hardware info panel (top panel, "Detected Hardware") is entirely missing — does not render at all
- The header instruction text (e.g. "↑↓ select, ←→ adjust, type number, Enter to confirm") inside
  the sliders panel is also missing
- Left panel border characters are missing; only right-side borders render, overlapping where the
  right border of the config panel should be
- The "chart edge clipping" in the ROADMAP refers to this same TUI panel border issue — NOT the
  evaluation PNG charts, which are fine

These three symptoms likely share a root cause in how Rich `Group` + `Panel` + `Text` renders inside
`Live(screen=True)`. The fix should restore `_make_layout()` so it correctly renders the hardware
panel on top, then the config panel below, with full borders on all sides.

### Pipeline Orchestration
- `run-pipeline` calls individual step logic via **function calls** (not subprocess invocations)
- Each command (build-rcac, build-labels, build-features, build-iric, train, evaluate) exposes a
  `run(args)` function
- Best-practice location for these functions is Claude's discretion (recommend a shared module such
  as a pipeline coordinator, so both `run-pipeline` and individual CLI handlers call the same logic)
- This eliminates the current code duplication in `run-pipeline`

### Hardware Config TUI in run-pipeline
- Single hardware config TUI shown **once at pipeline start**, before any step runs
- Config (n_jobs, RAM, device, n_iter, cv_folds) flows through **all** steps in the pipeline
  (rcac, labels, features, iric, train, evaluate)
- `--no-interactive` / `--skip-config` flag continues to bypass the TUI and use defaults

### Step-Skip and Resume Logic
- Steps skip by default if their output artifacts already exist (avoid redundant re-runs)
- `--force` flag causes all steps to re-run regardless
- `--start-from <step>` flag resumes from a named step (e.g. `--start-from train` skips to training)
  Supported step names: `rcac`, `labels`, `features`, `iric`, `train`, `evaluate`

### Claude's Discretion
- Internal module structure for exposing `run()` functions per subcommand — choose the pattern that
  best avoids circular imports and keeps `__main__.py` clean
- Whether to use a dataclass or plain dict for the shared pipeline config passed between steps

</decisions>

<specifics>
## Specific Ideas

- The three TUI symptoms (missing hardware panel, missing header text, missing left borders) likely
  share a common Rich rendering root cause — investigate `Group` + `Live(screen=True)` interaction
- `--start-from` should validate the step name and print a helpful error for unknown values
- Progress through pipeline steps should still print step banners/headers so the user knows which
  step is running

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 14-cli-tui-fixes-command-pipeline-refactor*
*Context gathered: 2026-03-06*
