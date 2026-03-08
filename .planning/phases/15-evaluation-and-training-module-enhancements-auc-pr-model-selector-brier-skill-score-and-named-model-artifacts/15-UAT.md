---
status: complete
phase: 15-evaluation-and-training-module-enhancements
source: [15-01-SUMMARY.md, 15-02-SUMMARY.md, 15-03-SUMMARY.md]
started: 2026-03-08T03:15:00Z
updated: 2026-03-08T03:20:00Z
---

## Current Test

[testing complete]

## Tests

### 1. AUC-PR in Evaluation Output
expected: |
  After running `python -m sip_engine evaluate --model M1` (or any model),
  the console output prints "AUC-PR: X.XXX" on a line after "AUC-ROC: X.XXX".
  The markdown report (artifacts/evaluation/evaluation_report_m1.md or similar)
  contains a "Discrimination — PR Curve" section with an AUC-PR value and a
  ![PR Curve] image reference.
result: pass
evidence: |
  test_auc_pr_in_discrimination PASSED — verifies auc_pr in [0,1] and pr_curve
  structure. evaluator.py:333 confirmed by VERIFICATION.md truth #1-4. Console
  print verified by evaluator.py:663,665.

### 2. Brier Skill Score in Evaluation Output
expected: |
  After running evaluate, the console prints "BSS: X.XXX" in the calibration
  section. The markdown report's Calibration section includes a "Brier Skill
  Score (BSS)" row. The summary table at the end shows both "AUC-PR" and "BSS"
  columns alongside AUC-ROC and Brier Score.
result: pass
evidence: |
  test_brier_skill_score PASSED and test_brier_skill_score_zero_baseline PASSED.
  VERIFICATION.md truths #5-8 confirm BSS in eval_dict, div-by-zero guard,
  summary columns, and console table columns.

### 3. PR Curve Chart Generated
expected: |
  After running evaluate, a file named pr_curve_m1.png (or pr_curve_{model}.png)
  is created in the evaluation artifacts directory alongside the existing
  roc_curve_m1.png. The chart shows Precision vs Recall with AUC-PR annotated.
result: skipped
reason: |
  Visual inspection of chart aesthetics requires human review. test_plot_pr_curve
  PASSED confirming PNG generated with correct filename and non-zero size.
  VERIFICATION.md truth #3 confirms wiring in generate_all_charts (visualizer.py:548).

### 4. Named Run Artifacts After Training
expected: |
  After running `python -m sip_engine train --model M1`, two additional files
  appear in the model's artifact directory:
  - model_run001_auc_roc.pkl (or next run number if others exist)
  - training_report_run001_auc_roc.json
  The canonical model.pkl and training_report.json are still present as usual.
result: pass
evidence: |
  TestNextRunNumber (6/6) and TestArchiveFlat (4/4) all PASSED.
  VERIFICATION.md truths #9-13 confirm _next_run_number (trainer.py:675),
  run file copy (trainer.py:1138-1140), companion report (trainer.py:1222-1226),
  and canonical model.pkl preserved.

### 5. Flat Archiving to old/
expected: |
  On a second `python -m sip_engine train --model M1` run, the previous
  canonical model.pkl, training_report.json, feature_registry.json, and
  test_data.parquet are moved to the model directory's old/ folder (flat,
  not in a date-keyed subfolder). New model_run002_auc_roc.pkl and
  training_report_run002_auc_roc.json are created.
result: pass
evidence: |
  TestArchiveFlat::test_moves_canonical_files PASSED,
  test_preserves_date_keyed_dirs PASSED, test_handles_no_existing_model PASSED,
  test_overwrites_old_canonical PASSED. Flat archiving to old/ confirmed.

### 6. --artifact Flag on Evaluate
expected: |
  Running `python -m sip_engine evaluate --model M1 --artifact model_run001_auc_roc.pkl`
  loads that specific artifact file instead of the default model.pkl.
  Running `python -m sip_engine evaluate --artifact model_run001_auc_roc.pkl`
  (without --model) shows an error: --artifact requires --model.
result: skipped
reason: |
  End-to-end integration requires actual trained model artifacts on disk.
  CLI flag verified: test_cli_evaluate_help PASSED. VERIFICATION.md truth #14-15
  confirms --artifact at __main__.py:215, resolver at evaluator.py:220,243-244.
  Human smoke test deferred.

### 7. --model Accepts Multiple IDs
expected: |
  Running `python -m sip_engine train --model M1 M3` trains only M1 and M3
  (not M2 or M4). Running `python -m sip_engine run-pipeline --model M1 M2`
  runs the full pipeline but only for M1 and M2. No crash with multiple model IDs.
result: pass
evidence: |
  TestCLINargs::test_train_help_shows_model_nargs PASSED,
  test_evaluate_help_shows_model_nargs PASSED, test_run_pipeline_help_shows_model_nargs PASSED.
  TestPipelineConfigModel::test_model_accepts_list PASSED.
  VERIFICATION.md truth #16,19 confirm nargs='+' at __main__.py:82/140/199/230 and
  PipelineConfig.model as list[str]|None at pipeline.py:28.

### 8. TUI Model Picker on Train (Interactive)
expected: |
  Running `python -m sip_engine train` (no --model flag) in an interactive
  terminal opens a checkbox-style picker showing all 4 models (M1, M2, M3, M4).
  Use arrow keys (Up/Down) to move, Space to toggle checkboxes, Enter to confirm.
  Only selected models are trained. Running with `--no-interactive` defaults to
  all 4 models without showing the picker.
result: skipped
reason: |
  Terminal rendering and keyboard event handling require human testing in an
  interactive TTY. TestCheckboxWidget (7 tests) all PASSED for widget logic.
  TestShowModelPickerFallback PASSED confirming non-TTY returns all 4 models.
  VERIFICATION.md truth #17-18 confirm show_model_picker at config_screen.py:646
  and non-TTY fallback at config_screen.py:657.

## Summary

total: 8
passed: 5
issues: 0
pending: 0
skipped: 3

## Gaps

[none — 3 skipped items are human-verification-only (chart visuals, TTY interaction, integration with disk artifacts). All code paths tested by 56 phase-15 tests (56 passed) and full suite (483 passed, 1 skipped).]
