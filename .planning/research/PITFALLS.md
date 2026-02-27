# Pitfalls Research

**Domain:** Public procurement corruption detection ML system — Colombian SECOP II data, heterogeneous sanction registry (RCAC), XGBoost models with severe class imbalance, IRIC rules index, SHAP explainability.
**Researched:** 2026-02-27
**Confidence:** HIGH — drawn from academic literature referenced in PROJECT.md (Gallego et al. 2021, VigIA/Salazar et al. 2024, Mojica 2021), direct inspection of actual data files, and established ML failure patterns in this specific domain.

---

## Critical Pitfalls

### Pitfall 1: Temporal Data Leakage via Provider History Features

**What goes wrong:**
Provider history features (`num_contratos_previos`, `num_sobrecostos_previos`, `num_retrasos_previos`, `valor_total_contratos_previos`, `historial_proveedor_alto`) are computed using the entire dataset without respecting the contract signing date as a temporal boundary. A contract signed in 2018 gets enriched with amendments and outcomes that were only known in 2022 — future information bleeds into the feature vector. AUC-ROC inflates dramatically (sometimes 0.85+ vs. a realistic 0.70). The model appears excellent in cross-validation but fails completely in production on new contracts.

**Why it happens:**
It is tempting to compute provider features as a single batch join across all records: `GROUP BY provider_id`. This is computationally simple but ignores the timeline. The VigIA notebook did this correctly but it is easy to replicate naively when porting to a production pipeline.

**How to avoid:**
For every contract being scored, filter the history dataset to records where `Fecha de Firma < current_contract_fecha_firma` before aggregating. Implement a dedicated `compute_provider_history_as_of(provider_id, cutoff_date)` function. Write a unit test that verifies no future dates appear in the history for a given contract. During train/test split, sort by `Fecha de Firma` and cut temporally (e.g., train = contracts before 2022-01-01, test = after) rather than random split. The labels for M1 and M2 (amendments) will not yet exist for recent contracts — this is correct behavior, not a bug.

**Warning signs:**
- AUC-ROC > 0.85 on the test set (unrealistically high for this domain; Gallego et al. achieved ~0.78 for M3)
- Provider history features appearing as top SHAP predictors with very high absolute values
- The model assigns high risk scores to first-time providers (they have no history — but if the aggregation includes future amendments, this makes no sense)
- Discrepancy between CV performance and performance on a known holdout set of recent contracts

**Phase to address:** Phase 2 (Feature Engineering) — the `provider_features.py` module must enforce temporal cutoffs as a core invariant, not an afterthought.

---

### Pitfall 2: Label Construction Contaminates Features for M1 and M2

**What goes wrong:**
M1 (cost overrun) and M2 (delay) labels are derived from `adiciones.csv`. If the feature pipeline joins `adiciones.csv` to `contratos_SECOP.csv` to compute the label, and separately uses `adiciones.csv` to compute provider history features (`num_sobrecostos_previos`, `num_retrasos_previos`), the model can learn the label directly from its own construction pathway — not from genuine pre-execution signals. This is a subtler form of leakage: IRIC components `proveedor_sobrecostos_previos` and `proveedor_retrasos_previos` require a working amendments join, and that exact same join produces the label. If the temporal cutoff is not enforced rigorously, a contract's own amendment is counted in its own provider history feature.

**Why it happens:**
The same source file (`adiciones.csv`) is the data source for both the label (does THIS contract have an amendment?) and provider history features (did the provider have PRIOR amendments on OTHER contracts?). Developers join once and reuse the result without isolating the temporal dimension.

**How to avoid:**
Separate the label construction step completely from the provider history feature step. Build them in distinct modules (`label_builder.py` vs. `provider_features.py`). When computing `num_sobrecostos_previos` for contract C signed on date D, the amendments dataset must be filtered to: (1) different contract ID, AND (2) amendment date (or signing date of the amended contract) < D. Add an assertion: the contract C's own contract_id should never appear in the history used to compute its features.

**Warning signs:**
- `proveedor_sobrecostos_previos` or `proveedor_retrasos_previos` are the strongest SHAP predictors for M1/M2 respectively with implausibly high values
- Model achieves MAP@100 > 0.90 for M1 or M2 (domain ceiling is much lower)
- When you remove all provider history features, AUC drops drastically (by > 0.15)

**Phase to address:** Phase 2 (Feature Engineering) and Phase 3 (Model Training validation step). Label construction must be reviewed before training begins.

---

### Pitfall 3: RCAC Document Number Normalization Fails Silently

**What goes wrong:**
The RCAC is indexed on `(tipo_documento, numero_documento)`. Each source formats these differently: `C.C.` vs. `CC`, `123.456.789` vs. `123456789`, NITs with check digit (`900123456-1`) vs. without, leading zeros stripped in some sources. The normalization routine in `rcac_builder.py` handles the common cases but misses edge cases (CE documents with letters, PASAPORTE with alphanumeric codes, combined field `Tipo y Num Documento` in `responsabilidades_fiscales_PACO.csv` where the type and number are concatenated without a separator in some rows). Result: 20-40% of RCAC records fail to match when cross-referenced against `proveedores_registrados.csv`. The system continues silently — providers appear clean when they are not. Features `proveedor_en_rcac`, `proveedor_responsable_fiscal`, etc. are systematically biased toward zero.

