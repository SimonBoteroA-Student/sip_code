# PRD: SIP — Sistema Inteligente de Predicción de Corrupción en Contratación Pública

## Backend — Project Requirements Document v1.0

---

## Meta

| Campo | Valor |
|---|---|
| Proyecto | SIP (Sistema Inteligente de Predicción) |
| Versión | 1.0 |
| Fecha | Febrero 2026 |
| Alcance de este documento | **Backend únicamente** |
| Lenguaje | Python 3.12 |
| Asesor metodológico | Jorge Gallego (IDB; coautor de VigIA y Gallego et al. 2021) |
| Bases académicas | Gallego, Rivero & Martínez (2021); Salazar, Pérez & Gallego (2024) — VigIA; Mojica (2021) |

---

## 1. Resumen Ejecutivo

SIP es un sistema backend en Python que recibe el identificador de un contrato público colombiano del SECOP II, consulta la API de datos abiertos, ejecuta 4 modelos XGBoost pre-entrenados y un índice de reglas (IRIC), y devuelve un **Índice Compuesto de Riesgo (ICR)** con explicaciones SHAP feature-por-feature.

**Decisiones de diseño fundamentales:**

- **Unidad de análisis:** contrato individual.
- **Modo temporal:** inferencia en tiempo real sobre modelos entrenados offline.
- **Algoritmo:** XGBoost para los 4 modelos, con SHAP (TreeSHAP) para explicabilidad.
- **Enfoque:** detección temprana (solo variables pre-ejecución).
- **Segmentación:** un solo modelo por outcome.
- **Índice compuesto:** promedio ponderado simple de las probabilidades de los 4 modelos + el IRIC. Pesos iniciales iguales (1/5 cada uno).
- **IRIC (Índice de Riesgo de Irregularidades Contractuales):** cumple doble rol: (a) se presenta como estadística descriptiva al usuario, y (b) se incluye como feature de entrada para los modelos ML.
- **Frontend:** se desarrollará en fase posterior. Este backend expone una API REST (FastAPI) que el frontend consumirá. La sección 10 define el contrato de interfaz.

---

## 2. Objetivos

### 2.1 Objetivo General

Construir un backend que, dado un ID de contrato SECOP II, calcule un índice compuesto de riesgo de corrupción basado en múltiples modelos ML y un índice de reglas, exponiendo los resultados vía API REST.

### 2.2 Objetivos Específicos

1. Construir un **Registro Consolidado de Antecedentes de Corrupción (RCAC)** que unifique 6+ fuentes de sanciones a nivel de persona (CC/NIT), incluyendo representantes legales.
2. Calcular un **IRIC** (11 red flags binarias) adaptado al nivel nacional, calibrado por tipo de contrato.
3. Entrenar **4 modelos XGBoost** de clasificación binaria para: sobrecostos (M1), retrasos (M2), aparición en Contraloría (M3), multas SECOP (M4).
4. Generar **SHAP values** por predicción para explicar cada resultado.
5. Combinar en un **Índice Compuesto de Riesgo (ICR)** con promedio ponderado.
6. Exponer todo vía **API REST** (FastAPI) lista para ser consumida por un frontend futuro.


## 3. Arquitectura

### 3.1 Dos Pipelines

```
PIPELINE OFFLINE
════════════════════════════════════
  Descarga masiva      Feature         Entrenamiento
  SECOP II API    ───► Engineering ───► XGBoost × 4
  + Fuentes RCAC       + RCAC build     modelos
                       + IRIC calibrar
                              │
                              ▼
                       Artifacts: modelos .pkl, RCAC .pkl,
                       iric_thresholds.json, metadata.json


PIPELINE ONLINE (tiempo real, por contrato)
════════════════════════════════════════════
  POST /api/v1/analyze    Consulta SECOP     Feature
  { contract_id }    ───► II API + RCAC ───► Engineering
                          lookup              (mismo código)
                                                  │
                                                  ▼
                                            Cálculo IRIC
                                                  │
                                                  ▼
                                            Inferencia XGBoost × 4
                                            + SHAP values
                                                  │
                                                  ▼
                                            ICR (promedio ponderado)
                                                  │
                                                  ▼
                                            JSON Response
```

**Principio clave:** el código de feature engineering, cálculo de IRIC e inferencia es **exactamente el mismo** en ambos pipelines. La única diferencia es la fuente de datos (batch vs. API individual).

### 3.2 Estructura del Proyecto

```
sip/
├── config/
│   ├── settings.py                # Constantes, API URLs, paths, feature lists
│   ├── iric_thresholds.json       # Umbrales del IRIC calibrados (generado offline)
│   └── model_weights.json         # Pesos del ICR: {"M1": 0.20, "M2": 0.20, ...}
│
├── data/
│   ├── secop_client.py            # Cliente async para Socrata API (datos.gov.co)
│   ├── rcac_builder.py            # Construye el RCAC desde las 6+ fuentes
│   ├── rcac_lookup.py             # Dict en memoria para consulta O(1)
│   └── batch_downloader.py        # Descarga masiva para entrenamiento
│
├── features/
│   ├── contract_features.py       # Features del contrato (valor, modalidad, tipo, etc.)
│   ├── provider_features.py       # Features del proveedor (antigüedad, historial, RCAC)
│   ├── process_features.py        # Features del proceso (ofertas, publicidad, decisión)
│   ├── temporal_features.py       # Features temporales (duraciones, firma-a-inicio, mes)
│   ├── iric.py                    # Cálculo de los 11 componentes del IRIC
│   └── pipeline.py                # Orquestador: raw data → feature vector completo
│
├── models/
│   ├── trainer.py                 # Entrenamiento: XGBoost + RandomSearch + StratifiedKFold
│   ├── predictor.py               # Inferencia: carga .pkl → predict_proba + SHAP
│   ├── composite_index.py         # ICR = Σ(wi × Pi)
│   ├── class_balance.py           # Estrategias de desbalance (scale_pos_weight, upsample)
│   └── evaluation.py              # Métricas: AUC, MAP@k, NDCG@k, Brier, Precision, Recall
│
├── api/
│   ├── app.py                     # FastAPI application
│   ├── routes.py                  # POST /analyze, GET /health, POST /analyze/batch
│   └── schemas.py                 # Pydantic models (request/response)
│
├── training/
│   ├── train_pipeline.py          # Pipeline completo: download → features → train → evaluate
│   └── calibrate_iric.py          # Calcula percentiles para iric_thresholds.json
│
├── artifacts/                     # Generados por el pipeline offline
│   ├── models/                    # M1.pkl, M2.pkl, M3.pkl, M4.pkl
│   ├── rcac.pkl                   # RCAC serializado
│   ├── iric_thresholds.json       # Umbrales calibrados
│   └── training_metadata.json     # Fechas, métricas, versiones
│
└── tests/
    ├── test_rcac.py
    ├── test_features.py
    ├── test_iric.py
    ├── test_models.py
    └── test_api.py
```

