#!/bin/bash
# ============================================================================
# Configure PubMed credentials for deployed CDSS backend (production-safe).
# Stores values in Key Vault and wires Container App env vars via secretRef.
#
# Usage:
#   CDSS_PUBMED_API_KEY=<key> CDSS_PUBMED_EMAIL=<email> \
#     ./infra/scripts/configure-pubmed-prod.sh <resource-group> [container-app-name] [key-vault-name]
# Optional env:
#   CDSS_KV_TEMP_IP_ALLOWLIST=true|false (default: true)
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIN_TRAFFIC_SCRIPT="${SCRIPT_DIR}/pin-containerapp-latest-ready.sh"

RESOURCE_GROUP="${1:-}"
CONTAINER_APP_NAME="${2:-}"
KEY_VAULT_NAME="${3:-}"
PUBMED_API_KEY="${CDSS_PUBMED_API_KEY:-${PUBMED_API_KEY:-}}"
PUBMED_EMAIL="${CDSS_PUBMED_EMAIL:-${PUBMED_EMAIL:-}}"
PUBMED_BASE_URL="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
TEMP_IP_ALLOWLIST="${CDSS_KV_TEMP_IP_ALLOWLIST:-true}"

ORIG_KV_PNA=""
ORIG_KV_DEFAULT_ACTION=""
TEMP_CLIENT_IP=""
TEMP_KV_RULE_ADDED="false"
TEMP_KV_NETWORK_UPDATED="false"
TEMP_KV_ACCESS_ACTIVE="false"
CALLER_OBJECT_ID=""
CALLER_PRINCIPAL_TYPE=""

log_info() { echo "[INFO] $1"; }
log_warn() { echo "[WARN] $1"; }
log_error() { echo "[ERROR] $1"; }
log_success() { echo "[SUCCESS] $1"; }

resolve_current_caller() {
  local account_type=""
  local account_name=""
  account_type="$(az account show --query user.type -o tsv 2>/dev/null || true)"
  account_name="$(az account show --query user.name -o tsv 2>/dev/null || true)"

  if [[ "${account_type}" == "user" ]]; then
    CALLER_OBJECT_ID="$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)"
    CALLER_PRINCIPAL_TYPE="User"
  elif [[ "${account_type}" == "servicePrincipal" || "${account_type}" == "serviceprincipal" ]]; then
    CALLER_OBJECT_ID="$(az ad sp show --id "${account_name}" --query id -o tsv 2>/dev/null || true)"
    CALLER_PRINCIPAL_TYPE="ServicePrincipal"
  else
    CALLER_OBJECT_ID=""
    CALLER_PRINCIPAL_TYPE=""
  fi
}

ensure_caller_keyvault_secret_write_role() {
  local role_count=""

  resolve_current_caller
  if [[ -z "${CALLER_OBJECT_ID}" || -z "${CALLER_PRINCIPAL_TYPE}" ]]; then
    log_warn "Could not resolve current caller object ID/principal type for Key Vault role assignment."
    return 1
  fi

  role_count="$(az role assignment list \
    --assignee-object-id "${CALLER_OBJECT_ID}" \
    --scope "${KEY_VAULT_ID}" \
    --query "[?roleDefinitionName=='Key Vault Secrets Officer'] | length(@)" \
    -o tsv 2>/dev/null || echo "0")"

  if [[ "${role_count}" != "0" ]]; then
    log_info "Caller already has Key Vault Secrets Officer role."
    return 0
  fi

  log_info "Attempting to grant Key Vault Secrets Officer role to current caller..."
  if az role assignment create \
    --assignee-object-id "${CALLER_OBJECT_ID}" \
    --assignee-principal-type "${CALLER_PRINCIPAL_TYPE}" \
    --role "Key Vault Secrets Officer" \
    --scope "${KEY_VAULT_ID}" \
    --only-show-errors \
    --output none; then
    log_info "Role assignment created. Waiting for RBAC propagation..."
    sleep 20
    return 0
  fi

  log_warn "Automatic caller role assignment failed. You may need Owner/User Access Administrator permissions."
  return 1
}

restore_keyvault_access() {
  if [[ "${TEMP_KV_RULE_ADDED}" != "true" && "${TEMP_KV_NETWORK_UPDATED}" != "true" ]]; then
    return 0
  fi

  log_info "Restoring Key Vault network restrictions..."

  if [[ "${TEMP_KV_RULE_ADDED}" == "true" && -n "${TEMP_CLIENT_IP}" ]]; then
    az keyvault network-rule remove \
      --resource-group "${RESOURCE_GROUP}" \
      --name "${KEY_VAULT_NAME}" \
      --ip-address "${TEMP_CLIENT_IP}" \
      --only-show-errors \
      --output none || log_warn "Could not remove temporary Key Vault IP rule (${TEMP_CLIENT_IP})."
  fi

  if [[ "${TEMP_KV_NETWORK_UPDATED}" == "true" ]]; then
    az keyvault update \
      --resource-group "${RESOURCE_GROUP}" \
      --name "${KEY_VAULT_NAME}" \
      --public-network-access "${ORIG_KV_PNA}" \
      --default-action "${ORIG_KV_DEFAULT_ACTION}" \
      --only-show-errors \
      --output none || log_warn "Could not restore Key Vault network settings. Restore manually."
  fi
}

