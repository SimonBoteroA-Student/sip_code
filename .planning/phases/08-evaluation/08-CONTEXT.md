# Phase 8: Evaluation - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

All 4 XGBoost models (M1 cost overruns, M2 delays, M3 Comptroller records, M4 SECOP fines) are comprehensively evaluated with academic metrics, and structured evaluation reports (JSON + CSV + Markdown) are generated per model. No model retraining, no new features, no explainability — just measurement and reporting of existing model performance.

</domain>

<decisions>
## Implementation Decisions

### Threshold & k-Value Selection
- Precision/Recall computed at a fine sweep: every 0.05 from 0.05 to 0.95 (19 thresholds)
- MAP@k computed at k=100, k=500, k=1000
- NDCG@k uses the same k values as MAP: k=100, k=500, k=1000 (consistency)
- Optimal threshold (maximizing F1 on test set) computed and reported per model as a recommended operating point

### Report Structure & Content
- Three output formats per model: JSON (machine-readable), CSV (tabular), Markdown (human-readable)
- JSON includes ROC curve data points (FPR/TPR pairs) for plot-ready output
- Confusion matrices included at each decision threshold
- Class imbalance strategy comparison results from Phase 7 included (both strategies' CV scores) — documents selection rationale
- Full hyperparameter search history (all 200 iterations) included — shows optimization landscape
- Label prevalence and test set size included per model for metric contextualization

### Cross-Model Comparison
- Per-model reports at `artifacts/evaluation/M{n}/` PLUS a cross-model summary (`summary.json` + `summary.csv`)
- Console output: verbose — print all metrics during evaluation, ending with a formatted summary table of key metrics across all 4 models
- No minimum performance thresholds or pass/fail gates — metrics reported as-is (academic context)
- Summary report includes dataset context: test set size, label prevalence per model

### Evaluation CLI & Workflow
- `sip evaluate` runs all 4 models; `sip evaluate --model M1` runs a single model
- Re-runs produce timestamped versions (e.g., `M1_eval_2026-03-02.json`) — no overwrite
- Auto-discovers models from `artifacts/models/M*/model.pkl` by default, with optional `--models-dir` override
- Output structure: `artifacts/evaluation/M{n}/` per-model subdirectories mirroring model artifact structure

### Claude's Discretion
- Exact threshold sweep for decision thresholds (Precision/Recall) — Claude decided on 0.05 to 0.95 in 0.05 increments per user correction
- Internal metric computation approach (sklearn vs manual) — choose what's most reliable
- Markdown report formatting and section ordering
- Console table library choice (rich, tabulate, etc.)

</decisions>

<specifics>
## Specific Ideas

- Report format inspiration: academic ML paper appendix — full metrics with context
- Hyperparameter search history preserves the optimization landscape for analysis
- Strategy comparison data carries forward from `training_report.json` artifacts produced in Phase 7

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-evaluation*
*Context gathered: 2026-03-02*