**Why it happens:**
The SIRI file (`sanciones_SIRI_PACO.csv`) has 46K rows and no headers — positional parsing of columns 5 and 6 requires careful inspection of the actual data (confirmed: column 4 = doc type text, column 5 = doc number). Edge rows with `nan` or unusual document types break the normalizer. The `responsabilidades_fiscales_PACO.csv` field `Tipo y Num Documento` has values like `8300401935` (no type prefix) or `CC123456789` (fused), requiring heuristic parsing. Normalization bugs produce zero match counts — which is indistinguishable from "no matches exist" without ground-truth verification.

**How to avoid:**
Build a document normalization test suite with real examples from each source before writing `rcac_builder.py`. Compute match rates per source after the cross-reference join and fail loudly if any source has < 5% match rate (indicates systematic failure). Log mismatches with sample rows. For `responsabilidades_fiscales_PACO.csv`, apply regex to separate type from number: if the entire field is numeric, treat it as NIT; if it starts with letters, separate type prefix from digits. For SIRI, explicitly log column position verification against a known record. Normalize all document numbers to: strip all non-digit characters, strip leading zeros for CC/CE/NIT comparisons (or decide on a canonical form and apply it everywhere uniformly). For NITs: strip the check digit (last digit after a dash, if present).

**Warning signs:**
- RCAC match rate < 15% when cross-referenced with `proveedores_registrados.csv` (should be higher for active contractors who have backgrounds)
- `proveedor_en_rcac` feature is near-zero across the entire training set
- `boletines.csv` (Comptroller bulletins, 10.8K rows) produces zero matches against any provider in the contracts table
- M3 model (Comptroller records) trains but SHAP shows RCAC features contributing nothing

**Phase to address:** Phase 1 (Data Infrastructure). Normalization must be validated before RCAC is built. Add `test_rcac.py` tests for document normalization round-trips with real data samples.

---

### Pitfall 4: IRIC Thresholds Calibrated on the Test Set

**What goes wrong:**
`calibrate_iric.py` computes percentile thresholds (P1, P5, P95, P99 for publicity period, decision period, provider history, contract value) on the entire contracts dataset. These thresholds are then used as IRIC component inputs for BOTH training and test sets. This means the test set has already influenced the thresholds — a subtle form of leakage. The IRIC-as-feature (`iric_score`) and IRIC components are evaluated on the same distribution they calibrated, slightly inflating all model metrics that depend on IRIC. More critically, in production inference on NEW contracts, thresholds computed on historical data may be stale — a value that was at P95 in 2021 may be at P70 in 2026 due to market inflation.

**Why it happens:**
The calibration script is naturally written as a one-shot process over all available data. Developers don't immediately think of percentile calibration as a form of "fitting" that is subject to the same train/test isolation rules as model training.

**How to avoid:**
Compute IRIC thresholds using ONLY the training set (same 70% temporal split). Save thresholds to `iric_thresholds.json` and apply them to the test set exactly as they would be applied in production. This ensures the test set evaluation is honest. Document the threshold calibration date in the JSON file. For production refresh: schedule threshold recalibration whenever the model is retrained (annually at minimum), and track threshold drift over time.

**Warning signs:**
- IRIC-based features contribute disproportionately to model performance (SHAP shows `iric_score` as the dominant predictor)
- Test set IRIC distribution is identical to training set IRIC distribution (expected given full-data calibration)
- Removing IRIC-as-feature causes AUC to drop by > 0.10 (suggests models are using IRIC as a proxy for test-set-calibrated patterns)

**Phase to address:** Phase 2 (Feature Engineering, `calibrate_iric.py`). Must be enforced before Phase 3 (Model Training) begins.

---

### Pitfall 5: Class Imbalance Strategy Evaluated Incorrectly with Standard Metrics

**What goes wrong:**
For M3 (Comptroller records, ~1-2% positive rate) and M4 (SECOP fines, ~1% positive rate), standard accuracy and even F1 are misleading. A model that predicts "no background" for everything achieves 98-99% accuracy. Developers evaluate the imbalance strategies using AUC-ROC only, which can be inflated by calibration effects. MAP@100 and MAP@1000 — the metrics that matter for operational use (can the model identify the riskiest 100 contracts for investigation?) — are not computed during the strategy selection phase, so the "best" strategy by AUC is not actually best for the intended use case.

**Why it happens:**
`RandomizedSearchCV` in scikit-learn defaults to accuracy or AUC-ROC as the scoring metric. Setting up MAP@k as a custom scorer requires more work and is skipped under time pressure.

