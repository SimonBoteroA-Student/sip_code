# PRD: SIP — Sistema Inteligente de Predicción de Corrupción en Contratación Pública
## Backend — Project Requirements Document v2.0 (Production-Ready)

*Versión original: 1.0 (Febrero 2026) → Versión refinada: 2.0*
*Estado: ✅ Production-Ready*

---

# ══════════════════════════════════════════════════════
# SECCIÓN A: DIAGNÓSTICO Y ANÁLISIS DEL PRD v1.0
# ══════════════════════════════════════════════════════

## 🔍 DIAGNÓSTICO EJECUTIVO

El PRD v1.0 de SIP es, en términos generales, uno de los documentos de requerimientos más sólidos para un proyecto de ML aplicado que se puede ver en este dominio. Su base académica es explícita y rastreable, el modelo de datos está documentado con dimensiones reales, los features tienen justificación en la literatura, y la arquitectura de dos pipelines (offline/online) con código compartido es una decisión de diseño excelente. Un equipo de vibe coding puede comenzar a trabajar con este PRD y producir código coherente en la gran mayoría de los módulos.

Sin embargo, existen **cuatro problemas que bloquearían el despliegue a producción** si no se resuelven: (1) la versión de Python especificada no existe en producción, (2) el API no tiene ninguna especificación de autenticación ni rate limiting, exponiendo inteligencia sensible de corrupción sin control de acceso, (3) hay un riesgo no-trivial de **data leakage temporal** en las features del RCAC que podría inflar artificialmente las métricas de los modelos, y (4) el comportamiento del sistema ante fallos externos (SECOP API caída, RCAC corrupto) no está especificado, lo que producirá errores no manejados en producción.

Adicionalmente, hay un "fantasma" en el documento: **la Fuente 2 del RCAC no existe** — el documento salta de Fuente 1 a Fuente 3 sin explicación. Esto puede ser un error de numeración o una fuente genuinamente faltante, pero debe aclararse.

El sistema de inferencia online también tiene una brecha de implementación crítica: para features como `num_contratos_previos`, `num_sobrecostos_previos` o `valor_total_contratos_previos`, el pipeline online necesita recuperar el historial completo del proveedor desde SECOP en tiempo real. Esto no está especificado y podría convertir cada llamada al endpoint en decenas de requests secundarios con latencia impredecible.

---

## ⚠️ PROBLEMAS CRÍTICOS (Deben resolverse antes de comenzar a codear)

### CRÍTICO 1 — Python 3.14 no existe en producción
**Problema:** El PRD especifica Python 3.14. Al momento de este documento (Febrero 2026), Python 3.14 está en alpha/pre-release y no es apto para producción. La versión estable más reciente es Python 3.13.
**Impacto:** Librerías core (XGBoost 2.x, SHAP 0.43+, FastAPI) no tienen soporte garantizado en 3.14 alpha.
**Solución:** Usar Python 3.12 (LTS, soporte extendido hasta 2028) o Python 3.13.

---

### CRÍTICO 2 — API sin autenticación ni control de acceso
**Problema:** Los endpoints `POST /api/v1/analyze` y `POST /api/v1/analyze/batch` no tienen ninguna especificación de autenticación. Un sistema que expone inteligencia sobre corrupción en contratos públicos sin control de acceso es un riesgo de seguridad y reputacional.
**Impacto:** Cualquier actor con la URL puede consultar el nivel de riesgo de cualquier contrato, incluyendo actores que podrían usar la información para evadir el sistema.
**Solución:** Implementar API Key authentication mínimo (header `X-API-Key`). Especificado en detalle en la sección 11 del PRD refinado.

---

### CRÍTICO 3 — Riesgo de data leakage temporal en features RCAC
**Problema:** Al construir el RCAC con datos históricos y cruzarlo contra contratos del dataset de entrenamiento, existe riesgo de que sanciones **posteriores** a la fecha de firma del contrato sean usadas como features para predecir si ese contrato tuvo problemas. Ejemplo: un proveedor firmó contrato en 2019, fue sancionado en 2022; si el RCAC se construye con datos hasta 2024 y se usa para featurizar ese contrato de 2019, el modelo "ve el futuro".
**Impacto:** AUC inflado artificialmente. El modelo no funcionará en producción como esperado.
**Solución:** Al construir features RCAC para entrenamiento, filtrar el RCAC por `fecha_sancion < fecha_firma_contrato`. En producción (online), el RCAC usa solo sanciones hasta la fecha actual. Implementado en `rcac_lookup.py` con parámetro `as_of_date`.

---

### CRÍTICO 4 — Comportamiento ante fallos externos no especificado
**Problema:** El pipeline online depende de la API de Socrata (datos.gov.co). Si esta API está caída, lenta, o retorna datos malformados, el comportamiento de SIP no está definido.
**Impacto:** El servidor devolverá errores HTTP 500 no controlados, o peor, resultados silenciosamente incorrectos.
**Solución:** Definir circuit breaker, timeouts explícitos, y códigos de error HTTP específicos para cada fallo. Ver sección 10.4 del PRD refinado.

---

### CRÍTICO 5 — Fuente 2 del RCAC faltante en el documento
**Problema:** La sección 4.2 enumera Fuente 1, luego salta a Fuente 3. La Fuente 2 está ausente. El objetivo 2.2.1 menciona "6+ fuentes" pero solo se describen 6 con numeración incorrecta.
**Impacto:** El `rcac_builder.py` puede estar incompleto si hay una fuente genuinamente faltante.
**Solución:** [ASUNCIÓN: La Fuente 2 es `responsabilidades_fiscales_PACO.csv` mencionada en el Paso 1 del pipeline del RCAC (sección 5.3). Se ha incorporado en el PRD refinado como Fuente 2.]

---

