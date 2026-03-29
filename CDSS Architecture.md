# CDSS Architecture — Intelligent Clinical Decision Support with Agentic RAG on Azure

> [!IMPORTANT]
> This document is the **design-target architecture** (future-state blueprint), not the strict current implementation manifest.
> For the validated implemented state, refer to:
> - [README.md](./README.md)
> - [docs/architecture.md](./docs/architecture.md)

# Intelligent Clinical Decision Support System (CDSS)

## Comprehensive Architecture Design with Agentic RAG on Azure

**Version:** 1.0 **Date:** 2026-02-20 **Author:** Cipher (Architecture Research)

---

## Table of Contents

1. Executive Summary
2. Architecture Overview
3. Component Breakdown
4. Data Flow — Patient Query Journey
5. RAG Pipeline Design
6. Agentic Orchestration Design
7. Data Sources Design
8. Cosmos DB Schema Design
9. Security & Compliance
10. Tech Stack
11. Implementation Phases
12. Challenges & Mitigations
13. References

---

## 1. Executive Summary

This document presents a comprehensive architecture for an **Intelligent Clinical Decision Support System (CDSS)** built on Azure, leveraging Agentic RAG (Retrieval-Augmented Generation) with multi-agent orchestration. The system ingests patient records, medical literature, treatment protocols, and drug interaction databases to produce evidence-based clinical recommendations with full citation trails.

### Key Improvements Over Initial Design

| Area | Initial Design | Improved Design |
| --- | --- | --- |
| Orchestration | Single "Agentic AI Orchestrator" | Multi-agent system with specialized clinical agents (Patient History, Drug Safety, Literature, Protocol, Synthesis) |
| Data Sources | 4 static sources | 7 sources including FHIR/EHR, OpenFDA, RxNorm, DrugBank, and real-time PubMed |
| Document Processing | Not specified | Azure Document Intelligence with medical-specific custom models + Text Analytics for Health NER |
| Vector Storage | Not specified | Cosmos DB with DiskANN vector index, Float16 embeddings, hybrid search + semantic reranking |
| Safety Layer | Not specified | Dedicated Drug Safety Agent + Clinical Guardrails Agent with hallucination detection |
| Compliance | Not specified | Full HIPAA architecture: Private Link, RBAC, audit logging, PHI de-identification pipeline |
| Interoperability | Not specified | Azure Health Data Services FHIR R4 integration for EHR interoperability |
| Evaluation | Not specified | RAGAS framework + healthcare-specific accuracy benchmarks |

---

## 2. Architecture Overview

### High-Level Architecture (Improved)

