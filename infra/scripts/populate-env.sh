#!/bin/bash
# Auto-populate .env and .env.azure from deployed Azure resources

set -euo pipefail

RG="${1:-cdss-prod-rg}"
ENVIRONMENT="${2:-}"

if [[ -z "$ENVIRONMENT" ]]; then
    if [[ "$RG" == *"prod"* ]]; then
        ENVIRONMENT="prod"
    elif [[ "$RG" == *"staging"* ]]; then
        ENVIRONMENT="staging"
    else
        ENVIRONMENT="dev"
    fi
fi

echo "Fetching Azure resource details from: $RG"

warn() {
    echo "[WARN] $1"
}

run_az_tsv() {
    local __result_var="$1"
    local __description="$2"
    shift 2

    local __output=""
    local __error=""
    if ! __output="$("$@" -o tsv 2>/tmp/cdss_populate_env_error.log)"; then
        __error="$(cat /tmp/cdss_populate_env_error.log 2>/dev/null || true)"
        if [[ -n "$__error" ]]; then
            warn "${__description} failed; leaving value empty. Details: ${__error}"
        else
            warn "${__description} failed; leaving value empty."
        fi
        __output=""
    fi

    printf -v "$__result_var" "%s" "$__output"
}

# Get resource names
run_az_tsv COSMOS "Failed to find Cosmos DB account" az cosmosdb list --resource-group "$RG" --query "[0].name"
run_az_tsv SEARCH "Failed to find Azure AI Search service" az search service list --resource-group "$RG" --query "[0].name"
run_az_tsv OPENAI "Failed to find Azure OpenAI account" az cognitiveservices account list --resource-group "$RG" --query "[?kind=='OpenAI'].name | [0]"
run_az_tsv DOCINTEL "Failed to find Document Intelligence account" az cognitiveservices account list --resource-group "$RG" --query "[?kind=='FormRecognizer'].name | [0]"
run_az_tsv KEYVAULT "Failed to find Key Vault" az keyvault list --resource-group "$RG" --query "[0].name"
run_az_tsv REDIS "Failed to find Azure Cache for Redis" az redis list --resource-group "$RG" --query "[0].name"

# Get storage account - filter out deployment scripts storage (contains 'scripts' in name)
run_az_tsv STORAGE "Failed to find Storage account" az storage account list --resource-group "$RG" --query "[?tags.project=='cdss-agentic-rag' && !contains(name, 'scripts')].name | [0]"

# Fallback: resolve Cosmos via generic resource list
if [[ -z "${COSMOS}" ]]; then
    run_az_tsv COSMOS "Failed to find Cosmos DB account fallback" az resource list --resource-group "$RG" --resource-type "Microsoft.DocumentDB/databaseAccounts" --query "[0].name"
fi

# Fallback: if no storage found with tag, try without tag filter but exclude scripts
if [[ -z "${STORAGE}" ]]; then
    run_az_tsv STORAGE "Failed to find Storage account fallback" az storage account list --resource-group "$RG" --query "[?(!contains(name, 'scripts') && !contains(name, 'zsa'))].name | [0]"
fi

# Fallback: resolve Storage via generic resource list
if [[ -z "${STORAGE}" ]]; then
    run_az_tsv STORAGE "Failed to find Storage account generic fallback" az resource list --resource-group "$RG" --resource-type "Microsoft.Storage/storageAccounts" --query "[?(!contains(name, 'scripts') && !contains(name, 'zsa'))].name | [0]"
fi

# Get endpoints
run_az_tsv COSMOS_EP "Failed to fetch Cosmos endpoint" az cosmosdb show --name "$COSMOS" --resource-group "$RG" --query documentEndpoint

# Fallback: construct Cosmos endpoint from account name if direct fetch failed
if [[ -z "${COSMOS_EP}" && -n "${COSMOS}" ]]; then
    COSMOS_EP="https://${COSMOS}.documents.azure.com:443/"
    echo "[INFO] Constructed Cosmos endpoint from account name: ${COSMOS_EP}"
fi