### CRÍTICO 6 — Features de historial del proveedor en el pipeline online
**Problema:** Features como `num_contratos_previos`, `num_sobrecostos_previos`, `num_actividades_economicas`, `valor_total_contratos_previos` requieren el historial completo del proveedor. En el pipeline offline esto se puede calcular sobre el dataset batch, pero en el pipeline online (tiempo real por contrato), no hay especificación de cómo se obtiene este historial.
**Impacto:** El pipeline online no puede calcular estas features sin múltiples requests adicionales a SECOP, lo que puede aumentar la latencia de 1-2 segundos a 10-30 segundos por análisis.
**Solución:** Mantener un índice de historial de proveedores pre-computado (`provider_history_index.pkl`) generado en el pipeline offline, análogo al RCAC. Ver sección 5.5 del PRD refinado.

---

## 💡 MEJORAS IMPORTANTES (No bloqueantes pero necesarias para producción)

- **Sin especificación de CORS:** El frontend futuro necesita saber qué orígenes están permitidos. FastAPI necesita `CORSMiddleware` configurado.
- **Sin especificación de timeout:** ¿Cuánto puede tardar `/api/v1/analyze`? Sin SLA definido, la IA generará código sin timeouts, resultando en requests que cuelgan indefinidamente.
- **Sin especificación de variables de entorno:** El `settings.py` necesita una lista explícita de variables de entorno requeridas vs. opcionales para deployment.
- **Logging no es opcional:** `structlog` está listado como dependencia "opcional" pero en producción es obligatorio. Toda llamada a `/analyze` debe ser loggeable con contract_id, duración, ICR score, y si hubo error.
- **`dias_a_proxima_eleccion` sin fuente de datos:** Esta feature requiere una lista hardcodeada de fechas electorales colombianas. No está especificada dónde vive esta lista.
- **Fuente 6 (`organized_people_data.csv`) sin integrar:** Está marcada como "Estado: Insumo separado, sin integrar." Si no se integra, el RCAC es incompleto. Necesita un criterio de aceptación de V1 claro.
- **Sin especificación de `max_contracts` en batch:** El endpoint acepta hasta 1000 contratos pero no especifica timeout ni comportamiento ante errores parciales (¿falla todo o continúa?).
- **Sin especificación de hardware mínimo:** Cargar 4 modelos XGBoost + RCAC (potencialmente cientos de MB en memoria) tiene requerimientos mínimos de RAM.
- **Estrategia de manejo de `tipo_contrato` desconocido en IRIC online:** Si llega un contrato con un tipo no visto en el calibrado de umbrales, ¿usa el fallback `"otros"`? No está explicitado.

---

## 📊 SCORECARD DEL PRD ORIGINAL v1.0

| Dimensión | Puntuación | Comentario |
|---|---|---|
| Claridad y Especificidad | 8/10 | Excelente detalle en features y modelos. Gaps en manejo de errores y comportamiento edge cases. |
| Stack Tecnológico | 6/10 | Core bien definido. Python 3.14 inválido. Faltan vars de entorno, Docker, logging obligatorio. |
| Modelo de Datos | 9/10 | Sobresaliente. Fuentes reales con dimensiones, llaves de cruce, y esquemas de dataclass. |
| Seguridad y Producción | 3/10 | Crítico: sin autenticación, sin rate limiting, sin circuit breaker para dependencias externas. |
| Reqs. No-Funcionales | 4/10 | Sin SLA de latencia, sin RAM mínima, sin timeout specs, sin CORS. |
| Estructura para AI Dev | 8/10 | Milestones claros con criterios de aceptación. La Fase 5 podría tener más detalle. |
| UX/UI | 7/10 | Bien definido para ser un PRD de backend. Las guías para el frontend futuro son útiles. |
| **TOTAL** | **45/70** | **Intermedio-Avanzado → production-ready con correcciones críticas** |

---

---

# ══════════════════════════════════════════════════════
# SECCIÓN B: PRD REFINADO v2.0 — PRODUCTION-READY
# ══════════════════════════════════════════════════════

---

## Meta

| Campo | Valor |
|---|---|
| Proyecto | SIP (Sistema Inteligente de Predicción) |
| Versión | **2.0 (Production-Ready)** |
| Fecha | Febrero 2026 |
| Alcance de este documento | **Backend únicamente** |
| Lenguaje | **Python 3.12** *(corregido de 3.14: no existe en producción)* |
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
- **Índice compuesto:** promedio ponderado simple de las probabilidades de los 4 modelos + el IRIC. Pesos iniciales iguales (1/5 cada uno).
- **IRIC:** cumple doble rol: (a) estadística descriptiva al usuario, (b) feature de entrada para los modelos ML.
- **Autenticación:** API Key obligatoria para todos los endpoints de análisis.
- **Frontend:** se desarrollará en fase posterior. Este backend expone una API REST (FastAPI) que el frontend consumirá.

---

## 2. Objetivos

### 2.1 Objetivo General

Construir un backend que, dado un ID de contrato SECOP II, calcule un índice compuesto de riesgo de corrupción basado en múltiples modelos ML y un índice de reglas, exponiendo los resultados vía API REST autenticada.

### 2.2 Objetivos Específicos

1. Construir un **Registro Consolidado de Antecedentes de Corrupción (RCAC)** que unifique 7 fuentes de sanciones a nivel de persona (CC/NIT), incluyendo representantes legales, **con control temporal para prevenir data leakage**.
2. Construir un **Índice de Historial de Proveedores (IHP)** pre-computado para servir features de historial en el pipeline online sin requests adicionales a SECOP.
3. Calcular un **IRIC** (11 red flags binarias) calibrado por tipo de contrato a nivel nacional.
4. Entrenar **4 modelos XGBoost** de clasificación binaria para: sobrecostos (M1), retrasos (M2), aparición en Contraloría (M3), multas SECOP (M4).
5. Generar **SHAP values** por predicción para explicar cada resultado.
6. Combinar en un **Índice Compuesto de Riesgo (ICR)** con promedio ponderado configurable.
7. Exponer todo vía **API REST** (FastAPI) con autenticación por API Key, rate limiting, y manejo de errores robusto.

