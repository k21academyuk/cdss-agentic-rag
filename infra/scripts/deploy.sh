#!/bin/bash
# ============================================================================
# Clinical Decision Support System - Azure Infrastructure Deployment
# ============================================================================
#
# Usage:
#   ./deploy.sh <environment> <resource-group> [location] [prod-public-api] [container-image]
#
# Examples:
#   ./deploy.sh dev cdss-dev-rg eastus2
#   ./deploy.sh staging cdss-staging-rg eastus2
#   ./deploy.sh prod cdss-prod-rg eastus2
#   ./deploy.sh prod cdss-prod-rg eastus2 true
#   ./deploy.sh prod cdss-prod-rg eastus2 true myacr.azurecr.io/cdss-api:2026.03.14
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - Sufficient permissions to create resources in the subscription
#   - Bicep CLI installed (comes with Azure CLI >= 2.20.0)
#
# ============================================================================

set -euo pipefail

# --- Color output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# --- Parse arguments ---
ENVIRONMENT="${1:-}"
RESOURCE_GROUP="${2:-}"
LOCATION="${3:-eastus2}"
PROD_PUBLIC_API_OVERRIDE="${4:-${PROD_PUBLIC_API:-}}"
CONTAINER_IMAGE_OVERRIDE="${5:-${CONTAINER_IMAGE:-}}"
ACR_NAME_OVERRIDE="${ACR_NAME:-}"
ACR_CREATE_OVERRIDE="${ACR_CREATE:-}"
ACR_SKU_OVERRIDE="${ACR_SKU:-}"
DEFAULT_PLACEHOLDER_IMAGE="cdssacr.azurecr.io/cdss-api:latest"
PARAMS_PARSE_AVAILABLE="false"
PARAMS_CONTAINER_IMAGE=""
EFFECTIVE_CONTAINER_IMAGE=""

if [[ -z "$ENVIRONMENT" || -z "$RESOURCE_GROUP" ]]; then
    echo "Usage: $0 <environment> <resource-group> [location] [prod-public-api] [container-image]"
    echo ""
    echo "Arguments:"
    echo "  environment     Target environment: dev, staging, or prod"
    echo "  resource-group  Azure resource group name"
    echo "  location        Azure region (default: eastus2)"
    echo "  prod-public-api Optional true/false override for prod API exposure"
    echo "  container-image Optional container image override (or use CONTAINER_IMAGE env var)"
    echo ""
    echo "Examples:"
    echo "  $0 dev cdss-dev-rg"
    echo "  $0 prod cdss-prod-rg westus2"
    echo "  $0 prod cdss-prod-rg eastus2 true"
    echo ""
    echo "Environment variable alternative:"
    echo "  PROD_PUBLIC_API=true $0 prod cdss-prod-rg"
    echo "  CONTAINER_IMAGE=<acr>.azurecr.io/cdss-api:<tag> ACR_CREATE=true $0 prod <rg>"
    exit 1
fi

# Validate environment
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "prod" ]]; then
    log_error "Invalid environment: $ENVIRONMENT. Must be one of: dev, staging, prod"
    exit 1
fi

if [[ -n "$PROD_PUBLIC_API_OVERRIDE" && "$PROD_PUBLIC_API_OVERRIDE" != "true" && "$PROD_PUBLIC_API_OVERRIDE" != "false" ]]; then
    log_error "Invalid prod-public-api value: $PROD_PUBLIC_API_OVERRIDE. Must be true or false."
    exit 1
fi

if [[ -n "$ACR_CREATE_OVERRIDE" && "$ACR_CREATE_OVERRIDE" != "true" && "$ACR_CREATE_OVERRIDE" != "false" ]]; then
    log_error "Invalid ACR_CREATE value: $ACR_CREATE_OVERRIDE. Must be true or false."
    exit 1
fi

if [[ -n "$ACR_SKU_OVERRIDE" && "$ACR_SKU_OVERRIDE" != "Basic" && "$ACR_SKU_OVERRIDE" != "Standard" && "$ACR_SKU_OVERRIDE" != "Premium" ]]; then
    log_error "Invalid ACR_SKU value: $ACR_SKU_OVERRIDE. Must be one of: Basic, Standard, Premium."
    exit 1
fi

if [[ "$ENVIRONMENT" != "prod" && -n "$PROD_PUBLIC_API_OVERRIDE" ]]; then
    log_warn "Ignoring prod-public-api override for non-prod environment: ${ENVIRONMENT}"
fi

# --- Configuration ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BICEP_DIR="${SCRIPT_DIR}/../bicep"
BICEP_FILE="${BICEP_DIR}/main.bicep"
PARAMS_FILE="${BICEP_DIR}/parameters.${ENVIRONMENT}.json"
CREATE_INDEX_SCRIPT="${SCRIPT_DIR}/create-search-indexes.sh"
PIN_TRAFFIC_SCRIPT="${SCRIPT_DIR}/pin-containerapp-latest-ready.sh"
DEPLOYMENT_NAME="cdss-${ENVIRONMENT}-$(date +%Y%m%d%H%M%S)"
EXTRA_BICEP_PARAMS=""
OPENAI_RESTORE_ENABLED="false"
DOCINTEL_RESTORE_ENABLED="false"
MAX_DEPLOY_RETRIES="${MAX_DEPLOY_RETRIES:-3}"
CDSS_PIN_LATEST_READY_TRAFFIC="${CDSS_PIN_LATEST_READY_TRAFFIC:-true}"

get_deployment_output() {
    local output_name="$1"
    az deployment group show \
        --name "${DEPLOYMENT_NAME}" \
        --resource-group "${RESOURCE_GROUP}" \
        --query "properties.outputs.${output_name}.value" \
        --output tsv 2>/dev/null || true
}