```
                            ┌─────────────────────────────────────────────────────┐
                            │              AZURE AI FOUNDRY                       │
                            │         (Foundry Agent Service Runtime)             │
                            └──────────────────────┬──────────────────────────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────────┐
                    │                              │                                  │
                    ▼                              ▼                                  ▼
           ┌─────────────────┐            ┌──────────────────┐               ┌───────────────────┐
           │   API Gateway   │            │  Azure Front Door│               │  Azure APIM       │
           │  (HTTPS/WSS)    │            │  (WAF + CDN)     │               │  (Rate Limiting)  │
           └────────┬────────┘            └──────────────────┘               └───────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                              ORCHESTRATOR AGENT (Meta-Agent)                             │
│                                                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────┐   │
│  │  Query      │  │  Session     │  │  Context     │  │  Response  │  │  Guardrails  │   │
│  │  Planner    │  │  Manager     │  │  Assembler   │  │ Synthesizer│  │  Agent       │   │
│  └──────┬──────┘  └──────────────┘  └──────────────┘  └────────────┘  └──────────────┘   │
│         │                                                                                │
│         ▼                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐    │
│  │                     SPECIALIZED CLINICAL AGENTS                                  │    │
│  │                                                                                  │    │
│  │  ┌──────────────┐  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │    │
│  │  │  Patient     │  │  Medical     │   │  Protocol    │   │  Drug Safety │        │    │
│  │  │  History     │  │  Literature  │   │  Agent       │   │  Agent       │        │    │
│  │  │  Agent       │  │  Agent       │   │              │   │              │        │    │
│  │  └──────┬───────┘  └──────┬───────┘   └──────┬───────┘   └──────┬──────-┘        │    │
│  │         │                 │                  │                  │                │    │
│  └─────────┼─────────────────┼──────────────────┼──────────────────┼────────────────┘    │
│            │                 │                  │                  │                     │
└────────────┼─────────────────┼──────────────────┼──────────────────┼─────────────────────┘
             │                 │                  │                  │
             ▼                 ▼                  ▼                  ▼
┌─────────────────┐ ┌──────────────────┐ ┌────────────────┐ ┌───────────────────────┐
│  AZURE AI       │ │  PubMed API +    │ │  Azure Blob    │ │  Drug Interaction     │
│  SEARCH         │ │  PubMed Central  │ │  Storage       │ │  Layer                │
│                 │ │                  │ │                │ │                       │
│ Patient Records │ │ E-Utilities API  │ │ Treatment PDFs │ │ ┌───────────────────┐ │
│ Clinical Notes  │ │ Cached Abstracts │ │ Guidelines     │ │ │ DrugBank API      │ │
│ Lab Results     │ │ Full-Text Index  │ │ SOPs           │ │ │ OpenFDA API       │ │
│ (Hybrid Index)  │ │                  │ │ (AI Search)    │ │ │ RxNorm API        │ │
└────────┬────────┘ └──────────────────┘ └────────────────┘ │ │ Azure SQL DB      │ │
         │                                                  │ └───────────────────┘ │
         │                                                  └───────────────────────┘
         ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                            AZURE DOCUMENT INTELLIGENCE                                │
│                                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │  Layout      │  │  Custom      │  │  Health Ins  │  │  Text Analytics          │   │
│  │  Analysis    │  │  Medical     │  │  Card Model  │  │  for Health (NER)        │   │
│  │              │  │  Models      │  │              │  │  SNOMED, ICD-10, UMLS    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              AZURE COSMOS DB (NoSQL)                                  │
│                                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐    │
│  │  Patient     │  │  Conversation│  │  Embedding   │  │  Audit Log              │    │
│  │  Profiles    │  │  History     │  │  Cache       │  │  Container              │    │
│  │  Container   │  │  Container   │  │  Container   │  │                         │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────────────────┘    │
└───────────────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│    AZURE HEALTH DATA SERVICES                                                         │
│                                                                                       │
│  ┌──────────────────────────────────────────┐  ┌──────────────────────────────────┐   │
│  │  FHIR R4 Service (Patient, Observation,  │  │  DICOM Service                   │   │
│  │  MedicationRequest, Condition, etc.)     │  │  (Medical Imaging)               │   │
│  └──────────────────────────────────────────┘  └──────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### Network Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     AZURE VIRTUAL NETWORK                           │
│                                                                     │
│  ┌──────────────────────┐     ┌──────────────────────┐              │
│  │  App Subnet          │     │  Data Subnet         │              │
│  │                      │     │                      │              │
│  │  • App Service       │     │ • Cosmos DB (PvtLink)│              │
│  │  • Azure Functions   │◄──► │ • AI Search (PvtLink)│              │
│  │  • Container Apps    │     │ • SQL DB (PvtLink)   │              │
│  │                      │     │ • Blob (PvtLink)     │              │
│  └──────────────────────┘     └──────────────────────┘              │
│                                                                     │
│  ┌──────────────────────┐     ┌──────────────────────┐              │
│  │  AI Subnet           │     │  Integration Subnet  │              │
│  │                      │     │                      │              │
│  │  • AI Foundry        │     │  • API Management    │              │
│  │  • Document Intel    │     │  • Azure Front Door  │              │
│  │  • OpenAI Endpoint   │     │  • Health Data Svc   │              │
│  └──────────────────────┘     └──────────────────────┘              │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │  Monitoring: Azure Monitor + Log Analytics + App Insights│       │
│  └──────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Breakdown

### 3.1 Azure AI Foundry (Orchestration Layer)

| Aspect | Detail |
| --- | --- |
| **Role** | Central orchestration runtime for all AI agents, model hosting, prompt management, and evaluation |
| **Azure Service** | Azure AI Foundry + Foundry Agent Service |
| **Why** | GA multi-agent orchestration with MCP support, built-in content safety, persistent memory, and tool integration. Only platform with both GPT-4o and Claude Sonnet 4.5 access. Healthcare Agent Orchestrator available in Agent Catalog. |
| **Model Selection** | GPT-4o for clinical reasoning (primary), GPT-4o-mini for routing/classification, text-embedding-3-large for embeddings |
| **Key Features** | Agent-to-Agent (A2A) protocol, MCP toolkit, Foundry Tools for enterprise connectors, built-in evaluation framework |

### 3.2 Azure AI Search (Knowledge Retrieval)

| Aspect | Detail |
| --- | --- |
| **Role** | Primary vector + keyword search engine for patient records, treatment protocols, and cached medical literature |
| **Azure Service** | Azure AI Search (Standard S2 tier minimum for healthcare scale) |
| **Why** | Hybrid search (BM25 + vector) with semantic reranking outperforms pure vector search by 10-20% on relevance benchmarks. Integrated vectorization eliminates separate embedding pipeline. |
| **Index Strategy** | 3 separate indexes: `patient-records`, `treatment-protocols`, `medical-literature-cache` |
| **Search Mode** | Hybrid (keyword + vector) with semantic ranker L2 for all queries |

### 3.3 Azure Document Intelligence (Document Ingestion)

| Aspect | Detail |
| --- | --- |
| **Role** | Extract structured data from medical PDFs (lab reports, prescriptions, discharge summaries, radiology reports) |
| **Azure Service** | Azure Document Intelligence (v4.0) + Text Analytics for Health |
| **Why** | Layout analysis preserves document structure (tables, headers, sections). Custom models achieve >95% accuracy on medical forms. Text Analytics for Health adds medical NER (SNOMED-CT, ICD-10, UMLS, RxNorm codes). |
| **Models Used** | Prebuilt Layout model (general documents), Custom model (lab reports), Health Insurance Card model, + Text Analytics for Health NER post-processing |

### 3.4 Azure Cosmos DB (State & Vector Store)

| Aspect | Detail |
| --- | --- |
| **Role** | Store patient embeddings, conversation history, session state, audit logs, and agent memory |
| **Azure Service** | Azure Cosmos DB for NoSQL |
| **Why** | Native vector search with DiskANN index (sub-10ms latency), Float16 support (50% storage reduction), hybrid search, semantic reranking (preview), change feed for real-time sync, global distribution, and 99.999% SLA. HIPAA BAA eligible. |
| **Capacity** | Autoscale provisioned throughput (400-40,000 RU/s), analytical store enabled |

### 3.5 Azure Health Data Services (FHIR Interoperability)

| Aspect | Detail |
| --- | --- |
| **Role** | Standard interface for EHR data exchange using FHIR R4 |
| **Azure Service** | Azure Health Data Services — FHIR Service |
| **Why** | HL7 FHIR R4 compliance for interoperability with Epic, Cerner, and other EHR systems. Converts legacy HL7v2 messages. Required for CMS Interoperability rules. |
| **Key Resources** | Patient, Observation, MedicationRequest, Condition, AllergyIntolerance, DiagnosticReport |

### 3.6 PubMed Integration (Medical Literature)

| Aspect | Detail |
| --- | --- |
| **Role** | Real-time access to 36+ million biomedical citations |
| **APIs Used** | NCBI E-Utilities (ESearch, EFetch, ELink), PubMed Central OA API |
| **Why** | Authoritative, free, comprehensive biomedical literature. Supports structured queries with MeSH terms. Full-text available for PMC Open Access subset. |

### 3.7 Drug Interaction Layer

| Aspect | Detail |
| --- | --- |
| **Role** | Check drug-drug, drug-allergy, drug-condition interactions with severity classification |
| **Services** | DrugBank Clinical API (primary, 1.3M+ interactions), OpenFDA Drug API (adverse events, labeling), RxNorm API (normalization), Azure SQL DB (local cache) |
| **Why** | DrugBank provides severity classification (minor/moderate/major) with evidence levels. OpenFDA adds real-world adverse event data. RxNorm normalizes drug identifiers across systems. |

### 3.8 Azure OpenAI Service (LLM Backend)

| Aspect | Detail |
| --- | --- |
| **Role** | Foundation model inference for clinical reasoning, synthesis, and summarization |
| **Azure Service** | Azure OpenAI Service (within AI Foundry) |
| **Models** | GPT-4o (128K context, clinical reasoning), GPT-4o-mini (routing, classification, extraction), text-embedding-3-large (3072 dimensions, medical embeddings) |
| **Why** | HIPAA-eligible for text-based inputs, PHI can be processed with BAA, highest reasoning capability for medical synthesis |

---

## 4. Data Flow — Patient Query Journey

### Step-by-Step Flow

```
STEP 1: QUERY INGESTION
━━━━━━━━━━━━━━━━━━━━━
Clinician → API Gateway (Azure APIM) → Authentication (Azure AD B2C)
                                        │
                                        ▼
                                   Rate Limiting + PHI Detection
                                        │
                                        ▼
                               Orchestrator Agent receives query
                               + session context from Cosmos DB

STEP 2: QUERY PLANNING (Orchestrator Agent)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Query Planner decomposes the clinical question:
  │
  ├─ Classify query type (diagnosis, treatment, drug check, general)
  ├─ Identify required data sources
  ├─ Determine which agents to invoke (parallel vs sequential)
  ├─ Extract patient identifiers, drug names, conditions (NER)
  └─ Generate sub-queries for each agent

STEP 3: PARALLEL AGENT DISPATCH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Orchestrator dispatches to agents concurrently:
  │
  ├─► Patient History Agent
  │     └─ Azure AI Search (patient-records index)
  │     └─ FHIR Service (real-time EHR pull)
  │     └─ Returns: patient timeline, active meds, allergies, labs
  │
  ├─► Medical Literature Agent
  │     └─ PubMed E-Utilities (ESearch → EFetch)
  │     └─ Azure AI Search (medical-literature-cache index)
  │     └─ Returns: top-k relevant abstracts/papers with citations
  │
  ├─► Protocol Agent
  │     └─ Azure AI Search (treatment-protocols index)
  │     └─ Returns: matching clinical guidelines, SOPs, care pathways
  │
  └─► Drug Safety Agent
        └─ DrugBank API (DDI check for active + proposed meds)
        └─ OpenFDA (adverse event signals)
        └─ RxNorm (drug normalization)
        └─ Returns: interaction alerts with severity + evidence

STEP 4: CONTEXT ASSEMBLY
━━━━━━━━━━━━━━━━━━━━━━━
Context Assembler receives all agent outputs:
  │
  ├─ Merges patient context + literature + protocols + drug safety
  ├─ De-duplicates and ranks byrelevance
  ├─ Trims to fit LLM context window (128K tokens)
  ├─ Preserves citation metadata for every piece of evidence
  └─ Constructs structured prompt with role-specific instructions

