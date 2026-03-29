# Architecture Overview

**Clinical Decision Support System (CDSS) with Agentic RAG on Azure**

This document provides a high-level overview of the system architecture. For the full architecture design document, refer to the project Notion workspace.

## Scope Note (Implemented vs Design-Target)

This file describes the **implemented runtime architecture** in this repository.

- Implemented core: FastAPI + Container Apps, Azure OpenAI, Azure AI Search, Cosmos DB, Blob, Document Intelligence, Entra auth, SSE streaming, persisted audit APIs.
- Design-target but not currently implemented in runtime/IaC path: APIM/Front Door, FHIR/DICOM, Service Bus/Event Hub/Azure Functions async pipeline, Web PubSub transport, SQL cache-first drug safety workflow, Text Analytics for Health enrichment.

---

## System Architecture Diagram

```
                         Clinical Decision Support System
                         ================================

  Clinician
     |
     | REST API (HTTPS/TLS 1.3)
     v
  +------------------------------------------------------------------+
  |                     FastAPI Application                           |
  |  +------------------------------------------------------------+  |
  |  |  Authentication (Azure Entra ID)  |  Rate Limiting (In-Memory; Redis optional) |  |
  |  +------------------------------------------------------------+  |
  |  |  Audit Middleware -- logs every request/response             |  |
  |  +------------------------------------------------------------+  |
  |  |                     API Routes                              |  |
  |  |  /query  /patients  /documents  /drugs  /search  /health   |  |
  |  +------------------------------------------------------------+  |
  +------------------------------------------------------------------+
       |
       v
  +------------------------------------------------------------------+
  |                  Agentic AI Orchestrator                          |
  |                                                                  |
  |  - Receives clinical query + patient context                     |
  |  - Decomposes into sub-tasks for specialized agents              |
  |  - Manages parallel execution and error handling                 |
  |  - Synthesizes agent outputs via Reciprocal Rank Fusion          |
  |  - Generates final recommendation with confidence score          |
  |                                                                  |
  |  Model: GPT-4o  |  Max tokens: 4096  |  Temperature: 0.1        |
  +------------------------------------------------------------------+
       |              |              |              |              |
       v              v              v              v              v
  +---------+   +---------+   +---------+   +---------+   +-----------+
  | Patient |   | Medical |   |Protocol |   |  Drug   |   |Guardrails |
  | History |   |Literatur|   | Agent   |   | Safety  |   |  Agent    |
  | Agent   |   |e Agent  |   |         |   | Agent   |   |           |
  |---------|   |---------|   |---------|   |---------|   |-----------|
  |GPT-4o-  |   |GPT-4o   |   |GPT-4o-  |   |GPT-4o   |   |GPT-4o    |
  |mini     |   |         |   |mini     |   |         |   |           |
  +---------+   +---------+   +---------+   +---------+   +-----------+
       |              |              |              |              |
       v              v              v              v              v
  +---------+   +---------+   +---------+   +---------+   +-----------+
  |Azure AI |   | PubMed  |   |Azure AI |   |DrugBank |   | Citation  |
  | Search  |   |  API    |   | Search  |   |  API    |   | Verifier  |
  |---------|   |---------|   |---------|   |---------|   |-----------|
  |Cosmos DB|   | Redis   |   |  Blob   |   |OpenFDA  |   | Safety    |
  |         |   | Cache   |   | Storage |   | API     |   | Rules     |
  |         |   |         |   |         |   |---------|   | Engine    |
  |         |   |         |   |         |   | RxNorm  |   |           |
  |         |   |         |   |         |   | API     |   |           |
  +---------+   +---------+   +---------+   +---------+   +-----------+
```

---

## Agent Descriptions

### 1. Patient History Agent

**Purpose:** Retrieves and summarizes the patient's complete medical profile, including demographics, conditions, medications, allergies, lab results, surgical history, and vital signs.

**Data Sources:**
- **Azure AI Search** -- Patient index with hybrid BM25 + vector search over unstructured clinical notes
- **Azure Cosmos DB** -- Structured patient records with DiskANN vector indexing for similarity queries

**Model:** GPT-4o-mini (optimized for speed; patient data retrieval is a lower-complexity task)

**Output:** Structured patient summary in JSON format containing:
- Active conditions with ICD-10 codes
- Current medications with RxNorm CUIs and dosing
- Allergies with severity and reaction details
- Recent lab results with trends
- Relevant social and family history

### 2. Medical Literature Agent

**Purpose:** Searches biomedical literature for evidence relevant to the clinical question, prioritizing high-quality evidence (systematic reviews, meta-analyses, clinical guidelines, RCTs).

**Data Sources:**
- **PubMed E-utilities API** -- Real-time access to 36M+ citations in MEDLINE
- **Azure AI Search (cached literature)** -- Pre-indexed full-text articles and guidelines for faster retrieval
- **Azure Cache for Redis** -- Provisioned and available as an optional cache backend (current runtime path does not require Redis)

**Model:** GPT-4o (full model for complex medical reasoning and evidence synthesis)

**Output:** Ranked list of evidence with:
- PubMed IDs (PMIDs) with titles, authors, journals
- Evidence grade classification (systematic review > RCT > cohort > case series > expert opinion)
- Relevance scores from semantic reranking
- Key findings extracted from abstracts

### 3. Protocol Agent

