#!/bin/bash
# ============================================================================
# CDSS first-run bootstrap deploy
# Creates RG/ACR, builds linux/amd64 image, deploys infra+app, bootstraps search.
# ============================================================================

set -euo pipefail

ENVIRONMENT="${1:-}"
RESOURCE_GROUP="${2:-}"
LOCATION="${3:-eastus2}"

if [[ -z "${ENVIRONMENT}" || -z "${RESOURCE_GROUP}" ]]; then
  echo "Usage: $0 <environment> <resource-group> [location]"
  echo "Example: $0 prod cdss-prod-rg eastus2"
  echo "Optional env vars:"
  echo "  ACR_NAME=<acr-name>"
  echo "  IMAGE_TAG=<tag>"
  echo "  CONTAINER_IMAGE=<acr>.azurecr.io/cdss-api:<tag>"
  echo "  PROD_PUBLIC_API=true|false (default: true)"
  echo "  SKIP_IMAGE_BUILD=true|false (default: false)"
  echo "  CDSS_IMAGE_BUILD_MODE=auto|local|acr (default: auto)"
  echo "  SKIP_SEARCH_BOOTSTRAP=true|false (default: false)"
  echo "  SKIP_AUTH_SETUP=true|false (default: true)"
  echo "  CDSS_PUBMED_API_KEY=<pubmed-api-key> (optional, prod recommended)"
  echo "  CDSS_PUBMED_EMAIL=<email@example.com> (optional, prod recommended)"
  echo "  CDSS_KV_TEMP_IP_ALLOWLIST=true|false (default: true)"
  echo "  CDSS_OPENAI_NETWORK_AUTOFIX=true|false (default: true)"
  exit 1
fi

if [[ "${ENVIRONMENT}" != "dev" && "${ENVIRONMENT}" != "staging" && "${ENVIRONMENT}" != "prod" ]]; then
  echo "[ERROR] environment must be one of: dev, staging, prod"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_SCRIPT="${SCRIPT_DIR}/deploy.sh"
INDEX_SCRIPT="${SCRIPT_DIR}/create-search-indexes.sh"
AUTH_SCRIPT="${SCRIPT_DIR}/setup-entra-spa-auth.sh"
POPULATE_ENV_SCRIPT="${SCRIPT_DIR}/populate-env.sh"
PUBMED_CONFIG_SCRIPT="${SCRIPT_DIR}/configure-pubmed-prod.sh"
OPENAI_ACCESS_SCRIPT="${SCRIPT_DIR}/ensure-openai-runtime-access.sh"
COSMOS_EMBEDDING_POLICY_SCRIPT="${SCRIPT_DIR}/ensure-cosmos-embedding-cache-policy.sh"

PROD_PUBLIC_API="${PROD_PUBLIC_API:-true}"
SKIP_IMAGE_BUILD="${SKIP_IMAGE_BUILD:-false}"
CDSS_IMAGE_BUILD_MODE="${CDSS_IMAGE_BUILD_MODE:-auto}"
SKIP_SEARCH_BOOTSTRAP="${SKIP_SEARCH_BOOTSTRAP:-false}"
SKIP_AUTH_SETUP="${SKIP_AUTH_SETUP:-true}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y.%m.%d.%H%M%S)}"
CONTAINER_IMAGE="${CONTAINER_IMAGE:-}"
ACR_NAME="${ACR_NAME:-}"
SEARCH_INDEXES_API_VERSION="2024-05-01-preview"
SEARCH_BOOTSTRAP_TAG_KEY="cdssSearchIndexBootstrapFingerprint"
SEARCH_INDEX_BOOTSTRAP_FINGERPRINT="${SEARCH_INDEX_BOOTSTRAP_FINGERPRINT:-}"
REQUIRED_SEARCH_INDEXES=()

log_info() { echo "[INFO] $1"; }
log_warn() { echo "[WARN] $1"; }
log_error() { echo "[ERROR] $1"; }
log_success() { echo "[SUCCESS] $1"; }
log_stage() { echo ""; echo "[INFO] ===== $1 ====="; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log_error "Required command not found: $1"
    exit 1
  fi
}