STEP 5: CLINICAL SYNTHESIS (GPT-4o)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Response Synthesizer Agent:
  │
  ├─ Generates clinical recommendation with structured output:
  │     {
  │       "assessment": "...",
  │       "recommendation": "...",
  │       "evidence_summary": [...],
  │       "drug_alerts": [...],
  │       "confidence_score": 0.87,
  │       "citations": [...]
  │     }
  │
  └─ Applies chain-of-thought medical reasoning

STEP 6: GUARDRAILS & VALIDATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Guardrails Agent validates output:
  │
  ├─ Hallucination check: every claim must have a citation
  ├─ Drug safety check: no recommendation contradicts DDI alerts
  ├─ Scope check: flags if recommendation exceeds system capability
  ├─ Disclaimer injection: "This is decision support, not a diagnosis"
  ├─ Content safety: Azure AI Content Safety filter
  └─ Confidence threshold: if < 0.6, escalate to "insufficient evidence"

STEP 7: RESPONSE DELIVERY + LOGGING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  │
  ├─ Formatted response → API → Clinician UI
  ├─ Full interaction → Cosmos DB (conversation_history container)
  ├─ Audit trail → Cosmos DB (audit_log container) + Log Analytics
  ├─ Feedback loop → Clinician can rate/correct recommendation
  └─ Metrics → Application Insights (latency, token usage, accuracy)
```

### Latency Budget

| Step | Target Latency | Notes |
| --- | --- | --- |
| Authentication + routing | <100ms | Azure AD cached tokens |
| Query planning | <500ms | GPT-4o-mini classification |
| Patient History retrieval | <800ms | AI Search hybrid query |
| PubMed API call | <2s | Cached results preferred |
| Protocol retrieval | <500ms | AI Search pre-indexed |
| Drug interaction check | <1s | DrugBank API + local cache |
| Context assembly | <200ms | In-memory merging |
| LLM synthesis | <5s | GPT-4o streaming |
| Guardrails check | <1s | GPT-4o-mini validation |
| **Total (P95)** | **<8-10s** | **Acceptable for clinical workflows** |

---

## 5. RAG Pipeline Design

### 5.1 Chunking Strategy

Medical documents require a **domain-aware chunking strategy** that preserves clinical meaning:

```
┌──────────────────────────────────────────────────────────────┐
│                    CHUNKING PIPELINE                         │
│                                                              │
│  Raw PDF                                                     │
│    │                                                         │
│    ▼                                                         │
│  Document Intelligence (Layout Analysis)                     │
│    │                                                         │
│    ├─ Detect: Headers, Sections, Tables, Paragraphs          │
│    ├─ Extract: Structured fields (patient, dates, results)   │
│    └─ Classify: Document type (lab report, prescription)     │
│    │                                                         │
│    ▼                                                         │
│  Text Analytics for Health (NER)                             │
│    │                                                         │
│    ├─ Tag: Diseases (ICD-10), Medications (RxNorm)           │
│    ├─ Tag: Procedures (CPT), Lab tests (LOINC)               │
│    └─ Tag: Dosages, Anatomical sites, Temporal expressions   │
│    │                                                         │
│    ▼                                                         │
│  Semantic Chunking (Document Layout Skill)                   │
│    │                                                         │
│    ├─ Chunk by clinical section (not arbitrary token count)  │
│    ├─ Target: 512-1024 tokens per chunk                      │
│    ├─ Overlap: 128 tokens (preserves cross-section context)  │
│    ├─ Metadata per chunk:                                    │
│    │   - document_id, section_type, page_number              │
│    │   - patient_id, date, medical_codes[]                   │
│    │   - confidence_score                                    │
│    └─ Special handling for tables (keep as structured JSON)  │
│    │                                                         │
│    ▼                                                         │
│  Embedding (text-embedding-3-large, 3072 dims)               │
│    │                                                         │
│    └─ Store in Azure AI Search + Cosmos DB                   │
└──────────────────────────────────────────────────────────────┘
```

#### Chunking Rules by Document Type

| Document Type | Chunking Strategy | Chunk Size | Special Handling |
| --- | --- | --- | --- |
| Lab Reports | By test section (CBC, metabolic panel, etc.) | 256-512 tokens | Preserve table structure as JSON, include reference ranges |
| Prescriptions | Whole document (usually small) | Full document | Extract: drug, dose, frequency, duration, prescriber |
| Discharge Summaries | By clinical section (HPI, Assessment, Plan) | 512-1024 tokens | Heavy overlap (256 tokens) between sections |
| Radiology Reports | Findings + Impression as separate chunks | 256-512 tokens | Link findings chunk to impression chunk via metadata |
| Clinical Guidelines | By recommendation/evidence level | 512-1024 tokens | Preserve recommendation strength (Grade A/B/C/D) |
| PubMed Abstracts | Structured sections (Background, Methods, Results, Conclusion) | Full abstract (~300-500 tokens) | Include MeSH terms and PMID as metadata |

### 5.2 Embedding Strategy

| Parameter | Value | Rationale |
| --- | --- | --- |
| **Model** | `text-embedding-3-large` | 3072 dimensions, best performance on medical benchmarks. Supports dimension reduction (e.g., 1536 or 768) for cost optimization |
| **Storage Format** | Float16 | 50% storage reduction vs Float32, <1% accuracy loss, supported natively by Cosmos DB |
| **Batch Size** | 16 documents per API call | Balance throughput vs latency |
| **Dimension** | 3072 (full) for patient records, 1536 (reduced) for literature cache | Critical data gets full fidelity |

### 5.3 Retrieval Strategy

**Three-stage retrieval with fallback:**

```
Stage 1: Hybrid Search (Azure AI Search)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Query → [Vector Search (cosine similarity)] + [BM25 Keyword Search]
                        │                              │
                        └──────────┬───────────────────┘
                                   ▼
                        Reciprocal Rank Fusion (RRF)
                                   │
                                   ▼
                        Top-50 candidates

Stage 2: Semantic Reranking
━━━━━━━━━━━━━━━━━━━━━━━━━━
  Top-50 → Azure AI Search Semantic Ranker (L2)
                        │
                        ▼
                 Reranked Top-20 with semantic scores

Stage 3: Agent-Level Relevance Filtering
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Top-20 → LLM-based relevance scoring (GPT-4o-mini)
                        │
                        ├─ Is this chunk relevant to the specific clinical question?
                        ├─ Score 0-1 relevance
                        └─ Filter: keep only score > 0.7
                                   │
                                   ▼
                        Final Top-K (typically 5-10 chunks per source)
```

### 5.4 Cross-Source Fusion

When multiple data sources return results, the Context Assembler performs **weighted cross-source fusion**:

```python
# Pseudo-code for cross-source fusion
source_weights = {
    "patient_records": 1.0,     # Highest: patient-specific data
    "drug_interactions": 0.95,  # Critical: safety-first
    "treatment_protocols": 0.85, # High: institutional guidelines
    "medical_literature": 0.75,  # Important: evidence base
    "cached_pubmed": 0.70       # Useful: supplementary
}

