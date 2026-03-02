# Phase 6: IRIC — Implementation Context

**Created:** 2026-03-01
**Phase Goal:** 11-component irregularity index calculated, nationally calibrated by contract type using training data only, added as model feature

## Decisions

### 1. Component Firing Rules

**Decision:** Follow the literature (Gallego et al. 2021, Imhof 2018, VigIA/Salazar 2024) for all 11 component definitions. Research agent must extract exact formulas from these papers.

**Specifics locked:**
- **Threshold-based components** (`historial_proveedor_alto`, `periodo_publicidad_extremo`, `periodo_decision_extremo`): Use **percentile-based** thresholds from `iric_thresholds.json` (P95/P99). No fixed absolute values.
- **`proveedor_multiproposito`**: Defined by **UNSPSC diversity** — provider bids across multiple distinct UNSPSC segments. Threshold for "multiple" comes from literature or calibrated percentiles.
- **`historial_proveedor_alto`**: **Volume outlier** — provider has more prior contracts than the P95/P99 of all providers. Not about win concentration or category dominance.
- **Straightforward components** (e.g., `unico_proponente` = 1 bidder, `contratacion_directa` = direct contracting modality, `regimen_especial` = special regime) should fire on their obvious conditions.

**Research directive:** Extract exact firing rules from Gallego et al. (2021) and VigIA code/documentation. Also check local VigIA folders for implementation reference.

### 2. Missing Data Scope (`datos_faltantes`)

**Decision:** Curated list of critical transparency fields, modality-aware, any missing = 1.

**Specifics locked:**
- **Field selection:** A curated list of fields that SHOULD be present for transparency purposes (not all contract columns). Research agent should determine which fields Gallego/VigIA consider critical.
- **Trigger mode:** Binary — if ANY single critical field from the curated list is missing/empty, the flag fires (= 1).
- **Modality-aware:** Different `modalidad_contratacion` values have different expected fields. Direct contracting legitimately lacks bid-related fields — those absences should NOT trigger the flag. The curated list must be conditioned on modality.
- **Scope includes data quality:** Flag covers both publication incompleteness (what the entity chose not to disclose) AND data quality issues (parsing failures, encoding errors that resulted in missing values).

### 3. Calibration Segmentation

**Decision:** Segment by `tipo_contrato`, merge rare types, Phase 6 builds machinery only.

**Specifics locked:**
- **Segmentation variable:** `tipo_contrato` (e.g., Prestacion de Servicios, Compraventa, Obra, Suministro). NOT modalidad, NOT cross-product.
- **Sparse groups:** Contract types with fewer than a minimum observation count (research should determine threshold, suggest 30) are merged into an "Other" category for percentile computation.
- **Phase 6 scope:** Build the calibration FUNCTION (code that computes percentiles given a DataFrame). The actual `iric_thresholds.json` artifact is produced in Phase 7 AFTER the train/test split is defined. Phase 6 produces the machinery, not the final artifact.
- **Percentile dual role:**
  - Component flags fire based on **literature-defined rules** (Gallego/VigIA). The percentiles may be USED by those rules (e.g., "extreme" = above P95 for that tipo_contrato).
  - Percentiles are ALSO stored as **context for risk interpretation** — downstream reporting and API responses can reference where a contract falls relative to national percentiles.
- **Percentiles computed:** P1, P5, P95, P99 for each relevant continuous variable, segmented by tipo_contrato.

## Deferred Ideas

None raised during discussion.

## Research Directives

The research agent MUST:
1. Extract exact IRIC component definitions from Gallego et al. (2021) and Imhof (2018)
2. Check local VigIA folders (`Data/Propia/` or similar) for implementation code that defines component rules
3. Identify which contract fields Gallego/VigIA consider critical for `datos_faltantes`
4. Determine modality-specific field expectations for the datos_faltantes curated list
5. Find the exact kurtosis and DRN (diferencia relativa normalizada) formulas from Imhof (2018)

## Integration Notes

- IRIC scores (`iric_score`, `iric_competencia`, `iric_transparencia`, `iric_anomalias`) become Category D features in `pipeline.py` (FEAT-04)
- IRIC components 9-10 (`proveedor_sobrecostos_previos`, `proveedor_retrasos_previos`) reuse data from the Provider History Index built in Phase 5
- IRIC component 11 (`ausencia_proceso`) needs definition from literature — likely contracts with no linked procurement process in SECOP
