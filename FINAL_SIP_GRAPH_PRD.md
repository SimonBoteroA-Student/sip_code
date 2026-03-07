# PRD: SIP-Graph — Graph-Based Corruption Network Detection Module
## Project Requirements Document v1.0 (English)
## Independent System — Not connected to the SIP XGBoost pipeline

*Date: March 2026*
*Status: MVP-Ready*
*Relationship with SIP Backend v2.0: Fully independent and parallel system. They share no pipeline, models, or indices.*

---

# ══════════════════════════════════════════════════════
# SECTION A: CONTEXT, JUSTIFICATION, AND DESIGN DECISIONS
# ══════════════════════════════════════════════════════

## 1. Executive Summary

SIP-Graph is an independent system for detecting corruption networks in Colombian public procurement, built on Graph Neural Networks (GNNs). Unlike the SIP XGBoost module (which analyzes individual contracts), SIP-Graph models the **relationships between actors** — contractors, legal representatives, government entities, political campaign donors — as a heterogeneous graph and detects structural patterns associated with organized corruption.

**Question answered by SIP (XGBoost):** "How risky is this individual contract?"
**Question answered by SIP-Graph:** "How suspicious is this network of actors?"

The system operates in two stages: (1) a Graph Autoencoder based on GraphSAGE (and later Heterogeneous Graph Transformer) that generates node embeddings and detects structural anomalies in an unsupervised fashion, and (2) a community detection module that identifies actor clusters and classifies them as potentially corrupt networks.

The system evolves across two architectural phases: Phase 1 uses GraphSAGE (MVP), and **Phase 2 adopts a Heterogeneous Graph Transformer (HGT)** that automatically learns the relative importance of different relationship types and multi-hop paths without manual meta-path engineering.

A React-based interactive graph explorer allows investigators to select any contractor or government entity as an anchor node and visually explore its network neighborhood, colored by risk level and annotated with anomaly scores.

**Core Design Decisions:**

- **Unit of analysis:** actors (contractors, individuals, entities) and their relationships, NOT individual contracts.
- **Total independence from SIP XGBoost:** no shared pipeline, features, models, or composite index.
- **Dual approach:** unsupervised anomaly detection (Stage 1) + subgraph classification with weak labels (Stage 2).
- **Algorithm progression:** Phase 1: GraphSAGE → Phase 2: HGT.
- **Heterogeneous graph:** 5 node types, 5 edge types with distinct semantics.
- **Temporal control:** all timestamped edges respect temporal cutoffs to prevent data leakage.
- **Target hardware:** RTX 2060 (6GB VRAM), 2× Intel CPU 3GHz, 90GB DDR3 RAM.
- **Frontend:** React with Cytoscape.js for interactive graph exploration.

---

## 2. Academic Justification and State of the Art

### 2.1 Limitations of the Current Tabular Approach

The SIP XGBoost pipeline treats each contract as an independent observation, enriched with contractor features (RCAC, IHP) and process features. This approach fails to capture:

- **Co-bidding networks:** contractors that systematically participate together in tenders, rotating who wins.
- **Shell companies with shared legal representatives:** one person controls multiple companies that appear to compete with each other.
- **Political financing → contracts cycles:** actors who finance campaigns and then obtain contracts, directly or indirectly.
- **Obfuscation structures:** sophisticated corruption uses intermediaries, cross-linked legal representatives, and second-level entities to evade direct detection.

### 2.2 International Evidence

- **Brazil (Ceará):** Pompeu & Holanda Filho (2025) used GraphSAGE on a bipartite graph of bidders and tenders across 184 municipalities (2010-2023), achieving ~90% accuracy in collusion detection.
- **Multi-country:** Rodríguez et al. (2024) demonstrated that GNNs outperform traditional neural networks in cross-country collusion detection (Brazil, Japan, Italy, USA, Switzerland).
- **Chile:** Muñoz-Cancino et al. (2025) combined Machine Learning with Social Network Analysis on Chilean public procurement data to detect suspicious supplier relationship patterns.
- **Financial fraud (Ethereum):** Kanezashi et al. (2022) showed that heterogeneous models (RGCN, HAN, HGT) consistently outperform homogeneous models in fraud detection on real Ethereum transaction networks.
- **Production deployment (Gojek):** GoSage (2023) deployed a heterogeneous GNN with multi-level attention in production for collusion fraud detection on a digital payment platform.
- **NVIDIA Blueprint:** Reference architecture combining GraphSAGE for node embeddings + XGBoost for final fraud classification.
- **HGT original paper:** Hu et al. (2020, WWW Conference) introduced the Heterogeneous Graph Transformer with type-dependent attention mechanisms, relative temporal encoding, and HGSampling for Web-scale graphs.
- **HGT for fraud detection:** Chen et al. (2025) applied HGT to Ethereum fraud smart contract detection using heterogeneous semantic graphs, achieving state-of-the-art results across Ponzi scheme, honeypot, and phishing datasets.
- **Heterogeneous Graph Autoencoder:** A 2024 study on credit card fraud detection used heterogeneous graph autoencoders trained on legitimate transactions to identify anomalies, achieving AUC-PR of 0.89 and F1-score of 0.81.
- **Portuguese procurement:** Potin et al. (2023, ECML PKDD) applied pattern mining for anomaly detection in graphs for fraud in public procurement.
- **Bipartite network analysis (Brazil):** Lyra et al. (2021) characterized the firm-firm public procurement co-bidding network from Ceará municipalities, demonstrating the power of network topology for collusion detection.

### 2.3 Colombian Context

- **VigIA** (Gallego, Rivero & Martínez, 2021): ML model for the Veeduría Distrital de Bogotá using SECOP data. Tabular models (not graphs).
- **SIP v2.0** (2026): VigIA evolution with 4 XGBoost models + IRIC + RCAC. Tabular.
- **Identified gap:** no deployed system in Colombia uses GNNs for corruption network detection in public procurement. SIP-Graph would be the first.

---

## 3. Objectives

### 3.1 General Objective

Build a Graph Neural Network-based system that models Colombia's public procurement network as a heterogeneous graph, detects structurally anomalous actors, and classifies actor communities as potential corruption networks.

### 3.2 Specific Objectives

1. Build a **heterogeneous graph** with 5 node types and 5 edge types from SECOP, RCAC, RUES, and political financing data.
2. Implement an **entity resolution module by name** to cross-reference the Monitor Ciudadano database (names only) with graph nodes (NIT/CC).
3. Train a **Graph Autoencoder with a GraphSAGE encoder** to generate node embeddings and detect structural anomalies in an unsupervised manner.
4. Implement **community detection** (Leiden/Louvain) on embeddings and compute aggregated features per community.
5. Classify communities as **potential corruption networks** using weak labels derived from Monitor Ciudadano and RCAC.
6. Build an **extended financing-contracts cross-reference module via legal representatives** that identifies indirect political financing → contracting relationships.
7. Optimize the entire pipeline for **RTX 2060 (6GB VRAM) + 90GB DDR3 RAM + 2× Intel 3GHz CPU**.
8. Build a **React-based interactive graph explorer** using Cytoscape.js where investigators can select any contractor or entity and explore its network neighborhood.

---

# ══════════════════════════════════════════════════════
# SECTION B: GRAPH ARCHITECTURE
# ══════════════════════════════════════════════════════

## 4. Heterogeneous Graph Definition

### 4.1 Node Types

```
NODE TYPE               | PRIMARY SOURCE                           | UNIQUE IDENTIFIER             | ESTIMATED VOLUME
═══════════════════════ | ════════════════════════════════════════  | ════════════════════════════   | ════════════════
Contractor (Proveedor)  | proveedores_registrados.csv               | (doc_type, doc_number)        | ~1,555,059
Natural Person          | Extracted from legal repr. in providers   | (doc_type, doc_number)        | ~500,000 - 800,000 (est.)
Procurement Process     | procesos_SECOP.csv                       | Process ID                    | ~5,106,527
Government Entity       | Extracted from contracts/processes SECOP  | Entity Code                   | ~5,000 - 10,000 (est.)
Political Campaign      | Financing database                       | Campaign ID or (party+year)   | ~500 - 2,000 (est.)
```

### 4.2 Edge Types

```
EDGE                    | SOURCE → TARGET              | DATA SOURCE                       | ESTIMATED VOLUME    | ATTRIBUTES
═══════════════════════ | ════════════════════════════  | ═════════════════════════════════  | ═══════════════════ | ═════════════════════════════
bid_in                  | Contractor → Process         | proponentes_proceso_SECOP.csv     | ~3,310,267          | won (bool), role (str)
is_legal_rep_of         | Person → Contractor          | proveedores_registrados.csv       | ~1,555,059          | registration_date (date)
contracted_with         | Contractor → Entity          | contratos_SECOP.csv               | ~341,727            | value (float), modality (str), signing_date (date)
financed                | Person/Contractor → Campaign  | Financing database                | Variable            | amount (float), year (int)
was_sanctioned          | Person/Contractor → (self)    | RCAC (bulletins, SIRI, SIC, etc) | ~60,000 (est.)      | sanction_date (date), type (str), source (str)
```

### 4.3 Node Features by Type

#### 4.3.1 Node: Contractor