# Final context = weighted interleave of top-k results from each source
# Patient data always appears first in context window
# Drug safety alerts are injected as system-level constraints
```

---

## 6. Agentic Orchestration Design

### 6.1 Agent Architecture

The system uses **Microsoft Agent Framework** running on **Foundry Agent Service** with a supervisor pattern:

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (Supervisor Agent)          │
│                                                             │
│  Model: GPT-4o                                              │
│  Role: Decompose queries, dispatch agents, resolve conflicts│
│  Memory: Cosmos DB (session state + long-term patient ctx)  │
│  Tools: Agent dispatcher, session manager, escalation       │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                  AGENT REGISTRY                       │  │ 
│  │                                                       │  │
│  │  ┌────────────────────────────────────────────────┐   │  │
│  │  │  PATIENT HISTORY AGENT                         │   │  │
│  │  │  Model: GPT-4o-mini                            │   │  │
│  │  │  Tools:                                        │   │  │
│  │  │  - azure_ai_search(index="patient-records")    │   │  │
│  │  │  - fhir_query(resource_type, patient_id)       │   │  │
│  │  │  - cosmos_db_read(container="patient_profiles")│   │  │
│  │  │  Output: PatientContext {                      │   │  │
│  │  │    demographics, conditions, medications,      │   │  │
│  │  │    allergies, recent_labs, timeline            │   │  │
│  │  │  }                                             │   │  │
│  │  └────────────────────────────────────────────────┘   │  │
│  │                                                       │  │
│  │  ┌────────────────────────────────────────────────┐   │  │
│  │  │  MEDICAL LITERATURE AGENT                      │   │  │
│  │  │  Model: GPT-4o                                 │   │  │
│  │  │  Tools:                                        │   │  │
│  │  │    - pubmed_search(query, max_results, mesh)   │   │  │
│  │  │    - pubmed_fetch(pmid_list)                   │   │  │
│  │  │    - azure_ai_search(index="literature-cache") │   │  │
│  │  │ Output: LiteratureEvidence {                   │   │  │
│  │  │    papers[], evidence_level, summary,          │   │  │
│  │  │    contradictions[], consensus_strength        │   │  │
│  │  │  }                                             │   │  │
│  │  └────────────────────────────────────────────────┘   │  │
│  │                                                       │  │
│  │  ┌────────────────────────────────────────────────┐   │  │
│  │  │  PROTOCOL AGENT                                │   │  │
│  │  │  Model: GPT-4o-mini                            │   │  │
│  │  │  Tools:                                        │   │  │
│  │  │    - azure_ai_search(index="protocols")        │   │  │
│  │  │    - blob_storage_read(container="guidelines") │   │  │
│  │  │  Output: ProtocolMatch {                       │   │  │
│  │  │    guideline_name, version, recommendation,    │   │  │
│  │  │    evidence_grade, contraindications           │   │  │
│  │  │  }                                             │   │  │
│  │  └────────────────────────────────────────────────┘   │  │
│  │                                                       │  │
│  │  ┌────────────────────────────────────────────────┐   │  │
│  │  │  DRUG SAFETY AGENT                             │   │  │
│  │  │  Model: GPT-4o                                 │   │  │
│  │  │  Tools:                                        │   │  │
│  │  │    - drugbank_ddi_check(drug_list)             │   │  │
│  │  │    - openfda_adverse_events(drug, condition)   │   │  │
│  │  │    - rxnorm_normalize(drug_name)               │   │  │
│  │  │    - sql_query(drug_interaction_cache)         │   │  │
│  │  │  Output: DrugSafetyReport {                    │   │  │
│  │  │    interactions[], severity, evidence_level,   │   │  │
│  │  │    alternatives[], dosage_adjustments          │   │  │
│  │  │  }                                             │   │  │
│  │  └────────────────────────────────────────────────┘   │  │
│  │                                                       │  │
│  │  ┌────────────────────────────────────────────────┐   │  │
│  │  │  GUARDRAILS AGENT                              │   │  │
│  │  │  Model: GPT-4o (independent instance)          │   │  │
│  │  │  Tools:                                        │   │  │
│  │  │    - citation_verifier(claims, sources)        │   │  │
│  │  │    - content_safety_filter(text)               │   │  │
│  │  │    - scope_classifier(recommendation)          │   │  │
│  │  │  Output: ValidationResult {                    │   │  │
│  │  │    is_valid, hallucination_flags[],            │   │  │
│  │  │    safety_concerns[], disclaimers[]            │   │  │
│  │  │  }                                             │   │  │
│  │  └────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Agent Communication Protocol

```
Message Schema (A2A Protocol):
{
  "message_id": "uuid",
  "from_agent": "orchestrator",
  "to_agent": "drug_safety_agent",
  "type": "task_request",
  "payload": {
    "query": "Check interactions for Metformin 500mg + Lisinopril 10mg",
    "patient_context": { "patient_id": "...", "allergies": [...] },
    "priority": "high",
    "timeout_ms": 3000
  },
  "session_id": "uuid",
  "trace_id": "uuid"  // For distributed tracing
}
```

### 6.3 Conflict Resolution

When agents return contradictory information:

1. **Drug Safety always wins** — If Drug Safety Agent flags a major interaction, it overrides protocol recommendations
2. **Patient-specific data > generic guidelines** — Patient allergies/history supersede population-level protocols
3. **Evidence hierarchy** — RCTs > cohort studies > case reports > expert opinion
4. **Explicit uncertainty** — When conflict cannot be resolved, present both views with evidence levels
5. **Human-in-the-loop** — Critical conflicts trigger escalation to senior clinician review

### 6.4 Self-Correction Loop

Inspired by recent research on Agentic Graph RAG with self-correction:

```
Initial Retrieval → Agent Synthesis → Dual-Model Evaluation
                                            │
                                    ┌───────┴───────┐
                                    │               │
                              Model A (GPT-4o)  Model B (Claude)
                              evaluates          evaluates
                              sufficiency        sufficiency
                                    │               │
                                    └───────┬───────┘
                                            │
                                     Both agree?
                                    ┌───┴───┐
                                    No      Yes
                                    │       │
                              Re-retrieve   → Output
                              with refined
                              query
                              (max 3 loops)
```

---

## 7. Data Sources Design

### 7.1 Patient Records (Document Intelligence → AI Search)

**Ingestion Pipeline:**

```
Source (EHR/Uploaded PDFs)
    │
    ▼
Azure Blob Storage (staging container)
    │
    ├─ Trigger: Blob upload → Azure Function
    │
    ▼
Azure Document Intelligence (v4.0)
    │
    ├─ Layout analysis (preserve structure)
    ├─ Custom model (trained on lab report templates)
    ├─ OCR confidence scoring (reject < 85%)
    │
    ▼
Text Analytics for Health
    │
    ├─ Medical NER extraction:
    │   - Diagnoses → ICD-10 codes
    │   - Medications → RxNorm codes
    │   - Lab tests → LOINC codes
    │   - Procedures → CPT codes
    │   - Anatomical sites → SNOMED-CT
    │
    ▼
PHI De-Identification (Optional — for research index)
    │
    ├─ Presidio + custom medical PII recognizer
    │
    ▼
Chunking + Embedding
    │
    ├─ Semantic chunking (512-1024 tokens)
    ├─ text-embedding-3-large (3072 dims, Float16)
    │
    ▼
Azure AI Search (patient-records index)
    │
    ├─ Fields: content, content_vector, patient_id, document_type,
    │          date, medical_codes[], section_type, confidence_score
    ├─ Skillset: Custom Web API skill for Text Analytics for Health
    └─ Indexer: scheduled (every 15 min) or on-demand
```

### 7.2 Medical Literature (PubMed API + Cached Index)

**Dual-mode retrieval:**

```
MODE 1: Real-Time (for current, specific queries)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Query → Medical Literature Agent
    │
    ├─ Generate optimized PubMed query (LLM-assisted)
    │   - Convert natural language → MeSH terms + Boolean logic
    │   - Example: "latest treatment for Type 2 diabetes with CKD"
    │     → "(diabetes mellitus, type 2[MeSH]) AND
    │        (renal insufficiency, chronic[MeSH]) AND
    │        (therapeutics[MeSH]) AND (2023:2026[pdat])"
    │
    ├─ ESearch API → get PMIDs (top 50)
    ├─ EFetch API → get abstracts + metadata
    ├─ LLM relevance scoring → filter to top 10
    ├─ Cache results in AI Search (literature-cache index)
    └─ Return with full citations (PMID, DOI, authors, journal)