enable_temporary_keyvault_access() {
  if [[ "${TEMP_IP_ALLOWLIST}" != "true" ]]; then
    log_error "Key Vault denied connection and CDSS_KV_TEMP_IP_ALLOWLIST=false. Cannot continue."
    return 1
  fi

  if ! command -v curl >/dev/null 2>&1; then
    log_error "curl is required for temporary Key Vault IP allowlisting."
    return 1
  fi

  ORIG_KV_PNA="$(az keyvault show --name "${KEY_VAULT_NAME}" --resource-group "${RESOURCE_GROUP}" --query properties.publicNetworkAccess -o tsv)"
  ORIG_KV_DEFAULT_ACTION="$(az keyvault show --name "${KEY_VAULT_NAME}" --resource-group "${RESOURCE_GROUP}" --query properties.networkAcls.defaultAction -o tsv)"
  TEMP_CLIENT_IP="$(curl -fsS https://api.ipify.org)"

  if [[ -z "${TEMP_CLIENT_IP}" ]]; then
    log_error "Could not determine current public IP for Key Vault allowlist."
    return 1
  fi

  log_warn "Key Vault denied public connection; temporarily allowlisting current IP (${TEMP_CLIENT_IP})."

  if [[ "${ORIG_KV_PNA}" != "Enabled" || "${ORIG_KV_DEFAULT_ACTION}" != "Deny" ]]; then
    az keyvault update \
      --resource-group "${RESOURCE_GROUP}" \
      --name "${KEY_VAULT_NAME}" \
      --public-network-access Enabled \
      --default-action Deny \
      --only-show-errors \
      --output none
    TEMP_KV_NETWORK_UPDATED="true"
  fi

  az keyvault network-rule add \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${KEY_VAULT_NAME}" \
    --ip-address "${TEMP_CLIENT_IP}" \
    --only-show-errors \
    --output none
  TEMP_KV_RULE_ADDED="true"
  TEMP_KV_ACCESS_ACTIVE="true"

  log_info "Waiting for Key Vault network ACL propagation..."
  sleep 20
}

write_pubmed_secrets() {
  az keyvault secret set --vault-name "${KEY_VAULT_NAME}" --name "pubmed-api-key" --value "${PUBMED_API_KEY}" --output none
  az keyvault secret set --vault-name "${KEY_VAULT_NAME}" --name "pubmed-email" --value "${PUBMED_EMAIL}" --output none
}

trap restore_keyvault_access EXIT

if [[ -z "${RESOURCE_GROUP}" ]]; then
  log_error "Usage: $0 <resource-group> [container-app-name] [key-vault-name]"
  exit 1
fi

if [[ -z "${PUBMED_API_KEY}" || -z "${PUBMED_EMAIL}" ]]; then
  log_error "CDSS_PUBMED_API_KEY and CDSS_PUBMED_EMAIL are required."
  log_error "Example:"
  log_error "  CDSS_PUBMED_API_KEY=<key> CDSS_PUBMED_EMAIL=<email> $0 ${RESOURCE_GROUP}"
  exit 1
fi

if ! command -v az >/dev/null 2>&1; then
  log_error "Azure CLI is required."
  exit 1
fi

if ! az account show >/dev/null 2>&1; then
  log_error "Not logged in to Azure CLI. Run: az login"
  exit 1
fi

if [[ -z "${CONTAINER_APP_NAME}" ]]; then
  CONTAINER_APP_NAME="$(az containerapp list -g "${RESOURCE_GROUP}" --query "[?contains(name,'-api')].name | [0]" -o tsv 2>/dev/null || true)"
fi
if [[ -z "${CONTAINER_APP_NAME}" ]]; then
  log_error "Could not resolve backend Container App in resource group ${RESOURCE_GROUP}."
  exit 1
fi

if [[ -z "${KEY_VAULT_NAME}" ]]; then
  KEY_VAULT_NAME="$(az keyvault list -g "${RESOURCE_GROUP}" --query "[0].name" -o tsv 2>/dev/null || true)"
fi
if [[ -z "${KEY_VAULT_NAME}" ]]; then
  log_error "Could not resolve Key Vault in resource group ${RESOURCE_GROUP}."
  exit 1
