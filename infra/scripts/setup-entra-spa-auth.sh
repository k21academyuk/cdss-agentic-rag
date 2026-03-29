#!/bin/bash
# Configure Entra app registrations for CDSS frontend <-> API auth.
#
# What this script does:
# 1) Ensures SPA redirect URIs include localhost dev ports (3000/3001).
# 2) Resolves or creates API app registration.
# 3) Ensures API identifier URI and delegated scope exist.
# 4) Grants SPA delegated permission to API scope.
# 5) Optionally runs admin consent.
#
# Usage:
#   ./infra/scripts/setup-entra-spa-auth.sh
#
# Optional:
#   --spa-app-id <spa-client-id>
#   --spa-app-display-name <name>          (default: cdss-frontend-spa)
#   --api-app-id <api-client-id>
#   --api-app-display-name <name>          (default: cdss-api)
#   --api-app-id-uri <uri>                 (default: api://cdss-api)
#   --scope-name <scope>                   (default: access_as_user)
#   --resource-group <rg>
#   --container-app-name <name>
#   --api-fqdn <fqdn>
#   --frontend-env-file <path>             (default: frontend/.env.local)
#   --skip-frontend-env
#   --skip-admin-consent
#
# Example:
#   ./infra/scripts/setup-entra-spa-auth.sh --resource-group cdss-prod-rg

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PIN_TRAFFIC_SCRIPT="${SCRIPT_DIR}/pin-containerapp-latest-ready.sh"

SPA_APP_ID=""
SPA_APP_DISPLAY_NAME="cdss-frontend-spa"
API_APP_ID=""
API_APP_DISPLAY_NAME="cdss-api"
API_APP_ID_URI="api://cdss-api"
API_APP_ID_URI_EXPLICIT="false"
SCOPE_NAME="access_as_user"
RESOURCE_GROUP=""
CONTAINER_APP_NAME=""
API_FQDN=""
FRONTEND_ENV_FILE="${REPO_ROOT}/frontend/.env.local"
SKIP_FRONTEND_ENV="false"
SKIP_ADMIN_CONSENT="false"

log_info() { echo "[INFO] $1"; }
log_warn() { echo "[WARN] $1"; }
log_error() { echo "[ERROR] $1"; }
log_success() { echo "[SUCCESS] $1"; }

get_permission_mapping_count() {
    local spa_app_id="$1"
    local api_app_id="$2"
    local scope_id="$3"

    python - "${spa_app_id}" "${api_app_id}" "${scope_id}" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys

spa_app_id = sys.argv[1]
api_app_id = sys.argv[2]
scope_id = sys.argv[3].lower()

try:
    app_json = subprocess.check_output(
        ["az", "ad", "app", "show", "--id", spa_app_id, "-o", "json"],
        text=True,
    )
    app = json.loads(app_json)
except Exception:
    print("0")
    raise SystemExit(0)

count = 0
for resource_access_block in app.get("requiredResourceAccess", []) or []:
    if resource_access_block.get("resourceAppId") != api_app_id:
        continue
    for resource_access in resource_access_block.get("resourceAccess", []) or []:
        if str(resource_access.get("id", "")).lower() == scope_id and resource_access.get("type") == "Scope":
            count += 1

print(str(count))
PY
}

resolve_container_app_name() {
    local rg="$1"
    local app_name="$2"

    if [[ -n "${app_name}" || -z "${rg}" ]]; then
        echo "${app_name}"
        return 0
    fi

    az containerapp list \
        --resource-group "${rg}" \
        --query "[?contains(name,'-api')].name | [0]" \
        -o tsv 2>/dev/null || true
}

get_container_app_env_value() {
    local rg="$1"
    local app="$2"
    local env_name="$3"

    if [[ -z "${rg}" || -z "${app}" || -z "${env_name}" ]]; then
        return 0
    fi

    az containerapp show \
        --resource-group "${rg}" \
        --name "${app}" \
        --query "properties.template.containers[0].env[?name=='${env_name}'].value | [0]" \
        -o tsv 2>/dev/null || true
}