---

## 4. Fuentes de Datos

### 4.1 Datos SECOP II (variables explicativas)

Todas accesibles vía Socrata API en datos.gov.co. Se incluyen dataset IDs para acceso directo.

#### 4.1.1 Contratos Electrónicos

- **Dataset:** `jbjy-vk9h`
- **Archivo local:** `Datos_Abiertos/contratos_SECOP.csv`
- **Dimensiones:** 341,727 × 87 | 570 MB
- **Unidad:** Contrato individual
- **Rol:** Tabla principal. Variables core del contrato.
- **Columnas clave usadas:**

```
ID Contrato                              → Llave primaria
Codigo Entidad, Nombre Entidad           → Entidad contratante
Codigo Proveedor, Nombre Proveedor       → Proveedor adjudicado
Tipo de Documento Proveedor              → "CC" o "NIT" (llave RCAC)
Documento Proveedor                      → Número de doc (llave RCAC)
Valor del Contrato                       → Monto en COP
Modalidad de Contratacion                → Directa, licitación, etc.
Tipo de Contrato                         → Servicios prof., obra, etc.
Fecha de Firma                           → Fecha firma
Fecha de Inicio del Contrato             → Fecha inicio planeado
Fecha de Fin del Contrato                → Fecha fin planeado
Fecha de Inicio de Ejecucion             → (EXCLUIDA: post-ejecución)
Fecha de Fin de Ejecucion                → (EXCLUIDA: post-ejecución)
Departamento, Ciudad                     → Ubicación geográfica
Codigo UNSPSC                            → Clasificación producto/servicio
Justificacion Modalidad de Contratacion  → Justificación del mecanismo
Origen de los Recursos                   → Fuente de financiación
```

#### 4.1.2 Procesos de Contratación

- **Dataset:** `p6dx-8zbt`
- **Archivo local:** `Datos_Abiertos/procesos_SECOP.csv`
- **Dimensiones:** 5,106,527 × 59 | 5.3 GB
- **Rol:** Variables de fase pre-contractual.
- **Columnas clave:**

```
ID Proceso                          → Llave de cruce con contratos
Fecha de Publicacion del Proceso    → Inicio publicidad
Fecha de Ultima Publicacion         → Fin publicidad
Fecha de Adjudicacion               → Adjudicación
Numero de Ofertas Recibidas         → Competencia
Duracion del Proceso                → Duración total
Tipo de Proceso                     → Clasificación
```

#### 4.1.3 Ofertas por Proceso

- **Archivo local:** `Datos_Abiertos/ofertas_proceso_SECOP.csv`
- **Dimensiones:** 6,454,843 × 163 | 3.4 GB
- **Rol:** Competencia real: cuántos oferentes, dispersión de ofertas.

#### 4.1.4 Proponentes por Proceso

- **Archivo local:** `Datos_Abiertos/proponentes_proceso_SECOP.csv`
- **Dimensiones:** 3,310,267 × 9 | 841 MB
- **Rol:** Detalle de proponentes (tipo doc, rol en consorcio). Historial del proveedor.
- **Columnas clave:**

```
ID Proceso          → Cruce con procesos
ID Proponente       → Identificador
Nombre Proponente   → Nombre/razón social
Tipo de Documento   → CC/NIT
Numero de Documento → Llave RCAC
Rol                 → Individual, consorcio, etc.
```

#### 4.1.5 Proveedores Registrados

- **Archivo local:** `Datos_Abiertos/proveedores_registrados.csv`
- **Dimensiones:** 1,555,059 × 55 | 564 MB
- **Rol:** Registro maestro de proveedores. Tabla de cruce entre contratos y RCAC. Contiene datos del representante legal.
- **Columnas clave:**

```
ID Proveedor                → Identificador
Nombre / Razon Social       → Nombre
Tipo de Persona             → Natural / Jurídica
Tipo de Documento           → CC / NIT / CE / Pasaporte
Numero de Documento         → Llave RCAC (cruce primario)
Fecha de Registro           → Antigüedad del proveedor
[Columnas de rep. legal]    → Nombre, documento del representante
                               (cruce secundario contra RCAC)
```

#### 4.1.6 Ejecución de Contratos

- **Archivo local:** `Datos_Abiertos/ejecucion_contratos.csv`
- **Dimensiones:** 4,211,724 × 16 | 682 MB
- **Rol:** Cantidades planeadas vs. adjudicadas vs. recibidas. Permite construir labels de sobrecostos y retrasos.
- **Columnas clave:**

```
ID Contrato            → Cruce
Cantidad planeada      → Baseline
Cantidad adjudicada    → Valor adjudicado
Cantidad Recibida      → Valor real
Valor planeado         → Baseline monetario
Valor adjudicado       → Valor monetario real
```