SEARCH_EP="https://${SEARCH}.search.windows.net"
run_az_tsv OPENAI_EP "Failed to fetch OpenAI endpoint" az cognitiveservices account show --name "$OPENAI" --resource-group "$RG" --query properties.endpoint
run_az_tsv DOCINTEL_EP "Failed to fetch Document Intelligence endpoint" az cognitiveservices account show --name "$DOCINTEL" --resource-group "$RG" --query properties.endpoint

# Get keys - these may fail in network-isolated prod environments
run_az_tsv COSMOS_KEY "Failed to fetch Cosmos key" az cosmosdb keys list --name "$COSMOS" --resource-group "$RG" --query primaryMasterKey
run_az_tsv SEARCH_KEY "Failed to fetch Search admin key" az search admin-key show --service-name "$SEARCH" --resource-group "$RG" --query primaryKey
run_az_tsv OPENAI_KEY "Failed to fetch OpenAI key" az cognitiveservices account keys list --name "$OPENAI" --resource-group "$RG" --query key1
run_az_tsv DOCINTEL_KEY "Failed to fetch Document Intelligence key" az cognitiveservices account keys list --name "$DOCINTEL" --resource-group "$RG" --query key1
run_az_tsv REDIS_KEY "Failed to fetch Redis key" az redis list-keys --name "$REDIS" --resource-group "$RG" --query primaryKey
run_az_tsv REDIS_HOST "Failed to fetch Redis host" az redis show --name "$REDIS" --resource-group "$RG" --query hostName

# Storage connection string - for Entra ID auth, we can leave this empty
run_az_tsv STORAGE_CONN "Failed to fetch Storage connection string" az storage account show-connection-string --name "$STORAGE" --resource-group "$RG" --query connectionString

# Get storage account endpoint for Entra ID auth
run_az_tsv STORAGE_EP "Failed to fetch Storage endpoint" az storage account show --name "$STORAGE" --resource-group "$RG" --query primaryEndpoints.blob

# Fallback: construct Storage blob endpoint from account name if direct fetch failed
if [[ -z "${STORAGE_EP}" && -n "${STORAGE}" ]]; then
    STORAGE_EP="https://${STORAGE}.blob.core.windows.net/"
    echo "[INFO] Constructed Storage endpoint from account name: ${STORAGE_EP}"
fi

# Cosmos key fallback: derive AccountKey from connection string when direct key lookup fails.
if [[ -z "${COSMOS_KEY}" ]]; then
    run_az_tsv COSMOS_CONN "Failed to fetch Cosmos connection string fallback" az cosmosdb keys list --name "$COSMOS" --resource-group "$RG" --type connection-strings --query "connectionStrings[0].connectionString"
    if [[ -n "${COSMOS_CONN}" ]]; then
        COSMOS_KEY="$(echo "$COSMOS_CONN" | sed -n 's/.*AccountKey=\([^;]*\).*/\1/p')"
        if [[ -n "${COSMOS_KEY}" ]]; then
            echo "[INFO] Derived Cosmos key from connection string fallback."
        fi
    fi
fi