derive_acr_name_from_image() {
    local image_ref="$1"
    local registry_host
    registry_host="${image_ref%%/*}"
    if [[ "$registry_host" == *.azurecr.io ]]; then
        echo "${registry_host%%.azurecr.io}"
    fi
}

parse_param_value() {
    local key="$1"
    if [[ "${PARAMS_PARSE_AVAILABLE}" != "true" ]]; then
        return 0
    fi
    jq -r --arg key "$key" '.parameters[$key].value // empty' "$PARAMS_FILE" 2>/dev/null || true
}

verify_acr_image_exists() {
    local image_ref="$1"
    local registry_host image_path acr_name

    registry_host="${image_ref%%/*}"
    image_path="${image_ref#*/}"

    if [[ "$registry_host" != *.azurecr.io || "$image_path" == "$image_ref" ]]; then
        return 0
    fi

    acr_name="${registry_host%%.azurecr.io}"
    if ! az acr repository show --name "$acr_name" --image "$image_path" --output none >/dev/null 2>&1; then
        log_error "Container image not found in ACR: ${image_ref}"
        log_error "Push the exact tag first, then redeploy."
        log_error "Tip: ./infra/scripts/bootstrap-deploy.sh can build/push/deploy in the correct order."
        return 1
    fi

    return 0
}

validate_private_networking() {
    local failures=0
    local openai_resource_id=""
    local docintel_resource_id=""

    normalize_bool_value() {
        echo "$1" | tr '[:upper:]' '[:lower:]'
    }

    if [[ -z "${OPENAI_NAME}" ]]; then
        log_error "OpenAI account name could not be resolved."
        failures=$((failures + 1))
    else
        local openai_pna
        openai_pna=$(az cognitiveservices account show -n "${OPENAI_NAME}" -g "${RESOURCE_GROUP}" --query "properties.publicNetworkAccess" -o tsv 2>/dev/null || echo "")
        if [[ "$(normalize_bool_value "${openai_pna}")" != "disabled" ]]; then
            log_error "OpenAI public network access is not disabled (current: ${openai_pna:-unknown})."
            failures=$((failures + 1))
        fi
        openai_resource_id=$(az cognitiveservices account show -n "${OPENAI_NAME}" -g "${RESOURCE_GROUP}" --query "id" -o tsv 2>/dev/null || echo "")
    fi

    if [[ -z "${DOCINTEL_NAME}" ]]; then
        log_error "Document Intelligence account name could not be resolved."
        failures=$((failures + 1))
    else
        local docintel_pna
        docintel_pna=$(az cognitiveservices account show -n "${DOCINTEL_NAME}" -g "${RESOURCE_GROUP}" --query "properties.publicNetworkAccess" -o tsv 2>/dev/null || echo "")
        if [[ "$(normalize_bool_value "${docintel_pna}")" != "disabled" ]]; then
            log_error "Document Intelligence public network access is not disabled (current: ${docintel_pna:-unknown})."
            failures=$((failures + 1))
        fi
        docintel_resource_id=$(az cognitiveservices account show -n "${DOCINTEL_NAME}" -g "${RESOURCE_GROUP}" --query "id" -o tsv 2>/dev/null || echo "")
    fi

    local cosmos_pna
    cosmos_pna=$(az cosmosdb show -n "${COSMOS_NAME}" -g "${RESOURCE_GROUP}" --query "publicNetworkAccess" -o tsv 2>/dev/null || echo "")
    if [[ "$(normalize_bool_value "${cosmos_pna}")" != "disabled" ]]; then
        log_error "Cosmos DB public network access is not disabled (current: ${cosmos_pna:-unknown})."
        failures=$((failures + 1))
    fi

    local search_pna
    search_pna=$(az search service show --name "${SEARCH_NAME}" --resource-group "${RESOURCE_GROUP}" --query "publicNetworkAccess" -o tsv 2>/dev/null || echo "")
    if [[ "$(normalize_bool_value "${search_pna}")" != "disabled" ]]; then
        log_error "AI Search public network access is not disabled (current: ${search_pna:-unknown})."
        failures=$((failures + 1))
    fi

    local openai_pe_count
    openai_pe_count="0"
    if [[ -n "${openai_resource_id}" ]]; then
        openai_pe_count=$(az network private-endpoint-connection list \
            --id "${openai_resource_id}" \
            --query "length([?properties.privateLinkServiceConnectionState.status=='Approved' || properties.privateLinkServiceConnectionState.status=='Pending'])" \
            -o tsv 2>/dev/null || echo "0")
    fi
    if [[ "${openai_pe_count}" -lt 1 ]]; then
        log_error "OpenAI private endpoint connection not found."
        failures=$((failures + 1))
    fi

    local docintel_pe_count
    docintel_pe_count="0"
    if [[ -n "${docintel_resource_id}" ]]; then
        docintel_pe_count=$(az network private-endpoint-connection list \
            --id "${docintel_resource_id}" \
            --query "length([?properties.privateLinkServiceConnectionState.status=='Approved' || properties.privateLinkServiceConnectionState.status=='Pending'])" \
            -o tsv 2>/dev/null || echo "0")
    fi
    if [[ "${docintel_pe_count}" -lt 1 ]]; then
        log_error "Document Intelligence private endpoint connection not found."
        failures=$((failures + 1))
    fi

    if [[ "${failures}" -gt 0 ]]; then
        return 1
    fi

    return 0
}

extract_cognitive_accounts_from_error() {
    local error_text="$1"
    echo "${error_text}" \
        | grep -oE 'Microsoft\.CognitiveServices/accounts/[A-Za-z0-9-]+' \
        | awk -F'/' '{print $NF}' \
        | sort -u
}