**Purpose:** Retrieves institutional treatment protocols and clinical practice guidelines that apply to the patient's conditions.

**Data Sources:**
- **Azure AI Search** -- Protocol index with metadata filtering (specialty, condition, evidence grade)
- **Azure Blob Storage** -- Raw protocol documents (PDF, DOCX) stored and versioned

**Model:** GPT-4o-mini (protocol retrieval is primarily a search and summarization task)

**Output:** Matching protocols with:
- Protocol ID, version, and effective date
- Relevant sections extracted
- Treatment algorithm steps applicable to the patient
- Dosing tables filtered by patient's renal/hepatic function

### 4. Drug Safety Agent

**Purpose:** Analyzes the patient's current and proposed medications for drug-drug interactions, drug-disease contraindications, and dose adjustments required by organ function.

**Data Sources:**
- **DrugBank API** -- Comprehensive drug interaction database
- **OpenFDA API** -- Adverse event reports and drug label information
- **RxNorm API** -- Drug name normalization and concept mapping

**Model:** GPT-4o (full model for critical safety analysis)

**Output:** Drug safety report with:
- Drug-drug interactions with severity levels (critical, major, moderate, minor)
- Drug-disease contraindications based on patient's condition list
- Required dose adjustments based on eGFR, hepatic function, age, weight
- Alerts with recommended actions

### 5. Guardrails Agent

**Purpose:** Final safety validation layer that verifies the synthesized recommendation before it is returned to the clinician.

**Checks Performed:**
1. **Citation Verification** -- Every cited PMID is verified against PubMed to confirm it exists and the abstract supports the claim made
2. **Contraindication Screening** -- Recommended medications are checked against the patient's allergy list, condition list, and current medications
3. **Dose Range Validation** -- Recommended doses are verified against approved ranges adjusted for the patient's renal and hepatic function
4. **Hallucination Detection** -- Claims in the recommendation are cross-referenced against the evidence retrieved by other agents
5. **Safety Flag Review** -- Configurable rules engine flags specific high-risk scenarios (e.g., narrow therapeutic index drugs, black box warnings)

**Model:** GPT-4o (full model for nuanced safety reasoning)

**Output:** Guardrails validation report with pass/fail status for each check and explanatory notes.

---

## RAG Pipeline Architecture

The Retrieval-Augmented Generation (RAG) pipeline is the core retrieval component used by agents 1-3.

### Hybrid Retrieval Strategy

```
Query
  |
  +---> BM25 Lexical Search (Azure AI Search)
  |          |
  |          v
  |     Top-K lexical results (keyword matches)
  |
  +---> Dense Vector Search (text-embedding-3-large, 3072-dim)
  |          |
  |          v
  |     Top-K semantic results (meaning matches)
  |
  +---> Reciprocal Rank Fusion
           |
           v
       Merged results (deduplicated, combined scores)
           |
           v
       Semantic Reranker (cross-encoder)
           |
           v
       Top-N final results with relevance scores
```

### Chunking Strategy

Documents are chunked using a layout-aware strategy powered by Azure AI Document Intelligence:

- **Chunk size:** 512 tokens (configurable)
- **Chunk overlap:** 64 tokens
- **Layout awareness:** Respects section headers, tables, lists, and paragraph boundaries
- **Metadata preservation:** Each chunk retains source document ID, section path, page number, and document type

---

## Data Flow Summary

1. **Query Reception** -- Authenticated request received, validated, audit record created
2. **Query Decomposition** -- Orchestrator analyzes query and selects agents to invoke
3. **Parallel Agent Execution** -- Selected agents run concurrently with their respective data sources
4. **Evidence Retrieval** -- Each agent's RAG pipeline performs hybrid search, reranking, and fusion
5. **Agent Synthesis** -- Orchestrator combines agent outputs into unified recommendation
6. **Guardrails Validation** -- Safety agent verifies citations, checks contraindications, detects hallucinations
7. **Response Delivery** -- Validated response returned with confidence score, citations, alerts, and disclaimers

---

## Infrastructure

All Azure resources are provisioned via Bicep templates located in the `infra/` directory. See the main [README](../README.md) for deployment instructions and the complete list of Azure services.

Implemented by current IaC/runtime path:
- VNet + private endpoints (production path), Container Apps, ACR
- Azure OpenAI, Azure AI Search, Cosmos DB, Blob Storage, Document Intelligence
- Key Vault, Log Analytics, App Insights, Redis (provisioned)

Not provisioned in current IaC path:
- APIM, Front Door/WAF
- FHIR/DICOM services
- Service Bus/Event Hub/Functions async event architecture
- Web PubSub
- SQL-backed drug cache subsystem

---

## Security Architecture

- **Authentication:** Azure Entra ID (OAuth 2.0 / OIDC) for all API access
- **Authorization:** Role-based access control (Clinician, Pharmacist, Admin, Auditor)
- **Encryption:** AES-256 at rest (customer-managed keys), TLS 1.3 in transit
- **Network:** VNet + private endpoints for core Azure services in production; optional bootstrap/runtime compatibility flow may temporarily relax OpenAI network access to avoid `403` runtime blockers
- **Secrets:** Azure Key Vault with automatic rotation
- **Audit:** Immutable audit trail with tamper-evident hashing, 7-year retention
- **PHI Handling:** Patient data referenced by opaque IDs; minimized in LLM context windows