#### 4.1.7 Adiciones (fuente de las variables objetivo M1 y M2)

- **Dataset:** `cb9c-h8sn` (SECOP II Adiciones)
- **Rol:** **Variables objetivo para M1 y M2.** Registro de modificaciones contractuales.
- **Construcción de labels:**
  - **M1 (Sobrecostos):** binaria (0/1). Vale 1 si el contrato tiene ≥ 1 adición en valor.
  - **M2 (Retrasos):** binaria (0/1). Vale 1 si el contrato tiene ≥ 1 adición en tiempo.
  - Misma estrategia usada en VigIA (Salazar et al., 2024, sección 4.4).

### 4.2 Datos para el RCAC (Registro Consolidado de Antecedentes de Corrupción)

Estas fuentes identifican personas naturales y jurídicas con antecedentes de corrupción. Se cruzan con proveedores del SECOP para generar features.

#### Fuente 1: Boletines de la Contraloría

- **Archivo:** `Contraloria Data Merger/boletines.csv`
- **Dimensiones:** 10,817 × 9 | 1.3 MB
- **Identificador:** `tipo de documento` + `numero de documento`
- **Captura:** Responsables fiscales declarados por la Contraloría General. Utilizado para el RCAC y el Modelo XGBoost 3 (M3)
- **Columnas:** `Responsable Fiscal`, `tipo de documento`, `numero de documento`, `Entidad Afectada`, `Cuantía del Daño Fiscal`, `Estado del Proceso`.

#### Fuente 2: Sanciones SIRI (Procuraduría)

- **Archivo:** `PACO/sanciones_SIRI_PACO.csv`
- **Dimensiones:** 46,583 × 28 | 18.2 MB
- **Identificador:** Columnas posicionales 5 (`Tipo de documento`) y 6 (`Número de documento`)
- **Captura:** Sanciones disciplinarias y penales. Servidores públicos y particulares. **Fuente más grande del RCAC.**
- **Nota:** Archivo sin encabezados explícitos. Interpretar por posición.


#### Fuente 3: Datos de Personas

- **Archivo:** `organized_people_data.csv`
- **Tamaño:** 12 MB
- **Captura:** Personas involucradas en corrupción según PACO.
- **Estado:** Insumo separado, sin integrar. Requiere análisis de estructura.
- **Acción:** Analizar columnas de identificación e integrar en rcac_builder.py.

#### Fuente 4: Datos de Personas

- **Archivo:** `SIP Code/Data/Propia/Monitor`
- **Tamaño:** 
- **Captura:** Personas involucradas en corrupción según Monitor Ciudadano.
- **Estado:** Insumo separado, sin integrar. Requiere análisis de estructura.
- **Acción:** Extraer nombres de personas o empresas con identificador CC o NIT. Analizar grado de crimen. 
---

## 5. Registro Consolidado de Antecedentes de Corrupción (RCAC)

### 5.1 Propósito

Tabla unificada indexada por `(tipo_documento, numero_documento)` que consolida todos los antecedentes de las 7 fuentes de la sección 4.2. Se cruza contra `proveedores_registrados.csv` para enriquecer cada contrato.

### 5.2 Schema del Registro

```python
@dataclass
class RCACRecord:
    tipo_documento: str             # "CC" | "NIT" | "CE" | "PASAPORTE" | "OTRO"
    numero_documento: str           # Normalizado: solo dígitos, sin puntos/guiones/dígito verificación
    nombre: str
    tipo_persona: str               # "NATURAL" | "JURIDICA"

    # Flags binarias por fuente (0/1)
    tiene_responsabilidad_fiscal_contraloria: int
    tiene_sancion_disciplinaria_siri: int
    tiene_sancion_penal_siri: int
    tiene_multa_secop: int
    tiene_antecedente_colusion_sic: int
    tiene_registro_monitor_ciudadano: int

    # Conteos acumulados
    num_responsabilidades_fiscales: int
    num_sanciones_disciplinarias: int
    num_sanciones_penales: int
    num_multas_secop: int
    cuantia_total_dano_fiscal: float  # Suma de cuantías (Contraloría)

    # Temporalidad
    fecha_primera_sancion: Optional[date]
    fecha_ultima_sancion: Optional[date]

    # Meta
    fuentes: List[str]              # Nombres de fuentes que reportan
    num_fuentes_distintas: int      # Cuántas fuentes independientes la reportan
```

### 5.3 Pipeline de Construcción (`rcac_builder.py`)

```
Paso 1: NORMALIZACIÓN DE DOCUMENTOS
  - Cada fuente tiene formatos distintos (CC, C.C., cédula, NIT con dígito verificación...)
  - Normalizar tipo_documento → catálogo controlado: CC, NIT, CE, PASAPORTE, OTRO
  - Normalizar numero_documento → string numérico puro (strip puntos, guiones, espacios)
  - Para responsabilidades_fiscales_PACO.csv: parsear campo combinado "Tipo y Num Documento"
  - Para sanciones_SIRI_PACO.csv: usar columnas posicionales 5 y 6

Paso 2: DEDUPLICACIÓN
  - Agrupar por (tipo_documento, numero_documento)
  - Un individuo en múltiples fuentes = información valiosa → num_fuentes_distintas
  - Para duplicados dentro de la misma fuente: agregar conteos, mantener la fecha más antigua/reciente

Paso 3: CRUCE CON PROVEEDORES
  - Inner join con proveedores_registrados.csv por (tipo_documento, numero_documento)
  - Esto genera features para el proveedor directo

Paso 4: CRUCE DE REPRESENTANTES LEGALES
  - Para proveedores con tipo_persona == "JURIDICA":
    - Extraer tipo_documento y numero_documento del representante legal
    - Segundo cruce contra RCAC
  - Esto detecta empresas fachada: NIT limpio pero representante legal con antecedentes

Paso 5: SERIALIZACIÓN
  - Dict indexado por (tipo_doc, num_doc) → RCACRecord
  - Serializar con joblib para carga rápida en el pipeline online
```

