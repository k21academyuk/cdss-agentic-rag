from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

PATIENT_PROFILE_ID: Final[str] = "patient_12345"
PROTOCOL_BLOB_NAME: Final[str] = "ENDO-DM-CKD-2025-v3.md"
LAB_REPORT_BLOB_NAME: Final[str] = "lab_report_patient_12345_20260128.txt"
PATIENT_VARIANTS_FILE: Final[str] = "sample_patients.json"
SAMPLE_PATIENT_FILE: Final[str] = "sample_patient.json"
# Backward-compatible fallback for environments that do not include sample_patients.json.
PATIENT_VARIANT_OVERRIDES: Final[list[dict[str, Any]]] = []


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _sample_data_dir() -> Path:
    override = os.getenv("CDSS_SAMPLE_DATA_DIR", "").strip()

    candidates: list[Path] = []
    if override:
        candidates.append(Path(override).expanduser())

    module_path = Path(__file__).resolve()
    candidates.extend(parent / "sample_data" for parent in module_path.parents)
    candidates.append(Path.cwd() / "sample_data")
    candidates.append(Path("/app/sample_data"))

    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if (candidate / SAMPLE_PATIENT_FILE).exists():
            return candidate

    searched = ", ".join(sorted(seen))
    raise FileNotFoundError(
        f"Missing sample patient file '{SAMPLE_PATIENT_FILE}'. Looked in: {searched}"
    )


def _load_sample_patient() -> dict[str, Any]:
    sample_path = _sample_data_dir() / SAMPLE_PATIENT_FILE
    if not sample_path.exists():
        raise FileNotFoundError(f"Missing sample patient file: {sample_path}")

    with sample_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_patient_variants() -> list[dict[str, Any]]:
    variants_path = _sample_data_dir() / PATIENT_VARIANTS_FILE
    if not variants_path.exists():
        return PATIENT_VARIANT_OVERRIDES

    with variants_path.open(encoding="utf-8") as fh:
        loaded = json.load(fh)

    if not isinstance(loaded, list):
        raise ValueError(f"Invalid variants payload in {variants_path}: expected a JSON array.")

    return [item for item in loaded if isinstance(item, dict)]


def _build_canonical_patient(sample: dict[str, Any], now: str) -> dict[str, Any]:
    patient_id = str(sample.get("patient_id") or PATIENT_PROFILE_ID)

    demographics = sample.get("demographics", {})
    vitals = sample.get("vital_signs", {})
    weight = vitals.get("weight", {})
    height = vitals.get("height", {})
    if isinstance(demographics, dict):
        first_name = demographics.get("first_name")
        last_name = demographics.get("last_name")
        full_name = " ".join(part for part in [first_name, last_name] if part)
    else:
        full_name = ""

    active_conditions = []
    for item in sample.get("conditions", []):
        if not isinstance(item, dict):
            continue
        active_conditions.append(
            {
                "code": item.get("icd10_code") or item.get("snomed_ct_code") or "unknown",
                "coding_system": "ICD-10" if item.get("icd10_code") else "SNOMED-CT",
                "display": item.get("description") or item.get("snomed_ct_display") or "Unknown condition",
                "onset_date": item.get("onset_date"),
                "status": item.get("clinical_status") or "active",
            }
        )

    active_medications = []
    for item in sample.get("medications", []):
        if not isinstance(item, dict):
            continue
        dose = item.get("dose")
        dose_unit = item.get("dose_unit")
        if isinstance(dose, str) and dose_unit and dose_unit not in dose:
            dose = f"{dose} {dose_unit}"
        active_medications.append(
            {
                "rxcui": str(item.get("rxnorm_cui") or "unknown"),
                "name": item.get("name") or item.get("generic_name") or "Unknown medication",
                "dose": dose or "unknown",
                "frequency": item.get("frequency_display") or item.get("frequency") or "unknown",
                "start_date": item.get("start_date"),
                "prescriber": item.get("prescriber"),
            }
        )

    allergies = []
    for item in sample.get("allergies", []):
        if not isinstance(item, dict):
            continue
        reactions = item.get("reactions")
        reactions = reactions if isinstance(reactions, list) else []
        first_reaction = reactions[0] if reactions and isinstance(reactions[0], dict) else {}
        severity = first_reaction.get("severity") or item.get("criticality") or "mild"
        if severity == "high":
            severity = "severe"
        elif severity == "low":
            severity = "mild"
        if severity not in {"mild", "moderate", "severe"}:
            severity = "mild"
        allergies.append(
            {
                "substance": item.get("substance") or "Unknown substance",
                "reaction": first_reaction.get("manifestation") or "Unknown reaction",
                "severity": severity,
                "code": item.get("snomed_ct_code"),
                "coding_system": "SNOMED-CT" if item.get("snomed_ct_code") else None,
            }
        )

    recent_labs = []
    for item in sample.get("lab_results", []):
        if not isinstance(item, dict):
            continue
        reference = item.get("reference_range")
        if isinstance(reference, dict):
            reference = reference.get("text")
        recent_labs.append(
            {
                "code": item.get("loinc_code") or "unknown",
                "coding_system": "LOINC",
                "display": item.get("test_name") or "Unknown lab",
                "value": item.get("value", 0),
                "unit": item.get("unit", ""),
                "test_date": item.get("effective_date") or now,
                "reference_range": reference if isinstance(reference, str) else None,
            }
        )

    return {
        "id": patient_id,
        "patient_id": patient_id,
        "doc_type": "patient_profile",
        "demographics": {
            "age": demographics.get("age", 0),
            "sex": str(demographics.get("sex", "unknown")).lower(),
            "weight_kg": weight.get("value", 0) if isinstance(weight, dict) else 0,
            "height_cm": height.get("value", 0) if isinstance(height, dict) else 0,
            "blood_type": demographics.get("blood_type"),
            "name": full_name,
        },
        "active_conditions": active_conditions,
        "active_medications": active_medications,
        "allergies": allergies,
        "recent_labs": recent_labs,
        "last_updated": sample.get("last_updated") or now,
        "created_at": now,
        "updated_at": now,
    }