**How to avoid:**
Implement a custom sklearn scorer for MAP@k immediately when building `evaluation.py`. Use it as the primary CV scoring metric for M3 and M4 specifically (models where ranking quality matters most). For M1 and M2 (16-18% positive), AUC-ROC is more appropriate as the primary metric. For `scale_pos_weight` vs. upsampling selection: evaluate all three metrics (AUC, MAP@100, Brier) per strategy in a single cross-validation run before selecting. Do not select strategy based on AUC alone. Add a baseline model (majority class predictor) to the evaluation report so degradation relative to trivial predictors is always visible.

**Warning signs:**
- M3 or M4 achieves AUC > 0.85 but MAP@100 is near 0.01-0.05 (the model calibrates probabilities poorly for the minority class despite good ranking)
- The chosen imbalance strategy has a Brier Score worse than a naive `p = base_rate` predictor
- Cross-validation AUC variance across folds is > 0.15 for M3/M4 (small positive class counts per fold cause instability)

**Phase to address:** Phase 3 (Model Training). Implement evaluation metrics and custom scorers before beginning hyperparameter optimization.

---

### Pitfall 6: Data Leakage from the `procesos_SECOP.csv` Join

**What goes wrong:**
`procesos_SECOP.csv` (5.1M rows, 5.3 GB) contains bid counts (`Numero de Ofertas Recibidas`), publicity dates, and award dates. Some process records are updated after award — the file contains the final, post-award process record, not the pre-award state. Joining this to contracts produces features that reflect what happened AFTER the contract was executed, not the pre-execution state. For example, `Numero de Ofertas Recibidas` might be updated post-award to reflect disqualified bids. Using this value in a model meant to detect pre-execution risk uses information that was not available at signing time.

**Why it happens:**
SECOP II is a live transactional system. The bulk-downloaded CSV reflects the current state of each record, not its state at signing time. There is no explicit version history in the local files.

**How to avoid:**
Document the known post-execution fields in `procesos_SECOP.csv` and exclude them from the pre-execution feature set. Cross-reference with the SECOP II data dictionary to identify fields that are updated after award. For `Numero de Ofertas Recibidas`: assume the value at the time of download reflects a settled number (bids are submitted before award; this is pre-execution). For fields like `Fecha de Ultima Publicacion`: only use if it precedes `Fecha de Adjudicacion`. Build a `post_execution_fields_exclusion_list` in `settings.py` and enforce it in the feature pipeline.

**Warning signs:**
- Features from `procesos_SECOP.csv` dominate SHAP explanations with very high |SHAP| values but no intuitive corruption-related interpretation
- Dates from process records appear AFTER the contract signing date for a significant fraction of contracts
- Left-joining `procesos_SECOP.csv` on `ID Proceso` produces many-to-one issues (multiple process records per contract) with inconsistent values

**Phase to address:** Phase 2 (Feature Engineering). Data audit of `procesos_SECOP.csv` fields during `process_features.py` development.

---

### Pitfall 7: Training on All Available Contracts, Including Those Without Resolvable Outcomes

**What goes wrong:**
Contracts with no corresponding amendment record in `adiciones.csv` are labeled 0 (no overrun / no delay) for M1 and M2. But many contracts have no amendment record simply because they are too recent, were added to SECOP II after the bulk download, or because the amendment was filed under a different process identifier. These spurious negatives contaminate the training data: the model learns that "no amendment found" = clean contract, when many of these are actually unresolved contracts. This suppresses recall for M1 and M2.

**Why it happens:**
Label construction is simple: if `contract_id` appears in `adiciones.csv`, label = 1; otherwise label = 0. No check is made for contract recency or completeness. VigIA applied a temporal filter (contracts with sufficient execution time to have accumulated amendments), but this step is easily missed.

**How to avoid:**
Apply a minimum execution-time filter before constructing labels: exclude contracts where `Fecha de Fin del Contrato` is within 12-18 months of the data download date. These contracts may not have had time to accumulate amendments. Cross-reference contract duration against amendment rates by cohort — plot the fraction of M1=1 by signing year to check for a recency tail (recent years will have artificially lower positive rates if amendments are not yet filed). Only include contracts where execution would be reasonably complete given the data snapshot date.

**Warning signs:**
- M1/M2 positive rates for contracts signed in the last 1-2 years before the data snapshot are significantly lower than for earlier cohorts
- MAP@100 drops considerably when evaluated on recent contracts vs. older contracts
- Model underperforms on contracts that intuitively should be high-risk (new providers, direct contracting, high values) in recent cohorts

**Phase to address:** Phase 3 (Model Training), label construction step. Must be addressed before training begins.

---

### Pitfall 8: Memory Crash During Large-File Feature Engineering Without Chunked Processing

**What goes wrong:**
`ofertas_proceso_SECOP.csv` (6.5M rows, 3.4 GB, 163 columns) and `procesos_SECOP.csv` (5.1M rows, 5.3 GB) exceed available RAM when loaded with default pandas settings. Loading both simultaneously to compute bid dispersion features crashes the process on a typical development machine (16 GB RAM). Developers attempt workarounds (loading just the columns they need, dropping types) but the full join of offers + processes + contracts still exceeds memory.

