# SIP Model Features

All 4 XGBoost models use the same 45 features. Features defined in `src/sip_engine/classifiers/features/pipeline.py`.

## Models

| ID | Predicts |
|----|----------|
| M1 | Cost overruns (contract value amendments) |
| M2 | Delays (contract time extensions) |
| M3 | Comptroller records (fiscal liability findings) |
| M4 | RCAC sanctions (irregularity records) |

---

## Features

### A — Contract Characteristics (10)
Source: `features/category_a.py`

| Feature | Description |
|---------|-------------|
| `valor_contrato` | Contract value |
| `tipo_contrato_cat` | Contract type (encoded) |
| `modalidad_contratacion_cat` | Procurement modality (encoded) |
| `departamento_cat` | Department (encoded) |
| `origen_recursos_cat` | Funding source (encoded) |
| `es_contratacion_directa` | 1 if direct contracting |
| `es_regimen_especial` | 1 if special regime modality |
| `es_servicios_profesionales` | 1 if professional services justification |
| `unspsc_categoria` | UNSPSC segment code |
| `tiene_justificacion_modalidad` | 1 if modality justification provided |

### B — Temporal (9)
Source: `features/category_b.py`

| Feature | Description |
|---------|-------------|
| `dias_firma_a_inicio` | Days between signing and contract start |
| `firma_posterior_a_inicio` | 1 if signed after contract start |
| `duracion_contrato_dias` | Contract duration in days |
| `mes_firma` | Month of signing (1–12) |
| `trimestre_firma` | Quarter of signing (1–4) |
| `dias_a_proxima_eleccion` | Days until next Colombian election |
| `dias_publicidad` | Days between process publication and response deadline |
| `dias_decision` | Days between last publication and award decision |
| `dias_proveedor_registrado` | Days since provider registration |

### C — Provider & Competition (11)
Source: `features/category_c.py`

| Feature | Description |
|---------|-------------|
| `tipo_persona_proveedor` | 1 if legal entity (NIT), 0 if natural person |
| `num_proponentes` | Unique bidders for the process |
| `num_ofertas_recibidas` | Total bids received |
| `proponente_unico` | 1 if only one bidder |
| `num_contratos_previos_nacional` | Provider's prior contracts (national) |
| `num_contratos_previos_depto` | Provider's prior contracts (same department) |
| `valor_total_contratos_previos_nacional` | Total value of prior contracts (national) |
| `valor_total_contratos_previos_depto` | Total value of prior contracts (same department) |
| `num_sobrecostos_previos` | Provider's prior cost overruns |
| `num_retrasos_previos` | Provider's prior delays |
| `num_actividades_economicas` | Distinct UNSPSC segments provider operates in |

### D — IRIC Scores (15)
Source: `classifiers/iric/`

#### Aggregate scores (4)
| Feature | Description |
|---------|-------------|
| `iric_score` | Overall irregularity-risk score |
| `iric_anomalias` | Anomaly sub-score |
| `iric_competencia` | Competition/bidding sub-score |
| `iric_transparencia` | Transparency sub-score |

#### Binary components (11, Phase 16)
| Feature | Description |
|---------|-------------|
| `ausencia_proceso` | 1 if no associated process record found |
| `contratacion_directa` | 1 if direct contracting (skips competitive bidding) |
| `datos_faltantes` | 1 if key contract data fields are missing |
| `historial_proveedor_alto` | 1 if provider has high prior contract volume |
| `periodo_decision_extremo` | 1 if decision period is unusually short or long |
| `periodo_publicidad_extremo` | 1 if publication period is unusually short or long |
| `proveedor_multiproposito` | 1 if provider operates across many UNSPSC sectors |
| `proveedor_retrasos_previos` | 1 if provider has prior contract delays |
| `proveedor_sobrecostos_previos` | 1 if provider has prior cost overruns |
| `regimen_especial` | 1 if contract uses special procurement regime |
| `unico_proponente` | 1 if only one bidder submitted a proposal |

---

## Notes

- **Categorical encoding:** `*_cat` features encoded to integers at training time (`features/encoding.py`)
- **RCAC features excluded** from model inputs to prevent circular leakage
- **Post-execution features excluded** to maintain early-detection capability