---

## 3. Arquitectura

### 3.1 Dos Pipelines

```
PIPELINE OFFLINE
════════════════════════════════════════════════════════════════
  Descarga masiva      Feature         Entrenamiento
  SECOP II API    ───► Engineering ───► XGBoost × 4
  + Fuentes RCAC       + RCAC build     modelos
                       + IHP build      (con temporal cut)
                       + IRIC calibrar
                              │
                              ▼
                       Artifacts:
                         modelos/ (M1-M4.pkl)
                         rcac.pkl (indexado por doc)
                         provider_history_index.pkl  ← NUEVO
                         iric_thresholds.json
                         training_metadata.json


PIPELINE ONLINE (tiempo real, por contrato)
════════════════════════════════════════════════════════════════
  POST /api/v1/analyze    Auth Check      Consulta SECOP
  { contract_id }    ───► (API Key)  ───► II API (contrato
                                          + proceso + proveedor)
                                                  │
                                                  ▼
                                          IHP Lookup + RCAC
                                          Lookup (as_of_date=
                                          fecha_firma)
                                                  │
                                                  ▼
                                          Feature Engineering
                                          (mismo código offline)
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

**Principio clave:** el código de feature engineering, cálculo de IRIC e inferencia es **exactamente el mismo** en ambos pipelines.

### 3.2 Estructura del Proyecto

```
sip/
├── config/
│   ├── settings.py                # Constantes, API URLs, paths, feature lists + carga de env vars
│   ├── iric_thresholds.json       # Umbrales del IRIC calibrados (generado offline)
│   └── model_weights.json         # Pesos del ICR: {"M1": 0.20, "M2": 0.20, ...}
│
├── data/
│   ├── secop_client.py            # Cliente async para Socrata API (datos.gov.co)
│   ├── rcac_builder.py            # Construye el RCAC desde las 7 fuentes (con temporal cut)
│   ├── rcac_lookup.py             # Dict en memoria para consulta O(1) por (doc_type, doc_num, as_of_date)
│   ├── provider_history_builder.py  # NUEVO: construye el IHP desde datos batch
│   ├── provider_history_lookup.py   # NUEVO: Dict en memoria para historial de proveedor
│   └── batch_downloader.py        # Descarga masiva para entrenamiento
│
├── features/
│   ├── contract_features.py       # Features del contrato
│   ├── provider_features.py       # Features del proveedor (antigüedad, historial, RCAC, IHP)
│   ├── process_features.py        # Features del proceso (ofertas, publicidad, decisión)
│   ├── temporal_features.py       # Features temporales (duraciones, firma-a-inicio, mes)
│   ├── election_dates.py          # NUEVO: lista de fechas electorales colombianas hardcodeadas
│   ├── iric.py                    # Cálculo de los 11 componentes del IRIC
│   └── pipeline.py                # Orquestador: raw data → feature vector completo
│
├── models/
│   ├── trainer.py                 # Entrenamiento: XGBoost + RandomSearch + StratifiedKFold
│   ├── predictor.py               # Inferencia: carga .pkl → predict_proba + SHAP
│   ├── composite_index.py         # ICR = Σ(wi × Pi)
│   ├── class_balance.py           # Estrategias de desbalance
│   └── evaluation.py              # Métricas: AUC, MAP@k, NDCG@k, Brier, Precision, Recall
│
├── api/
│   ├── app.py                     # FastAPI application + middleware (CORS, logging, auth)
│   ├── auth.py                    # NUEVO: API Key validation
│   ├── routes.py                  # POST /analyze, GET /health, POST /analyze/batch
│   ├── schemas.py                 # Pydantic models (request/response)
│   └── error_handlers.py          # NUEVO: handlers para errores específicos (SECOPError, etc.)
│
├── training/
│   ├── train_pipeline.py          # Pipeline completo: download → features → train → evaluate
│   └── calibrate_iric.py          # Calcula percentiles para iric_thresholds.json
│
├── artifacts/                     # Generados por el pipeline offline (NO versionar en git)
│   ├── models/                    # M1.pkl, M2.pkl, M3.pkl, M4.pkl
│   ├── rcac.pkl                   # RCAC serializado
│   ├── provider_history_index.pkl  # NUEVO: IHP serializado
│   ├── iric_thresholds.json
│   └── training_metadata.json
│
├── tests/
│   ├── test_rcac.py
│   ├── test_provider_history.py   # NUEVO
│   ├── test_features.py
│   ├── test_iric.py
│   ├── test_models.py
│   └── test_api.py
│
├── .env.example                   # NUEVO: plantilla de variables de entorno
├── Dockerfile                     # NUEVO
├── docker-compose.yml             # NUEVO
└── requirements.txt               # Dependencias con versiones pinneadas
```

---

## 4. Variables de Entorno y Configuración

### 4.1 Variables Requeridas (el sistema no arranca sin estas)

```bash
# .env.example

# Autenticación
API_KEY=<string-secreto-minimo-32-chars>      # Llave API para autenticar requests

# SECOP API
SECOP_APP_TOKEN=<token-socrata>               # Token de la Socrata API (datos.gov.co)
                                               # Registro gratuito en data.cityofchicago.org

# Paths de artifacts
ARTIFACTS_DIR=/app/artifacts                  # Dir con modelos .pkl, rcac.pkl, etc.
```

### 4.2 Variables Opcionales (tienen defaults razonables)

```bash
# Servidor
HOST=0.0.0.0
PORT=8000
WORKERS=1                                     # Uvicorn workers (1 para dev, 2-4 para prod)

