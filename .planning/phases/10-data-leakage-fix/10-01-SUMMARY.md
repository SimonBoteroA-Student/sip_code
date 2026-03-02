# Plan 10-01 Summary: Duration Leakage Fix

**Status:** Complete
**Duration:** ~8 min

## What Changed

1. **schemas.py**: Added "Duración del contrato" (str) + "Dias adicionados" (str) to CONTRATOS_USECOLS; removed "Fecha de Fin del Contrato"
2. **category_b.py**: Added `_parse_duracion_contrato()` with regex parser for all 6 SECOP formats (Dia/Mes/Año/Semana/Hora/No definido); updated `compute_category_b()` to use it
3. **conftest.py**: Updated 3 CSV fixtures (tiny_contratos, bad_byte, missing_column) with new columns
4. **test_features.py**: Replaced all 18 "Fecha de Fin del Contrato" references; added `TestParseDuracionContrato` class with 12 edge case tests
5. **test_labels.py**: Updated CSV header and row template to match new schema

## Verification

- 88 feature tests pass (76 original + 12 new)
- 349 total tests pass + 1 skipped
- 2 pre-existing failures in test_models.py (Phase 11 scope)
- Zero references to "Fecha de Fin del Contrato" in modified files

## Key Decision

- Duration text parsed to days: Mes×30, Año×365, Semana×7, Hora÷24 (rounded)
- "No definido" (5.2% of data) → NaN (XGBoost handles natively)