**Why it happens:**
pandas loads everything into memory by default. The natural impulse is to `pd.read_csv()` the whole file, which fails silently until Python OOM-kills the process or the machine swaps to disk and grinds to a halt.

**How to avoid:**
Use chunked processing from the start for all files > 500 MB. For `ofertas_proceso_SECOP.csv`: read in chunks of 100K rows, aggregate bid statistics (count, mean, std, min, max) per `ID Proceso`, and accumulate results before the final join. For the join itself: use `pyarrow`/parquet as an intermediate format and perform memory-efficient merges. Explicitly specify `usecols` to load only needed columns and `dtype` to use the smallest valid type (e.g., `float32` instead of `float64`, `int32` instead of `int64`). For the full training pipeline: profile memory usage and set memory limits on the pipeline process to catch regressions early. A batch downloader that saves pre-aggregated statistics per source avoids reprocessing the large files each training run.

**Warning signs:**
- Python process memory consumption exceeds 8 GB during any single step
- Processing `ofertas_proceso_SECOP.csv` or `procesos_SECOP.csv` takes > 30 minutes
- `pd.read_csv()` with no options on these files causes system swap to activate

**Phase to address:** Phase 1 (Data Infrastructure, `batch_downloader.py`) and Phase 2 (Feature Engineering). Chunked processing must be a design constraint from the first line of code.

---

### Pitfall 9: Legal Representative Cross-Reference Misidentifies RCAC Matches Due to Name Ambiguity

**What goes wrong:**
Step 4 of the RCAC construction pipeline cross-references legal representatives from `proveedores_registrados.csv` against the RCAC. However, natural person identification in Colombia sometimes requires both document number AND document type (CC vs. CE) to be unique. When the legal representative data in `proveedores_registrados.csv` has incomplete or ambiguous document type (many rows contain only a name, or "CC" without a number), the cross-reference either over-matches (false positives: innocent people flagged as having backgrounds) or under-matches (misses true connections). Over-matching is particularly damaging: it can generate false corruption flags against legitimate providers.

**Why it happens:**
Legal representative data quality in SECOP II is poor — it is a free-text field in many procurement systems that was later standardized. Some rows have the representative's name but no document number. The temptation is to fall back to name-based matching, which is highly error-prone with Spanish names that have common patterns (José García, Carlos Rodríguez).

**How to avoid:**
Only match legal representatives by `(tipo_documento, numero_documento)` — never by name alone. If document data is missing for a representative, set `representante_en_rcac = None` (unknown) rather than 0 (clean). Track the fraction of legal entities where representative document data is available vs. missing — report this coverage metric in training metadata. Do NOT attempt fuzzy name matching. Document this limitation explicitly: "X% of legal entities have incomplete representative document data and cannot be cross-referenced against the RCAC."

**Warning signs:**
- `representante_en_rcac = 1` appears in > 10% of legal entity contracts (implausibly high given RCAC source size)
- Legal representative feature has near-zero variance (all zeros — indicates normalization failure)
- After adding representative cross-reference, M3/M4 AUC drops instead of improving (false positives introducing noise)

**Phase to address:** Phase 1 (Data Infrastructure, RCAC builder Step 4). Design the cross-reference logic conservatively from the start.

---

### Pitfall 10: IRIC Dual-Role Creates Circular Feature Engineering During Training vs. Inference

**What goes wrong:**
IRIC requires knowing the thresholds (from `iric_thresholds.json`) and, for components `proveedor_sobrecostos_previos` / `proveedor_retrasos_previos`, requires knowing historical amendment rates — which depends on the same `adiciones.csv` that generates M1/M2 labels. During online inference on a new contract, `iric.py` correctly computes these from historical pre-execution data. But during training feature generation, if IRIC is computed AFTER labels are constructed from the full amendments dataset (not respecting the temporal cutoff), the IRIC score becomes a soft proxy for the label. Models trained this way appear to explain themselves via IRIC features when they are actually leaking the label through a third pathway.

**Why it happens:**
The IRIC pipeline is complex with 11 components. Components 9 and 10 (`proveedor_sobrecostos_previos`, `proveedor_retrasos_previos`) require the same amendment data as the labels. The temporal cutoff that prevents label leakage must apply inside `iric.py` for these two components, which requires passing the contract signing date into the IRIC computation function.

**How to avoid:**
Make `iric.py`'s `compute_iric(contract, historical_amendments, cutoff_date)` function accept a `cutoff_date` parameter and apply it to ALL amendment lookups internally. In the feature pipeline, always pass `cutoff_date = contract['Fecha de Firma']`. Write a test that verifies IRIC components 9 and 10 return 0 for a first-time provider even when amendments for that provider exist in the dataset but post-date the contract.

