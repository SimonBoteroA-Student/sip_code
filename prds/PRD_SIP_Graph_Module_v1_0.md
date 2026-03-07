# PRD: SIP-Graph — Módulo de Detección de Redes de Corrupción Basado en Grafos
## Project Requirements Document v1.0
## Sistema Independiente — No conectado al pipeline XGBoost de SIP

*Fecha: Marzo 2026*
*Estado: MVP-Ready*
*Relación con SIP Backend v2.0: Sistema independiente y paralelo. No comparten pipeline, modelos ni índices.*

---

# ══════════════════════════════════════════════════════
# SECCIÓN A: CONTEXTO, JUSTIFICACIÓN Y DECISIONES DE DISEÑO
# ══════════════════════════════════════════════════════

## 1. Resumen Ejecutivo

SIP-Graph es un sistema independiente de detección de redes de corrupción en contratación pública colombiana, basado en Graph Neural Networks (GNNs). A diferencia del módulo XGBoost de SIP (que analiza contratos individuales), SIP-Graph modela las **relaciones entre actores** — proveedores, representantes legales, entidades estatales, financiadores de campañas — como un grafo heterogéneo y detecta patrones estructurales asociados a corrupción organizada.

**Pregunta que responde SIP (XGBoost):** "¿Qué tan riesgoso es este contrato individual?"
**Pregunta que responde SIP-Graph:** "¿Qué tan sospechosa es esta red de actores?"

El sistema opera en dos etapas: (1) un Graph Autoencoder basado en GraphSAGE que genera embeddings de nodos y detecta anomalías estructurales de forma no supervisada, y (2) un módulo de detección de comunidades que identifica clusters de actores y los clasifica como redes potencialmente corruptas.

**Decisiones de diseño fundamentales:**

- **Unidad de análisis:** actores (proveedores, personas, entidades) y sus relaciones, NO contratos individuales.
- **Independencia total de SIP XGBoost:** no comparten pipeline, features, modelos ni índice compuesto. Son sistemas paralelos.
- **Enfoque dual:** detección de anomalías no supervisada (Etapa 1) + clasificación de subgrafos con weak labels (Etapa 2).
- **Algoritmo base (MVP):** GraphSAGE como encoder dentro de un Graph Autoencoder.
- **Algoritmo evolución (Fase 2):** R-GCN o HAN para manejar heterogeneidad explícita de aristas.
- **Grafo heterogéneo:** 5 tipos de nodos, 5 tipos de aristas con semánticas distintas.
- **Control temporal:** todas las aristas con timestamp respetan corte temporal para evitar data leakage.
- **Hardware target:** RTX 2060 (6GB VRAM), 2× CPU Intel 3GHz, 90GB RAM DDR3.

---

## 2. Justificación Académica y Estado del Arte

### 2.1 Limitaciones del enfoque tabular actual

El pipeline XGBoost de SIP trata cada contrato como una observación independiente, enriquecida con features del proveedor (RCAC, IHP) y del proceso. Este enfoque no captura:

- **Redes de co-licitación:** proveedores que se presentan sistemáticamente juntos a licitaciones, rotando quién gana.
- **Empresas fachada con representantes legales compartidos:** una persona controla múltiples empresas que aparentan competir entre sí.
- **Ciclos de financiación política → contratos:** actores que financian campañas y luego obtienen contratos, directa o indirectamente.
- **Estructuras de ofuscación:** la corrupción sofisticada usa intermediarios, representantes legales cruzados y entidades de segundo nivel para evadir detección directa.

### 2.2 Evidencia internacional

- **Brasil (Ceará):** Pompeu & Holanda Filho (2025) usaron GraphSAGE sobre un grafo bipartito de licitantes-licitaciones en 184 municipios (2010-2023), obteniendo ~90% de accuracy en detección de colusión.
- **Multi-país:** Rodríguez et al. (2024) demostraron que GNNs superan a redes neuronales tradicionales en detección de colusión cross-country (Brasil, Japón, Italia, USA, Suiza).
- **Detección financiera:** Kanezashi et al. (2022) mostraron que modelos heterogéneos (RGCN, HAN, HGT) superan consistentemente a modelos homogéneos en detección de fraude en Ethereum.
- **Producción:** GoSage (Gojek, 2023) desplegó GNN heterogéneo con atención multi-nivel en producción para detección de colusión en plataforma de pagos digitales.
- **NVIDIA Blueprint:** Arquitectura de referencia que combina GraphSAGE para generar embeddings + XGBoost para clasificación final.

### 2.3 Contexto colombiano

- **VigIA** (Gallego, Rivero & Martínez, 2021): modelo de machine learning para la Veeduría Distrital de Bogotá, usando datos SECOP. Usa modelos tabulares (no grafos).
- **SIP v2.0** (2026): evolución de VigIA con 4 modelos XGBoost + IRIC + RCAC. Tabular.
- **Gap identificado:** ningún sistema desplegado en Colombia usa GNNs para detección de redes de corrupción en contratación pública. SIP-Graph sería el primero.

---

## 3. Objetivos

### 3.1 Objetivo General

Construir un sistema basado en Graph Neural Networks que modele la red de contratación pública colombiana como un grafo heterogéneo, detecte actores estructuralmente anómalos y clasifique comunidades de actores como potenciales redes de corrupción.

### 3.2 Objetivos Específicos

1. Construir un **grafo heterogéneo** con 5 tipos de nodos y 5 tipos de aristas a partir de datos SECOP, RCAC, RUES y bases de financiación política.
2. Implementar un módulo de **resolución de entidades por nombre** para cruzar la base del Monitor Ciudadano (solo nombres) con los nodos del grafo (NIT/CC).
3. Entrenar un **Graph Autoencoder con encoder GraphSAGE** para generar embeddings de nodos y detectar anomalías estructurales de forma no supervisada.
4. Implementar **detección de comunidades** (Leiden/Louvain) sobre los embeddings y calcular features agregadas por comunidad.
5. Clasificar comunidades como **potenciales redes de corrupción** usando weak labels derivadas del Monitor Ciudadano y el RCAC.
6. Generar un módulo de **cruce financiación-contratos por representante legal** que identifique relaciones indirectas de financiación política → contratación.
7. Optimizar todo el pipeline para ejecutar en **RTX 2060 (6GB VRAM) + 90GB RAM DDR3 + 2× CPU Intel 3GHz**.

---

# ══════════════════════════════════════════════════════
# SECCIÓN B: ARQUITECTURA DEL GRAFO
# ══════════════════════════════════════════════════════

## 4. Definición del Grafo Heterogéneo

### 4.1 Tipos de Nodos

```
NODO                    | FUENTE PRIMARIA                          | IDENTIFICADOR ÚNICO           | VOLUMEN ESTIMADO
═══════════════════════ | ════════════════════════════════════════  | ════════════════════════════   | ════════════════
Proveedor               | proveedores_registrados.csv               | (tipo_documento, numero_doc)  | ~1,555,059
Persona Natural         | Extraído de repr. legal en proveedores   | (tipo_documento, numero_doc)  | ~500,000 - 800,000 (est.)
Proceso de Contratación | procesos_SECOP.csv                       | ID Proceso                    | ~5,106,527
Entidad Estatal         | Extraído de contratos/procesos SECOP     | Codigo Entidad                | ~5,000 - 10,000 (est.)
Campaña Política        | Base de financiación                     | ID campaña o (partido+año)    | ~500 - 2,000 (est.)
```

### 4.2 Tipos de Aristas

```
ARISTA                  | ORIGEN → DESTINO               | FUENTE                            | VOLUMEN ESTIMADO    | ATRIBUTOS
═══════════════════════ | ══════════════════════════════  | ═════════════════════════════════  | ═══════════════════ | ═════════════════════════════
propuso_en              | Proveedor → Proceso            | proponentes_proceso_SECOP.csv     | ~3,310,267          | ganó (bool), rol (str)
es_representante_de     | Persona → Proveedor            | proveedores_registrados.csv       | ~1,555,059          | fecha_registro (date)
contrato_con            | Proveedor → Entidad            | contratos_SECOP.csv               | ~341,727            | valor (float), modalidad (str), fecha_firma (date)
financió                | Persona/Proveedor → Campaña    | Base de financiación              | Variable            | monto (float), año (int)
fue_sancionado_por      | Persona/Proveedor → (self)     | RCAC (boletines, SIRI, SIC, etc) | ~60,000 (est.)      | fecha_sancion (date), tipo (str), fuente (str)
```