# Performance
SECOP_REQUEST_TIMEOUT_SEC=10                  # Timeout para llamadas a SECOP API
SECOP_MAX_RETRIES=3                           # Reintentos ante fallo de SECOP
ONLINE_PIPELINE_TIMEOUT_SEC=30               # Timeout total del pipeline online por request
BATCH_MAX_CONTRACTS=1000                      # Límite de contratos en el endpoint batch

# Rate limiting
RATE_LIMIT_PER_MINUTE=60                     # Requests por API Key por minuto
RATE_LIMIT_BATCH_PER_HOUR=10                 # Requests batch por API Key por hora

# Logging
LOG_LEVEL=INFO                                # DEBUG | INFO | WARNING | ERROR
LOG_FORMAT=json                               # json | text

# CORS (orígenes permitidos para el frontend)
CORS_ORIGINS=http://localhost:3000,https://sip.dominio.com
```

### 4.3 `settings.py` — Carga de Configuración

```python
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # Autenticación
    api_key: str

    # SECOP
    secop_app_token: str
    secop_base_url: str = "https://www.datos.gov.co/resource"
    secop_request_timeout_sec: int = 10
    secop_max_retries: int = 3

    # Artifacts
    artifacts_dir: Path = Path("/app/artifacts")

    # Performance
    online_pipeline_timeout_sec: int = 30
    batch_max_contracts: int = 1000

    # Rate limiting
    rate_limit_per_minute: int = 60
    rate_limit_batch_per_hour: int = 10

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
```

---

## 5. Fuentes de Datos

### 5.1 Datos SECOP II (variables explicativas)

#### 5.1.1 – 5.1.7 [Igual que v1.0: Contratos, Procesos, Ofertas, Proponentes, Proveedores, Ejecución, Adiciones]

*(Las definiciones de datasets, IDs, dimensiones y columnas son idénticas a la sección 4.1 del PRD v1.0. Se mantienen íntegras.)*

### 5.2 Datos para el RCAC

#### Fuente 1: Boletines de la Contraloría
*(Igual que v1.0)*

#### Fuente 2: Responsabilidades Fiscales PACO ← [AÑADIDA — faltaba en v1.0]
- **Archivo:** `PACO/responsabilidades_fiscales_PACO.csv`
- **Descripción:** Registro de responsabilidades fiscales del sistema PACO de la Contraloría.
- **Nota:** La sección 5.3 del PRD v1.0 menciona explícitamente `responsabilidades_fiscales_PACO.csv` en el Paso 1 del pipeline de construcción del RCAC, pero no aparecía como Fuente numerada.
- **Identificador:** Campo combinado "Tipo y Num Documento" (parsear: primeros caracteres = tipo, resto = número).
- **[ASUNCIÓN: Esta es la Fuente 2 faltante. Validar con el equipo antes de implementar.]**

#### Fuente 3: Sanciones SIRI (Procuraduría)
*(Igual que v1.0)*

#### Fuente 4: Multas SECOP (PACO)
*(Igual que v1.0)*

#### Fuente 5: Colusiones SIC
*(Igual que v1.0)*

#### Fuente 6: Datos de Personas (Monitor Ciudadano)
- **Archivo:** `organized_people_data.csv`
- **Estado V1:** Será integrada si el análisis de columnas de identificación resulta exitoso antes del inicio de la Fase 1.
- **Criterio de aceptación V1:** Si las columnas `tipo_documento` y `numero_documento` (o equivalentes) son identificables, se integra en `rcac_builder.py`. Si no, se deja como flag `tiene_registro_monitor_ciudadano = False` para todos los registros, documentado en `training_metadata.json`.
- **[ASUNCIÓN: Se hará un mejor esfuerzo de integración en la Fase 1. Si no es posible, se documenta y no bloquea las fases siguientes.]**

---

## 6. Registro Consolidado de Antecedentes de Corrupción (RCAC)

### 6.1 Propósito

*(Igual que v1.0)*

### 6.2 Schema del Registro (sin cambios respecto a v1.0)

```python
@dataclass
class RCACRecord:
    tipo_documento: str             # "CC" | "NIT" | "CE" | "PASAPORTE" | "OTRO"
    numero_documento: str           # Normalizado: solo dígitos, sin puntos/guiones
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
    cuantia_total_dano_fiscal: float

    # Temporalidad — CRÍTICO para anti-leakage
    fecha_primera_sancion: Optional[date]
    fecha_ultima_sancion: Optional[date]
    sanciones_con_fecha: List[dict]  # NUEVO: lista de {fuente, fecha_sancion} para consulta temporal

    # Meta
    fuentes: List[str]
    num_fuentes_distintas: int
```

### 6.3 Prevención de Data Leakage Temporal — NUEVO

**Regla crítica:** Al usar el RCAC como feature para un contrato con `fecha_firma = T`, solo deben considerarse sanciones con `fecha_sancion < T`.

**Implementación en `rcac_lookup.py`:**

```python
def lookup(self,
           tipo_doc: str,
           num_doc: str,
           as_of_date: date) -> RCACFeatures:
    """
    Retorna features del RCAC filtradas temporalmente.
    Solo incluye sanciones con fecha_sancion < as_of_date.

    En entrenamiento: as_of_date = fecha_firma del contrato
    En producción (online): as_of_date = fecha actual (datetime.today())
    """
    record = self._index.get((tipo_doc, num_doc))
    if record is None:
        return RCACFeatures.empty()

    # Filtrar sanciones al corte temporal
    sanciones_validas = [
        s for s in record.sanciones_con_fecha
        if s["fecha_sancion"] is None or s["fecha_sancion"] < as_of_date
    ]
    # ... construir features solo con sanciones_validas