| Feature | Type | Source | Description |
|---------|------|--------|-------------|
| `person_type` | categorical (2) | `proveedores_registrados.csv` | NATURAL / JURIDICA (legal entity) |
| `department` | categorical (~33) | `proveedores_registrados.csv` | Registration department |
| `municipality` | categorical (~1,100) | `proveedores_registrados.csv` | Registration municipality. Encode with target encoding or embeddings. |
| `num_ciiu_activities` | numerical | `proveedores_registrados.csv` | Number of registered CIIU economic activities |
| `seniority_days` | numerical | `proveedores_registrados.csv` | Days since SECOP registration until `as_of_date` |
| `status` | categorical | `proveedores_registrados.csv` | Contractor status (active, disqualified, etc.) |
| `has_rcac_sanction` | binary (0/1) | Consolidated RCAC | Whether the contractor appears in RCAC (with temporal cutoff) |
| `num_rcac_sanctions` | numerical | Consolidated RCAC | Number of sanctions prior to `as_of_date` |
| `num_rcac_sources` | numerical | Consolidated RCAC | Number of distinct sources where the contractor appears |

#### 4.3.2 Node: Natural Person (Legal Representative)

| Feature | Type | Source | Description |
|---------|------|--------|-------------|
| `num_companies_represented` | numerical | Derived from `proveedores_registrados.csv` | Number of contractors where this person is legal representative |
| `geographic_diversity` | numerical | Derived | Number of distinct departments of represented companies |
| `sectoral_diversity` | numerical | Derived | Number of distinct CIIU sectors of represented companies |
| `has_personal_sanction` | binary (0/1) | RCAC (SIRI, bulletins) | Whether the person appears sanctioned in RCAC |
| `num_personal_sanctions` | numerical | RCAC | Personal sanctions prior to `as_of_date` |
| `is_political_donor` | binary (0/1) | Financing database | Whether the person has financed political campaigns |

#### 4.3.3 Node: Procurement Process

| Feature | Type | Source | Description |
|---------|------|--------|-------------|
| `procurement_modality` | categorical (~8) | `procesos_SECOP.csv` | Licitación, selección abreviada, contratación directa, etc. |
| `official_budget_log` | numerical | `procesos_SECOP.csv` | log(official_budget + 1) |
| `process_status` | categorical | `procesos_SECOP.csv` | Open, closed, awarded, deserted |
| `num_bidders` | numerical | Derived from `proponentes_proceso_SECOP.csv` | Number of bidders that participated |
| `bidder_ratio_vs_median` | numerical | Derived | num_bidders / median for same modality |
| `year` | numerical | `procesos_SECOP.csv` | Process opening year |

#### 4.3.4 Node: Government Entity

| Feature | Type | Source | Description |
|---------|------|--------|-------------|
| `administrative_level` | categorical | `contratos_SECOP.csv` | National, territorial, capital district |
| `entity_type` | categorical | `contratos_SECOP.csv` | Centralized, decentralized, etc. |
| `department` | categorical | `contratos_SECOP.csv` | Entity department |
| `annual_contracting_volume` | numerical | Derived | Average number of contracts per year |
| `num_unique_contractors` | numerical | Derived | Distinct contractors it has contracted with |
| `contractor_concentration` | numerical | Derived | Herfindahl-Hirschman Index of contractor concentration |

#### 4.3.5 Node: Political Campaign

| Feature | Type | Source | Description |
|---------|------|--------|-------------|
| `campaign_type` | categorical | Financing database | Presidential, governor, mayor, congress |
| `electoral_year` | numerical | Financing database | Election year |
| `department` | categorical | Financing database | Department (if applicable) |
| `total_num_donors` | numerical | Derived | Total donors for this campaign |

### 4.4 Graph Storage

The graph is stored in PyTorch Geometric `HeteroData` format:

```python
from torch_geometric.data import HeteroData

data = HeteroData()

# Nodes with features (tensors)
data['contractor'].x = torch.tensor(...)     # [num_contractors, num_features_contractor]
data['person'].x = torch.tensor(...)         # [num_persons, num_features_person]
data['process'].x = torch.tensor(...)        # [num_processes, num_features_process]
data['entity'].x = torch.tensor(...)         # [num_entities, num_features_entity]
data['campaign'].x = torch.tensor(...)       # [num_campaigns, num_features_campaign]

# Edges (edge_index as pairs [2, num_edges])
data['contractor', 'bid_in', 'process'].edge_index = torch.tensor(...)
data['person', 'is_legal_rep_of', 'contractor'].edge_index = torch.tensor(...)
data['contractor', 'contracted_with', 'entity'].edge_index = torch.tensor(...)
data['person', 'financed', 'campaign'].edge_index = torch.tensor(...)
data['contractor', 'financed', 'campaign'].edge_index = torch.tensor(...)

# Edge attributes (optional)
data['contractor', 'bid_in', 'process'].edge_attr = torch.tensor(...)
```

### 4.5 Memory Size Estimation

```
COMPONENT                             | ESTIMATION
═════════════════════════════════════  | ══════════════
Total nodes                           | ~7.2M
Total edges                           | ~5.2M
Feature tensors (float32)             | ~2-4 GB
Edge index tensors (int64)            | ~80 MB
Edge attribute tensors                | ~200 MB
────────────────────────────────────  | ──────────────
ESTIMATED TOTAL IN RAM                | ~5-8 GB
────────────────────────────────────  | ──────────────
Margin in 90GB RAM                    | AMPLE (~82 GB free for preprocessing)
```

---

## 5. Temporal Graph Control (Anti Data Leakage)

### 5.1 Principle

Identical to the RCAC principle in SIP v2.0: when building the graph for training with cutoff date `T`, only edges whose event occurred before `T` are included.

### 5.2 Temporally Controlled Edges

| Edge | Temporal field | Rule |
|------|---------------|------|
| `bid_in` | Process closing date | Only processes closed before `T` |
| `contracted_with` | Contract signing date | Only contracts signed before `T` |
| `financed` | Financing year | Only financings from years ≤ year(T) |
| `was_sanctioned` | Sanction date | Only sanctions with date < `T` |
| `is_legal_rep_of` | Contractor registration date | Only registrations with date < `T` |

### 5.3 Implementation

```python
class TemporalGraphBuilder:
    """
    Builds the heterogeneous graph with temporal cutoff.

    Args:
        as_of_date (date): Cutoff date. Only edges whose events
                           occurred before this date are included.
    """
    def __init__(self, as_of_date: date):
        self.as_of_date = as_of_date

    def build(self, raw_data: dict) -> HeteroData:
        data = HeteroData()
        # Filter each edge type by its temporal field
        bids = raw_data['bidders'][
            raw_data['bidders']['closing_date'] < self.as_of_date
        ]
        contracts = raw_data['contracts'][
            raw_data['contracts']['signing_date'] < self.as_of_date
        ]
        financings = raw_data['financing'][
            raw_data['financing']['year'] <= self.as_of_date.year
        ]
        sanctions = raw_data['sanctions'][
            (raw_data['sanctions']['sanction_date'].isna()) |
            (raw_data['sanctions']['sanction_date'] < self.as_of_date)
        ]
        # ... build edge_index for each filtered type
        return data
```

---

# ══════════════════════════════════════════════════════
# SECTION C: ENTITY RESOLUTION
# ══════════════════════════════════════════════════════

## 6. Name-Based Entity Resolution

### 6.1 Problem

The Monitor Ciudadano database (`Base_de_datos_actores_2016_2022.xlsx`) contains actors involved in verified corruption events identified **only by name** (no NIT or CC). Graph nodes are identified by document (NIT/CC). To use the Monitor as ground truth, names from the Monitor must be cross-referenced with names in the graph.

### 6.2 Resolution Pipeline

```
Monitor Ciudadano              Graph Contractors + Persons
(names only)                   (name + document)
     │                                    │
     ▼                                    ▼
  Normalization                    Normalization
     │                                    │
     ▼                                    ▼
  Tokenization                     Tokenization
     │                                    │
     └──────────┐          ┌──────────────┘
                ▼          ▼
           Matching (TF-IDF + cosine similarity)
                     │
                     ▼
              Candidates (score > threshold)
                     │
                     ▼
              Validation (business rules)
                     │
                     ▼
              Confirmed matches
              (monitor_name → graph_document)
```

### 6.3 Name Normalization

```python
import unicodedata
import re

def normalize_name(name: str) -> str:
    """
    Normalizes a name for matching.

    Steps:
    1. Convert to uppercase
    2. Remove accents/diacritics (NFD decomposition + strip combining chars)
    3. Collapse multiple spaces to one
    4. Remove non-alphanumeric characters except spaces
    5. Strip leading/trailing spaces

    Examples:
        "  García   López, María " -> "GARCIA LOPEZ MARIA"
        "GARCÍA LÓPEZ MARÍA"       -> "GARCIA LOPEZ MARIA"
        "garcia lopez maria"       -> "GARCIA LOPEZ MARIA"
    """
    if not name or not isinstance(name, str):
        return ""
    name = name.upper()
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    name = re.sub(r'[^A-Z0-9\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name)
    name = name.strip()
    return name
```

