# Vigia vs. SIP Engine: Model Comparison

## Executive Summary

The current SIP Engine has a **critical M2 label construction bug** that reduces M2 positives from an expected ~39,000+ to only **19 contracts**. This document compares the reference Vigia notebooks against the current SIP implementation across label logic, feature selection, and model architecture.

---

## 1. Label Construction

### M1 — Cost Overruns (Tuvo_adiciones_valor)

| Aspect | Vigia (Reference) | SIP Engine (Current) | Match? |
|---|---|---|---|
| Data source | `SECOP_II_-_Adiciones.csv` | `secopDatabases/adiciones.csv` | ✅ |
| Positive types | "Adición en el valor" + "Reducción en el valor" | `ADICION EN EL VALOR` + `REDUCCION EN EL VALOR` | ✅ |
| Logic | `1*(Numero_adiciones_valor != 0)` | `id_contrato ∈ m1_contracts` | ✅ Equivalent |
| Positive rate | ~17.0% (87,387 contracts → ~14,370 positive) | 3.39% (340,480 → 11,536 positive) | ⚠️ Different dataset size |
| Verdict | — | **Correct logic**, rate difference due to different filtering (Bogotá-only vs. national) | — |

### M2 — Time Delays (Tuvo_adiciones_tiempo) — 🚨 CRITICAL BUG

| Aspect | Vigia (Reference) | SIP Engine (Current) | Match? |
|---|---|---|---|
| Data sources | **Two sources combined**: `Dias Adicionados` column from contratos + `Extensión` type from adiciones | **One source only**: `EXTENSION` type from adiciones | ❌ **MISSING SOURCE** |
| Logic | `1*((Dias Adicionados != 0) OR (Numero_adiciones_extension != 0))` | `tipo.upper() == "EXTENSION"` | ❌ **Incomplete** |
| Positive rate (Vigia) | ~18.7% (87,387 → 16,369 positive) | — | — |
| Positive count (SIP) | — | **19 positives** (0.01%) | 🚨 |
| Expected positives | ~39,153 contracts have `Dias adicionados ≠ 0` in current data | 19 from EXTENSION only (391 rows total, 341 unique contracts, minus filtering) | 🚨 |

**Root Cause**: The label builder at `src/sip_engine/data/label_builder.py:38` defines:
```python
M2_TIPOS: set[str] = {"EXTENSION"}
```
This only captures the `EXTENSION` tipo from `adiciones.csv`, which has only **391 rows** (0.003% of 14.3M adiciones rows). The Vigia notebook's primary source for time delays was the **`Dias Adicionados` column in the contratos table itself** — which has **39,153 non-zero values** (11.5% of contracts).

The `EXTENSION` tipo in adiciones is a nearly-empty category. The real delay signal lives in `contratos_SECOP.csv → "Dias adicionados"`.

**Impact**: M2 model trained on 19 positives out of 340K is statistically useless. The AUC of 0.996 is an artifact of extreme class imbalance with near-random separation on 6 test positives.

### M3 / M4 — Comptroller & RCAC

These models (M3, M4) have no direct Vigia equivalent — they are SIP-specific additions using boletines.csv and RCAC data. Not compared here.

---

## 2. Feature Selection Comparison

### Vigia Approach

The Vigia notebooks used **`SelectFromModel(RandomForestClassifier)`** with two rounds of feature selection:
1. First pass: select features with importance above the default mean threshold
2. Second pass: re-select from the first-pass features to further reduce

Both M1 and M2 were trained **three ways**: all contract types, prestación de servicios only, and non-prestación only.

Additionally, Vigia created **two model variants per target**:
- **All variables** (including post-execution: `Dias Inicio-Firma Ejecucion`, `Dias Fin-Inicio Ejecucion`, `Liquidación`, etc.)
- **Pre-execution variables only** (excluding the execution-phase features)

### SIP Engine Approach

SIP uses a **fixed 34-feature vector** (10 Cat-A + 9 Cat-B + 11 Cat-C + 4 Cat-D/IRIC) with XGBoost instead of Random Forest.

### Feature-by-Feature Comparison

#### Features Present in Both Systems