wait_for_search_state() {
  local rg="$1"
  local name="$2"
  local expected_pna="$3"
  local timeout_seconds="${4:-600}"
  local started_at now elapsed state pna

  started_at="$(date +%s)"
  while true; do
    state="$(az search service show -g "${rg}" -n "${name}" --query provisioningState -o tsv 2>/dev/null || echo "Unknown")"
    pna="$(az search service show -g "${rg}" -n "${name}" --query publicNetworkAccess -o tsv 2>/dev/null || echo "Unknown")"

    if [[ "${state}" == "succeeded" && "${pna}" == "${expected_pna}" ]]; then
      return 0
    fi

    now="$(date +%s)"
    elapsed=$((now - started_at))
    if (( elapsed >= timeout_seconds )); then
      log_error "Timed out waiting for Search service '${name}' to reach state='succeeded' pna='${expected_pna}'. Last: state=${state}, pna=${pna}"
      return 1
    fi

    log_info "Waiting for Search service update (state=${state}, pna=${pna})..."
    sleep 15
  done
}

compute_index_bootstrap_fingerprint() {
  local file_path="$1"
  if command -v shasum >/dev/null 2>&1; then
    shasum "${file_path}" | awk '{print substr($1,1,12)}'
  elif command -v sha1sum >/dev/null 2>&1; then
    sha1sum "${file_path}" | awk '{print substr($1,1,12)}'
  else
    cksum "${file_path}" | awk '{print $1}'
  fi
}

load_required_search_indexes() {
  REQUIRED_SEARCH_INDEXES=()
  while IFS= read -r index_name; do
    if [[ -n "${index_name}" ]]; then
      REQUIRED_SEARCH_INDEXES+=("${index_name}")
    fi
  done < <("${INDEX_SCRIPT}" --list-required-indexes 2>/dev/null || true)

  if [[ "${#REQUIRED_SEARCH_INDEXES[@]}" -eq 0 ]]; then
    REQUIRED_SEARCH_INDEXES=("patient-records" "treatment-protocols" "medical-literature-cache")
  fi
}

initialize_search_index_metadata() {
  if [[ -z "${SEARCH_INDEX_BOOTSTRAP_FINGERPRINT}" ]]; then
    SEARCH_INDEX_BOOTSTRAP_FINGERPRINT="$(compute_index_bootstrap_fingerprint "${INDEX_SCRIPT}")"
  fi
  load_required_search_indexes
}

get_search_bootstrap_marker() {
  local rg="$1"
  local search_name="$2"
  az search service show \
    --resource-group "${rg}" \
    --name "${search_name}" \
    --query "tags.${SEARCH_BOOTSTRAP_TAG_KEY}" \
    -o tsv 2>/dev/null || true
}

set_search_bootstrap_marker() {
  local rg="$1"
  local search_name="$2"
  local search_id=""
  local timestamp=""
  search_id="$(az search service show --resource-group "${rg}" --name "${search_name}" --query id -o tsv 2>/dev/null || true)"
  if [[ -z "${search_id}" ]]; then
    log_warn "Unable to resolve Search resource ID for bootstrap marker tag."
    return 1
  fi

  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  az resource tag \
    --ids "${search_id}" \
    --is-incremental \
    --tags \
      "${SEARCH_BOOTSTRAP_TAG_KEY}=${SEARCH_INDEX_BOOTSTRAP_FINGERPRINT}" \
      "cdssSearchIndexBootstrapAt=${timestamp}" \
    --only-show-errors \
    --output none
}

get_search_indexes_tsv() {
  local rg="$1"
  local search_name="$2"
  local admin_key=""
  admin_key="$(az search admin-key show --service-name "${search_name}" --resource-group "${rg}" --query primaryKey -o tsv 2>/dev/null || true)"
  if [[ -z "${admin_key}" ]]; then
    log_error "Failed to resolve Search admin key for service '${search_name}'."
    return 1
  fi

  AZURE_CORE_ONLY_SHOW_ERRORS=1 az rest \
    --method get \
    --url "https://${search_name}.search.windows.net/indexes?api-version=${SEARCH_INDEXES_API_VERSION}" \
    --skip-authorization-header \
    --headers "api-key=${admin_key}" \
    --query "value[].name" \
    -o tsv
}

check_required_search_indexes() {
  local rg="$1"
  local search_name="$2"
  local current_indexes=""
  local missing=()
  local index_name=""

  if ! current_indexes="$(get_search_indexes_tsv "${rg}" "${search_name}" 2>&1)"; then
    if [[ "${current_indexes}" == *"publicNetworkAccess: Disabled"* || "${current_indexes}" == *"source is not allowed by applicable rules"* || "${current_indexes}" == *"not from a trusted service"* ]]; then
      return 42
    fi
    echo "${current_indexes}" >&2
    return 1
  fi

  for index_name in "${REQUIRED_SEARCH_INDEXES[@]}"; do
    if ! grep -qx "${index_name}" <<<"${current_indexes}"; then
      missing+=("${index_name}")
    fi
  done

  if [[ "${#missing[@]}" -eq 0 ]]; then
    return 0
  fi

  log_info "Missing Search indexes: ${missing[*]}"
  return 10
}