is_transient_cognitive_provisioning_error() {
    local error_text="$1"
    if [[ "${error_text}" == *"AccountProvisioningStateInvalid"* ]]; then
        return 0
    fi
    if [[ "${error_text}" == *"Microsoft.CognitiveServices/accounts"* && "${error_text}" == *"state Accepted"* ]]; then
        return 0
    fi
    return 1
}

wait_for_cognitive_accounts_ready() {
    local timeout_seconds="${1:-1800}"
    shift || true
    local accounts=("$@")
    local started_at now elapsed state

    if [[ ${#accounts[@]} -eq 0 ]]; then
        return 1
    fi

    started_at="$(date +%s)"
    for account in "${accounts[@]}"; do
        if [[ -z "${account}" ]]; then
            continue
        fi

        log_warn "Waiting for Cognitive account '${account}' to reach Succeeded..."
        while true; do
            state="$(az cognitiveservices account show \
                --resource-group "${RESOURCE_GROUP}" \
                --name "${account}" \
                --query "properties.provisioningState" \
                -o tsv 2>/dev/null || echo "Unknown")"

            case "${state}" in
                Succeeded)
                    log_success "Cognitive account '${account}' is Succeeded."
                    break
                    ;;
                Failed)
                    log_error "Cognitive account '${account}' provisioning failed."
                    return 1
                    ;;
                *)
                    now="$(date +%s)"
                    elapsed=$((now - started_at))
                    if (( elapsed >= timeout_seconds )); then
                        log_error "Timed out waiting for '${account}' (last state: ${state})."
                        return 1
                    fi
                    log_info "Current state for '${account}': ${state}. Rechecking in 30s..."
                    sleep 30
                    ;;
            esac
        done
    done

    return 0
}

# --- Preflight checks ---
log_info "Running preflight checks..."

# Check Azure CLI
if ! command -v az &> /dev/null; then
    log_error "Azure CLI is not installed. Please install it: https://docs.microsoft.com/cli/azure/install-azure-cli"
    exit 1
fi

# Check if logged in
ACCOUNT=$(az account show --query "name" -o tsv 2>/dev/null || true)
if [[ -z "$ACCOUNT" ]]; then
    log_error "Not logged into Azure CLI. Please run: az login"
    exit 1
fi
log_info "Azure account: ${ACCOUNT}"

# Check subscription
SUBSCRIPTION_ID=$(az account show --query "id" -o tsv)
SUBSCRIPTION_NAME=$(az account show --query "name" -o tsv)
TENANT_ID=$(az account show --query "tenantId" -o tsv)
log_info "Subscription: ${SUBSCRIPTION_NAME} (${SUBSCRIPTION_ID})"

# Check Bicep file exists
if [[ ! -f "$BICEP_FILE" ]]; then
    log_error "Bicep template not found: ${BICEP_FILE}"
    exit 1
fi

# Check parameters file exists
if [[ ! -f "$PARAMS_FILE" ]]; then
    log_warn "Parameters file not found: ${PARAMS_FILE}"
    log_warn "Proceeding with default parameters only."
    PARAMS_FILE=""
fi

if [[ -n "$PARAMS_FILE" && -f "$PARAMS_FILE" ]] && command -v jq >/dev/null 2>&1; then
    PARAMS_PARSE_AVAILABLE="true"
    PARAMS_CONTAINER_IMAGE="$(parse_param_value "containerImage")"
fi

if [[ -n "$CONTAINER_IMAGE_OVERRIDE" ]]; then
    EFFECTIVE_CONTAINER_IMAGE="$CONTAINER_IMAGE_OVERRIDE"
elif [[ -n "$PARAMS_CONTAINER_IMAGE" ]]; then
    EFFECTIVE_CONTAINER_IMAGE="$PARAMS_CONTAINER_IMAGE"
fi

if [[ -n "$EFFECTIVE_CONTAINER_IMAGE" && "$EFFECTIVE_CONTAINER_IMAGE" == "$DEFAULT_PLACEHOLDER_IMAGE" ]]; then
    if [[ "$ENVIRONMENT" == "prod" ]]; then
        log_error "Container image is still the placeholder: ${DEFAULT_PLACEHOLDER_IMAGE}"
        log_error "Set a real image before production deployment."
        echo "Example:"
        echo "  CONTAINER_IMAGE=<acr>.azurecr.io/cdss-api:<tag> ACR_NAME=<acr> ACR_CREATE=true $0 prod ${RESOURCE_GROUP} ${LOCATION} ${PROD_PUBLIC_API_OVERRIDE:-false}"
        echo "Or use the first-run bootstrap wrapper:"
        echo "  ./infra/scripts/bootstrap-deploy.sh prod ${RESOURCE_GROUP} ${LOCATION}"
        exit 1
    fi
    log_warn "Container image is still the placeholder: ${DEFAULT_PLACEHOLDER_IMAGE}"
fi

if [[ -n "$EFFECTIVE_CONTAINER_IMAGE" ]]; then
    if ! verify_acr_image_exists "$EFFECTIVE_CONTAINER_IMAGE"; then
        exit 1
    fi
fi

if [[ "$ACR_CREATE_OVERRIDE" == "true" && -z "$ACR_NAME_OVERRIDE" ]]; then
    if [[ -n "$EFFECTIVE_CONTAINER_IMAGE" ]]; then
        ACR_NAME_OVERRIDE="$(derive_acr_name_from_image "$EFFECTIVE_CONTAINER_IMAGE")"
    fi
    if [[ -z "$ACR_NAME_OVERRIDE" ]]; then
        log_error "ACR_CREATE=true requires ACR_NAME or an Azure Container Registry image (e.g., *.azurecr.io/repo:tag)."
        exit 1
    fi