MODE 2: Cached (for common queries, faster response)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pre-indexed corpus:
    │
    ├─ Top 100 clinical conditions (weekly batch from PubMed)
    ├─ Systematic reviews and meta-analyses
    ├─ Treatment guidelines (NICE, WHO, AHA, etc.)
    ├─ PMC Open Access full-text subset
    │
    └─ Stored in Azure AI Search (literature-cache index)
        - Updated weekly via Azure Data Factory pipeline
        - ~500K abstracts, ~50K full-text articles
```

**PubMed API Rate Limits:**

- Without API key: 3 requests/second
- With API key (NCBI registered): 10 requests/second
- **Recommendation:** Register for API key, implement request queuing with exponential backoff

### 7.3 Treatment Protocols (Blob Storage → AI Search)

```
Azure Blob Storage
    │
    ├─ Container: "treatment-protocols"
    │   ├─ /cardiology/
    │   ├─ /oncology/
    │   ├─ /emergency/
    │   ├─ /infectious-disease/
    │   └─ /general-medicine/
    │
    ├─ Formats: PDF, DOCX, HTML
    ├─ Metadata tags: specialty, version, effective_date, author
    │
    ▼
Document Intelligence (Layout + Custom Model)
    │
    ├─ Extract: recommendation text, evidence grades,
    │           algorithm flowcharts (as structured data),
    │           dosing tables, contraindications
    │
    ▼
Chunking (by recommendation section)
    │
    ├─ Each chunk = one clinical recommendation + its evidence
    ├─ Metadata: guideline_name, section, evidence_grade,
    │            specialty, last_updated
    │
    ▼
Azure AI Search (protocols index)
    │
    └─ Filterable fields: specialty, evidence_grade, effective_date
```

### 7.4 Drug Interactions (Multi-Source with Local Cache)

```
┌─────────────────────────────────────────────────────────────────┐
│                  DRUG INTERACTION LAYER                         │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ DrugBank     │  │  OpenFDA     │  │  RxNorm              │   │
│  │ Clinical API │  │  Drug API    │  │  (NLM)               │   │
│  │              │  │              │  │                      │   │
│  │  DDI check   │  │  Adverse     │  │  Drug name →         │   │
│  │  (1.3M+)     │  │  events      │  │  normalized ID       │   │
│  │  Severity:   │  │  Drug labels │  │  (RxCUI)             │   │  
│  │  min/mod/maj │  │  Recalls     │  │                      │   │ 
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
│         │                 │                     │               │ 
│         └─────────────────┼─────────────────────┘               │
│                           │                                     │
│                           ▼                                     │
│                   ┌──────────────────┐                          │
│                   │  Azure SQL DB    │                          │
│                   │  (Local Cache)   │                          │
│                   │                  │                          │
│                   │  Tables:         │                          │
│                   │  - drug_master   │                          │
│                   │  - ddi_cache     │                          │
│                   │  - adverse_events│                          │
│                   │  - rxnorm_map    │                          │
│                   │                  │                          │
│                   │  Refresh: daily  │                          │
│                   └──────────────────┘                          │
│                                                                 │
│  Query Flow:                                                    │
│  1. Normalize drug names via RxNorm → RxCUI                     │
│  2. Check local cache first (Azure SQL)                         │
│  3. Cache miss → DrugBank API (DDI) + OpenFDA (adverse events)  │
│  4. Merge results: DDI severity + real-world adverse event freq │
│  5. Return structured DrugSafetyReport                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Cosmos DB Schema Design

### 8.1 Container Design

| Container | Partition Key | Purpose | TTL | RU Budget |
| --- | --- | --- | --- | --- |
| `patient_profiles` | `/patient_id` | Patient demographics, active meds, allergies, embeddings | None | 4,000 RU/s (autoscale) |
| `conversation_history` | `/session_id` | Full chat history, agent outputs, citations | 90 days | 2,000 RU/s (autoscale) |
| `embedding_cache` | `/source_type` | Pre-computed embeddings for common queries | 30 days | 1,000 RU/s (autoscale) |
| `audit_log` | `/date_partition` | PHI access logs, agent decisions, compliance trail | 7 years | 1,000 RU/s (autoscale) |
| `agent_state` | `/session_id` | Agent memory, intermediate results, tool call logs | 24 hours | 500 RU/s (autoscale) |

### 8.2 Document Schemas

#### Patient Profile Document

```json
{
  "id": "patient_12345",
  "patient_id": "patient_12345",
  "type": "patient_profile",
  "demographics": {
    "age": 65,
    "sex": "M",
    "weight_kg": 82,
    "height_cm": 175,
    "blood_type": "A+"
  },
  "active_conditions": [
    {
      "code": "E11.9",
      "system": "ICD-10",
      "display": "Type 2 Diabetes Mellitus",
      "onset_date": "2019-03-15",
      "status": "active"
    }
  ],
  "active_medications": [
    {
      "rxcui": "860975",
      "name": "Metformin 500mg",
      "dose": "500mg",
      "frequency": "BID",
      "start_date": "2019-04-01",
      "prescriber": "Dr. Smith"
    }
  ],
  "allergies": [
    {
      "substance": "Penicillin",
      "reaction": "Anaphylaxis",
      "severity": "severe",
      "code": "91936005",
      "system": "SNOMED-CT"
    }
  ],
  "recent_labs": [
    {
      "code": "4548-4",
      "system": "LOINC",
      "display": "HbA1c",
      "value": 7.2,
      "unit": "%",
      "date": "2026-02-01",
      "reference_range": "4.0-5.6"
    }
  ],
  "patient_embedding": [0.012, -0.034, ...],  // Float16, 3072 dims
  "_ts": 1708387200,
  "_etag": "\"0x8DC2F...\"",
  "last_updated": "2026-02-20T10:00:00Z"
}
```

#### Conversation History Document

```json
{
  "id": "conv_uuid_001",
  "session_id": "sess_abc123",
  "patient_id": "patient_12345",
  "type": "conversation_turn",
  "turn_number": 3,
  "timestamp": "2026-02-20T10:05:23Z",
  "clinician_id": "dr_jones_456",
  "query": {
    "text": "What are the treatment options for this patient's uncontrolled diabetes given their CKD stage 3?",
    "intent": "treatment_recommendation",
    "extracted_entities": [
      {"type": "condition", "value": "Type 2 Diabetes", "code": "E11.9"},
      {"type": "condition", "value": "CKD Stage 3", "code": "N18.3"}
    ]
  },
  "agent_outputs": {
    "patient_history": {
      "agent": "patient_history_agent",
      "latency_ms": 650,
      "sources_retrieved": 8,
      "summary": "65M with T2DM (HbA1c 7.2%), CKD3 (eGFR 42), on Metformin 500mg BID..."
    },
    "literature": {
      "agent": "medical_literature_agent",
      "latency_ms": 1800,
      "papers_retrieved": 12,
      "top_citations": ["PMID:38234567", "PMID:37891234"]
    },
    "protocols": {
      "agent": "protocol_agent",
      "latency_ms": 420,
      "guidelines_matched": ["ADA 2026 Standards of Care", "KDIGO CKD Guideline"]
    },
    "drug_safety": {
      "agent": "drug_safety_agent",
      "latency_ms": 890,
      "interactions_found": 2,
      "alerts": [
        {
          "severity": "moderate",
          "description": "Metformin dose adjustment needed for eGFR 30-45",
          "source": "DrugBank",
          "evidence_level": 1
        }
      ]
    }
  },
  "response": {
    "recommendation": "Based on ADA 2026 guidelines and patient's CKD stage 3...",
    "confidence_score": 0.87,
    "citations": [
      {"pmid": "38234567", "title": "...", "relevance": 0.92},
      {"guideline": "ADA 2026", "section": "9.1", "relevance": 0.95}
    ],
    "drug_alerts": [...],
    "disclaimers": ["Clinical decision support tool — verify with attending physician"]
  },
  "guardrails": {
    "hallucination_check": "passed",
    "safety_check": "passed",
   "scope_check": "passed"
  },
  "feedback": {
    "clinician_rating": null,
    "clinician_correction": null,
    "rated_at": null
  },
  "total_latency_ms": 7200,
  "tokens_used": {
    "input": 12500,
    "output": 2100,
    "embedding": 3072
  }
}
```

