# Deferred Items — Phase 08-evaluation

## Out-of-Scope Issues Discovered During 08-01

### Pre-existing iric test failures

**Discovered during:** Task 2 (full test suite run)

**Issue:** 3 tests in `tests/test_iric.py` were failing:
- `TestHistorialProveedorAlto::test_historial_proveedor_alto_fires_above_p95`
- `TestProveedorSobrecostosPrevios::test_proveedor_sobrecostos_previos_with_history`
- `TestProveedorRetrasosPrevios::test_proveedor_retrasos_previos_with_history`

**Root cause:** Pre-existing uncommitted modifications to `src/sip_engine/iric/calculator.py`
(along with `__main__.py`, `data/label_builder.py`, `data/loaders.py`) that existed before
the 08-01 plan execution. The failures reproduce when those stashed changes are present,
and tests pass without them.

**Action:** Out of scope — not caused by evaluation module changes. Defer to the session
that addresses those uncommitted modifications.