fi

if [[ "$ACR_CREATE_OVERRIDE" == "true" && -z "$CONTAINER_IMAGE_OVERRIDE" && "$EFFECTIVE_CONTAINER_IMAGE" == "$DEFAULT_PLACEHOLDER_IMAGE" ]]; then
    log_warn "ACR_CREATE=true set without a real container image."
    log_warn "ACR will be created, but Container App revision creation will fail until the image is pushed."
fi

# --- Confirmation for production ---
if [[ "$ENVIRONMENT" == "prod" ]]; then
    echo ""
    log_warn "============================================"
    log_warn "  PRODUCTION DEPLOYMENT"
    log_warn "============================================"
    log_warn "Environment:    ${ENVIRONMENT}"
    log_warn "Resource Group: ${RESOURCE_GROUP}"
    log_warn "Location:       ${LOCATION}"
    log_warn "Subscription:   ${SUBSCRIPTION_NAME}"
    if [[ -n "$EFFECTIVE_CONTAINER_IMAGE" ]]; then
        if [[ -n "$CONTAINER_IMAGE_OVERRIDE" ]]; then
            log_warn "Container Img:  ${EFFECTIVE_CONTAINER_IMAGE} (override)"
        else
            log_warn "Container Img:  ${EFFECTIVE_CONTAINER_IMAGE} (params)"
        fi
    fi
    if [[ "$ACR_CREATE_OVERRIDE" == "true" ]]; then
        log_warn "ACR Provision:  CREATE via IaC (ACR_CREATE=true)"
        if [[ -n "$ACR_NAME_OVERRIDE" ]]; then
            log_warn "ACR Name:       ${ACR_NAME_OVERRIDE}"
        fi
        if [[ -n "$ACR_SKU_OVERRIDE" ]]; then
            log_warn "ACR SKU:        ${ACR_SKU_OVERRIDE}"
        fi
    fi
    if [[ -n "$PROD_PUBLIC_API_OVERRIDE" ]]; then
        if [[ "$PROD_PUBLIC_API_OVERRIDE" == "true" ]]; then
            log_warn "API Exposure:   PUBLIC (override)"
        else
            log_warn "API Exposure:   PRIVATE (override)"
        fi
    fi
    echo ""
    read -p "Are you sure you want to deploy to PRODUCTION? (yes/no): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        log_info "Deployment cancelled."
        exit 0
    fi
fi

# --- Create resource group if it does not exist ---
log_info "Checking resource group: ${RESOURCE_GROUP}..."
RG_EXISTS=$(az group exists --name "$RESOURCE_GROUP")
if [[ "$RG_EXISTS" == "false" ]]; then
    log_info "Creating resource group: ${RESOURCE_GROUP} in ${LOCATION}..."
    az group create \
        --name "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --tags "project=cdss-agentic-rag" "environment=${ENVIRONMENT}" "managedBy=bicep" \
        --output none
    log_success "Resource group created: ${RESOURCE_GROUP}"
else
    log_info "Resource group already exists: ${RESOURCE_GROUP}"
fi

# --- Validate Bicep template ---
log_info "Validating Bicep template..."
refresh_extra_bicep_params() {
    local effective_acr_name="$ACR_NAME_OVERRIDE"
    EXTRA_BICEP_PARAMS=""

    if [[ "$OPENAI_RESTORE_ENABLED" == "true" ]]; then
        EXTRA_BICEP_PARAMS="${EXTRA_BICEP_PARAMS} openaiRestore=true"
    fi

    if [[ "$DOCINTEL_RESTORE_ENABLED" == "true" ]]; then
        EXTRA_BICEP_PARAMS="${EXTRA_BICEP_PARAMS} docIntelRestore=true"
    fi

    if [[ "$ENVIRONMENT" == "prod" && -n "$PROD_PUBLIC_API_OVERRIDE" ]]; then
        EXTRA_BICEP_PARAMS="${EXTRA_BICEP_PARAMS} prodPublicApi=${PROD_PUBLIC_API_OVERRIDE}"
    fi

    if [[ -n "$CONTAINER_IMAGE_OVERRIDE" ]]; then
        EXTRA_BICEP_PARAMS="${EXTRA_BICEP_PARAMS} containerImage=${CONTAINER_IMAGE_OVERRIDE}"
        if [[ -z "$effective_acr_name" ]]; then
            effective_acr_name="$(derive_acr_name_from_image "$CONTAINER_IMAGE_OVERRIDE")"
        fi
    fi

    if [[ -n "$effective_acr_name" ]]; then
        EXTRA_BICEP_PARAMS="${EXTRA_BICEP_PARAMS} acrUseManagedIdentity=true acrName=${effective_acr_name}"
    fi

    if [[ "$ACR_CREATE_OVERRIDE" == "true" ]]; then
        EXTRA_BICEP_PARAMS="${EXTRA_BICEP_PARAMS} acrCreate=true"
        if [[ -n "$ACR_SKU_OVERRIDE" ]]; then
            EXTRA_BICEP_PARAMS="${EXTRA_BICEP_PARAMS} acrSku=${ACR_SKU_OVERRIDE}"
        fi
    fi

    EXTRA_BICEP_PARAMS="$(echo "$EXTRA_BICEP_PARAMS" | xargs)"
}

run_validate() {
    local cmd="az deployment group validate \
        --resource-group ${RESOURCE_GROUP} \
        --template-file ${BICEP_FILE} \
        --parameters environment=${ENVIRONMENT} location=${LOCATION}"

    if [[ -n "${PARAMS_FILE}" ]]; then
        cmd="${cmd} --parameters @${PARAMS_FILE}"
    fi

    if [[ -n "${EXTRA_BICEP_PARAMS}" ]]; then
        cmd="${cmd} --parameters ${EXTRA_BICEP_PARAMS}"
    fi

    eval "$cmd" --output none 2>&1
}