### 5.4 Features Derivadas del RCAC (para cada contrato)

```python
# Features del proveedor directo
proveedor_en_rcac: bool                   # ¿Tiene algún antecedente?
proveedor_responsable_fiscal: bool
proveedor_sancion_disciplinaria: bool
proveedor_sancion_penal: bool
proveedor_multa_secop_previa: bool
proveedor_colusion_sic: bool
proveedor_monitor_ciudadano: bool
proveedor_num_antecedentes_total: int
proveedor_num_fuentes_distintas: int
proveedor_cuantia_dano_fiscal: float
proveedor_dias_desde_ultima_sancion: int | None

# Features del representante legal (solo personas jurídicas)
representante_en_rcac: bool
representante_num_antecedentes: int
```

---

## 6. IRIC — Índice de Riesgo de Irregularidades Contractuales

### 6.1 Fundamento

Adaptado de VigIA (Salazar et al., 2024), basado en Zuleta et al. (2019) e IMCO (2018). Originalmente calibrado para Bogotá; este sistema lo recalibra a nivel nacional.

### 6.2 Doble Rol

1. **Feature de los modelos ML:** se calcula ANTES de la inferencia y se incluye como variable explicativa para M1-M4. Esto da a los modelos una "opinión experta codificada" como insumo.
2. **Estadística descriptiva:** se muestra al usuario desglosado por componente, permitiendo ver qué red flags están activas.

### 6.3 Componentes (11 variables binarias, 2 calculos de anomalías)

#### Dimensión 1: Falta de Competencia (6 variables)

| # | Código | Vale 1 cuando... | Referencia |
|---|---|---|---|
| 1 | `unico_proponente` | El proceso recibió ≤ 1 oferta | Baltrunaite et al. (2020); Szucs (2023) |
| 2 | `proveedor_multiproposito` | Proveedor con > 1 actividad económica distinta en UNSPSC | Open Contracting Partnership (2020) |
| 3 | `historial_proveedor_alto` | Proveedor con > P95 contratos previos ganados (por tipo de contrato) | Fazekas & Kocsis (2020) |
| 4 | `contratacion_directa` | Modalidad = contratación directa | Fazekas & Kocsis (2020); Bosio et al. (2020) |
| 5 | `regimen_especial` | Modalidad = régimen especial | Zuleta et al. (2019) |
| 6 | `periodo_publicidad_extremo` | Duración publicidad < P1 o > P99 (por tipo de contrato) | Decarolis & Giorgiantonio (2022) |

#### Dimensión 2: Falta de Transparencia (2 variables)

| # | Código | Vale 1 cuando... | Referencia |
|---|---|---|---|
| 7 | `datos_faltantes` | Campos obligatorios ausentes: ID proveedor, justificación modalidad, o valor del contrato ausente/> P99 por tipo | Fazekas et al. (2016) |
| 8 | `periodo_decision_extremo` | Días entre cierre de ofertas y firma < P5 o > P95 (por tipo) | Fazekas & Kocsis (2020) |

#### Dimensión 3: Anomalías (3 variables)

| # | Código | Vale 1 cuando... | Referencia |
|---|---|---|---|
| 9 | `proveedor_sobrecostos_previos` | Proveedor tiene contratos previos con adiciones en valor | VigIA (Salazar et al., 2024) |
| 10 | `proveedor_retrasos_previos` | Proveedor tiene contratos previos con adiciones en tiempo | VigIA (Salazar et al., 2024) |
| 11 | `ausencia_proceso` | No se encuentra proceso de contratación asociado en SECOP | Zuleta et al. (2019) |


#### Calculo de anomalía 1: Curtosis

| Campo | Detalle |
|---|---|
| **Código** | `curtosis_licitacion` |
| **Fórmula** | `Kurt(bₜ) = [n(n+1)/(n-1)(n-2)(n-3)] × Σ((bᵢₜ - μₜ)/σₜ)⁴ − [3(n-1)²/(n-2)(n-3)]` |
| **Parámetros** | `n` = total ofertas; `bᵢₜ` = oferta `i`; `σₜ` = desviación estándar; `μₜ` = media aritmética |
| **Señal** | Escalado inteligente con factor común → pocas variaciones entre oferta más alta y más baja |
| **Referencia** | Imhof (2018) |

#### Cálculo de anomalía 2: Diferencia Relativa Normalizada

| Campo | Detalle |
|---|---|
| **Código** | `diferencia_relativa_norm` |
| **Fórmula** | `DRN = (b₂ₜ − b₁ₜ) / [(Σᵢ₌₁ⁿ⁻¹ bⱼₜ − bᵢₜ) / (n − 1)]` |
| **Parámetros** | `b₁ₜ`, `b₂ₜ` = ofertas adyacentes más bajas; ofertas ordenadas de forma creciente |
| **Señal** | Valor > 1 indica que la brecha entre las dos ofertas más bajas supera el promedio de diferencias adyacentes |
| **Interpretación** | Distancia entre ofertas perdedoras (cobertura) significativamente inferior a la de la oferta ganadora |
| **Referencia** | Imhof (2018) |

### 6.4 Fórmula

```
IRIC = (1/11) × Σ(componente_i)     para i = 1,...,11
Cada componente_i ∈ {0, 1}
Resultado: IRIC ∈ [0, 1]

Sub-scores por dimensión:
  iric_competencia    = (1/6) × Σ(componentes 1-6)
  iric_transparencia  = (1/2) × Σ(componentes 7-8)
  iric_anomalias      = (1/3) × Σ(componentes 9-11)
```

### 6.5 Calibración de Umbrales Nacionales (`calibrate_iric.py`)