```

**Nota:** Sanciones sin fecha (`fecha_sancion = None`) se incluyen siempre (conservador: better safe than sorry). Documentar en `training_metadata.json` el % de sanciones sin fecha por fuente.

### 6.4 Pipeline de Construcción (`rcac_builder.py`)

*(Igual que v1.0, con adición de campo `sanciones_con_fecha` en el schema)*

### 6.5 Features Derivadas del RCAC

*(Igual que v1.0)*

---

## 7. Índice de Historial de Proveedores (IHP) — NUEVO

### 7.1 Propósito

Índice pre-computado que almacena el historial agregado de cada proveedor, calculado sobre los datos batch del pipeline offline. Permite al pipeline online recuperar estas features en O(1) sin hacer requests adicionales a SECOP.

### 7.2 Schema

```python
@dataclass
class ProviderHistoryRecord:
    tipo_documento: str
    numero_documento: str
    nombre: str
    fecha_registro_secop: Optional[date]

    # Historial contractual (total histórico)
    num_contratos_total: int
    valor_total_contratos_cop: float
    num_actividades_economicas_distintas: int  # UNSPSC a 2 dígitos únicos

    # Historial por corte temporal — CRÍTICO para anti-leakage
    # Estructura: lista de {fecha_firma, valor, tuvo_sobrecosto, tuvo_retraso}
    contratos_historico: List[dict]
```

### 7.3 Consulta con Control Temporal

```python
def get_provider_features(self,
                           tipo_doc: str,
                           num_doc: str,
                           as_of_date: date) -> ProviderFeatures:
    """
    Retorna features del historial del proveedor anteriores a as_of_date.
    Solo contratos con fecha_firma < as_of_date son considerados.
    """
    record = self._index.get((tipo_doc, num_doc))
    if record is None:
        return ProviderFeatures.new_provider()

    contratos_previos = [
        c for c in record.contratos_historico
        if c["fecha_firma"] < as_of_date
    ]

    return ProviderFeatures(
        num_contratos_previos=len(contratos_previos),
        valor_total_contratos_previos=sum(c["valor"] for c in contratos_previos),
        num_sobrecostos_previos=sum(c["tuvo_sobrecosto"] for c in contratos_previos),
        num_retrasos_previos=sum(c["tuvo_retraso"] for c in contratos_previos),
        num_actividades_economicas=record.num_actividades_economicas_distintas,
        dias_proveedor_registrado=(as_of_date - record.fecha_registro_secop).days
            if record.fecha_registro_secop else None,
    )
```

### 7.4 Tamaño Estimado en Memoria

Con ~1.5M proveedores registrados y estructura liviana (~200 bytes/record): **~300 MB**. Junto con RCAC (~50MB) y 4 modelos XGBoost (~100MB total), el servidor requiere mínimo **1 GB de RAM disponible** en producción.

---

## 8. IRIC — Índice de Riesgo de Irregularidades Contractuales

*(Secciones 8.1 - 8.5 idénticas a secciones 6.1 - 6.5 del PRD v1.0)*

### 8.6 Manejo de Tipo de Contrato Desconocido en IRIC Online — NUEVO

Si el contrato analizado en el pipeline online tiene un `tipo_contrato` que no existe en `iric_thresholds.json`, se usa el fallback `"otros"`:

```python
def get_thresholds(self, tipo_contrato: str) -> dict:
    normalized = self._normalize_tipo(tipo_contrato)
    return self.thresholds.get(normalized, self.thresholds["otros"])
```

Este caso se loggea con nivel `WARNING` indicando el tipo de contrato desconocido.

### 8.7 Fechas Electorales (`election_dates.py`) — NUEVO

La feature `dias_a_proxima_eleccion` requiere una lista de fechas electorales. Se mantiene como constante en `features/election_dates.py`:

```python
# Elecciones presidenciales Colombia
PRESIDENTIAL_ELECTIONS = [
    date(2014, 5, 25),  # Primera vuelta
    date(2014, 6, 15),  # Segunda vuelta
    date(2018, 5, 27),
    date(2018, 6, 17),
    date(2022, 5, 29),
    date(2022, 6, 19),
    date(2026, 5, 31),  # Estimada — actualizar cuando se confirme
]

def dias_a_proxima_eleccion(fecha_firma: date) -> int:
    """Días hasta la próxima elección presidencial desde fecha_firma."""
    futuras = [e for e in PRESIDENTIAL_ELECTIONS if e >= fecha_firma]
    if not futuras:
        return 9999  # Más allá del horizonte conocido
    return (min(futuras) - fecha_firma).days
```

---

## 9. Modelos Predictivos

*(Secciones 9.1 - 9.6 idénticas a secciones 7.1 - 7.6 del PRD v1.0)*

---

## 10. Índice Compuesto de Riesgo (ICR)

*(Secciones 10.1 - 10.3 idénticas a secciones 8.1 - 8.3 del PRD v1.0)*

---

## 11. Seguridad y Autenticación — NUEVO

### 11.1 Autenticación por API Key

Todos los endpoints de análisis requieren autenticación. El endpoint `/health` es público.

**Mecanismo:** Header HTTP `X-API-Key`.

```python
# api/auth.py
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from sip.config.settings import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida o ausente"
        )
    return api_key
```

**Uso en routes:**
```python
@router.post("/analyze")
async def analyze(
    request: AnalyzeRequest,
    _: str = Depends(verify_api_key)  # Auth requerida
):
    ...
```

**Response ante auth fallida:**
```json
HTTP/1.1 401 Unauthorized
{
  "error": "UNAUTHORIZED",
  "message": "API Key inválida o ausente",
  "hint": "Incluir header: X-API-Key: <tu-api-key>"
}
```

### 11.2 Rate Limiting

Implementado en middleware usando `slowapi` (wrapper de `limits` para FastAPI):

```python
# api/app.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