### 6.4 TF-IDF + Cosine Similarity Matching

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
    Cross-references Monitor Ciudadano names with graph names.

    Args:
        monitor_names: Normalized names from Monitor Ciudadano.
        graph_names: Normalized names of contractors/persons in the graph.
        graph_documents: Documents (NIT/CC) corresponding to graph_names.
        threshold: Minimum cosine similarity threshold to consider a match.
        top_k: Maximum candidates to return per Monitor name.

    Returns:
        List of dicts with:
        - monitor_name: original Monitor name
        - matched_name: graph name with highest similarity
        - matched_document: matched NIT/CC
        - similarity_score: similarity score [0, 1]
        - confidence: 'high' if score >= 0.95, 'medium' if >= 0.85, 'review' if < 0.85

    IMPORTANT NOTE: Matches with confidence != 'high' must be manually reviewed.
    Do not use as automatic ground truth without review.
    """
    vectorizer = TfidfVectorizer(
        analyzer='char_wb',
        ngram_range=(2, 4),
        max_features=50000
    )
    all_names = monitor_names + graph_names
    vectorizer.fit(all_names)

    monitor_vectors = vectorizer.transform(monitor_names)
    graph_vectors = vectorizer.transform(graph_names)

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

### 6.5 Post-Matching Validation Rules

1. **Natural persons → natural persons:** if the Monitor name matches a legal representative (natural person with CC), verify document type is CC or CE, not NIT.
2. **Legal entities → contractors:** if the Monitor name appears to be a business name (contains "S.A.S.", "LTDA", "S.A.", "E.U.", etc.), only match against contractors with person_type = JURIDICA.
3. **Uniqueness:** if a Monitor name matches multiple graph nodes with score > 0.95, prioritize the one with the most contracts (greater visibility = more likely to be the actor mentioned in press/Monitor).
4. **Ambiguous matches:** all matches with `confidence = 'medium'` are exported to a CSV for manual review before being used as labels.

### 6.6 Output

`entity_resolution_matches.csv` and `entity_resolution_stats.json` (same format as Spanish version).

---

# ══════════════════════════════════════════════════════
# SECTION D: POLITICAL FINANCING CROSS-REFERENCE VIA LEGAL REPRESENTATIVES
# ══════════════════════════════════════════════════════

## 7. Extended Financing-Contracts Module

### 7.1 Purpose

The existing financing-contracts cross-reference identifies direct relationships: person/company A finances campaign Y, person/company A obtains contract with entity Z. This module extends the cross-reference to detect **indirect relationships through legal representatives**.

### 7.2 Relationships to Detect

```
LEVEL 1 — DIRECT (already exists in crossed database):
  Person A finances campaign Y
  Person A (as contractor or as company) obtains contract with Entity Z

LEVEL 2 — INDIRECT VIA LEGAL REPRESENTATIVE (NEW):
  Person A finances campaign Y
  Person A is legal representative of Company B
  Company B obtains contract with Entity Z
  → A financed campaign Y and their company B obtained contract with Z

LEVEL 3 — INDIRECT VIA REPRESENTATION NETWORK (NEW):
  Person A finances campaign Y
  Person A is legal representative of Company B
  Person A is also legal representative of Company C
  Company C obtains contract with Entity Z
  → C is linked to donor A through shared representation

LEVEL 4 — INDIRECT VIA SHARED REPRESENTATIVE (NEW):
  Person A finances campaign Y
  Person A is legal representative of Company B
  Person D is legal representative of Company B AND also of Company E
  Company E obtains contract with Entity Z
  → E is 2 representation hops from donor A
```

### 7.3 Temporal Control

**CRITICAL RULE:** Only cross-references where `financing_year <= year(contract_signing_date)` are reported. If financing was after the contract, it is NOT included as a corruption signal.

### 7.4 Implementation

```python
def build_extended_financing_links(
    financing_df: pd.DataFrame,
    representatives_df: pd.DataFrame,
    contracts_df: pd.DataFrame,
    max_hops: int = 2
) -> pd.DataFrame:
    """
    Builds extended financing → contracts cross-references
    through legal representatives.

    Args:
        financing_df: DataFrame with columns:
            - donor_document (str): NIT or CC of the donor
            - donor_doc_type (str): NIT/CC
            - campaign_id (str)
            - financing_year (int)
            - amount (float)

        representatives_df: DataFrame with columns:
            - representative_document (str): CC of the legal representative
            - company_document (str): NIT of the company
            - representative_name (str)
            - company_name (str)

        contracts_df: DataFrame with columns:
            - contractor_document (str): NIT or CC of the contractor
            - entity_code (str)
            - signing_date (date)
            - contract_value (float)
            - contract_id (str)

        max_hops: Maximum number of legal representative hops (1 or 2)

    Returns:
        DataFrame with each found cross-reference and indirection level:
        - donor_document, campaign_id, financing_year
        - contractor_document, contract_id, contract_date
        - indirection_level (1=direct, 2=1 legal rep. hop, 3+=more hops)
        - chain (list of intermediate documents forming the path)
    """
    results = []

    # LEVEL 1: Direct cross-reference (donor = contractor)
    direct = financing_df.merge(
        contracts_df,
        left_on='donor_document',
        right_on='contractor_document'
    )
    direct = direct[direct['financing_year'] <= direct['signing_date'].dt.year]
    for _, row in direct.iterrows():
        results.append({
            'donor_document': row['donor_document'],
            'campaign_id': row['campaign_id'],
            'financing_year': row['financing_year'],
            'contractor_document': row['contractor_document'],
            'contract_id': row['contract_id'],
            'contract_date': row['signing_date'],
            'indirection_level': 1,
            'chain': [row['donor_document']]
        })

    # LEVEL 2: Donor is legal representative of company that contracts
    donor_repr = financing_df.merge(
        representatives_df,
        left_on='donor_document',
        right_on='representative_document'
    )
    level2 = donor_repr.merge(
        contracts_df,
        left_on='company_document',
        right_on='contractor_document'
    )
    level2 = level2[level2['financing_year'] <= level2['signing_date'].dt.year]
    for _, row in level2.iterrows():
        results.append({
            'donor_document': row['donor_document'],
            'campaign_id': row['campaign_id'],
            'financing_year': row['financing_year'],
            'contractor_document': row['company_document'],
            'contract_id': row['contract_id'],
            'contract_date': row['signing_date'],
            'indirection_level': 2,
            'chain': [row['donor_document'], row['company_document']]
        })

    if max_hops >= 2:
        # LEVEL 3+: Implement with graph traversal on representatives_df
        pass

    return pd.DataFrame(results)
```

---

# ══════════════════════════════════════════════════════
# SECTION E: MODEL — STAGE 1: GRAPH AUTOENCODER + ANOMALY DETECTION
# ══════════════════════════════════════════════════════

## 8. Graph Autoencoder Architecture

### 8.1 Overview

```
                    ENCODER (GraphSAGE)                      DECODER
                    ════════════════════                      ════════
Heterogeneous       ───►  Layer 1 (SAGEConv)  ───►  Layer 2 (SAGEConv)  ───►  Embeddings Z
Graph (HeteroData)        [fan_out=15]              [fan_out=10]              [dim=128]
                          [hidden=256]              [out=128]                    │
                          [ReLU + Dropout]          [no activation]              │
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
                                                                     Anomaly Score per node =
                                                                     reconstruction error
```

### 8.2 Encoder: Heterogeneous GraphSAGE

```python
import torch
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv, to_hetero

class HomogeneousSAGEEncoder(torch.nn.Module):
    """
    Homogeneous GraphSAGE encoder to be converted to heterogeneous
    with to_hetero(). Two message passing layers.
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

# Convert to heterogeneous
encoder = HomogeneousSAGEEncoder(hidden_channels=256, out_channels=128)
encoder = to_hetero(encoder, data.metadata(), aggr='mean')
```

### 8.3 Decoder, Loss, and Anomaly Score

(Same implementation as Spanish version — Feature Decoder per node type, Structure Decoder with dot-product + sigmoid, combined loss with `lambda_structure`, anomaly score as normalized reconstruction error.)

### 8.4 MVP Hyperparameters

| Hyperparameter | MVP Value | Tuning Range | Justification |
|---|---|---|---|
| `hidden_channels` | 256 | [128, 256, 512] | 256 balances capacity and VRAM on RTX 2060 |
| `out_channels` (embedding_dim) | 128 | [64, 128, 256] | 128 is standard for graphs of this scale |
| `num_layers` | 2 | [2, 3] | 2 layers = 2-hop neighborhood. 3 layers risk over-smoothing |
| `fan_out` | [15, 10] | [[10,5], [15,10], [25,15]] | Sampling/information balance. [15,10] safe on RTX 2060 |
| `dropout` | 0.3 | [0.1, 0.3, 0.5] | Conservative for noisy graphs |
| `learning_rate` | 1e-3 | [1e-4, 5e-4, 1e-3, 5e-3] | Adam optimizer |
| `batch_size` | 1024 | [512, 1024, 2048] | 1024 seed nodes per batch fits in 6GB VRAM with FP16 |
| `lambda_structure` | 0.5 | [0.1, 0.5, 1.0, 2.0] | Relative weight of structure reconstruction loss |
| `epochs` | 100 | [50, 100, 200] | With early stopping patience=10 |
| `negative_sampling_ratio` | 1.0 | [0.5, 1.0, 2.0] | Negative edges per positive edge |
| `aggregation` | 'mean' | ['mean', 'max', 'sum'] | For to_hetero() |

---

# ══════════════════════════════════════════════════════
# SECTION F: MODEL — STAGE 2: COMMUNITY DETECTION AND CLASSIFICATION
# ══════════════════════════════════════════════════════

## 9. Community Detection

### 9.1 Algorithm

Leiden algorithm (improvement over Louvain) on encoder embeddings, using `leidenalg` with `igraph`.

### 9.2 Aggregated Community Features

```python
@dataclass
class CommunityFeatures:
    community_id: int
    size: int

    # Sanctions
    pct_sanctioned_members: float
    total_sanctions: int
    num_distinct_sanction_sources: int

    # Political financing
    pct_donor_members: float
    num_campaigns_financed: int
    has_financing_contract_crossref: bool
    has_indirect_legal_rep_crossref: bool

    # Legal representation structure
    num_shared_representatives: int
    max_companies_per_representative: int
    legal_rep_density: float

    # Contracting concentration
    num_distinct_contracting_entities: int
    hhi_entities: float
    pct_contracts_same_entity: float

    # Co-bidding
    num_shared_processes: int
    pct_processes_with_cobidding: float
    winner_rotation_pattern: float  # Entropy of who wins among members

    # Anomaly
    mean_anomaly_score: float
    max_anomaly_score: float

    # Geography
    num_departments: int
    geographic_concentration: float