### 4.3 Features por Tipo de Nodo

#### 4.3.1 Nodo: Proveedor

| Feature | Tipo | Fuente | Descripción |
|---------|------|--------|-------------|
| `tipo_persona` | categórica (2) | `proveedores_registrados.csv` | NATURAL / JURIDICA |
| `departamento` | categórica (~33) | `proveedores_registrados.csv` | Departamento de registro |
| `municipio` | categórica (~1,100) | `proveedores_registrados.csv` | Municipio de registro. Encode con target encoding o embeddings. |
| `num_actividades_ciiu` | numérica | `proveedores_registrados.csv` | Número de actividades CIIU registradas |
| `antiguedad_dias` | numérica | `proveedores_registrados.csv` | Días desde registro en SECOP hasta `as_of_date` |
| `estado` | categórica | `proveedores_registrados.csv` | Estado del proveedor (activo, inhabilitado, etc.) |
| `tiene_sancion_rcac` | binaria (0/1) | RCAC consolidado | Si el proveedor aparece en el RCAC (con corte temporal) |
| `num_sanciones_rcac` | numérica | RCAC consolidado | Número de sanciones anteriores a `as_of_date` |
| `num_fuentes_rcac` | numérica | RCAC consolidado | Número de fuentes distintas donde aparece |

#### 4.3.2 Nodo: Persona Natural (Representante Legal)

| Feature | Tipo | Fuente | Descripción |
|---------|------|--------|-------------|
| `num_empresas_representadas` | numérica | Derivado de `proveedores_registrados.csv` | Cantidad de proveedores donde aparece como repr. legal |
| `diversidad_geografica` | numérica | Derivado | Número de departamentos distintos de las empresas que representa |
| `diversidad_sectorial` | numérica | Derivado | Número de sectores CIIU distintos de las empresas que representa |
| `tiene_sancion_personal` | binaria (0/1) | RCAC (SIRI, boletines) | Si la persona aparece sancionada en el RCAC |
| `num_sanciones_personal` | numérica | RCAC | Sanciones personales anteriores a `as_of_date` |
| `es_financiador_politico` | binaria (0/1) | Base de financiación | Si la persona ha financiado campañas políticas |

#### 4.3.3 Nodo: Proceso de Contratación

| Feature | Tipo | Fuente | Descripción |
|---------|------|--------|-------------|
| `modalidad_contratacion` | categórica (~8) | `procesos_SECOP.csv` | Licitación, selección abreviada, contratación directa, etc. |
| `presupuesto_oficial_log` | numérica | `procesos_SECOP.csv` | log(presupuesto oficial + 1) |
| `estado_proceso` | categórica | `procesos_SECOP.csv` | Abierto, cerrado, adjudicado, desierto |
| `num_proponentes` | numérica | Derivado de `proponentes_proceso_SECOP.csv` | Cantidad de proponentes que se presentaron |
| `ratio_proponentes_vs_mediana` | numérica | Derivado | num_proponentes / mediana para misma modalidad |
| `año` | numérica | `procesos_SECOP.csv` | Año de apertura del proceso |

#### 4.3.4 Nodo: Entidad Estatal

| Feature | Tipo | Fuente | Descripción |
|---------|------|--------|-------------|
| `nivel_administrativo` | categórica | `contratos_SECOP.csv` | Nacional, territorial, distrito capital |
| `tipo_entidad` | categórica | `contratos_SECOP.csv` | Centralizado, descentralizado, etc. |
| `departamento` | categórica | `contratos_SECOP.csv` | Departamento de la entidad |
| `volumen_contratacion_anual` | numérica | Derivado | Número de contratos promedio por año |
| `num_proveedores_unicos` | numérica | Derivado | Proveedores distintos con los que ha contratado |
| `concentracion_proveedores` | numérica | Derivado | Índice Herfindahl-Hirschman de concentración de proveedores |

#### 4.3.5 Nodo: Campaña Política

| Feature | Tipo | Fuente | Descripción |
|---------|------|--------|-------------|
| `tipo_campaña` | categórica | Base de financiación | Presidencial, gobernación, alcaldía, congreso |
| `año_electoral` | numérica | Base de financiación | Año de la elección |
| `departamento` | categórica | Base de financiación | Departamento (si aplica) |
| `num_financiadores_total` | numérica | Derivado | Financiadores totales de esta campaña |

### 4.4 Almacenamiento del Grafo

El grafo se almacena en formato PyTorch Geometric `HeteroData`:

```python
from torch_geometric.data import HeteroData

data = HeteroData()

# Nodos con sus features (tensores)
data['proveedor'].x = torch.tensor(...)     # [num_proveedores, num_features_proveedor]
data['persona'].x = torch.tensor(...)       # [num_personas, num_features_persona]
data['proceso'].x = torch.tensor(...)       # [num_procesos, num_features_proceso]
data['entidad'].x = torch.tensor(...)       # [num_entidades, num_features_entidad]
data['campaña'].x = torch.tensor(...)       # [num_campañas, num_features_campaña]

# Aristas (edge_index como pares [2, num_edges])
data['proveedor', 'propuso_en', 'proceso'].edge_index = torch.tensor(...)
data['persona', 'es_representante_de', 'proveedor'].edge_index = torch.tensor(...)
data['proveedor', 'contrato_con', 'entidad'].edge_index = torch.tensor(...)
data['persona', 'financió', 'campaña'].edge_index = torch.tensor(...)
data['proveedor', 'financió', 'campaña'].edge_index = torch.tensor(...)

# Atributos de aristas (opcionales)
data['proveedor', 'propuso_en', 'proceso'].edge_attr = torch.tensor(...)  # [num_edges, num_edge_features]
```

### 4.5 Estimación de Tamaño en Memoria

```
COMPONENTE                            | ESTIMACIÓN
═════════════════════════════════════  | ══════════════
Nodos totales                         | ~7.2M
Aristas totales                       | ~5.2M
Feature tensors (float32)             | ~2-4 GB
Edge index tensors (int64)            | ~80 MB
Edge attribute tensors                | ~200 MB
────────────────────────────────────  | ──────────────
TOTAL ESTIMADO EN RAM                 | ~5-8 GB
────────────────────────────────────  | ──────────────
Margen en 90GB RAM                    | AMPLIO (~82 GB libres para preprocessing)
```

---

## 5. Control Temporal del Grafo (Anti Data Leakage)

### 5.1 Principio

Idéntico al principio del RCAC en SIP v2.0: al construir el grafo para entrenamiento con fecha de corte `T`, solo se incluyen aristas cuyo evento ocurrió antes de `T`.

### 5.2 Aristas con Control Temporal

| Arista | Campo temporal | Regla |
|--------|---------------|-------|
| `propuso_en` | Fecha de cierre del proceso | Solo procesos cerrados antes de `T` |
| `contrato_con` | Fecha de firma del contrato | Solo contratos firmados antes de `T` |
| `financió` | Año de la financiación | Solo financiaciones de años ≤ año(T) |
| `fue_sancionado_por` | Fecha de la sanción | Solo sanciones con fecha < `T` |
| `es_representante_de` | Fecha de registro del proveedor | Solo registros con fecha < `T` |

### 5.3 Implementación

```python
class TemporalGraphBuilder:
    """
    Construye el grafo heterogéneo con corte temporal.

    Args:
        as_of_date (date): Fecha de corte. Solo se incluyen aristas
                           cuyos eventos ocurrieron antes de esta fecha.
    """
    def __init__(self, as_of_date: date):
        self.as_of_date = as_of_date

    def build(self, raw_data: dict) -> HeteroData:
        data = HeteroData()
        # Filtrar cada tipo de arista por su campo temporal
        propuestas = raw_data['proponentes'][
            raw_data['proponentes']['fecha_cierre'] < self.as_of_date
        ]
        contratos = raw_data['contratos'][
            raw_data['contratos']['fecha_firma'] < self.as_of_date
        ]
        financiaciones = raw_data['financiacion'][
            raw_data['financiacion']['año'] <= self.as_of_date.year
        ]
        sanciones = raw_data['sanciones'][
            (raw_data['sanciones']['fecha_sancion'].isna()) |
            (raw_data['sanciones']['fecha_sancion'] < self.as_of_date)
        ]
        # ... construir edge_index para cada tipo filtrado
        return data
```

