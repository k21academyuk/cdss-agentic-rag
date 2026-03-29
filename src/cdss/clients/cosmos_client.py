"""Azure Cosmos DB client wrapper for patient data, conversations, and agent state."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from azure.core.credentials import TokenCredential
from azure.cosmos import CosmosClient, exceptions as cosmos_exceptions
from azure.identity import DefaultAzureCredential

from cdss.core.config import Settings, get_settings
from cdss.core.exceptions import AzureServiceError
from cdss.core.logging import get_logger

logger = get_logger(__name__)

# Logical container identifiers used by the Python codebase.
CONTAINER_PATIENT_PROFILES = "patient_profiles"
CONTAINER_CONVERSATIONS = "conversation_history"
CONTAINER_EMBEDDING_CACHE = "embedding_cache"
CONTAINER_AUDIT_LOG = "audit_log"
CONTAINER_AGENT_STATE = "agent_state"


class CosmosDBClient:
    """Wrapper for Azure Cosmos DB for NoSQL with vector search.

    Manages patient profiles, conversation history, embedding cache,
    audit logs, and agent state across dedicated containers.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize Cosmos DB client and container references.

        Args:
            settings: Application settings. If None, loads from environment.
        """
        self._settings = settings or get_settings()

        try:
            credential: str | TokenCredential
            auth_mode = "account_key"
            if self._settings.cosmos_db_use_entra_id or not self._settings.cosmos_db_key:
                credential = DefaultAzureCredential()
                auth_mode = "entra_id"
            else:
                credential = self._settings.cosmos_db_key

            self._client = CosmosClient(
                url=self._settings.cosmos_db_endpoint,
                credential=credential,
            )
            self._database = self._client.get_database_client(self._settings.cosmos_db_database_name)
            self._container_name_map: dict[str, str] = {
                CONTAINER_PATIENT_PROFILES: self._settings.azure_cosmos_patient_profiles_container,
                CONTAINER_CONVERSATIONS: self._settings.azure_cosmos_conversation_history_container,
                CONTAINER_EMBEDDING_CACHE: self._settings.azure_cosmos_embedding_cache_container,
                CONTAINER_AUDIT_LOG: self._settings.azure_cosmos_audit_log_container,
                CONTAINER_AGENT_STATE: self._settings.azure_cosmos_agent_state_container,
            }

            self._containers = {
                logical_name: self._database.get_container_client(physical_name)
                for logical_name, physical_name in self._container_name_map.items()
            }
            for logical_name, physical_name in self._container_name_map.items():
                self._containers[physical_name] = self._containers[logical_name]

            logger.info(
                "CosmosDBClient initialized",
                endpoint=self._settings.cosmos_db_endpoint,
                database=self._settings.cosmos_db_database_name,
                auth_mode=auth_mode,
                containers=self._container_name_map,
            )

        except Exception as exc:
            logger.error("Failed to initialize CosmosDBClient", error=str(exc))
            raise AzureServiceError(f"Failed to initialize Cosmos DB client: {exc}") from exc

    def _get_container(self, name: str) -> Any:
        """Get a container client by name.

        Args:
            name: Container name.

        Returns:
            Container client instance.

        Raises:
            AzureServiceError: If the container name is not recognized.
        """
        container = self._containers.get(name)
        if container is None:
            raise AzureServiceError(f"Unknown container: '{name}'. Valid containers: {list(self._containers.keys())}")
        return container

    # -------------------------------------------------------------------------
    # Patient Profiles
    # -------------------------------------------------------------------------

    async def get_patient_profile(self, patient_id: str) -> dict | None:
        """Retrieve a patient profile by patient ID.

        Args:
            patient_id: Unique patient identifier.

        Returns:
            Patient profile dict, or None if not found.

        Raises:
            AzureServiceError: If the read operation fails.
        """
        container = self._get_container(CONTAINER_PATIENT_PROFILES)

        try:
            item = container.read_item(item=patient_id, partition_key=patient_id)
            logger.debug("Patient profile retrieved", patient_id=patient_id)
            return dict(item)

        except cosmos_exceptions.CosmosResourceNotFoundError:
            logger.debug("Patient profile not found", patient_id=patient_id)
            return None

        except Exception as exc:
            logger.error(
                "Failed to get patient profile",
                patient_id=patient_id,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to retrieve patient profile '{patient_id}': {exc}") from exc

    async def upsert_patient_profile(self, profile: dict) -> dict:
        """Create or update a patient profile.

        Args:
            profile: Patient profile dict. Must include 'id' and 'patient_id' fields.

        Returns:
            The upserted profile dict as returned by Cosmos DB.

        Raises:
            AzureServiceError: If the upsert operation fails.
        """
        container = self._get_container(CONTAINER_PATIENT_PROFILES)

        try:
            profile["updated_at"] = datetime.now(timezone.utc).isoformat()
            if "created_at" not in profile:
                profile["created_at"] = profile["updated_at"]

            result = container.upsert_item(body=profile)
            logger.info(
                "Patient profile upserted",
                patient_id=profile.get("patient_id", profile.get("id")),
            )
            return dict(result)

        except Exception as exc:
            logger.error(
                "Failed to upsert patient profile",
                patient_id=profile.get("patient_id", profile.get("id")),
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to upsert patient profile: {exc}") from exc

    async def search_patient_profiles(
        self,
        search: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Search patient profiles with lightweight text filtering.

        Args:
            search: Optional free-text query (patient ID, condition, medication).
            limit: Maximum number of documents to read from Cosmos.

        Returns:
            Matching patient profile dictionaries.

        Raises:
            AzureServiceError: If the query operation fails.
        """
        container = self._get_container(CONTAINER_PATIENT_PROFILES)

        try:
            query = "SELECT TOP @limit * FROM c"
            parameters: list[dict[str, Any]] = [
                {"name": "@limit", "value": limit},
            ]
            documents = list(
                container.query_items(
                    query=query,
                    parameters=parameters,
                    enable_cross_partition_query=True,
                )
            )

            profiles = [dict(doc) for doc in documents]
            if not search:
                return profiles

            search_term = search.strip().lower()
            if not search_term:
                return profiles

            return [profile for profile in profiles if self._profile_matches_search(profile, search_term)]

        except Exception as exc:
            logger.error(
                "Failed to search patient profiles",
                search=search,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to search patient profiles: {exc}") from exc

    @staticmethod
    def _profile_matches_search(profile: dict[str, Any], search_term: str) -> bool:
        patient_id = str(profile.get("patient_id", "")).lower()
        if search_term in patient_id:
            return True

        demographics = profile.get("demographics", {})
        if isinstance(demographics, dict):
            name = str(demographics.get("name", "")).lower()
            if search_term in name:
                return True

        for condition in profile.get("active_conditions", []):
            if isinstance(condition, dict):
                display = str(condition.get("display", "")).lower()
                if search_term in display:
                    return True

        for medication in profile.get("active_medications", []):
            if isinstance(medication, dict):
                name = str(medication.get("name", "")).lower()
                if search_term in name:
                    return True

        return False

    async def vector_search_patients(self, query_vector: list[float], top: int = 10) -> list[dict]:
        """Search patient profiles using vector similarity.

        Uses the Cosmos DB for NoSQL vector search capability to find
        semantically similar patient profiles.

        Args:
            query_vector: Query embedding vector.
            top: Maximum number of results to return.

        Returns:
            List of matching patient profile dicts with similarity scores.

        Raises:
            AzureServiceError: If the vector search fails.
        """
        container = self._get_container(CONTAINER_PATIENT_PROFILES)

        try:
            query = (
                "SELECT TOP @top c.id, c.patient_id, c.name, c.conditions, "
                "c.medications, c.allergies, c.demographics, "
                "VectorDistance(c.embedding, @queryVector) AS similarity_score "
                "FROM c "
                "ORDER BY VectorDistance(c.embedding, @queryVector)"
            )

            parameters: list[dict[str, Any]] = [
                {"name": "@top", "value": top},
                {"name": "@queryVector", "value": query_vector},
            ]

            results = list(
                container.query_items(
                    query=query,
                    parameters=parameters,
                    enable_cross_partition_query=True,
                )
            )

            logger.info(
                "Vector search on patient profiles completed",
                results_count=len(results),
                top=top,
            )

            return [dict(r) for r in results]

        except Exception as exc:
            logger.error(
                "Vector search on patient profiles failed",
                error=str(exc),
            )
            raise AzureServiceError(f"Vector search on patient profiles failed: {exc}") from exc

    # -------------------------------------------------------------------------
    # Conversation History
    # -------------------------------------------------------------------------

    async def save_conversation_turn(self, turn: dict) -> dict:
        """Save a single conversation turn.

        Args:
            turn: Conversation turn dict. Must include 'id' and 'session_id'.
                  Expected keys: session_id, role, content, timestamp, metadata.

        Returns:
            The saved turn dict as returned by Cosmos DB.

        Raises:
            AzureServiceError: If the save operation fails.
        """
        container = self._get_container(CONTAINER_CONVERSATIONS)

        try:
            if "timestamp" not in turn:
                turn["timestamp"] = datetime.now(timezone.utc).isoformat()

            result = container.create_item(body=turn)
            logger.debug(
                "Conversation turn saved",
                session_id=turn.get("session_id"),
                turn_id=turn.get("id"),
            )
            return dict(result)

        except Exception as exc:
            logger.error(
                "Failed to save conversation turn",
                session_id=turn.get("session_id"),
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to save conversation turn: {exc}") from exc

    async def get_conversation_history(self, session_id: str, limit: int = 20) -> list[dict]:
        """Retrieve conversation history for a session.

        Args:
            session_id: Session identifier to retrieve history for.
            limit: Maximum number of turns to return, ordered by timestamp descending.

        Returns:
            List of conversation turn dicts, most recent first.

        Raises:
            AzureServiceError: If the query fails.
        """
        container = self._get_container(CONTAINER_CONVERSATIONS)

        try:
            query = "SELECT TOP @limit * FROM c WHERE c.session_id = @sessionId ORDER BY c.timestamp DESC"

            parameters: list[dict[str, Any]] = [
                {"name": "@limit", "value": limit},
                {"name": "@sessionId", "value": session_id},
            ]

            results = list(
                container.query_items(
                    query=query,
                    parameters=parameters,
                    partition_key=session_id,
                )
            )

            logger.debug(
                "Conversation history retrieved",
                session_id=session_id,
                turns_count=len(results),
            )

            return [dict(r) for r in results]

        except Exception as exc:
            logger.error(
                "Failed to get conversation history",
                session_id=session_id,
                error=str(exc),
            )
            raise AzureServiceError(
                f"Failed to retrieve conversation history for session '{session_id}': {exc}"
            ) from exc

    # -------------------------------------------------------------------------
    # Embedding Cache
    # -------------------------------------------------------------------------

    async def get_cached_embedding(self, source_type: str, content_hash: str) -> list[float] | None:
        """Retrieve a cached embedding by source type and content hash.

        Args:
            source_type: Type of source content (e.g., "patient_record", "protocol").
            content_hash: SHA-256 hash of the content that was embedded.

        Returns:
            The cached embedding vector, or None if not found.

        Raises:
            AzureServiceError: If the lookup fails.
        """
        container = self._get_container(CONTAINER_EMBEDDING_CACHE)
        cache_id = f"{source_type}:{content_hash}"

        try:
            item = container.read_item(item=cache_id, partition_key=source_type)
            logger.debug(
                "Embedding cache hit",
                source_type=source_type,
                content_hash=content_hash,
            )
            return item.get("embedding")

        except cosmos_exceptions.CosmosResourceNotFoundError:
            logger.debug(
                "Embedding cache miss",
                source_type=source_type,
                content_hash=content_hash,
            )
            return None

        except Exception as exc:
            logger.error(
                "Failed to get cached embedding",
                source_type=source_type,
                content_hash=content_hash,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to retrieve cached embedding: {exc}") from exc

    async def cache_embedding(self, source_type: str, content_hash: str, embedding: list[float]) -> None:
        """Cache an embedding vector for future retrieval.

        Args:
            source_type: Type of source content.
            content_hash: SHA-256 hash of the content that was embedded.
            embedding: The embedding vector to cache.

        Raises:
            AzureServiceError: If the cache write fails.
        """
        container = self._get_container(CONTAINER_EMBEDDING_CACHE)
        cache_id = f"{source_type}:{content_hash}"

        try:
            cache_entry = {
                "id": cache_id,
                "source_type": source_type,
                "content_hash": content_hash,
                "embedding": embedding,
                "dimensions": len(embedding),
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "ttl": 86400 * 30,  # 30 days TTL
            }

            container.upsert_item(body=cache_entry)
            logger.debug(
                "Embedding cached",
                source_type=source_type,
                content_hash=content_hash,
                dimensions=len(embedding),
            )

        except Exception as exc:
            logger.error(
                "Failed to cache embedding",
                source_type=source_type,
                content_hash=content_hash,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to cache embedding: {exc}") from exc

    # -------------------------------------------------------------------------
    # Audit Log
    # -------------------------------------------------------------------------

    async def log_audit_event(self, event: dict) -> dict:
        """Log an audit event for compliance tracking.

        Args:
            event: Audit event dict. Expected keys: event_type, user_id,
                   patient_id (optional), action, details, timestamp.

        Returns:
            The saved audit event dict.

        Raises:
            AzureServiceError: If the logging operation fails.
        """
        container = self._get_container(CONTAINER_AUDIT_LOG)

        try:
            if "timestamp" not in event:
                event["timestamp"] = datetime.now(timezone.utc).isoformat()
            if "epoch_ms" not in event:
                event["epoch_ms"] = int(time.time() * 1000)

            result = container.create_item(body=event)
            logger.info(
                "Audit event logged",
                event_id=event.get("id"),
                event_type=event.get("event_type"),
                patient_id=event.get("patient_id"),
            )
            return dict(result)

        except Exception as exc:
            logger.error(
                "Failed to log audit event",
                event_type=event.get("event_type"),
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to log audit event: {exc}") from exc

    async def get_audit_trail(
        self,
        patient_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Retrieve audit trail with optional filtering.

        Args:
            patient_id: Optional patient ID to filter audit events.
            date_from: Optional start date (ISO 8601 format) for date range filter.
            date_to: Optional end date (ISO 8601 format) for date range filter.
            limit: Maximum number of events to return.

        Returns:
            List of audit event dicts, ordered by timestamp descending.

        Raises:
            AzureServiceError: If the query fails.
        """
        container = self._get_container(CONTAINER_AUDIT_LOG)

        try:
            conditions: list[str] = []
            parameters: list[dict[str, Any]] = [
                {"name": "@limit", "value": limit},
            ]

            if patient_id is not None:
                conditions.append("c.patient_id = @patientId")
                parameters.append({"name": "@patientId", "value": patient_id})

            if date_from is not None:
                conditions.append("c.timestamp >= @dateFrom")
                parameters.append({"name": "@dateFrom", "value": date_from})

            if date_to is not None:
                conditions.append("c.timestamp <= @dateTo")
                parameters.append({"name": "@dateTo", "value": date_to})

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

            query = f"SELECT TOP @limit * FROM c {where_clause} ORDER BY c.timestamp DESC"

            results = list(
                container.query_items(
                    query=query,
                    parameters=parameters,
                    enable_cross_partition_query=True,
                )
            )

            logger.debug(
                "Audit trail retrieved",
                patient_id=patient_id,
                date_from=date_from,
                date_to=date_to,
                results_count=len(results),
            )

            return [dict(r) for r in results]

        except Exception as exc:
            logger.error(
                "Failed to get audit trail",
                patient_id=patient_id,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to retrieve audit trail: {exc}") from exc

    # -------------------------------------------------------------------------
    # Agent State
    # -------------------------------------------------------------------------

    async def save_agent_state(self, session_id: str, state: dict) -> dict:
        """Save or update agent state for a session.

        Args:
            session_id: Session identifier.
            state: Agent state dict containing workflow state, intermediate results, etc.

        Returns:
            The saved state dict as returned by Cosmos DB.

        Raises:
            AzureServiceError: If the save operation fails.
        """
        container = self._get_container(CONTAINER_AGENT_STATE)

        try:
            state_doc = {
                "id": session_id,
                "session_id": session_id,
                "state": state,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            result = container.upsert_item(body=state_doc)
            logger.debug(
                "Agent state saved",
                session_id=session_id,
            )
            return dict(result)

        except Exception as exc:
            logger.error(
                "Failed to save agent state",
                session_id=session_id,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to save agent state for session '{session_id}': {exc}") from exc

    async def get_agent_state(self, session_id: str) -> dict | None:
        """Retrieve agent state for a session.

        Args:
            session_id: Session identifier.

        Returns:
            Agent state dict, or None if no state exists for the session.

        Raises:
            AzureServiceError: If the read operation fails.
        """
        container = self._get_container(CONTAINER_AGENT_STATE)

        try:
            item = container.read_item(item=session_id, partition_key=session_id)
            logger.debug("Agent state retrieved", session_id=session_id)
            return dict(item).get("state")

        except cosmos_exceptions.CosmosResourceNotFoundError:
            logger.debug("Agent state not found", session_id=session_id)
            return None

        except Exception as exc:
            logger.error(
                "Failed to get agent state",
                session_id=session_id,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to retrieve agent state for session '{session_id}': {exc}") from exc

    async def upsert_embedding_documents(self, documents: list[dict[str, Any]]) -> int:
        """Upsert embedding documents into the embedding cache container.

        Args:
            documents: Embedding documents shaped for the embedding cache container.

        Returns:
            Number of successfully upserted embedding documents.

        Raises:
            AzureServiceError: If upsert operation fails.
        """
        container = self._get_container(CONTAINER_EMBEDDING_CACHE)

        try:
            upserted = 0
            for document in documents:
                container.upsert_item(body=document)
                upserted += 1

            logger.debug(
                "Embedding documents upserted",
                count=upserted,
            )
            return upserted

        except Exception as exc:
            logger.error(
                "Failed to upsert embedding documents",
                count=len(documents),
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to upsert embedding documents: {exc}") from exc

    # -------------------------------------------------------------------------
    # Ingestion Status (durable, multi-replica safe)
    # -------------------------------------------------------------------------

    async def upsert_ingestion_status(
        self,
        document_id: str,
        status: dict[str, Any],
        partition_key: str = "ingestion_status",
        doc_type: str = "ingestion_status",
    ) -> dict:
        """Create or update ingestion status for a document.

        Stores status records in the agent-state container under a shared
        partition to support consistent reads across multiple API replicas.

        Args:
            document_id: Ingestion document identifier.
            status: Status payload to persist.
            partition_key: Cosmos partition key value.
            doc_type: Optional discriminator for filtering/debugging.

        Returns:
            The persisted status record.

        Raises:
            AzureServiceError: If the upsert operation fails.
        """
        container = self._get_container(CONTAINER_AGENT_STATE)

        try:
            now = datetime.now(timezone.utc).isoformat()
            record = dict(status)
            record["id"] = document_id
            record["session_id"] = partition_key
            record["document_id"] = document_id
            record["doc_type"] = doc_type
            record["updated_at"] = record.get("updated_at", now)
            record["created_at"] = record.get("created_at", now)

            result = container.upsert_item(body=record)
            logger.debug(
                "Ingestion status upserted",
                document_id=document_id,
                partition_key=partition_key,
            )
            return dict(result)

        except Exception as exc:
            logger.error(
                "Failed to upsert ingestion status",
                document_id=document_id,
                partition_key=partition_key,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to upsert ingestion status for '{document_id}': {exc}") from exc

    async def get_ingestion_status(
        self,
        document_id: str,
        partition_key: str = "ingestion_status",
    ) -> dict | None:
        """Retrieve ingestion status for a document.

        Args:
            document_id: Ingestion document identifier.
            partition_key: Cosmos partition key value.

        Returns:
            Persisted ingestion status dictionary, or None if not found.

        Raises:
            AzureServiceError: If the read operation fails unexpectedly.
        """
        container = self._get_container(CONTAINER_AGENT_STATE)

        try:
            item = container.read_item(item=document_id, partition_key=partition_key)
            logger.debug(
                "Ingestion status retrieved",
                document_id=document_id,
                partition_key=partition_key,
            )
            return dict(item)

        except cosmos_exceptions.CosmosResourceNotFoundError:
            logger.debug(
                "Ingestion status not found",
                document_id=document_id,
                partition_key=partition_key,
            )
            return None

        except Exception as exc:
            logger.error(
                "Failed to get ingestion status",
                document_id=document_id,
                partition_key=partition_key,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to retrieve ingestion status for '{document_id}': {exc}") from exc

    async def delete_ingestion_status(
        self,
        document_id: str,
        partition_key: str = "ingestion_status",
    ) -> bool:
        """Delete ingestion status for a document.

        Args:
            document_id: Ingestion document identifier.
            partition_key: Cosmos partition key value.

        Returns:
            True if delete succeeded or the document was already absent.

        Raises:
            AzureServiceError: If the delete operation fails unexpectedly.
        """
        container = self._get_container(CONTAINER_AGENT_STATE)

        try:
            container.delete_item(item=document_id, partition_key=partition_key)
            logger.debug(
                "Ingestion status deleted",
                document_id=document_id,
                partition_key=partition_key,
            )
            return True
        except cosmos_exceptions.CosmosResourceNotFoundError:
            logger.debug(
                "Ingestion status delete skipped; not found",
                document_id=document_id,
                partition_key=partition_key,
            )
            return True
        except Exception as exc:
            logger.error(
                "Failed to delete ingestion status",
                document_id=document_id,
                partition_key=partition_key,
                error=str(exc),
            )
            raise AzureServiceError(f"Failed to delete ingestion status for '{document_id}': {exc}") from exc