```

### 9.3 Community Classification with Weak Labels

Communities containing members matched to Monitor Ciudadano actors (high confidence) or with sanctions from 2+ distinct RCAC sources are labeled positive. The classifier (Gradient Boosting on community features) prioritizes **precision over recall** because control bodies have limited investigation resources.

---

# ══════════════════════════════════════════════════════
# SECTION G: HGT — HETEROGENEOUS GRAPH TRANSFORMER ARCHITECTURE
# ══════════════════════════════════════════════════════

## 10. Phase 3 Target Architecture: Heterogeneous Graph Transformer

### 10.1 Why HGT Is the Target Architecture

The progression from GraphSAGE (Phase 1) through R-GCN (Phase 2) to HGT (Phase 3) reflects a fundamental increase in the model's ability to capture the semantics of Colombia's procurement corruption network.

**GraphSAGE** (Phase 1, MVP) treats all edges uniformly after conversion with `to_hetero()`. While `to_hetero()` creates separate parameters per edge type, the attention mechanism is implicit and the model cannot learn that a "financed campaign" edge connecting a person to a political campaign carries fundamentally different corruption signal than a "bid in" edge connecting the same person's company to a procurement process.

**R-GCN** (Phase 2) improves on this by training explicit weight matrices per relation type. However, it requires manual definition of meta-paths to capture multi-hop patterns (e.g., person → financed → campaign ... entity → contracted_with → contractor), and it treats all neighbors of the same relation type with equal importance.

**HGT** (Phase 3) solves both limitations simultaneously. It introduces three innovations that are critical for corruption network detection:

1. **Meta-relation-aware heterogeneous mutual attention:** For each edge `e = (source, target)`, HGT computes attention based on the meta-relation triplet `⟨τ(source), φ(e), τ(target)⟩` where `τ` maps node types and `φ` maps edge types. This means the model automatically learns that the attention weight for a "person → financed → campaign" edge should be computed differently from a "contractor → bid_in → process" edge, without any manual specification.

2. **Automatic "soft" meta-path learning:** Through multi-layer message passing, HGT implicitly learns and extracts meta-paths that are predictive of corruption. A 2-layer HGT can capture paths like: contractor ← is_legal_rep_of ← person → financed → campaign, without the researcher having to enumerate all possible relevant paths. This is critical because corruption obfuscation strategies evolve, and manually defined meta-paths may miss novel patterns.

3. **Relative Temporal Encoding (RTE):** HGT incorporates temporal information directly into the attention mechanism. For edges with timestamps (contract signing dates, sanction dates, financing years), HGT can learn that the temporal ordering matters — a financing event that precedes a contract award is more suspicious than one that follows it.

### 10.2 Academic Foundation

The HGT architecture was introduced by Hu et al. (2020) at WWW 2020 (paper: "Heterogeneous Graph Transformer", arXiv:2003.01332). Key citations and applications relevant to corruption detection:

- **Original HGT paper** (Hu, Dong, Wang & Sun, 2020): Demonstrated on the Open Academic Graph with 179M nodes and 2B edges, showing HGT's scalability to Web-scale heterogeneous graphs. The HGSampling algorithm achieves this by sampling a fixed number of nodes per type per iteration, with sampling probability proportional to the square of relative degree.

- **HGT for fraud detection** (Chen et al., 2025): Applied HGT with heterogeneous semantic graphs to Ethereum fraud smart contract detection. The HGT-based graph classifier outperformed or matched various existing fraud detection methods across Ponzi scheme, honeypot, and phishing datasets.

- **Heterogeneous Graph Autoencoder for credit card fraud** (2024): Combined heterogeneous graph structures with autoencoder-based anomaly detection. The model achieved AUC-PR of 0.89 and F1-score of 0.81, demonstrating that heterogeneous graph representations with reconstruction-based anomaly detection are effective for financial fraud.

- **GoSage (Gojek, 2023):** Multi-level attention-based GNN deployed in production for collusion fraud detection on heterogeneous transaction graphs with multiple node and edge types. Demonstrated real-world viability of heterogeneous attention mechanisms for fraud at scale.

- **Meta-HGT** (2022): Extended HGT with metapath-aware hypergraph structures for capturing high-order relations, showing state-of-the-art performance on heterogeneous information network embedding tasks.

### 10.3 HGT Architecture — Detailed Specification

#### 10.3.1 Formal Definition

Given a heterogeneous graph `G = (V, E, A, R)` where:
- `V` = nodes (contractors, persons, processes, entities, campaigns)
- `E` = edges (bid_in, is_legal_rep_of, contracted_with, financed, was_sanctioned)
- `A` = node type set {contractor, person, process, entity, campaign}
- `R` = edge type set {bid_in, is_legal_rep_of, contracted_with, financed, was_sanctioned}
- `τ(v): V → A` = node type mapping function
- `φ(e): E → R` = edge type mapping function

For each edge `e = (s, t)` linking source node `s` to target node `t`, the meta-relation is `⟨τ(s), φ(e), τ(t)⟩`.

#### 10.3.2 Three Components of HGT

**Component 1: Heterogeneous Mutual Attention**

For target node `t` and source node `s` connected by edge `e`, the attention is computed as:

```
Attention(s, e, t) = softmax_over_all_sources(
    (K(s) · W_ATT_φ(e) · Q(t)^T) / √d
)

where:
    Q(t) = W_Q_τ(t) · H^(l-1)(t)     # Query: depends on TARGET node type
    K(s) = W_K_τ(s) · H^(l-1)(s)     # Key: depends on SOURCE node type
    W_ATT_φ(e)                         # Attention weight: depends on EDGE type
```

The key insight: the attention weight matrix `W_ATT` is parameterized by the **edge type** `φ(e)`, while Q and K are parameterized by **node types** `τ(t)` and `τ(s)`. This means:
- A "person" node attending to "campaign" nodes through "financed" edges uses different attention parameters than the same "person" attending to "contractor" nodes through "is_legal_rep_of" edges.
- This is exactly what we need: the model should weight the "financed → campaign" signal differently from the "represents → company" signal when computing a person's corruption risk representation.

**Component 2: Heterogeneous Message Passing**

```
Message(s, e, t) = W_MSG_φ(e) · H^(l-1)(s)

where:
    W_MSG_φ(e) = message transformation matrix, depends on EDGE type
```

Each edge type has its own message transformation. Information flowing from a campaign node through a "financed" edge is transformed differently than information flowing from a process node through a "bid_in" edge.

**Component 3: Target-Specific Aggregation**

```
H_agg(t) = Σ_over_all_(s,e) [ Attention(s, e, t) × Message(s, e, t) ]

H^(l)(t) = W_τ(t) · σ(H_agg(t)) + H^(l-1)(t)    # Residual connection
```

The aggregated representation is passed through a target-type-specific linear transformation `W_τ(t)` with residual connection. This means "contractor" nodes and "person" nodes maintain their own representation spaces even after message passing.

#### 10.3.3 Relative Temporal Encoding (RTE)

For edges with timestamps (contract signing dates, sanction dates, financing years), HGT introduces temporal encoding:

```
ΔT(s, t) = timestamp(t) - timestamp(s)

Temporal_Encoding(ΔT) = Linear(sinusoidal_basis(ΔT))
```

The temporal encoding is added to the attention computation, allowing the model to learn that:
- A financing event 2 years before a contract is more suspicious than one 10 years before.
- A sanction that occurred right before a new contract signing is a stronger signal.
- The temporal gap between a person becoming a legal representative and the company winning a contract matters.

For our specific case, the relevant temporal differences are:
- `financing_year - contract_signing_year` for financed→contracted_with paths
- `registration_date - contract_signing_date` for is_legal_rep_of→contracted_with paths
- `sanction_date - contract_signing_date` for was_sanctioned→contracted_with paths

#### 10.3.4 HGSampling for Mini-Batch Training

The full graph (~7.2M nodes, ~5.2M edges) cannot fit in GPU VRAM during forward pass. HGT introduces HGSampling:

```python
from torch_geometric.loader import HGTLoader

