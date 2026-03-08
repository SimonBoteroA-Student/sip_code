---
phase: 15-evaluation-and-training-module-enhancements
plan: "03"
subsystem: classifiers/ui, pipeline, cli
tags: [model-selector, tui, cli, nargs, checkbox-picker, pipeline-config]
dependency_graph:
  requires: ["15-02"]
  provides: ["multi-model --model flag", "TUI checkbox picker", "PipelineConfig list[str] model type"]
  affects: ["__main__.py", "pipeline.py", "config_screen.py"]
tech_stack:
  added: []
  patterns: ["nargs='+' argparse multi-value", "Rich Live checkbox TUI", "fallback for non-TTY stdin"]
key_files:
  created:
    - tests/classifiers/test_model_selector.py
  modified:
    - src/sip_engine/__main__.py
    - src/sip_engine/pipeline.py
    - src/sip_engine/classifiers/ui/config_screen.py
    - tests/classifiers/test_pipeline.py
decisions:
  - "_CheckboxWidget uses set[str] for selected — order-preserving output reconstructed from original list"
  - "show_model_picker uses _KEY_UP/_KEY_DOWN/_KEY_ENTER/_KEY_QUIT constants for consistency with existing _read_key()"
  - "Space key support added to _read_key_unix() and _read_key_win() as ' ' literal"
  - "run_evaluate subset path returns Path('artifacts/evaluation') — consistent return type regardless of subset/all"
  - "evaluate handler does not show TUI picker — just defaults to all models when --model omitted"
metrics:
  duration: "~10 minutes"
  completed: "2026-03-08"
  tasks: 2
  files_changed: 4
  files_created: 1
---

# Phase 15 Plan 03: Multi-Model Selector TUI + nargs='+' CLI Flag Summary

**One-liner:** Interactive Rich checkbox picker and nargs='+' --model flag for selecting model subsets across train, evaluate, and run-pipeline commands.

## What Was Built

### Task 1: TUI Model Picker + --model nargs='+' (3 files)

**`config_screen.py`:**
- Added `_CheckboxWidget` class: multi-select checkbox with Up/Down navigation, Space to toggle, cursor rendering in Rich Text
- Added `show_model_picker()` function: uses `_CheckboxWidget` + Rich `Live` panel, falls back to all models when stdin is not TTY
- Added space key handling to `_read_key_unix()` and `_read_key_win()` (previously returned `""` for space)

**`__main__.py`:**
- Changed `--model` on all three subparsers (`train`, `evaluate`, `run-pipeline`) from single `choices=` to `nargs='+'` with `metavar="MODEL"`
- `train` handler: when `--model` omitted and interactive, calls `show_model_picker()`; with `--no-interactive`, defaults to all 4
- `evaluate` handler: `args.model if args.model else MODEL_IDS` (no TUI picker for evaluate)
- `run-pipeline` handler: model selection with `show_model_picker()` before `PipelineConfig` creation; passes `selected_models` (list or None)

**`pipeline.py`:**
- `PipelineConfig.model` type changed from `str | None = None` → `list[str] | None = None`
- `run_train()`: `cfg.model if cfg.model else MODEL_IDS` (already a list)
- `run_evaluate()`: iterates over `model_ids` list; calls `evaluate_all()` only when all 4 models selected; returns `Path("artifacts/evaluation")` for subsets

### Task 2: Tests (1 new file, 1 updated)

**`tests/classifiers/test_model_selector.py`** (new, 15 tests):
- `TestCheckboxWidget`: toggle, re-toggle, move+toggle, boundary clamps, render type
- `TestShowModelPickerFallback`: non-TTY returns all models, non-TTY with custom ids
- `TestPipelineConfigModel`: list accepted, None default, single-item list
- `TestCLINargs`: subprocess help output checks for `MODEL` metavar on all 3 subcommands

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_pipeline.py string model values incompatible with new list[str] type**
- **Found during:** Task 2 overall verification
- **Issue:** `test_pipeline.py` used `model="M2"`, `model="M1"`, `model="M3"` (strings) which became broken after `PipelineConfig.model` changed to `list[str] | None`. Python iterates strings character by character, so `run_train` called `train_model` twice with `model_id='M'` and `model_id='1'`.
- **Fix:** Changed all string values to list literals (`["M2"]`, `["M1"]`, `["M3"]`); updated `test_run_evaluate_single_model` assertion to `evaluate_model(model_id="M3")` (no artifact) and `result == Path("artifacts/evaluation")`
- **Files modified:** `tests/classifiers/test_pipeline.py`
- **Commit:** `71fd621`

## Self-Check

### Files Created
- [x] `tests/classifiers/test_model_selector.py` — exists

### Files Modified
- [x] `src/sip_engine/__main__.py` — nargs='+' on all 3 subcommands
- [x] `src/sip_engine/pipeline.py` — PipelineConfig.model is list[str]|None
- [x] `src/sip_engine/classifiers/ui/config_screen.py` — _CheckboxWidget + show_model_picker

### Commits
- [x] `3cdcca3` — feat(15-03): multi-model nargs='+' flag + TUI checkbox picker
- [x] `f58fcec` — test(15-03): tests for model picker, CLI nargs, PipelineConfig list type
- [x] `71fd621` — fix(15-03): update test_pipeline.py for list[str] PipelineConfig.model type

## Self-Check: PASSED