---

# ══════════════════════════════════════════════════════
# SECCIÓN C: RESOLUCIÓN DE ENTIDADES (ENTITY RESOLUTION)
# ══════════════════════════════════════════════════════

## 6. Resolución de Entidades por Nombre

### 6.1 Problema

La base del Monitor Ciudadano (`Base_de_datos_actores_2016_2022.xlsx`) contiene actores involucrados en hechos verificados de corrupción identificados **solo por nombre** (sin NIT ni cédula). Los nodos del grafo están identificados por documento (NIT/CC). Para usar el Monitor como ground truth, es necesario cruzar nombres del Monitor con nombres en el grafo.

### 6.2 Pipeline de Resolución

```
Monitor Ciudadano              Proveedores + Personas del Grafo
(solo nombres)                 (nombre + documento)
     │                                    │
     ▼                                    ▼
  Normalización                    Normalización
     │                                    │
     ▼                                    ▼
  Tokenización                     Tokenización
     │                                    │
     └──────────┐          ┌──────────────┘
                ▼          ▼
           Matching (TF-IDF + cosine similarity)
                     │
                     ▼
              Candidatos (score > threshold)
                     │
                     ▼
              Validación (reglas de negocio)
                     │
                     ▼
              Matches confirmados
              (nombre_monitor → documento_grafo)
```

### 6.3 Normalización de Nombres

```python
import unicodedata
import re

def normalize_name(name: str) -> str:
    """
    Normaliza un nombre para matching.

    Pasos:
    1. Convertir a mayúsculas
    2. Eliminar tildes/acentos (NFD decomposition + strip combining chars)
    3. Colapsar espacios múltiples a uno
    4. Eliminar caracteres no alfanuméricos excepto espacios
    5. Strip de espacios al inicio/final

    Ejemplos:
        "  García   López, María " -> "GARCIA LOPEZ MARIA"
        "GARCÍA LÓPEZ MARÍA"       -> "GARCIA LOPEZ MARIA"
        "garcia lopez maria"       -> "GARCIA LOPEZ MARIA"
    """
    if not name or not isinstance(name, str):
        return ""
    # Paso 1: mayúsculas
    name = name.upper()
    # Paso 2: eliminar tildes
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    # Paso 3-4: limpiar caracteres y espacios
    name = re.sub(r'[^A-Z0-9\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name)
    # Paso 5: strip
    name = name.strip()
    return name
```

### 6.4 Matching con TF-IDF + Cosine Similarity

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

def match_names(
    monitor_names: list[str],
    graph_names: list[str],
    graph_documents: list[str],
    threshold: float = 0.85,
    top_k: int = 3
) -> list[dict]:
    """
    Cruza nombres del Monitor Ciudadano con nombres del grafo.

    Args:
        monitor_names: Nombres normalizados del Monitor Ciudadano.
        graph_names: Nombres normalizados de proveedores/personas del grafo.
        graph_documents: Documentos (NIT/CC) correspondientes a graph_names.
        threshold: Umbral mínimo de similitud coseno para considerar match.
        top_k: Máximo de candidatos a retornar por nombre del Monitor.

    Returns:
        Lista de dicts con:
        - monitor_name: nombre original del Monitor
        - matched_name: nombre del grafo con mayor similitud
        - matched_document: documento (NIT/CC) del match
        - similarity_score: score de similitud [0, 1]
        - confidence: 'high' si score >= 0.95, 'medium' si >= 0.85, 'review' si < 0.85

    NOTA IMPORTANTE: Los matches con confidence != 'high' deben ser revisados
    manualmente. No usar como ground truth automático sin revisión.
    """
    # TF-IDF con n-gramas de caracteres para robustez ante typos
    vectorizer = TfidfVectorizer(
        analyzer='char_wb',
        ngram_range=(2, 4),
        max_features=50000
    )
    # Fit en todos los nombres combinados
    all_names = monitor_names + graph_names
    vectorizer.fit(all_names)

    monitor_vectors = vectorizer.transform(monitor_names)
    graph_vectors = vectorizer.transform(graph_names)

    # Calcular similitudes en batches (para no explotar RAM)
    BATCH_SIZE = 1000
    results = []
    for i in range(0, len(monitor_names), BATCH_SIZE):
        batch = monitor_vectors[i:i+BATCH_SIZE]
        sims = cosine_similarity(batch, graph_vectors)
        for j, row in enumerate(sims):
            top_indices = np.argsort(row)[-top_k:][::-1]
            for idx in top_indices:
                score = row[idx]
                if score >= threshold:
                    confidence = 'high' if score >= 0.95 else 'medium'
                    results.append({
                        'monitor_name': monitor_names[i + j],
                        'matched_name': graph_names[idx],
                        'matched_document': graph_documents[idx],
                        'similarity_score': float(score),
                        'confidence': confidence
                    })
    return results
```

### 6.5 Reglas de Validación Post-Matching

Después del matching por TF-IDF, aplicar las siguientes reglas para reducir falsos positivos:

1. **Personas naturales → personas naturales:** si el nombre del Monitor matchea con un representante legal (persona natural con CC), verificar que el tipo de documento sea CC o CE, no NIT.
2. **Personas jurídicas → proveedores:** si el nombre del Monitor parece razón social (contiene "S.A.S.", "LTDA", "S.A.", "E.U.", etc.), solo matchear contra proveedores con tipo_persona = JURIDICA.
3. **Unicidad:** si un nombre del Monitor matchea con múltiples nodos del grafo con score > 0.95, priorizar el que tenga mayor número de contratos (mayor visibilidad = más probable que sea el actor mencionado en prensa/Monitor).
4. **Matches ambiguos:** todos los matches con `confidence = 'medium'` se exportan a un archivo CSV para revisión manual antes de usarlos como labels.

### 6.6 Output

El módulo genera `entity_resolution_matches.csv`:

```
monitor_name,matched_name,matched_document,matched_doc_type,similarity_score,confidence,match_type
GARCIA LOPEZ MARIA,GARCIA LOPEZ MARIA FERNANDA,52345678,CC,0.92,medium,persona
CONSTRUCTORA XYZ SAS,CONSTRUCTORA XYZ S.A.S.,900123456,NIT,0.98,high,proveedor
```

Y `entity_resolution_stats.json`:

```json
{
    "total_monitor_actors": 1523,
    "matched_high_confidence": 834,
    "matched_medium_confidence": 312,
    "unmatched": 377,
    "match_rate_high": 0.548,
    "match_rate_total": 0.752
}
```

---

# ══════════════════════════════════════════════════════
# SECCIÓN D: CRUCE DE FINANCIACIÓN POLÍTICA POR REPRESENTANTE LEGAL
# ══════════════════════════════════════════════════════

## 7. Módulo de Financiación-Contratos Extendido

### 7.1 Propósito

El cruce existente de financiación-contratos identifica la relación directa: persona/empresa A financia campaña Y, persona/empresa A obtiene contrato con entidad Z. Este módulo extiende el cruce para detectar **relaciones indirectas a través de representantes legales**.

### 7.2 Relaciones a Detectar

```
NIVEL 1 — DIRECTO (ya existe en base cruzada):
  Persona A financia campaña Y
  Persona A (como proveedor o como empresa) obtiene contrato con Entidad Z

NIVEL 2 — INDIRECTO POR REPRESENTANTE LEGAL (NUEVO):
  Persona A financia campaña Y
  Persona A es representante legal de Empresa B
  Empresa B obtiene contrato con Entidad Z
  → A financió campaña Y y su empresa B obtuvo contrato con Z

NIVEL 3 — INDIRECTO POR RED DE REPRESENTACIÓN (NUEVO):
  Persona A financia campaña Y
  Persona A es representante legal de Empresa B
  Persona A es representante legal de Empresa C
  Empresa C obtiene contrato con Entidad Z
  → C está vinculada al financiador A a través de representación compartida

NIVEL 4 — INDIRECTO POR REPRESENTANTE COMPARTIDO (NUEVO):
  Persona A financia campaña Y
  Persona A es representante legal de Empresa B
  Persona D es representante legal de Empresa B Y también de Empresa E
  Empresa E obtiene contrato con Entidad Z
  → E está a 2 saltos de representación del financiador A