refresh_extra_bicep_params
for _ in 1 2 3; do
    set +e
    VALIDATE_OUTPUT=$(run_validate)
    VALIDATE_STATUS=$?
    set -e

    if [[ $VALIDATE_STATUS -eq 0 ]]; then
        break
    fi

    if [[ "$VALIDATE_OUTPUT" != *"FlagMustBeSetForRestore"* ]]; then
        break
    fi

    if [[ "$VALIDATE_OUTPUT" == *"docintel"* || "$VALIDATE_OUTPUT" == *"FormRecognizer"* ]]; then
        if [[ "$DOCINTEL_RESTORE_ENABLED" != "true" ]]; then
            log_warn "Detected a soft-deleted Document Intelligence account with the same name."
            log_warn "Retrying validation with docIntelRestore=true..."
            DOCINTEL_RESTORE_ENABLED="true"
            refresh_extra_bicep_params
            continue
        fi
    fi

    if [[ "$VALIDATE_OUTPUT" == *"oai"* || "$VALIDATE_OUTPUT" == *"OpenAI"* ]]; then
        if [[ "$OPENAI_RESTORE_ENABLED" != "true" ]]; then
            log_warn "Detected a soft-deleted Azure OpenAI account with the same name."
            log_warn "Retrying validation with openaiRestore=true..."
            OPENAI_RESTORE_ENABLED="true"
            refresh_extra_bicep_params
            continue
        fi
    fi

    if [[ "$OPENAI_RESTORE_ENABLED" != "true" ]]; then
        log_warn "Detected a soft-deleted AI account. Retrying validation with openaiRestore=true..."
        OPENAI_RESTORE_ENABLED="true"
        refresh_extra_bicep_params
        continue
    fi

    if [[ "$DOCINTEL_RESTORE_ENABLED" != "true" ]]; then
        log_warn "Detected a soft-deleted AI account. Retrying validation with docIntelRestore=true..."
        DOCINTEL_RESTORE_ENABLED="true"
        refresh_extra_bicep_params
        continue
    fi

    break
done

if [[ $VALIDATE_STATUS -eq 0 ]]; then
    log_success "Template validation passed."
elif [[ "$VALIDATE_OUTPUT" == *"715-123420"* ]]; then
    log_warn "Azure template validation returned internal error 715-123420."
    log_warn "Proceeding with deployment anyway (resources may already exist)."
else
    echo "$VALIDATE_OUTPUT"
    log_error "Template validation failed. Fix the errors above and retry."
    exit 1
fi

# --- Run What-If (preview changes) ---
log_info "Running what-if analysis..."
WHATIF_CMD="az deployment group what-if \
    --resource-group ${RESOURCE_GROUP} \
    --template-file ${BICEP_FILE} \
    --parameters environment=${ENVIRONMENT} location=${LOCATION}"

if [[ -n "${PARAMS_FILE}" ]]; then
    WHATIF_CMD="${WHATIF_CMD} --parameters @${PARAMS_FILE}"
fi

if [[ -n "${EXTRA_BICEP_PARAMS}" ]]; then
    WHATIF_CMD="${WHATIF_CMD} --parameters ${EXTRA_BICEP_PARAMS}"
fi

eval "$WHATIF_CMD" 2>&1 || true

echo ""
if [[ "$ENVIRONMENT" != "dev" ]]; then
    read -p "Review the changes above. Proceed with deployment? (yes/no): " PROCEED
    if [[ "$PROCEED" != "yes" ]]; then
        log_info "Deployment cancelled."
        exit 0
    fi
fi

# --- Deploy ---
log_info "Starting deployment: ${DEPLOYMENT_NAME}..."
log_info "This may take 15-30 minutes..."

DEPLOY_CMD="az deployment group create \
    --name ${DEPLOYMENT_NAME} \
    --resource-group ${RESOURCE_GROUP} \
    --template-file ${BICEP_FILE} \
    --parameters environment=${ENVIRONMENT} location=${LOCATION}"

if [[ -n "${PARAMS_FILE}" ]]; then
    DEPLOY_CMD="${DEPLOY_CMD} --parameters @${PARAMS_FILE}"
fi

if [[ -n "${EXTRA_BICEP_PARAMS}" ]]; then
    DEPLOY_CMD="${DEPLOY_CMD} --parameters ${EXTRA_BICEP_PARAMS}"
fi

