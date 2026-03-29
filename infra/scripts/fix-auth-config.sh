#!/bin/bash
# Fix authentication configuration for CDSS production deployment.
#
# This script diagnoses and fixes the 401 "Invalid or expired bearer token" error
# by ensuring the backend's CDSS_AUTH_AUDIENCE matches the token's audience claim.
#
# Usage:
#   ./infra/scripts/fix-auth-config.sh --resource-group <rg> [--dry-run]
#
# Prerequisites:
#   - Azure CLI installed and logged in
#   - Contributor access to the resource group

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIN_TRAFFIC_SCRIPT="${SCRIPT_DIR}/pin-containerapp-latest-ready.sh"
DRY_RUN="false"
RESOURCE_GROUP=""
CONTAINER_APP_NAME=""

# Expected auth metadata (resolved dynamically from Entra app registration when possible)
DEFAULT_API_APP_DISPLAY_NAME="cdss-api"
DEFAULT_API_IDENTIFIER_URI="api://cdss-api"
EXPECTED_SCOPE_NAME="access_as_user"
EXPECTED_API_RESOURCE_URI="${DEFAULT_API_IDENTIFIER_URI}"
EXPECTED_API_SCOPE=""
EXPECTED_AUTH_AUDIENCE=""

log_info() { echo "[INFO] $1"; }
log_warn() { echo "[WARN] $1"; }
log_error() { echo "[ERROR] $1"; }
log_success() { echo "[SUCCESS] $1"; }
log_diff() { echo "  $1"; }

find_api_app_by_identifier_uri() {
    local identifier_uri="$1"

    az rest \
        --method GET \
        --uri "https://graph.microsoft.com/v1.0/applications?\$filter=identifierUris/any(x:x eq '${identifier_uri}')&\$select=id,appId,displayName" \
        --query "value[0].appId" \
        -o tsv 2>/dev/null || true
}

resolve_expected_auth_values() {
    local resolved_app_id=""
    local resolved_identifier_uri=""

    resolved_app_id="$(find_api_app_by_identifier_uri "${DEFAULT_API_IDENTIFIER_URI}")"
    if [[ -z "${resolved_app_id}" || "${resolved_app_id}" == "None" ]]; then
        resolved_app_id="$(az ad app list \
            --display-name "${DEFAULT_API_APP_DISPLAY_NAME}" \
            --query "[0].appId" \
            -o tsv 2>/dev/null || true)"
    fi

    if [[ -n "${resolved_app_id}" && "${resolved_app_id}" != "None" ]]; then
        resolved_identifier_uri="$(az ad app show \
            --id "${resolved_app_id}" \
            --query "identifierUris[0]" \
            -o tsv 2>/dev/null || true)"
        if [[ -n "${resolved_identifier_uri}" && "${resolved_identifier_uri}" != "None" ]]; then
            EXPECTED_API_RESOURCE_URI="${resolved_identifier_uri}"
        fi
        EXPECTED_AUTH_AUDIENCE="${resolved_app_id}"
    else
        EXPECTED_AUTH_AUDIENCE="${DEFAULT_API_IDENTIFIER_URI}"
    fi

    EXPECTED_API_SCOPE="${EXPECTED_API_RESOURCE_URI}/${EXPECTED_SCOPE_NAME}"
}

usage() {
    cat <<EOF
Usage:
  ${SCRIPT_NAME} [options]

Options:
  --resource-group <rg>       Resource group containing the CDSS Container App (required)
  --container-app-name <name> Container App name (auto-detected if not provided)
  --dry-run                   Show what would be changed without making changes
  -h, --help                  Show this help

Examples:
  ${SCRIPT_NAME} --resource-group cdss-prod-rg
  ${SCRIPT_NAME} --resource-group cdss-prod-rg --dry-run
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --resource-group)
            RESOURCE_GROUP="$2"
            shift 2
            ;;
        --container-app-name)
            CONTAINER_APP_NAME="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown argument: $1"
            usage
            exit 1
            ;;
    esac
done

if [[ -z "${RESOURCE_GROUP}" ]]; then
    log_error "Resource group is required. Use --resource-group <rg>"
    usage
    exit 1
fi