#### Audit Log Document

```json
{
  "id": "audit_uuid_001",
  "date_partition": "2026-02-20",
  "type": "phi_access",
  "timestamp": "2026-02-20T10:05:23Z",
  "actor": {
    "clinician_id": "dr_jones_456",
    "role": "attending_physician",
    "department": "internal_medicine",
    "ip_address": "10.0.1.42"
  },
  "action": "query_patient_records",
  "resource": {
    "patient_id": "patient_12345",
    "data_types_accessed": ["conditions", "medications", "labs"],
    "documents_retrieved": 8
  },
  "session_id": "sess_abc123",
  "justification": "clinical_decision_support",
  "outcome": "success",
  "data_sent_to_llm": true,
  "phi_fields_sent": ["conditions", "medications", "lab_results"],
  "phi_fields_redacted": ["name", "dob", "ssn", "address"]
}
```

### 8.3 Vector Search Configuration

```json
// Cosmos DB container vector policy (patient_profiles)
{
  "vectorEmbeddings": [
    {
      "path": "/patient_embedding",
      "dataType": "float16",
      "distanceFunction": "cosine",
      "dimensions": 3072
    }
  ],
  "vectorIndexes": [
    {
      "path": "/patient_embedding",
      "type": "diskANN"
    }
  ]
}
```

### 8.4 Change Feed Integration

```
Cosmos DB Change Feed
    │
    ├─ patient_profiles container → Azure Function
    │   └─ Sync updated patient data to AI Search index
    │   └─ Invalidate embedding cache for changed records
    │
    ├─ conversation_history container → Azure Function
    │   └─ Stream to Azure Event Hub → Analytics pipeline
    │   └─ Update clinician usage dashboards
    │
    └─ audit_log container → Azure Function
        └─ Real-time compliance monitoring
        └─ Alert on anomalous PHI access patterns
```

---

## 9. Security & Compliance

### 9.1 HIPAA Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HIPAA SECURITY ARCHITECTURE                        │
│                                                                             │
│  ADMINISTRATIVE SAFEGUARDS                                                  │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  • Business Associate Agreement (BAA) with Microsoft                   │ │
│  │  • Designated Security Officer + Privacy Officer                       │ │
│  │  • Annual risk assessment + penetration testing                        │ │
│  │  • Staff training on PHI handling procedures                           │ │
│  │  • Incident response plan with <72hr breach notification               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  TECHNICAL SAFEGUARDS                                                       │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                                                                        │ │
│  │  ENCRYPTION                                                            │ │
│  │  • At rest: AES-256 (Azure Storage Service Encryption)                 │ │
│  │  • In transit: TLS 1.3 (enforced on all endpoints)                     │ │
│  │  • Key management: Azure Key Vault (HSM-backed, FIPS 140-2 L2)         │ │
│  │  • Customer-managed keys (CMK) for Cosmos DB + Blob Storage            │ │
│  │                                                                        │ │
│  │  ACCESS CONTROL                                                        │ │
│  │  • Azure AD + Conditional Access policies                              │ │
│  │  • RBAC roles: Clinician, Nurse, Admin, System (service principal)     │ │
│  │  • Minimum necessary access principle                                  │ │
│  │ • MFA required for all human access                                    │ │
│  │  • Managed Identities for service-to-service auth (no stored secrets)  │ │
│  │                                                                        │ │
│  │  NETWORK ISOLATION                                                     │ │
│  │  • Azure Virtual Network with NSGs                                     │ │
│  │  • Private Link for: Cosmos DB, AI Search, Blob, SQL, OpenAI           │ │
│  │  • No public endpoints for data services                               │ │
│  │  • Azure Firewall for egress filtering                                 │ │
│  │  • Azure Front Door with WAF for ingress                               │ │
│  │                                                                        │ │
│  │  AUDIT & MONITORING                                                    │ │
│  │  • Azure Monitor + Log Analytics workspace                             │ │
│  │  • Diagnostic logs: Cosmos DB, AI Search, App Service                  │ │
│  │  • Microsoft Defender for Cloud (healthcare compliance dashboard)      │ │
│  │  • Custom audit trail in Cosmos DB (7-year retention)                  │ │
│  │  • Azure Sentinel SIEM for threat detection                            │ │
│  │  • Anomaly detection on PHI access patterns                            │ │
│  │                                                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  PHI DATA HANDLING                                                          │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  • Data classification: PHI, PII, De-Identified, Public                │ │
│  │  • Sensitivity labels via Azure Purview (auto-classification)          │ │
│  │  • De-identification pipeline before LLM processing (when possible)    │ │
│  │  • PHIminimization: send only necessary fields to LLM                  │ │
│  │  • Azure OpenAI: HIPAA-eligible (text-based, with BAA)                 │ │
│  │  • Data residency: HIPAA-eligible US regions only                      │ │
│  │  • DLP policies: prevent PHI leakage via Azure Purview                 │ │
│  │  • Break-glass access with mandatory audit                             │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  PHYSICAL SAFEGUARDS (Azure-Managed)                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  • Azure datacenters: SOC 1/2, ISO 27001, HITRUST CSF certified        │ │
│  │  • Physical access controls managed by Microsoft                       │ │
│  │  • Availability Zones for HA (99.999% SLA for Cosmos DB)               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 RBAC Role Matrix

| Role | Patient Records | Drug DB | Literature | Protocols | Audit Logs | Agent Config |
| --- | --- | --- | --- | --- | --- | --- |
| Attending Physician | Read/Write | Read | Read | Read | Read (own) | None |
| Resident | Read | Read | Read | Read | Read (own) | None |
| Nurse | Read (limited) | Read | None | Read | Read (own) | None |
| Pharmacist | Read (meds only) | Read/Write | Read | Read | Read (own) | None |
| System Admin | None | None | None | None | Read (all) | Full |
| Service Principal (Agent) | Read | Read | Read | Read | Write | None |

### 9.3 Data Residency & Compliance Certifications Required

| Certification | Status | Notes |
| --- | --- | --- |
| HIPAA BAA | Required before go-live | Sign with Microsoft |
| HITRUST CSF | Recommended | Azure services certified |
| SOC 2 Type II | Required for audit | Azure services certified |
| ISO 27001 | Required | Azure services certified |
| FDA 21 CFR Part 11 | If applicable | For electronic records |

---

## 10. Tech Stack

### 10.1 Backend Services

