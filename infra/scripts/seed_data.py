#!/usr/bin/env python3
"""Seed sample data for CDSS using Entra ID authentication.

This script seeds sample patient profiles to Cosmos DB and uploads
sample documents to Blob Storage using Azure Entra ID authentication
(DefaultAzureCredential), which works with:
- `az login` for local development
- Managed Identity for Azure-hosted execution
- Service Principal via environment variables

Usage:
    python infra/scripts/seed_data.py --environment prod
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

SRC_DIR = Path(__file__).resolve().parents[2] / "src"
SEED_HELPER_PATH = SRC_DIR / "cdss" / "tools" / "seed_sample_data.py"


def _load_build_seed_patients():
    spec = importlib.util.spec_from_file_location("cdss_seed_sample_data", SEED_HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load seed helper module: {SEED_HELPER_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.build_seed_patients


build_seed_patients = _load_build_seed_patients()


def get_settings_from_env() -> dict[str, str]:
    import os

    settings = {}

    env_file = Path(".env.azure")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    settings[key] = value

    for key, value in os.environ.items():
        if key.startswith("CDSS_") or key == "ENVIRONMENT":
            settings[key] = value

    return settings


def read_setting(
    settings: dict[str, str],
    key: str,
    default: str = "",
) -> str:
    if key in settings and settings[key] != "":
        return settings[key]
    return default


def seed_cosmos(settings: dict[str, str], sample_data_dir: Path) -> bool:
    endpoint = read_setting(settings, "CDSS_AZURE_COSMOS_ENDPOINT")
    if not endpoint:
        print("[ERROR] CDSS_AZURE_COSMOS_ENDPOINT not set")
        return False

    database_name = read_setting(settings, "CDSS_AZURE_COSMOS_DATABASE_NAME", "cdss-db")
    cosmos_key = read_setting(settings, "CDSS_AZURE_COSMOS_KEY")
    use_entra_id = read_setting(settings, "CDSS_AZURE_COSMOS_USE_ENTRA_ID", "false").lower() == "true"

    print(f"[INFO] Connecting to Cosmos DB: {endpoint}")
    if not use_entra_id and cosmos_key:
        print("[INFO] Using Cosmos key authentication")
        client = CosmosClient(endpoint, cosmos_key)
    else:
        print("[INFO] Using Entra ID authentication")
        credential = DefaultAzureCredential()
        client = CosmosClient(endpoint, credential)

    database = client.get_database_client(database_name)
    container = database.get_container_client("patient-profiles")

    patient_file = sample_data_dir / "sample_patient.json"
    if not patient_file.exists():
        print(f"[WARN] Sample patient file not found: {patient_file}")
        return False

    seeded_profiles = build_seed_patients(now=datetime.now(UTC).isoformat())
    for profile in seeded_profiles:
        print(f"[INFO] Upserting patient profile: {profile.get('patient_id', 'unknown')}")
        container.upsert_item(body=profile)

    print(f"[SUCCESS] Seeded {len(seeded_profiles)} patient profiles to Cosmos DB")
    return True


def seed_blob_storage(settings: dict[str, str], sample_data_dir: Path) -> bool:
    endpoint = read_setting(settings, "CDSS_AZURE_BLOB_ENDPOINT")
    connection_string = read_setting(settings, "CDSS_AZURE_BLOB_CONNECTION_STRING")
    use_entra_id = read_setting(settings, "CDSS_AZURE_BLOB_USE_ENTRA_ID", "false").lower() == "true"

    if not use_entra_id and connection_string:
        print("[INFO] Connecting to Blob Storage using connection string")
        client = BlobServiceClient.from_connection_string(connection_string)
    else:
        if not endpoint:
            print("[ERROR] CDSS_AZURE_BLOB_ENDPOINT not set")
            return False
        print(f"[INFO] Connecting to Blob Storage: {endpoint}")
        print("[INFO] Using Entra ID authentication")
        credential = DefaultAzureCredential()
        client = BlobServiceClient(account_url=endpoint, credential=credential)

    uploads = [
        ("treatment-protocols", "ENDO-DM-CKD-2025-v3.md", "sample_protocol.md"),
        ("staging-documents", "lab_report_patient_12345_20260128.txt", "sample_lab_report.txt"),
    ]

    for container_name, blob_name, file_name in uploads:
        file_path = sample_data_dir / file_name
        if not file_path.exists():
            print(f"[WARN] File not found: {file_path}")
            continue

        container_client = client.get_container_client(container_name)

        with open(file_path, "rb") as f:
            content = f.read()

        print(f"[INFO] Uploading {file_name} to {container_name}/{blob_name}")
        container_client.upload_blob(name=blob_name, data=content, overwrite=True)
        print(f"[SUCCESS] Uploaded {blob_name}")

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed CDSS sample data")
    parser.add_argument(
        "--environment",
        "-e",
        default="dev",
        choices=["dev", "staging", "prod"],
        help="Target environment",
    )
    parser.add_argument(
        "--skip-cosmos",
        action="store_true",
        help="Skip Cosmos DB seeding",
    )
    parser.add_argument(
        "--skip-storage",
        action="store_true",
        help="Skip Blob Storage seeding",
    )
    args = parser.parse_args()

    print(f"[INFO] Seeding data for environment: {args.environment}")

    script_dir = Path(__file__).parent
    sample_data_dir = script_dir.parent.parent / "sample_data"

    if not sample_data_dir.exists():
        print(f"[ERROR] Sample data directory not found: {sample_data_dir}")
        return 1

    settings = get_settings_from_env()

    cosmos_ok = True
    storage_ok = True

    if not args.skip_cosmos:
        try:
            cosmos_ok = seed_cosmos(settings, sample_data_dir)
        except Exception as e:
            print(f"[ERROR] Failed to seed Cosmos DB: {e}")
            return 1

    if not args.skip_storage:
        try:
            storage_ok = seed_blob_storage(settings, sample_data_dir)
        except Exception as e:
            print(f"[ERROR] Failed to seed Blob Storage: {e}")
            return 1

    if not cosmos_ok or not storage_ok:
        print()
        print("[ERROR] Sample data seeding incomplete due to missing configuration.")
        if not cosmos_ok:
            print("  - Cosmos DB seeding did not run successfully.")
        if not storage_ok:
            print("  - Blob Storage seeding did not run successfully.")
        return 1

    print()
    print("[SUCCESS] Sample data seeded successfully!")
    print()
    print("Next steps:")
    print("  1. Run the ingestion pipeline to index documents")
    print("  2. Test patients (e.g., patient_12345, patient_1, patient_2)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