find_api_app_by_identifier_uri() {
    local identifier_uri="$1"

    local app_id=""
    app_id="$(az rest \
        --method GET \
        --uri "https://graph.microsoft.com/v1.0/applications?\$filter=identifierUris/any(x:x eq '${identifier_uri}')&\$select=id,appId,displayName" \
        --query "value[0].appId" \
        -o tsv 2>/dev/null || true)"

    if [[ -n "${app_id}" ]]; then
        echo "${app_id}"
        return 0
    fi

    # Fallback when application discovery is restricted but service principal is visible.
    az rest \
        --method GET \
        --uri "https://graph.microsoft.com/v1.0/servicePrincipals?\$filter=servicePrincipalNames/any(x:x eq '${identifier_uri}')&\$select=id,appId,displayName" \
        --query "value[0].appId" \
        -o tsv 2>/dev/null || true
}

sync_backend_auth_audience() {
    local rg="$1"
    local app="$2"
    local audience="$3"

    if [[ -z "${rg}" || -z "${app}" || -z "${audience}" ]]; then
        return 0
    fi

    local current_audience=""
    current_audience="$(az containerapp show \
        --resource-group "${rg}" \
        --name "${app}" \
        --query "properties.template.containers[0].env[?name=='CDSS_AUTH_AUDIENCE'].value | [0]" \
        -o tsv 2>/dev/null || true)"

    if [[ "${current_audience}" == "${audience}" ]]; then
        log_info "Backend CDSS_AUTH_AUDIENCE already matches ${audience}"
        return 0
    fi

    log_warn "Updating backend CDSS_AUTH_AUDIENCE from '${current_audience:-<empty>}' to '${audience}'..."
    if az containerapp update \
        --resource-group "${rg}" \
        --name "${app}" \
        --set-env-vars "CDSS_AUTH_AUDIENCE=${audience}" \
        --only-show-errors \
        --output none; then
        log_success "Backend auth audience updated."
        if [[ -x "${PIN_TRAFFIC_SCRIPT}" ]]; then
            if ! "${PIN_TRAFFIC_SCRIPT}" "${rg}" "${app}"; then
                log_warn "Audience updated, but failed to pin traffic to latest ready revision."
                log_warn "Run manually: ${PIN_TRAFFIC_SCRIPT} ${rg} ${app}"
            fi
        else
            log_warn "Traffic pin script not found/executable: ${PIN_TRAFFIC_SCRIPT}"
        fi
    else
        log_warn "Could not update backend auth audience automatically. Update CDSS_AUTH_AUDIENCE manually."
    fi
}

usage() {
    cat <<EOF
Usage:
  ${SCRIPT_NAME} [options]

Options:
  --spa-app-id <id>            SPA app registration Application (client) ID (optional)
  --spa-app-display-name <n>   SPA app display name (default: cdss-frontend-spa)
  --api-app-id <id>            API app registration Application (client) ID (optional)
  --api-app-display-name <n>   API app display name if app must be resolved/created (default: cdss-api)
  --api-app-id-uri <uri>       API identifier URI / audience (default: api://cdss-api)
  --scope-name <scope>         Delegated scope value (default: access_as_user)
  --resource-group <rg>        Resource group used to auto-resolve Container App FQDN
  --container-app-name <name>  Container App name (if omitted, auto-detected from resource group)
  --api-fqdn <fqdn>            Explicit API FQDN (skip auto-discovery from Container App)
  --frontend-env-file <path>   Output .env.local file path (default: frontend/.env.local)
  --skip-frontend-env          Skip writing frontend/.env.local
  --skip-admin-consent         Skip az ad app permission admin-consent
  -h, --help                   Show this help
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --spa-app-id)
            SPA_APP_ID="${2:-}"
            shift 2
            ;;
        --spa-app-display-name)
            SPA_APP_DISPLAY_NAME="${2:-}"
            shift 2
            ;;
        --api-app-id)
            API_APP_ID="${2:-}"
            shift 2
            ;;
        --api-app-display-name)
            API_APP_DISPLAY_NAME="${2:-}"
            shift 2
            ;;
        --api-app-id-uri)
            API_APP_ID_URI="${2:-}"
            API_APP_ID_URI_EXPLICIT="true"
            shift 2
            ;;
        --scope-name)
            SCOPE_NAME="${2:-}"
            shift 2
            ;;
        --resource-group|--rg)
            RESOURCE_GROUP="${2:-}"
            shift 2
            ;;
        --container-app-name|--app)
            CONTAINER_APP_NAME="${2:-}"
            shift 2
            ;;
        --api-fqdn)
            API_FQDN="${2:-}"
            shift 2
            ;;
        --frontend-env-file)
            FRONTEND_ENV_FILE="${2:-}"
            shift 2
            ;;
        --skip-frontend-env)
            SKIP_FRONTEND_ENV="true"
            shift
            ;;
        --skip-admin-consent)
            SKIP_ADMIN_CONSENT="true"
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

