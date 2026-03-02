# Plan 10-02 Summary: M2 Label Fix + Comparison Infrastructure

**Status:** Complete
**Duration:** ~6 min

## What Changed

1. **label_builder.py**: Added "Dias adicionados" to `_load_contratos_base()` needed_cols; augmented M2 from non-zero Dias adicionados (OR with EXTENSION). Comma thousands separator handled.
2. **comparison.py**: New module with `backup_v1_artifacts()` (copies evaluation/features/iric/labels/models to v1_baseline/, skips rcac/, raises FileExistsError on re-run) and `generate_comparison_report()` (reads v1/v2 summary.json, produces comparison.md + comparison.json)
3. **__main__.py**: Added `backup-v1` and `compare-v1v2` CLI subcommands
4. **.gitignore**: Added `!artifacts/v1_baseline/` exception
5. **test_labels.py**: Added `test_m2_from_dias_adicionados` (non-zero→M2=1, zero→M2=0, comma handling) and `test_m2_union_extension_and_dias` (both sources contribute)

## Verification

- 35 label tests pass (33 original + 2 new)
- 351 total tests pass + 1 skipped
- M2_TIPOS constant unchanged (still {"EXTENSION"})
- Comparison module verified with mock artifacts