Los umbrales de percentiles se calculan offline sobre los datos nacionales, diferenciando por tipo de contrato. Se almacenan en `iric_thresholds.json`:

```json
{
  "servicios_profesionales": {
    "historial_proveedor_p95": 42,
    "periodo_publicidad_p1": 1,
    "periodo_publicidad_p99": 45,
    "valor_contrato_p99": 980000000,
    "periodo_decision_p5": 2,
    "periodo_decision_p95": 120
  },
  "otros": {
    "historial_proveedor_p95": 28,
    "periodo_publicidad_p1": 3,
    "periodo_publicidad_p99": 90,
    "valor_contrato_p99": 2500000000,
    "periodo_decision_p5": 5,
    "periodo_decision_p95": 180
  }
}
```

---

## 7. Modelos Predictivos

### 7.1 Los 4 Modelos

| ID | Variable Objetivo | Tipo de Waste | Fuente del Label | % positivos estimado |
|---|---|---|---|---|
| **M1** | Sobrecostos (adición en valor) | Pasivo | SECOP II Adiciones (`cb9c-h8sn`) | ~16% (VigIA) |
| **M2** | Retrasos (adición en tiempo) | Pasivo | SECOP II Adiciones (`cb9c-h8sn`) | ~18% (VigIA) |
| **M3** | Proveedor aparece como responsable fiscal | Activo | Boletines Contraloría (archivo .csv) | ~1-2% (Gallego et al. 2021) |
| **M4** | Proveedor con multa/sanción SECOP | Mixto | RCAC (multas SECOP) | ~1% (estimado) |

### 7.2 Algoritmo: XGBoost

### 7.3 Features por Categoría

Todos los modelos comparten el mismo vector de features. La selección fina se hace vía importancia de variables del propio XGBoost. Se usa **enfoque de detección temprana: solo variables pre-ejecución**.

#### Categoría A: Variables del Contrato

| Feature | Tabla Fuente | Transformación | Evidencia en la Literatura |
|---|---|---|---|
| `log_valor_contrato` | contratos_SECOP → `Valor del Contrato` | log(valor + 1) | Gallego et al. (2021): top predictor para Contraloría, Confecámaras y extensiones. VigIA: top predictor para sobrecostos. |
| `tipo_contrato_cat` | contratos_SECOP → `Tipo de Contrato` | Categórica (agrupar < 0.1% en "Otro") | VigIA: rendimiento diferencial (AUC 0.948 profesionales vs 0.872 otros). |
| `modalidad_contratacion_cat` | contratos_SECOP → `Modalidad de Contratacion` | Categórica: Directa, Licitación, Selección Abreviada, Mínima Cuantía, Régimen Especial, Otro | Gallego et al. (2021): directa tipo H fue top predictor. |
| `es_contratacion_directa` | Derivada de modalidad | Binaria (1 si directa) | Fazekas & Kocsis (2020): red flag fundamental. |
| `es_regimen_especial` | Derivada de modalidad | Binaria | Zuleta et al. (2019). |
| `es_servicios_profesionales` | Derivada de tipo | Binaria | VigIA: se comportan diferente al resto. |
| `unspsc_categoria` | contratos_SECOP → `Codigo UNSPSC` | Primeros 2 dígitos (categoría) | VigIA: sector Cultura predictivo. Gallego et al.: transporte, servicios públicos. |
| `departamento_cat` | contratos_SECOP → `Departamento` | Categórica (32 deptos + Bogotá D.C.) | Gallego et al. (2021): Antioquia, Bogotá, Cundinamarca, Valle. |
| `origen_recursos_cat` | contratos_SECOP → `Origen de los Recursos` | Categórica | Mojica (2021): SGP como predictor. |
| `tiene_justificacion_modalidad` | contratos_SECOP → `Justificacion Modalidad de Contratacion` | Binaria: 1 si no nula/vacía | Fazekas et al. (2016). |

#### Categoría B: Variables Temporales y de Duración

| Feature | Cálculo | Evidencia |
|---|---|---|
| `dias_firma_a_inicio` | `Fecha Inicio Contrato` − `Fecha Firma` | VigIA: top predictor. Valores negativos (firma posterior al inicio) = red flag. |
| `duracion_contrato_dias` | `Fecha Fin Contrato` − `Fecha Inicio Contrato` | Gallego et al. (2021): top predictor de extensiones. |
| `dias_publicidad` | `Fecha Cierre Ofertas` − `Fecha Publicación Proceso` | VigIA: predictor para no-profesionales. Fazekas & Kocsis (2020). |
| `dias_decision` | `Fecha Firma` − `Fecha Cierre Ofertas` | Gallego et al. (2021): "waiting period" como top predictor. |
| `dias_proveedor_registrado` | `Fecha Firma` − `Fecha Registro Proveedor` | VigIA: top predictor. Proveedores < 228 días = mayor riesgo. |
| `firma_posterior_a_inicio` | Binaria: 1 si `dias_firma_a_inicio` < 0 | VigIA: anomalía de proceso. |
| `mes_firma` | month(Fecha Firma) | Gallego et al. (2021): proximidad a elecciones como predictor. |
| `trimestre_firma` | quarter(Fecha Firma) | Ciclo presupuestal. |
| `dias_a_proxima_eleccion` | Fecha Firma → días hasta próxima elección presidencial | Gallego et al. (2021): predictor específico para M3. |

**Variables temporales EXCLUIDAS (solo disponibles post-ejecución):**

```
Fecha de Inicio de Ejecucion
Fecha de Fin de Ejecucion
Pagos de anticipos
Variables derivadas de ejecución (start-to-end execution days)
```

#### Categoría C: Variables del Proveedor