def _build_variant_patients(base_patient: dict[str, Any], now: str, overrides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    for override in overrides:
        patient_id = str(override.get("patient_id", "")).strip()
        if not patient_id:
            continue

        profile = deepcopy(base_patient)
        profile["id"] = patient_id
        profile["patient_id"] = patient_id

        demographics_override = override.get("demographics")
        if isinstance(demographics_override, dict):
            base_demographics = profile.get("demographics", {})
            profile["demographics"] = {
                **(base_demographics if isinstance(base_demographics, dict) else {}),
                **demographics_override,
            }

        for key in ("active_conditions", "active_medications", "allergies", "recent_labs"):
            value = override.get(key)
            if isinstance(value, list):
                profile[key] = deepcopy(value)

        profile["last_updated"] = override.get("last_updated") or now
        profile["created_at"] = now
        profile["updated_at"] = now
        variants.append(profile)

    return variants


def build_seed_patients(now: str | None = None) -> list[dict[str, Any]]:
    """Build canonical seed patient profiles used across local and in-network seed flows."""
    seed_timestamp = now or datetime.now(UTC).isoformat()
    primary_profile = _build_canonical_patient(_load_sample_patient(), now=seed_timestamp)
    variant_overrides = _load_patient_variants()
    return [primary_profile, *_build_variant_patients(primary_profile, now=seed_timestamp, overrides=variant_overrides)]


def _seed_cosmos(credential: DefaultAzureCredential) -> list[str]:
    endpoint = _required_env("CDSS_AZURE_COSMOS_ENDPOINT")
    database_name = os.getenv("CDSS_AZURE_COSMOS_DATABASE_NAME", "cdss-db")
    container_name = os.getenv("CDSS_AZURE_COSMOS_PATIENT_PROFILES_CONTAINER", "patient-profiles")

    client = CosmosClient(endpoint, credential=credential)
    database = client.get_database_client(database_name)
    container = database.get_container_client(container_name)

    patients = build_seed_patients()
    for patient in patients:
        container.upsert_item(patient)

    return [str(patient.get("patient_id", "unknown")) for patient in patients]


def _seed_blob(credential: DefaultAzureCredential) -> None:
    blob_endpoint = _required_env("CDSS_AZURE_BLOB_ENDPOINT")
    protocol_container = os.getenv("CDSS_AZURE_BLOB_PROTOCOLS_CONTAINER", "treatment-protocols")
    staging_container = os.getenv("CDSS_AZURE_BLOB_STAGING_CONTAINER", "staging-documents")

    client = BlobServiceClient(account_url=blob_endpoint, credential=credential)

    protocol_content = """# Endocrinology Protocol - T2DM with CKD Stage 3
- Prefer SGLT2 inhibitor when clinically appropriate.
- Reassess metformin dose when eGFR <45.
- Monitor UACR and renal function every 3 months.
"""
    lab_content = "HbA1c 8.4; eGFR 42; UACR 110"

    client.get_blob_client(container=protocol_container, blob=PROTOCOL_BLOB_NAME).upload_blob(
        protocol_content.encode("utf-8"),
        overwrite=True,
    )
    client.get_blob_client(container=staging_container, blob=LAB_REPORT_BLOB_NAME).upload_blob(
        lab_content.encode("utf-8"),
        overwrite=True,
    )


def main() -> int:
    try:
        credential = DefaultAzureCredential()
        seeded_patient_ids = _seed_cosmos(credential)
        _seed_blob(credential)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] In-network seed failed: {exc}")
        return 1

    print("[SUCCESS] In-network sample data seeded.")
    print(f"[SUCCESS] Patient profiles upserted ({len(seeded_patient_ids)}): {', '.join(seeded_patient_ids)}")
    print(f"[SUCCESS] Protocol blob uploaded: {PROTOCOL_BLOB_NAME}")
    print(f"[SUCCESS] Lab report blob uploaded: {LAB_REPORT_BLOB_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