ensure_search_indexes_bootstrapped() {
  local rg="$1"
  local search_name="$2"
  local original_pna=""
  local restore_pna_arg=""
  local need_restore="false"
  local status=0
  local check_rc=0
  local bootstrap_marker=""

  initialize_search_index_metadata

  bootstrap_marker="$(get_search_bootstrap_marker "${rg}" "${search_name}")"
  if [[ "${bootstrap_marker}" == "${SEARCH_INDEX_BOOTSTRAP_FINGERPRINT}" ]]; then
    log_info "Search index bootstrap already marked current (${SEARCH_INDEX_BOOTSTRAP_FINGERPRINT}); skipping."
    return 0
  fi

  original_pna="$(az search service show -g "${rg}" -n "${search_name}" --query publicNetworkAccess -o tsv 2>/dev/null || echo "Disabled")"
  if [[ -z "${original_pna}" || "${original_pna}" == "null" ]]; then
    original_pna="Disabled"
  fi
  restore_pna_arg="$(echo "${original_pna}" | tr '[:upper:]' '[:lower:]')"

  if [[ "${original_pna}" != "Enabled" ]]; then
    log_warn "Temporarily enabling Search public network access for index pre-check/bootstrap"
    if ! az search service update -g "${rg}" -n "${search_name}" --public-network-access enabled --output none; then
      return 1
    fi
    if ! wait_for_search_state "${rg}" "${search_name}" "Enabled"; then
      return 1
    fi
    need_restore="true"
  fi

  if check_required_search_indexes "${rg}" "${search_name}"; then
    log_info "All required Search indexes already exist. Skipping index creation."
  else
    check_rc=$?
    if [[ "${check_rc}" -eq 10 ]]; then
      log_info "Creating/updating Search indexes"
      if ! "${INDEX_SCRIPT}" "${rg}" "${search_name}"; then
        status=$?
      fi
    else
      log_error "Search index pre-check failed."
      status="${check_rc}"
    fi
  fi

  if [[ "${status}" -eq 0 ]]; then
    if check_required_search_indexes "${rg}" "${search_name}"; then
      if set_search_bootstrap_marker "${rg}" "${search_name}"; then
        log_info "Search bootstrap marker set (${SEARCH_BOOTSTRAP_TAG_KEY}=${SEARCH_INDEX_BOOTSTRAP_FINGERPRINT})."
      else
        log_warn "Could not persist Search bootstrap marker tag; future runs may re-check."
      fi
    else
      log_error "Search index verification failed after bootstrap."
      status=1
    fi
  fi

  if [[ "${need_restore}" == "true" ]]; then
    log_info "Restoring Search public network access to ${restore_pna_arg}"
    if ! az search service update -g "${rg}" -n "${search_name}" --public-network-access "${restore_pna_arg}" --output none; then
      log_error "Failed to restore Search public network access."
      status=1
    elif ! wait_for_search_state "${rg}" "${search_name}" "${original_pna}"; then
      status=1
    fi
  fi

  return "${status}"
}

create_or_resolve_acr_name() {
  local rg="$1"
  if [[ -n "${ACR_NAME}" ]]; then
    echo "${ACR_NAME}"
    return 0
  fi

  local existing
  existing="$(az acr list -g "${rg}" --query "[0].name" -o tsv 2>/dev/null || true)"
  if [[ -n "${existing}" ]]; then
    echo "${existing}"
    return 0
  fi

  # Deterministic, globally unique-ish ACR name per subscription+resource group.
  python - "${SUBSCRIPTION_ID}" "${rg}" <<'PY'
import hashlib
import os
import re
import sys

sub = sys.argv[1]
rg = sys.argv[2]
base = re.sub(r"[^a-z0-9]", "", rg.lower())
base = (base[:24] or "cdss")
suffix = hashlib.sha1(f"{sub}:{rg}".encode()).hexdigest()[:8]
name = f"{base}acr{suffix}"[:50]
if not name[0].isalpha():
    name = f"cdss{name}"[:50]
print(name)
PY
}

require_cmd az
require_cmd bash