| Component | Technology | Justification |
| --- | --- | --- |
| **API Layer** | Python 3.12 + FastAPI | Async, type-safe, OpenAPI auto-docs, excellent Azure SDK support |
| **Agent Framework** | Microsoft Agent Framework (Python SDK) | Native Foundry Agent Service integration, A2A protocol, MCP support |
| **Orchestration Runtime** | Azure AI Foundry Agent Service | Managed runtime, persistent memory, tool orchestration, content safety |
| **LLM SDK** | Azure OpenAI Python SDK (`openai>=1.40`) | Official SDK, streaming, structured outputs, function calling |
| **Search SDK** | `azure-search-documents>=11.6` | Hybrid search, integrated vectorization, semantic ranking |
| **Document Processing** | `azure-ai-documentintelligence>=1.0` | Layout analysis, custom models, confidence scoring |
| **Database SDK** | `azure-cosmos>=4.7` | Vector search, change feed, hierarchical partitioning |
| **FHIR Client** | `fhir.resources>=7.0` + `httpx` | FHIR R4 resource models, async HTTP |
| **PubMed Client** | `biopython>=1.84` (Entrez module) | Official NCBI API wrapper |
| **Drug Interaction** | Custom REST client for DrugBank/OpenFDA/RxNorm | Unified interface over 3 APIs |
| **Task Queue** | Azure Service Bus | Reliable message delivery for async agent tasks |
| **Caching** | Azure Cache for Redis | Session caching, rate limiting, API response caching |

### 10.2 Infrastructure

| Component | Technology | Justification |
| --- | --- | --- |
| **Compute** | Azure Container Apps | Serverless containers, auto-scaling, VNET integration |
| **Async Workers** | Azure Functions (Python v2 model) | Event-driven (blob triggers, change feed), cost-efficient |
| **API Gateway** | Azure API Management (APIM) | Rate limiting, auth, analytics, OpenAPI publishing |
| **CDN/WAF** | Azure Front Door + WAF | DDoS protection, geo-routing, SSL termination |
| **CI/CD** | GitHub Actions + Azure DevOps | Automated testing, security scanning, deployment |
| **IaC** | Terraform + Azure Bicep | Reproducible infrastructure, compliance-as-code |
| **Monitoring** | Azure Monitor + App Insights + Grafana | E2E observability, custom dashboards |
| **Secret Management** | Azure Key Vault | HSM-backed, CMK rotation, managed identities |
| **Container Registry** | Azure Container Registry | Private images, vulnerability scanning |

### 10.3 Frontend (Clinical UI)

| Component | Technology | Justification |
| --- | --- | --- |
| **Framework** | React 19 + TypeScript | Type safety, large healthcare UI ecosystem |
| **UI Library** | Fluent UI v9 (Microsoft) | Healthcare-friendly design, accessible, Azure AD integration |
| **State** | TanStack Query + Zustand | Server state caching, real-time updates |
| **Real-time** | WebSocket (Azure Web PubSub) | Streaming LLM responses to clinician UI |
| **Auth** | MSAL.js + Azure AD B2C | SSO, MFA, HIPAA-compliant auth flow |

### 10.4 Evaluation & Testing

| Component | Technology | Purpose |
| --- | --- | --- |
| **RAG Evaluation** | RAGAS framework | Context relevancy, faithfulness, answer relevancy scoring |
| **Medical Accuracy** | Custom benchmark suite | Compare against medical board Q&A datasets (MedQA, PubMedQA) |
| **Load Testing** | Azure Load Testing (JMeter) | Simulate 100+ concurrent clinician queries |
| **Integration Tests** | pytest + testcontainers | Cosmos DB emulator, AI Search mock |
| **Security Testing** | Microsoft Defender for Cloud + OWASP ZAP | Vulnerability scanning, penetration testing |

---

## 11. Implementation Phases

### Phase 1: Foundation (Weeks 1-4)

```
GOAL: Core infrastructure + single-source RAG (patient records only)

Week 1-2: Infrastructure
  ├─ Provision Azure resources (Terraform/Bicep)
  │   - VNet, Private Links, Key Vault, Cosmos DB, AI Search, Blob
  ├─ Configure HIPAA compliance (BAA, encryption, RBAC, audit)
  ├─ Set up CI/CD pipeline (GitHub Actions → Container Apps)
  └─ Deploy monitoring stack (App Insights, Log Analytics)

Week 2-3: Document Ingestion Pipeline
  ├─ Build Document Intelligence pipeline (Blob → OCR → NER → Chunks)
  ├─ Configure AI Search index (patient-records) with hybrid search
  ├─ Implement embedding generation (text-embedding-3-large)
  └─ Load test documents (50-100 sample patient records)

Week 3-4: Basic RAG + API
  ├─ Build FastAPI service with basic RAG endpoint
  ├─ Single agent: retrieve patient records → synthesize with GPT-4o
  ├─ Conversation history in Cosmos DB
  ├─ Basic clinical UI (React + Fluent UI)
  └─ Initial accuracy benchmarks

DELIVERABLE: Working single-source CDSS with patient record search
```

### Phase 2: Multi-Source RAG (Weeks 5-8)

```
GOAL: Add treatment protocols + drug interactions + PubMed

Week 5-6: Additional Data Sources
  ├─ Ingest treatment protocols (Blob → AI Search protocols index)
  ├─ Build PubMed integration (E-Utilities client + caching)
  ├─ Set up drug interaction layer (DrugBank + OpenFDA + RxNorm)
  ├─ Configure Azure SQL for drug interaction cache
  └─ Build literature cache pipeline (weekly PubMed batch)

Week 7-8: Multi-Source Retrieval
  ├─ Implement cross-source fusion logic
  ├─ Add semantic reranking (AI Search L2)
  ├─ Build citation tracking system
  ├─ Add confidence scoring
  └─ Benchmark: compare single-source vs multi-source accuracy

DELIVERABLE: Multi-source RAG with 4 data sources, citations
```

### Phase 3: Agentic Orchestration (Weeks 9-12)

```
GOAL: Deploy specialized agents with orchestration

Week 9-10: Agent Development
  ├─ Build Orchestrator Agent (query planner, dispatcher)
  ├─ Build Patient History Agent (AI Search + FHIR tools)
  ├─ Build Medical Literature Agent (PubMed + cache tools)
  ├─ Build Protocol Agent (AI Search + Blob tools)
  ├─ Build Drug Safety Agent (DrugBank + OpenFDA + RxNorm tools)
  └─ Deploy on Foundry Agent Service

Week 11-12: Guardrails + Self-Correction
  ├─ Build Guardrails Agent (hallucination check, scope check)
  ├─ Implement self-correction loop (dual-model evaluation)
  ├─ Add clinical disclaimers and confidence thresholds
  ├─ Build conflict resolution logic
  └─ End-to-end testing with clinical scenarios

DELIVERABLE: Full agentic CDSS with 5 specialized agents
```

### Phase 4: FHIR + Production Hardening (Weeks 13-16)

```
GOAL: EHR interoperability + production readiness

Week 13-14: FHIR Integration
  ├─ Deploy Azure Health Data Services (FHIR R4)
  ├─ Build FHIR data ingestion (Patient, Observation, MedicationRequest)
  ├─ Integrate Patient History Agent with FHIR queries
  ├─ HL7v2 → FHIR conversion pipeline (if legacy EHR)
  └─ Test with Epic/Cerner sandbox

Week 15-16: Production Hardening
  ├─ Load testing (100+ concurrent users, <10s P95 latency)
  ├─ Security audit + penetration testing
  ├─ HIPAA compliance validation
  ├─ Clinician UAT (User Acceptance Testing)
  ├─ Runbook creation (incident response, scaling, failover)
  └─ Monitoring dashboards (Grafana: latency, accuracy, usage)

DELIVERABLE: Production-ready CDSS with EHR integration
```

