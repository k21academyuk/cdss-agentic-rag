#!/bin/bash
# ============================================================================
# CDSS - Create/Update Azure AI Search Indexes
# ============================================================================
#
# Usage:
#   ./create-search-indexes.sh <resource-group> [search-service-name]
#
# This script is idempotent and safe to re-run.

set -euo pipefail

REQUIRED_INDEXES=(
  "patient-records"
  "treatment-protocols"
  "medical-literature-cache"
)

if [[ "${1:-}" == "--list-required-indexes" ]]; then
  printf "%s\n" "${REQUIRED_INDEXES[@]}"
  exit 0
fi

RESOURCE_GROUP="${1:-}"
SEARCH_SERVICE_NAME="${2:-}"
API_VERSION="2024-05-01-preview"

if [[ -z "${RESOURCE_GROUP}" ]]; then
  echo "Usage: $0 <resource-group> [search-service-name]"
  exit 1
fi

if ! command -v az >/dev/null 2>&1; then
  echo "[ERROR] Azure CLI is required."
  exit 1
fi

if ! az account show >/dev/null 2>&1; then
  echo "[ERROR] Not logged in. Run: az login"
  exit 1
fi

if [[ -z "${SEARCH_SERVICE_NAME}" ]]; then
  SEARCH_SERVICE_NAME="$(az search service list --resource-group "${RESOURCE_GROUP}" --query "[0].name" -o tsv)"
fi

if [[ -z "${SEARCH_SERVICE_NAME}" ]]; then
  echo "[ERROR] Azure AI Search service not found in resource group: ${RESOURCE_GROUP}"
  exit 1
fi

SEARCH_ENDPOINT="https://${SEARCH_SERVICE_NAME}.search.windows.net"
SEARCH_ADMIN_KEY="$(az search admin-key show --service-name "${SEARCH_SERVICE_NAME}" --resource-group "${RESOURCE_GROUP}" --query primaryKey -o tsv)"

if [[ -z "${SEARCH_ADMIN_KEY}" ]]; then
  echo "[ERROR] Failed to resolve Search admin key for: ${SEARCH_SERVICE_NAME}"
  exit 1
fi

echo "[INFO] Search service: ${SEARCH_SERVICE_NAME}"
echo "[INFO] Endpoint: ${SEARCH_ENDPOINT}"

create_index() {
  local index_json="$1"
  local index_name
  index_name="$(echo "${index_json}" | python3 -c "import sys, json; print(json.load(sys.stdin)['name'])")"
  echo "[INFO] Creating/updating index: ${index_name}"

  local rest_output=""
  if ! rest_output="$(
    AZURE_CORE_ONLY_SHOW_ERRORS=1 az rest \
      --method put \
      --url "${SEARCH_ENDPOINT}/indexes/${index_name}?api-version=${API_VERSION}" \
      --skip-authorization-header \
      --headers "Content-Type=application/json" "api-key=${SEARCH_ADMIN_KEY}" \
      --body "${index_json}" \
      --output none 2>&1
  )"; then
    if [[ "${rest_output}" == *"publicNetworkAccess: Disabled"* || "${rest_output}" == *"source is not allowed by applicable rules"* ]]; then
      echo "[ERROR] Azure AI Search is private-network-only from this client path."
      echo "[ERROR] Run index bootstrap from a host inside the VNet, or temporarily allow public access."
      return 42
    fi

    echo "${rest_output}"
    return 1
  fi
}

PATIENT_RECORDS_INDEX='{
  "name": "patient-records",
  "fields": [
    {"name": "id", "type": "Edm.String", "key": true, "filterable": true},
    {"name": "document_id", "type": "Edm.String", "filterable": true, "sortable": true},
    {"name": "chunk_index", "type": "Edm.Int32", "filterable": true, "sortable": true},
    {"name": "content", "type": "Edm.String", "searchable": true, "analyzer": "en.microsoft"},
    {"name": "content_vector", "type": "Collection(Edm.Single)", "searchable": true, "dimensions": 3072, "vectorSearchProfile": "vector-profile"},
    {"name": "document_type", "type": "Edm.String", "filterable": true, "facetable": true},
    {"name": "patient_id", "type": "Edm.String", "filterable": true, "sortable": true},
    {"name": "ingested_at", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true},
    {"name": "entity_names", "type": "Collection(Edm.String)", "filterable": true, "searchable": true},
    {"name": "entity_codes", "type": "Collection(Edm.String)", "filterable": true},
    {"name": "metadata", "type": "Edm.String", "searchable": false}
  ],
  "vectorSearch": {
    "algorithms": [
      {"name": "hnsw-algorithm", "kind": "hnsw", "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}}
    ],
    "profiles": [
      {"name": "vector-profile", "algorithm": "hnsw-algorithm"}
    ]
  },
  "semantic": {
    "configurations": [
      {
        "name": "patient-records-semantic",
        "prioritizedFields": {
          "titleField": {"fieldName": "document_type"},
          "prioritizedContentFields": [{"fieldName": "content"}],
          "prioritizedKeywordsFields": [{"fieldName": "entity_names"}]
        }
      }
    ]
  }
}'