# Auto-detect container app name
if [[ -z "${CONTAINER_APP_NAME}" ]]; then
    CONTAINER_APP_NAME="$(az containerapp list \
        --resource-group "${RESOURCE_GROUP}" \
        --query "[?contains(name, '-api')].name | [0]" \
        -o tsv 2>/dev/null || true)"
    if [[ -z "${CONTAINER_APP_NAME}" ]]; then
        CONTAINER_APP_NAME="$(az containerapp list \
            --resource-group "${RESOURCE_GROUP}" \
            --query "[0].name" \
            -o tsv 2>/dev/null || true)"
    fi
fi

if [[ -z "${CONTAINER_APP_NAME}" ]]; then
    log_error "Could not find Container App in resource group ${RESOURCE_GROUP}"
    exit 1
fi

resolve_expected_auth_values

log_info "Resource Group: ${RESOURCE_GROUP}"
log_info "Container App: ${CONTAINER_APP_NAME}"
log_info "Expected API Scope: ${EXPECTED_API_SCOPE}"
log_info "Expected Auth Audience: ${EXPECTED_AUTH_AUDIENCE}"
echo ""

# Function to get environment variable value from container app
get_env_value() {
    local app="$1"
    local env_name="$2"
    az containerapp show \
        --resource-group "${RESOURCE_GROUP}" \
        --name "${app}" \
        --query "properties.template.containers[0].env[?name=='${env_name}'].value | [0]" \
        -o tsv 2>/dev/null || true
}

# Function to get CORS configuration
get_cors_origins() {
    local app="$1"
    az containerapp show \
        --resource-group "${RESOURCE_GROUP}" \
        --name "${app}" \
        --query "properties.configuration.ingress.corsPolicy.allowedOrigins" \
        -o tsv 2>/dev/null || true
}

# ============================================================
# DIAGNOSIS PHASE
# ============================================================

log_info "=== DIAGNOSING AUTHENTICATION CONFIGURATION ==="
echo ""

# Get current values
CURRENT_AUTH_ENABLED="$(get_env_value "${CONTAINER_APP_NAME}" "CDSS_AUTH_ENABLED")"
CURRENT_AUTH_TENANT_ID="$(get_env_value "${CONTAINER_APP_NAME}" "CDSS_AUTH_TENANT_ID")"
CURRENT_AUTH_AUDIENCE="$(get_env_value "${CONTAINER_APP_NAME}" "CDSS_AUTH_AUDIENCE")"
CURRENT_AUTH_SCOPES="$(get_env_value "${CONTAINER_APP_NAME}" "CDSS_AUTH_REQUIRED_SCOPES")"
CURRENT_CORS_ORIGINS="$(get_cors_origins "${CONTAINER_APP_NAME}")"
CURRENT_API_FQDN="$(az containerapp show \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${CONTAINER_APP_NAME}" \
    --query "properties.configuration.ingress.fqdn" \
    -o tsv 2>/dev/null || true)"

# If Graph lookup is restricted and backend already has a non-empty audience,
# prefer preserving the current value over forcing a potentially wrong fallback.
if [[ "${EXPECTED_AUTH_AUDIENCE}" == "${DEFAULT_API_IDENTIFIER_URI}" && -n "${CURRENT_AUTH_AUDIENCE}" && "${CURRENT_AUTH_AUDIENCE}" != "None" ]]; then
    log_warn "Could not resolve API app ID from Graph; using current CDSS_AUTH_AUDIENCE as expected value: ${CURRENT_AUTH_AUDIENCE}"
    EXPECTED_AUTH_AUDIENCE="${CURRENT_AUTH_AUDIENCE}"
fi

# Get subscription tenant ID
SUBSCRIPTION_TENANT_ID="$(az account show --query tenantId -o tsv 2>/dev/null || true)"

echo "Current Configuration:"
echo "  CDSS_AUTH_ENABLED:       ${CURRENT_AUTH_ENABLED:-<not set>}"
echo "  CDSS_AUTH_TENANT_ID:     ${CURRENT_AUTH_TENANT_ID:-<not set>}"
echo "  CDSS_AUTH_AUDIENCE:      ${CURRENT_AUTH_AUDIENCE:-<not set>}"
echo "  CDSS_AUTH_REQUIRED_SCOPES: ${CURRENT_AUTH_SCOPES:-<not set>}"
echo "  CORS Origins:            ${CURRENT_CORS_ORIGINS:-<not set>}"
echo "  API FQDN:                ${CURRENT_API_FQDN:-<not set>}"
echo "  Subscription Tenant:     ${SUBSCRIPTION_TENANT_ID:-<not set>}"
echo ""