```

### 7.3 Implementación

```python
def build_extended_financing_links(
    financiacion_df: pd.DataFrame,
    representantes_df: pd.DataFrame,
    contratos_df: pd.DataFrame,
    max_hops: int = 2
) -> pd.DataFrame:
    """
    Construye cruces extendidos de financiación → contratos
    a través de representantes legales.

    Args:
        financiacion_df: DataFrame con columnas:
            - documento_financiador (str): NIT o CC del financiador
            - tipo_doc_financiador (str): NIT/CC
            - id_campaña (str)
            - año_financiacion (int)
            - monto (float)

        representantes_df: DataFrame con columnas:
            - documento_representante (str): CC del representante legal
            - documento_empresa (str): NIT de la empresa
            - nombre_representante (str)
            - nombre_empresa (str)

        contratos_df: DataFrame con columnas:
            - documento_proveedor (str): NIT o CC del proveedor
            - codigo_entidad (str)
            - fecha_firma (date)
            - valor_contrato (float)
            - id_contrato (str)

        max_hops: Máximo número de saltos por representante legal (1 o 2)

    Returns:
        DataFrame con cada cruce encontrado y el nivel de indirección:
        - documento_financiador, id_campaña, año_financiacion
        - documento_contratista, id_contrato, fecha_contrato
        - nivel_indirección (1=directo, 2=1 salto repr. legal, 3+=más saltos)
        - cadena (lista de documentos intermedios que forman el camino)
    """
    results = []

    # NIVEL 1: Cruce directo (financiador = contratista)
    directo = financiacion_df.merge(
        contratos_df,
        left_on='documento_financiador',
        right_on='documento_proveedor'
    )
    directo = directo[directo['año_financiacion'] <= directo['fecha_firma'].dt.year]
    for _, row in directo.iterrows():
        results.append({
            'documento_financiador': row['documento_financiador'],
            'id_campaña': row['id_campaña'],
            'año_financiacion': row['año_financiacion'],
            'documento_contratista': row['documento_proveedor'],
            'id_contrato': row['id_contrato'],
            'fecha_contrato': row['fecha_firma'],
            'nivel_indirección': 1,
            'cadena': [row['documento_financiador']]
        })

    # NIVEL 2: Financiador es representante legal de empresa que contrata
    fin_repr = financiacion_df.merge(
        representantes_df,
        left_on='documento_financiador',
        right_on='documento_representante'
    )
    nivel2 = fin_repr.merge(
        contratos_df,
        left_on='documento_empresa',
        right_on='documento_proveedor'
    )
    nivel2 = nivel2[nivel2['año_financiacion'] <= nivel2['fecha_firma'].dt.year]
    for _, row in nivel2.iterrows():
        results.append({
            'documento_financiador': row['documento_financiador'],
            'id_campaña': row['id_campaña'],
            'año_financiacion': row['año_financiacion'],
            'documento_contratista': row['documento_empresa'],
            'id_contrato': row['id_contrato'],
            'fecha_contrato': row['fecha_firma'],
            'nivel_indirección': 2,
            'cadena': [row['documento_financiador'], row['documento_empresa']]
        })

    if max_hops >= 2:
        # NIVEL 3: Financiador → repr legal de Empresa A → otro repr legal
        #          compartido → Empresa B que contrata
        # (financiador comparte representante con otra empresa)
        pass  # Implementar con graph traversal sobre representantes_df

    return pd.DataFrame(results)
```

### 7.4 Control Temporal

**REGLA CRÍTICA:** Solo se reportan cruces donde `año_financiacion <= año(fecha_firma_contrato)`. Si la financiación fue posterior al contrato, NO se incluye como señal de corrupción (podría ser agradecimiento post-facto, pero no predicción).

---

# ══════════════════════════════════════════════════════
# SECCIÓN E: MODELO — ETAPA 1: GRAPH AUTOENCODER + ANOMALY DETECTION
# ══════════════════════════════════════════════════════

## 8. Arquitectura del Graph Autoencoder

### 8.1 Visión General

```
                    ENCODER (GraphSAGE)                      DECODER
                    ════════════════════                      ════════
Grafo Heterogéneo   ───►  Capa 1 (SAGEConv)  ───►  Capa 2 (SAGEConv)  ───►  Embeddings Z
     (HeteroData)         [fan_out=15]              [fan_out=10]              [dim=128]
                          [hidden=256]              [out=128]                    │
                          [ReLU + Dropout]          [sin activación]             │
                                                                                ▼
                                                                       ┌──────────────────┐
                                                                       │ Feature Decoder   │
                                                                       │ (reconstruct X)   │
                                                                       │                   │
                                                                       │ Structure Decoder  │
                                                                       │ (reconstruct A)    │
                                                                       └──────────────────┘
                                                                                │
                                                                                ▼
                                                                     Loss = L_feature + λ * L_structure
                                                                                │
                                                                                ▼
                                                                     Anomaly Score por nodo =
                                                                     error de reconstrucción
```

### 8.2 Encoder: GraphSAGE Heterogéneo

```python
import torch
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv, to_hetero

class HomogeneousSAGEEncoder(torch.nn.Module):
    """
    Encoder GraphSAGE homogéneo que será convertido a heterogéneo
    con to_hetero(). Dos capas de message passing.

    Args:
        in_channels (int): Dimensión de features de entrada (-1 para lazy init).
        hidden_channels (int): Dimensión de la capa oculta. Default: 256.
        out_channels (int): Dimensión del embedding de salida. Default: 128.
        dropout (float): Probabilidad de dropout. Default: 0.3.
    """
    def __init__(self, in_channels=-1, hidden_channels=256, out_channels=128, dropout=0.3):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, out_channels)
        self.dropout = dropout

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)
        x = self.conv2(x, edge_index)
        return x