# Final fallback: fetch Cosmos connection string from Key Vault secret generated by Bicep deployment.
if [[ -z "${COSMOS_KEY}" && -n "${KEYVAULT}" ]]; then
    run_az_tsv KV_COSMOS_CONN "Failed to fetch Key Vault cosmos-connection-string secret fallback" az keyvault secret show --vault-name "$KEYVAULT" --name "cosmos-connection-string" --query value
    if [[ -z "${KV_COSMOS_CONN}" ]]; then
        run_az_tsv CURRENT_USER_OID "Failed to detect signed-in user object ID for Key Vault role assignment" az ad signed-in-user show --query id
        run_az_tsv KEYVAULT_ID "Failed to resolve Key Vault resource ID for role assignment" az keyvault show --name "$KEYVAULT" --resource-group "$RG" --query id

        if [[ -n "${CURRENT_USER_OID}" && -n "${KEYVAULT_ID}" ]]; then
            echo "[INFO] Attempting to grant Key Vault Secrets User role to current user for ${KEYVAULT}..."
            if az role assignment create \
                --assignee-object-id "$CURRENT_USER_OID" \
                --assignee-principal-type User \
                --role "Key Vault Secrets User" \
                --scope "$KEYVAULT_ID" \
                --only-show-errors \
                --output none 2>/tmp/cdss_populate_env_error.log; then
                echo "[INFO] Role assignment completed. Waiting for RBAC propagation..."
            else
                warn "Automatic Key Vault role assignment failed. Details: $(cat /tmp/cdss_populate_env_error.log 2>/dev/null || true)"
            fi

            for _ in 1 2 3 4 5 6; do
                run_az_tsv KV_COSMOS_CONN "Failed to fetch Key Vault cosmos-connection-string secret after role assignment" az keyvault secret show --vault-name "$KEYVAULT" --name "cosmos-connection-string" --query value
                if [[ -n "${KV_COSMOS_CONN}" ]]; then
                    break
                fi
                echo "[INFO] Waiting 10s for role propagation before retrying Key Vault secret read..."
                sleep 10
            done
        fi
    fi

    if [[ -n "${KV_COSMOS_CONN}" ]]; then
        COSMOS_KEY="$(echo "$KV_COSMOS_CONN" | sed -n 's/.*AccountKey=\([^;]*\).*/\1/p')"
        if [[ -n "${COSMOS_KEY}" ]]; then
            echo "[INFO] Derived Cosmos key from Key Vault secret fallback."
        fi
    fi
fi

COSMOS_USE_ENTRA_ID="false"
if [[ -z "${COSMOS_KEY}" ]]; then
    COSMOS_USE_ENTRA_ID="true"
    warn "Cosmos key is unavailable. .env will enable Entra ID auth for Cosmos."
fi

STORAGE_USE_ENTRA_ID="false"
if [[ -z "${STORAGE_CONN}" ]]; then
    STORAGE_USE_ENTRA_ID="true"
    warn "Storage connection string is unavailable. .env will enable Entra ID auth for Storage."
fi

REDIS_URL="redis://localhost:6379/0"
if [[ -n "${REDIS_KEY}" && -n "${REDIS_HOST}" ]]; then
    REDIS_URL="rediss://:${REDIS_KEY}@${REDIS_HOST}:6380/0"
fi

# Create .env.azure (for seed-data.sh)
cat > .env.azure << EOF
ENVIRONMENT=$ENVIRONMENT
CDSS_AZURE_COSMOS_ENDPOINT=$COSMOS_EP
CDSS_AZURE_COSMOS_DATABASE_NAME=cdss-db
CDSS_AZURE_COSMOS_KEY=$COSMOS_KEY
CDSS_AZURE_COSMOS_USE_ENTRA_ID=$COSMOS_USE_ENTRA_ID
CDSS_AZURE_SEARCH_ENDPOINT=$SEARCH_EP
CDSS_AZURE_OPENAI_ENDPOINT=$OPENAI_EP
CDSS_AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
CDSS_AZURE_OPENAI_MINI_DEPLOYMENT_NAME=gpt-4o-mini
CDSS_AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
CDSS_AZURE_BLOB_ENDPOINT=$STORAGE_EP
CDSS_AZURE_BLOB_CONNECTION_STRING=$STORAGE_CONN
CDSS_AZURE_BLOB_USE_ENTRA_ID=$STORAGE_USE_ENTRA_ID
EOF

# Create .env (for Python app)
cat > .env << EOF
# ═══════════════════════════════════════════════════════════════════════════════
# CDSS Agentic RAG - Environment Configuration (Auto-generated)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Azure OpenAI ──────────────────────────────────────────────────────────────
CDSS_AZURE_OPENAI_ENDPOINT=$OPENAI_EP
CDSS_AZURE_OPENAI_API_KEY=$OPENAI_KEY
CDSS_AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
CDSS_AZURE_OPENAI_MINI_DEPLOYMENT_NAME=gpt-4o-mini
CDSS_AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
CDSS_AZURE_OPENAI_API_VERSION=2024-12-01-preview