# Identify issues
ISSUES=()
FIXES=()

# Check 1: Auth Enabled
if [[ "${CURRENT_AUTH_ENABLED}" != "true" ]]; then
    ISSUES+=("CDSS_AUTH_ENABLED is not 'true'")
    FIXES+=("CDSS_AUTH_ENABLED=true")
fi

# Check 2: Auth Tenant ID
if [[ -z "${CURRENT_AUTH_TENANT_ID}" || "${CURRENT_AUTH_TENANT_ID}" == "None" ]]; then
    ISSUES+=("CDSS_AUTH_TENANT_ID is not set")
    FIXES+=("CDSS_AUTH_TENANT_ID=${SUBSCRIPTION_TENANT_ID}")
fi

# Check 3: Auth Audience (CRITICAL)
if [[ -z "${CURRENT_AUTH_AUDIENCE}" || "${CURRENT_AUTH_AUDIENCE}" == "None" || "${CURRENT_AUTH_AUDIENCE}" != "${EXPECTED_AUTH_AUDIENCE}" ]]; then
    ISSUES+=("CDSS_AUTH_AUDIENCE mismatch: expected '${EXPECTED_AUTH_AUDIENCE}', got '${CURRENT_AUTH_AUDIENCE:-<empty>}'")
    FIXES+=("CDSS_AUTH_AUDIENCE=${EXPECTED_AUTH_AUDIENCE}")
fi

# Check 4: Auth Scopes
EXPECTED_SCOPES='["access_as_user"]'
if [[ -z "${CURRENT_AUTH_SCOPES}" || "${CURRENT_AUTH_SCOPES}" == "None" || "${CURRENT_AUTH_SCOPES}" == "[]" ]]; then
    ISSUES+=("CDSS_AUTH_REQUIRED_SCOPES is empty")
    FIXES+=("CDSS_AUTH_REQUIRED_SCOPES=${EXPECTED_SCOPES}")
fi

# Check 5: CORS Origins (get from Static Web Apps)
SWA_HOST="$(az staticwebapp list \
    --resource-group "${RESOURCE_GROUP}" \
    --query "[0].defaultHostname" \
    -o tsv 2>/dev/null || true)"

if [[ -n "${SWA_HOST}" ]]; then
    EXPECTED_CORS="https://${SWA_HOST}"
    if [[ -z "${CURRENT_CORS_ORIGINS}" ]] || ! echo "${CURRENT_CORS_ORIGINS}" | grep -q "${SWA_HOST}"; then
        ISSUES+=("CORS missing frontend origin: ${EXPECTED_CORS}")
        FIXES+=("Add CORS origin: ${EXPECTED_CORS}")
    fi
fi