# Convertir a heterogéneo
encoder = HomogeneousSAGEEncoder(hidden_channels=256, out_channels=128)
encoder = to_hetero(encoder, data.metadata(), aggr='mean')
```

**NOTA CRÍTICA para `to_hetero()`:** Se debe usar `add_self_loops=False` si se usa `SAGEConv` en el modelo homogéneo base, ya que self-loops no están bien definidos para aristas bipartitas. Sin embargo, `SAGEConv` no agrega self-loops por defecto (a diferencia de `GCNConv`), por lo que no se requiere cambio adicional.

### 8.3 Decoder: Feature + Structure

```python
class FeatureDecoder(torch.nn.Module):
    """
    Decodifica embeddings Z de vuelta al espacio de features X.
    Un MLP por tipo de nodo.

    Decoders por tipo de nodo porque cada tipo tiene dimensión
    de features diferente.
    """
    def __init__(self, embedding_dim: int, feature_dims: dict[str, int]):
        super().__init__()
        self.decoders = torch.nn.ModuleDict()
        for node_type, feat_dim in feature_dims.items():
            self.decoders[node_type] = torch.nn.Sequential(
                torch.nn.Linear(embedding_dim, embedding_dim),
                torch.nn.ReLU(),
                torch.nn.Linear(embedding_dim, feat_dim)
            )

    def forward(self, z_dict: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        return {
            node_type: self.decoders[node_type](z)
            for node_type, z in z_dict.items()
            if node_type in self.decoders
        }


class StructureDecoder(torch.nn.Module):
    """
    Decodifica la estructura del grafo (predicción de aristas).
    Para cada par de nodos (i, j), la probabilidad de que exista
    una arista se calcula como sigmoid(z_i · z_j).
    """
    def forward(self, z_src: torch.Tensor, z_dst: torch.Tensor,
                edge_index: torch.Tensor) -> torch.Tensor:
        src_z = z_src[edge_index[0]]
        dst_z = z_dst[edge_index[1]]
        return torch.sigmoid((src_z * dst_z).sum(dim=-1))
```

### 8.4 Loss Function

```python
class GraphAutoEncoderLoss(torch.nn.Module):
    """
    Loss combinada: reconstrucción de features + reconstrucción de estructura.

    L = L_feature + lambda_structure * L_structure

    L_feature = MSE(X, X_reconstructed) por tipo de nodo
    L_structure = BCE(A, A_predicted) por tipo de arista

    Args:
        lambda_structure (float): Peso relativo de la loss de estructura.
            Default: 0.5. Aumentar si se quiere priorizar la detección
            de anomalías basadas en conexiones inusuales vs. features inusuales.
    """
    def __init__(self, lambda_structure: float = 0.5):
        self.lambda_structure = lambda_structure

    def forward(self, x_dict, x_hat_dict, edge_labels_dict):
        # Feature reconstruction loss
        feature_loss = 0
        for node_type in x_dict:
            if node_type in x_hat_dict:
                feature_loss += F.mse_loss(x_hat_dict[node_type], x_dict[node_type])

        # Structure reconstruction loss (con negative sampling)
        structure_loss = 0
        for edge_type, (pos_pred, neg_pred) in edge_labels_dict.items():
            pos_loss = -torch.log(pos_pred + 1e-8).mean()
            neg_loss = -torch.log(1 - neg_pred + 1e-8).mean()
            structure_loss += pos_loss + neg_loss

        return feature_loss + self.lambda_structure * structure_loss
```

### 8.5 Anomaly Score

```python
def compute_anomaly_scores(
    model: GraphAutoEncoder,
    data: HeteroData,
    node_type: str
) -> torch.Tensor:
    """
    Calcula el anomaly score de cada nodo como el error de
    reconstrucción de sus features.

    Score alto = el nodo es difícil de reconstruir a partir de
    su vecindario = su posición/features en el grafo son inusuales.

    Args:
        model: Graph Autoencoder entrenado.
        data: Grafo completo.
        node_type: Tipo de nodo a evaluar ('proveedor', 'persona', etc.)

    Returns:
        Tensor de shape [num_nodos_del_tipo] con anomaly scores.
        Scores normalizados al rango [0, 1] usando min-max scaling.
    """
    model.eval()
    with torch.no_grad():
        z_dict = model.encode(data.x_dict, data.edge_index_dict)
        x_hat_dict = model.decode_features(z_dict)

    x_original = data[node_type].x
    x_reconstructed = x_hat_dict[node_type]

    # Error de reconstrucción por nodo (MSE por fila)
    errors = ((x_original - x_reconstructed) ** 2).mean(dim=1)

    # Normalizar a [0, 1]
    scores = (errors - errors.min()) / (errors.max() - errors.min() + 1e-8)
    return scores
```

### 8.6 Hiperparámetros del MVP

| Hiperparámetro | Valor MVP | Rango para tuning | Justificación |
|---|---|---|---|
| `hidden_channels` | 256 | [128, 256, 512] | 256 equilibra capacidad y VRAM en RTX 2060 |
| `out_channels` (embedding_dim) | 128 | [64, 128, 256] | 128 es estándar para grafos de este tamaño |
| `num_layers` | 2 | [2, 3] | 2 capas = vecindario de 2 saltos. 3 capas riesgo de over-smoothing |
| `fan_out` | [15, 10] | [[10,5], [15,10], [25,15]] | Balance sampling/información. [15,10] en RTX 2060 es seguro |
| `dropout` | 0.3 | [0.1, 0.3, 0.5] | 0.3 es conservador para grafos con noise |
| `learning_rate` | 1e-3 | [1e-4, 5e-4, 1e-3, 5e-3] | Adam optimizer |
| `batch_size` | 1024 | [512, 1024, 2048] | 1024 nodos por batch cabe en 6GB VRAM con FP16 |
| `lambda_structure` | 0.5 | [0.1, 0.5, 1.0, 2.0] | Peso relativo de reconstruction loss |
| `epochs` | 100 | [50, 100, 200] | Con early stopping patience=10 |
| `negative_sampling_ratio` | 1.0 | [0.5, 1.0, 2.0] | Aristas negativas por cada positiva |
| `aggregation` | 'mean' | ['mean', 'max', 'sum'] | Para to_hetero() |

---

# ══════════════════════════════════════════════════════
# SECCIÓN F: MODELO — ETAPA 2: DETECCIÓN DE COMUNIDADES Y CLASIFICACIÓN
# ══════════════════════════════════════════════════════

## 9. Detección de Comunidades

### 9.1 Algoritmo

Leiden algorithm (mejora de Louvain) sobre los embeddings del encoder, usando la librería `leidenalg` con `igraph`.

```python
import igraph as ig
import leidenalg
import numpy as np
from sklearn.neighbors import kneighbors_graph

def detect_communities(
    embeddings: np.ndarray,
    node_ids: list[str],
    k_neighbors: int = 15,
    resolution: float = 1.0
) -> list[dict]:
    """
    Detecta comunidades en el espacio de embeddings.

    Proceso:
    1. Construir grafo KNN sobre embeddings (k vecinos más cercanos).
    2. Aplicar Leiden algorithm para detección de comunidades.
    3. Retornar asignación de comunidades.

    Args:
        embeddings: Array [num_nodos, embedding_dim] con embeddings del encoder.
        node_ids: Lista de IDs de nodos correspondientes a cada fila.
        k_neighbors: Número de vecinos para el grafo KNN. Default: 15.
        resolution: Parámetro de resolución de Leiden. Mayor = más comunidades
                    más pequeñas. Default: 1.0.

    Returns:
        Lista de dicts, uno por comunidad:
        - community_id (int)
        - node_ids (list[str]): IDs de nodos en la comunidad
        - size (int): número de nodos
    """
    # Construir grafo KNN
    knn = kneighbors_graph(embeddings, n_neighbors=k_neighbors, mode='distance')
    knn_symmetric = knn + knn.T  # Hacer simétrico

    # Convertir a igraph
    sources, targets = knn_symmetric.nonzero()
    weights = np.array(knn_symmetric[sources, targets]).flatten()
    # Invertir distancias a similitudes
    weights = 1.0 / (1.0 + weights)

    g = ig.Graph(n=len(node_ids), edges=list(zip(sources.tolist(), targets.tolist())),
                 directed=False)
    g.es['weight'] = weights.tolist()

    # Leiden
    partition = leidenalg.find_partition(
        g,
        leidenalg.RBConfigurationVertexPartition,
        weights='weight',
        resolution_parameter=resolution
    )

    communities = []
    for i, members in enumerate(partition):
        communities.append({
            'community_id': i,
            'node_ids': [node_ids[m] for m in members],
            'size': len(members)
        })
    return communities
```

### 9.2 Features Agregadas por Comunidad

Para cada comunidad detectada, se calculan features que capturan patrones de corrupción organizada:

```python
@dataclass
class CommunityFeatures:
    community_id: int
    size: int                                    # Número de nodos

    # Sanciones
    pct_miembros_sancionados: float              # Proporción de miembros en RCAC
    num_sanciones_total: int                     # Sanciones totales de todos los miembros
    num_fuentes_sancion_distintas: int           # Diversidad de fuentes de sanción

    # Financiación política
    pct_miembros_financiadores: float            # Proporción que ha financiado campañas
    num_campañas_financiadas: int                # Campañas distintas financiadas por la comunidad
    tiene_cruce_financiacion_contrato: bool      # Algún miembro financió Y luego contrató
    tiene_cruce_indirecto_repr_legal: bool       # Cruce nivel 2+ por representante legal

    # Estructura de representación legal
    num_representantes_compartidos: int           # Personas que representan >1 empresa en la comunidad
    max_empresas_por_representante: int           # Máximo de empresas representadas por una persona
    densidad_repr_legal: float                   # Aristas repr. legal / posibles aristas repr. legal

    # Concentración de contratación
    num_entidades_contratantes_distintas: int     # Entidades con las que la comunidad contrata
    hhi_entidades: float                          # HHI de concentración en entidades
    pct_contratos_misma_entidad: float           # Proporción de contratos con la entidad más frecuente

    # Co-licitación
    num_procesos_compartidos: int                 # Procesos donde >1 miembro de la comunidad propuso
    pct_procesos_con_colicitacion: float          # De los procesos de la comunidad, en cuántos hubo co-licitación
    patron_rotacion_ganador: float                # Entropía de quién gana entre los miembros (alta entropía = rotación)

    # Anomalía
    mean_anomaly_score: float                     # Promedio de anomaly scores de los miembros
    max_anomaly_score: float                      # Máximo anomaly score en la comunidad

    # Geografía
    num_departamentos: int                        # Departamentos distintos de los miembros
    concentracion_geografica: float               # 1 = todos en el mismo municipio, 0 = dispersos
```

### 9.3 Clasificación de Comunidades (Weak Labels)

```python
def label_communities(
    communities: list[CommunityFeatures],
    monitor_matches: pd.DataFrame,
    rcac_records: dict
) -> list[tuple[CommunityFeatures, int, float]]:
    """
    Asigna weak labels a comunidades basándose en el Monitor Ciudadano y RCAC.

    Criterio de etiquetado:
    - POSITIVO (1): la comunidad contiene al menos 1 miembro que:
        (a) aparece en el Monitor Ciudadano como involucrado en hechos de corrupción
            (match con confidence='high'), O
        (b) tiene sanciones en 2+ fuentes distintas del RCAC.
    - NEGATIVO (0): ningún miembro cumple los criterios anteriores.

    El label es WEAK porque:
    - El Monitor puede no cubrir todos los actos de corrupción.
    - Un miembro sancionado no implica que toda la comunidad sea corrupta.
    - Matches del Monitor con confidence='medium' NO se usan como labels automáticos.

    Returns:
        Lista de tuplas (CommunityFeatures, label, confidence_score)
        donde confidence_score indica la fuerza de la evidencia.
    """
    pass  # Implementar según criterios arriba
```

### 9.4 Clasificador de Comunidades

Para el MVP, usar un modelo simple (Random Forest o Gradient Boosting) sobre las features agregadas:

```python
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import precision_recall_curve, average_precision_score

def train_community_classifier(
    features: np.ndarray,
    labels: np.ndarray,
    n_splits: int = 5
) -> tuple:
    """
    Entrena clasificador de comunidades con validación cruzada.

    NOTA: Se prioriza PRECISION sobre RECALL porque es preferible
    señalar pocas comunidades con alta confianza que muchas con
    muchos falsos positivos. Los órganos de control tienen
    recursos limitados para investigar.

    Métricas principales:
    - Average Precision (AP): métrica principal
    - Precision@k: precisión en las top-k comunidades más sospechosas
    - Recall: secundaria (no optimizar directamente)
    """
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    model = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.1,
        subsample=0.8,
        random_state=42
    )
    # ... validación cruzada estándar
    return model, metrics
