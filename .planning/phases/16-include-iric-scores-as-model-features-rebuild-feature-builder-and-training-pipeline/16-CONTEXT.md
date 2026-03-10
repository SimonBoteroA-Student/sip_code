# Phase 16 Context — IRIC Scores as Model Features

**Phase:** 16 — Include IRIC scores as model features — rebuild feature builder and training pipeline
**Discussed:** 2026-03-10

---

## A — Which IRIC Outputs Become Features

**Decision:** Include all IRIC sub-scores AND threshold flags as features. Composite score is NOT added separately (it would be redundant with sub-scores).

- Sub-scores: all individual IRIC dimensions (price anomaly, bid concentration, urgency, etc.) become separate columns in the feature matrix.
- Threshold flags: binary flagged/not-flagged per dimension also included alongside continuous scores.
- Existing 34 features are preserved as-is — IRIC columns are purely additive.

**Granularity:** IRIC scores are one-to-one with training rows (contract-level). No join complexity.

**⚠ Research required — leakage audit:**
It is unknown whether any IRIC components aggregate entity behavior across the full dataset (e.g., entity-level score computed across all contracts including future ones). Researcher must audit each IRIC sub-score to determine if any are forward-looking. Any leaky component must be excluded or time-bounded before it can be used as a feature.

---

## B — Pipeline Step Ordering

**Decision:** `build-iric` becomes a named pipeline step that runs before `build-features`.

- `iric` is inserted as an explicit `--start-from` resume point (between `rcac`/`labels` and `features`).
- `build-features` auto-triggers `build-iric` if IRIC output is not found on disk — no hard stop.
- `--start-from features` remains valid but at runtime validates that IRIC output exists; if not, IRIC runs automatically first.

**Step order (updated):** `download → rcac → labels → iric → features → train → evaluate`

---

## C — Scope of the Rebuild

**Feature builder:** Additive change only — load IRIC output file (CSV/parquet on disk), merge IRIC columns into the existing feature matrix. No structural rewrite of the builder.

**Training pipeline:** Models are retrained on the new feature set. No training code changes beyond the feature schema update. No hyperparameter re-tuning, no schema versioning, no additional evaluation reruns — just retrain.

---

## D — Inference-Time IRIC

**Decision:** At inference time, IRIC is computed on-the-fly. The inference path runs the IRIC module for each contract before scoring — IRIC scores are not expected to be pre-computed and passed in.

This increases inference complexity but is the correct design for a self-contained scoring path.

**Validation behavior:** If IRIC columns are missing from the feature matrix, the feature builder warns (logs a warning) but continues and produces the feature matrix without them. Hard failure is not enforced.

---

## Deferred Ideas

- Feature schema versioning per model artifact (track which schema each model was trained on) — not part of this phase.
- Hyperparameter re-tuning after IRIC integration — not part of this phase.
- Full feature builder refactor to support pluggable sources — not part of this phase.