```python
# En routes:
@router.post("/analyze")
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def analyze(request: Request, ...):
    ...

@router.post("/analyze/batch")
@limiter.limit(f"{settings.rate_limit_batch_per_hour}/hour")
async def analyze_batch(request: Request, ...):
    ...
```

**Response ante rate limit:**
```
HTTP/1.1 429 Too Many Requests
Retry-After: 60
```

### 11.3 CORS

```python
# api/app.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)
```

---

## 12. Manejo de Errores y Resiliencia — NUEVO

### 12.1 Catálogo de Errores del API

| Código HTTP | Error Code | Causa | Acción del cliente |
|---|---|---|---|
| 400 | `INVALID_CONTRACT_ID` | ID de contrato con formato inválido | Verificar formato `CO1.PCCNTR.XXXXX` |
| 401 | `UNAUTHORIZED` | API Key ausente o inválida | Incluir header `X-API-Key` |
| 404 | `CONTRACT_NOT_FOUND` | El contract_id no existe en SECOP II | Verificar que el ID exista en datos.gov.co |
| 422 | `VALIDATION_ERROR` | Request body malformado | Ver campo `detail` en la respuesta |
| 429 | `RATE_LIMIT_EXCEEDED` | Demasiadas requests | Esperar y reintentar con backoff exponencial |
| 503 | `SECOP_API_UNAVAILABLE` | Socrata API no responde | Reintentar en 30-60 segundos |
| 504 | `ANALYSIS_TIMEOUT` | El análisis superó `ONLINE_PIPELINE_TIMEOUT_SEC` | Reintentar; si persiste, reportar |
| 500 | `INTERNAL_ERROR` | Error inesperado del sistema | Reportar con el `request_id` incluido en el response |

### 12.2 Estructura de Respuesta de Error

```json
{
  "error": "CONTRACT_NOT_FOUND",
  "message": "El contrato 'CO1.PCCNTR.99999' no fue encontrado en SECOP II",
  "request_id": "req_a1b2c3d4",
  "timestamp": "2026-02-26T14:30:00Z"
}
```

### 12.3 Circuit Breaker para SECOP API

```python
# data/secop_client.py
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class SECOPClient:
    def __init__(self, timeout: int, max_retries: int):
        self.client = httpx.AsyncClient(timeout=timeout)
        self.max_retries = max_retries

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def get_contract(self, contract_id: str) -> dict:
        try:
            response = await self.client.get(
                f"{settings.secop_base_url}/jbjy-vk9h.json",
                params={"id_contrato": contract_id, "$$app_token": settings.secop_app_token}
            )
            response.raise_for_status()
            data = response.json()
            if not data:
                raise ContractNotFoundError(contract_id)
            return data[0]
        except httpx.TimeoutException:
            raise SECOPAPIUnavailableError("Timeout en SECOP API")
        except httpx.HTTPStatusError as e:
            raise SECOPAPIUnavailableError(f"SECOP API error: {e.response.status_code}")
```

### 12.4 Timeout del Pipeline Online

```python
# api/routes.py
import asyncio

@router.post("/analyze")
async def analyze(request: AnalyzeRequest, _: str = Depends(verify_api_key)):
    try:
        result = await asyncio.wait_for(
            run_online_pipeline(request.contract_id),
            timeout=settings.online_pipeline_timeout_sec
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(504, detail={"error": "ANALYSIS_TIMEOUT", ...})
```

### 12.5 Comportamiento del Endpoint Batch ante Errores Parciales

Si el análisis de uno o más contratos falla en el endpoint batch, el sistema continúa con los demás. La respuesta incluye los resultados exitosos y los errores separados:

```json
{
  "results": [ /* contratos analizados exitosamente */ ],
  "errors": [
    {
      "contract_id": "CO1.PCCNTR.99999",
      "error": "CONTRACT_NOT_FOUND",
      "message": "No encontrado en SECOP II"
    }
  ],
  "summary": {
    "total_requested": 10,
    "successful": 9,
    "failed": 1
  }
}
```

---

## 13. Logging y Observabilidad — NUEVO

`structlog` es **dependencia obligatoria**, no opcional.

### 13.1 Configuración

```python
# config/logging_config.py
import structlog

def configure_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
            if settings.log_format == "json"
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
```

### 13.2 Campos Obligatorios en Cada Log de Análisis

Cada llamada a `/analyze` debe producir exactamente un log entry con los siguientes campos:

```json
{
  "event": "contract_analyzed",
  "contract_id": "CO1.PCCNTR.12345",
  "request_id": "req_a1b2c3d4",
  "duration_ms": 1234,
  "icr_score": 0.72,
  "icr_category": "Alto",
  "secop_latency_ms": 450,
  "pipeline_step_durations_ms": {
    "secop_fetch": 450,
    "rcac_lookup": 2,
    "ihp_lookup": 1,
    "feature_engineering": 85,
    "iric_calculation": 12,
    "model_inference": 95,
    "shap_calculation": 580
  },
  "error": null,
  "timestamp": "2026-02-26T14:30:00Z"
}
```

---

## 14. API REST — Contrato de Interfaz con Frontend

### 14.1 Framework

FastAPI. Documentación OpenAPI auto-generada en `/docs` y `/redoc`. Esta documentación sirve como especificación canónica para el equipo de frontend.

### 14.2 Especificación de Latencia (SLA)

| Operación | Latencia Target (p50) | Latencia Máxima (p99) |
|---|---|---|
| `GET /health` | < 50 ms | < 200 ms |
| `POST /analyze` (SECOP disponible) | < 3 s | < 10 s |
| `POST /analyze` (SECOP lento) | < 8 s | < 30 s (timeout) |
| `POST /analyze/batch` (100 contratos) | < 60 s | < 120 s |

*Nota: La mayor latencia proviene de SHAP calculation (~500ms) y de la consulta a SECOP API (~500ms). Esto no es optimizable en V1 sin cachear resultados.*