train_loader = HGTLoader(
    data,
    num_samples={
        # Per node type, per layer: [layer_1_samples, layer_2_samples]
        'contractor': [128, 64],
        'person': [64, 32],
        'process': [128, 64],
        'entity': [32, 16],
        'campaign': [16, 8],
    },
    batch_size=512,                  # Seed nodes per batch
    input_nodes=('contractor', train_mask),
    shuffle=True,
    num_workers=4,
    pin_memory=True,
)
```

**Key difference from NeighborLoader (used in GraphSAGE Phase 1):** HGTLoader samples a fixed number of nodes **per type** at each hop, rather than a fixed number of neighbors per edge. This ensures balanced representation of all node types in each mini-batch, which is critical because our graph is highly heterogeneous (millions of processes vs. thousands of campaigns).

#### 10.3.5 Implementation with PyTorch Geometric

```python
import torch
import torch.nn.functional as F
from torch_geometric.nn import HGTConv, Linear

class HGTEncoder(torch.nn.Module):
    """
    Heterogeneous Graph Transformer encoder for corruption network detection.

    Uses type-dependent attention over meta-relations to learn
    contextualized representations for each node.

    Args:
        hidden_channels (int): Hidden dimension. Default: 256.
        out_channels (int): Output embedding dimension. Default: 128.
        num_heads (int): Number of attention heads. Default: 8.
        num_layers (int): Number of HGT layers (hops). Default: 2.
        node_types (list[str]): List of node type names.
        edge_types (list[tuple]): List of (src_type, edge_type, dst_type) triplets.
        dropout (float): Dropout probability. Default: 0.3.
    """
    def __init__(
        self,
        hidden_channels: int = 256,
        out_channels: int = 128,
        num_heads: int = 8,
        num_layers: int = 2,
        node_types: list = None,
        edge_types: list = None,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.num_layers = num_layers
        self.dropout = dropout

        # Input projection: one linear layer per node type to map
        # heterogeneous input features to a common hidden dimension
        self.input_projections = torch.nn.ModuleDict()
        for node_type in node_types:
            self.input_projections[node_type] = Linear(-1, hidden_channels)

        # HGT convolution layers
        self.convs = torch.nn.ModuleList()
        for i in range(num_layers):
            conv_out = hidden_channels if i < num_layers - 1 else out_channels
            conv = HGTConv(
                in_channels=hidden_channels if i > 0 else hidden_channels,
                out_channels=conv_out,
                metadata=(node_types, edge_types),
                heads=num_heads,
            )
            self.convs.append(conv)

        # Layer normalization per node type per layer
        self.norms = torch.nn.ModuleList()
        for i in range(num_layers):
            norm_dim = hidden_channels if i < num_layers - 1 else out_channels
            norm_dict = torch.nn.ModuleDict()
            for node_type in node_types:
                norm_dict[node_type] = torch.nn.LayerNorm(norm_dim)
            self.norms.append(norm_dict)

    def forward(self, x_dict, edge_index_dict):
        """
        Forward pass.

        Args:
            x_dict: Dict mapping node_type → feature tensor.
            edge_index_dict: Dict mapping (src_type, edge_type, dst_type) → edge_index.

        Returns:
            Dict mapping node_type → embedding tensor [num_nodes, out_channels].
        """
        # Project input features to common hidden dimension
        h_dict = {}
        for node_type, x in x_dict.items():
            h_dict[node_type] = self.input_projections[node_type](x)

        # HGT message passing layers
        for i, conv in enumerate(self.convs):
            h_dict = conv(h_dict, edge_index_dict)
            # Apply layer norm and activation (except last layer)
            for node_type in h_dict:
                h_dict[node_type] = self.norms[i][node_type](h_dict[node_type])
                if i < self.num_layers - 1:
                    h_dict[node_type] = F.relu(h_dict[node_type])
                    h_dict[node_type] = F.dropout(
                        h_dict[node_type], p=self.dropout, training=self.training
                    )

        return h_dict
```

### 10.4 HGT Hyperparameters

| Hyperparameter | Value | Justification |
|---|---|---|
| `hidden_channels` | 256 | Same as GraphSAGE for fair comparison; fits in 6GB VRAM with FP16 |
| `out_channels` | 128 | Embedding dimension |
| `num_heads` | 8 | Standard for HGT; 256 / 8 = 32 dims per head |
| `num_layers` | 2 | 2-hop neighborhood captures the critical meta-paths; 3 risks over-smoothing |
| `dropout` | 0.3 | Regularization |
| `learning_rate` | 5e-4 | Slightly lower than GraphSAGE due to transformer complexity |
| `batch_size` | 512 | Smaller than GraphSAGE (1024) due to higher per-sample memory from multi-head attention |
| `weight_decay` | 1e-4 | L2 regularization for transformer weights |
| `warmup_epochs` | 5 | Linear LR warmup for transformer stability |
| `epochs` | 150 | More epochs due to slower convergence with attention mechanisms |

### 10.5 HGT VRAM Budget for RTX 2060 (6GB)

```
COMPONENT                              | ESTIMATED VRAM (FP16)
═══════════════════════════════════════ | ═════════════════════
Model parameters (all HGTConv layers)  | ~200 MB
Input projections (5 node types)       | ~50 MB
Mini-batch node features               | ~100 MB (512 seeds × 2-hop sampled)
Attention matrices (8 heads × 2 layers)| ~300 MB
Gradient buffers                       | ~400 MB
Optimizer states (Adam)                | ~400 MB
────────────────────────────────────── | ─────────────────────
TOTAL ESTIMATED                        | ~1.5 GB
────────────────────────────────────── | ─────────────────────
AVAILABLE                              | 6 GB
MARGIN                                 | ~4.5 GB (safe)
```

With FP16 mixed precision, the RTX 2060 has ample margin for HGT training.

### 10.6 Comparison: GraphSAGE vs R-GCN vs HGT for SIP-Graph

| Dimension | GraphSAGE (Phase 1) | R-GCN (Phase 2) | HGT (Phase 3) |
|---|---|---|---|
| **Edge-type awareness** | Implicit via `to_hetero()` | Explicit: separate weights per edge type | Explicit: type-dependent attention + message |
| **Attention mechanism** | None (mean/max aggregation) | None (learned but uniform weights) | Multi-head type-aware attention |
| **Meta-path learning** | Cannot learn meta-paths | Requires manual meta-path definition | Automatic "soft" meta-path discovery |
| **Temporal encoding** | None natively | None natively | Native Relative Temporal Encoding |
| **Scalability** | Excellent (NeighborLoader) | Good (standard mini-batch) | Good (HGSampling, type-aware) |
| **Interpretability** | Low (opaque embeddings) | Medium (per-relation weights) | High (attention weights reveal which relations and neighbors matter most) |
| **Training complexity** | Low | Medium | High |
| **VRAM usage (FP16)** | ~1 GB | ~1.2 GB | ~1.5 GB |
| **Estimated training time** | 2-6 hours | 4-12 hours | 8-24 hours |
| **Best for (SIP-Graph)** | MVP, fast iteration | Explicit edge-type learning | Full heterogeneous corruption pattern discovery |
| **Why choose for SIP-Graph** | Fast to deploy, proves GNN value | Learns financing vs. bidding edge semantics | Discovers novel corruption patterns automatically, temporal awareness |

### 10.7 What HGT Specifically Captures That Others Cannot

For the SIP-Graph corruption detection use case, HGT's advantages are concrete:

**Example 1 — Indirect Political Financing Detection:**
A 2-layer HGT processing the path: `Contractor B ← is_legal_rep_of ← Person A → financed → Campaign Y`
- Layer 1: Person A aggregates information from both Contractor B (through is_legal_rep_of attention) and Campaign Y (through financed attention), with different attention weights for each edge type.
- Layer 2: Contractor B aggregates information from Person A's already-enriched representation (which now contains campaign financing information).
- Result: Contractor B's embedding encodes the political financing signal, even though B never directly financed anything.
- GraphSAGE with `to_hetero()` can technically do this, but with uniform aggregation weights. HGT learns that the "financed" signal should be amplified relative to other neighbor signals.

**Example 2 — Temporal Pattern Detection:**
Consider two contractors:
- Contractor X: financed campaign in 2018, won contract in 2019 (financing BEFORE contract).
- Contractor Z: financed campaign in 2022, won contract in 2019 (financing AFTER contract).
With Relative Temporal Encoding, HGT learns that the X pattern (financing precedes contracting) is more anomalous than the Z pattern. GraphSAGE and R-GCN have no mechanism to capture this temporal ordering.

**Example 3 — Automatic Meta-Path Discovery:**
Consider the unknown meta-path: `Contractor → bid_in → Process ← bid_in ← Contractor2 → contracted_with → Entity`
If this path is predictive of collusion (two co-bidders contracting with the same entity), HGT's multi-head attention can learn to up-weight this pattern across layers, without the researcher needing to define it as a meta-path. HAN and R-GCN require the researcher to explicitly specify which meta-paths to consider.

---

# ══════════════════════════════════════════════════════
# SECTION H: COMPUTATIONAL OPTIMIZATION
# ══════════════════════════════════════════════════════

## 11. Hardware-Specific Optimization Strategy

### 11.1 Target Hardware

| Component | Specification | Main Limitation | Strategy |
|---|---|---|---|
| GPU | NVIDIA RTX 2060 (6GB VRAM) | Limited VRAM for large graphs | Mini-batch training with NeighborLoader/HGTLoader |
| RAM | 90GB DDR3 | Lower bandwidth than DDR4/DDR5 | Full graph in RAM, pin_memory=True |
| CPU | 2× Intel 3GHz (older generation) | Preprocessing throughput | Parallelization with joblib/multiprocessing |

### 11.2 CUDA Configuration

```python
import torch

assert torch.cuda.is_available(), "CUDA not available"
device = torch.device('cuda:0')

torch.backends.cudnn.benchmark = True
torch.backends.cuda.matmul.allow_tf32 = True

# Mixed precision (FP16) — CRITICAL for RTX 2060
from torch.cuda.amp import GradScaler, autocast
scaler = GradScaler()

for batch in loader:
    optimizer.zero_grad()
    with autocast():
        z_dict = model.encode(batch.x_dict, batch.edge_index_dict)
        loss = compute_loss(z_dict, batch)
    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()

    if batch_idx % 50 == 0:
        torch.cuda.empty_cache()
```

### 11.3 DataLoader Configuration

```python
from torch_geometric.loader import NeighborLoader  # Phase 1
# from torch_geometric.loader import HGTLoader     # Phase 3

train_loader = NeighborLoader(
    data,
    num_neighbors={
        ('contractor', 'bid_in', 'process'): [15, 10],
        ('process', 'rev_bid_in', 'contractor'): [15, 10],
        ('person', 'is_legal_rep_of', 'contractor'): [10, 5],
        ('contractor', 'rev_is_legal_rep_of', 'person'): [10, 5],
        ('contractor', 'contracted_with', 'entity'): [10, 5],
        ('entity', 'rev_contracted_with', 'contractor'): [10, 5],
    },
    batch_size=1024,
    input_nodes=('contractor', train_mask),
    shuffle=True,
    num_workers=4,            # Parallelize sampling on CPU
    pin_memory=True,          # Accelerate CPU→GPU transfer (mitigates DDR3)
    drop_last=False,
)
```

### 11.4 CPU Parallelization and RAM Management

- `num_workers=4` or `num_workers=6` in DataLoaders for parallel neighborhood sampling.
- `joblib` with `n_jobs=-1` for CSV preprocessing.
- Chunked loading for CSVs > 1GB with explicit dtypes and `pd.Categorical` for string columns.
- `gc.collect()` after large DataFrame concatenations.

### 11.5 Time Estimates

| Phase | Operation | Estimate | Limiting Resource |
|---|---|---|---|
| Preprocessing | Load and clean CSVs (~12GB total) | 15-30 min | RAM + CPU |
| Preprocessing | Entity resolution (Monitor) | 5-15 min | CPU |
| Construction | Build HeteroData graph | 10-20 min | RAM |
| Training (Phase 1) | GraphSAGE Autoencoder (100 epochs) | 2-6 hours | GPU VRAM |
| Training (Phase 3) | HGT Autoencoder (150 epochs) | 8-24 hours | GPU VRAM |
| Detection | Leiden communities | 5-15 min | CPU + RAM |
| Classification | Train community classifier | < 5 min | CPU |
| **TOTAL MVP (Phase 1)** | | **3-8 hours** | |
| **TOTAL Phase 3 (HGT)** | | **10-26 hours** | |

---

# ══════════════════════════════════════════════════════
# SECTION I: WEB VISUALIZATION — REACT GRAPH EXPLORER
# ══════════════════════════════════════════════════════

## 12. Interactive Graph Explorer

### 12.1 Purpose

Provide investigators from control bodies (Contraloría, Veeduría, Procuraduría) with an interactive web interface where they can:
- Select any **contractor** or **government entity** as an anchor node.
- Visually explore the network neighborhood around that anchor (legal representatives, co-bidders, entities they contract with, campaigns they've financed).
- See **anomaly scores** and **community membership** overlaid on the graph.
- Drill down into suspicious communities.
- Export identified networks for further investigation.

### 12.2 Technology Stack

| Component | Technology | Justification |
|---|---|---|
| Frontend framework | **React** | Consistent with future SIP frontend |
| Graph rendering | **Cytoscape.js** via `react-cytoscapejs` | Purpose-built for network visualization, handles large interactive graphs, supports heterogeneous styling, multiple layouts, and smooth zooming/panning. MIT license. |
| State management | React Context or Zustand | Lightweight state for selected node, filters, and view configuration |
| API communication | Fetch / Axios | REST calls to backend API |
| Backend API | **FastAPI** (Python) | Consistent with SIP backend, serves graph subsets and node details |
| Graph data storage | **NetworkX** in memory + JSON serialization | For serving subgraphs on demand |

**Why Cytoscape.js over D3.js or Sigma.js:**
- Cytoscape.js is purpose-built for graph/network visualization, while D3 is a general-purpose visualization library that requires significantly more code for equivalent graph functionality.
- Cytoscape.js natively supports heterogeneous node and edge types with different visual styles, which maps directly to our 5 node types and 5 edge types.
- The `react-cytoscapejs` wrapper provides seamless React integration.
- Built-in layout algorithms (CoSE for force-directed, concentric for ego-networks, hierarchical for trees) work out of the box.
- For the graph sizes we serve to the frontend (ego-networks of 50-500 nodes), Cytoscape.js handles performance well.

### 12.3 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        REACT FRONTEND                           │
│                                                                 │
│  ┌──────────────┐  ┌────────────────────────┐  ┌─────────────┐│
│  │ Search Panel  │  │  Cytoscape.js Graph    │  │ Detail Panel││
│  │              │  │  (react-cytoscapejs)    │  │             ││
│  │ - Search by  │  │                        │  │ - Node info ││
│  │   contractor │  │  Nodes colored by:     │  │ - Anomaly   ││
│  │   name/NIT   │  │  • type (shape+color)  │  │   score     ││
│  │ - Search by  │  │  • anomaly score       │  │ - Community ││
│  │   entity     │  │    (color intensity)   │  │   features  ││
│  │ - Filter by  │  │  • community membership│  │ - Sanctions ││
│  │   dept/year  │  │    (border color)      │  │ - Financing ││
│  │              │  │                        │  │   crossrefs ││
│  │ - Top anoma- │  │  Edges colored by:     │  │ - Contracts ││
│  │   lous nodes │  │  • type (color+style)  │  │   history   ││
│  │              │  │  • weight (thickness)   │  │             ││
│  └──────────────┘  └────────────────────────┘  └─────────────┘│
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐│
│  │ Community Panel (bottom)                                    ││
│  │ - List of top suspicious communities                       ││
│  │ - Community features (sanctions, financing, co-bidding)    ││
│  │ - Click to focus graph on community subgraph               ││
│  └────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ REST API
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FASTAPI BACKEND                              │
│                                                                  │
│  GET /api/v1/graph/ego/{node_type}/{node_id}                    │
│      → Returns ego-network (1-2 hops) as Cytoscape JSON         │
│      → Query params: hops (1|2), max_nodes (50|100|200|500)     │
│                                                                  │
│  GET /api/v1/graph/community/{community_id}                     │
│      → Returns community subgraph + features                    │
│                                                                  │
│  GET /api/v1/search/contractor?q={name_or_nit}                  │
│      → Returns matching contractors with anomaly scores          │
│                                                                  │
│  GET /api/v1/search/entity?q={name_or_code}                     │
│      → Returns matching entities with stats                      │
│                                                                  │
│  GET /api/v1/anomalies/top?node_type={type}&limit={n}           │
│      → Returns top-N anomalous nodes of given type               │
│                                                                  │
│  GET /api/v1/communities/top?limit={n}                          │
│      → Returns top-N suspicious communities with features        │
│                                                                  │
│  GET /api/v1/financing/crossrefs/{document}                     │
│      → Returns all financing-contract cross-references           │
│         (direct + indirect via legal representatives)            │
│                                                                  │
│  Authentication: Same API Key mechanism as SIP v2.0              │
│  Rate Limiting: slowapi, same configuration as SIP v2.0         │
└─────────────────────────────────────────────────────────────────┘
```

### 12.4 Cytoscape.js Visual Encoding

#### 12.4.1 Node Visual Encoding

| Node Type | Shape | Base Color | Size Encodes |
|---|---|---|---|
| Contractor | Rectangle | Blue (#4A90D9) | log(total_contract_value) |
| Person (Legal Rep) | Ellipse | Green (#5CB85C) | num_companies_represented |
| Process | Diamond | Gray (#95A5A6) | log(official_budget) |
| Government Entity | Hexagon | Orange (#F0AD4E) | annual_contracting_volume |
| Campaign | Triangle | Purple (#9B59B6) | num_donors |

**Anomaly score overlay:** Node border width and color intensity encode anomaly score:
- Score 0.0-0.3: thin border, light color → normal
- Score 0.3-0.7: medium border, yellow tint → moderate anomaly
- Score 0.7-1.0: thick border, red color → high anomaly

**Community overlay:** Nodes in the same community share a background color halo.

#### 12.4.2 Edge Visual Encoding

| Edge Type | Line Style | Color | Label |
|---|---|---|---|
| bid_in | Solid | Blue (#4A90D9) | "Won" if won=True |
| is_legal_rep_of | Dashed | Green (#5CB85C) | — |
| contracted_with | Solid, thick | Orange (#F0AD4E) | Contract value |
| financed | Dotted | Red (#D9534F) | Amount |
| was_sanctioned | Solid, thick | Dark Red (#C0392B) | Sanction type |

#### 12.4.3 Cytoscape.js Stylesheet

```javascript
const graphStylesheet = [
  // Contractor nodes
  {
    selector: 'node[type="contractor"]',
    style: {
      'shape': 'rectangle',
      'background-color': '#4A90D9',
      'label': 'data(label)',
      'width': 'mapData(size, 0, 100, 30, 80)',
      'height': 'mapData(size, 0, 100, 30, 80)',
      'font-size': '10px',
      'text-wrap': 'wrap',
      'text-max-width': '80px',
      'border-width': 'mapData(anomaly_score, 0, 1, 1, 6)',
      'border-color': 'mapData(anomaly_score, 0, 1, #CCCCCC, #FF0000)',
    }
  },
  // Person nodes
  {
    selector: 'node[type="person"]',
    style: {
      'shape': 'ellipse',
      'background-color': '#5CB85C',
      'label': 'data(label)',
      'border-width': 'mapData(anomaly_score, 0, 1, 1, 6)',
      'border-color': 'mapData(anomaly_score, 0, 1, #CCCCCC, #FF0000)',
    }
  },
  // ... (similar for process, entity, campaign)

  // Edge styles
  {
    selector: 'edge[type="financed"]',
    style: {
      'line-style': 'dotted',
      'line-color': '#D9534F',
      'target-arrow-color': '#D9534F',
      'target-arrow-shape': 'triangle',
      'width': 2,
      'curve-style': 'bezier',
    }
  },
  {
    selector: 'edge[type="is_legal_rep_of"]',
    style: {
      'line-style': 'dashed',
      'line-color': '#5CB85C',
      'target-arrow-color': '#5CB85C',
      'target-arrow-shape': 'triangle',
      'width': 1.5,
      'curve-style': 'bezier',
    }
  },
  // ... (similar for bid_in, contracted_with, was_sanctioned)
];
```

### 12.5 React Component Structure

```
src/
├── components/
│   ├── GraphExplorer/
│   │   ├── GraphExplorer.jsx        # Main container component
│   │   ├── CytoscapeGraph.jsx       # Cytoscape.js wrapper using react-cytoscapejs
│   │   ├── SearchPanel.jsx          # Left panel: search by name/NIT/entity
│   │   ├── DetailPanel.jsx          # Right panel: selected node details
│   │   ├── CommunityPanel.jsx       # Bottom panel: community list and features
│   │   ├── FilterControls.jsx       # Filters: department, year, anomaly threshold
│   │   ├── LegendOverlay.jsx        # Visual legend for node/edge types
│   │   └── ExportButton.jsx         # Export current view as PNG or CSV
│   │
│   └── shared/
│       ├── AnomalyBadge.jsx         # Visual badge showing anomaly score
│       ├── RiskIndicator.jsx        # Color-coded risk level indicator
│       └── LoadingSpinner.jsx
│
├── hooks/
│   ├── useGraphData.js              # Fetch and cache ego-network data
│   ├── useSearch.js                 # Debounced search against API
│   └── useCommunities.js            # Fetch and cache community data
│
├── api/
│   └── graphApi.js                  # API client for all graph endpoints
│
├── utils/
│   ├── cytoscapeTransforms.js       # Transform API response to Cytoscape elements
│   └── layoutConfig.js              # Layout configurations (cose, concentric, etc.)
│
└── styles/
    └── graphExplorer.css
```

### 12.6 Key User Interactions

1. **Search and anchor:** Investigator searches for a contractor by name or NIT. The system returns matches with anomaly scores. Clicking a result sets that contractor as the anchor node and loads its ego-network (1-2 hops).

2. **Explore neighborhood:** The graph renders around the anchor node. The investigator can click on any node to see its details in the right panel. Double-clicking a node re-centers the graph on that node (load its ego-network).

3. **Anomaly highlighting:** Nodes with high anomaly scores visually stand out (thick red borders). The investigator can filter to show only nodes above an anomaly threshold.

4. **Community inspection:** If the anchor node belongs to a detected community, the community panel shows the community features and all members. Clicking "Focus on community" loads the full community subgraph.

5. **Financing trail:** For any contractor or person, the detail panel shows all financing-contract cross-references (direct and indirect via legal representatives), with the chain of relationships highlighted in the graph.

6. **Export:** The investigator can export the current graph view as PNG (for reports) or as CSV (list of nodes and edges with all attributes, for further analysis).

### 12.7 Backend API: Ego-Network Extraction

```python
from fastapi import APIRouter, Depends, Query
import networkx as nx

router = APIRouter(prefix="/api/v1/graph")

@router.get("/ego/{node_type}/{node_id}")
async def get_ego_network(
    node_type: str,
    node_id: str,
    hops: int = Query(default=1, ge=1, le=2),
    max_nodes: int = Query(default=200, ge=10, le=500),
    _: str = Depends(verify_api_key)
):
    """
    Returns the ego-network around a given node as Cytoscape-compatible JSON.

    The ego-network includes all nodes within `hops` hops of the anchor node,
    capped at `max_nodes` to prevent overloading the frontend.

    If more nodes exist than max_nodes, the highest-anomaly-score nodes
    are prioritized to ensure the most suspicious actors are always visible.

    Response format (Cytoscape JSON):
    {
        "elements": {
            "nodes": [
                {
                    "data": {
                        "id": "contractor_900123456",
                        "label": "CONSTRUCTORA XYZ SAS",
                        "type": "contractor",
                        "anomaly_score": 0.82,
                        "community_id": 47,
                        "size": 65,
                        ...node features
                    }
                },
                ...
            ],
            "edges": [
                {
                    "data": {
                        "id": "e1",
                        "source": "contractor_900123456",
                        "target": "process_CO1.PCCNTR.12345",
                        "type": "bid_in",
                        "won": true
                    }
                },
                ...
            ]
        },
        "anchor_node_id": "contractor_900123456",
        "total_nodes_available": 342,
        "nodes_returned": 200,
        "truncated": true
    }
    """
    pass  # Implementation extracts subgraph from in-memory NetworkX graph
```

### 12.8 Performance Considerations for Visualization

- **Ego-network cap:** Max 500 nodes per request. Larger networks are sampled (highest anomaly scores prioritized).
- **Lazy loading:** Edges between nodes not in the current view are not loaded. When the user double-clicks a node to re-center, new edges are fetched.
- **Canvas vs SVG:** For ego-networks up to 500 nodes, Cytoscape.js's default canvas rendering is sufficient. For larger visualizations (full community view), consider `cytoscape-webgl-renderer` extension.
- **Layout computation:** CoSE (Compound Spring Embedder) layout runs in the browser. For ego-networks up to 500 nodes, layout computation takes < 2 seconds. Pre-computed layouts are cached in the backend for communities.

---

# ══════════════════════════════════════════════════════
# SECTION J: PROJECT STRUCTURE AND PIPELINE
# ══════════════════════════════════════════════════════

## 13. Project Structure

```
sip_graph/
├── config/
│   ├── settings.py
│   ├── hardware_config.py
│   └── graph_schema.py
│
├── data/
│   ├── loaders/
│   │   ├── secop_loader.py
│   │   ├── rcac_loader.py
│   │   ├── financing_loader.py
│   │   ├── monitor_loader.py
│   │   └── rues_loader.py
│   ├── preprocessing/
│   │   ├── name_normalizer.py
│   │   ├── document_normalizer.py
│   │   ├── feature_encoder.py
│   │   └── temporal_filter.py
│   ├── entity_resolution/
│   │   ├── tfidf_matcher.py
│   │   ├── validation_rules.py
│   │   └── export_for_review.py
│   ├── graph_builder/
│   │   ├── node_builder.py
│   │   ├── edge_builder.py
│   │   ├── hetero_graph.py
│   │   └── financing_crosser.py
│   └── artifacts/
│       ├── graph.pt
│       ├── entity_resolution_matches.csv
│       ├── entity_resolution_stats.json
│       ├── node_id_mappings.json
│       └── preprocessing_metadata.json
│
├── models/
│   ├── encoders/
│   │   ├── sage_encoder.py          # Phase 1: GraphSAGE
│   │   ├── rgcn_encoder.py          # Phase 2: R-GCN
│   │   └── hgt_encoder.py           # Phase 3: HGT
│   ├── decoder.py
│   ├── autoencoder.py
│   ├── anomaly_scorer.py
│   ├── community_detector.py
│   ├── community_features.py
│   ├── community_classifier.py
│   └── artifacts/
│       ├── autoencoder.pt
│       ├── embeddings.pt
│       ├── anomaly_scores.pt
│       ├── communities.json
│       ├── community_classifier.pkl
│       └── training_metadata.json
│
├── api/
│   ├── app.py                       # FastAPI application
│   ├── auth.py                      # API Key validation (same as SIP v2.0)
│   ├── routes_graph.py              # Graph exploration endpoints
│   ├── routes_search.py             # Search endpoints
│   ├── routes_communities.py        # Community endpoints
│   ├── routes_financing.py          # Financing cross-reference endpoints
│   ├── schemas.py                   # Pydantic models
│   ├── graph_store.py               # In-memory NetworkX graph for serving
│   └── cytoscape_serializer.py      # Convert internal graph to Cytoscape JSON
│
├── frontend/                        # React application
│   ├── package.json
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── GraphExplorer/
│   │   │   └── shared/
│   │   ├── hooks/
│   │   ├── api/
│   │   ├── utils/
│   │   └── styles/
│   └── README.md
│
├── analysis/
│   ├── anomaly_analysis.py
│   ├── community_analysis.py
│   ├── financing_analysis.py
│   └── validation.py
│
├── optimization/
│   ├── cuda_setup.py
│   ├── memory_manager.py
│   └── parallel_processing.py
│
├── tests/
│   ├── test_name_normalizer.py
│   ├── test_entity_resolution.py
│   ├── test_graph_builder.py
│   ├── test_temporal_filter.py
│   ├── test_autoencoder.py
│   ├── test_community_detector.py
│   ├── test_financing_crosser.py
│   ├── test_api_graph.py
│   └── test_cytoscape_serializer.py
│
├── notebooks/
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

## 14. Tech Stack

| Component | Package | Min Version | Purpose |
|---|---|---|---|
| Runtime | `python` | 3.12 | Consistent with SIP v2.0 |
| GNN | `torch` | 2.1+ | Deep learning framework |
| GNN | `torch-geometric` | 2.4+ | GNN library (SAGEConv, HGTConv, to_hetero, NeighborLoader, HGTLoader) |
| GNN | `torch-scatter` | 2.1+ | PyG dependency |
| GNN | `torch-sparse` | 0.6+ | PyG dependency |
| Graphs | `igraph` | 0.11+ | Community detection backend |
| Graphs | `leidenalg` | 0.10+ | Leiden algorithm |
| Graphs | `networkx` | 3.1+ | In-memory graph for API serving + visualization |
| Data | `pandas` | 2.0+ | Tabular processing |
| Data | `numpy` | 1.24+ | Numerical operations |
| ML | `scikit-learn` | 1.3+ | TF-IDF, community classifier, metrics |
| API | `fastapi` | 0.100+ | REST server |
| API | `uvicorn` | 0.23+ | ASGI server |
| API | `pydantic` | 2.0+ | Request/response schemas |
| API | `slowapi` | 0.1.9+ | Rate limiting |
| Parallelism | `joblib` | 1.3+ | CPU parallelization |
| Frontend | `react` | 18+ | UI framework |
| Frontend | `react-cytoscapejs` | 2.0+ | Cytoscape.js React wrapper |
| Frontend | `cytoscape` | 3.25+ | Graph visualization engine |
| Testing | `pytest` | 7.0+ | Tests |

---

## 15. Implementation Roadmap

### Phase 1: Data Loading + Preprocessing (weeks 1-2)

| Task | Module | Acceptance Criteria |
|---|---|---|
| Load large SECOP CSVs | `secop_loader.py` | procesos_SECOP.csv (5.3GB) and ofertas_proceso_SECOP.csv (3.4GB) loaded in < 10 min with dtype optimization |
| Name normalization | `name_normalizer.py` | "  García   López, María " → "GARCIA LOPEZ MARIA". Test with 20+ edge cases |
| Document normalization | `document_normalizer.py` | NIT with dots/dashes → digits only. CC with prefix → number only |
| Legal representative extraction | `secop_loader.py` | DataFrame of (representative_doc, company_doc) extracted from proveedores_registrados.csv |
| CUDA configuration | `cuda_setup.py` | RTX 2060 detected. Mixed precision functional |
| Parallel configuration | `parallel_processing.py` | Cores detected. joblib functional with n_jobs=-1 |

### Phase 2: Entity Resolution (weeks 2-3)

| Task | Module | Acceptance Criteria |
|---|---|---|
| TF-IDF matching | `tfidf_matcher.py` | Full Monitor Ciudadano matching. Match rate > 50% |
| Post-match validation | `validation_rules.py` | Person type/legal entity rules applied |
| Export for review | `export_for_review.py` | CSV with medium-confidence matches generated |

### Phase 3: Graph Construction (weeks 3-4)

| Task | Module | Acceptance Criteria |
|---|---|---|
| Nodes with features | `node_builder.py` | 5 node types built. Features normalized. No NaN |
| Edges with temporal control | `edge_builder.py` | 5 edge types. Test: edge with date > as_of_date does NOT appear |
| Extended financing cross-reference | `financing_crosser.py` | Level 1 (direct) and Level 2 (legal rep) implemented |
| HeteroData graph | `hetero_graph.py` | graph.pt generated. Validation: num_nodes and num_edges match expected |

### Phase 4: Model Training — Stage 1 (weeks 4-6)

| Task | Module | Acceptance Criteria |
|---|---|---|
| GraphSAGE encoder | `sage_encoder.py` | Forward pass without errors on batch of 1024. VRAM < 4GB with FP16 |
| Autoencoder complete | `autoencoder.py` | Training loop functional. Loss decreases. Early stopping implemented |
| Anomaly scores | `anomaly_scorer.py` | Scores [0,1] for all nodes. Non-trivial distribution |
| Basic validation | `validation.py` | Monitor Ciudadano nodes have avg anomaly score > global median |

### Phase 5: Community Detection — Stage 2 (weeks 6-7)

| Task | Module | Acceptance Criteria |
|---|---|---|
| Leiden detection | `community_detector.py` | Communities detected. Reasonable size distribution |
| Community features | `community_features.py` | All CommunityFeatures dataclass fields computed without errors |
| Classifier | `community_classifier.py` | AP (Average Precision) > 0.3 in cross-validation |

### Phase 6: API + Frontend (weeks 7-10)

| Task | Module | Acceptance Criteria |
|---|---|---|
| Graph API endpoints | `routes_graph.py` | Ego-network endpoint returns valid Cytoscape JSON in < 500ms |
| Search endpoints | `routes_search.py` | Search by name/NIT returns results in < 200ms |
| Cytoscape serializer | `cytoscape_serializer.py` | Subgraph → Cytoscape JSON with all visual encoding attributes |
| React graph explorer | `frontend/` | Select contractor → see ego-network. Click node → see details. Anomaly colors working |
| Community panel | `frontend/` | Top communities listed. Click → focus graph on community |
| Export functionality | `frontend/` | PNG export of current view. CSV export of visible nodes/edges |

### Phase 7: HGT Upgrade (weeks 11-14)

| Task | Module | Acceptance Criteria |
|---|---|---|
| HGT encoder implementation | `hgt_encoder.py` | Forward pass on HeteroData. VRAM < 3GB with FP16 |
| HGT autoencoder training | `autoencoder.py` | Converges. Loss < GraphSAGE loss (improvement) |
| Attention weight extraction | `hgt_encoder.py` | Per-edge-type attention weights extractable for interpretability |
| Comparative evaluation | `validation.py` | HGT anomaly scores have higher correlation with Monitor Ciudadano than GraphSAGE |
| RTE integration | `hgt_encoder.py` | Temporal encoding active for timestamped edges |

### Phase 8: Analysis + Validation (weeks 14-16)

| Task | Module | Acceptance Criteria |
|---|---|---|
| Anomaly analysis | `anomaly_analysis.py` | Top-100 anomalous nodes exported with context |
| Community analysis | `community_analysis.py` | Top-20 suspicious communities exported with members and visualization |
| Financing analysis | `financing_analysis.py` | Direct and indirect cross-references tabulated |
| Monitor validation | `validation.py` | Report: what % of Monitor actors are in top-suspicious communities |
| Documentation | `README.md` | Setup, usage, results interpretation |

---

## 16. Open Questions and Pending Decisions

| # | Question | Impact | Deadline |
|---|---|---|---|
| 1 | How many Monitor Ciudadano actors can be matched with high confidence? | Determines weak label quality | Phase 2 (week 3) |
| 2 | Is the legal representative in proveedores_registrados.csv always current or is there historical data? | If only current, temporal dimension of representation is lost | Phase 1 (week 1) |
| 3 | Does the financing database include both natural persons and legal entities as donors? | Determines if there are `financed` edges from both node types | Phase 1 (week 1) |
| 4 | What is the temporal period covered by the financing database? | Affects how many campaigns/periods can be modeled | Phase 1 (week 1) |
| 5 | Is manual review of medium-confidence matches required before using as labels? | If yes, there's a human dependency before Phase 5 | Phase 2 (week 3) |
| 6 | What anomaly score threshold defines "anomalous" for reporting to control bodies? | Post-training calibration | Phase 8 (week 15) |
| 7 | Leiden resolution parameter: prefer many small communities or fewer large ones? | Affects analysis granularity | Phase 5 (week 7) |
| 8 | Should the frontend be deployed as a separate service or bundled with the backend? | Deployment architecture | Phase 6 (week 8) |

---

## 17. Out of Scope (MVP)

- Connection to SIP XGBoost pipeline
- Temporal Graph Networks (dynamic graphs with edge timestamps as native feature — different from RTE)
- Graph explanation / embedding interpretability beyond attention weights (post-MVP)
- Automatic retraining
- Level 3+ financing cross-reference via legal representatives (only Levels 1 and 2 in MVP)
- Integration with Fiscalía data (municipal aggregates, not contract-level)
- NLP processing of contract object descriptions
- Real-time streaming graph updates
- Mobile-responsive frontend