DEPLOY_ATTEMPT=1
DEPLOY_STATUS=1
DEPLOY_OUTPUT=""
while (( DEPLOY_ATTEMPT <= MAX_DEPLOY_RETRIES )); do
    log_info "Deployment attempt ${DEPLOY_ATTEMPT}/${MAX_DEPLOY_RETRIES}..."
    set +e
    DEPLOY_OUTPUT=$(eval "$DEPLOY_CMD" --output json 2>&1)
    DEPLOY_STATUS=$?
    set -e

    if [[ ${DEPLOY_STATUS} -eq 0 ]]; then
        break
    fi

    if (( DEPLOY_ATTEMPT < MAX_DEPLOY_RETRIES )) && is_transient_cognitive_provisioning_error "${DEPLOY_OUTPUT}"; then
        log_warn "Detected transient Cognitive provisioning state issue."
        COGNITIVE_ACCOUNTS=()
        while IFS= read -r account; do
            if [[ -n "${account}" ]]; then
                COGNITIVE_ACCOUNTS+=("${account}")
            fi
        done < <(extract_cognitive_accounts_from_error "${DEPLOY_OUTPUT}")

        if [[ ${#COGNITIVE_ACCOUNTS[@]} -eq 0 ]]; then
            while IFS= read -r account; do
                if [[ -n "${account}" ]]; then
                    COGNITIVE_ACCOUNTS+=("${account}")
                fi
            done < <(az cognitiveservices account list \
                --resource-group "${RESOURCE_GROUP}" \
                --query "[?kind=='OpenAI' || kind=='FormRecognizer'].name" \
                -o tsv 2>/dev/null || true)
        fi

        if wait_for_cognitive_accounts_ready 1800 "${COGNITIVE_ACCOUNTS[@]}"; then
            DEPLOY_ATTEMPT=$((DEPLOY_ATTEMPT + 1))
            continue
        fi
    fi

    break
done

if [[ $DEPLOY_STATUS -ne 0 ]]; then
    log_error "Deployment failed!"
    echo "$DEPLOY_OUTPUT"

    # Show deployment operations for debugging
    log_info "Fetching deployment error details..."
    az deployment group show \
        --name "$DEPLOYMENT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "properties.error" \
        --output json 2>/dev/null || true

    az deployment operation group list \
        --name "$DEPLOYMENT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "[?properties.provisioningState=='Failed'].{resource:properties.targetResource.resourceName, status:properties.statusMessage.error}" \
        --output table 2>/dev/null || true

    exit 1
fi

log_success "Deployment completed successfully!"
if [[ "$OPENAI_RESTORE_ENABLED" == "true" ]]; then
    log_warn "Azure OpenAI was deployed in restore mode due to soft-delete detection."
fi
if [[ "$DOCINTEL_RESTORE_ENABLED" == "true" ]]; then
    log_warn "Document Intelligence was deployed in restore mode due to soft-delete detection."
fi

# --- Fetch resource details directly from Azure ---
log_info "Fetching deployed resource details..."

# Get resource names
COSMOS_NAME=$(az cosmosdb list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")
SEARCH_NAME=$(az search service list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")
OPENAI_NAME=$(az cognitiveservices account list -g "$RESOURCE_GROUP" --query "[?kind=='OpenAI'].name | [0]" -o tsv 2>/dev/null || echo "")
DOCINTEL_NAME=$(az cognitiveservices account list -g "$RESOURCE_GROUP" --query "[?kind=='FormRecognizer'].name | [0]" -o tsv 2>/dev/null || echo "")
if [[ -z "${DOCINTEL_NAME}" ]]; then
    DOCINTEL_NAME=$(az cognitiveservices account list -g "$RESOURCE_GROUP" --query "[?kind=='DocumentIntelligence'].name | [0]" -o tsv 2>/dev/null || echo "")
fi
STORAGE_NAME=$(az storage account list -g "$RESOURCE_GROUP" --query "[?tags.project=='cdss-agentic-rag'].name" -o tsv 2>/dev/null | head -1 || echo "")
REDIS_NAME=$(az redis list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")

# Get endpoints
COSMOS_ENDPOINT=$(az cosmosdb show -n "$COSMOS_NAME" -g "$RESOURCE_GROUP" --query documentEndpoint -o tsv 2>/dev/null || echo "N/A")
SEARCH_ENDPOINT="https://${SEARCH_NAME}.search.windows.net"
OPENAI_ENDPOINT=$(az cognitiveservices account show -n "$OPENAI_NAME" -g "$RESOURCE_GROUP" --query properties.endpoint -o tsv 2>/dev/null || echo "N/A")
DOCINTEL_ENDPOINT=$(az cognitiveservices account show -n "$DOCINTEL_NAME" -g "$RESOURCE_GROUP" --query properties.endpoint -o tsv 2>/dev/null || echo "N/A")

# Get keys
COSMOS_KEY=$(az cosmosdb keys list -n "$COSMOS_NAME" -g "$RESOURCE_GROUP" --query primaryMasterKey -o tsv 2>/dev/null || echo "")
SEARCH_KEY=$(az search admin-key show --service-name "$SEARCH_NAME" -g "$RESOURCE_GROUP" --query primaryKey -o tsv 2>/dev/null || echo "")
OPENAI_KEY=$(az cognitiveservices account keys list -n "$OPENAI_NAME" -g "$RESOURCE_GROUP" --query key1 -o tsv 2>/dev/null || echo "")
DOCINTEL_KEY=$(az cognitiveservices account keys list -n "$DOCINTEL_NAME" -g "$RESOURCE_GROUP" --query key1 -o tsv 2>/dev/null || echo "")
STORAGE_CONN=$(az storage account show-connection-string -n "$STORAGE_NAME" -g "$RESOURCE_GROUP" --query connectionString -o tsv 2>/dev/null || echo "")
STORAGE_ENDPOINT=$(az storage account show -n "$STORAGE_NAME" -g "$RESOURCE_GROUP" --query primaryEndpoints.blob -o tsv 2>/dev/null || echo "")
REDIS_KEY=$(az redis list-keys -n "$REDIS_NAME" -g "$RESOURCE_GROUP" --query primaryKey -o tsv 2>/dev/null || echo "")
REDIS_HOST=$(az redis show -n "$REDIS_NAME" -g "$RESOURCE_GROUP" --query hostName -o tsv 2>/dev/null || echo "")

REDIS_URL=""
if [[ -n "${REDIS_KEY}" && -n "${REDIS_HOST}" ]]; then
    REDIS_URL="rediss://:${REDIS_KEY}@${REDIS_HOST}:6380/0"
fi
if [[ -z "${REDIS_URL}" ]]; then
    REDIS_URL="redis://localhost:6379/0"
fi

# Deployment outputs
KEY_VAULT_URI=$(get_deployment_output "keyVaultUri")
CONTAINER_APP_URL=$(get_deployment_output "containerAppUrl")
APP_INSIGHTS_KEY=$(get_deployment_output "appInsightsKey")
MANAGED_IDENTITY_ID=$(get_deployment_output "managedIdentityClientId")

if [[ -z "${CONTAINER_APP_URL}" ]]; then
    CONTAINER_APP_URL="https://$(get_deployment_output "backendUrl")"
fi

if [[ ! -f "${CREATE_INDEX_SCRIPT}" ]]; then
    log_error "Search index provisioning script not found: ${CREATE_INDEX_SCRIPT}"
    exit 1
fi

log_info "Ensuring Azure AI Search indexes exist..."
chmod +x "${CREATE_INDEX_SCRIPT}"
set +e
INDEX_SCRIPT_OUTPUT=$("${CREATE_INDEX_SCRIPT}" "${RESOURCE_GROUP}" "${SEARCH_NAME}" 2>&1)
INDEX_SCRIPT_STATUS=$?
set -e

if [[ ${INDEX_SCRIPT_STATUS} -ne 0 ]]; then
    if [[ "${ENVIRONMENT}" == "prod" && ${INDEX_SCRIPT_STATUS} -eq 42 ]]; then
        log_warn "Search index bootstrap could not run from this client due to private-network restrictions."
        echo "${INDEX_SCRIPT_OUTPUT}"
        log_warn "Infrastructure deployment is successful. Index bootstrap is still pending."
        log_warn "Run index bootstrap from a VNet-connected runner, or temporarily enable Search public access, create indexes, then disable it."
    else
        echo "${INDEX_SCRIPT_OUTPUT}"
        log_error "Search index bootstrap failed."
        exit 1
    fi
fi

if [[ "${ENVIRONMENT}" == "prod" ]]; then
    log_info "Validating private endpoint/network settings for production..."
    if ! validate_private_networking; then
        log_error "Production private networking validation failed."
        exit 1
    fi
    log_success "Production private networking validation passed."
fi

if [[ "${CDSS_PIN_LATEST_READY_TRAFFIC}" == "true" ]]; then
    APP_NAME_FOR_TRAFFIC="$(az containerapp list -g "${RESOURCE_GROUP}" --query "[?contains(name,'-api')].name | [0]" -o tsv 2>/dev/null || true)"
    if [[ -n "${APP_NAME_FOR_TRAFFIC}" ]]; then
        if [[ -x "${PIN_TRAFFIC_SCRIPT}" ]]; then
            log_info "Ensuring backend traffic is pinned to latest ready revision..."
            if ! "${PIN_TRAFFIC_SCRIPT}" "${RESOURCE_GROUP}" "${APP_NAME_FOR_TRAFFIC}"; then
                log_warn "Could not pin traffic to latest ready revision automatically."
                log_warn "Run manually: ${PIN_TRAFFIC_SCRIPT} ${RESOURCE_GROUP} ${APP_NAME_FOR_TRAFFIC}"
            fi
        else
            log_warn "Traffic pin script not found/executable: ${PIN_TRAFFIC_SCRIPT}"
        fi
    else
        log_warn "Could not resolve backend Container App name for traffic pinning."
    fi
else
    log_info "Skipping traffic pin to latest ready revision (CDSS_PIN_LATEST_READY_TRAFFIC=false)."
fi

echo ""
log_success "============================================"
log_success "  CDSS Deployment Summary"
log_success "============================================"
echo ""
echo "  Environment:          ${ENVIRONMENT}"
echo "  Resource Group:       ${RESOURCE_GROUP}"
echo "  Location:             ${LOCATION}"
echo "  Deployment Name:      ${DEPLOYMENT_NAME}"
echo ""
echo "  Cosmos DB Endpoint:   ${COSMOS_ENDPOINT}"
echo "  AI Search Endpoint:   ${SEARCH_ENDPOINT}"
echo "  OpenAI Endpoint:      ${OPENAI_ENDPOINT}"
echo "  Key Vault URI:        ${KEY_VAULT_URI}"
echo "  Container App URL:    ${CONTAINER_APP_URL}"
echo "  App Insights Key:     ${APP_INSIGHTS_KEY}"
echo "  Managed Identity ID:  ${MANAGED_IDENTITY_ID}"
echo ""
log_success "============================================"

# --- Write .env files for local development (Create .env.azure for seed-data.sh) ---
if [[ "$ENVIRONMENT" == "dev" ]]; then
    ENV_AZURE="${SCRIPT_DIR}/../../.env.azure"
    ENV_FILE="${SCRIPT_DIR}/../../.env"
    
    log_info "Writing .env.azure for seed-data.sh..."
    cat > "$ENV_AZURE" <<EOF
ENVIRONMENT=${ENVIRONMENT}
CDSS_AZURE_COSMOS_ENDPOINT=${COSMOS_ENDPOINT}
CDSS_AZURE_COSMOS_DATABASE_NAME=cdss-db
CDSS_AZURE_COSMOS_KEY=${COSMOS_KEY}
CDSS_AZURE_COSMOS_USE_ENTRA_ID=false
CDSS_AZURE_SEARCH_ENDPOINT=${SEARCH_ENDPOINT}
CDSS_AZURE_OPENAI_ENDPOINT=${OPENAI_ENDPOINT}
CDSS_AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
CDSS_AZURE_OPENAI_MINI_DEPLOYMENT_NAME=gpt-4o-mini
CDSS_AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
CDSS_AZURE_BLOB_ENDPOINT=${STORAGE_ENDPOINT}
CDSS_AZURE_BLOB_CONNECTION_STRING=${STORAGE_CONN}
CDSS_AZURE_BLOB_USE_ENTRA_ID=false
EOF
    log_success "Created ${ENV_AZURE}"
    
# Create .env (for Python app)
    log_info "Writing .env with full credentials for Python app..."
    cat > "$ENV_FILE" <<'ENVEOF'
    
# ═══════════════════════════════════════════════════════════════════════════════
# CDSS Agentic RAG - Environment Configuration (Auto-generated)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Azure OpenAI ──────────────────────────────────────────────────────────────
ENVEOF
    cat >> "$ENV_FILE" <<EOF
CDSS_AZURE_OPENAI_ENDPOINT=${OPENAI_ENDPOINT}
CDSS_AZURE_OPENAI_API_KEY=${OPENAI_KEY}
CDSS_AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
CDSS_AZURE_OPENAI_MINI_DEPLOYMENT_NAME=gpt-4o-mini
CDSS_AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
CDSS_AZURE_OPENAI_API_VERSION=2024-12-01-preview

# ── Azure AI Search ───────────────────────────────────────────────────────────
CDSS_AZURE_SEARCH_ENDPOINT=${SEARCH_ENDPOINT}
CDSS_AZURE_SEARCH_API_KEY=${SEARCH_KEY}
CDSS_AZURE_SEARCH_PATIENT_RECORDS_INDEX=patient-records
CDSS_AZURE_SEARCH_TREATMENT_PROTOCOLS_INDEX=treatment-protocols
CDSS_AZURE_SEARCH_MEDICAL_LITERATURE_INDEX=medical-literature-cache
CDSS_AZURE_SEARCH_PATIENT_RECORDS_SEMANTIC_CONFIG=patient-records-semantic
CDSS_AZURE_SEARCH_TREATMENT_PROTOCOLS_SEMANTIC_CONFIG=protocols-semantic
CDSS_AZURE_SEARCH_MEDICAL_LITERATURE_SEMANTIC_CONFIG=literature-semantic

# ── Azure Cosmos DB ───────────────────────────────────────────────────────────
CDSS_AZURE_COSMOS_ENDPOINT=${COSMOS_ENDPOINT}
CDSS_AZURE_COSMOS_KEY=${COSMOS_KEY}
CDSS_AZURE_COSMOS_USE_ENTRA_ID=false
CDSS_AZURE_COSMOS_DATABASE_NAME=cdss-db
CDSS_AZURE_COSMOS_PATIENT_PROFILES_CONTAINER=patient-profiles
CDSS_AZURE_COSMOS_CONVERSATION_HISTORY_CONTAINER=conversation-history
CDSS_AZURE_COSMOS_EMBEDDING_CACHE_CONTAINER=embedding-cache
CDSS_AZURE_COSMOS_AUDIT_LOG_CONTAINER=audit-log
CDSS_AZURE_COSMOS_AGENT_STATE_CONTAINER=agent-state

# ── Azure Document Intelligence ──────────────────────────────────────────────
CDSS_AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=${DOCINTEL_ENDPOINT}
CDSS_AZURE_DOCUMENT_INTELLIGENCE_KEY=${DOCINTEL_KEY}

# ── Azure Blob Storage ───────────────────────────────────────────────────────
CDSS_AZURE_BLOB_CONNECTION_STRING=${STORAGE_CONN}
CDSS_AZURE_BLOB_ENDPOINT=${STORAGE_ENDPOINT}
CDSS_AZURE_BLOB_USE_ENTRA_ID=false
CDSS_AZURE_BLOB_PROTOCOLS_CONTAINER=treatment-protocols
CDSS_AZURE_KEY_VAULT_URL=${KEY_VAULT_URI}

# ── PubMed / NCBI Entrez ─────────────────────────────────────────────────────
CDSS_PUBMED_API_KEY=
CDSS_PUBMED_EMAIL=
CDSS_PUBMED_BASE_URL=https://eutils.ncbi.nlm.nih.gov/entrez/eutils/

# ── OpenFDA ──────────────────────────────────────────────────────────────────
CDSS_OPENFDA_BASE_URL=https://api.fda.gov

# ── RxNorm ───────────────────────────────────────────────────────────────────
CDSS_RXNORM_BASE_URL=https://rxnav.nlm.nih.gov/REST

# ── DrugBank ─────────────────────────────────────────────────────────────────
CDSS_DRUGBANK_API_KEY=
CDSS_DRUGBANK_BASE_URL=https://api.drugbank.com/v1

# ── Redis ────────────────────────────────────────────────────────────────────
CDSS_REDIS_URL=${REDIS_URL}

# ── Application Settings ─────────────────────────────────────────────────────
CDSS_DEBUG=false
CDSS_LOG_LEVEL=INFO
CDSS_CORS_ORIGINS=["http://localhost:3000","http://localhost:3001"]
CDSS_CORS_ALLOW_METHODS=["GET","POST","PUT","PATCH","DELETE","OPTIONS"]
CDSS_CORS_ALLOW_HEADERS=["Authorization","Content-Type","X-Request-ID"]
CDSS_CORS_EXPOSE_HEADERS=["X-Request-ID","X-Trace-ID"]
CDSS_CORS_ALLOW_CREDENTIALS=true
CDSS_AUTH_ENABLED=false
CDSS_AUTH_TENANT_ID=${TENANT_ID}
CDSS_AUTH_AUDIENCE=
CDSS_AUTH_REQUIRED_SCOPES=[]
CDSS_MAX_CONCURRENT_AGENTS=10
CDSS_RESPONSE_TIMEOUT_SECONDS=30
CDSS_CONFIDENCE_THRESHOLD=0.6
EOF
    log_success "Created ${ENV_FILE}"
    log_warn "NOTE: Add your PubMed API key to CDSS_PUBMED_API_KEY in .env"
fi

log_success "Deployment complete! Your CDSS infrastructure is ready."