### 14.3 Endpoints

#### `POST /api/v1/analyze` — Análisis de Contrato Individual

**Headers requeridos:**
```
X-API-Key: <api-key>
Content-Type: application/json
```

**Request:**
```json
{
  "contract_id": "CO1.PCCNTR.12345"
}
```

**Validación de `contract_id`:**
- No nulo, no vacío.
- Longitud entre 5 y 50 caracteres.
- Solo caracteres alfanuméricos, puntos, guiones y barras.

**Response exitoso (200):**
*(Idéntico al definido en sección 10.2 del PRD v1.0, que se mantiene íntegro)*

---

#### `GET /api/v1/health` — Estado del Sistema (público, sin auth)

```json
{
  "status": "healthy",
  "model_version": "2025-Q4",
  "last_training_date": "2025-12-15",
  "rcac_last_updated": "2025-12-01",
  "rcac_total_records": 58432,
  "provider_history_total_records": 1524893,
  "secop_api_status": "connected",
  "models_loaded": ["M1", "M2", "M3", "M4"]
}
```

**Estado "degraded"** (modelos cargados pero SECOP no responde):
```json
{
  "status": "degraded",
  "issues": ["SECOP API no responde. Los análisis están temporalmente no disponibles."],
  ...
}
```

---

#### `POST /api/v1/analyze/batch` — Análisis Batch

**Headers:** mismos que `/analyze`.

**Request:**
```json
{
  "contract_ids": ["id1", "id2", "..."],
  "max_contracts": 1000
}
```

**Validaciones:**
- `contract_ids`: lista no vacía, máximo `BATCH_MAX_CONTRACTS` elementos.
- IDs duplicados son procesados una sola vez (deduplicar en el servidor).

**Response:** Ver sección 12.5 para estructura con errores parciales.

---

## 15. Tech Stack

### Dependencias Core

| Componente | Paquete | Versión mínima | Propósito |
|---|---|---|---|
| Runtime | `python` | **3.12** *(corregido de 3.14)* | Runtime |
| ML | `xgboost` | 2.0+ | Algoritmo principal × 4 modelos |
| Explicabilidad | `shap` | 0.43+ | TreeSHAP para SHAP values |
| Data | `pandas` | 2.0+ | Procesamiento de datos |
| Data | `numpy` | 1.24+ | Operaciones numéricas |
| ML Utils | `scikit-learn` | 1.3+ | StratifiedKFold, RandomizedSearchCV, métricas |
| API | `fastapi` | 0.100+ | Servidor REST |
| API | `uvicorn` | 0.23+ | ASGI server |
| Serialización | `pydantic` | 2.0+ | Schemas request/response |
| Config | `pydantic-settings` | 2.0+ | **NUEVO:** Gestión de variables de entorno |
| HTTP | `httpx` | 0.25+ | Cliente async para SECOP API |
| Serialización ML | `joblib` | 1.3+ | Guardar/cargar modelos .pkl |
| Logging | `structlog` | 23.0+ | **Obligatorio** (movido de opcional) |
| Rate Limiting | `slowapi` | 0.1.9+ | **NUEVO:** Rate limiting por IP/API Key |
| Resiliencia | `tenacity` | 8.0+ | **NUEVO:** Retry logic para SECOP API |
| Testing | `pytest` | 7.0+ | Tests unitarios e integración |
| Testing | `pytest-asyncio` | 0.21+ | **NUEVO:** Tests de endpoints async |
| Testing | `httpx` | 0.25+ | Cliente async para tests de API |

### Dependencias Opcionales (pipeline offline)

| Componente | Paquete | Propósito |
|---|---|---|
| Almacenamiento | `pyarrow` | Archivos Parquet para datos batch |
| Scheduling | `celery` o cron job | Reentrenamiento trimestral |

### RCAC e IHP en Producción

- **V1 (inicial):** Dicts Python en memoria cargados desde `.pkl` al inicio del servidor.
- **V2 (si escala):** Redis para lookup distribuido. Misma interfaz de `rcac_lookup.py` y `provider_history_lookup.py`.

### Requerimientos de Hardware Mínimos (Producción)

| Recurso | Mínimo | Recomendado |
|---|---|---|
| RAM | 2 GB | 4 GB |
| CPU | 2 cores | 4 cores |
| Disco | 5 GB | 10 GB (para artifacts + logs) |

---

## 16. Deployment

### 16.1 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sip/ ./sip/
COPY config/ ./config/

# Los artifacts se montan como volumen, no se incluyen en la imagen
VOLUME ["/app/artifacts"]

ENV PYTHONPATH=/app
ENV PORT=8000

EXPOSE 8000

