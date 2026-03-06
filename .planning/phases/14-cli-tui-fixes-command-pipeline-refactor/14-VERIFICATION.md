---
phase: 14-cli-tui-fixes-command-pipeline-refactor
verified: 2026-03-06T19:46:39Z
status: human_needed
score: 11/11 must-haves verified (automated)
human_verification:
  - test: "Visual TUI rendering: Training config screen"
    expected: "Detected Hardware panel with full borders + 5 info lines, header instruction text visible, Training Settings panel with full borders"
    why_human: "Rich Live(screen=True) rendering in alternate buffer cannot be tested programmatically — only visual inspection confirms no clipping/overlap"
  - test: "Visual TUI rendering: Feature build config screen"
    expected: "Same as training: hardware panel, header text, Feature Build Settings panel all visible with full borders"
    why_human: "Same reason — alternate buffer rendering needs terminal"
  - test: "Visual TUI rendering: Pipeline config screen"
    expected: "SIP Pipeline — Full Run header panel at top, Detected Hardware panel below, Full Pipeline Settings panel below that"
    why_human: "Same reason — alternate buffer rendering needs terminal"
---

# Phase 14: CLI & TUI Fixes — Command Pipeline Refactor Verification Report

**Phase Goal:** Fix chart edge clipping, restore hardware config display and title in TUI, refactor CLI commands so `run-pipeline` acts as a master orchestrator calling individual subcommands, and centralize hardware config prompting at pipeline start.
**Verified:** 2026-03-06T19:46:39Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Hardware panel ('Detected Hardware') renders with full borders and all 5 info lines in all 3 config screens | ✓ VERIFIED | `_build_hardware_panel()` (line 199) builds Panel with 5 lines + "Detected Hardware" title; called in all 3 `_make_layout()` closures (lines 304, 419, 539); placed in Layout with `size=8` in `_make_screen_layout()` |
| 2 | Header instruction text ('↑↓ select, ←→ adjust, type number, Enter to confirm') renders inside each config panel | ✓ VERIFIED | Lines 308, 423, 543 each create a bold Text header appended to `lines` list, which is passed to `Group(*lines)` inside Panel |
| 3 | Left panel borders render correctly — no missing box-drawing characters | ✓ VERIFIED | `_make_screen_layout()` uses `Layout.split_column()` with explicit `size` parameters, giving Rich the height hints needed to avoid clipping in `Live(screen=True)` |
| 4 | All three config screens render identically well in screen=True mode | ✓ VERIFIED | All three `_make_layout()` closures use the same pattern: `_make_screen_layout(hw_panel, config_panel[, header_panel])` with `Group(*lines)` inside Panel |
| 5 | run-pipeline delegates to per-step run() functions — no inline step logic in __main__.py | ✓ VERIFIED | Line 510: `run_pipeline(cfg, start_from=args.start_from)` — single call; no direct domain imports in run-pipeline block |
| 6 | Single hardware config TUI shown once at pipeline start, config flows to all 6 steps | ✓ VERIFIED | Lines 466-509: hardware detected once, TUI config shown once, PipelineConfig built once and passed to `run_pipeline()` which distributes to all steps |
| 7 | --start-from <step> resumes pipeline from the named step, skipping earlier ones | ✓ VERIFIED | `--start-from` arg at lines 186-189; pipeline.py lines 188-194 slice STEP_NAMES from index; test `test_start_from_skips_earlier_steps` passes |
| 8 | --force causes all steps to rebuild regardless of existing artifacts | ✓ VERIFIED | PipelineConfig.force set from args.force (line 504); each run_*() passes cfg.force to domain functions (pipeline.py lines 65, 72, 80, 93, 105) |
| 9 | Steps auto-skip when artifacts exist and force=False | ✓ VERIFIED | Pipeline correctly propagates `force=False` (default) to domain modules which handle artifact-exists checks; this behavior pre-existed and is preserved |
| 10 | Each standalone command (build-rcac, train, evaluate, etc.) still works identically | ✓ VERIFIED | All 10 commands visible in `--help`; build-rcac/labels/iric use pipeline functions; train/evaluate/build-features keep inline logic for backward compat; all tests pass |
| 11 | Step banners (e.g. [1/6] RCAC) print as pipeline progresses | ✓ VERIFIED | pipeline.py line 211: `con.rule(f"[bold]{label}")` with `_STEP_LABELS` dict containing "[1/6] RCAC" through "[6/6] Evaluation" |