```

---

# ══════════════════════════════════════════════════════
# SECCIÓN G: OPTIMIZACIÓN COMPUTACIONAL
# ══════════════════════════════════════════════════════

## 10. Estrategia de Optimización para Hardware Específico

### 10.1 Hardware Target

| Componente | Especificación | Limitación principal | Estrategia |
|---|---|---|---|
| GPU | NVIDIA RTX 2060 (6GB VRAM) | VRAM limitada para grafos grandes | Mini-batch training con NeighborLoader |
| RAM | 90GB DDR3 | Ancho de banda menor que DDR4/DDR5 | Grafo completo en RAM, pin_memory=True |
| CPU | 2× Intel 3GHz (generación anterior) | Throughput de preprocessing | Paralelización con joblib/multiprocessing |

### 10.2 Configuración CUDA

```python
import torch

# Verificar disponibilidad de GPU
assert torch.cuda.is_available(), "CUDA no disponible"
device = torch.device('cuda:0')

# Optimizaciones CUDA
torch.backends.cudnn.benchmark = True    # Optimizar kernels para tamaño de tensor repetido
torch.backends.cuda.matmul.allow_tf32 = True  # Permitir TF32 para matmul (si soportado)

# Precisión mixta (FP16) — CRÍTICO para RTX 2060
from torch.cuda.amp import GradScaler, autocast
scaler = GradScaler()

# Training loop con mixed precision
for batch in loader:
    optimizer.zero_grad()
    with autocast():
        # Forward pass en FP16 (mitad de VRAM)
        z_dict = model.encode(batch.x_dict, batch.edge_index_dict)
        loss = compute_loss(z_dict, batch)
    # Backward pass con gradient scaling
    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()

# Liberar cache CUDA periódicamente (cada N batches)
if batch_idx % 50 == 0:
    torch.cuda.empty_cache()
```

### 10.3 DataLoader con NeighborLoader

```python
from torch_geometric.loader import NeighborLoader

# NeighborLoader samplea subgrafos alrededor de nodos semilla
# Esto permite entrenar en grafos que no caben en VRAM
train_loader = NeighborLoader(
    data,
    num_neighbors={
        # Fan-out por tipo de arista y por capa
        ('proveedor', 'propuso_en', 'proceso'): [15, 10],
        ('proceso', 'rev_propuso_en', 'proveedor'): [15, 10],
        ('persona', 'es_representante_de', 'proveedor'): [10, 5],
        ('proveedor', 'rev_es_representante_de', 'persona'): [10, 5],
        ('proveedor', 'contrato_con', 'entidad'): [10, 5],
        ('entidad', 'rev_contrato_con', 'proveedor'): [10, 5],
    },
    batch_size=1024,              # Nodos semilla por batch
    input_nodes=('proveedor', train_mask),  # Tipo de nodo a clasificar
    shuffle=True,
    num_workers=4,                # Paralelizar sampling en CPU
    pin_memory=True,              # Acelerar transferencia CPU→GPU (mitiga DDR3)
    drop_last=False,
)
```

**NOTA sobre `pin_memory=True` y DDR3:** La memoria pineada (page-locked) permite transferencias DMA directas CPU→GPU sin copia intermedia. En DDR3, el ancho de banda (~12 GB/s) es menor que DDR4 (~25 GB/s), por lo que esta optimización es especialmente importante para compensar.

### 10.4 Paralelización de Preprocessing en CPU

```python
from joblib import Parallel, delayed
import multiprocessing

N_CORES = multiprocessing.cpu_count()  # Usar todos los cores disponibles

def preprocess_in_parallel(dataframes: dict, n_jobs: int = -1):
    """
    Procesa múltiples DataFrames en paralelo usando todos los cores.

    Args:
        dataframes: Dict con nombre → DataFrame a procesar.
        n_jobs: -1 para usar todos los cores.

    NOTA: Con 2 CPUs Intel de 3GHz, n_jobs=-1 típicamente usa 4-8 cores
    (dependiendo de si tienen hyper-threading).
    """
    results = Parallel(n_jobs=n_jobs, verbose=1)(
        delayed(process_single_df)(name, df) for name, df in dataframes.items()
    )
    return dict(results)
```

### 10.5 Gestión de Memoria RAM

```python
import gc

def load_large_csv_chunked(filepath: str, usecols: list = None,
                            chunksize: int = 500_000) -> pd.DataFrame:
    """
    Carga CSVs grandes en chunks para controlar uso de RAM.

    Para archivos > 1GB (procesos_SECOP.csv = 5.3GB,
    ofertas_proceso_SECOP.csv = 3.4GB), cargar en chunks
    y procesar incrementalmente.

    Con 90GB RAM hay margen, pero es buena práctica:
    - Especificar dtypes explícitos para reducir memoria
    - Usar usecols para cargar solo columnas necesarias
    - Convertir categorías con pd.Categorical
    """
    dtype_optimizations = {
        'Modalidad de Contratacion': 'category',
        'Tipo de Contrato': 'category',
        'Departamento': 'category',
        'Estado': 'category',
    }
    chunks = []
    for chunk in pd.read_csv(filepath, chunksize=chunksize,
                              usecols=usecols, dtype=dtype_optimizations,
                              low_memory=False):
        chunks.append(chunk)

    result = pd.concat(chunks, ignore_index=True)
    gc.collect()  # Forzar garbage collection después de concat
    return result