if ! command -v az >/dev/null 2>&1; then
    log_error "Azure CLI (az) is required."
    exit 1
fi

if ! command -v python >/dev/null 2>&1; then
    log_error "python is required."
    exit 1
fi

if ! az account show >/dev/null 2>&1; then
    log_error "Not logged in to Azure CLI. Run: az login"
    exit 1
fi

TENANT_ID="$(az account show --query tenantId -o tsv)"
log_info "Tenant ID: ${TENANT_ID}"

if [[ "${API_APP_ID_URI_EXPLICIT}" != "true" ]]; then
    CONTAINER_APP_NAME="$(resolve_container_app_name "${RESOURCE_GROUP}" "${CONTAINER_APP_NAME}")"

    if [[ -n "${RESOURCE_GROUP}" && -n "${CONTAINER_APP_NAME}" ]]; then
        BACKEND_AUTH_AUDIENCE="$(get_container_app_env_value "${RESOURCE_GROUP}" "${CONTAINER_APP_NAME}" "CDSS_AUTH_AUDIENCE")"
        if [[ -n "${BACKEND_AUTH_AUDIENCE}" && "${BACKEND_AUTH_AUDIENCE}" != "None" ]]; then
            if [[ "${BACKEND_AUTH_AUDIENCE}" == api://* ]]; then
                API_APP_ID_URI="${BACKEND_AUTH_AUDIENCE}"
                log_info "Using backend CDSS_AUTH_AUDIENCE as API identifier URI default: ${API_APP_ID_URI}"
            else
                log_info "Backend CDSS_AUTH_AUDIENCE is not an identifier URI (${BACKEND_AUTH_AUDIENCE}); keeping default API URI: ${API_APP_ID_URI}"
            fi
        else
            log_info "Backend CDSS_AUTH_AUDIENCE is empty; using script default: ${API_APP_ID_URI}"
        fi
    fi
fi

# Resolve/create SPA app when not explicitly provided.
if [[ -z "${SPA_APP_ID}" ]]; then
    SPA_APP_ID="$(az ad app list --display-name "${SPA_APP_DISPLAY_NAME}" --query "[0].appId" -o tsv 2>/dev/null || true)"
fi

if [[ -z "${SPA_APP_ID}" ]]; then
    SPA_APP_ID="$(az ad app list --all \
        --query "[?spa && spa.redirectUris && (contains(join(',',spa.redirectUris), 'localhost:3000') || contains(join(',',spa.redirectUris), 'localhost:3001'))].appId | [0]" \
        -o tsv 2>/dev/null || true)"
fi

if [[ -z "${SPA_APP_ID}" ]]; then
    log_warn "SPA app not found. Creating new app registration: ${SPA_APP_DISPLAY_NAME}"
    SPA_APP_ID="$(az ad app create \
        --display-name "${SPA_APP_DISPLAY_NAME}" \
        --sign-in-audience AzureADMyOrg \
        --query appId \
        -o tsv)"
    log_success "Created SPA app: ${SPA_APP_ID}"
fi

# Resolve SPA object ID and ensure app exists.
SPA_OBJ_ID="$(az ad app show --id "${SPA_APP_ID}" --query id -o tsv 2>/dev/null || true)"
if [[ -z "${SPA_OBJ_ID}" ]]; then
    log_error "SPA app not found: ${SPA_APP_ID}"
    exit 1
fi
log_info "SPA app found: ${SPA_APP_ID}"

# Ensure SPA redirect URIs include localhost entries.
REDIRECT_BODY="$(python - "${SPA_APP_ID}" <<'PY'
import json
import subprocess
import sys

spa_app_id = sys.argv[1]
cmd = ["az", "ad", "app", "show", "--id", spa_app_id, "--query", "spa.redirectUris", "-o", "json"]
out = subprocess.check_output(cmd, text=True)
uris = json.loads(out or "[]") or []
needed = [
    "http://localhost:3000",
    "https://localhost:3000",
    "http://localhost:3001",
    "https://localhost:3001",
]
for u in needed:
    if u not in uris:
        uris.append(u)
print(json.dumps({"spa": {"redirectUris": uris}}, separators=(",", ":")))
PY
)"

log_info "Ensuring SPA redirect URIs include localhost dev ports..."
az rest \
    --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${SPA_OBJ_ID}" \
    --headers "Content-Type=application/json" \
    --body "${REDIRECT_BODY}" \
    --only-show-errors \
    --output none
log_success "SPA redirect URIs updated."

# Resolve API app by explicit ID, identifier URI, or display name; create if missing.
if [[ -z "${API_APP_ID}" ]]; then
    API_APP_ID="$(find_api_app_by_identifier_uri "${API_APP_ID_URI}")"
fi

if [[ -z "${API_APP_ID}" ]]; then
    API_APP_ID="$(az ad app list --display-name "${API_APP_DISPLAY_NAME}" \
        --query "[0].appId" \
        -o tsv 2>/dev/null || true)"
fi

API_APP_CREATED="false"
if [[ -z "${API_APP_ID}" ]]; then
    log_warn "API app not found. Creating new app registration: ${API_APP_DISPLAY_NAME}"
    API_APP_ID="$(az ad app create \
        --display-name "${API_APP_DISPLAY_NAME}" \
        --sign-in-audience AzureADMyOrg \
        --query appId \
        -o tsv)"
    API_APP_CREATED="true"
    log_success "Created API app: ${API_APP_ID}"
else
    log_info "Using API app: ${API_APP_ID}"
fi

API_OBJ_ID="$(az ad app show --id "${API_APP_ID}" --query id -o tsv)"

# Ensure identifier URI matches expected audience.
if ! az ad app update --id "${API_APP_ID}" --identifier-uris "${API_APP_ID_URI}" --only-show-errors >/dev/null 2>&1; then
    EXISTING_URI_APP_ID="$(find_api_app_by_identifier_uri "${API_APP_ID_URI}")"
    if [[ -n "${EXISTING_URI_APP_ID}" && "${EXISTING_URI_APP_ID}" != "${API_APP_ID}" ]]; then
        PREVIOUS_API_APP_ID="${API_APP_ID}"
        API_APP_ID="${EXISTING_URI_APP_ID}"
        API_OBJ_ID="$(az ad app show --id "${API_APP_ID}" --query id -o tsv)"
        log_warn "Identifier URI '${API_APP_ID_URI}' is already owned by app ${API_APP_ID}. Switched to existing app."
        if [[ "${API_APP_CREATED}" == "true" ]]; then
            log_warn "Newly created API app ${PREVIOUS_API_APP_ID} is unused. Delete it if not needed:"
            log_warn "  az ad app delete --id ${PREVIOUS_API_APP_ID}"
        fi
    else
        FALLBACK_API_APP_ID_URI="api://${API_APP_ID}"
        log_warn "Failed to set API identifier URI '${API_APP_ID_URI}'. Falling back to '${FALLBACK_API_APP_ID_URI}'."
        if az ad app update --id "${API_APP_ID}" --identifier-uris "${FALLBACK_API_APP_ID_URI}" --only-show-errors >/dev/null 2>&1; then
            API_APP_ID_URI="${FALLBACK_API_APP_ID_URI}"
            log_warn "Using fallback API audience: ${API_APP_ID_URI}"
        else
            log_error "Failed to set API identifier URI to both '${API_APP_ID_URI}' and fallback '${FALLBACK_API_APP_ID_URI}'."
            log_error "Pass --api-app-id for an existing API app you control, or resolve tenant app URI conflicts."
            exit 1
        fi
    fi
fi
log_success "API identifier URI ensured: ${API_APP_ID_URI}"

# Ensure delegated scope exists and is enabled.
SCOPE_SCRIPT_OUTPUT="$(python - "${API_APP_ID}" "${SCOPE_NAME}" <<'PY'
import json
import subprocess
import sys
import uuid

api_app_id = sys.argv[1]
scope_name = sys.argv[2]

api_json = subprocess.check_output(
    ["az", "ad", "app", "show", "--id", api_app_id, "--query", "api", "-o", "json"],
    text=True,
)
api = json.loads(api_json or "{}") or {}
scopes = api.get("oauth2PermissionScopes") or []

target = None
for s in scopes:
    if s.get("value") == scope_name:
        target = s
        break

if target is None:
    target = {
        "id": str(uuid.uuid4()),
        "value": scope_name,
        "type": "User",
        "isEnabled": True,
        "adminConsentDisplayName": "Access CDSS API",
        "adminConsentDescription": "Allow the application to access CDSS API on behalf of a signed-in user.",
        "userConsentDisplayName": "Access CDSS API",
        "userConsentDescription": "Allow this app to access CDSS API on your behalf.",
    }
    scopes.append(target)
else:
    target["isEnabled"] = True

api["oauth2PermissionScopes"] = scopes
if not api.get("requestedAccessTokenVersion"):
    api["requestedAccessTokenVersion"] = 2

print(target["id"])
print(json.dumps({"api": api}, separators=(",", ":")))
PY
)"