normalize_build_mode() {
  local mode="$1"
  mode="$(echo "${mode}" | tr '[:upper:]' '[:lower:]')"
  case "${mode}" in
    auto|local|acr)
      echo "${mode}"
      ;;
    *)
      log_error "Invalid CDSS_IMAGE_BUILD_MODE='${mode}'. Expected one of: auto, local, acr."
      exit 1
      ;;
  esac
}

if ! az account show >/dev/null 2>&1; then
  log_error "Not logged in to Azure CLI. Run: az login"
  exit 1
fi

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
SUBSCRIPTION_NAME="$(az account show --query name -o tsv)"
log_info "Subscription: ${SUBSCRIPTION_NAME} (${SUBSCRIPTION_ID})"

log_info "Ensuring resource group exists: ${RESOURCE_GROUP}"
az group create -n "${RESOURCE_GROUP}" -l "${LOCATION}" --output none

log_stage "Container Image"
if [[ -z "${CONTAINER_IMAGE}" ]]; then
  ACR_NAME="$(create_or_resolve_acr_name "${RESOURCE_GROUP}")"

  if ! az acr show -n "${ACR_NAME}" -g "${RESOURCE_GROUP}" >/dev/null 2>&1; then
    log_info "Creating ACR: ${ACR_NAME}"
    az acr create -n "${ACR_NAME}" -g "${RESOURCE_GROUP}" -l "${LOCATION}" --sku Standard --output none
  else
    log_info "Using existing ACR: ${ACR_NAME}"
  fi

  CONTAINER_IMAGE="${ACR_NAME}.azurecr.io/cdss-api:${IMAGE_TAG}"
  BUILD_MODE="$(normalize_build_mode "${CDSS_IMAGE_BUILD_MODE}")"

  if [[ "${SKIP_IMAGE_BUILD}" != "true" ]]; then
    if [[ "${BUILD_MODE}" == "auto" ]]; then
      if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        BUILD_MODE="local"
      else
        BUILD_MODE="acr"
      fi
    fi

    if [[ "${BUILD_MODE}" == "local" ]]; then
      require_cmd docker
      log_info "Image build mode: local docker buildx"
      log_info "Logging in to ACR: ${ACR_NAME}"
      az acr login -n "${ACR_NAME}" --output none

      log_info "Preparing docker buildx builder"
      docker buildx create --name cdssbuilder --use >/dev/null 2>&1 || docker buildx use cdssbuilder >/dev/null
      docker buildx inspect --bootstrap >/dev/null

      log_info "Building and pushing backend image: ${CONTAINER_IMAGE}"
      docker buildx build --platform linux/amd64 -t "${CONTAINER_IMAGE}" --push .
    else
      log_info "Image build mode: ACR cloud build"
      log_info "Building and pushing backend image in ACR: ${CONTAINER_IMAGE}"
      az acr build \
        --registry "${ACR_NAME}" \
        --image "cdss-api:${IMAGE_TAG}" \
        --platform linux/amd64 \
        .
    fi
  else
    log_warn "SKIP_IMAGE_BUILD=true, expecting image already exists: ${CONTAINER_IMAGE}"
  fi

  log_info "Verifying image tag in ACR"
  az acr repository show --name "${ACR_NAME}" --image "cdss-api:${IMAGE_TAG}" --output none
else
  if [[ -z "${ACR_NAME}" ]]; then
    ACR_NAME="${CONTAINER_IMAGE%%/*}"
    ACR_NAME="${ACR_NAME%%.azurecr.io}"
  fi
  log_info "Using pre-supplied container image: ${CONTAINER_IMAGE}"
fi

log_stage "Infrastructure Deploy"
log_info "Deploying infrastructure and app via deploy.sh"
CONTAINER_IMAGE="${CONTAINER_IMAGE}" \
ACR_NAME="${ACR_NAME}" \
"${DEPLOY_SCRIPT}" "${ENVIRONMENT}" "${RESOURCE_GROUP}" "${LOCATION}" "${PROD_PUBLIC_API}"

if [[ -x "${COSMOS_EMBEDDING_POLICY_SCRIPT}" ]]; then
  log_stage "Cosmos Embedding Cache Policy"
  if ! "${COSMOS_EMBEDDING_POLICY_SCRIPT}" "${RESOURCE_GROUP}"; then
    log_error "Cosmos embedding cache policy stage failed."
    exit 1
  fi
else
  log_warn "Cosmos embedding policy script not found/executable: ${COSMOS_EMBEDDING_POLICY_SCRIPT}"
fi

