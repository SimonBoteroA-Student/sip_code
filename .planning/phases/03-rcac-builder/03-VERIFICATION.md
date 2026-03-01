---
phase: 03-rcac-builder
verified: 2026-03-01T16:30:00Z
status: passed
score: 14/14 must-haves verified
re_verification: false
gaps: []
human_verification: []
---

# Phase 3: RCAC Builder Verification Report

**Phase Goal:** A validated Consolidated Corruption Background Registry (RCAC) built from 6 sanction sources, serialized to artifacts/rcac.pkl, providing O(1) lookup by (document_type, document_number)
**Verified:** 2026-03-01T16:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

Combined must-haves from Plan 03-01 and Plan 03-02.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Document numbers are normalized to digit-only strings with dots, dashes, spaces stripped | VERIFIED | `normalize_numero` in rcac_builder.py:81-98; 5 passing tests (test_normalize_numero_*) |
| 2 | Document types from all sources map to controlled catalog CC/NIT/CE/PASAPORTE/OTRO | VERIFIED | `normalize_tipo` in rcac_builder.py:133-169; 12 passing tests (test_normalize_tipo_*) including accent-insensitive forms |
| 3 | Malformed IDs (empty, all-zeros, <3 digits) are excluded from lookup index and logged to bad-rows CSV | VERIFIED | `is_malformed` + build_rcac bad_rows separation (lines 366-382); tests test_build_malformed_excluded_from_index and test_build_bad_rows_log_written both pass |
| 4 | Records from multiple sources for the same (tipo, num) are deduplicated into one row with boolean source flags | VERIFIED | `defaultdict(set)` keyed on (tipo_norm, num_norm) in build_rcac lines 386-389; test_build_dedup_same_person_two_sources passes with en_boletines=True, en_siri=True |
| 5 | num_fuentes_distintas correctly counts distinct sources, not raw rows | VERIFIED | `len(seen_sources)` at line 403; test_build_dedup_duplicate_rows_same_source confirms single-source count = 1 |
| 6 | RCAC is serialized to artifacts/rcac.pkl via joblib | VERIFIED | `joblib.dump(index, rcac_path)` at line 422; test_build_creates_pkl passes |
| 7 | en_sanciones_penales is always False (no person-level data in FGN source) | VERIFIED | Hardcoded `False` at line 402; test_build_sanciones_penales_always_false passes for all records |
| 8 | Sources without tipo_documento (resp_fiscales, multas) use name-pattern + length heuristic to infer CC vs NIT | VERIFIED | `_infer_tipo` at lines 172-203, 14 company keywords + 9-digit threshold; 5 passing tests (test_infer_tipo_*) |
| 9 | rcac_lookup(tipo_doc, num_doc) returns full record dict for known identities in O(1) | VERIFIED | `rcac_lookup` in rcac_lookup.py:98-125, dict.get() on in-memory index; test_lookup_hit_returns_record passes with all 10 expected keys |
| 10 | rcac_lookup returns None for unknown, malformed, or missing identities | VERIFIED | is_malformed short-circuit at line 121-122, index.get returns None; test_lookup_miss_returns_none, test_lookup_malformed_returns_none both pass |
| 11 | rcac_lookup normalizes inputs internally so callers do not need to pre-normalize | VERIFIED | normalize_tipo/normalize_numero called internally at lines 118-119; test_lookup_normalizes_input passes ('43.922.546' hits '43922546' record) |
| 12 | RCAC index is loaded lazily on first lookup call and cached in module state | VERIFIED | `_rcac_index: dict | None = None` + guard in get_rcac_index() lines 82-84; test_lookup_without_pkl_raises confirms FileNotFoundError when no pkl; test_build_cache_used confirms mtime unchanged without force |
| 13 | python -m sip_engine build-rcac runs the builder; --force triggers rebuild | VERIFIED | CLI dispatch at __main__.py:33-41, --force arg at line 18-22; confirmed via `python -m sip_engine build-rcac --help` output |
| 14 | rcac_lookup and build_rcac are importable from sip_engine.data | VERIFIED | Explicit imports and __all__ entries in data/__init__.py lines 19-20 and 37-38; confirmed via `from sip_engine.data import rcac_lookup, build_rcac` |

**Score:** 14/14 truths verified

---

### Required Artifacts