| Feature | Cálculo | Evidencia |
|---|---|---|
| `tipo_persona_proveedor` | proveedores_registrados → `Tipo de Persona` | Gallego et al. (2021): tipo H directa (personas naturales). |
| `num_contratos_previos` | Conteo de contratos del proveedor con fecha firma anterior | VigIA: base para historial_proveedor_alto del IRIC. |
| `num_ofertas_recibidas` | procesos_SECOP → `Numero de Ofertas Recibidas` | VigIA: predictor para no-profesionales. |
| `num_proponentes` | Conteo en proponentes_proceso_SECOP por proceso | Competencia real. |
| `proponente_unico` | Binaria: 1 si num_proponentes ≤ 1 | Baltrunaite et al. (2020). |
| `num_actividades_economicas` | Conteo de UNSPSC distintos en contratos previos del proveedor | Base para multiproposito IRIC. |
| `valor_total_contratos_previos` | Suma de valores de contratos previos del proveedor | Historial de volumen. |
| `num_sobrecostos_previos` | Conteo de contratos previos con adición en valor | VigIA: componente IRIC + feature. |
| `num_retrasos_previos` | Conteo de contratos previos con adición en tiempo | VigIA: componente IRIC + feature. |


#### Categoría D: IRIC como Feature

| Feature | Descripción |
|---|---|
| `iric_score` | IRIC total (0-1) |
| `iric_competencia` | Sub-score dimensión competencia (0-1) |
| `iric_transparencia` | Sub-score dimensión transparencia (0-1) |
| `iric_anomalias` | Sub-score dimensión anomalías (0-1) |

### 7.4 Manejo de Desbalance de Clases

Cada modelo tiene un nivel diferente de desbalance. Se evalúan **3 estrategias por modelo** y se selecciona la mejor por rendimiento en validación cruzada:

**Estrategia 1: `scale_pos_weight` de XGBoost (primera opción)**

Parámetro nativo. Se configura como `n_negativos / n_positivos`. En Gallego et al. (2021): peso de 25 para Contraloría/Confecámaras, 10 para extensiones. No modifica los datos, solo la función de pérdida.

**Estrategia 2: Up-sampling de la clase minoritaria**

Duplicar observaciones de la clase positiva hasta proporción objetivo (e.g., 25%). En Gallego et al. (2021): produjo resultados ligeramente mejores en MAP@k y NDCG@k que pesos.

**Estrategia 3: Validación cruzada estratificada (obligatoria siempre)**

Toda validación cruzada debe ser estratificada. Crítico para M3 y M4 donde clase positiva < 2%.

Implementación en `class_balance.py`:

```python
def get_balance_strategies(y_train):
    """Retorna lista de configuraciones a evaluar."""
    pos_ratio = y_train.mean()
    strategies = []

    # Estrategia 1: scale_pos_weight
    strategies.append({
        "name": "scale_pos_weight",
        "xgb_params": {"scale_pos_weight": (1 - pos_ratio) / pos_ratio},
        "X_train": None,  # usar datos originales
        "y_train": None
    })

    # Estrategia 2: up-sampling
    X_up, y_up = upsample_minority(X_train, y_train, target_ratio=0.25)
    strategies.append({
        "name": "upsample_25pct",
        "xgb_params": {},
        "X_train": X_up,
        "y_train": y_up
    })

    return strategies
```

### 7.5 Entrenamiento y Validación

#### Split de Datos

- **Train:** 70% de contratos históricos con ejecución finalizada.
- **Test (hold-out):** 30% restante.
- **Validación cruzada:** 5-fold estratificada sobre train para optimización de hiperparámetros.

#### Hiperparámetros a Optimizar (Random Search)

```python
PARAM_GRID = {
    "max_depth": [3, 5, 7, 9, 11],
    "learning_rate": [0.01, 0.05, 0.1, 0.3],
    "n_estimators": [100, 300, 500, 800, 1000],
    "min_child_weight": [1, 5, 13, 30],
    "colsample_bytree": [0.5, 0.7, 0.85, 1.0],
    "gamma": [0, 1, 5, 10],
    "scale_pos_weight": [calculado_por_modelo],
}
# Random search: 200 iteraciones por modelo (Mojica 2021 evaluó 136K combinaciones)
```

#### Métricas de Evaluación

| Métrica | Descripción | Referencia | Rol |
|---|---|---|---|
| **AUC-ROC** | Área bajo curva ROC | VigIA | Métrica principal |
| **MAP@100** | Precisión promedio en top-100 | Gallego et al. (2021) | "Si investigan los 100 más riesgosos, ¿cuántos lo son?" |
| **MAP@1000** | Precisión promedio en top-1000 | Gallego et al. (2021) | Escala mayor |
| **NDCG@k** | Ganancia acumulada descontada | Gallego et al. (2021) | Calidad del ranking |
| **Precisión** | TP / (TP + FP) | VigIA | ¿Cuántos alertados son reales? |
| **Recall** | TP / (TP + FN) | VigIA | ¿Cuántos reales fueron detectados? |
| **Brier Score** | Calibración de probabilidades | Gallego et al. (2021) | ¿Son confiables las probabilidades? |


### 7.6 Explicabilidad: SHAP Values

Cada predicción incluye SHAP values calculados con TreeSHAP:

```python
import shap

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_contrato)

# Para el response: top-N features con mayor |SHAP value|
top_features = sorted(
    zip(feature_names, shap_values[0]),
    key=lambda x: abs(x[1]),
    reverse=True
)[:N]
# Ejemplo: [("contratacion_directa", +0.15), ("proveedor_responsable_fiscal", +0.12), ...]
```

Interpretación para el usuario: "Este contrato tiene riesgo alto *porque*: contratación directa (+0.15), proveedor con antecedentes fiscales (+0.12), firma posterior al inicio (+0.10)..."

---

## 8. Índice Compuesto de Riesgo (ICR)

### 8.1 Fórmula