SCOPE_ID="$(printf "%s" "${SCOPE_SCRIPT_OUTPUT}" | sed -n '1p')"
SCOPE_PATCH_BODY="$(printf "%s" "${SCOPE_SCRIPT_OUTPUT}" | sed -n '2p')"

if [[ -z "${SCOPE_ID}" || -z "${SCOPE_PATCH_BODY}" ]]; then
    log_error "Failed to prepare API scope patch payload."
    exit 1
fi

az rest \
    --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${API_OBJ_ID}" \
    --headers "Content-Type=application/json" \
    --body "${SCOPE_PATCH_BODY}" \
    --only-show-errors \
    --output none
log_success "API scope ensured: ${SCOPE_NAME} (${SCOPE_ID})"

# Add delegated permission from SPA -> API scope (idempotent check first).
az ad sp create --id "${API_APP_ID}" --only-show-errors --output none >/dev/null 2>&1 || true
az ad sp create --id "${SPA_APP_ID}" --only-show-errors --output none >/dev/null 2>&1 || true

MAPPING_COUNT="$(get_permission_mapping_count "${SPA_APP_ID}" "${API_APP_ID}" "${SCOPE_ID}" 2>/dev/null || true)"

if [[ "${MAPPING_COUNT}" == "0" || -z "${MAPPING_COUNT}" ]]; then
    log_info "Adding delegated permission ${SCOPE_NAME} to SPA app..."
    az ad app permission add \
        --id "${SPA_APP_ID}" \
        --api "${API_APP_ID}" \
        --api-permissions "${SCOPE_ID}=Scope" \
        --only-show-errors \
        --output none
    log_success "Delegated permission added."