| Artifact | Min Lines | Actual Lines | Status | Details |
|----------|-----------|--------------|--------|---------|
| `src/sip_engine/data/rcac_builder.py` | 200 | 431 | VERIFIED | Contains build_rcac(), normalize_tipo(), normalize_numero(), is_malformed(), _infer_tipo(), 5 source extractors |
| `src/sip_engine/config/settings.py` | — | — | VERIFIED | Contains `rcac_bad_rows_path` field (line 106) and __post_init__ assignment (line 180) |
| `tests/test_rcac.py` | 150 | 473 | VERIFIED | 40 tests covering normalization, tipo mapping, tipo inference, deduplication, serialization, bad-rows logging, and lookup |
| `src/sip_engine/data/rcac_lookup.py` | 60 | 125 | VERIFIED | Contains rcac_lookup(), _load_rcac(), get_rcac_index(), reset_rcac_cache() |
| `src/sip_engine/__main__.py` | — | — | VERIFIED | build-rcac subparser with --force arg, dispatches to build_rcac() with try/except and sys.exit codes |
| `src/sip_engine/data/__init__.py` | — | — | VERIFIED | Re-exports build_rcac and rcac_lookup; both in __all__ |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `rcac_builder.py` | `loaders.py` | `from sip_engine.data.loaders import load_boletines, load_paco_siri, ...` | WIRED | Lines 34-40: imports all 5 used loaders explicitly |
| `rcac_builder.py` | `settings.py` | `get_settings()` for rcac_path and rcac_bad_rows_path | WIRED | Lines 33 and 346-347, 410: get_settings() called, both paths used |
| `rcac_lookup.py` | `rcac_builder.py` | `from sip_engine.data.rcac_builder import normalize_tipo, normalize_numero, is_malformed` | WIRED | Line 23: explicit import; all three used at lines 118-121 |
| `rcac_lookup.py` | `artifacts/rcac/rcac.pkl` | `joblib.load()` on first call | WIRED | `_load_rcac()` at line 61: `_rcac_index = joblib.load(rcac_path)` |
| `__main__.py` | `rcac_builder.py` | `from sip_engine.data.rcac_builder import build_rcac` | WIRED | Line 34: deferred import inside if-block, called at line 36 |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DATA-01 | 03-01 | Build RCAC from 6 core sources | SATISFIED | 5 source extractors implemented + sanciones_penales always False (v1 limitation per design); all 6 source flags present in every record |
| DATA-02 | 03-01 | Normalize documento identifiers to controlled catalog | SATISFIED | normalize_numero strips all non-digits; normalize_tipo maps 10+ raw strings; 17 normalization tests passing |
| DATA-03 | 03-01 | Deduplicate RCAC records by (tipo, num), track num_fuentes_distintas | SATISFIED | defaultdict(set) dedup strategy; num_fuentes_distintas = len(seen_sources); 2 dedup tests passing |
| DATA-04 | 03-01 | Handle SIRI file positional column parsing (no headers) | SATISFIED | load_paco_siri() in schemas/loaders (Phase 2) produces tipo_documento/numero_documento columns; _extract_siri() reads them correctly |
| DATA-05 | 03-01 | Handle resp_fiscales combined "Tipo y Num Documento" field | SATISFIED | _extract_resp_fiscales() reads "Tipo y Num Docuemento" as numero, uses _infer_tipo() for tipo; confirmed by CONTEXT.md that field is purely numeric |
| DATA-08 | 03-01 | Serialize RCAC as indexed dict via joblib | SATISFIED | joblib.dump(index, rcac_path) in build_rcac(); test_build_creates_pkl passes |
| DATA-09 | 03-02 | O(1) RCAC lookup by (document_type, document_number) | SATISFIED | rcac_lookup() uses dict.get() on in-memory dict; 6 lookup tests passing including hit, miss, input normalization, malformed rejection |

**All 7 requirements claimed by Phase 3 plans are SATISFIED.**

No orphaned requirements: REQUIREMENTS.md traceability table maps DATA-01 through DATA-09 (excluding DATA-06, DATA-07, DATA-10 which are Phase 2) to Phase 3, all accounted for.

---

### Anti-Patterns Found

None. Grep over rcac_builder.py, rcac_lookup.py, and data/__init__.py found zero occurrences of TODO/FIXME/XXX/HACK/PLACEHOLDER/placeholder/stub patterns or empty return values.

---

### Human Verification Required

None. All behaviors verified programmatically via the test suite (40 tests, 100% passing). The following items are noteworthy but do not require human verification:

- The actual `artifacts/rcac.pkl` file is not present in the repository (it is gitignored as expected — it is a build artifact). The `build_rcac()` pipeline has been verified correct by tests using tmp_path fixtures.
- Real-world correctness of `_infer_tipo` heuristics against actual PACO data cannot be assessed without running against live files, but the 9-digit NIT threshold and 14 company keywords are grounded in Colombian document ID conventions and documented in CONTEXT.md.

---

### Test Suite Summary

| Suite | Tests | Pass | Fail | Status |
|-------|-------|------|------|--------|
| tests/test_rcac.py (RCAC only) | 40 | 40 | 0 | ALL PASS |
| tests/ (full suite) | 65 | 65 | 0 | ALL PASS — no regressions |

Phase 1/2 tests (25 loader tests, conftest fixtures) all continue to pass.

---

## Gaps Summary

No gaps. All 14 must-have truths verified, all 6 artifacts substantive and wired, all 5 key links confirmed, all 7 requirements satisfied, 65 tests passing with zero failures.

---

_Verified: 2026-03-01T16:30:00Z_
_Verifier: Claude (gsd-verifier)_
