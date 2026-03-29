#!/bin/bash
# ============================================================================
# CDSS - Seed Sample Data Script
# ============================================================================

set -euo pipefail

ENVIRONMENT="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLE_DATA_DIR="${SCRIPT_DIR}/../../sample_data"

echo "Seeding sample data for environment: ${ENVIRONMENT}"

# Load Azure config
if [[ -f "${SCRIPT_DIR}/../../.env.azure" ]]; then
    source "${SCRIPT_DIR}/../../.env.azure"
else
    echo ".env.azure not found. Run deploy.sh first."
    exit 1
fi

COSMOS_DATABASE_NAME="${CDSS_AZURE_COSMOS_DATABASE_NAME:-cdss-db}"
COSMOS_ENDPOINT="${CDSS_AZURE_COSMOS_ENDPOINT:-}"

if [[ -z "${COSMOS_ENDPOINT}" ]]; then
    echo "CDSS_AZURE_COSMOS_ENDPOINT is not set in .env.azure"
    exit 1
fi

COSMOS_ACCOUNT=$(echo "${COSMOS_ENDPOINT}" | sed 's|https://||' | sed 's|.documents.azure.com.*||')

# 1. Upload patient data to Cosmos DB
echo "Uploading patient profile to Cosmos DB..."
az cosmosdb sql container item upsert \
    --account-name "${COSMOS_ACCOUNT}" \
    --database-name "${COSMOS_DATABASE_NAME}" \
    --container-name patient-profiles \
    --partition-key-value "patient_12345" \
    --body @"${SAMPLE_DATA_DIR}/sample_patient.json"

# 2. Upload protocol to Blob Storage
echo "Uploading treatment protocol to Blob Storage..."
STORAGE_ACCOUNT=$(az storage account list --query "[?tags.project=='cdss-agentic-rag' && tags.environment=='${ENVIRONMENT}'].name" -o tsv | head -1)
az storage blob upload \
    --account-name "$STORAGE_ACCOUNT" \
    --container-name treatment-protocols \
    --name "ENDO-DM-CKD-2025-v3.md" \
    --file "${SAMPLE_DATA_DIR}/sample_protocol.md" \
    --auth-mode login \
    --overwrite


# 3. Upload lab report to staging
echo "Uploading lab report to staging..."
az storage blob upload \
    --account-name "$STORAGE_ACCOUNT" \
    --container-name staging-documents \
    --name "lab_report_patient_12345_20260128.txt" \
    --file "${SAMPLE_DATA_DIR}/sample_lab_report.txt" \
    --auth-mode login \
    --overwrite

echo "Sample data seeded successfully!"
echo ""
echo "Next steps:"
echo "  1. Run the ingestion pipeline to index documents"
echo "  2. Test queries against patient_12345"