```
ICR = w1 × P(M1) + w2 × P(M2) + w3 × P(M3) + w4 × P(M4) + w5 × IRIC

Donde:
  P(Mi) = probabilidad predicha por modelo i ∈ [0, 1]
  IRIC  = índice de irregularidades ∈ [0, 1]
  Σ(wi) = 1
  ICR ∈ [0, 1]
```

### 8.2 Pesos Iniciales

```json
{
  "M1_sobrecostos": 0.20,
  "M2_retrasos": 0.20,
  "M3_contraloria": 0.20,
  "M4_multas": 0.20,
  "IRIC": 0.20
}
```

Pesos iguales (1/5) como configuración base. La calibración empírica de pesos se define como tarea de investigación futura. Los pesos son configurables en `config/model_weights.json` y pueden ajustarse sin reentrenar modelos.

### 8.3 Categorías de Riesgo

| Rango ICR | Categoría | Color (para frontend) |
|---|---|---|
| 0.00 – 0.20 | Muy Bajo | Verde |
| 0.20 – 0.40 | Bajo | Verde claro |
| 0.40 – 0.60 | Medio | Amarillo |
| 0.60 – 0.80 | Alto | Naranja |
| 0.80 – 1.00 | Muy Alto | Rojo |

---


## 9. API REST — Contrato de Interfaz con Frontend

### 9.1 Framework

FastAPI. Documentación OpenAPI auto-generada en `/docs`. Esta documentación sirve como especificación completa para el equipo de frontend.

### 9.2 Endpoints

#### `POST /api/v1/analyze` — Análisis de Contrato Individual

**Request:**
```json
{
  "contract_id": "CO1.PCCNTR.12345"
}
```

**Response:**
```json
{
  "contract_id": "CO1.PCCNTR.12345",

  "contract_summary": {
    "entity_name": "Alcaldía de Bogotá",
    "provider_name": "Empresa XYZ S.A.S",
    "provider_document_type": "NIT",
    "provider_document_number": "900123456",
    "value_cop": 150000000,
    "contract_type": "Servicios profesionales",
    "procurement_method": "Contratación directa",
    "sign_date": "2025-03-15",
    "department": "Bogotá D.C."
  },

  "composite_risk_index": {
    "score": 0.72,
    "category": "Alto",
    "components": {
      "M1_sobrecostos": { "probability": 0.65, "weight": 0.20 },
      "M2_retrasos": { "probability": 0.58, "weight": 0.20 },
      "M3_contraloria": { "probability": 0.82, "weight": 0.20 },
      "M4_multas": { "probability": 0.91, "weight": 0.20 },
      "IRIC": { "score": 0.636, "weight": 0.20 }
    }
  },

  "iric_detail": {
    "score": 0.636,
    "dimensions": {
      "competencia": 0.667,
      "transparencia": 0.500,
      "anomalias": 0.667
    },
    "flags": {
      "unico_proponente": true,
      "proveedor_multiproposito": false,
      "historial_proveedor_alto": true,
      "contratacion_directa": true,
      "regimen_especial": false,
      "periodo_publicidad_extremo": true,
      "datos_faltantes": false,
      "periodo_decision_extremo": true,
      "proveedor_sobrecostos_previos": true,
      "proveedor_retrasos_previos": true,
      "ausencia_proceso": false
    }
  },

  "provider_background": {
    "in_rcac": true,
    "document_type": "NIT",
    "document_number": "900123456",
    "flags": {
      "responsable_fiscal_contraloria": true,
      "sancion_disciplinaria_siri": false,
      "sancion_penal_siri": false,
      "multa_secop_previa": true,
      "colusion_sic": false,
      "monitor_ciudadano": false
    },
    "total_antecedentes": 3,
    "fuentes_distintas": 2,
    "cuantia_dano_fiscal_cop": 45000000,
    "representante_legal": {
      "in_rcac": false,
      "document_type": "CC",
      "num_antecedentes": 0
    }
  },

  "shap_explanation": {
    "M1_sobrecostos": {
      "top_features": [
        { "feature": "log_valor_contrato", "shap_value": 0.18, "actual_value": 18.83 },
        { "feature": "es_contratacion_directa", "shap_value": 0.12, "actual_value": 1 },
        { "feature": "dias_proveedor_registrado", "shap_value": -0.08, "actual_value": 540 },
        { "feature": "iric_score", "shap_value": 0.06, "actual_value": 0.636 },
        { "feature": "proveedor_responsable_fiscal", "shap_value": 0.05, "actual_value": 1 }
      ]
    },
    "M2_retrasos": { "top_features": [] },
    "M3_contraloria": { "top_features": [] },
    "M4_multas": { "top_features": [] }
  },

  "metadata": {
    "model_version": "2025-Q4",
    "rcac_last_updated": "2025-12-01",
    "iric_thresholds_version": "2025-Q4",
    "analysis_timestamp": "2026-02-26T14:30:00Z"
  }
}
```

#### `GET /api/v1/health` — Estado del Sistema

```json
{
  "status": "healthy",
  "model_version": "2025-Q4",
  "last_training_date": "2025-12-15",
  "rcac_last_updated": "2025-12-01",
  "rcac_total_records": 58432,
  "secop_api_status": "connected",
  "models_loaded": ["M1", "M2", "M3", "M4"]
}
```

#### `POST /api/v1/analyze/batch` — Análisis Batch

**Request:**
```json
{
  "contract_ids": ["id1", "id2", "..."],
  "max_contracts": 1000
}
```

**Response:** Array de objetos con la misma estructura que el endpoint individual.

### 9.3 Especificación para Frontend (fase posterior)

El frontend debe consumir esta API. Las siguientes son las visualizaciones esperadas (como guía para el equipo frontend, no son parte de este backend):

- ICR como métrica principal (gauge o número grande con color).
- Desglose por modelo (M1-M4 + IRIC) como gráfico radial o de barras.
- Flags del IRIC como checklist visual (11 componentes rojo/verde).
- Antecedentes del proveedor (RCAC) como sección de detalle.
- SHAP values como waterfall chart o explicación textual por modelo.
- Datos del contrato como resumen en la cabecera.