### Phase 5: Advanced Features (Weeks 17-24)

```
GOAL: Continuous learning + advanced clinical features

  ├─ Clinician feedback loop (reinforcement from corrections)
  ├─ Multi-turn clinical reasoning (complex case discussions)
  ├─ Medical imaging integration (DICOM via Health Data Services)
  ├─ Custom medical embedding model (fine-tuned on clinical corpus)
  ├─ Knowledge graph layer (medical ontology + relationship inference)
  ├─ Patient risk scoring (predictive models using historical data)
  ├─ Clinical trial matching agent (ClinicalTrials.gov API)
  └─ Regulatory submission documentation (FDA pre-submission if SaMD)
```

---

## 12. Challenges & Mitigations

### 12.1 Technical Challenges

| Challenge | Impact | Mitigation |
| --- | --- | --- |
| **Medical hallucinations** | Critical — incorrect recommendations could harm patients | Guardrails Agent with citation verification; every claim must cite a source; dual-model self-correction loop; confidence thresholds; explicit "insufficient evidence" responses |
| **LLM latency for clinical workflows** | High — clinicians expect sub-10s responses | Parallel agent dispatch; aggressive caching (Redis + Cosmos); streaming responses to UI; pre-computed embeddings; GPT-4o-mini for non-critical steps |
| **Stale medical knowledge** | High — treatment guidelines update frequently | Weekly PubMed batch refresh; version-tracked protocols; cache invalidation on protocol updates; "last verified" timestamps on all recommendations |
| **Drug name disambiguation** | Medium — brand vs generic, international names | RxNorm normalization as first step in Drug Safety Agent; fuzzy matching with confirmation; maintain drug alias mapping table |
| **Document OCR accuracy** | Medium — poor scan quality reduces extraction quality | Confidence scoring with rejection threshold (85%); manual review queue for low-confidence documents; custom Document Intelligence models trained on facility-specific templates |
| **Cross-source contradiction** | Medium — guidelines may conflict with recent literature | Evidence hierarchy (RCT > cohort > case report); explicit conflict reporting; timestamp-based recency weighting; human-in-the-loop for unresolvable conflicts |
| **Context window limits** | Medium — patient with extensive history may exceed 128K tokens | Hierarchical summarization; most-recent-first retrieval; patient history summarization agent that creates a condensed timeline; chunked context windows with continuation |

### 12.2 Compliance Challenges

| Challenge | Impact | Mitigation |
| --- | --- | --- |
| **PHI in LLM prompts** | Critical — data sent to AI model | Azure OpenAI with BAA (HIPAA-eligible); PHI minimization (send only necessary fields); de-identification for non-essential context; no PHI in system prompts |
| **Audit trail completeness** | High — regulatory requirement | Every agent action logged to Cosmos DB audit container; 7-year retention; immutable write-once pattern; correlation IDs across all services |
| **Data residency** | High — PHI must stay in approved regions | Azure region lock to US (HIPAA-eligible regions); network policies to prevent cross-region transfer; Azure Policy enforcement |
| **Model output liability** | Critical — who is responsible for AI recommendations? | Mandatory disclaimer on every output; "decision support, not diagnosis" framing; clinician must acknowledge before acting; institutional review of system behavior |
| **Right to access / correction** | Medium — patient data rights | FHIR-based patient data access; correction workflow via clinical staff; audit trail of all data modifications |

### 12.3 Operational Challenges

| Challenge | Impact | Mitigation |
| --- | --- | --- |
| **Cost management** | High — GPT-4o + multi-agent = high token spend | GPT-4o-mini for routing/classification; cached retrieval; prompt optimization; token usage monitoring with alerts; batch processing for non-urgent queries |
| **Clinician adoption** | High — tool must fit clinical workflow | Embedded in EHR (SMART on FHIR); sub-10s response time; one-click citation access; clinician co-design of UI; training program |
| **Evaluation at scale** | Medium — hard to measure medical accuracy | RAGAS framework for RAG metrics; gold-standard test set reviewed by physicians; A/B testing with clinician panel; continuous monitoring of feedback ratings |
| **Multi-tenant isolation** | Medium — different hospital departments | Cosmos DB partition-level isolation; tenant-scoped RBAC; separate AI Search indexes per facility (if multi-hospital) |

---

## 13. References

### Azure Documentation

- [Azure AI Foundry Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/overview)
- [Azure AI Search — RAG Overview](https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview)
- [Azure AI Search — Hybrid Search](https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview)
- [Azure AI Search — Semantic Ranking](https://learn.microsoft.com/en-us/azure/search/semantic-search-overview)
- [Azure AI Search — Chunking Strategies](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-chunk-documents)
- [Azure Document Intelligence](https://azure.microsoft.com/en-us/products/ai-foundry/tools/document-intelligence)
- [Azure Cosmos DB — Vector Database](https://learn.microsoft.com/en-us/azure/cosmos-db/vector-database)
- [Azure Cosmos DB — Hybrid Search](https://learn.microsoft.com/en-us/azure/cosmos-db/gen-ai/hybrid-search)
- [Azure Health Data Services — FHIR](https://learn.microsoft.com/en-us/azure/healthcare-apis/fhir/overview)
- [HIPAA on Azure](https://learn.microsoft.com/en-us/azure/compliance/offerings/offering-hipaa-us)
- [Text Analytics for Health](https://learn.microsoft.com/en-us/azure/ai-services/language-service/text-analytics-for-health/overview)

### Microsoft Healthcare AI

- [Healthcare Agent Orchestrator (GitHub)](https://github.com/Azure-Samples/healthcare-agent-orchestrator)
- [Agentic AI Healthcare Innovation at Ignite 2025](https://www.microsoft.com/en-us/industry/blog/healthcare/2025/11/18/agentic-ai-in-action-healthcare-innovation-at-microsoft-ignite-2025/)
- [Microsoft Agent Framework](https://azure.microsoft.com/en-us/blog/introducing-microsoft-agent-framework/)
- [Claude in Microsoft Foundry for Healthcare](https://www.microsoft.com/en-us/industry/blog/healthcare/2026/01/11/bridging-the-gap-between-ai-and-medicine-claude-in-microsoft-foundry-advances-capabilities-for-healthcare-and-life-sciences-customers/)
- [Cosmos DB Ignite 2025 Updates](https://devblogs.microsoft.com/cosmosdb/whats-new-in-search-for-azure-cosmos-db-at-ignite-2025/)

### Drug Interaction APIs

- [DrugBank Clinical API — DDI Checker](https://go.drugbank.com/clinical/drug_drug_interaction_checker)
- [OpenFDA API](https://open.fda.gov/apis/)
- [RxNorm — NLM](https://lhncbc.nlm.nih.gov/RxNav/)

### Research Papers

- [PubMed Retrieval with RAG Techniques](https://pubmed.ncbi.nlm.nih.gov/39176826/)
- [Enhancing Medical AI with RAG](https://pmc.ncbi.nlm.nih.gov/articles/PMC12059965/)
- [Self-Correcting Agentic Graph RAG for Clinical Decision Support](https://pmc.ncbi.nlm.nih.gov/articles/PMC12748213/)
- [Multi-Agent RAG in Healthcare Decision Support](https://techkraftinc.com/how-multi-agent-rag-systems-transform-healthcare/)
- [Evaluating Medical RAG with NVIDIA AI Endpoints and Ragas](https://developer.nvidia.com/blog/evaluating-medical-rag-with-nvidia-ai-endpoints-and-ragas/)

---

*Document generated: 2026-02-20 | This architecture is opinionated and based on current Azure capabilities. Review with your clinical informatics and compliance teams before implementation.*