| Vigia Feature | SIP Feature | Notes |
|---|---|---|
| `Valor del Contrato` | `valor_contrato` | ✅ Direct mapping |
| `Dias Proveedor Inscrito` | `dias_proveedor_registrado` | ✅ Same concept |
| `Sector_*` (one-hot) | `departamento_cat` | ⚠️ Vigia used Sector, SIP uses Departamento |
| `Modalidad de Contratacion_*` | `modalidad_contratacion_cat` + `es_contratacion_directa` + `es_regimen_especial` | ✅ Expanded |
| `Justificacion Modalidad_*` | `es_servicios_profesionales` + `tiene_justificacion_modalidad` | ✅ Simplified |
| `Tipo de Contrato_*` | `tipo_contrato_cat` | ✅ |
| `Mes Firma Contrato` | `mes_firma` + `trimestre_firma` | ✅ SIP adds trimestre |
| `Grupo categoria principal_*` | `unspsc_categoria` | ✅ Different encoding |
| `Proveedores Invitados` | `num_proponentes` + `num_ofertas_recibidas` | ⚠️ SIP uses `Proveedores Unicos con Respuestas` |
| `Es Pyme` | — | ❌ Not in SIP |
| `Entidad Centralizada_*` | — | ❌ Not in SIP |
| `Destino Gasto_*` | `origen_recursos_cat` | ⚠️ Different column |

#### Features in Vigia but NOT in SIP

| Feature | Category | Impact |
|---|---|---|
| `Dias Inicio-Firma Contrato` | Post-execution | Excluded by design (FEAT-08) ✅ |
| `Dias Fin-Inicio Contrato` | Post-execution | Excluded by design (FEAT-08) ✅ |
| `Dias Inicio-Firma Ejecucion` | Post-execution | Excluded by design (FEAT-08) ✅ |
| `Dias Fin-Inicio Ejecucion` | Post-execution | Excluded by design (FEAT-08) ✅ |
| `Liquidación` | Post-execution | Excluded by design (FEAT-08) ✅ |
| `Proporcion pagada adelantado` | Post-execution | Excluded by design (FEAT-08) ✅ |
| `Codigo Segmento Categoria Principal_*` | One-hot segments | Replaced by `unspsc_categoria` (ordinal) |
| `Es Pyme` | Provider attribute | ❌ Missing — moderately important in Vigia |
| `Entidad Centralizada` | Entity attribute | ❌ Missing |
| `Sector_*` (one-hot) | Entity sector | ❌ SIP has `departamento_cat` but not Sector |
| `Destino Gasto` | Contract attribute | ⚠️ SIP has `origen_recursos_cat` (different column) |
| `EsPostConflicto` | Contract attribute | ❌ Missing |
| `Habilita Pago Adelantado` | Contract attribute | ❌ Missing |
| `Es Grupo` | Provider attribute | ❌ Missing |
| `Dias Proceso Contratacion Abierto` | Temporal | ❌ Missing (SIP has `dias_publicidad` instead) |
| `Mes de Publicacion del Proceso_*` | Temporal (one-hot month) | ❌ Missing (SIP has `mes_firma` only) |

#### Features in SIP but NOT in Vigia

| Feature | Category | Notes |
|---|---|---|
| `dias_a_proxima_eleccion` | Temporal | New — Colombian election calendar proximity |
| `dias_decision` | Temporal | New — time from last publication to signing |
| `dias_publicidad` | Temporal | New — publication to response deadline |
| `firma_posterior_a_inicio` | Temporal | New — signed after contract start date |
| `duracion_contrato_dias` | Temporal | ⚠️ **Known leakage risk** — uses `Fecha de Fin del Contrato` which is post-amendment |
| `num_contratos_previos_depto` | Provider history | New — provider's prior contracts in department |
| `num_contratos_previos_nacional` | Provider history | New — provider's total prior contracts |
| `valor_total_contratos_previos_*` | Provider history | New — cumulative prior contract value |
| `num_sobrecostos_previos` | Provider history | New — provider's prior M1 label count |
| `num_retrasos_previos` | Provider history | New — provider's prior M2 label count |
| `num_actividades_economicas` | Provider breadth | New — distinct UNSPSC segments |
| `iric_score`, `iric_*` (4 features) | IRIC aggregate | New — composite risk index |

---

## 3. Model Architecture