**Score:** 11/11 truths verified (automated)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/sip_engine/classifiers/ui/config_screen.py` | Fixed TUI rendering with Layout instead of Group at screen level | ✓ VERIFIED | 608 lines; `from rich.layout import Layout` at line 16; `_make_screen_layout()` helper at line 225; `Group(*lines)` inside Panel at lines 318, 433, 553; all 3 `_make_layout()` return `Layout` |
| `src/sip_engine/pipeline.py` | PipelineConfig dataclass + run_*() functions + run_pipeline() orchestrator | ✓ VERIFIED | 233 lines; frozen dataclass at line 19; STEP_NAMES at line 38; 6 run_*() functions with lazy imports (lines 61-128); run_pipeline() orchestrator at line 159; _STEP_FN_NAMES for dynamic dispatch |
| `src/sip_engine/__main__.py` | Thin CLI dispatch delegating to pipeline.py | ✓ VERIFIED | 539 lines; 4 `from sip_engine.pipeline import` statements (lines 278, 289, 331, 455); run-pipeline block delegates to run_pipeline() at line 510; --start-from flag at line 186 |
| `tests/classifiers/test_pipeline.py` | Unit tests for PipelineConfig, step validation, orchestrator logic | ✓ VERIFIED | 234 lines (≥ 60 min); 21 tests across 4 classes; all pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `config_screen.py _make_layout()` | `rich.layout.Layout` | `Layout.split_column()` with explicit size for hardware panel | ✓ WIRED | Line 238: `layout.split_column(*parts)` with `Layout(hw_panel, name="hardware", size=8)` at line 236 |
| `config_screen.py config panel content` | `rich.console.Group` | `Group(*lines)` inside Panel | ✓ WIRED | Lines 318, 433, 553: `Panel(Group(*lines), title=..., border_style=...)` |
| `__main__.py run-pipeline block` | `pipeline.py run_pipeline()` | Function call with PipelineConfig | ✓ WIRED | Line 455: `from sip_engine.pipeline import PipelineConfig, run_pipeline`; Line 510: `run_pipeline(cfg, start_from=args.start_from)` |
| `__main__.py standalone commands` | `pipeline.py run_*() functions` | Function call with PipelineConfig | ✓ WIRED | Lines 278, 289, 331: build-rcac→run_rcac, build-labels→run_labels, build-iric→run_iric |
| `pipeline.py run_*() functions` | Domain modules (rcac_builder, label_builder, etc.) | Lazy imports inside function bodies | ✓ WIRED | 6 lazy imports confirmed: lines 63, 70, 77, 91, 98, 120 — all inside function bodies |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TUI-FIX-01 | 14-01 | Hardware panel rendering restored | ✓ SATISFIED | `_build_hardware_panel()` called in all 3 layouts; placed in Layout with explicit size |
| TUI-FIX-02 | 14-01 | Header instruction text visible | ✓ SATISFIED | Header Text appended to lines list in all 3 config screens; rendered via `Group(*lines)` |
| TUI-FIX-03 | 14-01 | Panel border clipping fixed | ✓ SATISFIED | Layout.split_column() with size hints replaces Group at screen level |
| PIPE-01 | 14-02 | run-pipeline delegates to coordinator | ✓ SATISFIED | `run_pipeline(cfg, start_from=...)` at line 510; no inline step logic |
| PIPE-02 | 14-02 | --start-from resume support | ✓ SATISFIED | argparse choices + pipeline.py STEP_NAMES slicing; tested |
| PIPE-03 | 14-02 | --force rebuild all | ✓ SATISFIED | PipelineConfig.force propagated to all run_*() → domain modules |
| PIPE-04 | 14-02 | Centralized hardware config at pipeline start | ✓ SATISFIED | Single detect_hardware() + show_pipeline_config_screen() in __main__.py; PipelineConfig flows to all steps |

**Note:** No `.planning/REQUIREMENTS.md` file exists. Requirement IDs are defined only in PLAN frontmatter. No orphaned requirements detected.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None found | — | — |

No TODO, FIXME, PLACEHOLDER, or stub patterns found in any modified files (`pipeline.py`, `__main__.py`, `config_screen.py`).

### Human Verification Required

### 1. Training Config Screen TUI Rendering

**Test:** Run `python -m sip_engine train --no-stats` in a terminal ≥ 80×24
**Expected:**
- "Detected Hardware" panel renders at top with full borders (all 4 sides) and 5 info lines (OS, CPU, RAM, GPU, Container)
- "Training Settings" panel has complete borders (left + right + top + bottom)
- Header text "Training Configuration (↑↓ select, ←→ adjust, type number, Enter to confirm)" is visible inside the config panel
- Press `q` to quit
**Why human:** Rich Live(screen=True) alternate buffer rendering cannot be tested programmatically

### 2. Feature Build Config Screen TUI Rendering

**Test:** Run `python -m sip_engine build-features` in a terminal ≥ 80×24
**Expected:**
- Same layout: hardware panel at top with full borders, "Feature Build Settings" panel below with full borders
- Header text "Feature Build Configuration (↑↓ select, ←→ adjust...)" visible
- Press `q` to quit
**Why human:** Alternate buffer rendering needs visual terminal inspection

### 3. Pipeline Config Screen TUI Rendering

**Test:** Run `python -m sip_engine run-pipeline` in a terminal ≥ 80×24
**Expected:**
- "SIP Pipeline — Full Run" header panel at very top
- "Detected Hardware" panel below it
- "Full Pipeline Settings" config panel below that with instruction header
- Press `q` to quit
**Why human:** Three-panel layout with header is the most complex arrangement — needs visual confirmation

### Test Results

| Test Suite | Result | Details |
|------------|--------|---------|
| `tests/classifiers/test_pipeline.py` | 21 passed | PipelineConfig, step registry, run_* delegation, orchestrator logic |
| `tests/classifiers/test_ui.py` | 20 passed | Existing UI tests unbroken |
| CLI `--help` validation | ✓ | All 10 commands visible; `run-pipeline --help` shows `--start-from` and `--force` |

### Commits Verified

| Commit | Message | Status |
|--------|---------|--------|
| `5ac303d` | fix(14-01): replace Group with Layout in all three config screen _make_layout() closures | ✓ EXISTS |
| `c3357f5` | feat(14-02): create pipeline.py coordinator with PipelineConfig and step functions | ✓ EXISTS |
| `d4e6d5e` | refactor(14-02): thin CLI dispatch via pipeline.py coordinator | ✓ EXISTS |

### Gaps Summary

No automated gaps found. All 11 observable truths verified through code analysis. All artifacts exist, are substantive, and are properly wired. All 7 requirement IDs are satisfied. No anti-patterns detected. 41 tests pass across both test suites.

**Human verification is required** for the 3 TUI visual rendering checks — the structural code changes are correct (Layout with split_column + explicit sizes replaces Group at screen level), but visual confirmation in a real terminal is needed to fully close the TUI-FIX requirements.

---

_Verified: 2026-03-06T19:46:39Z_
_Verifier: Claude (gsd-verifier)_