La documentación OpenAPI de FastAPI (en `/docs`) es la especificación canónica.

---

## 10. Tech Stack

### Dependencias Core

| Componente | Paquete | Versión mínima | Propósito |
|---|---|---|---|
| ML | `xgboost` | 2.0+ | Algoritmo principal × 4 modelos |
| Explicabilidad | `shap` | 0.43+ | TreeSHAP para SHAP values |
| Data | `pandas` | 2.0+ | Procesamiento de datos |
| Data | `numpy` | 1.24+ | Operaciones numéricas |
| ML Utils | `scikit-learn` | 1.3+ | StratifiedKFold, RandomizedSearchCV, métricas |
| API | `fastapi` | 0.100+ | Servidor REST |
| API | `uvicorn` | 0.23+ | ASGI server |
| Serialización | `pydantic` | 2.0+ | Schemas request/response |
| HTTP | `httpx` | 0.25+ | Cliente async para SECOP API |
| Serialización ML | `joblib` | 1.3+ | Guardar/cargar modelos .pkl |
| Testing | `pytest` | 7.0+ | Tests unitarios e integración |

### Dependencias Opcionales (pipeline offline)

| Componente | Paquete | Propósito |
|---|---|---|
| Almacenamiento | `pyarrow` | Archivos Parquet para datos batch |
| Logging | `structlog` | Logging estructurado |

### RCAC en Producción

- **V1 (inicial):** 4 modelos entrenados, RCAC consolidado, cálculos de indices de riesgo hechos y documento .csv con el historial de contratos proovedor.
- **V2 (listo para frontend):** Dict Python en memoria cargado desde `rcac.pkl` al inicio del servidor.
- **V2 (si escala):** Redis para lookup distribuido. Misma interfaz `rcac_lookup.py`.

---

## 12. Roadmap de Implementación

### Fase 1: Infraestructura de Datos (semanas 1-3)

**Entregable:** RCAC construido y validado. Datos SECOP descargados.

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Cliente SECOP II API (Socrata) | `secop_client.py` | Puede descargar las 7 tablas SECOP vía API. Maneja paginación y rate limits. |
| RCAC builder | `rcac_builder.py` | Consolida 7 fuentes. Normaliza documentos. Deduplica. Genera `rcac.pkl`. |
| RCAC lookup | `rcac_lookup.py` | Carga `rcac.pkl`. Consulta O(1) por (tipo_doc, num_doc). Cruce de representantes legales. |
| Tests de datos | `test_rcac.py` | Tests de normalización, deduplicación, cruce. |

### Fase 2: Feature Engineering + IRIC (semanas 4-5)

**Entregable:** Pipeline de features funcional. IRIC calibrado para todos los contratos históricos.

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Features del contrato | `contract_features.py` | Genera todas las features de Categoría A. |
| Features del proveedor | `provider_features.py` | Genera features Categoría C + D (RCAC). |
| Features del proceso | `process_features.py` | Genera features de competencia (ofertas, proponentes). |
| Features temporales | `temporal_features.py` | Genera features Categoría B. Calcula dias_a_proxima_eleccion. |
| IRIC | `iric.py` | Calcula 11 componentes + score total + sub-scores. Usa umbrales de `iric_thresholds.json`. |
| Calibración IRIC | `calibrate_iric.py` | Calcula percentiles nacionales por tipo de contrato. Genera `iric_thresholds.json`. |
| Pipeline orquestador | `pipeline.py` | Raw data → feature vector completo (incluyendo IRIC como feature). Mismo código batch y online. |
| Tests | `test_features.py`, `test_iric.py` | Tests unitarios para cada feature y cada componente IRIC. |

### Fase 3: Entrenamiento de Modelos (semanas 6-8)

**Entregable:** 4 modelos entrenados, evaluados y documentados.

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Estrategias de balance | `class_balance.py` | Implementa scale_pos_weight y up-sampling. Retorna configs a evaluar. |
| Entrenamiento | `trainer.py` | XGBoost + RandomizedSearchCV + StratifiedKFold(5). 200 iteraciones. Guarda mejor modelo .pkl. |
| Evaluación | `evaluation.py` | Calcula AUC, MAP@100, MAP@1000, NDCG@k, Precision, Recall, Brier. Genera reporte JSON. |
| SHAP | `predictor.py` | TreeExplainer. Retorna top-N features con SHAP values. |
| Entrenar M1-M4 | `train_pipeline.py` | 4 modelos entrenados. Todos superan AUC mínimo. Reporte de métricas en archivo .csv|
| Tests | `test_models.py` | Tests de entrenamiento, predicción, SHAP. |

### Fase 4: Índice Compuesto + API (semanas 9-10)

**Entregable:** API funcional end-to-end.

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Índice compuesto | `composite_index.py` | ICR = Σ(wi × Pi). Categorización por rango. Pesos configurables. |
| Inferencia online | `predictor.py` | Carga 4 modelos .pkl. Recibe feature vector. Retorna probabilidades + SHAP. |
| API REST | `app.py`, `routes.py`, `schemas.py` | POST /analyze retorna JSON completo. GET /health funcional. POST /analyze/batch funcional. |
| Tests API | `test_api.py` | Tests end-to-end con contratos conocidos. |

### Fase 5: Testing + Validación (semanas 11-12)

**Entregable:** Sistema testeado, documentado, listo para frontend.

| Tarea | Criterio de aceptación |
|---|---|
| Tests de integración | Pipeline completo: ID contrato → JSON response. |
| Validación con contratos conocidos | Set de contratos con outcomes conocidos produce resultados coherentes. |
| Documentación API | OpenAPI docs completa en /docs. |
| README del proyecto | Instrucciones de setup, entrenamiento y despliegue. |

--
