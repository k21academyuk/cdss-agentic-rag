#!/bin/bash
# ============================================================================
# Ensures Cosmos embedding-cache container uses supported vector policy.
# Fixes legacy deployments with vectorEmbeddings.dataType=float16 by
# recreating embedding-cache with float32.
# ============================================================================

set -euo pipefail

RESOURCE_GROUP="${1:-}"
COSMOS_ACCOUNT_NAME="${2:-}"
DATABASE_NAME="${3:-cdss-db}"
CONTAINER_NAME="${4:-embedding-cache}"

if [[ -z "${RESOURCE_GROUP}" ]]; then
  echo "Usage: $0 <resource-group> [cosmos-account-name] [database-name] [container-name]"
  echo "Example: $0 cdss-prod-rg"
  exit 1
fi

log_info() { echo "[INFO] $1"; }
log_warn() { echo "[WARN] $1"; }
log_error() { echo "[ERROR] $1"; }
log_success() { echo "[SUCCESS] $1"; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log_error "Required command not found: $1"
    exit 1
  fi
}

create_embedding_cache_container() {
  local rg="$1"
  local account="$2"
  local db="$3"
  local container="$4"
  local idx_file=""
  local vector_file=""

  idx_file="$(mktemp)"
  vector_file="$(mktemp)"

  cat > "${idx_file}" <<'JSON'
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {
      "path": "/*"
    }
  ],
  "excludedPaths": [
    {
      "path": "/\"_etag\"/?"
    },
    {
      "path": "/content_vector/*"
    }
  ],
  "vectorIndexes": [
    {
      "path": "/content_vector",
      "type": "diskANN"
    }
  ]
}
JSON

  cat > "${vector_file}" <<'JSON'
{
  "vectorEmbeddings": [
    {
      "path": "/content_vector",
      "dataType": "float32",
      "dimensions": 3072,
      "distanceFunction": "cosine"
    }
  ]
}
JSON

  az cosmosdb sql container create \
    --resource-group "${rg}" \
    --account-name "${account}" \
    --database-name "${db}" \
    --name "${container}" \
    --partition-key-path "/document_id" \
    --idx @"${idx_file}" \
    --vector-embeddings @"${vector_file}" \
    --output none

  rm -f "${idx_file}" "${vector_file}"
}

require_cmd az

if ! az account show >/dev/null 2>&1; then
  log_error "Not logged in to Azure CLI. Run: az login"
  exit 1
fi

if [[ -z "${COSMOS_ACCOUNT_NAME}" ]]; then
  COSMOS_ACCOUNT_NAME="$(az cosmosdb list -g "${RESOURCE_GROUP}" --query "[0].name" -o tsv 2>/dev/null || true)"
fi

if [[ -z "${COSMOS_ACCOUNT_NAME}" ]]; then
  log_error "Unable to resolve Cosmos DB account in resource group '${RESOURCE_GROUP}'."
  exit 1
fi

log_info "Checking embedding cache vector policy in Cosmos account: ${COSMOS_ACCOUNT_NAME}"

CONTAINER_EXISTS="false"
if az cosmosdb sql container show \
  --resource-group "${RESOURCE_GROUP}" \
  --account-name "${COSMOS_ACCOUNT_NAME}" \
  --database-name "${DATABASE_NAME}" \
  --name "${CONTAINER_NAME}" >/dev/null 2>&1; then
  CONTAINER_EXISTS="true"
fi

CURRENT_DATA_TYPE=""
if [[ "${CONTAINER_EXISTS}" == "true" ]]; then
  CURRENT_DATA_TYPE="$(az cosmosdb sql container show \
    --resource-group "${RESOURCE_GROUP}" \
    --account-name "${COSMOS_ACCOUNT_NAME}" \
    --database-name "${DATABASE_NAME}" \
    --name "${CONTAINER_NAME}" \
    --query "resource.vectorEmbeddingPolicy.vectorEmbeddings[0].dataType" \
    -o tsv 2>/dev/null || true)"
fi

if [[ "${CONTAINER_EXISTS}" == "true" && "${CURRENT_DATA_TYPE}" == "float32" ]]; then
  log_success "Embedding cache vector policy already uses float32. No action needed."
  exit 0
fi

if [[ "${CONTAINER_EXISTS}" == "true" ]]; then
  if [[ "${CURRENT_DATA_TYPE}" == "float16" ]]; then
    log_warn "Detected unsupported vector dataType=float16 on '${CONTAINER_NAME}'. Recreating container with float32."
  else
    log_warn "Container '${CONTAINER_NAME}' exists but vector policy is missing/unsupported ('${CURRENT_DATA_TYPE:-none}'). Recreating."
  fi

  az cosmosdb sql container delete \
    --resource-group "${RESOURCE_GROUP}" \
    --account-name "${COSMOS_ACCOUNT_NAME}" \
    --database-name "${DATABASE_NAME}" \
    --name "${CONTAINER_NAME}" \
    --yes \
    --output none
else
  log_warn "Container '${CONTAINER_NAME}' not found. Creating with float32 vector policy."
fi

create_embedding_cache_container "${RESOURCE_GROUP}" "${COSMOS_ACCOUNT_NAME}" "${DATABASE_NAME}" "${CONTAINER_NAME}"
log_success "Embedding cache container is configured with float32 vector policy."