# ── Azure AI Search ───────────────────────────────────────────────────────────
CDSS_AZURE_SEARCH_ENDPOINT=$SEARCH_EP
CDSS_AZURE_SEARCH_API_KEY=$SEARCH_KEY
CDSS_AZURE_SEARCH_PATIENT_RECORDS_INDEX=patient-records
CDSS_AZURE_SEARCH_TREATMENT_PROTOCOLS_INDEX=treatment-protocols
CDSS_AZURE_SEARCH_MEDICAL_LITERATURE_INDEX=medical-literature-cache
CDSS_AZURE_SEARCH_PATIENT_RECORDS_SEMANTIC_CONFIG=patient-records-semantic
CDSS_AZURE_SEARCH_TREATMENT_PROTOCOLS_SEMANTIC_CONFIG=protocols-semantic
CDSS_AZURE_SEARCH_MEDICAL_LITERATURE_SEMANTIC_CONFIG=literature-semantic

# ── Azure Cosmos DB ───────────────────────────────────────────────────────────
CDSS_AZURE_COSMOS_ENDPOINT=$COSMOS_EP
CDSS_AZURE_COSMOS_KEY=$COSMOS_KEY
CDSS_AZURE_COSMOS_USE_ENTRA_ID=$COSMOS_USE_ENTRA_ID
CDSS_AZURE_COSMOS_DATABASE_NAME=cdss-db
CDSS_AZURE_COSMOS_PATIENT_PROFILES_CONTAINER=patient-profiles
CDSS_AZURE_COSMOS_CONVERSATION_HISTORY_CONTAINER=conversation-history
CDSS_AZURE_COSMOS_EMBEDDING_CACHE_CONTAINER=embedding-cache
CDSS_AZURE_COSMOS_AUDIT_LOG_CONTAINER=audit-log
CDSS_AZURE_COSMOS_AGENT_STATE_CONTAINER=agent-state

# ── Azure Document Intelligence ──────────────────────────────────────────────
CDSS_AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=$DOCINTEL_EP
CDSS_AZURE_DOCUMENT_INTELLIGENCE_KEY=$DOCINTEL_KEY

# ── Azure Blob Storage ───────────────────────────────────────────────────────
CDSS_AZURE_BLOB_CONNECTION_STRING=$STORAGE_CONN
CDSS_AZURE_BLOB_ENDPOINT=$STORAGE_EP
CDSS_AZURE_BLOB_USE_ENTRA_ID=$STORAGE_USE_ENTRA_ID
CDSS_AZURE_BLOB_PROTOCOLS_CONTAINER=treatment-protocols
CDSS_AZURE_KEY_VAULT_URL=https://$KEYVAULT.vault.azure.net/

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
CDSS_REDIS_URL=$REDIS_URL

# ── Application Settings ─────────────────────────────────────────────────────
CDSS_DEBUG=false
CDSS_LOG_LEVEL=INFO
CDSS_CORS_ORIGINS=["http://localhost:3000","http://localhost:3001"]
CDSS_CORS_ALLOW_METHODS=["GET","POST","PUT","PATCH","DELETE","OPTIONS"]
CDSS_CORS_ALLOW_HEADERS=["Authorization","Content-Type","X-Request-ID"]
CDSS_CORS_EXPOSE_HEADERS=["X-Request-ID","X-Trace-ID"]
CDSS_CORS_ALLOW_CREDENTIALS=true
CDSS_AUTH_ENABLED=false
CDSS_AUTH_TENANT_ID=
CDSS_AUTH_AUDIENCE=
CDSS_AUTH_REQUIRED_SCOPES=[]
CDSS_MAX_CONCURRENT_AGENTS=10
CDSS_RESPONSE_TIMEOUT_SECONDS=30
CDSS_CONFIDENCE_THRESHOLD=0.6
EOF

echo "✅ Created .env.azure"
echo "✅ Created .env with all Azure credentials"
echo ""
if [[ "$ENVIRONMENT" == "prod" ]]; then
    echo "Next: ./infra/scripts/seed-data-infra-network.sh $RG"
else
    echo "Next: python infra/scripts/seed_data.py --environment $ENVIRONMENT"
fi