**Warning signs:**
- `iric_score` is the dominant SHAP predictor for M1 and M2 (not necessarily wrong, but warrants scrutiny)
- IRIC scores correlate with M1/M2 labels at > 0.4 Pearson correlation (could indicate circular construction)
- IRIC computation produces different scores when called with vs. without a `cutoff_date` parameter on the training set (this difference is the leakage)

**Phase to address:** Phase 2 (Feature Engineering, `iric.py`). Enforce cutoff_date from the first implementation.

---

### Pitfall 11: Socrata API Rate Limits Cause Incomplete Bulk Downloads

**What goes wrong:**
The Socrata API at datos.gov.co applies rate limits (typically 1000 requests/hour for anonymous clients, higher for authenticated). `procesos_SECOP.csv` (5.1M rows) requires ~5,100 paginated requests at 1000 rows/page. Without authentication tokens or exponential backoff, the bulk download silently truncates after hitting a rate limit error, producing an apparently complete but actually truncated CSV. The training pipeline runs on incomplete data without any warning.

**Why it happens:**
Socrata APIs return HTTP 429 or HTTP 200 with an error body (not a standard HTTP error) when rate-limited. Without explicit pagination completion checks and response validation, the downloader stops early and writes an apparently valid but incomplete file.

**How to avoid:**
Use authenticated Socrata API access (app token) for all bulk downloads — this raises the rate limit substantially. Implement exponential backoff with jitter for all API calls. After download, verify row counts against the known dataset size (compare to the `$count` endpoint before beginning). Store row counts in `training_metadata.json`. For the very large files (`procesos_SECOP.csv`, `ofertas_proceso_SECOP.csv`): use the Socrata export endpoint (direct CSV download) rather than paginated API calls when possible — it is faster and not subject to the same rate limits.

**Warning signs:**
- `procesos_SECOP.csv` local file has fewer rows than known from dataset metadata
- Feature coverage rates drop suddenly (many contracts have `ausencia_proceso = 1` despite SECOP reporting the processes exist)
- Download completes in suspiciously short time (< 10 minutes for a 5 GB file)

**Phase to address:** Phase 1 (Data Infrastructure, `secop_client.py` and `batch_downloader.py`).

---

### Pitfall 12: Encoding and Locale Issues with Spanish-Language CSVs from SECOP

**What goes wrong:**
SECOP II CSV files use UTF-8 encoding with Spanish accented characters (á, é, ó, ü, ñ). PACO data files (`sanciones_SIRI_PACO.csv`, `responsabilidades_fiscales_PACO.csv`) use Latin-1 (ISO-8859-1) encoding. The Monitor Ciudadano Excel files use a different encoding still. Loading any file without explicit encoding declaration causes `UnicodeDecodeError` or, worse, silent mojibake (garbled characters) that causes string comparisons to fail. Department names (`Bogotá D.C.` vs. `Bogota D.C.`), modality names, and document type strings all contain encoding-sensitive characters used as categorical features and RCAC match keys.

**Why it happens:**
Python's `pd.read_csv()` defaults to UTF-8, which raises an error for Latin-1 files. Developers add `encoding='latin-1'` globally, which then breaks the SECOP files. The inconsistency between sources is not discovered until late in integration.

**How to avoid:**
In `settings.py`, define per-file encoding constants. Inspect actual file encodings using `chardet` before committing to a codec. Normalize all string features to lowercase + NFD normalization (strip accents) as the final step of text preprocessing before string comparison or categorical encoding. Build a single `normalize_text(s)` utility used uniformly everywhere. For the RCAC cross-reference: normalize department names and entity names before any string match. For categorical features (modality, contract type): normalize strings before one-hot or label encoding to avoid split categories (`"Contratación directa"` vs. `"Contratacion directa"` becoming separate levels).

**Warning signs:**
- Categorical feature cardinality is 2-3x expected (e.g., 10 modality types becomes 18 after encoding — duplicates with different accent patterns)
- Document normalization test for PACO sources fails with `UnicodeDecodeError`
- `Departamento` feature has > 40 levels (32 departments + Bogotá D.C. = 33 expected; duplicates indicate encoding issues)

**Phase to address:** Phase 1 (Data Infrastructure). Encoding must be standardized before any data loading code is written.

---

### Pitfall 13: Monitor Ciudadano Excel Files Are Structurally Heterogeneous Across Years

**What goes wrong:**
The 4 Monitor Ciudadano Excel files (`Base_de_datos_actores_2016_2022.xlsx`, `Base_de_datos_general_2016_2022.xlsx`, `Base_de_datos_hechos_2016_2022.xlsx`, `Base_de_datos_notas_2016_2022.xlsx`) are produced by a civil society organization and have changed structure between editions. Column names, column order, identifier fields (some use CC, some use organization name only), and even the unit of analysis (some rows are actors, some are events) differ. Reading them with `pd.read_excel(sheet_name=0)` and assuming consistent column names across all 4 files causes silent data loss: the actor-level identifiers needed for the RCAC are in the `actores` file but not in the `hechos` file.