if [[ -x "${OPENAI_ACCESS_SCRIPT}" ]]; then
  log_stage "OpenAI Runtime Connectivity"
  if ! "${OPENAI_ACCESS_SCRIPT}" "${RESOURCE_GROUP}"; then
    log_error "OpenAI runtime connectivity stage failed."
    log_error "If your runtime has private-link-only access configured and verified, set CDSS_OPENAI_NETWORK_AUTOFIX=false."
    exit 1
  fi
else
  log_warn "OpenAI connectivity script not found/executable: ${OPENAI_ACCESS_SCRIPT}"
fi

if [[ "${SKIP_SEARCH_BOOTSTRAP}" != "true" ]]; then
  log_stage "Search Bootstrap"
  SEARCH_NAME="$(az search service list -g "${RESOURCE_GROUP}" --query "[0].name" -o tsv 2>/dev/null || true)"
  if [[ -n "${SEARCH_NAME}" ]]; then
    if ! ensure_search_indexes_bootstrapped "${RESOURCE_GROUP}" "${SEARCH_NAME}"; then
      log_error "Search bootstrap stage failed."
      exit 1
    fi
  else
    log_warn "No Search service found; skipping index bootstrap"
  fi
else
  log_warn "Skipping Search bootstrap by request"
fi

if [[ -x "${POPULATE_ENV_SCRIPT}" ]]; then
  log_stage "Environment Materialization"
  log_info "Generating local env files from Azure resources"
  "${POPULATE_ENV_SCRIPT}" "${RESOURCE_GROUP}" || log_warn "populate-env.sh failed; continue manually if needed."
fi

APP_NAME="$(az containerapp list -g "${RESOURCE_GROUP}" --query "[?contains(name,'-api')].name | [0]" -o tsv 2>/dev/null || true)"
if [[ "${SKIP_AUTH_SETUP}" != "true" && -n "${APP_NAME}" ]]; then
  log_stage "Entra Auth Setup"
  log_info "Running Entra SPA auth setup"
  "${AUTH_SCRIPT}" --resource-group "${RESOURCE_GROUP}" --container-app-name "${APP_NAME}" || \
    log_warn "setup-entra-spa-auth.sh failed; run it manually if tenant permissions are restricted."
else
  log_info "Skipping Entra SPA auth setup (SKIP_AUTH_SETUP=${SKIP_AUTH_SETUP})"
fi

if [[ "${ENVIRONMENT}" == "prod" && -n "${APP_NAME}" && -x "${PUBMED_CONFIG_SCRIPT}" ]]; then
  if [[ -n "${CDSS_PUBMED_API_KEY:-}" && -n "${CDSS_PUBMED_EMAIL:-}" ]]; then
    log_stage "PubMed Configuration"
    log_info "Configuring PubMed credentials in production backend (Key Vault + secretRef)..."
    CDSS_PUBMED_API_KEY="${CDSS_PUBMED_API_KEY}" \
    CDSS_PUBMED_EMAIL="${CDSS_PUBMED_EMAIL}" \
      "${PUBMED_CONFIG_SCRIPT}" "${RESOURCE_GROUP}" "${APP_NAME}" || \
      log_warn "PubMed production configuration failed; run configure-pubmed-prod.sh manually."
  else
    log_warn "PubMed credentials not provided. Backend will run without CDSS_PUBMED_API_KEY/CDSS_PUBMED_EMAIL."
    log_warn "Provide CDSS_PUBMED_API_KEY and CDSS_PUBMED_EMAIL to bootstrap-deploy.sh for auto-configuration."
  fi
fi

API_FQDN=""
if [[ -n "${APP_NAME}" ]]; then
  API_FQDN="$(az containerapp show -g "${RESOURCE_GROUP}" -n "${APP_NAME}" --query properties.configuration.ingress.fqdn -o tsv 2>/dev/null || true)"
fi

log_success "Bootstrap deployment completed"
echo ""
echo "Next steps:"
echo "  1) Frontend auth setup (if skipped): ./infra/scripts/setup-entra-spa-auth.sh --resource-group ${RESOURCE_GROUP} --container-app-name ${APP_NAME:-<api-app-name>}"
echo "  2) (Prod recommended) Configure PubMed in backend runtime:"
echo "     CDSS_PUBMED_API_KEY=<key> CDSS_PUBMED_EMAIL=<email> ./infra/scripts/configure-pubmed-prod.sh ${RESOURCE_GROUP} ${APP_NAME:-<api-app-name>}"
echo "  3) Start frontend: cd frontend && npm install && npm run dev"
if [[ -n "${API_FQDN}" ]]; then
  echo "  4) API docs: https://${API_FQDN}/docs"
fi
