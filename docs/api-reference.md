# API Reference

**Clinical Decision Support System (CDSS) -- REST API v1**

Base URL: `https://<your-deployment>.azurewebsites.net/api/v1`
Local Development: `http://localhost:8000/api/v1`

All endpoints require authentication via Azure Entra ID OAuth 2.0 Bearer token unless otherwise noted.

---

## Table of Contents

- [Authentication](#authentication)
- [POST /query](#post-query)
- [POST /query/stream](#post-querystream)
- [GET /patients/{id}](#get-patientsid)
- [POST /documents/ingest](#post-documentsingest)
- [POST /drugs/interactions](#post-drugsinteractions)
- [POST /search/literature](#post-searchliterature)
- [POST /search/protocols](#post-searchprotocols)
- [GET /health](#get-health)
- [GET /audit](#get-audit)
- [Error Responses](#error-responses)

---

## Authentication

All API requests (except `/health`) require a valid OAuth 2.0 Bearer token issued by Azure Entra ID.

**Header:**
```
Authorization: Bearer <access_token>
```

**Required Scopes:**
| Scope | Description |
|-------|-------------|
| `cdss.query` | Submit clinical queries |
| `cdss.patients.read` | Read patient data |
| `cdss.documents.write` | Ingest documents |
| `cdss.drugs.read` | Check drug interactions |
| `cdss.search` | Search literature and protocols |
| `cdss.audit.read` | Read audit trail (admin only) |

---

## POST /query

Submit a clinical query for multi-agent analysis. The system orchestrates all five agents to produce an evidence-based clinical recommendation.

### Request

**Content-Type:** `application/json`
**Required Scope:** `cdss.query`

```json
{
  "text": "string (required) -- The clinical question in natural language",
  "patient_id": "string (required) -- Patient identifier to load context",
  "session_id": "string | null (optional) -- Session ID for conversation continuity",
  "context": {
    "requesting_provider": "string (optional) -- Name of requesting clinician",
    "provider_role": "string (optional) -- Role (e.g., 'Primary Care Physician')",
    "clinical_setting": "string (optional) -- 'inpatient' | 'outpatient' | 'emergency'",
    "urgency": "string (optional) -- 'routine' | 'urgent' | 'emergent'"
  },
  "preferences": {
    "include_literature": "boolean (optional, default: true)",
    "include_protocols": "boolean (optional, default: true)",
    "include_drug_interactions": "boolean (optional, default: true)",
    "max_literature_results": "integer (optional, default: 10)",
    "evidence_level_minimum": "string (optional) -- 'high' | 'moderate' | 'low'",
    "response_detail": "string (optional) -- 'brief' | 'standard' | 'comprehensive'"
  }
}
```

### Response (200 OK)

```json
{
  "query_id": "string -- Unique query identifier",
  "session_id": "string -- Session identifier",
  "patient_id": "string -- Patient identifier",
  "status": "string -- 'completed' | 'partial' | 'failed'",
  "created_at": "string -- ISO 8601 timestamp",
  "completed_at": "string -- ISO 8601 timestamp",
  "total_latency_ms": "integer -- Total processing time in milliseconds",
  "clinical_response": {
    "assessment": "string -- Clinical assessment summary",
    "recommendation": "string -- Evidence-based recommendation (Markdown)",
    "evidence_summary": "string -- Summary of supporting evidence",
    "confidence_score": "number -- 0.0 to 1.0",
    "confidence_rationale": "string -- Explanation of confidence level"
  },
  "drug_alerts": [
    {
      "alert_id": "string",
      "severity": "string -- 'critical' | 'major' | 'moderate' | 'minor'",
      "type": "string -- 'drug-drug' | 'drug-disease' | 'drug-allergy' | 'dose-adjustment'",
      "category": "string -- Alert category",
      "description": "string -- Alert description",
      "recommendation": "string -- Recommended action",
      "source": "string -- Data source for the alert",
      "evidence_level": "string -- 'high' | 'moderate' | 'low'"
    }
  ],
  "citations": [
    {
      "citation_id": "string",
      "source_type": "string -- 'pubmed' | 'clinical_guideline' | 'protocol' | 'drug_label'",
      "pmid": "string | null -- PubMed ID if applicable",
      "title": "string",
      "authors": "string | null",
      "journal": "string | null",
      "year": "integer",
      "doi": "string | null",
      "relevance_score": "number -- 0.0 to 1.0",
      "used_in_recommendation": "boolean",
      "claim_supported": "string -- The claim this citation supports"
    }
  ],
  "guardrails_report": {
    "status": "string -- 'passed' | 'passed_with_notes' | 'failed'",
    "checks_performed": [
      {
        "check": "string -- Check name",
        "status": "string -- 'passed' | 'passed_with_notes' | 'failed'",
        "details": "string -- Check details"
      }
    ]
  },
  "agent_outputs": [
    {
      "agent": "string -- Agent name",
      "model": "string -- Model used",
      "status": "string -- 'completed' | 'failed' | 'timeout'",
      "latency_ms": "integer",
      "tokens_used": {
        "prompt": "integer",
        "completion": "integer",
        "total": "integer"
      },
      "sources_retrieved": "integer",
      "summary": "string -- Agent output summary"
    }
  ],
  "disclaimers": ["string -- Legal and clinical disclaimers"]
}
```

### Example

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "text": "What are the treatment options for this patient'\''s uncontrolled diabetes given their CKD stage 3?",
    "patient_id": "patient_12345"
  }'
```

---

## POST /query/stream

Submit a clinical query with Server-Sent Events (SSE) streaming response. Provides real-time updates as each agent completes its work.

### Request

Same as [POST /query](#post-query).

**Accept:** `text/event-stream`

### Response (200 OK -- SSE Stream)

The response is a stream of Server-Sent Events. Each event has a `type` field indicating the event kind.

```
event: agent_started
data: {"agent": "patient_history", "timestamp": "2026-02-15T14:32:10.500Z"}

event: agent_completed
data: {"agent": "patient_history", "latency_ms": 1245, "summary": "..."}

event: agent_started
data: {"agent": "medical_literature", "timestamp": "2026-02-15T14:32:10.500Z"}

event: agent_completed
data: {"agent": "medical_literature", "latency_ms": 3892, "sources_retrieved": 47}

event: synthesis_started
data: {"timestamp": "2026-02-15T14:32:14.500Z"}

event: recommendation_chunk
data: {"content": "Based on current evidence, the following treatment modifications..."}

event: recommendation_chunk
data: {"content": "1. **SGLT2 Inhibitor Initiation (First Priority):**..."}

event: guardrails_completed
data: {"status": "passed", "checks_passed": 5, "checks_failed": 0}

event: completed
data: {"query_id": "q_a1b2c3d4", "total_latency_ms": 8742, "confidence_score": 0.87}
```

### Event Types

| Event Type | Description |
|------------|-------------|
| `agent_started` | An agent has begun processing |
| `agent_completed` | An agent has finished with summary |
| `agent_failed` | An agent encountered an error |
| `synthesis_started` | Orchestrator is synthesizing results |
| `recommendation_chunk` | Partial recommendation text |
| `drug_alert` | A drug alert was generated |
| `guardrails_completed` | Guardrails validation finished |
| `completed` | Full processing complete |
| `error` | An error occurred |

---

## GET /patients/{id}

Retrieve a patient profile with full medical history.

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Patient identifier (e.g., `patient_12345`) |

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_labs` | boolean | `true` | Include laboratory results |
| `include_vitals` | boolean | `true` | Include vital signs |
| `include_history` | boolean | `true` | Include surgical/social/family history |
| `labs_limit` | integer | `10` | Maximum number of lab results per test |

### Response (200 OK)

Returns the full patient profile in the format shown in `sample_data/sample_patient.json`.

### Example

```bash
curl -X GET "http://localhost:8000/api/v1/patients/patient_12345?include_labs=true&labs_limit=5" \
  -H "Authorization: Bearer $TOKEN"
```

### Error Responses

| Status | Description |
|--------|-------------|
| 404 | Patient not found |
| 403 | Insufficient permissions to access patient record |

---

## POST /documents/ingest

Ingest a medical document (PDF, DOCX, or image) into the RAG pipeline. The document is processed through Azure AI Document Intelligence, chunked, embedded, and indexed.

### Request

**Content-Type:** `multipart/form-data`
**Required Scope:** `cdss.documents.write`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | The document file (PDF, DOCX, PNG, JPG, TIFF) |
| `document_type` | string | Yes | `protocol` \| `guideline` \| `lab_report` \| `clinical_note` \| `research_article` |
| `metadata` | JSON string | No | Additional metadata (specialty, condition, author, version) |

### Response (202 Accepted)

```json
{
  "document_id": "string -- Unique document identifier",
  "status": "string -- 'processing' | 'queued'",
  "message": "string -- Status message",
  "file_name": "string -- Original file name",
  "file_size_bytes": "integer",
  "document_type": "string",
  "chunks_estimated": "integer -- Estimated number of chunks",
  "estimated_completion_seconds": "integer",
  "status_url": "string -- URL to poll for processing status"
}
```

### Example

```bash
curl -X POST http://localhost:8000/api/v1/documents/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/clinical_guideline.pdf" \
  -F "document_type=protocol" \
  -F 'metadata={"specialty": "endocrinology", "condition": "type_2_diabetes", "version": "2026-v1"}'
```

### Checking Ingestion Status

```bash
curl -X GET "http://localhost:8000/api/v1/documents/doc_m4n5o6/status" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "document_id": "doc_m4n5o6",
  "status": "completed",
  "chunks_created": 24,
  "chunks_indexed": 24,
  "processing_time_seconds": 38,
  "errors": []
}
```

### Supported File Types

| Format | Max Size | Notes |
|--------|----------|-------|
| PDF | 50 MB | Supports scanned PDFs via OCR |
| DOCX | 25 MB | Microsoft Word documents |
| PNG | 10 MB | Image documents (OCR applied) |
| JPG/JPEG | 10 MB | Image documents (OCR applied) |
| TIFF | 20 MB | Multi-page TIFF supported |

---

## POST /drugs/interactions

Check drug-drug interactions for a list of medications, optionally in the context of a patient's conditions and renal/hepatic function.

### Request

**Content-Type:** `application/json`
**Required Scope:** `cdss.drugs.read`

```json
{
  "medications": [
    {
      "name": "string (required) -- Drug name",
      "rxnorm_cui": "string (optional) -- RxNorm CUI for precise identification",
      "dose": "string (optional) -- Dose with unit (e.g., '500mg')",
      "frequency": "string (optional) -- Frequency (e.g., 'BID', 'QD')",
      "route": "string (optional) -- Route (e.g., 'oral', 'IV')"
    }
  ],
  "patient_id": "string | null (optional) -- Patient ID for context-aware checking",
  "include_severity": ["string (optional) -- Filter by severity: 'critical', 'major', 'moderate', 'minor'"],
  "include_openfda_events": "boolean (optional, default: false) -- Include OpenFDA adverse event frequency data"
}
```

### Response (200 OK)

```json
{
  "interaction_check_id": "string",
  "timestamp": "string -- ISO 8601",
  "medications_checked": "integer",
  "interactions_found": "integer",
  "alerts": [
    {
      "alert_id": "string",
      "severity": "string -- 'critical' | 'major' | 'moderate' | 'minor'",
      "type": "string -- 'drug-drug' | 'drug-disease' | 'drug-allergy' | 'drug-food'",
      "category": "string",
      "drugs": ["string -- Drug names involved"],
      "rxnorm_cuis": ["string -- RxNorm CUIs"],
      "condition": "string | null -- Related condition if drug-disease",
      "description": "string",
      "mechanism": "string -- Pharmacological mechanism",
      "recommendation": "string",
      "source": "string -- Data source",
      "evidence_level": "string -- 'high' | 'moderate' | 'low'",
      "openfda_event_count": "integer | null -- Adverse event reports if requested"
    }
  ],
  "patient_context": {
    "conditions_considered": ["string -- Conditions checked for drug-disease interactions"],
    "allergies_considered": ["string -- Allergies checked"],
    "renal_function": {
      "egfr": "number | null",
      "adjustments_applied": "boolean"
    }
  }
}
```

### Example

```bash
curl -X POST http://localhost:8000/api/v1/drugs/interactions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "medications": [
      {"name": "metformin", "rxnorm_cui": "6809", "dose": "500mg", "frequency": "BID"},
      {"name": "lisinopril", "rxnorm_cui": "29046", "dose": "10mg", "frequency": "QD"},
      {"name": "empagliflozin", "rxnorm_cui": "1545653", "dose": "10mg", "frequency": "QD"}
    ],
    "patient_id": "patient_12345",
    "include_openfda_events": true
  }'
```

---

## POST /search/literature

Search PubMed and cached medical literature for articles relevant to a clinical question.

### Request

**Content-Type:** `application/json`
**Required Scope:** `cdss.search`

```json
{
  "query": "string (required) -- Search query in natural language or MeSH terms",
  "max_results": "integer (optional, default: 10, max: 100)",
  "date_range": {
    "start": "string (optional) -- ISO 8601 date (e.g., '2020-01-01')",
    "end": "string (optional) -- ISO 8601 date (e.g., '2026-01-01')"
  },
  "article_types": ["string (optional) -- Filter by type: 'meta-analysis', 'systematic-review', 'randomized-controlled-trial', 'clinical-guideline', 'cohort-study', 'case-report'"],
  "journals": ["string (optional) -- Filter by journal name"],
  "mesh_terms": ["string (optional) -- Specific MeSH terms to include"],
  "use_cache": "boolean (optional, default: true) -- Use cached results if available"
}
```

### Response (200 OK)

```json
{
  "search_id": "string",
  "query": "string -- Original query",
  "query_expanded": "string -- MeSH-expanded query sent to PubMed",
  "total_results": "integer -- Total matching articles in PubMed",
  "returned_results": "integer -- Number returned in this response",
  "cached": "boolean -- Whether results were served from cache",
  "results": [
    {
      "pmid": "string -- PubMed ID",
      "title": "string",
      "authors": "string -- First author et al.",
      "journal": "string -- Journal name",
      "year": "integer",
      "month": "string | null",
      "volume": "string | null",
      "issue": "string | null",
      "pages": "string | null",
      "doi": "string | null",
      "abstract": "string -- Article abstract",
      "article_type": "string",
      "mesh_terms": ["string -- MeSH terms"],
      "relevance_score": "number -- 0.0 to 1.0 (semantic relevance)",
      "citation_count": "integer | null -- Approximate citation count"
    }
  ]
}
```

### Example

```bash
curl -X POST http://localhost:8000/api/v1/search/literature \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "SGLT2 inhibitors renal outcomes type 2 diabetes CKD",
    "max_results": 10,
    "date_range": {"start": "2020-01-01", "end": "2026-01-01"},
    "article_types": ["meta-analysis", "randomized-controlled-trial"]
  }'
```

---

## POST /search/protocols

Search institutional treatment protocols and clinical practice guidelines.

### Request

**Content-Type:** `application/json`
**Required Scope:** `cdss.search`

```json
{
  "query": "string (required) -- Search query",
  "specialty": "string (optional) -- Filter by specialty (e.g., 'endocrinology', 'nephrology')",
  "condition": "string (optional) -- Filter by condition",
  "icd10_codes": ["string (optional) -- Filter by ICD-10 codes"],
  "max_results": "integer (optional, default: 5, max: 20)",
  "include_archived": "boolean (optional, default: false) -- Include archived protocol versions"
}
```

### Response (200 OK)

```json
{
  "search_id": "string",
  "total_results": "integer",
  "results": [
    {
      "protocol_id": "string",
      "title": "string -- Protocol title",
      "version": "string -- Protocol version",
      "effective_date": "string -- ISO 8601 date",
      "specialty": "string",
      "conditions": ["string -- Applicable conditions"],
      "icd10_codes": ["string"],
      "department": "string",
      "approved_by": "string",
      "relevance_score": "number -- 0.0 to 1.0",
      "summary": "string -- Relevant section summary",
      "matching_sections": [
        {
          "section_title": "string",
          "content": "string -- Section content (Markdown)",
          "page": "integer | null"
        }
      ],
      "document_url": "string -- URL to full document in Blob Storage"
    }
  ]
}
```

### Example

```bash
curl -X POST http://localhost:8000/api/v1/search/protocols \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "type 2 diabetes management in chronic kidney disease",
    "specialty": "endocrinology",
    "icd10_codes": ["E11.9", "N18.3"],
    "max_results": 5
  }'
```

---

## GET /health

Health check endpoint. Returns the status of the application and all dependent services. **No authentication required.**

### Response (200 OK)

```json
{
  "status": "string -- 'healthy' | 'degraded' | 'unhealthy'",
  "version": "string -- Application version",
  "timestamp": "string -- ISO 8601",
  "uptime_seconds": "integer",
  "dependencies": {
    "azure_openai": {
      "status": "string -- 'healthy' | 'unhealthy'",
      "latency_ms": "integer"
    },
    "azure_ai_search": {
      "status": "string",
      "latency_ms": "integer"
    },
    "cosmos_db": {
      "status": "string",
      "latency_ms": "integer"
    },
    "azure_sql": {
      "status": "string",
      "latency_ms": "integer"
    },
    "redis": {
      "status": "string",
      "latency_ms": "integer"
    },
    "blob_storage": {
      "status": "string",
      "latency_ms": "integer"
    }
  }
}
```

### Example

```bash
curl http://localhost:8000/api/v1/health
```

---

## GET /audit

Query the audit trail. Requires the `cdss.audit.read` scope (admin role only).

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start_date` | string | 24h ago | Start of date range (ISO 8601) |
| `end_date` | string | now | End of date range (ISO 8601) |
| `user_id` | string | all | Filter by user ID |
| `patient_id` | string | all | Filter by patient ID |
| `action` | string | all | Filter by action type |
| `page` | integer | 1 | Page number |
| `page_size` | integer | 50 | Results per page (max 200) |

### Response (200 OK)

```json
{
  "total_records": "integer",
  "page": "integer",
  "page_size": "integer",
  "total_pages": "integer",
  "records": [
    {
      "audit_id": "string",
      "timestamp": "string -- ISO 8601",
      "user_id": "string",
      "patient_id": "string | null",
      "action": "string -- Action type",
      "query_id": "string | null",
      "data_sources_accessed": ["string"],
      "phi_accessed": "boolean",
      "total_tokens": "integer | null",
      "total_latency_ms": "integer | null",
      "ip_address": "string",
      "user_agent": "string"
    }
  ]
}
```

### Action Types

| Action | Description |
|--------|-------------|
| `clinical_query_submitted` | A clinical query was received |
| `clinical_query_completed` | A clinical query was processed |
| `clinical_query_failed` | A clinical query failed |
| `patient_record_accessed` | A patient record was read |
| `document_ingested` | A document was ingested |
| `drug_interaction_checked` | A drug interaction check was performed |
| `literature_searched` | A literature search was performed |
| `protocol_searched` | A protocol search was performed |

### Example

```bash
curl -X GET "http://localhost:8000/api/v1/audit?start_date=2026-02-01T00:00:00Z&patient_id=patient_12345&page_size=20" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Error Responses

All error responses follow a consistent format:

```json
{
  "error": {
    "code": "string -- Machine-readable error code",
    "message": "string -- Human-readable description",
    "details": "object | null -- Additional error context",
    "request_id": "string -- Request correlation ID for debugging"
  }
}
```

### Standard Error Codes

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | `INVALID_REQUEST` | Request body validation failed |
| 401 | `UNAUTHORIZED` | Missing or invalid authentication token |
| 403 | `FORBIDDEN` | Insufficient permissions for the requested resource |
| 404 | `NOT_FOUND` | Requested resource does not exist |
| 409 | `CONFLICT` | Resource conflict (e.g., duplicate document) |
| 413 | `PAYLOAD_TOO_LARGE` | Uploaded file exceeds size limit |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Uploaded file type not supported |
| 422 | `UNPROCESSABLE_ENTITY` | Request is syntactically valid but semantically incorrect |
| 429 | `RATE_LIMITED` | Too many requests; retry after `Retry-After` header |
| 500 | `INTERNAL_ERROR` | Unexpected server error |
| 502 | `UPSTREAM_ERROR` | An external service (PubMed, DrugBank, etc.) returned an error |
| 503 | `SERVICE_UNAVAILABLE` | Service is temporarily unavailable or in maintenance mode |
| 504 | `TIMEOUT` | Request processing exceeded the timeout limit |

### Rate Limiting

Rate limits are enforced per user token:

| Endpoint | Rate Limit |
|----------|-----------|
| `POST /query` | 10 requests/minute |
| `POST /query/stream` | 10 requests/minute |
| `POST /documents/ingest` | 20 requests/hour |
| `POST /drugs/interactions` | 30 requests/minute |
| `POST /search/*` | 60 requests/minute |
| `GET /patients/*` | 60 requests/minute |
| `GET /audit` | 30 requests/minute |

Rate limit headers are included in all responses:

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1708012380
Retry-After: 45
```

---

## Pagination

Endpoints that return lists support cursor-based pagination:

```
GET /api/v1/audit?page=2&page_size=50
```

Pagination metadata is included in the response body:

```json
{
  "total_records": 1247,
  "page": 2,
  "page_size": 50,
  "total_pages": 25
}
```

---

## Versioning

The API is versioned via URL path (`/api/v1/`). Breaking changes will result in a new version (`/api/v2/`). Non-breaking additions (new optional fields, new endpoints) may be added to the current version without a version bump.

---

## OpenAPI Specification

Interactive API documentation is available at:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`