CMD ["uvicorn", "sip.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 16.2 docker-compose.yml (Desarrollo)

```yaml
version: "3.9"
services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./artifacts:/app/artifacts
      - ./sip:/app/sip  # hot reload en desarrollo
    env_file:
      - .env
    command: uvicorn sip.api.app:app --host 0.0.0.0 --port 8000 --reload
```

### 16.3 Startup Sequence

Al iniciar el servidor, en `api/app.py`:

```python
@app.on_event("startup")
async def startup():
    # 1. Cargar modelos
    predictor.load_models(settings.artifacts_dir / "models")

    # 2. Cargar RCAC en memoria
    rcac_store.load(settings.artifacts_dir / "rcac.pkl")

    # 3. Cargar IHP en memoria
    ihp_store.load(settings.artifacts_dir / "provider_history_index.pkl")

    # 4. Cargar thresholds IRIC
    iric_calculator.load_thresholds(settings.artifacts_dir / "iric_thresholds.json")

    # 5. Verificar conectividad SECOP (no-blocking: solo loggea si falla)
    await secop_client.health_check()

    logger.info("SIP backend ready", models_loaded=["M1", "M2", "M3", "M4"])
```

Si cualquiera de los pasos 1-4 falla, el servidor **no debe arrancar** (fail fast). El paso 5 no es bloqueante.

---

## 17. Estrategia de Reentrenamiento

*(Igual que sección 9 del PRD v1.0, sin cambios)*

---

## 18. Roadmap de Implementación

### Fase 1: Infraestructura de Datos (semanas 1-3)

**Entregable:** RCAC + IHP construidos y validados. Datos SECOP descargados.

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Variables de entorno + settings | `settings.py`, `.env.example` | `settings.api_key` y `settings.secop_app_token` se cargan desde .env sin errores. |
| Cliente SECOP II API (Socrata) | `secop_client.py` | Puede descargar las 7 tablas SECOP vía API. Maneja paginación, rate limits, y timeouts. Retry automático con tenacity. |
| Descarga masiva batch | `batch_downloader.py` | Descarga completa en Parquet. |
| RCAC builder | `rcac_builder.py` | Consolida 7 fuentes (incluyendo Fuente 2). Cada RCACRecord tiene `sanciones_con_fecha`. Genera `rcac.pkl`. |
| RCAC lookup temporal | `rcac_lookup.py` | Consulta con `as_of_date` retorna solo sanciones anteriores a esa fecha. |
| IHP builder | `provider_history_builder.py` | Genera `provider_history_index.pkl` con historial temporal de cada proveedor. |
| IHP lookup temporal | `provider_history_lookup.py` | `get_provider_features(tipo_doc, num_doc, as_of_date)` retorna features históricas correctas. |
| Tests | `test_rcac.py`, `test_provider_history.py` | Test específico de temporal cut: proveedor sancionado en T+1 no aparece en lookup con as_of_date=T. |

### Fase 2: Feature Engineering + IRIC (semanas 4-5)

*(Igual que v1.0, con adición de `election_dates.py` y test del fallback IRIC para tipo_contrato desconocido)*

### Fase 3: Entrenamiento de Modelos (semanas 6-8)

*(Igual que v1.0)*

### Fase 4: Índice Compuesto + API (semanas 9-10)

**Entregable:** API funcional end-to-end con seguridad y manejo de errores.

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Índice compuesto | `composite_index.py` | ICR = Σ(wi × Pi). Categorización por rango. |
| Autenticación | `auth.py` | Request sin API Key → 401. Request con API Key inválida → 401. Request válida → 200. |
| Rate limiting | Middleware | Más de N requests/minuto → 429 con header Retry-After. |
| CORS | Middleware | Solo orígenes en `CORS_ORIGINS` son permitidos. |
| Manejo de errores | `error_handlers.py` | SECOP caído → 503 con error code `SECOP_API_UNAVAILABLE`. Contrato no encontrado → 404. Timeout → 504. |
| Timeout pipeline online | `routes.py` | Request que supere `ONLINE_PIPELINE_TIMEOUT_SEC` retorna 504. |
| Batch con errores parciales | `routes.py` | Si 1 de 10 contratos falla, los 9 restantes se devuelven exitosamente. |
| Logging estructurado | `logging_config.py` | Cada análisis produce un log JSON con todos los campos definidos en sección 13.2. |
| API REST completa | `app.py`, `routes.py`, `schemas.py` | POST /analyze, GET /health, POST /analyze/batch todos funcionales. |
| Tests API | `test_api.py` | Tests de auth, rate limit, error codes, y análisis end-to-end. |

### Fase 5: Testing + Validación (semanas 11-12)

| Tarea | Criterio de aceptación |
|---|---|
| Tests de integración | Pipeline completo: ID contrato → JSON response en < SLA definido. |
| Test de temporal leakage | Validar que features RCAC e IHP en entrenamiento usan correctamente `as_of_date`. |
| Validación con contratos conocidos | Set de contratos con outcomes conocidos produce resultados coherentes. |
| Test de resiliencia | Simular SECOP API caída → sistema retorna 503 en lugar de 500 genérico. |
| Documentación API | OpenAPI docs completa en /docs. |
| README del proyecto | Instrucciones de setup, entrenamiento, variables de entorno y despliegue con Docker. |

---

## 19. Preguntas Abiertas y Decisiones Pendientes

| # | Pregunta | Impacto | Deadline |
|---|---|---|---|
| 1 | ¿La Fuente 2 del RCAC es efectivamente `responsabilidades_fiscales_PACO.csv`? | Completitud del RCAC | Antes de Fase 1 |
| 2 | ¿Se logra integrar `organized_people_data.csv` (Fuente 6)? | Features de monitor ciudadano | Semana 1-2 |
| 3 | ¿Cuál es la fecha de la elección presidencial 2026? (para `election_dates.py`) | Feature M3 | Antes de Fase 2 |
| 4 | ¿El API Key será uno compartido o por-usuario? | Arquitectura de auth | Antes de Fase 4 |
| 5 | ¿Se necesita cachear resultados de `/analyze` por contract_id? | Latencia y costo SECOP | Fase 4 (si la latencia es inaceptable) |
| 6 | ¿Cuál es el origen del CORS para el frontend? | Configuración de CORS | Antes de go-live |
| 7 | Calibración de pesos del ICR: ¿permanecen iguales (1/5) para V1? | Calidad del ICR | Después de entrenamiento de modelos |

---

## 20. Fuera de Scope (V1)

- Frontend / interfaz de usuario
- Autenticación multi-usuario (roles, usuarios individuales)
- Cache de resultados de análisis
- Almacenamiento de histórico de análisis realizados
- Calibración empírica de pesos del ICR (pesos iguales en V1)
- Modelo específico para colusiones SIC (solo 103 registros — insuficiente)
- Dashboard de métricas / monitoreo de drift del modelo
- Integración con sistemas externos distintos a SECOP y las 7 fuentes RCAC