**Why it happens:**
Excel files from civil society sources are maintained manually and evolve organically. There is no API contract. Developers assume they share a common schema because they are from the same dataset family.

**How to avoid:**
Print the full column list for each Excel file before writing any parsing code. Determine the join key: `Base_de_datos_actores` likely contains the person identifiers (CC/NIT); `Base_de_datos_hechos` contains the event classification (type of corruption). Build the Monitor Ciudadano RCAC contribution by joining actor → event at the `ID_hecho` level. Handle missing CC/NIT fields with null (do not attempt name-based matching). Document which fraction of Monitor events can be attributed to identifiable natural/legal persons vs. anonymous actors.

**Warning signs:**
- Monitor Ciudadano RCAC source contributes 0 records after integration (integration failed silently)
- `pd.read_excel()` raises `KeyError` on any expected column name
- More than 50% of Monitor events lack CC/NIT identifiers (means the source contributes little to the RCAC for cross-referencing)

**Phase to address:** Phase 1 (Data Infrastructure, RCAC builder). Requires manual schema inspection before any parsing code is written.

---

### Pitfall 14: Hyperparameter Search Overfits to Validation Folds with Very Small Positive Classes

**What goes wrong:**
For M3 (1-2% positive rate) and M4 (~1%), a 5-fold stratified cross-validation on 70% of 341K contracts gives approximately 2,400 positive examples per fold in the worst case (M4). RandomizedSearchCV with 200 iterations × 5 folds = 1,000 model fits, each evaluated on ~2,400 positive examples. With this many hyperparameter configurations, the search finds parameters that exploit random variation in fold composition. The "best" hyperparameters perform well on the specific positive examples that happened to be in the validation folds, not on the general pattern. The hold-out test AUC is consistently 3-8% lower than CV AUC.

**Why it happens:**
200 iterations of random search is appropriate for balanced datasets. For 1% positive rate datasets, the effective sample size for the positive class is tiny, and 200 iterations is enough to overfit the CV.

**How to avoid:**
For M3 and M4: reduce random search to 50-100 iterations and increase StratifiedKFold to 10 folds (more positive examples per validation fold). Use early stopping in XGBoost rather than relying on a fixed `n_estimators` range. Reserve a temporal holdout (most recent 10% of contracts by date) that is NEVER used during hyperparameter search — compare this holdout to CV performance to detect overfit to CV. Report the CV-to-holdout gap in training metadata; if gap > 0.05 AUC, flag it.

**Warning signs:**
- CV AUC for M3 or M4 is > 0.05 higher than holdout AUC
- Best `n_estimators` from random search is at the boundary of the search range (1000) — may indicate underfitting or overfitting pressure
- Best `max_depth` is very deep (9-11) for M3/M4 — XGBoost on small positive class tends toward overfitting with deep trees

**Phase to address:** Phase 3 (Model Training). CV strategy must be designed for small positive class constraints before the search runs.

---

### Pitfall 15: SHAP Values Computed on Non-Normalized Features Produce Misleading Explanations

**What goes wrong:**
`valor_contrato` spans from ~1 million COP to ~10 billion COP (4 orders of magnitude). Without log transformation, XGBoost trees split on raw COP values, and SHAP values for contract value are in raw COP units. A SHAP value of +500,000 COP for a high-value contract looks small compared to a SHAP value of +0.15 for `es_contratacion_directa`. The displayed explanations confuse end users (journalists, oversight agencies) because the magnitude ordering is not intuitive: "why does direct contracting matter more than a contract worth 5 billion pesos?"

**Why it happens:**
XGBoost handles wide feature ranges internally via splits and does not strictly require normalization. Developers skip normalization since the model trains fine, without considering that SHAP values are in raw feature units and the ordering of importance may change dramatically under log vs. raw scale.

**How to avoid:**
Apply log transformation to all monetary features before training: `log_valor_contrato = log1p(valor_contrato)`. Apply log to `valor_total_contratos_previos`, `cuantia_total_dano_fiscal`. This is explicitly noted in the VigIA paper. For temporal features with extreme outliers: apply winsorization (clip to P1/P99) before training. This changes the SHAP interpretability frame — document it clearly in the API response: "log_valor_contrato: a 1-unit SHAP increase means the log-scale contract value adds X risk." Ensure the same transformations are applied identically in the online inference pipeline.

**Warning signs:**
- `valor_contrato` SHAP values appear as large absolute numbers (> 1M) while binary features have SHAP values of 0.01-0.20
- XGBoost splits on contract value at very specific raw values (e.g., 50,000,000) rather than on the distribution (indicating it is not capturing the distributional shape efficiently)
- Model performance degrades when evaluated on contracts with unusually large values (outliers dominate tree splits)