# Report findings
if [[ ${#ISSUES[@]} -eq 0 ]]; then
    log_success "All authentication settings are correctly configured!"
    echo ""
    log_info "If you're still experiencing 401 errors, check:"
    echo "  1. Frontend VITE_API_SCOPE matches: ${EXPECTED_API_SCOPE}"
    echo "  2. API App Registration has identifierUris: ${EXPECTED_API_RESOURCE_URI}"
    echo "  3. API App Registration has scope: ${EXPECTED_SCOPE_NAME}"
    echo "  4. SPA App Registration has delegated permission to API scope"
    exit 0
fi

log_warn "Found ${#ISSUES[@]} configuration issue(s):"
for issue in "${ISSUES[@]}"; do
    log_diff "✗ ${issue}"
done
echo ""

# ============================================================
# FIX PHASE
# ============================================================

if [[ "${DRY_RUN}" == "true" ]]; then
    log_info "=== DRY RUN - WOULD APPLY FIXES ==="
    for fix in "${FIXES[@]}"; do
        log_diff "Would set: ${fix}"
    done
    echo ""
    log_info "To apply fixes, run without --dry-run"
    exit 0
fi

log_info "=== APPLYING FIXES ==="

# Build the environment variables to update
ENV_VARS=()

if [[ "${CURRENT_AUTH_ENABLED}" != "true" ]]; then
    ENV_VARS+=("CDSS_AUTH_ENABLED=true")
fi

if [[ -z "${CURRENT_AUTH_TENANT_ID}" || "${CURRENT_AUTH_TENANT_ID}" == "None" ]]; then
    ENV_VARS+=("CDSS_AUTH_TENANT_ID=${SUBSCRIPTION_TENANT_ID}")
fi

if [[ -z "${CURRENT_AUTH_AUDIENCE}" || "${CURRENT_AUTH_AUDIENCE}" == "None" || "${CURRENT_AUTH_AUDIENCE}" != "${EXPECTED_AUTH_AUDIENCE}" ]]; then
    ENV_VARS+=("CDSS_AUTH_AUDIENCE=${EXPECTED_AUTH_AUDIENCE}")
fi

if [[ -z "${CURRENT_AUTH_SCOPES}" || "${CURRENT_AUTH_SCOPES}" == "None" || "${CURRENT_AUTH_SCOPES}" == "[]" ]]; then
    ENV_VARS+=("CDSS_AUTH_REQUIRED_SCOPES=[\"${EXPECTED_SCOPE_NAME}\"]")
fi

# Apply environment variable fixes
if [[ ${#ENV_VARS[@]} -gt 0 ]]; then
    log_info "Updating container app environment variables..."
    ENV_ARGS=""
    for var in "${ENV_VARS[@]}"; do
        ENV_ARGS="${ENV_ARGS} --set-env-vars ${var}"
        log_diff "Setting: ${var}"
    done

    if az containerapp update \
        --resource-group "${RESOURCE_GROUP}" \
        --name "${CONTAINER_APP_NAME}" \
        ${ENV_ARGS} \
        --only-show-errors \
        --output none; then
        log_success "Environment variables updated"
        if [[ -x "${PIN_TRAFFIC_SCRIPT}" ]]; then
            if ! "${PIN_TRAFFIC_SCRIPT}" "${RESOURCE_GROUP}" "${CONTAINER_APP_NAME}"; then
                log_warn "Auth settings updated, but failed to pin traffic to latest ready revision."
                log_warn "Run manually: ${PIN_TRAFFIC_SCRIPT} ${RESOURCE_GROUP} ${CONTAINER_APP_NAME}"
            fi
        else
            log_warn "Traffic pin script not found/executable: ${PIN_TRAFFIC_SCRIPT}"
        fi
    else
        log_error "Failed to update environment variables"
        exit 1
    fi
fi

# Update CORS if needed
if [[ -n "${SWA_HOST}" ]]; then
    EXPECTED_CORS="https://${SWA_HOST}"
    if [[ -z "${CURRENT_CORS_ORIGINS}" ]] || ! echo "${CURRENT_CORS_ORIGINS}" | grep -q "${SWA_HOST}"; then
        log_info "Updating CORS configuration to include frontend origin..."
        # Get existing origins and add new one
        EXISTING_ORIGINS="${CURRENT_CORS_ORIGINS}"
        NEW_ORIGINS="${EXPECTED_CORS}"
        if [[ -n "${EXISTING_ORIGINS}" && "${EXISTING_ORIGINS}" != "None" ]]; then
            # Parse existing origins and add new one
            NEW_ORIGINS="${EXISTING_ORIGINS} ${EXPECTED_CORS}"
        fi

        if az containerapp ingress cors update \
            --resource-group "${RESOURCE_GROUP}" \
            --name "${CONTAINER_APP_NAME}" \
            --allowed-origins ${NEW_ORIGINS} \
            --only-show-errors \
            --output none; then
            log_success "CORS updated to include: ${EXPECTED_CORS}"
        else
            log_warn "Could not update CORS. Manual update required."
        fi
    fi
fi

echo ""
log_success "=== FIX COMPLETE ==="
echo ""
log_info "Verification steps:"
echo "  1. Wait 1-2 minutes for container app revision to deploy"
echo "  2. Test health endpoint: curl https://${CURRENT_API_FQDN}/api/v1/health"
echo "  3. Test authenticated endpoint with token from:"
echo "     export TOKEN=\$(az account get-access-token --scope '${EXPECTED_API_SCOPE}' --query accessToken -o tsv)"
echo "     curl -H 'Authorization: Bearer \$TOKEN' https://${CURRENT_API_FQDN}/api/v1/patients?limit=1"
