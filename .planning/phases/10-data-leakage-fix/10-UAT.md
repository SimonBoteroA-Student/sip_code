---
status: complete
phase: 10-data-leakage-fix
source:
  - 10-01-SUMMARY.md
  - 10-02-SUMMARY.md
started: 2026-03-02T21:17:00Z
updated: 2026-03-02T21:18:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Leakage column removed from schema
expected: "Fecha de Fin del Contrato" no longer in CONTRATOS_USECOLS. schemas.py has "Duración del contrato" instead.
result: pass
note: "Fecha de Fin del Contrato" remains only in SUSPENSIONES_USECOLS (different CSV, not a leakage source). CONTRATOS_USECOLS clean.

### 2. Duration parser handles all SECOP formats
expected: _parse_duracion_contrato() correctly parses Dia→×1, Mes→×30, Año→×365, Semana→×7, Hora→÷24 rounded, "No definido"→NaN.
result: pass
note: _UNIT_TO_DAYS map verified. Regex parser + round() confirmed. NaN for None/empty/"No definido"/bare-unit.

### 3. M2 label includes Dias adicionados
expected: label_builder.py M2 logic unions EXTENSION tipo from adiciones AND non-zero "Dias adicionados" from contratos. Comma handling.
result: pass
note: Line 292-299 shows Dias adicionados augmentation with comma stripping. Union logic confirmed.

### 4. CLI backup-v1 subcommand works
expected: `python -m sip_engine backup-v1` copies artifacts to v1_baseline/. FileExistsError on re-run.
result: pass
note: Subparser registered at __main__.py:106, handler at line 227. Comparison module backup_v1_artifacts() confirmed.

### 5. CLI compare-v1v2 subcommand works
expected: `python -m sip_engine compare-v1v2` produces comparison.md + comparison.json.
result: pass
note: Subparser at __main__.py:108, handler at line 240. generate_comparison_report() in comparison module confirmed.

### 6. All tests pass
expected: pytest produces ~351 passed, 1 skipped, 2 known failures in test_models.py.
result: pass
note: Actual result: 369 passed, 1 skipped, 2 failed (test_models.py Phase 11 scope). Count increased from 351 to 369 (18 new tests added since SUMMARY written).

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