```

### 10.6 Estimación de Tiempos

| Fase | Operación | Estimación | Recurso limitante |
|---|---|---|---|
| Preprocessing | Cargar y limpiar CSVs (~12GB total) | 15-30 min | RAM + CPU |
| Preprocessing | Resolución de entidades (Monitor) | 5-15 min | CPU |
| Construcción | Construir grafo HeteroData | 10-20 min | RAM |
| Entrenamiento MVP | GraphSAGE Autoencoder (100 epochs) | 2-6 horas | GPU VRAM |
| Detección | Comunidades Leiden | 5-15 min | CPU + RAM |
| Clasificación | Entrenar classifier de comunidades | < 5 min | CPU |
| **TOTAL MVP** | | **3-8 horas** | |

---

# ══════════════════════════════════════════════════════
# SECCIÓN H: ESTRUCTURA DEL PROYECTO Y PIPELINE
# ══════════════════════════════════════════════════════

## 11. Estructura del Proyecto

```
sip_graph/
├── config/
│   ├── settings.py                  # Configuración general + paths + hiperparámetros
│   ├── hardware_config.py           # Detección automática de GPU/RAM + optimizaciones
│   └── graph_schema.py              # Definición de tipos de nodos, aristas, features
│
├── data/
│   ├── loaders/
│   │   ├── secop_loader.py          # Carga contratos, procesos, proponentes, proveedores
│   │   ├── rcac_loader.py           # Carga datos RCAC consolidado
│   │   ├── financiacion_loader.py   # Carga base de financiación + cruce con contratos
│   │   ├── monitor_loader.py        # Carga Monitor Ciudadano (actores 2016-2022)
│   │   └── rues_loader.py           # Carga RUES (si se necesita para repr. legales)
│   │
│   ├── preprocessing/
│   │   ├── name_normalizer.py       # Normalización de nombres (mayúsculas, tildes, espacios)
│   │   ├── document_normalizer.py   # Normalización de NIT/CC (sin puntos, dígito verificación)
│   │   ├── feature_encoder.py       # Encoding de features categóricas → numérico
│   │   └── temporal_filter.py       # Filtrado temporal de aristas (as_of_date)
│   │
│   ├── entity_resolution/
│   │   ├── tfidf_matcher.py         # Matching TF-IDF + cosine similarity
│   │   ├── validation_rules.py      # Reglas de validación post-matching
│   │   └── export_for_review.py     # Exportar matches ambiguos para revisión manual
│   │
│   ├── graph_builder/
│   │   ├── node_builder.py          # Construye nodos con features
│   │   ├── edge_builder.py          # Construye aristas con atributos
│   │   ├── hetero_graph.py          # Ensambla HeteroData completo
│   │   └── financing_crosser.py     # Cruce extendido financiación→contratos por repr. legal
│   │
│   └── artifacts/                   # Generados por el pipeline (NO versionar en git)
│       ├── graph.pt                 # Grafo HeteroData serializado
│       ├── entity_resolution_matches.csv
│       ├── entity_resolution_stats.json
│       ├── node_id_mappings.json    # Mapeo de IDs originales ↔ índices del grafo
│       └── preprocessing_metadata.json
│
├── models/
│   ├── encoder.py                   # GraphSAGE encoder (homogéneo, convertido con to_hetero)
│   ├── decoder.py                   # Feature decoder + Structure decoder
│   ├── autoencoder.py               # Graph Autoencoder completo
│   ├── anomaly_scorer.py            # Calcula anomaly scores por nodo
│   ├── community_detector.py        # Leiden/Louvain sobre embeddings
│   ├── community_features.py        # Features agregadas por comunidad
│   ├── community_classifier.py      # Clasificador de comunidades (weak labels)
│   └── artifacts/                   # Modelos entrenados
│       ├── autoencoder.pt           # Pesos del autoencoder
│       ├── embeddings.pt            # Embeddings de todos los nodos
│       ├── anomaly_scores.pt        # Scores de anomalía
│       ├── communities.json         # Comunidades detectadas
│       ├── community_classifier.pkl # Clasificador de comunidades
│       └── training_metadata.json
│
├── analysis/
│   ├── anomaly_analysis.py          # Análisis de nodos anómalos (top-k, distribución)
│   ├── community_analysis.py        # Análisis de comunidades (visualización, features)
│   ├── financing_analysis.py        # Análisis de cruces financiación-contratos
│   └── validation.py                # Validación contra Monitor Ciudadano
│
├── optimization/
│   ├── cuda_setup.py                # Configuración CUDA + mixed precision
│   ├── memory_manager.py            # Gestión de RAM para CSVs grandes
│   └── parallel_processing.py       # Paralelización CPU con joblib
│
├── tests/
│   ├── test_name_normalizer.py
│   ├── test_entity_resolution.py
│   ├── test_graph_builder.py
│   ├── test_temporal_filter.py
│   ├── test_autoencoder.py
│   ├── test_community_detector.py
│   └── test_financing_crosser.py
│
├── notebooks/                       # Exploración y visualización
│   ├── 01_data_exploration.ipynb
│   ├── 02_graph_statistics.ipynb
│   ├── 03_embedding_visualization.ipynb
│   ├── 04_anomaly_analysis.ipynb
│   └── 05_community_analysis.ipynb
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 12. Pipeline Completo

```
PIPELINE DE CONSTRUCCIÓN Y ENTRENAMIENTO
═══════════════════════════════════════════════════════════════════════

  FASE 1: Data Loading
  ────────────────────
  secop_loader.py         ──► DataFrames crudos (contratos, procesos,
  rcac_loader.py              proponentes, proveedores, sanciones,
  financiacion_loader.py      financiación, monitor ciudadano)
  monitor_loader.py
         │
         ▼
  FASE 2: Preprocessing
  ─────────────────────
  name_normalizer.py      ──► Nombres normalizados
  document_normalizer.py  ──► Documentos normalizados
  feature_encoder.py      ──► Features numéricas/encoded
  temporal_filter.py      ──► Datos filtrados por as_of_date
         │
         ▼
  FASE 3: Entity Resolution
  ─────────────────────────
  tfidf_matcher.py        ──► entity_resolution_matches.csv
  validation_rules.py         (Monitor Ciudadano → documentos del grafo)
  export_for_review.py        + matches_para_revision_manual.csv
         │
         ▼
  FASE 4: Graph Construction
  ──────────────────────────
  node_builder.py         ──► Nodos con features
  edge_builder.py         ──► Aristas con atributos y control temporal
  financing_crosser.py    ──► Cruces extendidos financiación-repr. legal
  hetero_graph.py         ──► graph.pt (HeteroData serializado)
         │
         ▼
  FASE 5: Model Training (Etapa 1)
  ──────────────────────────────────
  autoencoder.py          ──► autoencoder.pt (modelo entrenado)
  (GraphSAGE encoder         embeddings.pt (embeddings de todos los nodos)
   + Feature/Structure        anomaly_scores.pt
   decoders)
   Con: mixed precision,
   NeighborLoader,
   pin_memory=True
         │
         ▼
  FASE 6: Community Detection (Etapa 2)
  ──────────────────────────────────────
  community_detector.py   ──► communities.json
  community_features.py       (comunidades con features agregadas)
  community_classifier.py     community_classifier.pkl
         │
         ▼
  FASE 7: Analysis & Validation
  ─────────────────────────────
  anomaly_analysis.py     ──► Reportes de nodos anómalos
  community_analysis.py       Reportes de comunidades sospechosas
  financing_analysis.py       Cruces financiación-contratos
  validation.py               Métricas contra Monitor Ciudadano
```

---

## 13. Tech Stack

### 13.1 Dependencias Core

| Componente | Paquete | Versión mínima | Propósito |
|---|---|---|---|
| Runtime | `python` | 3.12 | Consistente con SIP v2.0 |
| GNN | `torch` | 2.1+ | Framework de deep learning |
| GNN | `torch-geometric` | 2.4+ | Librería de GNN (SAGEConv, to_hetero, NeighborLoader) |
| GNN | `torch-scatter` | 2.1+ | Dependencia de PyG |
| GNN | `torch-sparse` | 0.6+ | Dependencia de PyG |
| Grafos | `igraph` | 0.11+ | Backend para detección de comunidades |
| Grafos | `leidenalg` | 0.10+ | Algoritmo Leiden |
| Data | `pandas` | 2.0+ | Procesamiento tabular |
| Data | `numpy` | 1.24+ | Operaciones numéricas |
| Data | `polars` | 0.20+ | Alternativa rápida para CSVs grandes (opcional) |
| ML | `scikit-learn` | 1.3+ | TF-IDF, clasificador de comunidades, métricas |
| NLP | `unidecode` | 1.3+ | Normalización de nombres (fallback) |
| Paralelismo | `joblib` | 1.3+ | Paralelización CPU |
| Serialización | `torch` (save/load) | - | Guardar/cargar grafos y modelos |
| Visualización | `matplotlib` | 3.7+ | Plots de análisis |
| Visualización | `networkx` | 3.1+ | Visualización de subgrafos pequeños |
| Testing | `pytest` | 7.0+ | Tests |