fi

MANAGED_IDENTITY_ID="$(az containerapp show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${CONTAINER_APP_NAME}" \
  --query "keys(identity.userAssignedIdentities)[0]" \
  -o tsv 2>/dev/null || true)"
if [[ -z "${MANAGED_IDENTITY_ID}" ]]; then
  log_error "Container App does not have a user-assigned managed identity."
  exit 1
fi

MANAGED_IDENTITY_PRINCIPAL_ID="$(az identity show --ids "${MANAGED_IDENTITY_ID}" --query principalId -o tsv)"
KEY_VAULT_ID="$(az keyvault show --name "${KEY_VAULT_NAME}" --resource-group "${RESOURCE_GROUP}" --query id -o tsv)"
KEY_VAULT_URI="$(az keyvault show --name "${KEY_VAULT_NAME}" --resource-group "${RESOURCE_GROUP}" --query properties.vaultUri -o tsv)"

log_info "Ensuring Key Vault Secrets User role for Container App identity..."
KV_ROLE_COUNT="$(az role assignment list \
  --assignee-object-id "${MANAGED_IDENTITY_PRINCIPAL_ID}" \
  --scope "${KEY_VAULT_ID}" \
  --query "[?roleDefinitionName=='Key Vault Secrets User'] | length(@)" \
  -o tsv 2>/dev/null || echo "0")"

if [[ "${KV_ROLE_COUNT}" == "0" ]]; then
  az role assignment create \
    --assignee-object-id "${MANAGED_IDENTITY_PRINCIPAL_ID}" \
    --assignee-principal-type ServicePrincipal \
    --role "Key Vault Secrets User" \
    --scope "${KEY_VAULT_ID}" \
    --only-show-errors \
    --output none
  log_info "Role assignment created. Waiting for RBAC propagation..."
  sleep 20
else
  log_info "Role assignment already present."
fi

log_info "Writing PubMed secrets to Key Vault..."
if ! SECRET_WRITE_ERROR="$(write_pubmed_secrets 2>&1)"; then
  if [[ "${SECRET_WRITE_ERROR}" == *"ForbiddenByConnection"* || "${SECRET_WRITE_ERROR}" == *"Public network access is disabled"* ]]; then
    enable_temporary_keyvault_access
    write_pubmed_secrets
  elif [[ "${SECRET_WRITE_ERROR}" == *"ForbiddenByRbac"* || "${SECRET_WRITE_ERROR}" == *"setSecret/action"* ]]; then
    if ensure_caller_keyvault_secret_write_role; then
      write_pubmed_secrets
    else
      echo "${SECRET_WRITE_ERROR}" >&2
      exit 1
    fi
  else
    echo "${SECRET_WRITE_ERROR}" >&2
    exit 1
  fi
fi

log_info "Binding Key Vault-backed secrets to Container App..."
az containerapp secret set \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${CONTAINER_APP_NAME}" \
  --secrets \
    "pubmed-api-key=keyvaultref:${KEY_VAULT_URI}secrets/pubmed-api-key,identityref:${MANAGED_IDENTITY_ID}" \
    "pubmed-email=keyvaultref:${KEY_VAULT_URI}secrets/pubmed-email,identityref:${MANAGED_IDENTITY_ID}" \
  --only-show-errors \
  --output none

log_info "Updating backend runtime env vars to use secretRef..."
az containerapp update \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${CONTAINER_APP_NAME}" \
  --set-env-vars \
    "CDSS_PUBMED_API_KEY=secretref:pubmed-api-key" \
    "CDSS_PUBMED_EMAIL=secretref:pubmed-email" \
    "CDSS_PUBMED_BASE_URL=${PUBMED_BASE_URL}" \
  --only-show-errors \
  --output none

if [[ -x "${PIN_TRAFFIC_SCRIPT}" ]]; then
  if ! "${PIN_TRAFFIC_SCRIPT}" "${RESOURCE_GROUP}" "${CONTAINER_APP_NAME}"; then
    log_warn "PubMed env updated, but failed to pin traffic to latest ready revision."
    log_warn "Run manually: ${PIN_TRAFFIC_SCRIPT} ${RESOURCE_GROUP} ${CONTAINER_APP_NAME}"
  fi
else
  log_warn "Traffic pin script not found/executable: ${PIN_TRAFFIC_SCRIPT}"
fi

log_success "PubMed production configuration applied."

echo ""
echo "Configured backend env vars:"
az containerapp show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${CONTAINER_APP_NAME}" \
  --query "properties.template.containers[0].env[?name=='CDSS_PUBMED_API_KEY'||name=='CDSS_PUBMED_EMAIL'||name=='CDSS_PUBMED_BASE_URL'].{name:name,secretRef:secretRef,value:value}" \
  -o table
