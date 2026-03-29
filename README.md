# Clinical Decision Support System (CDSS) with Agentic RAG

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Azure](https://img.shields.io/badge/Azure-Cloud-0078D4?style=for-the-badge&logo=microsoftazure&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

**Intelligent Clinical Decision Support System powered by Multi-Agent RAG on Azure**

A production-grade clinical decision support platform that orchestrates five specialized AI agents to synthesize patient records, medical literature, treatment protocols, and drug safety data into evidence-based clinical recommendations with full citation provenance and HIPAA-compliant audit trails.

---

<img width="2458" height="4026" alt="Image" src="https://github.com/user-attachments/assets/32a1aadc-4d68-4ea3-b158-61b1a84a70b4" />

## Architecture

```
                         Clinical Decision Support System
                         ================================

  Patient Query
       |
       v
  +------------------------------------------------------------+
  |              Agentic AI Orchestrator (GPT-4o)              |
  |                                                            |
  |  Decomposes query, delegates to specialized agents,        |
  |  synthesizes final recommendation with citations           |
  +----+----------+----------+----------+----------+-----------+
       |          |          |          |          |
       v          v          v          v          v
  +---------+ +----------+ +---------+ +---------+ +-----------+
  | Patient | | Medical  | |Protocol | |  Drug   | |Guardrails |
  | History | |Literature| | Agent   | | Safety  | |  Agent    |
  | Agent   | | Agent    | |         | | Agent   | |           |
  +---------+ +----------+ +---------+ +---------+ +-----------+
       |          |            |          |          |
       v          v            v          v          v
  +---------+ +---------+ +---------+ +---------+ +------------+
  |Azure AI | | PubMed  | |Azure AI | |DrugBank | | Citation   |
  | Search  | |  API    | | Search  | |OpenFDA  | |Verification|
  |Cosmos DB| | Cache   | |  Blob   | | RxNorm  | |Safety Val. |
  +---------+ +---------+ +---------+ +---------+ +------------+
       |           |          |            |          |
       +-----------+----------+------------+----------+
                             |
                             v
                  +---------------------+
                  |   Agent Synthesis   |
                  |  (Fusion + Rerank)  |
                  +---------------------+
                             |
                             v
                  +---------------------+
                  | Clinical            |
                  | Recommendation      |
                  | + Citations         |
                  | + Drug Alerts       |
                  | + Confidence Score  |
                  | + Audit Trail       |
                  +---------------------+
```

---

## Implementation Scope (Current State)

This repository currently implements a production-ready **core CDSS path**:
- FastAPI + Container Apps backend with Entra-authenticated APIs
- Five-agent orchestration (Patient History, Literature, Protocol, Drug Safety, Guardrails)
- Azure OpenAI + Azure AI Search + Cosmos DB + Blob + Document Intelligence integrations
- SSE-based streaming orchestration responses and persisted audit logs

The following items are **documented in design artifacts but not implemented in this repo/runtime path**:
- APIM / Front Door perimeter layer
- FHIR/DICOM interoperability path
- Service Bus/Event Hub/Azure Functions async event architecture
- Web PubSub/WebSocket transport (current transport is SSE)
- SQL cache-first drug safety workflow
- Text Analytics for Health enrichment pipeline

Use this README and `docs/architecture.md` as the source of truth for implemented behavior.

### Alignment Snapshot

| Area | Status | Notes |
|---|---|---|
| OpenAI / orchestration | Implemented | GPT-4o + GPT-4o-mini used by orchestrator/specialist agents |
| Azure AI Search | Implemented | Patient/protocol/literature indexes used by runtime APIs |
| Cosmos DB | Implemented | Patient data, ingestion status, audit + state persistence |
| Document Intelligence + Blob | Implemented | Ingestion pipeline uses DocIntel parsing + Blob-backed content flow |
| PubMed / OpenFDA / RxNorm | Implemented | Active external integrations in literature + drug safety paths |
| DrugBank | Partial | Optional/key-gated integration |
| Redis | Provisioned, partial usage | Not the active distributed limiter backend in current runtime |
| Streaming transport | Implemented (SSE) | Web PubSub/WebSocket not part of current runtime |
| APIM / Front Door | Not implemented | Not deployed by current IaC |
| FHIR / DICOM | Not implemented | Not integrated in current runtime |
| Service Bus / Event Hub / Functions | Not implemented | Ingestion/execution path is API/background-task driven |
| SQL cache-first DDI path | Not implemented | Drug safety flow is external API driven |

---

## Key Features

- **Multi-Agent Orchestration** -- Five specialized clinical agents coordinated by an intelligent orchestrator that decomposes complex queries and synthesizes evidence from multiple sources
- **Hybrid RAG Pipeline** -- BM25 lexical search + dense vector search + semantic reranking with Reciprocal Rank Fusion for maximum recall and precision
- **Real-Time PubMed Integration** -- Live access to 36M+ biomedical citations via the NCBI E-utilities API with intelligent caching and rate limiting
- **Drug Interaction Checking** -- Multi-source drug safety analysis using DrugBank, OpenFDA adverse event reports, and RxNorm drug normalization
- **Document Intelligence** -- Azure AI Document Intelligence for ingesting medical PDFs, lab reports, and clinical notes with layout-aware chunking
- **Cosmos DB Vector Search** -- DiskANN-powered vector search in Azure Cosmos DB for sub-millisecond similarity queries over patient records
- **Clinical Guardrails** -- Hallucination detection via citation verification, contraindication flagging, and safety validation before any recommendation is returned
- **HIPAA-Compliant Audit Trail** -- Every query, agent action, data access, and recommendation is logged with immutable audit records
- **Infrastructure as Code** -- Full Azure deployment via Bicep templates with environment-specific parameterization

---

## Architecture Overview

The system employs five specialized agents, each with distinct roles, tools, and model configurations:

### 1. Patient History Agent

| Property | Value |
|----------|-------|
| **Model** | GPT-4o-mini |
| **Tools** | Azure AI Search, Cosmos DB |
| **Role** | Retrieves and summarizes the patient's medical history, current medications, allergies, lab results, and problem list |

This agent queries the patient index in Azure AI Search and enriches the results with structured data from Cosmos DB. It produces a concise patient summary that contextualizes the clinical query.

### 2. Medical Literature Agent

| Property | Value |
|----------|-------|
| **Model** | GPT-4o |
| **Tools** | PubMed E-utilities API, Azure AI Search (cached literature) |
| **Role** | Searches biomedical literature for evidence relevant to the clinical question, prioritizing systematic reviews, meta-analyses, and clinical guidelines |

This agent constructs optimized MeSH-term queries for PubMed, retrieves abstracts, and cross-references them against a locally cached literature index. It returns ranked evidence with PMIDs and evidence grades.

### 3. Protocol Agent

| Property | Value |
|----------|-------|
| **Model** | GPT-4o-mini |
| **Tools** | Azure AI Search, Azure Blob Storage |
| **Role** | Retrieves institutional treatment protocols, clinical practice guidelines, and standard operating procedures relevant to the patient's conditions |

Protocols are ingested from PDF documents stored in Azure Blob Storage, chunked with layout-aware processing, and indexed in Azure AI Search with metadata filtering by specialty, condition, and evidence grade.

### 4. Drug Safety Agent

| Property | Value |
|----------|-------|
| **Model** | GPT-4o |
| **Tools** | DrugBank API, OpenFDA API, RxNorm API |
| **Role** | Analyzes the patient's current and proposed medications for drug-drug interactions, contraindications based on comorbidities, and required dose adjustments based on renal/hepatic function |

This agent normalizes drug names via RxNorm, queries DrugBank for interaction data, and enriches findings with OpenFDA adverse event frequency data. It flags critical interactions with severity levels.

### 5. Guardrails Agent

| Property | Value |
|----------|-------|
| **Model** | GPT-4o |
| **Tools** | Citation verification engine, safety validation rules |
| **Role** | Validates the synthesized recommendation by verifying all citations are real and support the claims made, checking for contraindications against patient data, and ensuring the response does not hallucinate treatments |

This agent acts as the final safety layer. It cross-references every cited PMID against PubMed, validates dosing recommendations against formulary data, and applies a configurable set of clinical safety rules.

---

## Tech Stack

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Language** | Python 3.12 | Core application language |
| **Web Framework** | FastAPI 0.115 | Async REST API with OpenAPI docs |
| **AI Orchestration** | Azure OpenAI (GPT-4o, GPT-4o-mini) | LLM inference for all agents |
| **Embeddings** | text-embedding-3-large (3072-dim) | Dense vector representations |
| **Vector Search** | Azure Cosmos DB (DiskANN) | Sub-ms vector similarity search |
| **Full-Text Search** | Azure AI Search | BM25 + vector hybrid search |
| **Document Processing** | Azure AI Document Intelligence | PDF/image medical document ingestion |
| **Blob Storage** | Azure Blob Storage | Protocol and document storage |
| **Audit & State Store** | Azure Cosmos DB | Patient profiles, conversation history, audit logs, ingestion state |
| **Caching / Throttling** | In-memory runtime (Redis provisioned) | Current runtime limiter/cache path is in-memory; Redis is provisioned but not the active limiter backend |
| **External APIs** | PubMed E-utilities, DrugBank, OpenFDA, RxNorm | Medical data sources |
| **Authentication** | Azure Entra ID (OAuth 2.0) | Service and user authentication |
| **Secrets** | Azure Key Vault | Secure credential management |
| **Monitoring** | Azure Application Insights + Log Analytics | Distributed tracing and metrics |
| **Containerization** | Docker | Application packaging |
| **IaC** | Azure Bicep | Infrastructure as Code |
| **Testing** | pytest, pytest-asyncio, pytest-cov | Comprehensive test suite |
| **Linting** | Ruff | Fast Python linting and formatting |
| **Type Checking** | mypy | Static type analysis |

---

## Project Structure

```
cdss-agentic-rag-main/                  # Repository root
├── src/                                # Backend source root
│   └── cdss/                           # Main Python package
│       ├── __init__.py                 # Package initializer
│       ├── agents/                     # Multi-agent orchestration layer
│       │   ├── base.py                 # Shared agent interface/base behavior
│       │   ├── orchestrator.py         # Coordinates specialist agent execution
│       │   ├── patient_history.py      # Patient context retrieval agent
│       │   ├── medical_literature.py   # PubMed + evidence retrieval agent
│       │   ├── protocol_agent.py       # Guideline/protocol reasoning agent
│       │   ├── drug_safety.py          # Interaction/safety analysis agent
│       │   └── guardrails.py           # Clinical safety/hallucination checks
│       ├── api/                        # FastAPI transport layer
│       │   ├── app.py                  # App factory, middleware wiring, lifespan
│       │   ├── routes.py               # All API endpoints (query, docs, search, etc.)
│       │   └── middleware.py           # Auth, rate limits, request tracing logic
│       ├── clients/                    # External/infra service adapters
│       │   ├── openai_client.py        # Azure OpenAI chat/embedding access
│       │   ├── search_client.py        # Azure AI Search retrieval operations
│       │   ├── cosmos_client.py        # Cosmos DB reads/writes + status persistence
│       │   ├── blob_storage_client.py  # Azure Blob read/write utilities
│       │   ├── document_intelligence_client.py # OCR/form extraction client
│       │   ├── keyvault_client.py      # Key Vault secret resolution helper
│       │   ├── pubmed_client.py        # NCBI PubMed E-utilities integration
│       │   ├── drugbank_client.py      # DrugBank integration adapter
│       │   ├── openfda_client.py       # OpenFDA integration adapter
│       │   └── rxnorm_client.py        # RxNorm normalization/lookup client
│       ├── core/                       # Shared app foundations
│       │   ├── config.py               # Pydantic settings and env binding
│       │   ├── models.py               # Domain DTOs and response models
│       │   ├── exceptions.py           # Typed exception hierarchy
│       │   └── logging.py              # Structured logging configuration
│       ├── ingestion/                  # Document ingestion pipeline package
│       │   └── pipeline.py             # Parse/chunk/index ingestion workflow
│       ├── rag/                        # Retrieval-augmented generation utilities
│       │   ├── chunker.py              # Clinical-aware text chunking
│       │   ├── embedder.py             # Embedding generation wrapper
│       │   ├── retriever.py            # Hybrid retrieval strategy
│       │   └── fusion.py               # Result fusion/ranking logic
│       ├── services/                   # Business service orchestrations
│       │   ├── query_service.py        # Main clinical query application service
│       │   └── ingestion_service.py    # Document ingestion service facade
│       ├── tools/                      # Operational utility scripts/modules
│       │   └── seed_sample_data.py     # In-network sample data bootstrap module
│       └── utils/                      # Shared utility helpers
├── frontend/                           # Production React + Vite SPA
│   ├── src/                            # Frontend source code
│   │   ├── components/                 # Reusable UI components
│   │   ├── pages/                      # Route/page-level containers
│   │   ├── hooks/                      # Custom React hooks
│   │   ├── stores/                     # Client state management stores
│   │   ├── styles/                     # Global and module styles
│   │   ├── theme/                      # Theme tokens/system configuration
│   │   └── mocks/                      # Mock handlers and local fixtures
│   ├── public/                         # Static public assets
│   │   └── mockServiceWorker.js        # MSW runtime worker asset
│   ├── docs/                           # Frontend-specific design/docs
│   ├── stories/                        # Storybook stories
│   ├── tests/visual/                   # UI visual regression/e2e tests
│   ├── package.json                    # Frontend scripts and dependencies
│   ├── playwright.config.ts            # Playwright test configuration
│   └── staticwebapp.config.json        # Azure Static Web Apps routing/auth config
├── tests/                              # Backend Python test suite
│   ├── conftest.py                     # Shared pytest fixtures
│   ├── unit/                           # Fast unit tests
│   │   ├── test_agents.py              # Agent-level unit coverage
│   │   ├── test_api.py                 # API behavior unit tests
│   │   ├── test_chunker.py             # Chunking logic tests
│   │   ├── test_clients.py             # Service client contract tests
│   │   ├── test_ingestion.py           # Ingestion service/pipeline tests
│   │   ├── test_models.py              # Core model validation tests
│   │   ├── test_orchestrator.py        # Orchestrator flow tests
│   │   ├── test_query_service.py       # Query service integration-style units
│   │   └── test_rag_pipeline.py        # RAG pipeline behavior tests
│   └── integration/                    # Cross-component integration tests
│       └── test_e2e.py                 # End-to-end backend integration checks
├── infra/                              # Infrastructure-as-code and operations
│   ├── bicep/                          # Azure deployment templates/params
│   │   ├── main.bicep                 # Canonical IaC template
│   │   ├── main.json                  # Compiled Bicep JSON artifact
│   │   ├── parameters.dev.json        # Dev environment parameters
│   │   ├── parameters.staging.json    # Staging environment parameters
│   │   └── parameters.prod.json       # Production environment parameters
│   └── scripts/                        # Deployment/bootstrap helper scripts
│       ├── bootstrap-deploy.sh         # End-to-end first-run bootstrap flow
│       ├── deploy.sh                   # Core infra + app deployment script
│       ├── setup-entra-spa-auth.sh     # Entra SPA/API app registration alignment
│       ├── fix-auth-config.sh          # Auth audience mismatch diagnosis/fix
│       ├── configure-pubmed-prod.sh    # PubMed Key Vault + runtime secret wiring
│       ├── ensure-openai-runtime-access.sh # OpenAI network accessibility guard for runtime calls
│       ├── ensure-cosmos-embedding-cache-policy.sh # Cosmos embedding cache policy helper
│       ├── create-search-indexes.sh    # Idempotent Azure AI Search index setup
│       ├── seed-data-infra-network.sh  # In-network data seeding execution
│       ├── seed-data.sh                # Legacy/local seeding script
│       ├── seed_data.py                # Python seed payload logic
│       ├── pin-containerapp-latest-ready.sh # Traffic pin helper for latest ready revision
│       └── populate-env.sh             # Generate env files from deployed resources
├── sample_data/                        # Sample datasets for UI/API validation
│   ├── sample_patient.json             # Canonical primary patient source payload
│   ├── sample_patients.json            # Additional patient variant fixtures (patient_1..patient_5)
│   ├── sample_query.json               # Example clinical query payload
│   ├── sample_response.json            # Example response payload
│   ├── sample_protocol.md              # Example treatment protocol content
│   ├── sample_protocol_upload.txt      # Upload-ready protocol validation sample
│   ├── sample_literature_upload.txt    # Upload-ready literature validation sample
│   └── sample_lab_report.txt           # Example uploaded lab report document
├── docs/                               # Project architecture/API docs
│   ├── architecture.md                 # System design documentation
│   └── api-reference.md                # API endpoint reference
├── .env.example                        # Root environment template
├── Dockerfile                          # Backend container build recipe
├── docker-compose.yml                  # Local multi-service compose stack
├── pyproject.toml                      # Python project metadata/dependencies
├── compact.md                          # Production API/system validation runbook
├── guide.md                            # Production UI-only validation runbook
└── README.md                           # Primary project documentation
```

---

## Prerequisites

- **Python 3.12+** -- Required for modern type hints and performance improvements
- **Azure Subscription** -- With permissions to create the required services (see [Azure Services Required](#azure-services-required))
- **Docker** -- For local development and containerized deployment
- **Azure CLI** -- For infrastructure deployment (`az` command)
- **Git** -- For version control

---

## Quick Start

## 1) Clone the repository

```bash
git clone https://github.com/your-org/cdss-agentic-rag.git
cd cdss-agentic-rag
```

## 2) Initialize deployment variables

```bash 
export ENV=prod
export RG=cdss-prod-rg
export LOCATION=eastus2
export SWA_NAME=cdss-frontend-prod
export SPA_APP_DISPLAY_NAME=cdss-frontend-spa
export API_APP_DISPLAY_NAME=cdss-api
export SCOPE_NAME=access_as_user
```

## 3) Verify prerequisites and Azure context

```bash
az --version
az bicep version
# az extension add --name containerapp --upgrade --yes
# az extension add --name staticwebapp --upgrade --yes

docker --version
docker buildx version

jq --version
python3 --version
# python --version || echo "python command missing (set alias to python3)"
npm --version
npx --version
git --version
curl --version

az login
az account show -o table
```

## 4) Set PubMed credentials (used in step 10)

```bash
# Option A: enter values interactively
read -r -s -p "PubMed API key: " CDSS_PUBMED_API_KEY; echo
read -r -p "PubMed contact email: " CDSS_PUBMED_EMAIL
export CDSS_PUBMED_API_KEY CDSS_PUBMED_EMAIL

# Option B: if values already exist in local .env, load them directly
# export CDSS_PUBMED_API_KEY="$(grep -E '^CDSS_PUBMED_API_KEY=' .env | cut -d= -f2-)"
# export CDSS_PUBMED_EMAIL="$(grep -E '^CDSS_PUBMED_EMAIL=' .env | cut -d= -f2-)"

# Verify values are set (prints only the email)
test -n "$CDSS_PUBMED_API_KEY" && test -n "$CDSS_PUBMED_EMAIL" && echo "PubMed vars loaded: $CDSS_PUBMED_EMAIL"
```

## 5) Deploy backend infrastructure and backend application

```bash
# Run bootstrap first. PubMed Key Vault secret wiring is done in step 11
# after RBAC preflight so this runbook succeeds cleanly end-to-end.
env -u CDSS_PUBMED_API_KEY -u CDSS_PUBMED_EMAIL \
  ./infra/scripts/bootstrap-deploy.sh "$ENV" "$RG" "$LOCATION"

# Optional: strict private-link mode only (skip automatic OpenAI network remediation)
# env -u CDSS_PUBMED_API_KEY -u CDSS_PUBMED_EMAIL \
#   CDSS_OPENAI_NETWORK_AUTOFIX=false ./infra/scripts/bootstrap-deploy.sh "$ENV" "$RG" "$LOCATION"
```

`bootstrap-deploy.sh` now performs idempotent Search bootstrap checks and skips costly Search public network toggles when index bootstrap is already complete.
It also runs `infra/scripts/ensure-openai-runtime-access.sh` by default to prevent OpenAI `403 Traffic is not from an approved private endpoint` runtime blockers.

## 6) Resolve deployed resource names

```bash
export APP=$(az containerapp list -g "$RG" --query "[?contains(name,'-api')].name | [0]" -o tsv)
export API_FQDN=$(az containerapp show -g "$RG" -n "$APP" --query properties.configuration.ingress.fqdn -o tsv)
export SEARCH_NAME=$(az search service list -g "$RG" --query "[0].name" -o tsv)
export OPENAI_NAME=$(az cognitiveservices account list -g "$RG" --query "[?kind=='OpenAI'].name | [0]" -o tsv)
export DOCINTEL_NAME=$(az cognitiveservices account list -g "$RG" --query "[?kind=='FormRecognizer'].name | [0]" -o tsv)
export KV_NAME=$(az keyvault list -g "$RG" --query "[0].name" -o tsv)
export KV_ID=$(az keyvault show -g "$RG" -n "$KV_NAME" --query id -o tsv)

printf "APP=%s\nAPI_FQDN=%s\nSEARCH_NAME=%s\nOPENAI_NAME=%s\nDOCINTEL_NAME=%s\nKV_NAME=%s\n" \
  "$APP" "$API_FQDN" "$SEARCH_NAME" "$OPENAI_NAME" "$DOCINTEL_NAME" "$KV_NAME"
```

## 6.1) Optional fallback for Key Vault RBAC failures

`configure-pubmed-prod.sh` now attempts automatic caller role assignment (`Key Vault Secrets Officer`) and retries secret writes.  
Use manual RBAC commands only if your account cannot create role assignments (missing Owner/User Access Administrator permissions).

## 7) Validate backend readiness

```bash
curl -i "https://${API_FQDN}/api/v1/health"

az cognitiveservices account show -g "$RG" -n "$OPENAI_NAME" \
  --query "{state:properties.provisioningState,pna:properties.publicNetworkAccess,defaultAction:properties.networkAcls.defaultAction}" -o table

az cognitiveservices account show -g "$RG" -n "$DOCINTEL_NAME" \
  --query "{state:properties.provisioningState,pna:properties.publicNetworkAccess}" -o table

az search service show -g "$RG" -n "$SEARCH_NAME" \
  --query "{state:provisioningState,pna:publicNetworkAccess}" -o table

az containerapp show -g "$RG" -n "$APP" \
  --query "properties.template.containers[0].env[?name=='CDSS_AUTH_ENABLED'||name=='CDSS_AUTH_TENANT_ID'||name=='CDSS_AUTH_AUDIENCE'||name=='CDSS_AUTH_REQUIRED_SCOPES'].[name,value]" \
  -o table
```

## 8) Optional recovery: ensure Azure AI Search indexes exist (only if step 4 failed before Search bootstrap completed)

```bash
SEARCH_NAME="${SEARCH_NAME:-$(az search service list -g "$RG" --query "[0].name" -o tsv)}"
ORIG_PNA="$(az search service show -g "$RG" -n "$SEARCH_NAME" --query publicNetworkAccess -o tsv)"

if [[ "$ORIG_PNA" != "Enabled" ]]; then
  az search service update -g "$RG" -n "$SEARCH_NAME" --public-network-access enabled
fi

./infra/scripts/create-search-indexes.sh "$RG" "$SEARCH_NAME"

if [[ "$ORIG_PNA" != "Enabled" ]]; then
  az search service update -g "$RG" -n "$SEARCH_NAME" --public-network-access disabled
fi
```

<!-- ```bash
SEARCH_ADMIN_KEY=$(az search admin-key show --service-name "$SEARCH_NAME" --resource-group "$RG" --query primaryKey -o tsv)
EXPECTED_INDEXES=("patient-records" "treatment-protocols" "medical-literature-cache")

CURRENT_INDEXES=$(AZURE_CORE_ONLY_SHOW_ERRORS=1 az rest \
  --method get \
  --url "https://${SEARCH_NAME}.search.windows.net/indexes?api-version=2024-05-01-preview" \
  --skip-authorization-header \
  --headers "api-key=${SEARCH_ADMIN_KEY}" \
  --query "value[].name" -o tsv || true)

MISSING=()
for idx in "${EXPECTED_INDEXES[@]}"; do
  if ! grep -qx "$idx" <<<"$CURRENT_INDEXES"; then
    MISSING+=("$idx")
  fi
done

if [[ ${#MISSING[@]} -eq 0 ]]; then
  echo "All required Search indexes already exist."
else
  echo "Missing indexes: ${MISSING[*]}"

  wait_search() {
    local expected_pna="$1"
    while true; do
      S=$(az search service show -g "$RG" -n "$SEARCH_NAME" --query provisioningState -o tsv)
      P=$(az search service show -g "$RG" -n "$SEARCH_NAME" --query publicNetworkAccess -o tsv)
      echo "state=$S pna=$P"
      [[ "$S" == "succeeded" && "$P" == "$expected_pna" ]] && break
      sleep 15
    done
  }

  ORIG_PNA=$(az search service show -g "$RG" -n "$SEARCH_NAME" --query publicNetworkAccess -o tsv)
  if [[ "$ORIG_PNA" != "Enabled" ]]; then
    az search service update -g "$RG" -n "$SEARCH_NAME" --public-network-access enabled
    wait_search "Enabled"
  fi

  ./infra/scripts/create-search-indexes.sh "$RG" "$SEARCH_NAME"

  if [[ "$ORIG_PNA" != "Enabled" ]]; then
    az search service update -g "$RG" -n "$SEARCH_NAME" --public-network-access disabled
    wait_search "Disabled"
  fi
fi
``` -->

## 9) Generate local environment files and seed sample data

```bash
./infra/scripts/populate-env.sh "$RG"
./infra/scripts/seed-data-infra-network.sh "$RG" "$APP"
```

Seeding now uses both `sample_data/sample_patient.json` (primary canonical profile) and
`sample_data/sample_patients.json` (additional patient fixtures), so the Patients workspace can validate multiple IDs.

## 10) Configure Entra SPA/API auth and backend audience alignment

```bash
./infra/scripts/setup-entra-spa-auth.sh \
  --resource-group "$RG" \
  --container-app-name "$APP" \
  --spa-app-display-name "$SPA_APP_DISPLAY_NAME" \
  --api-app-display-name "$API_APP_DISPLAY_NAME"
```

`setup-entra-spa-auth.sh` aligns `CDSS_AUTH_AUDIENCE` to the API app **client ID** (JWT `aud`) and keeps frontend token scope on the API identifier URI.

## 11) Configure PubMed credentials in deployed backend runtime

```bash
# If not already set in this shell:
# read -r -s -p "PubMed API key: " CDSS_PUBMED_API_KEY; echo
# read -r -p "PubMed contact email: " CDSS_PUBMED_EMAIL
# export CDSS_PUBMED_API_KEY CDSS_PUBMED_EMAIL

test -n "$CDSS_PUBMED_API_KEY" && test -n "$CDSS_PUBMED_EMAIL" && echo "PubMed vars loaded: $CDSS_PUBMED_EMAIL"

./infra/scripts/configure-pubmed-prod.sh "$RG" "$APP" "$KV_NAME"

# Optional: disable temporary Key Vault IP allowlist fallback if your runner already has private-link access.
# CDSS_KV_TEMP_IP_ALLOWLIST=false ./infra/scripts/configure-pubmed-prod.sh "$RG" "$APP" "$KV_NAME"

# If you hit a network restriction path (ForbiddenByConnection) right after RBAC was granted.
CDSS_KV_TEMP_IP_ALLOWLIST=true ./infra/scripts/configure-pubmed-prod.sh "$RG" "$APP" "$KV_NAME"


az containerapp show -g "$RG" -n "$APP" \
  --query "properties.template.containers[0].env[?name=='CDSS_PUBMED_API_KEY'||name=='CDSS_PUBMED_EMAIL'||name=='CDSS_PUBMED_BASE_URL'].{name:name,secretRef:secretRef,value:value}" \
  -o table
```

`configure-pubmed-prod.sh` now handles Key Vault `ForbiddenByConnection` automatically (temporary caller-IP allowlist with automatic rollback), so no manual Key Vault network commands are required.

## 12) Ensure Static Web App exists and fetch deployment values

```bash
az staticwebapp show --name "$SWA_NAME" --resource-group "$RG" >/dev/null 2>&1 || \
az staticwebapp create --name "$SWA_NAME" --resource-group "$RG" --location "$LOCATION" --sku Standard

export SWA_HOST=$(az staticwebapp show --name "$SWA_NAME" --resource-group "$RG" --query defaultHostname -o tsv)
export SWA_TOKEN=$(az staticwebapp secrets list --name "$SWA_NAME" --resource-group "$RG" --query properties.apiKey -o tsv)
echo "$SWA_HOST"
```

## 13) Set production-only redirect URIs for the SPA app

```bash
export SPA_CLIENT_ID=$(az ad app list --display-name "$SPA_APP_DISPLAY_NAME" --query "[0].appId" -o tsv)
export SPA_OBJECT_ID=$(az ad app show --id "$SPA_CLIENT_ID" --query id -o tsv)

az rest --method PATCH \
  --uri "https://graph.microsoft.com/v1.0/applications/${SPA_OBJECT_ID}" \
  --headers "Content-Type=application/json" \
  --body "{\"spa\":{\"redirectUris\":[\"https://${SWA_HOST}\",\"https://${SWA_HOST}/auth/callback\"]}}"
```

## 14) Configure backend CORS for the production frontend origin

```bash
az containerapp ingress cors update -g "$RG" -n "$APP" \
  --allowed-origins "https://${SWA_HOST}"
```

## 15) Create frontend production environment file

```bash
export TENANT_ID=$(az account show --query tenantId -o tsv)
export API_CLIENT_ID="${API_CLIENT_ID:-$(az ad app list --display-name "$API_APP_DISPLAY_NAME" --query "[0].appId" -o tsv)}"
export API_IDENTIFIER_URI=$(az ad app show --id "$API_CLIENT_ID" --query "identifierUris[0]" -o tsv)
export API_AUDIENCE=$(az containerapp show -g "$RG" -n "$APP" --query "properties.template.containers[0].env[?name=='CDSS_AUTH_AUDIENCE'].value | [0]" -o tsv)
export API_SCOPE="${API_IDENTIFIER_URI}/${SCOPE_NAME}"
export WEBPUBSUB_NAME=$(az resource list -g "$RG" --resource-type "Microsoft.SignalRService/webPubSub" --query "[0].name" -o tsv)
if [[ -n "$WEBPUBSUB_NAME" ]]; then
  export VITE_WS_ENDPOINT_VALUE="wss://${WEBPUBSUB_NAME}.webpubsub.azure.com"
else
  export VITE_WS_ENDPOINT_VALUE="wss://${API_FQDN}"
fi

cat > frontend/.env.production <<EOF
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=https://${API_FQDN}/api
VITE_AZURE_CLIENT_ID=${SPA_CLIENT_ID}
VITE_AZURE_TENANT_ID=${TENANT_ID}
VITE_AZURE_AUTHORITY=https://login.microsoftonline.com/${TENANT_ID}
VITE_API_SCOPE=${API_SCOPE}
VITE_REDIRECT_URI=https://${SWA_HOST}
VITE_POST_LOGOUT_URI=https://${SWA_HOST}
VITE_WS_ENDPOINT=${VITE_WS_ENDPOINT_VALUE}
VITE_ENVIRONMENT=production
EOF
```

## 16) Build and deploy frontend to Azure Static Web Apps

```bash
cd frontend
npm ci
npm run build
cp staticwebapp.config.json dist/staticwebapp.config.json
# grep -R "localhost" dist/ && exit 1 || true
npx @azure/static-web-apps-cli deploy ./dist --deployment-token "$SWA_TOKEN" --env production
cd ..
```

## 17) Validate authentication and backend APIs with bearer token

```bash
export TOKEN=$(az account get-access-token --scope "$API_SCOPE" --query accessToken -o tsv)

curl -i -H "Authorization: Bearer $TOKEN" \
  "https://${API_FQDN}/api/v1/patients?search=P0&page=1&limit=10"

curl -i -N \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"text":"Summarize care priorities for patient_12345"}' \
  "https://${API_FQDN}/api/v1/query/stream"
```

## 18) Validate document ingestion and retrieval APIs

```bash
export DOC_ID=$(curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample_data/sample_lab_report.txt;type=text/plain" \
  -F "document_type=lab_report" \
  "https://${API_FQDN}/api/v1/documents/ingest" | jq -r '.document_id')

curl -s -H "Authorization: Bearer $TOKEN" \
  "https://${API_FQDN}/api/v1/documents/${DOC_ID}/status" | jq

curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query":"type 2 diabetes CKD stage 3","max_results":5}' \
  "https://${API_FQDN}/api/v1/search/literature" | jq

curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query":"hypertension protocol","max_results":5}' \
  "https://${API_FQDN}/api/v1/search/protocols" | jq
```

### Recommended test queries (for upload-ready docs)

If you uploaded `sample_data/sample_protocol_upload.txt` and `sample_data/sample_literature_upload.txt`,
use these queries to verify index retrieval quality and phrase matching:

```bash
# Protocol retrieval probes (expected: protocol-oriented hits)
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query":"SGLT2 inhibitor CKD stage 3 monitoring cadence","max_results":5}' \
  "https://${API_FQDN}/api/v1/search/protocols" | jq

curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query":"eGFR decline more than 5 mL/min/1.73m2 per year referral criteria","max_results":5}' \
  "https://${API_FQDN}/api/v1/search/protocols" | jq

# Literature retrieval probes (expected: literature-oriented hits)
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query":"atrial fibrillation CKD stage 3 major bleeding hazard ratio","max_results":5}' \
  "https://${API_FQDN}/api/v1/search/literature" | jq

curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query":"DOAC versus warfarin intracranial hemorrhage propensity-score matching","max_results":5}' \
  "https://${API_FQDN}/api/v1/search/literature" | jq
```

Expected behavior:
- Protocol queries should return recommendations, monitoring cadence, and escalation trigger language.
- Literature queries should return comparative-effectiveness and safety evidence terms from the uploaded article text.

## 19) Validate production frontend end-to-end in browser

```bash
curl -I "https://${SWA_HOST}"
echo "https://${SWA_HOST}"
```

1. Open `https://${SWA_HOST}`.
2. Sign in with Entra ID.
3. Load patient list.
4. Run Clinical Workspace orchestration query.
5. Verify streaming response updates in UI.
6. Upload a document and verify completion.
7. Run literature and protocol searches.

## 20) Final production checks

```bash
az containerapp show -g "$RG" -n "$APP" \
  --query "properties.template.containers[0].env[?name=='CDSS_AUTH_ENABLED'||name=='CDSS_AUTH_AUDIENCE'||name=='CDSS_AUTH_REQUIRED_SCOPES'].[name,value]" \
  -o table

az containerapp ingress cors show -g "$RG" -n "$APP" -o json

curl -i -X OPTIONS \
  -H "Origin: https://${SWA_HOST}" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Authorization,Content-Type" \
  "https://${API_FQDN}/api/v1/query/stream"

az containerapp revision list -g "$RG" -n "$APP" -o table
```

## 21) Authentication Troubleshooting

If you encounter **401 Unauthorized** errors with "Invalid or expired bearer token":

### Quick Diagnosis

```bash
# Check current auth configuration
az containerapp show -g "$RG" -n "$APP" \
  --query "properties.template.containers[0].env[?name=='CDSS_AUTH_ENABLED'||name=='CDSS_AUTH_TENANT_ID'||name=='CDSS_AUTH_AUDIENCE'||name=='CDSS_AUTH_REQUIRED_SCOPES'].[name,value]" \
  -o table

# Expected values:
# CDSS_AUTH_ENABLED        true
# CDSS_AUTH_TENANT_ID      <your-tenant-id>
# CDSS_AUTH_AUDIENCE       <API app client ID GUID>
# CDSS_AUTH_REQUIRED_SCOPES ["access_as_user"]
```

### Root Cause: Audience Mismatch

The 401 error typically occurs when `CDSS_AUTH_AUDIENCE` is empty or doesn't match the token's `aud` claim:

- **Frontend requests token** with scope `api://cdss-api/access_as_user`
- **Entra ID issues token** with `aud` = `<API app client ID GUID>`
- **Backend validates** against `CDSS_AUTH_AUDIENCE` value
- **Mismatch** → JWT validation fails → 401

### Quick Fix

```bash
export API_CLIENT_ID=$(az ad app list --display-name "$API_APP_DISPLAY_NAME" --query "[0].appId" -o tsv)

# Update the auth configuration
az containerapp update -g "$RG" -n "$APP" \
  --set-env-vars \
    "CDSS_AUTH_ENABLED=true" \
    "CDSS_AUTH_TENANT_ID=$(az account show --query tenantId -o tsv)" \
    "CDSS_AUTH_AUDIENCE=${API_CLIENT_ID}" \
    'CDSS_AUTH_REQUIRED_SCOPES=["access_as_user"]'
```

### Automated Fix Script

```bash
# Diagnose and fix authentication issues
./infra/scripts/fix-auth-config.sh --resource-group "$RG" --dry-run  # Preview changes
./infra/scripts/fix-auth-config.sh --resource-group "$RG"            # Apply fixes
```

### Verify the Fix

```bash
export API_CLIENT_ID=$(az ad app list --display-name "$API_APP_DISPLAY_NAME" --query "[0].appId" -o tsv)
export API_IDENTIFIER_URI=$(az ad app show --id "$API_CLIENT_ID" --query "identifierUris[0]" -o tsv)

# Get a token with the correct API identifier URI scope
export TOKEN=$(az account get-access-token --scope "${API_IDENTIFIER_URI}/access_as_user" --query accessToken -o tsv)

# Test authenticated endpoint
curl -H "Authorization: Bearer $TOKEN" \
  "https://${API_FQDN}/api/v1/patients?limit=1"
```
---

## Azure Services Required

| Service | SKU / Tier | Purpose |
|---------|-----------|---------|
| **Azure OpenAI** | Standard (S0) | GPT-4o and GPT-4o-mini for agent inference; text-embedding-3-large for embeddings |
| **Azure AI Search** | Standard (S1) | Hybrid BM25 + vector search over patient records, protocols, and cached literature |
| **Azure Cosmos DB** | Serverless | Patient record storage with DiskANN vector search capability |
| **Azure Blob Storage** | Standard LRS | Storage for medical documents, protocols, and ingested files |
| **Azure AI Document Intelligence** | Standard (S0) | PDF and image text extraction with layout understanding |
| **Azure Cache for Redis** | Basic (C1) | Provisioned; currently optional (runtime limiter/cache path is in-memory) |
| **Azure Key Vault** | Standard | Secure storage for API keys, connection strings, and certificates |
| **Azure Container Apps** | Consumption / Dedicated | Container hosting for the FastAPI backend |
| **Azure Container Registry** | Basic | Docker image storage for backend deployments |
| **Azure Log Analytics + App Insights** | Pay-as-you-go | Metrics, traces, diagnostics |
| **Azure Static Web Apps** | Free/Standard | Frontend hosting and Entra auth integration |
| **Azure Entra ID** | Free tier | OAuth 2.0 authentication and RBAC |

---

## Data Flow

The journey of a patient clinical query through the system follows seven steps:

### Step 1: Query Reception

The clinician submits a natural-language clinical question via the REST API, optionally referencing a patient by ID. The request is authenticated via Azure Entra ID, validated, and assigned a unique query ID. An audit record is created.

### Step 2: Query Decomposition

The Orchestrator Agent analyzes the query and determines which specialized agents to invoke. For a query about diabetes treatment with CKD, it would activate the Patient History Agent, Medical Literature Agent, Protocol Agent, and Drug Safety Agent.

### Step 3: Parallel Agent Execution

The orchestrator dispatches tasks to the selected agents concurrently. Each agent independently queries its data sources:

- **Patient History Agent** retrieves the patient's record from Azure AI Search and Cosmos DB
- **Medical Literature Agent** searches PubMed for relevant clinical evidence
- **Protocol Agent** retrieves applicable treatment guidelines
- **Drug Safety Agent** checks current and proposed medications for interactions

### Step 4: Evidence Retrieval and Ranking

Each agent's RAG pipeline performs hybrid retrieval (BM25 + vector search), applies semantic reranking, and returns the top-k results with relevance scores. Results are deduplicated across agents via Reciprocal Rank Fusion.

### Step 5: Agent Synthesis

The Orchestrator Agent receives all agent outputs and synthesizes them into a unified clinical recommendation. It resolves conflicts between sources, assigns an overall confidence score, and generates a structured response with assessment, recommendations, and supporting evidence.

### Step 6: Guardrails Validation

The Guardrails Agent validates the synthesized response by:
- Verifying every cited PMID exists in PubMed and supports the claim
- Checking that no recommended drug is contraindicated for the patient
- Flagging any recommendation that lacks sufficient evidence support
- Ensuring dosing recommendations fall within safe ranges

### Step 7: Response Delivery

The validated response is returned to the clinician with a confidence score, citations, drug alerts, and disclaimers. The complete interaction -- including all agent inputs, outputs, latencies, and the final recommendation -- is written to the audit trail.

---

## Security and Compliance

This system is designed with HIPAA compliance requirements in mind:

### Data Protection

- **Encryption at rest** -- All Azure services configured with AES-256 encryption using customer-managed keys in Azure Key Vault
- **Encryption in transit** -- TLS 1.3 enforced on all API endpoints and inter-service communication
- **PHI minimization** -- Patient data is referenced by opaque IDs; full records are never included in LLM prompts beyond what is clinically necessary

### Access Control

- **Azure Entra ID** -- OAuth 2.0 / OpenID Connect for user and service authentication
- **Role-Based Access Control (RBAC)** -- Clinician, Pharmacist, Admin, and Auditor roles with granular permissions
- **API key rotation** -- Automated key rotation via Azure Key Vault with zero-downtime rollover
- **Network isolation** -- VNet + private endpoints are configured for core data/AI services in production; bootstrap can optionally apply OpenAI runtime accessibility remediation to prevent `403` startup/runtime blockers

### Audit and Logging

- **Immutable audit trail** -- Every query, data access, and recommendation persisted in the audit store (Cosmos-backed runtime path) with tamper-evident hashing metadata
- **Structured logging** -- JSON-formatted logs with correlation IDs shipped to Azure Application Insights
- **Retention policies** -- Configurable log retention (default: 7 years for HIPAA)
- **Audit API** -- Queryable audit endpoint for compliance officers (requires admin role)

### Clinical Safety

- **Hallucination detection** -- Citation verification against PubMed ensures recommendations are evidence-based
- **Contraindication checking** -- Automated flagging of drug-disease and drug-drug contraindications
- **Confidence scoring** -- Every recommendation includes a confidence score; low-confidence responses include explicit uncertainty disclaimers
- **Human-in-the-loop** -- The system provides decision support only; it never autonomously initiates treatment

---

## Running Tests

```bash
# Run the full test suite with coverage
pytest tests/ -v --cov=cdss --cov-report=term-missing

# Run only unit tests
pytest tests/unit/ -v

# Run integration coverage tests (mocked external dependencies)
pytest tests/integration/ -v

# Run the integration E2E workflow test module
pytest tests/integration/test_e2e.py -v

# Run with parallel execution
pytest tests/ -v -n auto --cov=cdss

# Generate HTML coverage report
pytest tests/ --cov=cdss --cov-report=html
open htmlcov/index.html
```
---

## Infrastructure Deployment

The entire Azure infrastructure is defined as code using Azure Bicep templates.
### What gets deployed

The Bicep templates provision and configure the implemented runtime stack, including:

- Virtual Network with subnets and private endpoints
- Azure OpenAI with model deployments (GPT-4o, GPT-4o-mini, text-embedding-3-large)
- Azure AI Search with index definitions and skillsets
- Cosmos DB account with vector indexing policy
- Container Apps managed environment + backend container app
- All supporting services (Key Vault, Redis, Storage, App Insights, ACR)

Not currently provisioned in this repo's IaC path: APIM, Front Door/WAF, FHIR/DICOM services, Service Bus/Event Hub/Functions pipeline, Web PubSub.

---

## Configuration

The application is configured via environment variables. Copy `.env.example` to `.env` and set the following:

### Required Variables

| Variable | Description |
|----------|-------------|
| `CDSS_AZURE_OPENAI_ENDPOINT` | Azure OpenAI service endpoint URL |
| `CDSS_AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `CDSS_AZURE_OPENAI_DEPLOYMENT_NAME` | GPT-4o model deployment name |
| `CDSS_AZURE_OPENAI_MINI_DEPLOYMENT_NAME` | GPT-4o-mini model deployment name |
| `CDSS_AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | text-embedding-3-large deployment name |
| `CDSS_AZURE_SEARCH_ENDPOINT` | Azure AI Search service endpoint URL |
| `CDSS_AZURE_SEARCH_API_KEY` | Azure AI Search admin API key |
| `CDSS_AZURE_SEARCH_PATIENT_RECORDS_INDEX` | Patient records index name (default: `patient-records`) |
| `CDSS_AZURE_SEARCH_TREATMENT_PROTOCOLS_INDEX` | Treatment protocols index name (default: `treatment-protocols`) |
| `CDSS_AZURE_SEARCH_MEDICAL_LITERATURE_INDEX` | Literature index name (default: `medical-literature-cache`) |
| `CDSS_AZURE_COSMOS_ENDPOINT` | Azure Cosmos DB endpoint URL |
| `CDSS_AZURE_COSMOS_KEY` | Azure Cosmos DB primary key (optional when Entra ID is enabled) |
| `CDSS_AZURE_COSMOS_DATABASE_NAME` | Cosmos DB database name (default: `cdss-db`) |
| `CDSS_AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Azure Document Intelligence endpoint |
| `CDSS_AZURE_DOCUMENT_INTELLIGENCE_KEY` | Azure Document Intelligence API key |
| `CDSS_AZURE_BLOB_CONNECTION_STRING` | Azure Blob Storage connection string |
| `CDSS_AZURE_BLOB_ENDPOINT` | Azure Blob Storage endpoint URL |
| `CDSS_AZURE_KEY_VAULT_URL` | Azure Key Vault URL |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CDSS_PUBMED_API_KEY` | `None` | NCBI API key for higher PubMed rate limits |
| `CDSS_REDIS_URL` | `redis://localhost:6379/0` | Provisioned Redis URL (currently optional; distributed limiter/cache path is not required for runtime) |
| `CDSS_DRUGBANK_API_KEY` | `None` | DrugBank API key for drug interaction data |
| `CDSS_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `CDSS_CORS_ORIGINS` | `["http://localhost:3000","http://localhost:3001"]` | Allowed CORS origins |
| `CDSS_AUTH_ENABLED` | `false` | Enable Entra ID JWT validation middleware |
| `CDSS_AUTH_TENANT_ID` | `None` | Entra tenant ID for JWT issuer/JWKS |
| `CDSS_AUTH_AUDIENCE` | `None` | Entra API audience (Application ID URI/client ID) |
| `MAX_CONCURRENT_AGENTS` | `5` | Maximum parallel agent executions |
| `RAG_TOP_K` | `10` | Number of documents to retrieve per query |
| `RAG_RERANK_TOP_N` | `5` | Number of documents after reranking |
| `EMBEDDING_DIMENSIONS` | `3072` | Embedding vector dimensions |
| `CHUNK_SIZE` | `512` | Document chunk size in tokens |
| `CHUNK_OVERLAP` | `64` | Overlap between document chunks |
| `PUBMED_CACHE_TTL` | `86400` | PubMed cache TTL in seconds (24h) |
| `AUDIT_LOG_RETENTION_DAYS` | `2555` | Audit log retention (7 years) |

---

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Empty `CDSS_AUTH_AUDIENCE` | Bicep default is empty | Set to API app client ID (GUID) |
| 503 Service Unavailable | Auth enabled but config incomplete | Check tenant ID and audience |
| CORS preflight fails | Frontend origin not allowed | Add SWA hostname to CORS |
| Token has wrong audience | Backend uses API identifier URI instead of app client ID | Set `CDSS_AUTH_AUDIENCE` to API app client ID |
| PubMed configure fails with `ForbiddenByRbac` | Deployer cannot write Key Vault secrets and cannot self-assign role | Grant `Key Vault Secrets Officer` on the vault to the deployer, then rerun step 10 |

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes and add tests
4. Run the test suite (`pytest tests/ -v --cov=cdss`)
5. Run linting and type checks (`ruff check . && mypy src/`)
6. Commit your changes (`git commit -m "Add your feature"`)
7. Push to the branch (`git push origin feature/your-feature`)
8. Open a Pull Request

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Disclaimer

> **This system is for research and educational purposes only. It is not approved for clinical use and has not been validated in a clinical setting. The recommendations generated by this system should not be used as the sole basis for clinical decisions. Always consult qualified healthcare professionals for medical advice, diagnosis, and treatment. The authors and contributors assume no liability for any actions taken based on the output of this system.**