**Phase to address:** Phase 2 (Feature Engineering). Transformations must be part of the feature pipeline, not a separate preprocessing step.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Random train/test split instead of temporal split | Simpler code, higher AUC | Leaks future information; deployment performance is much lower | Never — use temporal split always |
| Computing RCAC match once globally (no per-contract temporal cutoff) | 10x faster batch computation | Provider history features are contaminated by future sanctions | Never — temporal cutoff is non-negotiable |
| `pd.read_csv()` with no dtype/encoding/usecols specification | Rapid prototyping | OOM crashes, encoding errors, silent type mismatches | Only in EDA notebooks, never in production pipeline |
| Hardcoding file paths in feature modules | Faster initial development | Breaks when pipeline runs from different CWD or in a container | Never — use `settings.py` path constants from day 1 |
| Skipping unit tests on RCAC normalization and treat output match rate as validation | Saves 2 days | Silent correctness bugs; RCAC contributes nothing to model signal | Never for normalization logic |
| Using `accuracy` as CV scoring metric for M3/M4 | Default sklearn behavior | Optimizes for majority class; minority class recall may be 0 | Never — always use AUC or MAP@k |
| Building RCAC from only the easiest sources (boletines + SIRI) and skipping Monitor/FGN | Reduces integration work by ~30% | Misses organized corruption networks not in official records | Acceptable for v1 MVP if documented |
| Equal CRI weights (1/5 each) permanently | No calibration needed | Models with lower AUC contribute equally to risk score | Acceptable for v1; plan calibration for v2 |
| Saving models with pickle instead of joblib | Standard library, no dependency | Slower serialization, version compatibility issues across Python | Acceptable only if joblib is not available |
| Skipping SHAP computation during batch training evaluation | 5-10x faster training | Cannot validate SHAP explanations are sensible before deployment | Acceptable to skip for training; required at evaluation step |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Socrata API (datos.gov.co) | Assuming the `$offset` parameter starts at 0 and increments are exact — but Socrata can change record counts between paginated requests | Verify total count with `$count` endpoint before starting, re-verify after all pages are collected |
| Socrata API | Using unauthenticated requests for bulk download (7 different datasets totaling 12 GB) | Register a Socrata app token; pass it in the `X-App-Token` header; request pagination via `$limit=50000` for efficiency |
| Socrata API | Joining local CSVs to API responses assumes schema is stable between download dates | Pin dataset schema versions in `settings.py`; log column names on each download; fail if unexpected columns appear |
| SIRI file (no headers) | Trusting column position indices without verifying the actual content — column 4 = doc type, column 5 = doc number, but this is based on inspection of the first few rows | Assert that columns 4 and 5 match expected patterns (CC/NIT patterns, numeric IDs) for > 90% of rows before processing |
| Monitor Ciudadano Excel | `pd.read_excel()` without `sheet_name` — defaults to first sheet, but some files have metadata on sheet 0 and data on sheet 1 | Explicitly inspect sheet names with `pd.ExcelFile(path).sheet_names` before loading |
| joblib serialization of RCAC dict | Saving/loading a Python dict of 58K+ RCACRecord dataclasses — loading is slow if not warmed up | Load RCAC at server startup, not per-request; store total load time in health endpoint response |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading all provider history into memory for each contract during online inference | Acceptable for single contract, catastrophic for batch endpoint | Pre-build the provider history lookup table as a dict keyed by provider ID, loaded at startup alongside RCAC | Batch endpoint with 1000 contracts causes OOM if computing history on the fly |
| Full `procesos_SECOP.csv` join during feature engineering | Works on sampled data (10K contracts), fails on full 341K training set | Pre-aggregate process statistics (bid counts, dates) by `ID Proceso` into a compact lookup table | Breaks when full training dataset is used |
| Computing IRIC for all 341K contracts sequentially in Python | ~2-3 minutes per 10K contracts → hours for full dataset | Vectorize IRIC component computations using pandas vector operations; avoid row-by-row loops | Full training feature generation takes > 8 hours with naive implementation |
| SHAP computation via `TreeExplainer` on the full training set for feature importance | Works fine for 10K, extremely slow for 341K | Compute SHAP on a stratified sample (5K contracts) for feature analysis; compute per-contract in real-time only for inference | SHAP TreeExplainer on 341K rows can take > 2 hours |
| In-memory RCAC dict grows unbounded if Monitor Ciudadano and FGN data duplicates are not deduplicated | Memory usage creeps over 2 GB for the RCAC dict | Deduplication step is mandatory before serialization; assert final RCAC size < 100K records | RCAC loading at server startup takes > 30 seconds (response SLA violation) |

---

## "Looks Done But Isn't" Checklist

Patterns that appear complete in development but break in practice.