TREATMENT_PROTOCOLS_INDEX='{
  "name": "treatment-protocols",
  "fields": [
    {"name": "id", "type": "Edm.String", "key": true, "filterable": true},
    {"name": "document_id", "type": "Edm.String", "filterable": true, "sortable": true},
    {"name": "chunk_index", "type": "Edm.Int32", "filterable": true, "sortable": true},
    {"name": "content", "type": "Edm.String", "searchable": true, "analyzer": "en.microsoft"},
    {"name": "content_vector", "type": "Collection(Edm.Single)", "searchable": true, "dimensions": 3072, "vectorSearchProfile": "vector-profile"},
    {"name": "specialty", "type": "Edm.String", "filterable": true, "facetable": true, "searchable": true},
    {"name": "guideline_name", "type": "Edm.String", "filterable": true, "searchable": true, "sortable": true},
    {"name": "version", "type": "Edm.String", "filterable": true, "sortable": true},
    {"name": "is_protocol", "type": "Edm.Boolean", "filterable": true},
    {"name": "document_type", "type": "Edm.String", "filterable": true, "facetable": true},
    {"name": "ingested_at", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true},
    {"name": "entity_names", "type": "Collection(Edm.String)", "filterable": true, "searchable": true},
    {"name": "entity_codes", "type": "Collection(Edm.String)", "filterable": true},
    {"name": "metadata", "type": "Edm.String", "searchable": false}
  ],
  "vectorSearch": {
    "algorithms": [
      {"name": "hnsw-algorithm", "kind": "hnsw", "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}}
    ],
    "profiles": [
      {"name": "vector-profile", "algorithm": "hnsw-algorithm"}
    ]
  },
  "semantic": {
    "configurations": [
      {
        "name": "protocols-semantic",
        "prioritizedFields": {
          "titleField": {"fieldName": "guideline_name"},
          "prioritizedContentFields": [{"fieldName": "content"}],
          "prioritizedKeywordsFields": [{"fieldName": "specialty"}]
        }
      }
    ]
  }
}'

MEDICAL_LITERATURE_INDEX='{
  "name": "medical-literature-cache",
  "fields": [
    {"name": "id", "type": "Edm.String", "key": true, "filterable": true},
    {"name": "document_id", "type": "Edm.String", "filterable": true, "sortable": true},
    {"name": "chunk_index", "type": "Edm.Int32", "filterable": true, "sortable": true},
    {"name": "content", "type": "Edm.String", "searchable": true, "analyzer": "en.microsoft"},
    {"name": "content_vector", "type": "Collection(Edm.Single)", "searchable": true, "dimensions": 3072, "vectorSearchProfile": "vector-profile"},
    {"name": "pmid", "type": "Edm.String", "filterable": true, "sortable": true},
    {"name": "title", "type": "Edm.String", "searchable": true, "sortable": true},
    {"name": "journal", "type": "Edm.String", "filterable": true, "facetable": true, "searchable": true},
    {"name": "publication_date", "type": "Edm.String", "filterable": true, "sortable": true},
    {"name": "mesh_terms", "type": "Collection(Edm.String)", "filterable": true, "facetable": true, "searchable": true},
    {"name": "document_type", "type": "Edm.String", "filterable": true, "facetable": true},
    {"name": "ingested_at", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true},
    {"name": "entity_names", "type": "Collection(Edm.String)", "filterable": true, "searchable": true},
    {"name": "entity_codes", "type": "Collection(Edm.String)", "filterable": true},
    {"name": "metadata", "type": "Edm.String", "searchable": false}
  ],
  "vectorSearch": {
    "algorithms": [
      {"name": "hnsw-algorithm", "kind": "hnsw", "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}}
    ],
    "profiles": [
      {"name": "vector-profile", "algorithm": "hnsw-algorithm"}
    ]
  },
  "semantic": {
    "configurations": [
      {
        "name": "literature-semantic",
        "prioritizedFields": {
          "titleField": {"fieldName": "title"},
          "prioritizedContentFields": [{"fieldName": "content"}],
          "prioritizedKeywordsFields": [{"fieldName": "mesh_terms"}]
        }
      }
    ]
  }
}'

create_index "${PATIENT_RECORDS_INDEX}"
create_index "${TREATMENT_PROTOCOLS_INDEX}"
create_index "${MEDICAL_LITERATURE_INDEX}"

echo "[SUCCESS] Search indexes created/updated successfully."
