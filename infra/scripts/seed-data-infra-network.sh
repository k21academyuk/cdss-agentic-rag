#!/bin/bash
# Seed sample data from inside Azure Container App network boundary.
#
# This script executes a Python payload inside the deployed Container App so
# Cosmos DB and Storage private-network restrictions do not block seeding.
#
# Usage:
#   ./infra/scripts/seed-data-infra-network.sh <resource-group> [container-app-name]
#
# Example:
#   ./infra/scripts/seed-data-infra-network.sh cdss-prod-rg

set -euo pipefail

RESOURCE_GROUP="${1:-cdss-prod-rg}"
CONTAINER_APP_NAME="${2:-}"

log_info() {
    echo "[INFO] $1"
}

log_warn() {
    echo "[WARN] $1"
}

log_error() {
    echo "[ERROR] $1"
}

if ! command -v az >/dev/null 2>&1; then
    log_error "Azure CLI is required."
    exit 1
fi

if ! az account show >/dev/null 2>&1; then
    log_error "Not logged in to Azure CLI. Run: az login"
    exit 1
fi

if [[ -z "${CONTAINER_APP_NAME}" ]]; then
    CONTAINER_APP_NAME="$(az containerapp list --resource-group "${RESOURCE_GROUP}" --query "[?contains(name, '-api')].name | [0]" -o tsv)"
fi

if [[ -z "${CONTAINER_APP_NAME}" ]]; then
    log_error "Could not resolve a Container App name in resource group ${RESOURCE_GROUP}."
    log_error "Pass it explicitly as the second argument."
    exit 1
fi

log_info "Using Container App: ${CONTAINER_APP_NAME}"
log_info "Preparing in-network seeding execution..."

KEYVAULT_NAME="$(az keyvault list --resource-group "${RESOURCE_GROUP}" --query "[0].name" -o tsv 2>/dev/null || true)"
MANAGED_IDENTITY_ID="$(az containerapp show --resource-group "${RESOURCE_GROUP}" --name "${CONTAINER_APP_NAME}" --query "keys(identity.userAssignedIdentities)[0]" -o tsv 2>/dev/null || true)"

if [[ -n "${KEYVAULT_NAME}" && -n "${MANAGED_IDENTITY_ID}" ]]; then
    KEYVAULT_ID="$(az keyvault show --name "${KEYVAULT_NAME}" --resource-group "${RESOURCE_GROUP}" --query id -o tsv 2>/dev/null || true)"
    MANAGED_IDENTITY_PRINCIPAL_ID="$(az identity show --ids "${MANAGED_IDENTITY_ID}" --query principalId -o tsv 2>/dev/null || true)"

    if [[ -n "${KEYVAULT_ID}" && -n "${MANAGED_IDENTITY_PRINCIPAL_ID}" ]]; then
        KV_ROLE_COUNT="$(az role assignment list \
            --assignee-object-id "${MANAGED_IDENTITY_PRINCIPAL_ID}" \
            --scope "${KEYVAULT_ID}" \
            --query "[?roleDefinitionName=='Key Vault Secrets User'] | length(@)" \
            -o tsv 2>/dev/null || true)"

        if [[ "${KV_ROLE_COUNT}" == "0" || -z "${KV_ROLE_COUNT}" ]]; then
            log_info "Assigning Key Vault Secrets User role to Container App managed identity..."
            if az role assignment create \
                --assignee-object-id "${MANAGED_IDENTITY_PRINCIPAL_ID}" \
                --assignee-principal-type ServicePrincipal \
                --role "Key Vault Secrets User" \
                --scope "${KEYVAULT_ID}" \
                --only-show-errors \
                --output none 2>/tmp/cdss_seed_network_error.log; then
                log_info "Role assignment created. Waiting for RBAC propagation..."
                sleep 20
            else
                log_warn "Could not assign Key Vault role automatically: $(cat /tmp/cdss_seed_network_error.log 2>/dev/null || true)"
            fi
        fi
    fi
fi

# Resolve a runnable revision for `az containerapp exec`.
ACTIVE_REVISION="$(az containerapp show \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${CONTAINER_APP_NAME}" \
    --query "properties.latestReadyRevisionName" \
    -o tsv 2>/dev/null || true)"

if [[ -z "${ACTIVE_REVISION}" || "${ACTIVE_REVISION}" == "null" ]]; then
    ACTIVE_REVISION="$(az containerapp show \
        --resource-group "${RESOURCE_GROUP}" \
        --name "${CONTAINER_APP_NAME}" \
        --query "properties.latestRevisionName" \
        -o tsv 2>/dev/null || true)"
fi