- [ ] RCAC is built and serialized — **verify:** load RCAC.pkl and check that at least one known sanctioned entity (from boletines.csv) appears in the dict with correct flags
- [ ] Feature pipeline runs on sample data — **verify:** run on a known high-risk contract (one with Comptroller record) and confirm `proveedor_responsable_fiscal = 1` in output
- [ ] IRIC calibration produces thresholds — **verify:** `iric_thresholds.json` has separate entries for at least 3 contract types; each threshold value is in the correct range (e.g., `periodo_publicidad_p99` should be > 30 days for most types)
- [ ] Model training completes with AUC reported — **verify:** MAP@100 for M3 must be > 0.10 (10%) — if it is not, the model is not meaningfully ranking high-risk providers above baseline
- [ ] SHAP values computed — **verify:** for a known direct contracting case with high value, `es_contratacion_directa` and `log_valor_contrato` should appear in top-5 SHAP features with positive values
- [ ] API returns JSON response — **verify:** submit a contract known to have a Comptroller background; check that `provider_background.in_rcac = true` in the response
- [ ] Batch endpoint works — **verify:** submit 100 contract IDs; confirm exactly 100 results returned; confirm no results share identical risk scores (would indicate feature pipeline returning defaults silently)
- [ ] Temporal data split is enforced — **verify:** no contract in the test set has a signing date earlier than any contract in the training set (i.e., the split is truly temporal)
- [ ] SIRI positional parsing is correct — **verify:** document type column (position 4, 0-indexed) contains only known values (CÉDULA DE CIUDADANÍA, NIT, PASAPORTE, etc.) with > 90% coverage; no numeric values appear in this column

---

## Pitfall-to-Phase Mapping

| Pitfall | Phase | Verification |
|---------|-------|--------------|
| Temporal data leakage via provider history features | Phase 2 | Unit test: `compute_provider_history_as_of()` returns 0 contracts for a provider queried before their first contract date |
| Label construction contaminates provider features | Phase 2 + Phase 3 | Assert: contract's own ID never appears in its own provider history |
| RCAC document normalization fails silently | Phase 1 | Test: known sanctioned entity from boletines.csv appears in RCAC dict; match rate > 20% for all sources |
| IRIC thresholds calibrated on test set | Phase 2 | Verify: calibrate_iric.py takes training-set-only contracts as input |
| Class imbalance evaluated with wrong metrics | Phase 3 | MAP@100 implemented as custom CV scorer before hyperparameter search |
| Data leakage from procesos_SECOP.csv join | Phase 2 | Post-execution field exclusion list enforced in `process_features.py` |
| Training on contracts without resolvable outcomes | Phase 3 | Temporal filter applied to label construction; positive rate checked by signing-year cohort |
| Memory crash on large CSVs | Phase 1 + Phase 2 | Chunked processing tested on full-size files before batch training |
| Legal representative over-matching | Phase 1 | Coverage metric logged: fraction of legal entities with document-complete representative data |
| IRIC dual-role circular construction | Phase 2 | IRIC components 9/10 tested with explicit cutoff_date parameter |
| Socrata API incomplete downloads | Phase 1 | Row count verification after download vs. `$count` endpoint |
| CSV encoding and locale issues | Phase 1 | All string normalizations tested with accented characters; categorical cardinality checks |
| Monitor Ciudadano heterogeneous Excel schemas | Phase 1 | Manual schema inspection documented; failing gracefully when CC/NIT missing |
| Hyperparameter search overfits small positive class | Phase 3 | CV-to-holdout AUC gap < 0.05 required for M3 and M4 |
| SHAP values on non-normalized features | Phase 2 | Log-transformed monetary features used from first training run |

---

## Sources

- Gallego, Rivero & Martínez (2021) — "Preventing Waste Abuse and Corruption" — ML on Colombian procurement data. Established scale_pos_weight of 25 for M3/M4, MAP@k as primary evaluation metric, contract value as top predictor.
- Salazar, Pérez & Gallego (2024) — "VigIA" — IRIC definition, dual-role of IRIC, provider temporal features (days_registered < 228 as risk signal), log transformation of monetary features, Bogotá calibration as baseline.
- Mojica (2021) — 136K hyperparameter combinations evaluated; 200 iterations sufficient for Colombian procurement scale.
- Fazekas & Kocsis (2020) — Registry of corruption risk indicators in public procurement; single-bidder contracts as core signal; publicity period duration anomalies.
- Imhof (2018) — Kurtosis and normalized relative difference bid-screening indicators (IRIC Anomaly Calculations 1 and 2).
- Baltrunaite et al. (2020) — Competition suppression in procurement as collusion indicator.
- Open Contracting Partnership (2020) — Multi-purpose provider risk indicators.
- Direct inspection of local data files: `sanciones_SIRI_PACO.csv` (no headers, positional columns confirmed), `responsabilidades_fiscales_PACO.csv` (combined `Tipo y Num Documento` field), Monitor Ciudadano 4-file Excel structure in `/Data/Propia/Monitor/base_de_datos_hechos/`.
- VigIA source notebooks in `/data/Vigia/` — Python 3.7 Jupyter notebooks confirming temporal cutoff approach and feature transformation decisions.

---
*Pitfalls research for: Colombian public procurement corruption detection ML system (SIP)*
*Researched: 2026-02-27*
