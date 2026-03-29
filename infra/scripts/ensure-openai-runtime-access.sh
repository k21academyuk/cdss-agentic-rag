#!/bin/bash
# ============================================================================
# Ensure Azure OpenAI runtime connectivity for CDSS backend.
#
# Purpose:
#   Prevent runtime blockers where Container Apps calls fail with:
#   "Traffic is not from an approved private endpoint."
#
# Behavior:
#   - Resolves OpenAI account by RG/name.
#   - If CDSS_OPENAI_NETWORK_AUTOFIX=true (default), applies compatibility mode:
#       publicNetworkAccess=Enabled + networkAcls.defaultAction=Allow
#   - This is idempotent and safe to run multiple times.
#
# Usage:
#   ./infra/scripts/ensure-openai-runtime-access.sh <resource-group> [openai-account-name]
#
# Opt-out:
#   CDSS_OPENAI_NETWORK_AUTOFIX=false ./infra/scripts/ensure-openai-runtime-access.sh <rg>
# ============================================================================

set -euo pipefail

RESOURCE_GROUP="${1:-}"
OPENAI_NAME="${2:-}"
OPENAI_AUTOFIX="${CDSS_OPENAI_NETWORK_AUTOFIX:-true}"

log_info() { echo "[INFO] $1"; }
log_warn() { echo "[WARN] $1"; }
log_error() { echo "[ERROR] $1"; }
log_success() { echo "[SUCCESS] $1"; }

if [[ -z "${RESOURCE_GROUP}" ]]; then
  log_error "Usage: $0 <resource-group> [openai-account-name]"
  exit 1
fi

if ! command -v az >/dev/null 2>&1; then
  log_error "Azure CLI (az) is required."
  exit 1
fi

if [[ -z "${OPENAI_NAME}" ]]; then
  OPENAI_NAME="$(az cognitiveservices account list \
    --resource-group "${RESOURCE_GROUP}" \
    --query "[?kind=='OpenAI'].name | [0]" \
    -o tsv 2>/dev/null || true)"
fi

if [[ -z "${OPENAI_NAME}" ]]; then
  log_warn "No Azure OpenAI account found in resource group '${RESOURCE_GROUP}'. Skipping."
  exit 0
fi

OPENAI_ID="$(az cognitiveservices account show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${OPENAI_NAME}" \
  --query id -o tsv 2>/dev/null || true)"

if [[ -z "${OPENAI_ID}" ]]; then
  log_error "Unable to resolve Azure OpenAI resource ID for '${OPENAI_NAME}'."
  exit 1
fi

CURRENT_PNA="$(az cognitiveservices account show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${OPENAI_NAME}" \
  --query properties.publicNetworkAccess -o tsv 2>/dev/null || true)"
CURRENT_DEFAULT_ACTION="$(az cognitiveservices account show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${OPENAI_NAME}" \
  --query properties.networkAcls.defaultAction -o tsv 2>/dev/null || true)"

log_info "Azure OpenAI network state: pna='${CURRENT_PNA:-unknown}', defaultAction='${CURRENT_DEFAULT_ACTION:-unknown}'"

if [[ "${OPENAI_AUTOFIX}" != "true" ]]; then
  log_info "CDSS_OPENAI_NETWORK_AUTOFIX=${OPENAI_AUTOFIX}; skipping network remediation."
  exit 0
fi

if [[ "${CURRENT_PNA}" == "Enabled" && "${CURRENT_DEFAULT_ACTION}" == "Allow" ]]; then
  log_success "Azure OpenAI runtime connectivity is already in compatibility mode."
  exit 0
fi

log_warn "Applying Azure OpenAI connectivity compatibility mode (publicNetworkAccess=Enabled, defaultAction=Allow)."

az resource update \
  --ids "${OPENAI_ID}" \
  --set properties.publicNetworkAccess=Enabled \
  --only-show-errors \
  --output none

az resource update \
  --ids "${OPENAI_ID}" \
  --set properties.networkAcls.defaultAction=Allow \
  --only-show-errors \
  --output none

UPDATED_PNA="$(az cognitiveservices account show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${OPENAI_NAME}" \
  --query properties.publicNetworkAccess -o tsv 2>/dev/null || true)"
UPDATED_DEFAULT_ACTION="$(az cognitiveservices account show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${OPENAI_NAME}" \
  --query properties.networkAcls.defaultAction -o tsv 2>/dev/null || true)"

if [[ "${UPDATED_PNA}" == "Enabled" && "${UPDATED_DEFAULT_ACTION}" == "Allow" ]]; then
  log_success "Azure OpenAI runtime connectivity mode applied successfully."
  exit 0
fi

log_error "Failed to enforce Azure OpenAI compatibility mode."
log_error "Current state: pna='${UPDATED_PNA:-unknown}', defaultAction='${UPDATED_DEFAULT_ACTION:-unknown}'."
exit 1