if [[ -z "${ACTIVE_REVISION}" || "${ACTIVE_REVISION}" == "null" ]]; then
    ACTIVE_REVISION="$(az containerapp revision list \
        --resource-group "${RESOURCE_GROUP}" \
        --name "${CONTAINER_APP_NAME}" \
        --query "sort_by(@, &properties.createdTime)[-1].name" \
        -o tsv 2>/dev/null || true)"
fi

if [[ -z "${ACTIVE_REVISION}" || "${ACTIVE_REVISION}" == "null" ]]; then
    log_warn "No revision found. Attempting to trigger a fresh revision..."
    PROBE_VALUE="$(date +%s)"
    if az containerapp update \
        --resource-group "${RESOURCE_GROUP}" \
        --name "${CONTAINER_APP_NAME}" \
        --set-env-vars "SEED_PROBE_TS=${PROBE_VALUE}" \
        --output none 2>/tmp/cdss_seed_network_error.log; then
        log_info "Container App update submitted. Waiting for revision provisioning..."
        sleep 20
    else
        log_warn "Container App update failed: $(cat /tmp/cdss_seed_network_error.log 2>/dev/null || true)"
    fi

    ACTIVE_REVISION="$(az containerapp show \
        --resource-group "${RESOURCE_GROUP}" \
        --name "${CONTAINER_APP_NAME}" \
        --query "properties.latestReadyRevisionName" \
        -o tsv 2>/dev/null || true)"

    if [[ -z "${ACTIVE_REVISION}" || "${ACTIVE_REVISION}" == "null" ]]; then
        ACTIVE_REVISION="$(az containerapp revision list \
            --resource-group "${RESOURCE_GROUP}" \
            --name "${CONTAINER_APP_NAME}" \
            --query "sort_by(@, &properties.createdTime)[-1].name" \
            -o tsv 2>/dev/null || true)"
    fi

    if [[ -z "${ACTIVE_REVISION}" || "${ACTIVE_REVISION}" == "null" ]]; then
        PROVISIONING_STATE="$(az containerapp show --resource-group "${RESOURCE_GROUP}" --name "${CONTAINER_APP_NAME}" --query "properties.provisioningState" -o tsv 2>/dev/null || true)"
        log_error "No Container App revision found for ${CONTAINER_APP_NAME}."
        log_error "Check revision status with:"
        log_error "  az containerapp revision list -g ${RESOURCE_GROUP} -n ${CONTAINER_APP_NAME} -o table"
        log_error "  az containerapp show -g ${RESOURCE_GROUP} -n ${CONTAINER_APP_NAME} --query properties.provisioningState -o tsv"
        if [[ "${PROVISIONING_STATE}" == "Failed" ]]; then
            log_error "Container App provisioning is Failed. Apply latest infra fixes and recreate a revision:"
            log_error "  ./infra/scripts/deploy.sh prod ${RESOURCE_GROUP}"
        fi
        exit 1
    fi
fi

log_info "Using revision: ${ACTIVE_REVISION}"

# Keep command short to avoid Azure CLI websocket URL length limits (414 errors).
REMOTE_COMMAND="python -m cdss.tools.seed_sample_data"
log_info "Executing in-network seeding module inside Container App..."

EXEC_LOG="$(mktemp)"
MAX_EXEC_RETRIES=3
EXEC_SUCCESS="false"

for ATTEMPT in $(seq 1 "${MAX_EXEC_RETRIES}"); do
    log_info "Exec attempt ${ATTEMPT}/${MAX_EXEC_RETRIES}..."

    if az containerapp exec \
        --resource-group "${RESOURCE_GROUP}" \
        --name "${CONTAINER_APP_NAME}" \
        --revision "${ACTIVE_REVISION}" \
        --command "${REMOTE_COMMAND}" 2>&1 | tee "${EXEC_LOG}"; then
        if grep -q "\[ERROR\] In-network seed failed:" "${EXEC_LOG}"; then
            log_warn "In-network seed reported an application error."
        elif grep -q "ClusterExecFailure" "${EXEC_LOG}" || grep -q "websocket: close 1011" "${EXEC_LOG}"; then
            log_warn "Container exec encountered a transient platform error."
        else
            EXEC_SUCCESS="true"
            break
        fi
    else
        log_warn "az containerapp exec command failed on attempt ${ATTEMPT}."
    fi

    if [[ "${ATTEMPT}" -lt "${MAX_EXEC_RETRIES}" ]]; then
        log_info "Retrying in 10s..."
        sleep 10
    fi
done

if [[ "${EXEC_SUCCESS}" != "true" ]]; then
    log_error "In-network seed command failed."
    log_error "Ensure the backend image includes sample_data and 'cdss.tools.seed_sample_data', then retry."
    rm -f "${EXEC_LOG}" || true
    exit 1
fi

rm -f "${EXEC_LOG}" || true

log_info "Done."