| Aspect | Vigia | SIP Engine |
|---|---|---|
| Algorithm | Random Forest (sklearn) + Logistic Regression | XGBoost |
| Balancing | Downsampling majority class | `scale_pos_weight` (XGBoost) or downsampling comparison |
| Feature selection | `SelectFromModel(RF)` — 2 rounds | Fixed feature set (no selection) |
| Scaling | `StandardScaler` before training | XGBoost handles natively |
| Cross-validation | 10-fold CV | Stratified K-Fold (configurable) |
| Contract type split | Separate models per type (prestación de servicios, other, all) | Single model for all types |
| Hyperparameter tuning | None (default RF params) | RandomizedSearchCV with Gallego et al. ranges |

---

## 4. Key Problems in Current Setup

### 🚨 P1: M2 Label Missing Primary Data Source (Critical)
- **Current**: M2 uses only `EXTENSION` tipo from adiciones.csv → 19 positives
- **Expected**: Should also use `Dias adicionados` column from contratos → ~39,153 positives
- **Fix**: In `label_builder.py`, after building m2_contracts from adiciones, also scan contratos for `Dias adicionados != 0` and union those contract IDs into m2_contracts

### ⚠️ P2: `duracion_contrato_dias` Leakage (Known)
- Uses `Fecha de Fin del Contrato` which reflects post-amendment end date (already documented in stored memory)
- Should use `Duración del contrato` column (column 72) or the original `Duracion` + `Unidad de Duracion` from procesos
- This was the #1 feature by importance splits — inflating M1 AUC by ~7-15pp

### ⚠️ P3: `num_retrasos_previos` Circular Dependency with M2
- Provider history counts prior M2 labels to create `num_retrasos_previos` feature
- But if M2 labels are broken (only 19 positives), this feature is effectively always 0
- The `num_sobrecostos_previos` feature has the same issue with the IRIC calculator key mismatch (stored memory: `calculator.py:332` looks for `num_sobrecostos` but provider_history returns `num_sobrecostos_previos`)

### ⚠️ P4: Missing Vigia Features
- `Es Pyme`, `Entidad Centralizada`, `Sector`, `EsPostConflicto` were important in Vigia but absent in SIP
- `Sector_Cultura` was consistently selected across both M1 and M2 models in Vigia

### ℹ️ P5: Architecture Differences (Acceptable)
- XGBoost vs. Random Forest — reasonable upgrade
- Fixed feature set vs. SelectFromModel — acceptable for production, but may include noise
- Single model vs. per-contract-type split — simplification, but Vigia showed significant performance differences between prestación de servicios and other contract types

---

## 5. Vigia M2 Label Logic (Detailed)

For absolute clarity, here is the exact Vigia label construction for `Tuvo_adiciones_tiempo`:

```python
# Source 1: From adiciones.csv — filter to "Extensión" tipo only
adic_interes = ["Adición en el valor", "Extensión", "Reducción en el valor"]
adiciones = adiciones[adiciones['Tipo'].isin(adic_interes)]
adiciones = pd.get_dummies(adiciones[['ID_Contrato', 'Tipo']], columns=['Tipo'])
adiciones = adiciones.groupby('ID_Contrato').sum().reset_index()
# → Numero_adiciones_extension (per contract count of "Extensión" rows)

# Source 2: From contratos electrónicos — "Dias Adicionados" column (already in contratos table)

# Combined label:
secop_2_ce_port['Tuvo_adiciones_tiempo'] = 1 * (
    (secop_2_ce_port['Dias Adicionados'] != 0) |          # ← PRIMARY SOURCE
    (secop_2_ce_port['Numero_adiciones_extension'] != 0)   # ← SECONDARY SOURCE
)
```

**The `Dias Adicionados` column is the PRIMARY source** (contributes the vast majority of positives). The `Extensión` tipo from adiciones is barely used (0.000% of adiciones rows in Vigia data, and only 391 out of 14.3M in our data).

---

## 6. Recommended Fixes (Priority Order)

1. **Fix M2 labels** — Add `Dias adicionados` from contratos as an M2 positive source
2. **Fix `duracion_contrato_dias`** — Use original duration, not post-amendment end date
3. **Fix IRIC calculator key mismatch** — `num_sobrecostos` → `num_sobrecostos_previos`
4. **Consider adding** `Sector` (entity sector) and `Es Pyme` features
5. **Retrain all models** after label fix — M2 will go from unusable to meaningful