### 13.2 Instalación CUDA para RTX 2060

```bash
# RTX 2060 = arquitectura Turing (SM_75)
# Requiere CUDA 11.8+ o 12.x

# Opción 1: pip con CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install torch-geometric
pip install torch-scatter torch-sparse -f https://data.pyg.org/whl/torch-2.1.0+cu121.html

# Opción 2: conda
conda install pytorch torchvision torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia
conda install pyg -c pyg
```

---

# ══════════════════════════════════════════════════════
# SECCIÓN I: ROADMAP DE IMPLEMENTACIÓN
# ══════════════════════════════════════════════════════

## 14. Roadmap

### Fase 1: Data Loading + Preprocessing (semanas 1-2)

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Cargar CSVs SECOP grandes | `secop_loader.py` | procesos_SECOP.csv (5.3GB) y ofertas_proceso_SECOP.csv (3.4GB) cargados en < 10 min con optimización de dtypes |
| Normalización de nombres | `name_normalizer.py` | "  García   López, María " → "GARCIA LOPEZ MARIA". Test con 20+ casos edge |
| Normalización de documentos | `document_normalizer.py` | NIT con puntos/guiones → solo dígitos. CC con prefijo → solo número |
| Extracción de representantes legales | `secop_loader.py` | DataFrame de (doc_representante, doc_empresa) extraído de proveedores_registrados.csv |
| Configuración CUDA | `cuda_setup.py` | RTX 2060 detectada. Mixed precision funcional. torch.cuda.amp.autocast() sin errores |
| Configuración paralela | `parallel_processing.py` | Cores detectados. joblib funcional con n_jobs=-1 |

### Fase 2: Entity Resolution (semanas 2-3)

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Matching TF-IDF | `tfidf_matcher.py` | Matching completo del Monitor Ciudadano contra proveedores+personas. Match rate > 50% |
| Validación post-match | `validation_rules.py` | Reglas de tipo persona/jurídica aplicadas. Falsos positivos evidentes eliminados |
| Exportar para revisión | `export_for_review.py` | CSV con matches medium-confidence generado. Formato claro para revisión manual |
| Estadísticas | `entity_resolution_stats.json` | Stats generados: total, matched_high, matched_medium, unmatched |

### Fase 3: Graph Construction (semanas 3-4)

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Nodos con features | `node_builder.py` | 5 tipos de nodos construidos. Features normalizadas. Sin NaN |
| Aristas con control temporal | `edge_builder.py` | 5 tipos de aristas. Test: arista con fecha > as_of_date NO aparece |
| Cruce financiación extendido | `financing_crosser.py` | Nivel 1 (directo) y Nivel 2 (repr. legal) implementados. Control temporal verificado |
| Grafo HeteroData | `hetero_graph.py` | graph.pt generado. Validación: num_nodes y num_edges coinciden con esperado |
| Test de integridad | `test_graph_builder.py` | Sin nodos huérfanos. Todos los edge_index dentro de rango. Features sin NaN/Inf |

### Fase 4: Model Training — Etapa 1 (semanas 4-6)

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Encoder GraphSAGE | `encoder.py` | Forward pass sin errores en batch de 1024. VRAM < 4GB con FP16 |
| Decoders | `decoder.py` | Feature decoder reconstruct. Structure decoder con negative sampling |
| Autoencoder completo | `autoencoder.py` | Training loop funcional. Loss decrece. Early stopping implementado |
| Anomaly scores | `anomaly_scorer.py` | Scores [0,1] para todos los nodos. Distribución no trivial (no todo 0 o todo 1) |
| Validación básica | `validation.py` | Nodos del Monitor Ciudadano tienen anomaly score promedio > mediana global |

### Fase 5: Community Detection — Etapa 2 (semanas 6-7)

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Detección Leiden | `community_detector.py` | Comunidades detectadas. Distribución de tamaños razonable (no 1 comunidad gigante) |
| Features de comunidad | `community_features.py` | Todas las features del dataclass CommunityFeatures calculadas sin errores |
| Clasificador | `community_classifier.py` | AP (Average Precision) > 0.3 en validación cruzada (baseline razonable para weak labels) |

### Fase 6: Analysis + Validation (semanas 7-8)

| Tarea | Módulo | Criterio de aceptación |
|---|---|---|
| Análisis de anomalías | `anomaly_analysis.py` | Top-100 nodos anómalos exportados con contexto (nombre, documento, features, vecinos) |
| Análisis de comunidades | `community_analysis.py` | Top-20 comunidades sospechosas exportadas con miembros, features, visualización |
| Análisis de financiación | `financing_analysis.py` | Cruces directos e indirectos tabulados. Estadísticas de niveles de indirección |
| Validación contra Monitor | `validation.py` | Reporte de overlap: qué % de actores del Monitor están en comunidades top-sospechosas |
| Documentación | `README.md` | Setup, uso, interpretación de resultados |

---

## 15. Evolución Post-MVP

### Fase 2 del sistema: R-GCN Heterogéneo (después del MVP)

Reemplazar el encoder GraphSAGE homogéneo (convertido con `to_hetero`) por un R-GCN nativo que entrena parámetros separados por tipo de arista. Esto permite que el modelo aprenda que "financió campaña" tiene una semántica completamente distinta a "propuso en proceso".

```python
from torch_geometric.nn import RGCNConv

class RGCNEncoder(torch.nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels, num_relations):
        super().__init__()
        self.conv1 = RGCNConv(in_channels, hidden_channels, num_relations)
        self.conv2 = RGCNConv(hidden_channels, out_channels, num_relations)
    # ...
```

### Fase 3 del sistema: HGT (futuro)

Heterogeneous Graph Transformer que aprende automáticamente la importancia de diferentes tipos de relaciones y caminos en el grafo, sin meta-paths manuales.

### Integración con SIP XGBoost (futura, opcional)

Si en el futuro se decide conectar los dos sistemas, la forma más limpia sería:
- Generar embeddings de grafo para cada proveedor con SIP-Graph.
- Exponer esos embeddings como features adicionales para los modelos XGBoost de SIP.
- Esto NO está en scope del MVP ni de las Fases 2-3. Solo se consideraría después de validar ambos sistemas independientemente.

---

## 16. Preguntas Abiertas y Decisiones Pendientes

| # | Pregunta | Impacto | Deadline |
|---|---|---|---|
| 1 | ¿Cuántos actores del Monitor Ciudadano se logran matchear con high confidence? | Determina calidad de weak labels | Fase 2 (semana 3) |
| 2 | ¿El representante legal en proveedores_registrados.csv es siempre el actual o hay histórico? | Si solo hay el actual, se pierde la dimensión temporal de la representación | Fase 1 (semana 1) |
| 3 | ¿La base de financiación incluye financiadores tanto de persona natural como jurídica? | Determina si hay aristas financió desde ambos tipos de nodos | Fase 1 (semana 1) |
| 4 | ¿Cuál es el período temporal cubierto por la base de financiación? | Afecta cuántas campañas/períodos se pueden modelar | Fase 1 (semana 1) |
| 5 | ¿Se necesita revisión manual de los matches medium-confidence antes de usarlos como labels? | Si sí, hay dependencia humana antes de Fase 5 | Fase 2 (semana 3) |
| 6 | ¿Qué umbral de anomaly score define "anómalo" para reportar a órganos de control? | Calibración post-entrenamiento | Fase 6 (semana 8) |
| 7 | Resolución del algoritmo Leiden: ¿preferir muchas comunidades pequeñas o pocas grandes? | Afecta granularidad del análisis | Fase 5 (semana 7) |

---

## 17. Fuera de Scope (MVP)

- Frontend / interfaz de usuario
- Conexión con pipeline XGBoost de SIP
- API REST para consulta en tiempo real
- R-GCN o HGT (reservado para Fases 2-3 post-MVP)
- Temporal Graph Networks (grafos dinámicos con timestamps en aristas)
- Graph explanation / interpretabilidad de embeddings (post-MVP)
- Reentrenamiento automático
- Nivel 3+ de cruce de financiación por representante legal (solo Nivel 1 y 2 en MVP)
- Integración con datos de la Fiscalía (datos municipales agregados, no a nivel de contrato)
- Procesamiento NLP del objeto contractual