else
    log_info "Delegated permission already present."
fi

if [[ "${SKIP_ADMIN_CONSENT}" != "true" ]]; then
    log_info "Granting admin consent (requires tenant admin privileges)..."
    if az ad app permission admin-consent --id "${SPA_APP_ID}" --only-show-errors --output none; then
        log_success "Admin consent granted."
    else
        log_warn "Admin consent step failed. Ask a tenant admin to grant consent in Entra ID."
    fi
else
    log_warn "Skipping admin consent as requested."
fi

FINAL_COUNT="$(get_permission_mapping_count "${SPA_APP_ID}" "${API_APP_ID}" "${SCOPE_ID}" 2>/dev/null || true)"

log_info "Verification (expected 1): ${FINAL_COUNT:-0}"

build_api_base_url() {
    local fqdn="$1"
    if [[ "${fqdn}" == http://* || "${fqdn}" == https://* ]]; then
        echo "${fqdn%/}/api"
    else
        echo "https://${fqdn}/api"
    fi
}

CONTAINER_APP_NAME="$(resolve_container_app_name "${RESOURCE_GROUP}" "${CONTAINER_APP_NAME}")"

if [[ -n "${RESOURCE_GROUP}" && -n "${CONTAINER_APP_NAME}" ]]; then
    # Entra access tokens for custom APIs carry the API app client ID in aud.
    sync_backend_auth_audience "${RESOURCE_GROUP}" "${CONTAINER_APP_NAME}" "${API_APP_ID}"
fi

if [[ "${SKIP_FRONTEND_ENV}" != "true" ]]; then
    if [[ -z "${API_FQDN}" && -n "${RESOURCE_GROUP}" ]]; then
        if [[ -n "${CONTAINER_APP_NAME}" ]]; then
            API_FQDN="$(az containerapp show \
                --resource-group "${RESOURCE_GROUP}" \
                --name "${CONTAINER_APP_NAME}" \
                --query "properties.configuration.ingress.fqdn" \
                -o tsv 2>/dev/null || true)"
        fi
    fi

    if [[ -z "${API_FQDN}" ]]; then
        log_warn "API FQDN unavailable. Skipping ${FRONTEND_ENV_FILE} generation."
        log_warn "Pass --resource-group (and optional --container-app-name) or --api-fqdn."
    else
        API_BASE_URL="$(build_api_base_url "${API_FQDN}")"
        mkdir -p "$(dirname "${FRONTEND_ENV_FILE}")"
        cat > "${FRONTEND_ENV_FILE}" <<EOF
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=${API_BASE_URL}
VITE_AZURE_CLIENT_ID=${SPA_APP_ID}
VITE_AZURE_TENANT_ID=${TENANT_ID}
VITE_API_SCOPE=${API_APP_ID_URI}/${SCOPE_NAME}
EOF
        log_success "Wrote frontend env file: ${FRONTEND_ENV_FILE}"
    fi
else
    log_warn "Skipping frontend env file generation as requested."
fi

echo ""
echo "Set frontend env values:"
echo "  VITE_AZURE_CLIENT_ID=${SPA_APP_ID}"
echo "  VITE_AZURE_TENANT_ID=${TENANT_ID}"
echo "  VITE_API_SCOPE=${API_APP_ID_URI}/${SCOPE_NAME}"
if [[ -n "${API_FQDN}" ]]; then
    echo "  VITE_API_BASE_URL=$(build_api_base_url "${API_FQDN}")"
fi
echo ""
echo "Current API auth settings should align to:"
echo "  CDSS_AUTH_AUDIENCE=${API_APP_ID}"
echo "  CDSS_AUTH_REQUIRED_SCOPES=[\"${SCOPE_NAME}\"]"
