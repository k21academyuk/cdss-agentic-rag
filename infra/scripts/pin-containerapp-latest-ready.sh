#!/bin/bash
# Ensure a Container App in activeRevisionsMode=Multiple serves the latest ready revision.
# Usage: ./infra/scripts/pin-containerapp-latest-ready.sh <resource-group> <container-app-name> [timeout-seconds]

set -euo pipefail

RESOURCE_GROUP="${1:-}"
CONTAINER_APP_NAME="${2:-}"
TIMEOUT_SECONDS="${3:-600}"
POLL_SECONDS="${POLL_SECONDS:-10}"

log_info() { echo "[INFO] $1"; }
log_warn() { echo "[WARN] $1"; }
log_error() { echo "[ERROR] $1"; }
log_success() { echo "[SUCCESS] $1"; }

if [[ -z "${RESOURCE_GROUP}" || -z "${CONTAINER_APP_NAME}" ]]; then
  log_error "Usage: $0 <resource-group> <container-app-name> [timeout-seconds]"
  exit 1
fi

if ! command -v az >/dev/null 2>&1; then
  log_error "Azure CLI is required."
  exit 1
fi

if ! az account show >/dev/null 2>&1; then
  log_error "Not logged into Azure CLI. Run: az login"
  exit 1
fi

ACTIVE_MODE="$(az containerapp show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${CONTAINER_APP_NAME}" \
  --query "properties.configuration.activeRevisionsMode" \
  -o tsv 2>/dev/null || true)"

if [[ "${ACTIVE_MODE}" != "Multiple" ]]; then
  log_info "Container App activeRevisionsMode=${ACTIVE_MODE:-unknown}; traffic pin not required."
  exit 0
fi

STARTED_AT="$(date +%s)"
LATEST_REVISION=""
LATEST_READY_REVISION=""

while true; do
  LATEST_REVISION="$(az containerapp show \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${CONTAINER_APP_NAME}" \
    --query "properties.latestRevisionName" \
    -o tsv 2>/dev/null || true)"
  LATEST_READY_REVISION="$(az containerapp show \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${CONTAINER_APP_NAME}" \
    --query "properties.latestReadyRevisionName" \
    -o tsv 2>/dev/null || true)"

  if [[ -n "${LATEST_READY_REVISION}" && "${LATEST_READY_REVISION}" == "${LATEST_REVISION}" ]]; then
    break
  fi

  NOW="$(date +%s)"
  ELAPSED=$((NOW - STARTED_AT))
  if (( ELAPSED >= TIMEOUT_SECONDS )); then
    break
  fi

  log_info "Waiting for latest revision readiness (latest=${LATEST_REVISION:-<none>} latestReady=${LATEST_READY_REVISION:-<none>})..."
  sleep "${POLL_SECONDS}"
done

if [[ -z "${LATEST_READY_REVISION}" ]]; then
  log_error "Could not resolve latest ready revision for ${CONTAINER_APP_NAME}."
  exit 1
fi

CURRENT_TRAFFIC_REVISION="$(az containerapp show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${CONTAINER_APP_NAME}" \
  --query "properties.configuration.ingress.traffic[0].revisionName" \
  -o tsv 2>/dev/null || true)"
CURRENT_TRAFFIC_WEIGHT="$(az containerapp show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${CONTAINER_APP_NAME}" \
  --query "properties.configuration.ingress.traffic[0].weight" \
  -o tsv 2>/dev/null || true)"

if [[ "${CURRENT_TRAFFIC_REVISION}" == "${LATEST_READY_REVISION}" && "${CURRENT_TRAFFIC_WEIGHT}" == "100" ]]; then
  log_info "Traffic already pinned to latest ready revision (${LATEST_READY_REVISION})."
  exit 0
fi

log_info "Pinning 100% traffic to latest ready revision: ${LATEST_READY_REVISION}"
az containerapp ingress traffic set \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${CONTAINER_APP_NAME}" \
  --revision-weight "${LATEST_READY_REVISION}=100" \
  --only-show-errors \
  --output none

log_success "Traffic pinned to ${LATEST_READY_REVISION}."
